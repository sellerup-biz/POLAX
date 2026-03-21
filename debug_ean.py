"""
Отладка EAN: пробуем новый эндпоинт GET /sale/product-offers/{id}
и также смотрим полный ответ GET /sale/offers (список).
"""
import requests, json, os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
OFFER_ID = "18325278148"  # Plandeka 5x6m — sygnatura 70-122, EAN 4823127517116

SHOPS = {
    "Mlot_i_Klucz":  (os.environ.get("CLIENT_ID_MLOT",""),  os.environ.get("CLIENT_SECRET_MLOT",""),  os.environ.get("REFRESH_TOKEN_MLOT","")),
    "PolaxEuroGroup": (os.environ.get("CLIENT_ID_POLAX",""), os.environ.get("CLIENT_SECRET_POLAX",""), os.environ.get("REFRESH_TOKEN_POLAX","")),
    "Sila_Narzedzi":  (os.environ.get("CLIENT_ID_SILA",""),  os.environ.get("CLIENT_SECRET_SILA",""),  os.environ.get("REFRESH_TOKEN_SILA","")),
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
    print(f"\n{'='*60}\nМагазин: {shop_name}")
    token, _ = get_token(cid, cs, rt)
    if not token:
        print("  Токен не получен"); continue
    print("  Токен OK")

    # 1. Пробуем новый эндпоинт: /sale/product-offers/{id}
    r1 = requests.get(f"https://api.allegro.pl/sale/product-offers/{OFFER_ID}",
        headers=hdrs(token), timeout=30)
    print(f"\n  [1] GET /sale/product-offers/{OFFER_ID}: HTTP {r1.status_code}")
    if r1.status_code == 200:
        d1 = r1.json()
        print(f"  Ключи: {list(d1.keys())}")
        print("  === parameters ===")
        for p in d1.get("parameters", []):
            print(f"    name={p.get('name')!r:35} values={p.get('values')}")
        print("  === productSet ===")
        for ps in d1.get("productSet", []):
            prod = ps.get("product") or {}
            print(f"    product.id={prod.get('id')}  name={str(prod.get('name',''))[:50]}")
    else:
        print(f"  Ответ: {r1.text[:300]}")

    # 2. Берём один оффер из списка — смотрим ВСЕ поля
    r2 = requests.get("https://api.allegro.pl/sale/offers",
        headers=hdrs(token),
        params={"publication.status":"ACTIVE","limit":1,"external.id":"70-122"},
        timeout=30)
    print(f"\n  [2] GET /sale/offers?external.id=70-122: HTTP {r2.status_code}")
    if r2.status_code == 200:
        offers = r2.json().get("offers", [])
        if offers:
            print(f"  Ключи оффера: {list(offers[0].keys())}")
            print(f"  parameters: {offers[0].get('parameters')}")
            print(f"  productSet: {offers[0].get('productSet')}")
            print(f"  external:   {offers[0].get('external')}")
            print(f"  id:         {offers[0].get('id')}")
        else:
            print("  Оффер с этим SKU не найден")
    else:
        print(f"  Ответ: {r2.text[:200]}")

    break  # достаточно одного магазина с токеном
