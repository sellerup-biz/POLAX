import requests, json, os, base64
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

MARKETPLACES = {
    "allegro-pl": "PLN",
    "allegro-cz": "CZK",
    "allegro-hu": "HUF",
    "allegro-sk": "EUR",
}

BILLING_CATEGORIES = {
    "commission": ["SUC", "SUJ"],
    "ads":        ["CPC", "ADS", "ADG"],
    "delivery":   ["KOS", "ZDO", "ZWP", "ZPP"],
    "promo":      ["WYR", "POD", "BOL", "DEP", "EMF", "EMB", "EMH"],
    "other":      ["LIS", "ABN", "OTH"],
}

def cat_for_type(type_id):
    for cat, ids in BILLING_CATEGORIES.items():
        if type_id in ids:
            return cat
    return "other"

SHOPS = {}
if os.environ.get("CLIENT_ID_SILA") and os.environ.get("REFRESH_TOKEN_SILA"):
    SHOPS["Sila_Narzedzi"] = {
        "client_id": os.environ["CLIENT_ID_SILA"], "client_secret": os.environ["CLIENT_SECRET_SILA"],
        "refresh_token": os.environ["REFRESH_TOKEN_SILA"], "secret_name": "REFRESH_TOKEN_SILA"
    }
if os.environ.get("CLIENT_ID_POLAX") and os.environ.get("REFRESH_TOKEN_POLAX"):
    SHOPS["PolaxEuroGroup"] = {
        "client_id": os.environ["CLIENT_ID_POLAX"], "client_secret": os.environ["CLIENT_SECRET_POLAX"],
        "refresh_token": os.environ["REFRESH_TOKEN_POLAX"], "secret_name": "REFRESH_TOKEN_POLAX"
    }
if os.environ.get("CLIENT_ID_MLOT") and os.environ.get("REFRESH_TOKEN_MLOT"):
    SHOPS["Mlot_i_Klucz"] = {
        "client_id": os.environ["CLIENT_ID_MLOT"], "client_secret": os.environ["CLIENT_SECRET_MLOT"],
        "refresh_token": os.environ["REFRESH_TOKEN_MLOT"], "secret_name": "REFRESH_TOKEN_MLOT"
    }

_rates_cache = {}
def get_rate(currency, date_str):
    if currency == "PLN": return 1.0
    key = f"{currency}_{date_str}"
    if key in _rates_cache: return _rates_cache[key]
    for delta in range(0, 7):
        d = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            r = requests.get(f"https://api.nbp.pl/api/exchangerates/rates/a/{currency.lower()}/{d}/?format=json", timeout=5)
            if r.status_code == 200:
                rate = float(r.json()["rates"][0]["mid"])
                _rates_cache[key] = rate
                return rate
        except: pass
    return 1.0

def get_gh_public_key():
    r = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
                     headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"})
    return r.json()

def encrypt_secret(pk_str, val):
    pk = public.PublicKey(pk_str.encode(), encoding.Base64Encoder())
    return base64.b64encode(public.SealedBox(pk).encrypt(val.encode())).decode()

def update_gh_secret(name, val, key_id, key_val):
    r = requests.put(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{name}",
                     headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
                     json={"encrypted_value": encrypt_secret(key_val, val), "key_id": key_id})
    return r.status_code in (201, 204)

def get_access_token(client_id, client_secret, refresh_token):
    r = requests.post("https://allegro.pl/auth/oauth/token", auth=(client_id, client_secret),
                      data={"grant_type": "refresh_token", "refresh_token": refresh_token, "redirect_uri": REDIRECT_URI})
    d = r.json()
    if "access_token" not in d:
        print(f"  Ошибка: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token", refresh_token)

