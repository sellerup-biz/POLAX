import requests, json, os, base64
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

# Польское время
now_utc   = datetime.now(timezone.utc)
tz_offset = 2 if 3 <= now_utc.month <= 10 else 1
polish_now   = now_utc + timedelta(hours=tz_offset)
yesterday_pl = polish_now - timedelta(days=1)
tz_str       = f"+0{tz_offset}:00"
date_from    = yesterday_pl.strftime("%Y-%m-%dT00:00:00") + tz_str
date_to      = yesterday_pl.strftime("%Y-%m-%dT23:59:59") + tz_str
date_key     = yesterday_pl.strftime("%Y-%m-%d")

# Страны Allegro → валюты
MARKETPLACES = {
    "allegro-pl": "PLN",
    "allegro-cz": "CZK",
    "allegro-hu": "HUF",
    "allegro-sk": "EUR",
}

# Коды типов billing → категория расходов
BILLING_CATEGORIES = {
    "commission":  ["SUC", "SUJ"],
    "ads":         ["CPC", "ADS", "ADG"],
    "delivery":    ["KOS", "ZDO", "ZWP", "ZPP"],
    "promo":       ["WYR", "POD", "BOL", "DEP", "EMF", "EMB", "EMH"],
    "other":       ["LIS", "ABN", "OTH"],
}

def cat_for_type(type_id):
    for cat, ids in BILLING_CATEGORIES.items():
        if type_id in ids:
            return cat
    return "other"

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

# ── NBP курсы ────────────────────────────────────────────────
_rates_cache = {}
def get_rate(currency, date_str):
    if currency == "PLN":
        return 1.0
    key = f"{currency}_{date_str}"
    if key in _rates_cache:
        return _rates_cache[key]
    for delta in range(0, 7):
        d = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            r = requests.get(
                f"https://api.nbp.pl/api/exchangerates/rates/a/{currency.lower()}/{d}/?format=json",
                timeout=5
            )
            if r.status_code == 200:
                rate = float(r.json()["rates"][0]["mid"])
                _rates_cache[key] = rate
                return rate
        except:
            pass
    return 1.0

# ── GitHub Secrets ────────────────────────────────────────────
def get_gh_public_key():
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
        headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
    )
    return r.json()

def encrypt_secret(public_key_str, secret_value):
    pk = public.PublicKey(public_key_str.encode("utf-8"), encoding.Base64Encoder())
    box = public.SealedBox(pk)
    return base64.b64encode(box.encrypt(secret_value.encode("utf-8"))).decode("utf-8")

def update_gh_secret(secret_name, secret_value, key_id, key_val):
    r = requests.put(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
        headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"encrypted_value": encrypt_secret(key_val, secret_value), "key_id": key_id}
    )
    return r.status_code in (201, 204)

# ── OAuth ─────────────────────────────────────────────────────
def get_access_token(client_id, client_secret, refresh_token):
    r = requests.post(
        "https://allegro.pl/auth/oauth/token",
        auth=(client_id, client_secret),
        data={"grant_type": "refresh_token", "refresh_token": refresh_token, "redirect_uri": REDIRECT_URI}
    )
    d = r.json()
    if "access_token" not in d:
        print(f"  Ошибка токена: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token", refresh_token)

def allegro_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.allegro.public.v1+json"
    }

# ── ПРОДАЖИ по странам ────────────────────────────────────────
def get_sales_by_country(token, date_from, date_to, date_key):
    result = {}
    total_pln = 0.0
    for marketplace, currency in MARKETPLACES.items():
        mkt_total = 0.0
        offset = 0
        while True:
            r = requests.get(
                "https://api.allegro.pl/payments/payment-operations",
                headers=allegro_headers(token),
                params={
                    "group":           "INCOME",
                    "occurredAt.gte":  date_from,
                    "occurredAt.lte":  date_to,
                    "marketplaceId":   marketplace,
                    "limit": 100, "offset": offset
                }
            )
            ops = r.json().get("paymentOperations", [])
            for op in ops:
                try:
                    amount = float(op["value"]["amount"])
                    cur    = op["value"]["currency"]
                    rate   = get_rate(cur, date_key)
                    mkt_total += amount * rate
                except:
                    pass
            if len(ops) < 100:
                break
            offset += 100
        result[marketplace] = round(mkt_total, 2)
        total_pln += mkt_total
        print(f"    {marketplace}: {mkt_total:.2f} PLN")
    return result, round(total_pln, 2)

