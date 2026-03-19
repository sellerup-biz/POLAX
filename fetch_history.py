import requests, json, os
from datetime import datetime, timedelta
from collections import defaultdict

CLIENT_ID    = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"

SHOPS = {}
if os.environ.get("REFRESH_TOKEN_SILA"):
    SHOPS["Sila_Narzedzi"] = os.environ["REFRESH_TOKEN_SILA"]
if os.environ.get("REFRESH_TOKEN_POLAX"):
    SHOPS["PolaxEuroGroup"] = os.environ["REFRESH_TOKEN_POLAX"]
if os.environ.get("REFRESH_TOKEN_MLOT"):
    SHOPS["Mlot_i_Klucz"] = os.environ["REFRESH_TOKEN_MLOT"]

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

def get_sales_for_day(access_token, date_key):
    date_from = date_key + "T00:00:00Z"
    date_to   = date_key + "T23:59:59Z"
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
        for o in orders:
            try:
                total += float(o["summary"]["totalToPay"]["amount"])
            except:
                pass
        if len(orders) < limit:
            break
        offset += limit
    return round(total, 2)

# Диапазон: с 1 января 2026 до вчера
start_date = datetime(2026, 1, 1)
end_date   = datetime.utcnow() - timedelta(days=1)

# Генерируем все даты
all_dates = []
d = start_date
while d <= end_date:
    all_dates.append(d.strftime("%Y-%m-%d"))
    d += timedelta(days=1)

print(f"Дат для обработки: {len(all_dates)}")
print(f"Активные магазины: {list(SHOPS.keys())}")

# Получаем access_token для каждого магазина один раз
tokens = {}
for shop, refresh in SHOPS.items():
    print(f"Получаем токен для {shop}...")
    token = get_access_token(refresh)
    if token:
        tokens[shop] = token
        print(f"  OK")
    else:
        print(f"  ОШИБКА")

# Строим data по дням
days_data = {}
for date_key in all_dates:
    days_data[date_key] = {
        "date":           date_key,
        "Mlot_i_Klucz":    0,
        "PolaxEuroGroup":  0,
        "Sila_Narzedzi":   0
    }

# Заполняем продажи
for shop, token in tokens.items():
    print(f"\n=== {shop} — загружаем историю ===")
    for date_key in all_dates:
        sales = get_sales_for_day(token, date_key)
        days_data[date_key][shop] = sales
        if sales > 0:
            print(f"  {date_key}: {sales} zł")

# Сортируем по дате
days_list = [days_data[d] for d in sorted(days_data.keys())]

# Считаем месяцы
months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
monthly = defaultdict(lambda: {"Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0})
month_order = {}

for day in days_list:
    month_key = day["date"][:7]
    dt = datetime.strptime(month_key, "%Y-%m")
    label = f"{months_ru[dt.month-1]} {dt.year}"
    month_order[label] = month_key
    for shop in ["Mlot_i_Klucz", "PolaxEuroGroup", "Sila_Narzedzi"]:
        monthly[label][shop] += day.get(shop, 0)

months_list = [
    {"month": k, **v}
    for k, v in sorted(monthly.items(), key=lambda x: month_order[x[0]])
]

# Округляем месячные суммы
for m in months_list:
    for shop in ["Mlot_i_Klucz", "PolaxEuroGroup", "Sila_Narzedzi"]:
        m[shop] = round(m[shop], 2)

result = {"days": days_list, "months": months_list}

with open("data.json", "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print("\n✓ data.json обновлён!")
print(f"Дней: {len(days_list)}")
print(f"Месяцев: {len(months_list)}")
for m in months_list:
    total = sum(m[s] for s in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"])
    print(f"  {m['month']}: {total:.2f} zł")
