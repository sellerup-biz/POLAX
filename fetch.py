"""
POLAX — ежедневный сбор данных (все 3 магазина)
Запускается каждую ночь в 03:00 UTC через fetch.yml

За один запуск собирает:
  1. Вчера  — полные данные (complete)
  2. Сегодня — накопленные данные с начала дня (partial: true)

Сегодняшняя partial-запись при следующем запуске автоматически
перезаписывается полными вчерашними данными.

Это позволяет goal-блоку и analytics.html показывать
растущий текущий месяц в течение дня.
"""
import requests, json, os, base64, calendar
from datetime import datetime, timedelta, timezone
from nacl import encoding, public
from collections import defaultdict

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

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
    "SUM":"IGNORE",
}

COST_CATS = ["commission","delivery","ads","subscription","discount"]


def get_billing_cat(tid, tnam):
    if tid in BILLING_MAP:
        return BILLING_MAP[tid]
    n = tnam.lower()
    if "kampanii" in n or "kampania" in n: return "ads"
    if any(x in n for x in ["prowizja","lokalna dopłata","opłata transakcyjna"]): return "commission"
    if any(x in n for x in ["dostawa","kurier","inpost","dpd","gls","ups","orlen","poczta",
                              "przesyłka","fulfillment","one kurier","allegro delivery",
                              "packeta","international","dodatkowa za dostawę"]): return "delivery"
    if any(x in n for x in ["kampani","reklam","promowanie","wyróżnienie","pogrubienie",
                              "podświetlenie","strona działu","pakiet promo","cpc","ads"]): return "ads"
    if any(x in n for x in ["abonament","smart"]): return "subscription"
    if any(x in n for x in ["rozliczenie akcji","wyrównanie w programie allegro","rabat"]): return "discount"
    if any(x in n for x in ["zwrot kosztów","zwrot prowizji"]): return "zwrot_commission"
    if "pobranie opłat z wpływów" in n: return "IGNORE"
    return "other"


# ── AUTH & GITHUB ─────────────────────────────────────────────

def get_gh_pubkey():
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
        headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"})
    return r.json()


def save_token(secret_name, new_rt, pubkey):
    if not new_rt or not GH_TOKEN: return
    try:
        pk  = public.PublicKey(pubkey["key"].encode(), encoding.Base64Encoder())
        enc = base64.b64encode(public.SealedBox(pk).encrypt(new_rt.encode())).decode()
        resp = requests.put(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
            headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"},
            json={"encrypted_value":enc,"key_id":pubkey["key_id"]})
        if resp.status_code in (201, 204):
            print(f"  ✅ Токен {secret_name} сохранён")
        else:
            print(f"  ⚠ Токен {secret_name}: статус {resp.status_code}")
    except Exception as e:
        print(f"  ⚠ Ошибка токена {secret_name}: {e}")


