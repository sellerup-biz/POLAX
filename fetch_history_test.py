import requests, json, os, base64
from datetime import datetime, timedelta
from nacl import encoding, public

REDIRECT_URI  = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN      = os.environ.get("GH_TOKEN", "")
GH_REPO       = "sellerup-biz/POLAX"

TEST_SHOP  = "PolaxEuroGroup"
ALL_SHOPS  = ["Mlot_i_Klucz", "PolaxEuroGroup", "Sila_Narzedzi"]

# Январь + Февраль
TEST_DATES = []
for month in [1, 2]:
    for day in range(1, (32 if month == 1 else 29)):
        TEST_DATES.append(f"2026-{month:02d}-{day:02d}")

# Страны: marketplace → (валюта, display)
COUNTRIES = {
    "allegro-pl":          ("PLN", "PL (польша)"),
    "allegro-business-pl": ("PLN", "PL biznes"),
    "allegro-cz":          ("CZK", "CZ (чехия)"),
    "allegro-hu":          ("HUF", "HU (венгрия)"),
    "allegro-sk":          ("EUR", "SK (словакия)"),
}

# Маппинг billing
BILLING_MAP = {
    "SUC":"commission","SUJ":"commission","LDS":"commission",
    "REF":"zwrot_commission",
    "HB4":"delivery","HB1":"delivery","DPB":"delivery","DXP":"delivery",
    "HXO":"delivery","HLB":"delivery","ORB":"delivery","DHR":"delivery",
    "GLS":"delivery","UPS":"delivery",
    "NSP":"ads","DPG":"ads","WYR":"ads","POD":"ads","BOL":"ads","EMF":"ads","CPC":"ads",
    "SB2":"subscription","ABN":"subscription",
    "RET":"discount","PS1":"discount",
    "PAD":"IGNORE",
}

def get_billing_cat(tid, tnam):
    if tid in BILLING_MAP: return BILLING_MAP[tid]
    n = tnam.lower()
    if any(x in n for x in ["prowizja","lokalna dopłata","opłata transakcyjna"]): return "commission"
    if any(x in n for x in ["dostawa","kurier","inpost","dpd","gls","ups","orlen","poczta",
                              "przesyłka","fulfillment","one kurier","allegro delivery"]): return "delivery"
    if any(x in n for x in ["kampani","reklam","promowanie","wyróżnienie","pogrubienie",
                              "podświetlenie","strona działu","pakiet promo","cpc"]): return "ads"
    if any(x in n for x in ["abonament","smart"]): return "subscription"
    if any(x in n for x in ["rozliczenie akcji","wyrównanie w programie allegro","rabat"]): return "discount"
    if any(x in n for x in ["zwrot kosztów","zwrot prowizji"]): return "zwrot_commission"
    if "pobranie opłat z wpływów" in n: return "IGNORE"
    return "other"

def get_tz(month): return 2 if 3 <= month <= 10 else 1

def hdrs(t):
    return {"Authorization": f"Bearer {t}", "Accept": "application/vnd.allegro.public.v1+json"}

def update_gh_secret(name, val):
    r = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
                     headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"})
    key = r.json()
    pk  = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
    enc = base64.b64encode(public.SealedBox(pk).encrypt(val.encode())).decode()
    requests.put(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{name}",
                 headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
                 json={"encrypted_value": enc, "key_id": key["key_id"]})

