"""
Диагностика billing API Allegro.
Забирает ВСЕ записи за январь 2026 для PolaxEuroGroup,
группирует по type.id + type.name + знак суммы,
выводит итоги — чтобы написать правильный маппинг.
"""
import requests, os, json
from datetime import datetime, timedelta
from collections import defaultdict

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"

CLIENT_ID     = os.environ["CLIENT_ID_POLAX"]
CLIENT_SECRET = os.environ["CLIENT_SECRET_POLAX"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN_POLAX"]

# Январь 2026 (UTC+1)
DATE_FROM = "2026-01-01T00:00:00+01:00"
DATE_TO   = "2026-01-31T23:59:59+01:00"

def save_token(new_rt):
    import base64
    from nacl import encoding, public
    gh_token = os.environ.get("GH_TOKEN","")
    if not gh_token or not new_rt: return
    r = __import__("requests").get(f"https://api.github.com/repos/sellerup-biz/POLAX/actions/secrets/public-key",headers={"Authorization":f"token {gh_token}","Accept":"application/vnd.github+json"})
    key=r.json()
    pk=public.PublicKey(key["key"].encode(),encoding.Base64Encoder())
    enc=base64.b64encode(public.SealedBox(pk).encrypt(new_rt.encode())).decode()
    __import__("requests").put(f"https://api.github.com/repos/sellerup-biz/POLAX/actions/secrets/REFRESH_TOKEN_POLAX",headers={"Authorization":f"token {gh_token}","Accept":"application/vnd.github+json"},json={"encrypted_value":enc,"key_id":key["key_id"]})

def get_token():
    r = requests.post("https://allegro.pl/auth/oauth/token",
                      auth=(CLIENT_ID, CLIENT_SECRET),
                      data={"grant_type":"refresh_token","refresh_token":REFRESH_TOKEN,"redirect_uri":REDIRECT_URI})
    return r.json()["access_token"]

def hdrs(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"}

token = get_token()
print("Токен: OK")

# Забираем ВСЕ billing записи за январь
all_entries = []
offset = 0
while True:
    r = requests.get("https://api.allegro.pl/billing/billing-entries",
                     headers=hdrs(token),
                     params={"occurredAt.gte": DATE_FROM,
                             "occurredAt.lte": DATE_TO,
                             "limit": 100, "offset": offset})
    data = r.json()
    entries = data.get("billingEntries", [])
    all_entries.extend(entries)
    print(f"  Загружено: {len(all_entries)} записей (offset={offset})")
    if len(entries) < 100:
        break
    offset += 100

print(f"\nВсего записей: {len(all_entries)}")

# Сохраняем сырые данные для анализа
with open("billing_raw_jan.json", "w") as f:
    json.dump(all_entries, f, indent=2, ensure_ascii=False)

# Группируем: type.id | type.name | знак | итого
groups = defaultdict(lambda: {"name": "", "positive": 0.0, "negative": 0.0, "count_pos": 0, "count_neg": 0})

for e in all_entries:
    tid   = e["type"]["id"]
    tname = e["type"]["name"]
    amt   = float(e["value"]["amount"])
    groups[tid]["name"] = tname
    if amt >= 0:
        groups[tid]["positive"] += amt
        groups[tid]["count_pos"] += 1
    else:
        groups[tid]["negative"] += abs(amt)
        groups[tid]["count_neg"] += 1

# Выводим таблицу
print(f"\n{'='*100}")
print(f"  ВСЕ ТИПЫ BILLING — PolaxEuroGroup — Январь 2026")
print(f"{'='*100}")
print(f"  {'ID':<6} {'Название':50} {'РАСХОД (-)':>14} {'ВОЗВРАТ (+)':>14} {'Записей':>8}")
print(f"  {'─'*6} {'─'*50} {'─'*14} {'─'*14} {'─'*8}")

total_neg = 0.0
total_pos = 0.0
for tid, v in sorted(groups.items(), key=lambda x: -x[1]["negative"]):
    n   = v["negative"]
    p   = v["positive"]
    cnt = v["count_neg"] + v["count_pos"]
    total_neg += n
    total_pos += p
    neg_str = f"-{n:.2f}" if n > 0 else "—"
    pos_str = f"+{p:.2f}" if p > 0 else "—"
    print(f"  [{tid:<4}] {v['name']:50} {neg_str:>14} {pos_str:>14} {cnt:>8}")

print(f"  {'─'*6} {'─'*50} {'─'*14} {'─'*14} {'─'*8}")
print(f"  {'ИТОГО':56} -{total_neg:>13.2f} +{total_pos:>13.2f}")

# Allegro показывает в UI:
ALLEGRO_UI = {
    "Obowiązkowe":      -4727.83,
    "Dostawa":          -1793.56,
    "Reklama":          -8968.75,
    "Abonament":        -199.00,
    "Rabaty od Allegro": +46.54,
    "ИТОГО расходы":    -15642.60,
}
print(f"\n{'─'*50}")
print("  ЭТАЛОН Allegro UI (Январь 2026, только PL):")
for k, v in ALLEGRO_UI.items():
    print(f"    {k:30} {v:>10.2f} PLN")

print(f"\nСырые данные сохранены в billing_raw_jan.json")