def hdrs(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"}

def get_tz(month):
    return 2 if 3 <= month <= 10 else 1

def get_sales_for_day(token, date_key):
    month = int(date_key[5:7])
    tz    = get_tz(month)
    tz_s  = f"+0{tz}:00"
    df    = date_key + f"T00:00:00{tz_s}"
    dt    = date_key + f"T23:59:59{tz_s}"
    countries = {"allegro-pl": 0.0, "allegro-cz": 0.0, "allegro-hu": 0.0, "allegro-sk": 0.0}
    for marketplace in MARKETPLACES:
        offset = 0
        while True:
            r = requests.get("https://api.allegro.pl/payments/payment-operations", headers=hdrs(token),
                             params={"group": "INCOME", "occurredAt.gte": df, "occurredAt.lte": dt,
                                     "marketplaceId": marketplace, "limit": 100, "offset": offset})
            ops = r.json().get("paymentOperations", [])
            for op in ops:
                try:
                    amount = float(op["value"]["amount"])
                    cur    = op["value"]["currency"]
                    countries[marketplace] += amount * get_rate(cur, date_key)
                except: pass
            if len(ops) < 100: break
            offset += 100
    total = round(sum(countries.values()), 2)
    countries = {k: round(v, 2) for k, v in countries.items()}
    return total, countries

def get_costs_for_day(token, date_key):
    month = int(date_key[5:7])
    tz    = get_tz(month)
    tz_s  = f"+0{tz}:00"
    df    = date_key + f"T00:00:00{tz_s}"
    dt    = date_key + f"T23:59:59{tz_s}"
    costs = {"commission": 0.0, "ads": 0.0, "delivery": 0.0, "promo": 0.0, "other": 0.0}
    offset = 0
    while True:
        r = requests.get("https://api.allegro.pl/billing/billing-entries", headers=hdrs(token),
                         params={"occurredAt.gte": df, "occurredAt.lte": dt, "limit": 100, "offset": offset})
        entries = r.json().get("billingEntries", [])
        for e in entries:
            try:
                amount = float(e["value"]["amount"])
                if amount < 0:
                    costs[cat_for_type(e["type"]["id"])] += abs(amount)
            except: pass
        if len(entries) < 100: break
        offset += 100
    return {k: round(v, 2) for k, v in costs.items()}

# Диапазон дат
now_utc    = datetime.now(timezone.utc)
tz_offset  = get_tz(now_utc.month)
polish_now = now_utc + timedelta(hours=tz_offset)
yesterday  = (polish_now - timedelta(days=1)).replace(tzinfo=None)
start      = datetime(2026, 1, 1)
all_dates  = []
d = start
while d <= yesterday:
    all_dates.append(d.strftime("%Y-%m-%d"))
    d += timedelta(days=1)

print(f"Дат: {len(all_dates)} | Магазины: {list(SHOPS.keys())}")

gh_key    = get_gh_public_key()
gh_key_id  = gh_key.get("key_id")
gh_key_val = gh_key.get("key")

# Получаем токены и сразу обновляем
tokens = {}
for shop, creds in SHOPS.items():
    print(f"Токен для {shop}...")
    t, new_refresh = get_access_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if t:
        tokens[shop] = t
        if new_refresh and gh_key_id and gh_key_val:
            ok = update_gh_secret(creds["secret_name"], new_refresh, gh_key_id, gh_key_val)
            print(f"  Обновлён: {'OK' if ok else 'ERR'}")
    else:
        print("  ОШИБКА")

# Строим дни
days_data = {}
for date_key in all_dates:
    days_data[date_key] = {
        "date": date_key,
        "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0,
        "countries": {"allegro-pl": 0, "allegro-cz": 0, "allegro-hu": 0, "allegro-sk": 0},
        "costs": {"commission": 0, "ads": 0, "delivery": 0, "promo": 0, "other": 0}
    }

# Собираем по каждому магазину
for shop, token in tokens.items():
    print(f"\n=== {shop} ===")
    for date_key in all_dates:
        sales, countries = get_sales_for_day(token, date_key)
        costs            = get_costs_for_day(token, date_key)
        days_data[date_key][shop] = sales
        # Страны — суммируем по всем магазинам
        for k in countries:
            days_data[date_key]["countries"][k] = round(days_data[date_key]["countries"][k] + countries[k], 2)
        # Расходы — суммируем по всем магазинам
        for k in costs:
            days_data[date_key]["costs"][k] = round(days_data[date_key]["costs"][k] + costs[k], 2)
        total = sales + sum(costs.values())
        if total > 0:
            print(f"  {date_key}: продажи={sales:.0f} расходы={sum(costs.values()):.0f} PLN")

days_list = [days_data[d] for d in sorted(days_data.keys())]

# Месяцы
months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
monthly   = {}
for day in days_list:
    mk = day["date"][:7]
    dt = datetime.strptime(mk, "%Y-%m")
    label = f"{months_ru[dt.month-1]} {dt.year}"
    if label not in monthly:
        monthly[label] = {
            "month": label, "_order": mk,
            "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0,
            "countries": {"allegro-pl": 0, "allegro-cz": 0, "allegro-hu": 0, "allegro-sk": 0},
            "costs": {"commission": 0, "ads": 0, "delivery": 0, "promo": 0, "other": 0}
        }
    m = monthly[label]
    for s in ["Mlot_i_Klucz", "PolaxEuroGroup", "Sila_Narzedzi"]:
        m[s] = round(m[s] + day.get(s, 0), 2)
    for k in ["allegro-pl", "allegro-cz", "allegro-hu", "allegro-sk"]:
        m["countries"][k] = round(m["countries"][k] + day.get("countries", {}).get(k, 0), 2)
    for k in ["commission", "ads", "delivery", "promo", "other"]:
        m["costs"][k] = round(m["costs"][k] + day.get("costs", {}).get(k, 0), 2)

months_list = sorted(
    [{k: v for k, v in m.items() if k != "_order"} for m in monthly.values()],
    key=lambda x: monthly[x["month"]]["_order"]
)

result = {"days": days_list, "months": months_list}
with open("data.json", "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print(f"\nГотово! Дней: {len(days_list)} | Месяцев: {len(months_list)}")
for m in months_list:
    sales = sum(m[s] for s in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"])
    costs = sum(m["costs"].values())
    print(f"  {m['month']}: продажи={sales:.0f} расходы={costs:.0f} PLN")
