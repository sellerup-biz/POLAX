import requests, json, os, base64
from datetime import datetime, timedelta, timezone
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO  = "sellerup-biz/POLAX"
MARKETPLACES = {"allegro-pl":"PLN","allegro-cz":"CZK","allegro-hu":"HUF","allegro-sk":"EUR"}

TEST_SHOP  = "PolaxEuroGroup"
ALL_SHOPS  = ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"]
TEST_DATES = []
for month in [1, 2]:
    days_in = 31 if month == 1 else 28
    for day in range(1, days_in + 1):
        TEST_DATES.append(f"2026-{month:02d}-{day:02d}")

SHOPS = {}
if os.environ.get("CLIENT_ID_POLAX") and os.environ.get("REFRESH_TOKEN_POLAX"):
    SHOPS[TEST_SHOP] = {
        "client_id":     os.environ["CLIENT_ID_POLAX"],
        "client_secret": os.environ["CLIENT_SECRET_POLAX"],
        "refresh_token": os.environ["REFRESH_TOKEN_POLAX"],
        "secret_name":   "REFRESH_TOKEN_POLAX"
    }

# ── МАППИНГ по type.id ────────────────────────────────────────
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

_rates = {}
def get_rate(currency, date_str):
    if currency == "PLN": return 1.0
    key = f"{currency}_{date_str}"
    if key in _rates: return _rates[key]
    for delta in range(7):
        d = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            r = requests.get(f"https://api.nbp.pl/api/exchangerates/rates/a/{currency.lower()}/{d}/?format=json", timeout=5)
            if r.status_code == 200:
                rate = float(r.json()["rates"][0]["mid"])
                _rates[key] = rate
                return rate
        except: pass
    return 1.0

def get_gh_pk():
    r = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
                     headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"})
    return r.json()

def update_gh_secret(name, val, key_id, key_val):
    pk  = public.PublicKey(key_val.encode(), encoding.Base64Encoder())
    enc = base64.b64encode(public.SealedBox(pk).encrypt(val.encode())).decode()
    r   = requests.put(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{name}",
                       headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
                       json={"encrypted_value": enc, "key_id": key_id})
    return r.status_code in (201, 204)