# ── РАСХОДЫ по категориям ─────────────────────────────────────
def get_billing_types(token):
    """Получаем актуальный список типов billing для маппинга"""
    r = requests.get(
        "https://api.allegro.pl/billing/billing-types",
        headers=allegro_headers(token)
    )
    return r.json()

def get_costs_by_category(token, date_from, date_to, date_key):
    costs = {"commission": 0.0, "ads": 0.0, "delivery": 0.0, "promo": 0.0, "other": 0.0}
    offset = 0
    total_ops = 0
    while True:
        r = requests.get(
            "https://api.allegro.pl/billing/billing-entries",
            headers=allegro_headers(token),
            params={
                "occurredAt.gte": date_from,
                "occurredAt.lte": date_to,
                "limit": 100, "offset": offset
            }
        )
        data  = r.json()
        entries = data.get("billingEntries", [])
        total_ops += len(entries)
        for e in entries:
            try:
                amount  = float(e["value"]["amount"])
                type_id = e["type"]["id"]
                cat     = cat_for_type(type_id)
                # Расходы — отрицательные суммы
                if amount < 0:
                    costs[cat] += abs(amount)
            except:
                pass
        if len(entries) < 100:
            break
        offset += 100
    costs = {k: round(v, 2) for k, v in costs.items()}
    print(f"    Billing записей: {total_ops} | Расходы: {sum(costs.values()):.2f} PLN")
    return costs

# ── ОСНОВНОЙ ЦИКЛ ─────────────────────────────────────────────
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

# Находим или создаём запись за вчера
existing = next((d for d in data["days"] if d["date"] == date_key), None)
if not existing:
    existing = {
        "date": date_key,
        "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0,
        "countries": {"allegro-pl": 0, "allegro-cz": 0, "allegro-hu": 0, "allegro-sk": 0},
        "costs": {"commission": 0, "ads": 0, "delivery": 0, "promo": 0, "other": 0}
    }
    data["days"].append(existing)

# Агрегация по всем магазинам для стран и расходов
all_countries = {"allegro-pl": 0.0, "allegro-cz": 0.0, "allegro-hu": 0.0, "allegro-sk": 0.0}
all_costs     = {"commission": 0.0, "ads": 0.0, "delivery": 0.0, "promo": 0.0, "other": 0.0}

for shop, creds in SHOPS.items():
    print(f"\n--- {shop} ---")
    token, new_refresh = get_access_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if not token:
        continue
    if new_refresh and gh_key_id and gh_key_val:
        ok = update_gh_secret(creds["secret_name"], new_refresh, gh_key_id, gh_key_val)
        print(f"  Токен обновлён: {'OK' if ok else 'ОШИБКА'}")

    # Продажи по странам
    print("  Продажи по странам:")
    countries, total_sales = get_sales_by_country(token, date_from, date_to, date_key)
    existing[shop] = total_sales
    for mkt, val in countries.items():
        all_countries[mkt] = round(all_countries[mkt] + val, 2)
    print(f"  Итого продажи: {total_sales:.2f} PLN")

    # Расходы
    print("  Расходы (billing):")
    costs = get_costs_by_category(token, date_from, date_to, date_key)
    for cat, val in costs.items():
        all_costs[cat] = round(all_costs[cat] + val, 2)

existing["countries"] = all_countries
existing["costs"]     = all_costs

print(f"\nСтраны: {all_countries}")
print(f"Расходы: {all_costs}")

# ── Пересчёт месяцев ──────────────────────────────────────────
months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
monthly   = {}

for day in data["days"]:
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

data["months"] = sorted(
    [{k: v for k, v in m.items() if k != "_order"} for m in monthly.values()],
    key=lambda x: monthly[x["month"]]["_order"]
)

with open("data.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\nОК: {json.dumps(existing, ensure_ascii=False)}")