def get_token(shop):
    r = requests.post(
        "https://allegro.pl/auth/oauth/token",
        auth=(shop["client_id"], shop["client_secret"]),
        data={"grant_type":"refresh_token",
              "refresh_token":shop["refresh_token"],
              "redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d:
        print(f"  ОШИБКА токена: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token","")


def hdrs(t):
    return {"Authorization":f"Bearer {t}","Accept":"application/vnd.allegro.public.v1+json"}


def get_tz(month):
    return 2 if 3 <= month <= 10 else 1


# ── НБП КУРСЫ ─────────────────────────────────────────────────

def get_nbp_rates():
    rates = {"CZK": 0.0, "HUF": 0.0, "EUR": 0.0}
    try:
        resp = requests.get(
            "https://api.nbp.pl/api/exchangerates/tables/a/?format=json",
            timeout=15)
        if resp.status_code == 200:
            for r in resp.json()[0]["rates"]:
                if r["code"] in rates:
                    rates[r["code"]] = r["mid"]
            print(f"  НБП: CZK={rates['CZK']:.4f}  HUF={rates['HUF']:.6f}  EUR={rates['EUR']:.4f}")
        else:
            print(f"  ⚠ НБП: HTTP {resp.status_code}")
    except Exception as e:
        print(f"  ⚠ НБП недоступен: {e}")
    return rates


# ── ПРОДАЖИ ───────────────────────────────────────────────────

def get_sales_for_day(token, date_str):
    dt     = datetime.strptime(date_str, "%Y-%m-%d")
    tz     = get_tz(dt.month)
    d_from = f"{date_str}T00:00:00+0{tz}:00"
    d_to   = f"{date_str}T23:59:59+0{tz}:00"
    by_mkt = defaultdict(float)

    for mkt in ["allegro-pl","allegro-business-pl","allegro-cz","allegro-hu","allegro-sk"]:
        offset = 0
        while True:
            resp = requests.get(
                "https://api.allegro.pl/payments/payment-operations",
                headers=hdrs(token),
                params={"group":"INCOME","occurredAt.gte":d_from,"occurredAt.lte":d_to,
                        "marketplaceId":mkt,"limit":50,"offset":offset})
            if resp.status_code != 200:
                print(f"    ⚠ payments {mkt}: HTTP {resp.status_code}")
                break
            ops = resp.json().get("paymentOperations",[])
            for op in ops:
                try: by_mkt[mkt] += float(op["value"]["amount"])
                except Exception: pass
            if len(ops) < 50: break
            offset += 50

    return {
        "allegro-pl": round(by_mkt["allegro-pl"] + by_mkt["allegro-business-pl"], 2),
        "allegro-cz": round(by_mkt["allegro-cz"], 2),
        "allegro-hu": round(by_mkt["allegro-hu"], 2),
        "allegro-sk": round(by_mkt["allegro-sk"], 2),
    }


# ── РАСХОДЫ ───────────────────────────────────────────────────

def get_billing_for_day(token, date_str, marketplace_id=None):
    dt     = datetime.strptime(date_str, "%Y-%m-%d")
    tz     = get_tz(dt.month)
    d_from = f"{date_str}T00:00:00+0{tz}:00"
    d_to   = f"{date_str}T23:59:59+0{tz}:00"
    costs  = {cat: 0.0 for cat in COST_CATS}
    offset = 0
    params = {"occurredAt.gte":d_from,"occurredAt.lte":d_to,"limit":100}
    if marketplace_id:
        params["marketplaceId"] = marketplace_id

    while True:
        params["offset"] = offset
        resp = requests.get(
            "https://api.allegro.pl/billing/billing-entries",
            headers=hdrs(token), params=params)
        if resp.status_code != 200:
            print(f"    ⚠ billing {marketplace_id or 'pl'}: HTTP {resp.status_code}")
            break
        entries = resp.json().get("billingEntries",[])
        for e in entries:
            try:
                amt  = float(e["value"]["amount"])
                cat  = get_billing_cat(e["type"]["id"], e["type"]["name"])
                if cat == "IGNORE": continue
                if cat == "other":
                    print(f"    ⚠ UNKNOWN: {e['type']['id']} '{e['type']['name']}' {amt:.2f}")
                    continue
                if amt < 0:
                    if cat in costs: costs[cat] += abs(amt)
                elif amt > 0:
                    if cat == "zwrot_commission": costs["commission"] = max(0.0, costs["commission"]-amt)
                    elif cat == "delivery":       costs["delivery"]   = max(0.0, costs["delivery"]-amt)
                    elif cat == "discount":       costs["discount"]  += amt
            except Exception: pass
        if len(entries) < 100: break
        offset += 100

    return {k: round(v, 2) for k, v in costs.items()}


# ── СБОР ДАННЫХ ЗА ОДИН ДЕНЬ ─────────────────────────────────

def collect_day(access_tokens, date_str, nbp, partial=False):
    """
    Собирает продажи и расходы за date_str по всем магазинам.
    access_tokens: {shop_name: token} — переиспользуем без ротации.
    Возвращает готовую запись для data.days.
    """
    entry = {
        "date":          date_str,
        "Mlot_i_Klucz":  0.0,
        "PolaxEuroGroup":0.0,
        "Sila_Narzedzi": 0.0,
        "countries":     {"allegro-pl":0.0,"allegro-cz":0.0,"allegro-hu":0.0,"allegro-sk":0.0},
        "costs":         {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0},
    }
    if partial:
        entry["partial"] = True

    for shop_name, token in access_tokens.items():
        if not token:
            continue
        print(f"    {shop_name}...", end=" ", flush=True)

        # Продажи
        sales = get_sales_for_day(token, date_str)
        for mkt in ["allegro-pl","allegro-cz","allegro-hu","allegro-sk"]:
            entry["countries"][mkt] = round(entry["countries"][mkt] + sales.get(mkt, 0.0), 2)

        czk_pln = round(sales["allegro-cz"] * nbp["CZK"], 2)
        huf_pln = round(sales["allegro-hu"] * nbp["HUF"], 2)
        eur_pln = round(sales["allegro-sk"] * nbp["EUR"], 2)
        total   = round(sales["allegro-pl"] + czk_pln + huf_pln + eur_pln, 2)
        entry[shop_name] = round(entry[shop_name] + total, 2)

        # Расходы (все маркетплейсы → PLN)
        costs_pln = {cat: 0.0 for cat in COST_CATS}
        c_pl = get_billing_for_day(token, date_str, None)
        for cat in COST_CATS: costs_pln[cat] += c_pl.get(cat, 0.0)

        if nbp["CZK"] > 0:
            c_cz = get_billing_for_day(token, date_str, "allegro-cz")
            for cat in COST_CATS: costs_pln[cat] += c_cz.get(cat, 0.0) * nbp["CZK"]

        if nbp["HUF"] > 0:
            c_hu = get_billing_for_day(token, date_str, "allegro-hu")
            for cat in COST_CATS: costs_pln[cat] += c_hu.get(cat, 0.0) * nbp["HUF"]

        if nbp["EUR"] > 0:
            c_sk = get_billing_for_day(token, date_str, "allegro-sk")
            for cat in COST_CATS: costs_pln[cat] += c_sk.get(cat, 0.0) * nbp["EUR"]

        for cat in COST_CATS:
            entry["costs"][cat] = round(entry["costs"][cat] + costs_pln.get(cat, 0.0), 2)

        total_costs = sum(v for k,v in costs_pln.items() if k != "discount")
        print(f"PLN={total:,.2f}  costs={total_costs:,.2f}")

    # Финальное округление
    for mkt in entry["countries"]: entry["countries"][mkt] = round(entry["countries"][mkt], 2)
    for cat in entry["costs"]:     entry["costs"][cat]     = round(entry["costs"][cat], 2)
    for s in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"]: entry[s] = round(entry[s], 2)
    return entry


# ── DATA.JSON ─────────────────────────────────────────────────

def load_data():
    try:
        with open("data.json") as f: return json.load(f)
    except Exception: return {"days":[],"months":[]}


def save_data(data):
    with open("data.json","w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",",":"))


def update_months(data):
    months_map = defaultdict(lambda:{
        "Mlot_i_Klucz":0,"PolaxEuroGroup":0,"Sila_Narzedzi":0,
        "countries":{"allegro-pl":0,"allegro-cz":0,"allegro-hu":0,"allegro-sk":0},
        "costs":{"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0}
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
    MONTH_RU_REV = {v:k for k,v in MONTH_RU.items()}
    data["months"] = [
        {"month":k,**v}
        for k,v in sorted(
            months_map.items(),
            key=lambda x: (int(x[0][-4:]), MONTH_RU_REV[x[0][:3]])
        )
    ]


# ── MAIN ──────────────────────────────────────────────────────

now       = datetime.now(timezone.utc)
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
today_str = now.strftime("%Y-%m-%d")

print(f"Вчера:   {yesterday}")
print(f"Сегодня: {today_str}")

data        = load_data()
existing    = {d["date"]: d for d in data["days"]}

# Нужно ли собирать вчера?
# Пропускаем только если вчера уже есть как ПОЛНАЯ (не partial) запись
collect_yesterday = not (
    yesterday in existing and not existing[yesterday].get("partial", False)
)

if not collect_yesterday:
    print(f"\n{yesterday} уже есть (полный) — пропускаем вчера")

print("\n── НБП курсы ────────────────────────────────────────────")
nbp    = get_nbp_rates()
pubkey = get_gh_pubkey()

# ── ШАГ 1: Получаем токены (один раз на все операции) ─────────
print("\n── Авторизация ──────────────────────────────────────────")
access_tokens = {}  # {shop_name: access_token}

for shop_name, shop in SHOPS.items():
    token, new_rt = get_token(shop)
    if not token:
        print(f"  ❌ {shop_name}: токен не получен")
        continue
    save_token(shop["secret_name"], new_rt, pubkey)
    access_tokens[shop_name] = token

# ── ШАГ 2: Вчера (complete) ────────────────────────────────────
if collect_yesterday and access_tokens:
    print(f"\n── Вчера: {yesterday} ───────────────────────────────────")
    if yesterday in existing and existing[yesterday].get("partial", False):
        print(f"  Была partial-запись — перезаписываем")
    # Удаляем существующую запись за вчера (если была partial)
    data["days"] = [d for d in data["days"] if d["date"] != yesterday]

    yest_entry = collect_day(access_tokens, yesterday, nbp, partial=False)
    data["days"].append(yest_entry)

    total_yest = yest_entry["Mlot_i_Klucz"]+yest_entry["PolaxEuroGroup"]+yest_entry["Sila_Narzedzi"]
    print(f"  ✅ {yesterday}: {total_yest:,.2f} PLN")

# ── ШАГ 3: Сегодня (partial) ─────────────────────────────────
# Переиспользуем те же access_tokens — ротация уже прошла на шаге 1
if access_tokens:
    print(f"\n── Сегодня: {today_str} (partial) ───────────────────────")
    # Всегда перезаписываем сегодняшнюю partial-запись свежими данными
    data["days"] = [d for d in data["days"] if d["date"] != today_str]

    today_entry = collect_day(access_tokens, today_str, nbp, partial=True)
    data["days"].append(today_entry)

    total_today = today_entry["Mlot_i_Klucz"]+today_entry["PolaxEuroGroup"]+today_entry["Sila_Narzedzi"]
    print(f"  ✅ {today_str}: {total_today:,.2f} PLN (неполный день)")

# ── СОХРАНЯЕМ ─────────────────────────────────────────────────
data["days"].sort(key=lambda x: x["date"])
update_months(data)
save_data(data)

cur_month_key = MONTH_RU[now.month] + " " + str(now.year)
cur_month = next((m for m in data["months"] if m["month"] == cur_month_key), None)
if cur_month:
    cur_total = (cur_month.get("Mlot_i_Klucz",0)
                +cur_month.get("PolaxEuroGroup",0)
                +cur_month.get("Sila_Narzedzi",0))
    print(f"\n📊 {cur_month_key} — текущий итог: {cur_total:,.2f} PLN  "
          f"(цель 200 000, выполнено {cur_total/200000*100:.1f}%)")

print(f"\n✅ Готово. Дней в data.json: {len(data['days'])}")
