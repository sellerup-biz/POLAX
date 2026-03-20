import requests, json, os, base64
from datetime import datetime, timedelta, timezone
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"
MARKETPLACES = {"allegro-pl":"PLN","allegro-business-pl":"PLN","allegro-cz":"CZK","allegro-hu":"HUF","allegro-sk":"EUR"}

SHOPS = {}
for key, name, sname in [("SILA","Sila_Narzedzi","REFRESH_TOKEN_SILA"),
                          ("POLAX","PolaxEuroGroup","REFRESH_TOKEN_POLAX"),
                          ("MLOT","Mlot_i_Klucz","REFRESH_TOKEN_MLOT")]:
    if os.environ.get(f"CLIENT_ID_{key}") and os.environ.get(f"REFRESH_TOKEN_{key}"):
        SHOPS[name] = {"client_id":     os.environ[f"CLIENT_ID_{key}"],
                       "client_secret": os.environ[f"CLIENT_SECRET_{key}"],
                       "refresh_token": os.environ[f"REFRESH_TOKEN_{key}"],
                       "secret_name":   sname}

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

def get_billing_cat(tid, tnam, amt):
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
    if "access_token" not in d: return None, None
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
                cat  = get_billing_cat(tid, tnam, amt)
                if cat == "IGNORE": continue
                if amt < 0:
                    if cat in costs: costs[cat] += abs(amt)
                    if cat == "other": unknown[tid] = tnam
                elif amt > 0:
                    if cat == "zwrot_commission": costs["commission"] = max(0, costs["commission"] - amt)
                    elif cat == "delivery":       costs["delivery"]   = max(0, costs["delivery"]   - amt)
                    elif cat == "discount":       costs["discount"]   += amt
                    elif cat not in ("IGNORE",):  unknown[f"+{tid}"] = f"+{tnam}"
            except: pass
        if len(entries) < 100: break
        offset += 100
    if unknown:
        print(f"  ⚠ НОВЫЕ ТИПЫ [{date_key}]: {unknown}")
    return {k: round(v, 2) for k, v in costs.items()}

# ── ДИАПАЗОН ДАТ ──────────────────────────────────────────────
now_utc   = datetime.now(timezone.utc)
tz_off    = get_tz(now_utc.month)
yesterday = (now_utc + timedelta(hours=tz_off) - timedelta(days=1)).replace(tzinfo=None)
start     = datetime(2026, 1, 1)
all_dates = []
d = start
while d <= yesterday:
    all_dates.append(d.strftime("%Y-%m-%d"))
    d += timedelta(days=1)

print(f"Дат: {len(all_dates)} | Магазины: {list(SHOPS.keys())}")

gh_key    = get_gh_pk()
gh_key_id  = gh_key.get("key_id")
gh_key_val = gh_key.get("key")

tokens = {}
for shop, creds in SHOPS.items():
    t, nr = get_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if t:
        tokens[shop] = t
        if nr and gh_key_id and gh_key_val:
            print(f"  {shop} токен: {'OK' if update_gh_secret(creds['secret_name'], nr, gh_key_id, gh_key_val) else 'ERR'}")

days_data = {date: {"date":date,"Mlot_i_Klucz":0,"PolaxEuroGroup":0,"Sila_Narzedzi":0,
                    "countries":{k:0 for k in MARKETPLACES},
                    "costs":{"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0,"other":0}}
             for date in all_dates}

for shop, token in tokens.items():
    print(f"\n=== {shop} ===")
    for date_key in all_dates:
        countries, total = get_sales_for_day(token, date_key)
        costs            = get_costs_for_day(token, date_key)
        days_data[date_key][shop] = total
        for k in countries: days_data[date_key]["countries"][k] = round(days_data[date_key]["countries"][k] + countries[k], 2)
        for k in costs:     days_data[date_key]["costs"][k]     = round(days_data[date_key]["costs"][k] + costs[k], 2)
        tc = sum(v for k,v in costs.items() if k != "discount")
        if total > 0 or tc > 0:
            print(f"  {date_key}: продажи={total:.2f} | Obowiązkowe={costs['commission']:.2f} Dostawa={costs['delivery']:.2f} Reklama={costs['ads']:.2f} Abonament={costs['subscription']:.2f} Rabaty=+{costs['discount']:.2f}")

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
    for s in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"]: m[s] = round(m[s] + day.get(s, 0), 2)
    for k in MARKETPLACES: m["countries"][k] = round(m["countries"][k] + day.get("countries",{}).get(k, 0), 2)
    for k in ["commission","delivery","ads","subscription","discount","other"]:
        m["costs"][k] = round(m["costs"][k] + day.get("costs",{}).get(k, 0), 2)

months_list = sorted([{k:v for k,v in m.items() if k != "_o"} for m in monthly.values()],
                     key=lambda x: monthly[x["month"]]["_o"])
result = {"days": days_list, "months": months_list}
with open("data.json", "w") as f: json.dump(result, f, indent=2, ensure_ascii=False)

print(f"\n{'='*60}")
for m in months_list:
    sales = sum(m[s] for s in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"])
    c = m["costs"]
    print(f"{m['month']}: продажи={sales:.2f} | Obowiązkowe={c['commission']:.2f} Dostawa={c['delivery']:.2f} Reklama={c['ads']:.2f} Abonament={c['subscription']:.2f} Rabaty=+{c['discount']:.2f}" +
          (f" ⚠Other={c['other']:.2f}" if c["other"] > 0 else ""))
