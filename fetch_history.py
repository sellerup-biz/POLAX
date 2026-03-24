"""
POLAX — загрузка истории (все 3 магазина, все месяцы)
Период задаётся через HISTORY_FROM / HISTORY_TO (env или дефолт)
Запускается вручную через history.yml

Что исправлено vs предыдущей версии:
  • total = только PLN (allegro-pl + allegro-business-pl) — без смешивания CZK/HUF/EUR
  • расходы собираются для ВСЕХ трёх магазинов
  • биллинг запрашивается по ВСЕМ маркетплейсам (PL/CZ/HU/SK)
  • CZK/HUF/EUR расходы конвертируются в PLN по среднему курсу НБП за месяц
  • SUM добавлен в BILLING_MAP как IGNORE
"""
import requests, json, os, base64, calendar
from datetime import datetime
from nacl import encoding, public
from collections import defaultdict

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

HISTORY_FROM = os.environ.get("HISTORY_FROM", "2026-01-01")
HISTORY_TO   = os.environ.get("HISTORY_TO",   "2026-03-31")

MONTH_RU = {1:"Янв",2:"Фев",3:"Мар",4:"Апр",5:"Май",6:"Июн",
            7:"Июл",8:"Авг",9:"Сен",10:"Окт",11:"Ноя",12:"Дек"}

SHOPS = {
    "Mlot_i_Klucz":   {
        "client_id":     os.environ.get("CLIENT_ID_MLOT",""),
        "client_secret": os.environ.get("CLIENT_SECRET_MLOT",""),
        "refresh_token": os.environ.get("REFRESH_TOKEN_MLOT",""),
        "secret_name":   "REFRESH_TOKEN_MLOT",
    },
    "PolaxEuroGroup": {
        "client_id":     os.environ.get("CLIENT_ID_POLAX",""),
        "client_secret": os.environ.get("CLIENT_SECRET_POLAX",""),
        "refresh_token": os.environ.get("REFRESH_TOKEN_POLAX",""),
        "secret_name":   "REFRESH_TOKEN_POLAX",
    },
    "Sila_Narzedzi":  {
        "client_id":     os.environ.get("CLIENT_ID_SILA",""),
        "client_secret": os.environ.get("CLIENT_SECRET_SILA",""),
        "refresh_token": os.environ.get("REFRESH_TOKEN_SILA",""),
        "secret_name":   "REFRESH_TOKEN_SILA",
    },
}

BILLING_MAP = {
    "SUC":"commission","SUJ":"commission","LDS":"commission","HUN":"commission",
    "REF":"zwrot_commission",
    "HB4":"delivery","HB1":"delivery","HB8":"delivery","HB9":"delivery",
    "DPB":"delivery","DXP":"delivery","HXO":"delivery","HLB":"delivery",
    "ORB":"delivery","DHR":"delivery","DAP":"delivery","DKP":"delivery","DPP":"delivery",
    "GLS":"delivery","UPS":"delivery","UPD":"delivery",
    "DTR":"delivery","DPA":"delivery","ITR":"delivery","HLA":"delivery",
    "DDP":"delivery","HB3":"delivery","DPS":"delivery","UTR":"delivery",
    "NSP":"ads","DPG":"ads","WYR":"ads","POD":"ads","BOL":"ads","EMF":"ads","CPC":"ads",
    "FEA":"ads","BRG":"ads","FSF":"ads",
    "SB2":"subscription","ABN":"subscription",
    "RET":"discount","PS1":"discount",
    "PAD":"IGNORE",
    "SUM":"IGNORE",  # Podsumowanie miesiąca — итоговая строка, всегда 0.00
}

COST_CATS = ["commission","delivery","ads","subscription","discount"]


