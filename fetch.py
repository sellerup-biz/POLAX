import requests, json, os
from datetime import datetime, timedelta

SHOPS = {
    "Mlot_i_Klucz": {
        "client_id":     os.environ["CLIENT_ID_MLOT"],
        "client_secret": os.environ["CLIENT_SECRET_MLOT"]
    },
    "PolaxEuroGroup": {
        "client_id":     os.environ["CLIENT_ID_POLAX"],
        "client_secret": os.environ["CLIENT_SECRET_POLAX"]
    },
    "Sila_Narzedzi": {
        "client_id":     os.environ["CLIENT_ID_SILA"],
        "client_secret": os.environ["CLIENT_SECRET_SILA"]
    }
}

def get_token(client_id, client_secret):
    r = requests.post(
        "https://allegro.pl/auth/oauth/token",
        params={"grant_type": "client_credentials"},
        auth=(client_id, client_secret)
    )
    return r.json()["access_token"]

def get_sales(token, date_from, date_to):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.allegro.public.v1+json"
    }
    r = requests.get(
        "https://api.allegro.pl/order/checkout-forms",
        headers=headers,
        params={
            "lineItems.boughtAt.gte": date_from,
            "lineItems.boughtAt.lte": date_to,
            "status": "BOUGHT"
        }
    )
    orders = r.json().get("checkoutForms", [])
    total = sum(
        float(o["summary"]["totalToPay"]["amount"])
        for o in orders
    )
    return round(total, 2)

yesterday = datetime.now() - timedelta(days=1)
date_from = yesterday.strftime("%Y-%m-%dT00:00:00Z")
date_to   = yesterday.strftime("%Y-%m-%dT23:59:59Z")
date_key  = yesterday.strftime("%Y-%m-%d")

try:
    with open("data.json", "r") as f:
        data = json.load(f)
except:
    data = {"days": []}

entry = {"date": date_key}
for shop_name, creds in SHOPS.items():
    token = get_token(creds["client_id"], creds["client_secret"])
    entry[shop_name] = get_sales(token, date_from, date_to)
    print(f"{shop_name}: {entry[shop_name]} zł")

dates = [d["date"] for d in data["days"]]
if date_key not in dates:
    data["days"].append(entry)

with open("data.json", "w") as f:
    json.dump(data, f, indent=2)

print("data.json updated!")
