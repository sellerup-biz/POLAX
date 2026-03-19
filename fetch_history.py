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

def get_sales_for_day(access_token, date_key):
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
            params={
                "lineItems.boughtAt.gte": date_key + "T00:00:00Z",
                "lineItems.boughtAt.lte": date_key + "T23:59:59Z",
                "limit": 100, "offset": offset
            }
        )
        orders = r.json().get("checkoutForms", [])
        for o in orders:
            try:
                total += float(o["summary"]["totalToPay"]["amount"])
            except:
                pass
        if len(orders) < 100:
            break
        offset += 100
    return round(total, 2)

# Диапазон с 1 января 2026 до вчера
start = datetime(2026, 1, 1)
end   = datetime.utcnow() - timedelta(days=1)
all_dates = []
d = start
while d <= end:
    all_dates.append(d.strftime("%Y-%m-%d"))
    d += timedelta(days=1)

print(f"Дат: {len(all_dates)} | Магазины: {list(SHOPS.keys())}")

# Получаем access_token один раз для каждого магазина
tokens = {}
for shop, creds in SHOPS.items():
    print(f"Токен для {shop}...")
    t = get_access_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if t:
        tokens[shop] = t
        print(f"  OK")
    else:
        print(f"  ОШИБКА — пропускаем")

# Строим структуру дней
days_data = {date: {"date": date, "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0}
             for date in all_dates}

# Заполняем продажи
for shop, token in tokens.items():
    print(f"\n=== {shop} ===")
    for date_key in all_dates:
        sales = get_sales_for_day(token, date_key)
        days_data[date_key][shop] = sales
        if sales > 0:
            print(f"  {date_key}: {sales} zł")

days_list = [days_data[d] for d in sorted(days_data.keys())]

# Считаем месяцы
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
    print(f"  {m['month']}: {total:.2f} zł")
