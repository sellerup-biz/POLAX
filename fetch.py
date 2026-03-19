import requests, json, os
from datetime import datetime, timedelta
from collections import defaultdict

CLIENT_ID     = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REDIRECT_URI  = "https://sellerup-biz.github.io/POLAX/callback.html"

# Только те магазины у которых есть refresh_token
SHOPS = {}

if os.environ.get("REFRESH_TOKEN_SILA"):
    SHOPS["Sila_Narzedzi"] = os.environ["REFRESH_TOKEN_SILA"]
if os.environ.get("REFRESH_TOKEN_MLOT"):
    SHOPS["Mlot_i_Klucz"] = os.environ["REFRESH_TOKEN_MLOT"]
if os.environ.get("REFRESH_TOKEN_POLAX"):
    SHOPS["PolaxEuroGroup"] = os.environ["REFRESH_TOKEN_POLAX"]

def get_access_token(refresh_token):
    r = requests.post(
        "https://allegro.pl/auth/oauth/token",
        auth=(CLIENT_ID, CLIENT_SECRET),
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri":  REDIRECT_URI
        }
    )
    data = r.json()
    if "access_token" not in data:
        print(f"Ошибка токена: {data}")
        return None
    return data["access_token"]

def get_sales(access_token, date_from, date_to):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept":        "application/vnd.allegro.public.v1+json"
    }
    total  = 0.0
    offset = 0
    limit  = 100

    while True:
        r = requests.get(
            "https://api.allegro.pl/order/checkout-forms",
            headers=headers,
            params={
                "lineItems.boughtAt.gte": date_from,
                "lineItems.boughtAt.lte": date_to,
                "limit":  limit,
                "offset": offset
            }
        )
        data   = r.json()
        orders = data.get("checkoutForms", [])
        print(f"  Получено заказов: {len(orders)} (offset={offset})")

        for o in orders:
            try:
                total += float(o["summary"]["totalToPay"]["amount"])
            except:
                pass

        if len(orders) < limit:
            break
        offset += limit

    return round(total, 2)

# Вчерашняя дата (польское время UTC+2)
yesterday  = datetime.utcnow() - timedelta(days=1)
date_from  = yesterday.strftime("%Y-%m-%dT00:00:00Z")
date_to    = yesterday.strftime("%Y-%m-%dT23:59:59Z")
date_key   = yesterday.strftime("%Y-%m-%d")

print(f"Собираем данные за: {date_key}")
print(f"Активные магазины: {list(SHOPS.keys())}")

# Читаем старый data.json
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
        "date":          date_key,
        "Mlot_i_Klucz":    0,
        "PolaxEuroGroup":  0,
        "Sila_Narzedzi":   0
    }
    data["days"].append(existing)

# Получаем продажи по каждому магазину
for shop_name, refresh_token in SHOPS.items():
    print(f"\n--- {shop_name} ---")
    token = get_access_token(refresh_token)
    if not token:
        print(f"Пропускаем {shop_name} — нет токена")
        continue
    sales = get_sales(token, date_from, date_to)
    existing[shop_name] = sales
    print(f"Итого {shop_name}: {sales} zł")

# Пересчитываем месяцы
monthly = defaultdict(lambda: {"Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0})
for day in data["days"]:
    month_key = day["date"][:7]
    dt = datetime.strptime(month_key, "%Y-%m")
    months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
    label = f"{months_ru[dt.month-1]} {dt.year}"
    for shop in ["Mlot_i_Klucz", "PolaxEuroGroup", "Sila_Narzedzi"]:
        monthly[label][shop] += day.get(shop, 0)

data["months"] = [{"month": k, **v} for k, v in sorted(monthly.items())]

# Сохраняем
with open("data.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("\ndata.json обновлён!")
print(json.dumps(existing, ensure_ascii=False, indent=2))
