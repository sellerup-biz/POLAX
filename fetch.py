import requests, json, os
from datetime import datetime, timedelta
from collections import defaultdict

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"

SHOPS = {}
if os.environ.get("CLIENT_ID_SILA") and os.environ.get("REFRESH_TOKEN_SILA"):
    SHOPS["Sila_Narzedzi"] = {
        "client_id":     os.environ["CLIENT_ID_SILA"],
        "client_secret": os.environ["CLIENT_SECRET_SILA"],
        "refresh_token": os.environ["REFRESH_TOKEN_SILA"]
    }
if os.environ.get("CLIENT_ID_POLAX") and os.environ.get("REFRESH_TOKEN_POLAX"):
    SHOPS["PolaxEuroGroup"] = {
        "client_id":     os.environ["CLIENT_ID_POLAX"],
        "client_secret": os.environ["CLIENT_SECRET_POLAX"],
        "refresh_token": os.environ["REFRESH_TOKEN_POLAX"]
    }
if os.environ.get("CLIENT_ID_MLOT") and os.environ.get("REFRESH_TOKEN_MLOT"):
    SHOPS["Mlot_i_Klucz"] = {
        "client_id":     os.environ["CLIENT_ID_MLOT"],
        "client_secret": os.environ["CLIENT_SECRET_MLOT"],
        "refresh_token": os.environ["REFRESH_TOKEN_MLOT"]
    }

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
        print(f"Ошибка токена: {d}")
        return None
    return d["access_token"]

def get_sales(access_token, date_from, date_to):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.allegro.public.v1+json"
    }
    total = 0.0
    offset = 0
    while True:
        r = requests.get(
            "https://api.allegro.pl/order/checkout-forms",
            headers=headers,
            params={"lineItems.boughtAt.gte": date_from, "lineItems.boughtAt.lte": date_to, "limit": 100, "offset": offset}
        )
        orders = r.json().get("checkoutForms", [])
        print(f"  Заказов: {len(orders)} (offset={offset})")
        for o in orders:
            try:
                total += float(o["summary"]["totalToPay"]["amount"])
            except:
                pass
        if len(orders) < 100:
            break
        offset += 100
    return round(total, 2)

yesterday = datetime.utcnow() - timedelta(days=1)
date_from = yesterday.strftime("%Y-%m-%dT00:00:00Z")
date_to   = yesterday.strftime("%Y-%m-%dT23:59:59Z")
date_key  = yesterday.strftime("%Y-%m-%d")

print(f"Дата: {date_key} | Магазины: {list(SHOPS.keys())}")

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
    token = get_access_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if not token:
        continue
    sales = get_sales(token, date_from, date_to)
    existing[shop] = sales
    print(f"Итого: {sales} zł")

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

data["months"] = [{"month": k, **{s: round(v[s], 2) for s in v}}
                  for k, v in sorted(monthly.items(), key=lambda x: month_order[x[0]])]

with open("data.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\nОК: {json.dumps(existing, ensure_ascii=False)}")