def get_token():
    cid = os.environ["CLIENT_ID_POLAX"]
    cs  = os.environ["CLIENT_SECRET_POLAX"]
    rt  = os.environ["REFRESH_TOKEN_POLAX"]
    r = requests.post("https://allegro.pl/auth/oauth/token", auth=(cid, cs),
                      data={"grant_type":"refresh_token","refresh_token":rt,"redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d:
        print(f"ОШИБКА ТОКЕНА: {d}")
        exit(1)
    # Сохраняем НОВЫЙ refresh_token сразу!
    new_rt = d.get("refresh_token", rt)
    if new_rt and GH_TOKEN:
        update_gh_secret("REFRESH_TOKEN_POLAX", new_rt)
    print(f"Токен {TEST_SHOP}: OK (сохранён)")
    return d["access_token"]

# ── ПРОДАЖИ по стране в ЛОКАЛЬНОЙ валюте ─────────────────────
def get_sales_local(token, df, dt, marketplace):
    """Возвращает сумму в локальной валюте страны"""
    total = 0.0
    offset = 0
    while True:
        ops = requests.get("https://api.allegro.pl/payments/payment-operations",
                           headers=hdrs(token),
                           params={"group":"INCOME","occurredAt.gte":df,"occurredAt.lte":dt,
                                   "marketplaceId":marketplace,"limit":100,"offset":offset}
                           ).json().get("paymentOperations", [])
        for op in ops:
            try: total += float(op["value"]["amount"])
            except: pass
        if len(ops) < 100: break
        offset += 100
    return round(total, 2)

# ── РАСХОДЫ по стране в ЛОКАЛЬНОЙ валюте ─────────────────────
def get_costs_local(token, df, dt, marketplace):
    """Расходы через billing-entries с фильтром marketplaceId"""
    costs   = {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0,"other":0.0}
    unknown = {}
    offset  = 0
    while True:
        entries = requests.get("https://api.allegro.pl/billing/billing-entries",
                               headers=hdrs(token),
                               params={"occurredAt.gte":df,"occurredAt.lte":dt,
                                       "marketplaceId":marketplace,"limit":100,"offset":offset}
                               ).json().get("billingEntries", [])
        for e in entries:
            try:
                amt  = float(e["value"]["amount"])
                tid  = e["type"]["id"]
                tnam = e["type"]["name"]
                cat  = get_billing_cat(tid, tnam)
                if cat == "IGNORE": continue
                if amt < 0:
                    if cat in costs: costs[cat] += abs(amt)
                    if cat == "other": unknown[tid] = tnam
                elif amt > 0:
                    if cat == "zwrot_commission": costs["commission"] = max(0, costs["commission"] - amt)
                    elif cat == "delivery":       costs["delivery"]   = max(0, costs["delivery"] - amt)
                    elif cat == "discount":       costs["discount"]   += amt
                    else: unknown[f"+{tid}"] = tnam
            except: pass
        if len(entries) < 100: break
        offset += 100
    if unknown:
        print(f"    ⚠ НОВЫЕ ТИПЫ ({marketplace}): {unknown}")
    return {k: round(v, 2) for k, v in costs.items()}

# ── ЭТАЛОН из скриншотов Allegro ─────────────────────────────
ETALON = {
    "2026-01": {
        "allegro-pl": {
            "cur": "PLN",
            "sales":        33998.72,
            "commission":   -4727.83,
            "delivery":     -1793.56,
            "ads":          -8968.75,
            "subscription": -199.00,
            "discount":     +46.54,
        },
        "allegro-cz": {
            "cur": "CZK",
            "sales":        1613.00,
            "commission":   -253.44,
            "delivery":     -454.98,
            "ads":          0.00,
            "subscription": 0.00,
            "discount":     0.00,
        },
        "allegro-hu": {
            "cur": "HUF",
            "sales":        3790.00,
            "commission":   -662.79,
            "delivery":     -2570.00,
            "ads":          0.00,
            "subscription": 0.00,
            "discount":     0.00,
        },
        "allegro-sk": {
            "cur": "EUR",
            "sales":        93.36,
            "commission":   -11.66,
            "delivery":     -9.26,
            "ads":          0.00,
            "subscription": 0.00,
            "discount":     0.00,
        },
    }
}

# ── ОСНОВНОЙ ЦИКЛ ─────────────────────────────────────────────
print(f"ТЕСТ: {TEST_SHOP} | Янв+Фев 2026 | {len(TEST_DATES)} дней\n")
token = get_token()

# Накапливаем данные по месяцам
months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
monthly = {}

for date_key in TEST_DATES:
    mk  = date_key[:7]
    lbl = f"{months_ru[int(mk[5:7])-1]} {mk[:4]}"
    tz  = get_tz(int(date_key[5:7]))
    df  = date_key + f"T00:00:00+0{tz}:00"
    dt  = date_key + f"T23:59:59+0{tz}:00"

    if lbl not in monthly:
        monthly[lbl] = {"_mk": mk}
        for mkt in COUNTRIES:
            monthly[lbl][mkt] = {"sales": 0.0,
                                  "commission":0.0,"delivery":0.0,"ads":0.0,
                                  "subscription":0.0,"discount":0.0,"other":0.0}

    for mkt in COUNTRIES:
        sales = get_sales_local(token, df, dt, mkt)
        costs = get_costs_local(token, df, dt, mkt)
        monthly[lbl][mkt]["sales"] += sales
        for k in costs:
            monthly[lbl][mkt][k] += costs[k]

    print(f"  {date_key} OK")

# ── ОТЧЁТ ─────────────────────────────────────────────────────
COST_NAMES = {
    "commission":   "Obowiązkowe",
    "delivery":     "Dostawa",
    "ads":          "Reklama i promowanie",
    "subscription": "Abonament",
    "discount":     "Rabaty od Allegro",
}
COST_SIGN = {"commission":"-","delivery":"-","ads":"-","subscription":"-","discount":"+"}

def pct(val, base):
    if base == 0: return "—"
    return f"{abs(val)/base*100:.1f}%"

def ok(our, ref):
    if ref == 0 and our == 0: return "OK"
    if ref == 0: return "—"
    diff = abs(our - abs(ref))
    return "OK" if diff < 2 else ("~OK" if diff < 20 else "ОШИБКА")

print(f"\n{'='*80}")
print(f"  СРАВНЕНИЕ С ЭТАЛОНОМ ALLEGRO — {TEST_SHOP}")
print(f"{'='*80}")

for lbl, mdata in monthly.items():
    mk = mdata["_mk"]
    et = ETALON.get(mk)
    print(f"\n  {'─'*76}")
    print(f"  {lbl}")
    print(f"  {'─'*76}")

    # Объединяем PL + business-PL
    pl_sales = round(mdata["allegro-pl"]["sales"] + mdata["allegro-business-pl"]["sales"], 2)
    pl_costs = {}
    for k in ["commission","delivery","ads","subscription","discount","other"]:
        pl_costs[k] = round(mdata["allegro-pl"][k] + mdata["allegro-business-pl"][k], 2)

    display_data = {
        "allegro-pl":  {"label":"PL (PLN)", "cur":"PLN", "sales":pl_sales, **pl_costs},
        "allegro-cz":  {"label":"CZ (CZK)", "cur":"CZK", **{k:round(mdata["allegro-cz"][k],2) for k in ["sales","commission","delivery","ads","subscription","discount","other"]}},
        "allegro-hu":  {"label":"HU (HUF)", "cur":"HUF", **{k:round(mdata["allegro-hu"][k],2) for k in ["sales","commission","delivery","ads","subscription","discount","other"]}},
        "allegro-sk":  {"label":"SK (EUR)", "cur":"EUR", **{k:round(mdata["allegro-sk"][k],2) for k in ["sales","commission","delivery","ads","subscription","discount","other"]}},
    }

    for mkt, d in display_data.items():
        cur   = d["cur"]
        label = d["label"]
        e     = et.get(mkt) if et else None

        print(f"\n  ┌─ {label} {'─'*(60-len(label))}")

        # Продажи
        our_s = d["sales"]
        if e:
            ref_s = e["sales"]
            diff  = our_s - ref_s
            status = ok(our_s, ref_s)
            print(f"  │  Wartość sprzedaży  {our_s:>12.2f} {cur}  │  эталон: {ref_s:>10.2f}  │  разница: {diff:>+8.2f}  {status}")
        else:
            print(f"  │  Wartość sprzedaży  {our_s:>12.2f} {cur}")

        # Расходы
        for cat in ["commission","delivery","ads","subscription","discount"]:
            our_c = d[cat]
            sign  = COST_SIGN[cat]
            name  = COST_NAMES[cat]
            if e:
                ref_c = e[cat]  # уже со знаком
                diff  = our_c - abs(ref_c)
                status = ok(our_c, ref_c)
                print(f"  │  {name:<22} {sign}{our_c:>10.2f} {cur}  │  эталон: {ref_c:>+10.2f}  │  разница: {diff:>+8.2f}  {status}")
            else:
                if our_c != 0:
                    print(f"  │  {name:<22} {sign}{our_c:>10.2f} {cur}")
        if d.get("other", 0) > 0:
            print(f"  │  ⚠ OTHER              -{d['other']:>10.2f} {cur}  ← добавить в BILLING_MAP!")
        print(f"  └{'─'*63}")

print(f"\n{'='*80}")
print("Готово!")
