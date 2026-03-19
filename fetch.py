import requests, json, os, base64
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

now_utc   = datetime.now(timezone.utc)
tz_offset = 2 if 3 <= now_utc.month <= 10 else 1
polish_now   = now_utc + timedelta(hours=tz_offset)
yesterday_pl = polish_now - timedelta(days=1)
tz_str       = f"+0{tz_offset}:00"
date_from    = yesterday_pl.strftime("%Y-%m-%dT00:00:00") + tz_str
date_to      = yesterday_pl.strftime("%Y-%m-%dT23:59:59") + tz_str
date_key     = yesterday_pl.strftime("%Y-%m-%d")

MARKETPLACES = {"allegro-pl": "PLN", "allegro-cz": "CZK", "allegro-hu": "HUF", "allegro-sk": "EUR"}

SHOPS = {}
if os.environ.get("CLIENT_ID_SILA") and os.environ.get("REFRESH_TOKEN_SILA"):
    SHOPS["Sila_Narzedzi"] = {"client_id": os.environ["CLIENT_ID_SILA"], "client_secret": os.environ["CLIENT_SECRET_SILA"],
                               "refresh_token": os.environ["REFRESH_TOKEN_SILA"], "secret_name": "REFRESH_TOKEN_SILA"}
if os.environ.get("CLIENT_ID_POLAX") and os.environ.get("REFRESH_TOKEN_POLAX"):
    SHOPS["PolaxEuroGroup"] = {"client_id": os.environ["CLIENT_ID_POLAX"], "client_secret": os.environ["CLIENT_SECRET_POLAX"],
                                "refresh_token": os.environ["REFRESH_TOKEN_POLAX"], "secret_name": "REFRESH_TOKEN_POLAX"}
if os.environ.get("CLIENT_ID_MLOT") and os.environ.get("REFRESH_TOKEN_MLOT"):
    SHOPS["Mlot_i_Klucz"] = {"client_id": os.environ["CLIENT_ID_MLOT"], "client_secret": os.environ["CLIENT_SECRET_MLOT"],
                               "refresh_token": os.environ["REFRESH_TOKEN_MLOT"], "secret_name": "REFRESH_TOKEN_MLOT"}

# ── Категория расхода по названию (как в веб-версии Allegro) ──
def cat_by_name(name):
    n = name.lower()
    if any(x in n for x in ["prowizja", "obowiązkow", "opłata transakcyjna"]):
        return "commission"   # Obowiązkowe
    if any(x in n for x in ["dostawa", "wysyłka", "kurier", "paczka", "inpost", "dpd", "gls", "ups"]):
        return "delivery"     # Dostawa
    if any(x in n for x in ["reklama", "kampania", "cpc", "ads", "promowanie", "wyróżnienie", "pogrubienie",
                              "podświetlenie", "strona działu", "pakiet promo", "brand zone"]):
        return "ads"          # Reklama i promowanie
    if any(x in n for x in ["abonament", "smart"]):
        return "subscription" # Abonament
    if any(x in n for x in ["rabat", "zwrot prowizji", "korekta"]):
        return "discount"     # Rabaty od Allegro (положительные)
    return "other"

# ── NBP курсы ─────────────────────────────────────────────────
_rates = {}
def get_rate(currency, date_str):
    if currency == "PLN": return 1.0
    key = f"{currency}_{date_str}"
    if key in _rates: return _rates[key]
    for delta in range(0, 7):
        d = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            r = requests.get(f"https://api.nbp.pl/api/exchangerates/rates/a/{currency.lower()}/{d}/?format=json", timeout=5)
            if r.status_code == 200:
                rate = float(r.json()["rates"][0]["mid"])
                _rates[key] = rate
                return rate
        except: pass
    return 1.0

# ── GitHub Secrets ────────────────────────────────────────────
def get_gh_pk():
    r = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
                     headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"})
    return r.json()

def update_gh_secret(name, val, key_id, key_val):
    pk = public.PublicKey(key_val.encode(), encoding.Base64Encoder())
    enc = base64.b64encode(public.SealedBox(pk).encrypt(val.encode())).decode()
    r = requests.put(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{name}",
                     headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
                     json={"encrypted_value": enc, "key_id": key_id})
    return r.status_code in (201, 204)

# ── OAuth ─────────────────────────────────────────────────────
def get_token(client_id, client_secret, refresh_token):
    r = requests.post("https://allegro.pl/auth/oauth/token", auth=(client_id, client_secret),
                      data={"grant_type": "refresh_token", "refresh_token": refresh_token, "redirect_uri": REDIRECT_URI})
    d = r.json()
    if "access_token" not in d:
        print(f"  Ошибка: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token", refresh_token)

