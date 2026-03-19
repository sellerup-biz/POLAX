import requests, json, os, base64
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

SHOPS = {}
if os.environ.get("CLIENT_ID_SILA") and os.environ.get("REFRESH_TOKEN_SILA"):
    SHOPS["Sila_Narzedzi"] = {
        "client_id":     os.environ["CLIENT_ID_SILA"],
        "client_secret": os.environ["CLIENT_SECRET_SILA"],
        "refresh_token": os.environ["REFRESH_TOKEN_SILA"],
        "secret_name":   "REFRESH_TOKEN_SILA"
    }
if os.environ.get("CLIENT_ID_POLAX") and os.environ.get("REFRESH_TOKEN_POLAX"):
    SHOPS["PolaxEuroGroup"] = {
        "client_id":     os.environ["CLIENT_ID_POLAX"],
        "client_secret": os.environ["CLIENT_SECRET_POLAX"],
        "refresh_token": os.environ["REFRESH_TOKEN_POLAX"],
        "secret_name":   "REFRESH_TOKEN_POLAX"
    }
if os.environ.get("CLIENT_ID_MLOT") and os.environ.get("REFRESH_TOKEN_MLOT"):
    SHOPS["Mlot_i_Klucz"] = {
        "client_id":     os.environ["CLIENT_ID_MLOT"],
        "client_secret": os.environ["CLIENT_SECRET_MLOT"],
        "refresh_token": os.environ["REFRESH_TOKEN_MLOT"],
        "secret_name":   "REFRESH_TOKEN_MLOT"
    }

_rates_cache = {}

def get_rate_to_pln(currency, date_str):
    if currency == "PLN":
        return 1.0
    key = f"{currency}_{date_str}"
    if key in _rates_cache:
        return _rates_cache[key]
    cur = currency.lower()
    for delta in range(0, 7):
        try_date = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            r = requests.get(
                f"https://api.nbp.pl/api/exchangerates/rates/a/{cur}/{try_date}/?format=json",
                timeout=5
            )
            if r.status_code == 200:
                rate = float(r.json()["rates"][0]["mid"])
                _rates_cache[key] = rate
                return rate
        except:
            pass
    return 1.0

def get_gh_public_key():
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
        headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
    )
    return r.json()

def encrypt_secret(public_key_str, secret_value):
    pk = public.PublicKey(public_key_str.encode("utf-8"), encoding.Base64Encoder())
    box = public.SealedBox(pk)
    encrypted = box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")

def update_gh_secret(secret_name, secret_value, key_id, key_val):
    encrypted = encrypt_secret(key_val, secret_value)
    r = requests.put(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
        headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"encrypted_value": encrypted, "key_id": key_id}
    )
    return r.status_code in (201, 204)

def get_access_token(client_id, client_secret, refresh_token):
    r = requests.post(
        "https://allegro.pl/auth/oauth/token",
        auth=(client_id, client_secret),
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri":  REDIRECT_URI
        }
    )
    d = r.json()
    if "access_token" not in d:
        print(f"  Ошибка токена: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token", refresh_token)

def get_tz_offset(month):
    return 2 if 3 <= month <= 10 else 1

def get_sales_for_day(access_token, date_key):
    month     = int(date_key[5:7])
    tz        = get_tz_offset(month)
    tz_str    = f"+0{tz}:00"
    date_from = date_key + f"T00:00:00{tz_str}"
    date_to   = date_key + f"T23:59:59{tz_str}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.allegro.public.v1+json"
    }
    total_pln = 0.0
    offset = 0
    while True:
        r = requests.get(
            "https://api.allegro.pl/payments/payment-operations",
            headers=headers,
            params={
                "group":          "INCOME",
                "occurredAt.gte": date_from,
                "occurredAt.lte": date_to,
                "limit": 100, "offset": offset
            }
        )
        ops = r.json().get("paymentOperations", [])
        for op in ops:
            try:
                amount   = float(op["value"]["amount"])
                currency = op["value"]["currency"]
                rate     = get_rate_to_pln(currency, date_key)
                total_pln += amount * rate
            except:
                pass
        if len(ops) < 100:
            break
        offset += 100
    return round(total_pln, 2)

# Диапазон с 1 января 2026 до вчера
now_utc    = datetime.now(timezone.utc)
tz_offset  = get_tz_offset(now_utc.month)
polish_now = now_utc + timedelta(hours=tz_offset)
yesterday  = (polish_now - timedelta(days=1)).replace(tzinfo=None)

start = datetime(2026, 1, 1)
all_dates = []
d = start
while d <= yesterday:
    all_dates.append(d.strftime("%Y-%m-%d"))
    d += timedelta(days=1)

print(f"Дат: {len(all_dates)} | Магазины: {list(SHOPS.keys())}")

gh_key    = get_gh_public_key()
gh_key_id  = gh_key.get("key_id")
gh_key_val = gh_key.get("key")

tokens = {}
for shop, creds in SHOPS.items():
    print(f"Токен для {shop}...")
    t, new_refresh = get_access_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if t:
        tokens[shop] = t
        if new_refresh and gh_key_id and gh_key_val:
            ok = update_gh_secret(creds["secret_name"], new_refresh, gh_key_id, gh_key_val)
            print(f"  Токен обновлён: {'OK' if ok else 'ОШИБКА'}")
    else:
        print(f"  ОШИБКА — пропускаем")

days_data = {date: {"date": date, "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0}
             for date in all_dates}

for shop, token in tokens.items():
    print(f"\n=== {shop} ===")
    for date_key in all_dates:
        sales = get_sales_for_day(token, date_key)
        days_data[date_key][shop] = sales
        if sales > 0:
            print(f"  {date_key}: {sales:.2f} PLN")

days_list = [days_data[d] for d in sorted(days_data.keys())]

months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
monthly = defaultdict(lambda: {"Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0})
month_order = {}
for day in days_list:
    mk = day["date"][:7]
    dt = datetime.strptime(mk, "%Y-%m")
    label = f"{months_ru[dt.month-1]} {dt.year}"
    month_order[label] = mk
    for s in ["Mlot_i_Klucz", "PolaxEuroGroup", "Sila_Narzedzi"]:
        monthly[label][s] += day.get(s, 0)

months_list = [{"month": k, **{s: round(v[s], 2) for s in v}}
               for k, v in sorted(monthly.items(), key=lambda x: month_order[x[0]])]

result = {"days": days_list, "months": months_list}
with open("data.json", "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print(f"\nГотово! Дней: {len(days_list)} | Месяцев: {len(months_list)}")
for m in months_list:
    total = sum(m[s] for s in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"])
    print(f"  {m['month']}: {total:.2f} PLN")
