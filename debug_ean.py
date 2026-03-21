import requests, os
try:
    from dotenv import load_dotenv; load_dotenv()
except: pass

TOKEN_URL = "https://allegro.pl/auth/oauth/token"
REDIRECT  = "https://sellerup-biz.github.io/POLAX/callback.html"

def get_token(cid, cs, rt):
    r = requests.post(TOKEN_URL, auth=(cid,cs),
        data={"grant_type":"refresh_token","refresh_token":rt,"redirect_uri":REDIRECT}, timeout=20)
    return r.json().get("access_token")

# Используем POLAX токен
cid = os.environ.get("CLIENT_ID_POLAX","")
cs  = os.environ.get("CLIENT_SECRET_POLAX","")
rt  = os.environ.get("REFRESH_TOKEN_POLAX","")

if not cid:
    print("Нет токенов в .env"); exit(1)

token = get_token(cid, cs, rt)
if not token:
    print("Ошибка токена"); exit(1)

hdrs = {"Authorization":f"Bearer {token}","Accept":"application/vnd.allegro.public.v1+json"}

# Проверяем разные рекламные эндпоинты
endpoints = [
    "/sale/offer-statistics",
    "/ads/campaigns",
    "/sale/offers/sponsored",
    "/reporting/revenue-by-offer",
]

for ep in endpoints:
    r = requests.get(f"https://api.allegro.pl{ep}", headers=hdrs, params={"limit":1}, timeout=10)
    print(f"{ep}: HTTP {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  keys: {list(data.keys())[:5]}")
    elif r.status_code != 404:
        print(f"  {r.text[:150]}")