def get_billing_cat(tid, tnam):
    if tid in BILLING_MAP:
        return BILLING_MAP[tid]
    n = tnam.lower()
    if "kampanii" in n or "kampania" in n:
        return "ads"
    if any(x in n for x in ["prowizja","lokalna dopłata","opłata transakcyjna"]):
        return "commission"
    if any(x in n for x in ["dostawa","kurier","inpost","dpd","gls","ups","orlen","poczta",
                              "przesyłka","fulfillment","one kurier","allegro delivery",
                              "packeta","international","dodatkowa za dostawę"]):
        return "delivery"
    if any(x in n for x in ["kampani","reklam","promowanie","wyróżnienie","pogrubienie",
                              "podświetlenie","strona działu","pakiet promo","cpc","ads"]):
        return "ads"
    if any(x in n for x in ["abonament","smart"]):
        return "subscription"
    if any(x in n for x in ["rozliczenie akcji","wyrównanie w programie allegro","rabat"]):
        return "discount"
    if any(x in n for x in ["zwrot kosztów","zwrot prowizji"]):
        return "zwrot_commission"
    if "pobranie opłat z wpływów" in n:
        return "IGNORE"
    return "other"


# ── AUTH & GITHUB ─────────────────────────────────────────────

def get_gh_pubkey():
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
        headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"})
    return r.json()


def save_token(secret_name, new_rt, pubkey):
    if not new_rt or not GH_TOKEN:
        return
    try:
        pk  = public.PublicKey(pubkey["key"].encode(), encoding.Base64Encoder())
        enc = base64.b64encode(public.SealedBox(pk).encrypt(new_rt.encode())).decode()
        resp = requests.put(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
            headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"},
            json={"encrypted_value":enc,"key_id":pubkey["key_id"]})
        if resp.status_code in (201, 204):
            print(f"    ✅ Токен {secret_name} сохранён")
        else:
            print(f"    ⚠ Токен {secret_name}: статус {resp.status_code}")
    except Exception as e:
        print(f"    ⚠ Ошибка токена {secret_name}: {e}")


