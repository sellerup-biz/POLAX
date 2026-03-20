"""
Загружает billing за январь 2026 по всем 4 странам отдельно.
Сохраняет в billing_all_feb.json для анализа.
Эталон (из скриншотов):
  PL: Obowiązkowe=-4727.83 Dostawa=-1793.56 Reklama=-8968.75 Abonament=-199.00 Rabaty=+46.54
  CZ: Obowiązkowe=-253.44  Dostawa=-454.98
  HU: Obowiązkowe=-662.79  Dostawa=-2570.00
  SK: Obowiązkowe=-11.66   Dostawa=-9.26
"""
import requests, json, os, base64
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN","")
GH_REPO      = "sellerup-biz/POLAX"

DATE_FROM = "2026-02-01T00:00:00+01:00"
DATE_TO   = "2026-02-28T23:59:59+01:00"

MARKETPLACES = ["allegro-pl","allegro-cz","allegro-hu","allegro-sk"]

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
        print("  Токен сохранён")
    except Exception as e: print(f"  Ошибка сохранения токена: {e}")

def get_token():
    r = requests.post("https://allegro.pl/auth/oauth/token",
                      auth=(os.environ["CLIENT_ID_POLAX"], os.environ["CLIENT_SECRET_POLAX"]),
                      data={"grant_type":"refresh_token",
                            "refresh_token":os.environ["REFRESH_TOKEN_POLAX"],
                            "redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d: print(f"ОШИБКА: {d}"); exit(1)
    # Диагностический скрипт — токен НЕ ротируем
    return d["access_token"]

def hdrs(t):
    return {"Authorization":f"Bearer {t}","Accept":"application/vnd.allegro.public.v1+json"}

def fetch_billing(token, marketplace):
    entries = []
    offset  = 0
    while True:
        r = requests.get("https://api.allegro.pl/billing/billing-entries",
                         headers=hdrs(token),
                         params={"occurredAt.gte":DATE_FROM,"occurredAt.lte":DATE_TO,
                                 "marketplaceId":marketplace,"limit":100,"offset":offset})
        batch = r.json().get("billingEntries",[])
        entries.extend(batch)
        if len(batch) < 100: break
        offset += 100
    return entries

token = get_token()
print(f"Токен: OK\nПериод: {DATE_FROM} → {DATE_TO}\n")

result = {}
for mkt in MARKETPLACES:
    entries = fetch_billing(token, mkt)
    # Статистика по типам
    by_type = {}
    for e in entries:
        tid  = e["type"]["id"]
        tnam = e["type"]["name"]
        amt  = float(e["value"]["amount"])
        cur  = e["value"]["currency"]
        if tid not in by_type:
            by_type[tid] = {"name":tnam,"neg":0.0,"pos":0.0,"cur":cur,"cnt":0}
        by_type[tid]["cnt"] += 1
        if amt < 0: by_type[tid]["neg"] += abs(amt)
        else:       by_type[tid]["pos"] += amt

    result[mkt] = {"entries":entries,"by_type":by_type}
    print(f"\n{'='*60}")
    print(f"  {mkt} — {len(entries)} записей")
    print(f"  {'ID':<6} {'Название':<45} {'РАСХОД':>12} {'ВОЗВРАТ':>10} {'Валюта':>6}")
    print(f"  {'─'*6} {'─'*45} {'─'*12} {'─'*10} {'─'*6}")
    for tid, v in sorted(by_type.items(), key=lambda x:-x[1]["neg"]):
        neg = f"-{v['neg']:.2f}" if v["neg"] else "—"
        pos = f"+{v['pos']:.2f}" if v["pos"] else "—"
        print(f"  [{tid:<4}] {v['name']:<45} {neg:>12} {pos:>10} {v['cur']:>6}")

# Сохраняем сырые данные
with open("billing_all_feb.json","w") as f:
    # Сохраняем только by_type для компактности
    summary = {mkt: result[mkt]["by_type"] for mkt in MARKETPLACES}
    json.dump(summary, f, indent=2, ensure_ascii=False)
print(f"\n\nСохранено в billing_all_feb.json")
print(f"Записей: PL={len(result['allegro-pl']['entries'])} CZ={len(result['allegro-cz']['entries'])} HU={len(result['allegro-hu']['entries'])} SK={len(result['allegro-sk']['entries'])}")

# ── ДЕТАЛИ PS1 и RET записей ──────────────────────────────────
print(f"\n{'='*60}")
print("ДЕТАЛИ PS1 и RET записей за февраль (PL):")
print(f"{'='*60}")
offset = 0
while True:
    entries = requests.get("https://api.allegro.pl/billing/billing-entries",
                           headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.allegro.public.v1+json"},
                           params={"occurredAt.gte":"2026-02-01T00:00:00+01:00",
                                   "occurredAt.lte":"2026-02-28T23:59:59+01:00",
                                   "marketplaceId":"allegro-pl","limit":100,"offset":offset}
                           ).json().get("billingEntries",[])
    for e in entries:
        tid = e["type"]["id"].strip()
        if tid in ["PS1","RET","REF"]:
            amt  = e["value"]["amount"]
            cur  = e["value"]["currency"]
            date = e.get("occurredAt","")[:10]
            offer = (e.get("offer") or {}).get("id","—")
            order = (e.get("order") or {}).get("id","—")
            print(f"  [{tid}] {date}  {amt:>10} {cur}  offer:{offer}  order:{order}")
    if len(entries) < 100: break
    offset += 100
