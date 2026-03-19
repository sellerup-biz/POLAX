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

# Кэш курсов НБП
_rates_cache = {}

def get_rate_to_pln(currency, date_str):
    """Получить курс валюты к PLN через NBP API на конкретную дату"""
    if currency == "PLN":
        return 1.0
    key = f"{currency}_{date_str}"
    if key in _rates_cache:
        return _rates_cache[key]
    cur = currency.lower()
    # Пробуем дату, если выходной — берём предыдущий рабочий день
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
                print(f"  Курс {currency}/PLN на {try_date}: {rate}")
                return rate
        except:
            pass
    print(f"  Курс {currency} не найден, используем 1.0")
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

def get_sales(access_token, date_from, date_to, date_key):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.allegro.public.v1+json"
    }
    total_pln = 0.0
    by_currency = defaultdict(float)
    offset = 0
    while True:
        r = requests.get(
            "https://api.allegro.pl/payments/payment-operations",
            headers=headers,
            params={
                "group":          "INCOME",
                "occurredAt.gte": date_from,
                "occurredAt.lte": date_to,
                "limit":  100,
                "offset": offset
            }
        )
        ops = r.json().get("paymentOperations", [])
        print(f"  Операций INCOME: {len(ops)} (offset={offset})")
        for op in ops:
            try:
                amount   = float(op["value"]["amount"])
                currency = op["value"]["currency"]
                by_currency[currency] += amount
                rate = get_rate_to_pln(currency, date_key)
                total_pln += amount * rate
            except:
                pass
        if len(ops) < 100:
            break
        offset += 100

    # Печатаем разбивку по валютам
    for cur, amt in by_currency.items():
        rate = get_rate_to_pln(cur, date_key)
        print(f"  {cur}: {amt:.2f} × {rate:.4f} = {amt*rate:.2f} PLN")

    return round(total_pln, 2)

print(f"Дата (Польша UTC+{tz_offset}): {date_key}")
print(f"Период: {date_from} → {date_to}")
print(f"Магазины: {list(SHOPS.keys())}")

gh_key    = get_gh_public_key()
gh_key_id  = gh_key.get("key_id")
gh_key_val = gh_key.get("key")

try:
    with open("data.json", "r") as f:
        data = json.load(f)
except:
    data = {"days": [], "months": []}
if "months" not in data:
    data["months"] = []

existing = next((d for d in data["days"] if d["date"] == date_key), None)
if not existing:
    existing = {"date": date_key, "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0}
    data["days"].append(existing)

for shop, creds in SHOPS.items():
    print(f"\n--- {shop} ---")
    token, new_refresh = get_access_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if not token:
        continue
    if new_refresh and gh_key_id and gh_key_val:
        ok = update_gh_secret(creds["secret_name"], new_refresh, gh_key_id, gh_key_val)
        print(f"  Токен обновлён: {'OK' if ok else 'ОШИБКА'}")
    sales = get_sales(token, date_from, date_to, date_key)
    existing[shop] = sales
    print(f"  Итого в PLN: {sales} zł")

months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
monthly = defaultdict(lambda: {"Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0})
month_order = {}
for day in data["days"]:
    mk = day["date"][:7]
    dt = datetime.strptime(mk, "%Y-%m")
    label = f"{months_ru[dt.month-1]} {dt.year}"
    month_order[label] = mk
    for s in ["Mlot_i_Klucz", "PolaxEuroGroup", "Sila_Narzedzi"]:
        monthly[label][s] += day.get(s, 0)

data["months"] = [
    {"month": k, **{s: round(v[s], 2) for s in v}}
    for k, v in sorted(monthly.items(), key=lambda x: month_order[x[0]])
]

with open("data.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\nОК: {json.dumps(existing, ensure_ascii=False)}")
