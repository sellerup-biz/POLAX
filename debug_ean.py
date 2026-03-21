"""
Отладка: смотрим реальную структуру /sale/offers/{id}
чтобы понять где хранится EAN в ответе API.
"""
import requests, json, os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"

def get_token(cid, cs, rt):
    r = requests.post("https://allegro.pl/auth/oauth/token",
        auth=(cid, cs),
        data={"grant_type":"refresh_token","refresh_token":rt,"redirect_uri":REDIRECT_URI},
        timeout=30)
    d = r.json()
    if "access_token" not in d:
        print(f"ОШИБКА токена: {d}"); exit(1)
    return d["access_token"]

def hdrs(t):
    return {"Authorization":f"Bearer {t}","Accept":"application/vnd.allegro.public.v1+json"}

token = get_token(
    os.environ["CLIENT_ID_POLAX"],
    os.environ["CLIENT_SECRET_POLAX"],
    os.environ["REFRESH_TOKEN_POLAX"])
print("Токен OK")

# Берём оффер 18325278148 (plandeka с EAN 4823127517116 из скриншота)
OFFER_ID = "18325278148"

resp = requests.get(
    f"https://api.allegro.pl/sale/offers/{OFFER_ID}",
    headers=hdrs(token), timeout=30)
print(f"Status: {resp.status_code}")
data = resp.json()

# Выводим только нужные поля
print("\n=== parameters ===")
for p in data.get("parameters", []):
    print(f"  name={p.get('name')!r:30} values={p.get('values')} valuesIds={p.get('valuesIds')}")

print("\n=== productSet ===")
for ps in data.get("productSet", []):
    prod = ps.get("product") or {}
    print(f"  product.id={prod.get('id')} product.name={str(prod.get('name',''))[:50]}")

print("\n=== external ===")
print(f"  {data.get('external')}")

print("\n=== Все ключи верхнего уровня ===")
print(list(data.keys()))