def get_token(cid, cs, rt):
    r = requests.post("https://allegro.pl/auth/oauth/token", auth=(cid, cs),
                      data={"grant_type":"refresh_token","refresh_token":rt,"redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d:
        print(f"  ОШИБКА ТОКЕНА: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token", rt)

def hdrs(t):
    return {"Authorization": f"Bearer {t}", "Accept": "application/vnd.allegro.public.v1+json"}

def get_tz(month): return 2 if 3 <= month <= 10 else 1

def get_sales_for_day(token, date_key):
    tz = get_tz(int(date_key[5:7]))
    df = date_key + f"T00:00:00+0{tz}:00"
    dt = date_key + f"T23:59:59+0{tz}:00"
    total = 0.0
    offset = 0
    while True:
        ops = requests.get("https://api.allegro.pl/payments/payment-operations", headers=hdrs(token),
                           params={"group":"INCOME","occurredAt.gte":df,"occurredAt.lte":dt,
                                   "limit":100,"offset":offset}).json().get("paymentOperations",[])
        for op in ops:
            try: total += float(op["value"]["amount"]) * get_rate(op["value"]["currency"], date_key)
            except: pass
        if len(ops) < 100: break
        offset += 100
    countries = {k: 0.0 for k in MARKETPLACES}
    for mkt in MARKETPLACES:
        offset = 0
        while True:
            ops = requests.get("https://api.allegro.pl/payments/payment-operations", headers=hdrs(token),
                               params={"group":"INCOME","occurredAt.gte":df,"occurredAt.lte":dt,
                                       "marketplaceId":mkt,"limit":100,"offset":offset}).json().get("paymentOperations",[])
            for op in ops:
                try: countries[mkt] += float(op["value"]["amount"]) * get_rate(op["value"]["currency"], date_key)
                except: pass
            if len(ops) < 100: break
            offset += 100
        countries[mkt] = round(countries[mkt], 2)
    return countries, round(total, 2)

def get_costs_for_day(token, date_key):
    tz = get_tz(int(date_key[5:7]))
    df = date_key + f"T00:00:00+0{tz}:00"
    dt = date_key + f"T23:59:59+0{tz}:00"
    costs   = {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0,"other":0.0}
    unknown = {}
    offset  = 0
    while True:
        entries = requests.get("https://api.allegro.pl/billing/billing-entries", headers=hdrs(token),
                               params={"occurredAt.gte":df,"occurredAt.lte":dt,
                                       "limit":100,"offset":offset}).json().get("billingEntries",[])
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
                    elif cat == "delivery":       costs["delivery"]   = max(0, costs["delivery"]   - amt)
                    elif cat == "discount":       costs["discount"]   += amt
                    else: unknown[f"+{tid}"] = f"+{tnam}"
            except: pass
        if len(entries) < 100: break
        offset += 100
    if unknown:
        print(f"  ⚠ НОВЫЕ ТИПЫ [{date_key}]: {unknown}")
    return {k: round(v, 2) for k, v in costs.items()}

# ── ОСНОВНОЙ ЦИКЛ ─────────────────────────────────────────────
print(f"ТЕСТ: {TEST_SHOP} | Янв+Фев 2026 | {len(TEST_DATES)} дней")
print(f"ENV: CLIENT_ID_POLAX={'OK' if os.environ.get('CLIENT_ID_POLAX') else 'ОТСУТСТВУЕТ'}")
print(f"ENV: CLIENT_SECRET_POLAX={'OK' if os.environ.get('CLIENT_SECRET_POLAX') else 'ОТСУТСТВУЕТ'}")
print(f"ENV: REFRESH_TOKEN_POLAX={'OK (len='+str(len(os.environ.get('REFRESH_TOKEN_POLAX',''')))+')' if os.environ.get('REFRESH_TOKEN_POLAX') else 'ОТСУТСТВУЕТ'}")

gh_key    = get_gh_pk()
gh_key_id  = gh_key.get("key_id")
gh_key_val = gh_key.get("key")

tokens = {}
for shop, creds in SHOPS.items():
    t, nr = get_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if t:
        tokens[shop] = t
        if nr and gh_key_id and gh_key_val:
            print(f"  Токен {shop}: {'OK' if update_gh_secret(creds['secret_name'], nr, gh_key_id, gh_key_val) else 'ERR'}")

days_data = {date: {"date":date,"Mlot_i_Klucz":0,"PolaxEuroGroup":0,"Sila_Narzedzi":0,
                    "countries":{k:0 for k in MARKETPLACES},
                    "costs":{"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0,"other":0}}
             for date in TEST_DATES}

for shop, token in tokens.items():
    print(f"\n=== {shop} ===")
    for date_key in TEST_DATES:
        countries, total = get_sales_for_day(token, date_key)
        costs            = get_costs_for_day(token, date_key)
        days_data[date_key][shop] = total
        for k in countries: days_data[date_key]["countries"][k] = round(days_data[date_key]["countries"][k] + countries[k], 2)
        for k in costs:     days_data[date_key]["costs"][k]     = round(days_data[date_key]["costs"][k] + costs[k], 2)
        tc = sum(v for k,v in costs.items() if k != "discount")
        if total > 0 or tc > 0:
            print(f"  {date_key}: продажи={total:.2f} | Obowiązk={costs['commission']:.2f} Dost={costs['delivery']:.2f} Rekl={costs['ads']:.2f} Abon={costs['subscription']:.2f} Rab=+{costs['discount']:.2f}")

days_list = [days_data[d] for d in sorted(days_data)]

months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
monthly   = {}
for day in days_list:
    mk  = day["date"][:7]
    dt  = datetime.strptime(mk, "%Y-%m")
    lbl = f"{months_ru[dt.month-1]} {dt.year}"
    if lbl not in monthly:
        monthly[lbl] = {"month":lbl,"_o":mk,"Mlot_i_Klucz":0,"PolaxEuroGroup":0,"Sila_Narzedzi":0,
                        "countries":{k:0.0 for k in MARKETPLACES},
                        "costs":{"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0,"other":0.0}}
    m = monthly[lbl]
    for s in ALL_SHOPS: m[s] = round(m[s] + day.get(s, 0), 2)
    for k in MARKETPLACES: m["countries"][k] = round(m["countries"][k] + day.get("countries",{}).get(k,0), 2)
    for k in ["commission","delivery","ads","subscription","discount","other"]:
        m["costs"][k] = round(m["costs"][k] + day.get("costs",{}).get(k,0), 2)

months_list = sorted([{k:v for k,v in m.items() if k!="_o"} for m in monthly.values()],
                     key=lambda x: monthly[x["month"]]["_o"])

result = {"days": days_list, "months": months_list}
with open("data.json", "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

# ── ИТОГ ──────────────────────────────────────────────────────
ETALON_JAN = {"commission":4727.83,"delivery":1793.56,"ads":8968.75,"subscription":199.00,"discount":46.54}

print(f"\n{'='*70}")
for m in months_list:
    c     = m["costs"]
    sales = m[TEST_SHOP]
    ctr   = m["countries"]
    print(f"\n  {m['month']} — {TEST_SHOP}")
    print(f"  {'─'*66}")
    print(f"  Продажи итого:    {sales:>10.2f} PLN")
    print(f"  PL:{ctr['allegro-pl']:>10.2f} CZ:{ctr['allegro-cz']:>10.2f} HU:{ctr['allegro-hu']:>10.2f} SK:{ctr['allegro-sk']:>10.2f} (PLN)")
    print(f"  {'─'*66}")
    print(f"  {'Категория':<28} {'НАШИ':>10} {'ЭТАЛОН(Янв)':>12} {'РАЗНИЦА':>10}")
    for cat in ["commission","delivery","ads","subscription","discount"]:
        our = c[cat]
        ref = ETALON_JAN.get(cat, 0) if m["month"] == "Янв 2026" else None
        sign = "+" if cat == "discount" else "-"
        if ref is not None:
            diff = our - ref
            ok = "OK" if abs(diff) < 2 else "ОШИБКА"
            print(f"  {cat:<28} {sign}{our:>9.2f} {sign}{ref:>11.2f} {diff:>+10.2f}  {ok}")
        else:
            print(f"  {cat:<28} {sign}{our:>9.2f}")
    if c["other"] > 0:
        print(f"  {'⚠ other':<28} -{c['other']:>9.2f}  ← ДОБАВИТЬ В BILLING_MAP!")
print(f"\n{'='*70}")