def get_token(shop):
    r = requests.post(
        "https://allegro.pl/auth/oauth/token",
        auth=(shop["client_id"], shop["client_secret"]),
        data={"grant_type":"refresh_token",
              "refresh_token":shop["refresh_token"],
              "redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d:
        print(f"    ОШИБКА токена: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token","")


def hdrs(t):
    return {"Authorization":f"Bearer {t}","Accept":"application/vnd.allegro.public.v1+json"}


def get_tz(month):
    return 2 if 3 <= month <= 10 else 1


# ── NBP КУРСЫ ─────────────────────────────────────────────────

def get_nbp_monthly_rate(currency_code, year, month):
    """
    Средний курс НБП за месяц (PLN за 1 единицу иностранной валюты).
    currency_code: 'czk', 'huf', 'eur' — строчными
    Возвращает float или None если данных нет.
    """
    last_day = calendar.monthrange(year, month)[1]
    d_from   = f"{year}-{month:02d}-01"
    d_to     = f"{year}-{month:02d}-{last_day:02d}"
    url = f"https://api.nbp.pl/api/exchangerates/rates/a/{currency_code}/{d_from}/{d_to}/?format=json"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            rates = resp.json().get("rates", [])
            if rates:
                avg = sum(r["mid"] for r in rates) / len(rates)
                return round(avg, 6)
        print(f"    ⚠ NBP {currency_code.upper()} {d_from}..{d_to}: HTTP {resp.status_code}")
    except Exception as e:
        print(f"    ⚠ NBP {currency_code.upper()}: {e}")
    return None


# ── ПРОДАЖИ ───────────────────────────────────────────────────

def get_sales_for_month(token, year, month):
    """
    Продажи по всем маркетплейсам.
    Возвращает:
      allegro-pl  = PLN (включает allegro-business-pl)
      allegro-cz  = CZK (нативная валюта)
      allegro-hu  = HUF (нативная валюта)
      allegro-sk  = EUR (нативная валюта)
    """
    last_day = calendar.monthrange(year, month)[1]
    tz       = get_tz(month)
    d_from   = f"{year}-{month:02d}-01T00:00:00+0{tz}:00"
    d_to     = f"{year}-{month:02d}-{last_day:02d}T23:59:59+0{tz}:00"
    by_mkt   = defaultdict(float)

    for mkt in ["allegro-pl","allegro-business-pl","allegro-cz","allegro-hu","allegro-sk"]:
        offset = 0
        while True:
            resp = requests.get(
                "https://api.allegro.pl/payments/payment-operations",
                headers=hdrs(token),
                params={"group":"INCOME","occurredAt.gte":d_from,"occurredAt.lte":d_to,
                        "marketplaceId":mkt,"limit":50,"offset":offset})
            if resp.status_code != 200:
                print(f"      ⚠ payments {mkt}: HTTP {resp.status_code}")
                break
            ops = resp.json().get("paymentOperations",[])
            for op in ops:
                try:
                    by_mkt[mkt] += float(op["value"]["amount"])
                except Exception:
                    pass
            if len(ops) < 50:
                break
            offset += 50

    return {
        # PLN: pl + business-pl суммируются → одно число
        "allegro-pl": round(by_mkt["allegro-pl"] + by_mkt["allegro-business-pl"], 2),
        "allegro-cz": round(by_mkt["allegro-cz"], 2),
        "allegro-hu": round(by_mkt["allegro-hu"], 2),
        "allegro-sk": round(by_mkt["allegro-sk"], 2),
    }


# ── РАСХОДЫ ───────────────────────────────────────────────────

def get_billing_for_month(token, year, month, marketplace_id=None):
    """
    Расходы за месяц в нативной валюте маркетплейса.
    marketplace_id=None    → allegro-pl (PLN, включает business-pl автоматически)
    marketplace_id=str     → конкретный рынок (CZK/HUF/EUR)

    allegro-business-pl НЕ запрашивается отдельно — вернул бы те же данные (двойной счёт).
    """
    last_day = calendar.monthrange(year, month)[1]
    tz       = get_tz(month)
    d_from   = f"{year}-{month:02d}-01T00:00:00+0{tz}:00"
    d_to     = f"{year}-{month:02d}-{last_day:02d}T23:59:59+0{tz}:00"

    costs  = {cat: 0.0 for cat in COST_CATS}
    offset = 0
    params = {"occurredAt.gte":d_from,"occurredAt.lte":d_to,"limit":100}
    if marketplace_id:
        params["marketplaceId"] = marketplace_id

    while True:
        params["offset"] = offset
        resp = requests.get(
            "https://api.allegro.pl/billing/billing-entries",
            headers=hdrs(token),
            params=params)
        if resp.status_code != 200:
            print(f"      ⚠ billing {marketplace_id or 'pl'}: HTTP {resp.status_code}")
            break

        entries = resp.json().get("billingEntries",[])
        for e in entries:
            try:
                amt  = float(e["value"]["amount"])
                cat  = get_billing_cat(e["type"]["id"], e["type"]["name"])
                if cat == "IGNORE":
                    continue
                if cat == "other":
                    # Неизвестный type.id — логируем для пополнения BILLING_MAP
                    print(f"      ⚠ UNKNOWN: {e['type']['id']} '{e['type']['name']}' {amt:.2f}")
                    continue
                if amt < 0:
                    if cat in costs:
                        costs[cat] += abs(amt)
                elif amt > 0:
                    if cat == "zwrot_commission":
                        costs["commission"] = max(0.0, costs["commission"] - amt)
                    elif cat == "delivery":
                        costs["delivery"]   = max(0.0, costs["delivery"] - amt)
                    elif cat == "discount":
                        costs["discount"]  += amt
            except Exception:
                pass

        if len(entries) < 100:
            break
        offset += 100

    return {k: round(v, 2) for k, v in costs.items()}


# ── DATA.JSON ─────────────────────────────────────────────────

def load_data():
    try:
        with open("data.json") as f:
            return json.load(f)
    except Exception:
        return {"days":[],"months":[]}


def save_data(data):
    with open("data.json","w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",",":"))


def update_months(data):
    """Пересчитываем месячные агрегаты из дневных записей."""
    def empty_costs():
        return {"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0}
    def empty_shop_costs():
        return {"Mlot_i_Klucz":empty_costs(),"PolaxEuroGroup":empty_costs(),"Sila_Narzedzi":empty_costs()}
    months_map = defaultdict(lambda:{
        "Mlot_i_Klucz":0,"PolaxEuroGroup":0,"Sila_Narzedzi":0,
        "countries":{"allegro-pl":0,"allegro-cz":0,"allegro-hu":0,"allegro-sk":0},
        "costs":empty_costs(),
        "shop_costs":empty_shop_costs(),
    })
    for day in data["days"]:
        raw = day["date"][:7]
        y, mo = int(raw[:4]), int(raw[5:7])
        mk = MONTH_RU[mo] + " " + str(y)
        for shop in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"]:
            months_map[mk][shop] = round(months_map[mk][shop] + day.get(shop, 0), 2)
        for c in ["allegro-pl","allegro-cz","allegro-hu","allegro-sk"]:
            months_map[mk]["countries"][c] = round(
                months_map[mk]["countries"][c] + day.get("countries",{}).get(c, 0), 2)
        for cat in COST_CATS:
            months_map[mk]["costs"][cat] = round(
                months_map[mk]["costs"][cat] + day.get("costs",{}).get(cat, 0), 2)
        for shop in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"]:
            sc = day.get("shop_costs", {}).get(shop, {})
            for cat in COST_CATS:
                months_map[mk]["shop_costs"][shop][cat] = round(
                    months_map[mk]["shop_costs"][shop][cat] + sc.get(cat, 0), 2)

    MONTH_RU_REV = {v:k for k,v in MONTH_RU.items()}
    data["months"] = [
        {"month":k,**v}
        for k,v in sorted(
            months_map.items(),
            key=lambda x: (int(x[0][-4:]), MONTH_RU_REV[x[0][:3]])
        )
    ]


def get_months_in_range(date_from, date_to):
    months = []
    df  = datetime.strptime(date_from, "%Y-%m-%d")
    dt  = datetime.strptime(date_to,   "%Y-%m-%d")
    cur = datetime(df.year, df.month, 1)
    while cur <= dt:
        months.append((cur.year, cur.month))
        if cur.month == 12:
            cur = datetime(cur.year+1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month+1, 1)
    return months


# ── MAIN ──────────────────────────────────────────────────────

print(f"История: {HISTORY_FROM} → {HISTORY_TO}")
months = get_months_in_range(HISTORY_FROM, HISTORY_TO)
print(f"Месяцев: {len(months)}")

data   = load_data()
pubkey = get_gh_pubkey()

# ── ШАГ 1: Получаем курсы НБП для каждого месяца ─────────────
# (один раз, до начала работы с магазинами)
print("\n── Курсы НБП ────────────────────────────────────────────")
MONTH_RU_REV = {v:k for k,v in MONTH_RU.items()}
nbp_by_month = {}

for year, month in months:
    mk    = MONTH_RU[month] + " " + str(year)
    rates = {}
    for curr in ["czk","huf","eur"]:
        r = get_nbp_monthly_rate(curr, year, month)
        rates[curr.upper()] = r if r is not None else 0.0
    nbp_by_month[mk] = rates
    print(f"  {mk}: CZK={rates['CZK']:.6f}  HUF={rates['HUF']:.8f}  EUR={rates['EUR']:.4f}")

# ── ШАГ 2: Собираем данные по магазинам (строго последовательно) ─
# month_data[mk][shop_name] = {sales, total (PLN), costs_pln}

month_data = defaultdict(lambda: {
    "Mlot_i_Klucz":   {"sales":{},"total":0.0,"costs_pln":{c:0.0 for c in COST_CATS}},
    "PolaxEuroGroup": {"sales":{},"total":0.0,"costs_pln":{c:0.0 for c in COST_CATS}},
    "Sila_Narzedzi":  {"sales":{},"total":0.0,"costs_pln":{c:0.0 for c in COST_CATS}},
})

for shop_name, shop in SHOPS.items():
    print(f"\n{'='*60}")
    print(f"  МАГАЗИН: {shop_name}")
    print(f"{'='*60}")

    token, new_rt = get_token(shop)
    if not token:
        print("  ❌ Токен не получен — пропускаем магазин")
        continue
    # ОБЯЗАТЕЛЬНО сохраняем токен сразу после получения
    save_token(shop["secret_name"], new_rt, pubkey)

    for year, month in months:
        mk    = MONTH_RU[month] + " " + str(year)
        rates = nbp_by_month[mk]
        print(f"\n  ── {mk} ──")

        # ── Продажи ──────────────────────────────────────────
        sales = get_sales_for_month(token, year, month)
        # total = все рынки магазина в PLN-эквиваленте:
        #   PLN + CZK×курс_НБП + HUF×курс_НБП + EUR×курс_НБП
        czk_pln = round(sales["allegro-cz"] * rates["CZK"], 2)
        huf_pln = round(sales["allegro-hu"] * rates["HUF"], 2)
        eur_pln = round(sales["allegro-sk"] * rates["EUR"], 2)
        total   = round(sales["allegro-pl"] + czk_pln + huf_pln + eur_pln, 2)
        month_data[mk][shop_name]["sales"] = sales
        month_data[mk][shop_name]["total"] = total
        print(f"    Продажи → "
              f"PLN {sales['allegro-pl']:>10,.2f}  "
              f"CZK {sales['allegro-cz']:,.0f}→{czk_pln:,.2f}  "
              f"HUF {sales['allegro-hu']:,.0f}→{huf_pln:,.2f}  "
              f"EUR {sales['allegro-sk']:,.2f}→{eur_pln:,.2f}  "
              f"│ ИТОГО: {total:,.2f} PLN")

        # ── Расходы (все конвертируем в PLN) ─────────────────
        costs_pln = {cat: 0.0 for cat in COST_CATS}

        # PL — без marketplaceId (PLN, уже включает business-pl)
        c_pl = get_billing_for_month(token, year, month, None)
        for cat in COST_CATS:
            costs_pln[cat] += c_pl.get(cat, 0.0)
        print(f"    Расходы PL  → PLN: {sum(v for k,v in c_pl.items() if k!='discount'):>8,.2f}")

        # CZ — allegro-cz → CZK → PLN
        if rates["CZK"] > 0:
            c_cz = get_billing_for_month(token, year, month, "allegro-cz")
            cz_total = sum(v for k,v in c_cz.items() if k != "discount")
            for cat in COST_CATS:
                costs_pln[cat] += c_cz.get(cat, 0.0) * rates["CZK"]
            print(f"    Расходы CZ  → CZK: {cz_total:>8,.2f}  "
                  f"→ PLN: {cz_total*rates['CZK']:>8,.2f} (курс {rates['CZK']:.4f})")
        else:
            print(f"    Расходы CZ  → пропущены (нет курса CZK)")

        # HU — allegro-hu → HUF → PLN
        if rates["HUF"] > 0:
            c_hu = get_billing_for_month(token, year, month, "allegro-hu")
            hu_total = sum(v for k,v in c_hu.items() if k != "discount")
            for cat in COST_CATS:
                costs_pln[cat] += c_hu.get(cat, 0.0) * rates["HUF"]
            print(f"    Расходы HU  → HUF: {hu_total:>8,.2f}  "
                  f"→ PLN: {hu_total*rates['HUF']:>8,.2f} (курс {rates['HUF']:.6f})")
        else:
            print(f"    Расходы HU  → пропущены (нет курса HUF)")

        # SK — allegro-sk → EUR → PLN
        if rates["EUR"] > 0:
            c_sk = get_billing_for_month(token, year, month, "allegro-sk")
            sk_total = sum(v for k,v in c_sk.items() if k != "discount")
            for cat in COST_CATS:
                costs_pln[cat] += c_sk.get(cat, 0.0) * rates["EUR"]
            print(f"    Расходы SK  → EUR: {sk_total:>8,.2f}  "
                  f"→ PLN: {sk_total*rates['EUR']:>8,.2f} (курс {rates['EUR']:.4f})")
        else:
            print(f"    Расходы SK  → пропущены (нет курса EUR)")

        costs_pln_rounded = {k: round(v, 2) for k, v in costs_pln.items()}
        month_data[mk][shop_name]["costs_pln"] = costs_pln_rounded
        total_costs = sum(v for k,v in costs_pln_rounded.items() if k != "discount")
        print(f"    ─── Итого расходы (все валюты → PLN): {total_costs:>8,.2f}")

# ── ШАГ 3: Формируем записи и сохраняем ──────────────────────

# Удаляем старые записи за период из data.json
date_set    = {f"{y}-{m:02d}" for y,m in months}
data["days"] = [d for d in data["days"] if d["date"][:7] not in date_set]

for mk in sorted(month_data.keys(), key=lambda x: (int(x[-4:]), MONTH_RU_REV[x[:3]])):
    d  = month_data[mk]
    ml = d["Mlot_i_Klucz"]
    pl = d["PolaxEuroGroup"]
    si = d["Sila_Narzedzi"]

    # Год и месяц из ключа "Янв 2026" — НЕ из переменных внешнего цикла!
    mk_year  = int(mk[-4:])
    mk_month = MONTH_RU_REV[mk[:3]]

    # countries: PLN суммируем, CZK/HUF/EUR храним в нативных валютах
    countries = {"allegro-pl":0.0,"allegro-cz":0.0,"allegro-hu":0.0,"allegro-sk":0.0}
    for shop_d in [ml, pl, si]:
        for key in countries:
            countries[key] = round(countries[key] + shop_d["sales"].get(key, 0.0), 2)

    # costs: сумма по всем магазинам, всё уже в PLN
    costs_total = {cat: 0.0 for cat in COST_CATS}
    for shop_d in [ml, pl, si]:
        for cat in COST_CATS:
            costs_total[cat] += shop_d["costs_pln"].get(cat, 0.0)
    costs_total = {k: round(v, 2) for k, v in costs_total.items()}

    day_entry = {
        "date":          f"{mk_year:04d}-{mk_month:02d}-01",
        "Mlot_i_Klucz":  round(ml["total"], 2),
        "PolaxEuroGroup":round(pl["total"], 2),
        "Sila_Narzedzi": round(si["total"], 2),
        "countries":     countries,
        "costs":         costs_total,
        "shop_costs": {
            "Mlot_i_Klucz":   {k: round(v, 2) for k, v in ml["costs_pln"].items()},
            "PolaxEuroGroup":  {k: round(v, 2) for k, v in pl["costs_pln"].items()},
            "Sila_Narzedzi":   {k: round(v, 2) for k, v in si["costs_pln"].items()},
        },
    }
    data["days"].append(day_entry)

    net = sum(v for k,v in costs_total.items() if k != "discount")
    print(f"\n  ✅ {mk} → {day_entry['date']}  "
          f"PLN: {day_entry['Mlot_i_Klucz']+day_entry['PolaxEuroGroup']+day_entry['Sila_Narzedzi']:,.2f}  "
          f"расходы: {net:,.2f}")

data["days"].sort(key=lambda x: x["date"])
update_months(data)
save_data(data)

print(f"\n{'='*60}")
print(f"✅ Готово!")
print(f"   Месяцев загружено:       {len(months)}")
print(f"   Дней в data.json:        {len(data['days'])}")
print(f"   Месяцев в data.json:     {len(data['months'])}")
print(f"{'='*60}")