def hdrs(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"}

# ── ПРОДАЖИ по странам ────────────────────────────────────────
def get_sales(token, date_from, date_to, date_key):
    countries = {k: 0.0 for k in MARKETPLACES}
    for mkt in MARKETPLACES:
        offset = 0
        while True:
            r = requests.get("https://api.allegro.pl/payments/payment-operations", headers=hdrs(token),
                             params={"group": "INCOME", "occurredAt.gte": date_from, "occurredAt.lte": date_to,
                                     "marketplaceId": mkt, "limit": 100, "offset": offset})
            ops = r.json().get("paymentOperations", [])
            for op in ops:
                try:
                    countries[mkt] += float(op["value"]["amount"]) * get_rate(op["value"]["currency"], date_key)
                except: pass
            if len(ops) < 100: break
            offset += 100
        countries[mkt] = round(countries[mkt], 2)
        if countries[mkt] > 0:
            print(f"    {mkt}: {countries[mkt]:.2f} PLN")
    return countries, round(sum(countries.values()), 2)

# ── РАСХОДЫ по категориям (по названию типа) ─────────────────
def get_costs(token, date_from, date_to):
    costs = {"commission": 0.0, "delivery": 0.0, "ads": 0.0, "subscription": 0.0, "discount": 0.0, "other": 0.0}
    unknown_types = {}
    offset = 0
    while True:
        r = requests.get("https://api.allegro.pl/billing/billing-entries", headers=hdrs(token),
                         params={"occurredAt.gte": date_from, "occurredAt.lte": date_to,
                                 "limit": 100, "offset": offset})
        entries = r.json().get("billingEntries", [])
        for e in entries:
            try:
                amount    = float(e["value"]["amount"])
                type_name = e["type"]["name"]
                type_id   = e["type"]["id"]
                cat       = cat_by_name(type_name)
                if amount < 0:
                    costs[cat] += abs(amount)
                elif amount > 0 and cat == "discount":
                    costs["discount"] += amount  # положительный = скидка от Allegro
                # Логируем неизвестные типы
                if cat == "other":
                    unknown_types[type_id] = type_name
            except: pass
        if len(entries) < 100: break
        offset += 100
    if unknown_types:
        print(f"    Неизвестные типы billing: {unknown_types}")
    costs = {k: round(v, 2) for k, v in costs.items()}
    print(f"    Obowiązkowe={costs['commission']} Dostawa={costs['delivery']} Reklama={costs['ads']} Abonament={costs['subscription']} Rabaty={costs['discount']}")
    return costs

# ── ОСНОВНОЙ ЦИКЛ ─────────────────────────────────────────────
print(f"Дата: {date_key} | UTC+{tz_offset} | {date_from} → {date_to}")
print(f"Магазины: {list(SHOPS.keys())}")

gh_key = get_gh_pk()
gh_key_id, gh_key_val = gh_key.get("key_id"), gh_key.get("key")

try:
    with open("data.json") as f: data = json.load(f)
except:
    data = {"days": [], "months": []}
if "months" not in data: data["months"] = []

existing = next((d for d in data["days"] if d["date"] == date_key), None)
if not existing:
    existing = {"date": date_key, "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0,
                "countries": {k: 0 for k in MARKETPLACES},
                "costs": {"commission": 0, "delivery": 0, "ads": 0, "subscription": 0, "discount": 0, "other": 0}}
    data["days"].append(existing)

all_countries = {k: 0.0 for k in MARKETPLACES}
all_costs     = {"commission": 0.0, "delivery": 0.0, "ads": 0.0, "subscription": 0.0, "discount": 0.0, "other": 0.0}

for shop, creds in SHOPS.items():
    print(f"\n--- {shop} ---")
    token, new_refresh = get_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if not token: continue
    if new_refresh and gh_key_id and gh_key_val:
        ok = update_gh_secret(creds["secret_name"], new_refresh, gh_key_id, gh_key_val)
        print(f"  Токен: {'OK' if ok else 'ERR'}")
    print("  Продажи:")
    countries, total = get_sales(token, date_from, date_to, date_key)
    existing[shop] = total
    for k, v in countries.items(): all_countries[k] = round(all_countries[k] + v, 2)
    print(f"  Итого: {total:.2f} PLN")
    print("  Расходы:")
    costs = get_costs(token, date_from, date_to)
    for k, v in costs.items(): all_costs[k] = round(all_costs[k] + v, 2)

existing["countries"] = all_countries
existing["costs"]     = {k: round(v, 2) for k, v in all_costs.items()}

# ── Месяцы ────────────────────────────────────────────────────
months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
monthly = {}
for day in data["days"]:
    mk = day["date"][:7]
    dt = datetime.strptime(mk, "%Y-%m")
    label = f"{months_ru[dt.month-1]} {dt.year}"
    if label not in monthly:
        monthly[label] = {"month": label, "_o": mk, "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0,
                          "countries": {k: 0.0 for k in MARKETPLACES},
                          "costs": {"commission": 0.0, "delivery": 0.0, "ads": 0.0, "subscription": 0.0, "discount": 0.0, "other": 0.0}}
    m = monthly[label]
    for s in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"]:
        m[s] = round(m[s] + day.get(s, 0), 2)
    for k in MARKETPLACES:
        m["countries"][k] = round(m["countries"][k] + day.get("countries", {}).get(k, 0), 2)
    for k in ["commission","delivery","ads","subscription","discount","other"]:
        m["costs"][k] = round(m["costs"][k] + day.get("costs", {}).get(k, 0), 2)

data["months"] = sorted(
    [{k: v for k, v in m.items() if k != "_o"} for m in monthly.values()],
    key=lambda x: monthly[x["month"]]["_o"]
)
with open("data.json", "w") as f: json.dump(data, f, indent=2, ensure_ascii=False)
print(f"\nОК: {json.dumps(existing, ensure_ascii=False)}")
