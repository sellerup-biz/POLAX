"""
Обменивает Allegro authorization_code на refresh_token
и сохраняет его в GitHub Secrets.
"""
import requests, os, base64
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ["GH_TOKEN"]
GH_REPO      = "sellerup-biz/POLAX"
SHOP         = os.environ["SHOP"]   # MLOT / POLAX / SILA
CODE         = os.environ["CODE"]

CLIENT_ID     = os.environ[f"CLIENT_ID_{SHOP}"]
CLIENT_SECRET = os.environ[f"CLIENT_SECRET_{SHOP}"]
SECRET_NAME   = f"REFRESH_TOKEN_{SHOP}"

SHOP_NAMES = {"MLOT": "Mlot_i_Klucz", "POLAX": "PolaxEuroGroup", "SILA": "Sila_Narzedzi"}
print(f"Магазин: {SHOP_NAMES.get(SHOP, SHOP)}")

# 1. Обмениваем authorization_code → access_token + refresh_token
print("Обмениваем code → tokens...")
r = requests.post(
    "https://allegro.pl/auth/oauth/token",
    auth=(CLIENT_ID, CLIENT_SECRET),
    data={
        "grant_type":   "authorization_code",
        "code":         CODE,
        "redirect_uri": REDIRECT_URI,
    },
    timeout=30
)
data = r.json()
if "refresh_token" not in data:
    print(f"ОШИБКА Allegro: {data}")
    exit(1)

refresh_token = data["refresh_token"]
print("Получен access_token + refresh_token")

# 2. Сохраняем refresh_token в GitHub Secrets
print(f"Сохраняем {SECRET_NAME} в GitHub Secrets...")
r2 = requests.get(
    f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
    headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
)
pubkey = r2.json()

pk  = public.PublicKey(pubkey["key"].encode(), encoding.Base64Encoder())
enc = base64.b64encode(public.SealedBox(pk).encrypt(refresh_token.encode())).decode()

r3 = requests.put(
    f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{SECRET_NAME}",
    headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
    json={"encrypted_value": enc, "key_id": pubkey["key_id"]}
)

if r3.status_code in (201, 204):
    print(f"✅ {SECRET_NAME} успешно сохранён!")
else:
    print(f"ОШИБКА сохранения: HTTP {r3.status_code} — {r3.text[:200]}")
    exit(1)

print(f"\n🎉 Авторизация {SHOP_NAMES.get(SHOP, SHOP)} завершена!")
