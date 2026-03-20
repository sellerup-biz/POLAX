"""
Диагностика billing за апрель 2025 — ищем type.id для Kampanie i programy
"""
import requests, os, base64, json
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN","")
GH_REPO      = "sellerup-biz/POLAX"

DATE_FROM = "2025-04-01T00:00:00+02:00"
DATE_TO   = "2025-04-30T23:59:59+02:00"

def save_token(new_rt):
    if not new_rt or not GH_TOKEN: return
    try:
        r   = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
                           headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"})
        key = r.json()
        pk  = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
        enc = base64.b64encode(public.SealedBox(pk).encrypt(new_rt.encode())).decode()
        requests.put(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/REFRESH_TOKEN_POLAX",
                     headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"},
                     json={"encrypted_value":enc,"key_id":key["key_id"]})
    except: pass

def get_token():
    r = requests.post("https://allegro.pl/auth/oauth/token",
                      auth=(os.environ["CLIENT_ID_POLAX"], os.environ["CLIENT_SECRET_POLAX"]),
                      data={"grant_type":"refresh_token",
                            "refresh_token":os.environ["REFRESH_TOKEN_POLAX"],
                            "redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d: print(f"ОШИБКА: {d}"); exit(1)
    save_token(d.get("refresh_token",""))
    return d["access_token"]

def hdrs(t):
    return {"Authorization":f"Bearer {t}","Accept":"application/vnd.allegro.public.v1+json"}

token = get_token()
print(f"Токен: OK | allegro-pl | {DATE_FROM[:10]} → {DATE_TO[:10]}\n")

# Забираем все записи и ищем неизвестные type.id
entries = []
offset = 0
while True:
    batch = requests.get("https://api.allegro.pl/billing/billing-entries",
                         headers=hdrs(token),
                         params={"occurredAt.gte":DATE_FROM,"occurredAt.lte":DATE_TO,
                                 "limit":100,"offset":offset}
                         ).json().get("billingEntries",[])
    entries.extend(batch)
    if len(batch) < 100: break
    offset += 100

print(f"Всего записей: {len(entries)}\n")

# Группируем все type.id
from collections import defaultdict
by_type = defaultdict(lambda:{"name":"","neg":0.0,"pos":0.0,"cnt":0})
for e in entries:
    tid  = e["type"]["id"].strip()
    name = e["type"]["name"]
    amt  = float(e["value"]["amount"])
    by_type[tid]["name"] = name
    by_type[tid]["cnt"] += 1
    if amt < 0: by_type[tid]["neg"] += abs(amt)
    else:       by_type[tid]["pos"] += amt

KNOWN = {"SUC","SUJ","LDS","HUN","REF","HB4","HB1","HB8","HB9","DPB","DXP","HXO",
         "HLB","ORB","DHR","DAP","DKP","DPP","GLS","UPS","UPD","DTR","DPA","ITR",
         "HLA","NSP","DPG","WYR","POD","BOL","EMF","CPC","SB2","ABN","RET","PS1","PAD"}

print(f"{'ID':<6} {'Название':<55} {'РАСХОД':>10} {'ВОЗВРАТ':>10} {'KNOWN':>6}")
print(f"{'─'*6} {'─'*55} {'─'*10} {'─'*10} {'─'*6}")
for tid, v in sorted(by_type.items(), key=lambda x:-x[1]["neg"]):
    known = "✅" if tid in KNOWN else "❌ NEW"
    neg = f"-{v['neg']:.2f}" if v["neg"] else "—"
    pos = f"+{v['pos']:.2f}" if v["pos"] else "—"
    print(f"[{tid:<4}] {v['name']:<55} {neg:>10} {pos:>10}  {known}")
