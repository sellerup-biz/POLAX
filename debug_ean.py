"""
Отладка: смотрим реальную структуру /sale/offers/{id}
Пробуем все три магазина чтобы найти оффер 18325278148 (plandeka из скриншота).
"""
import requests, json, os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
OFFER_ID = "18325278148"  # Plandeka с EAN 4823127517116

SHOPS = {
    "Mlot_i_Klucz":   (os.environ.get("CLIENT_ID_MLOT",""),  os.environ.get("CLIENT_SECRET_MLOT",""),  os.environ.get("REFRESH_TOKEN_MLOT","")),
    "PolaxEuroGroup":  (os.environ.get("CLIENT_ID_POLAX",""), os.environ.get("CLIENT_SECRET_POLAX",""), os.environ.get("REFRESH_TOKEN_POLAX","")),
    "Sila_Narzedzi":   (os.environ.get("CLIENT_ID_SILA",""),  os.environ.get("CLIENT_SECRET_SILA",""),  os.environ.get("REFRESH_TOKEN_SILA","")),
}

def get_token(cid, cs, rt):
    r = requests.post("https://allegro.pl/auth/oauth/token",
        auth=(cid, cs),
        data={"grant_type":"refresh_token","refresh_token":rt,"redirect_uri":REDIRECT_URI},
        timeout=30)
    d = r.json()
    return d.get("access_token"), d.get("refresh_token","")

def hdrs(t):
    return {"Authorization":f"Bearer {t}","Accept":"application/vnd.allegro.public.v1+json"}

for shop_name, (cid, cs, rt) in SHOPS.items():
    print(f"\n{'='*60}")
    print(f"Магазин: {shop_name}")
    token, _ = get_token(cid, cs, rt)
    if not token:
        print("  Токен не получен"); continue
    print("  Токен OK")

    resp = requests.get(
        f"https://api.allegro.pl/sale/offers/{OFFER_ID}",
        headers=hdrs(token), timeout=30)
    print(f"  Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"  Ответ: {resp.text[:200]}")
        continue

    data = resp.json()
    print(f"  Ключи: {list(data.keys())}")

    print("\n  === parameters ===")
    for p in data.get("parameters", []):
        print(f"    name={p.get('name')!r:35} values={p.get('values')} valuesIds={p.get('valuesIds')}")

    print("\n  === productSet ===")
    for ps in data.get("productSet", []):
        prod = ps.get("product") or {}
        print(f"    product.id={prod.get('id')} name={str(prod.get('name',''))[:50]}")

    print(f"\n  === external ===  {data.get('external')}")
    break  # нашли нужный магазин — дальше не идём
