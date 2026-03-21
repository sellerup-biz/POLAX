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

cid = os.environ.get("CLIENT_ID_POLAX","")
cs  = os.environ.get("CLIENT_SECRET_POLAX","")
rt  = os.environ.get("REFRESH_TOKEN_POLAX","")
token = get_token(cid, cs, rt)
print(f"Token: {'OK' if token else 'FAIL'}")

# Пробуем разные версии заголовков для /ads/campaigns
versions = ["v1","v2","v3","v4"]
for v in versions:
    hdrs = {
        "Authorization": f"Bearer {token}",
        "Accept": f"application/vnd.allegro.public.{v}+json"
    }
    r = requests.get("https://api.allegro.pl/ads/campaigns", headers=hdrs, timeout=10)
    print(f"  /ads/campaigns [{v}]: HTTP {r.status_code} — {r.text[:200]}")

# Также проверим NSP billing entry — есть ли там offer.id
print("\n--- Проверка billing entries с NSP ---")
hdrs = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"}
r = requests.get("https://api.allegro.pl/billing/billing-entries",
    headers=hdrs,
    params={"type.id":"NSP", "limit":5, "occurredAt.gte":"2026-03-01T00:00:00+01:00", "occurredAt.lte":"2026-03-20T23:59:59+01:00"},
    timeout=20)
print(f"NSP billing: HTTP {r.status_code}")
if r.status_code == 200:
    data = r.json()
    entries = data.get("billingEntries", [])
    print(f"Найдено {len(entries)} NSP записей")
    for e in entries[:3]:
        print(f"  id={e.get('id')} type={e.get('type',{}).get('id')} offer={e.get('offer')} amount={e.get('amount',{}).get('amount')}")
