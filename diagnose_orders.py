"""
Проверяем сумму заказов за январь через orders API.
Если совпадает с 33998.72 — значит Allegro UI считает по заказам.
"""
import requests, json, os, base64
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN","")
GH_REPO      = "sellerup-biz/POLAX"

DATE_FROM = "2026-01-01T00:00:00+01:00"
DATE_TO   = "2026-01-31T23:59:59+01:00"

ETALON_PL  = 33998.72
ETALON_CZ  = 1613.00
ETALON_HU  = 3790.00
ETALON_SK  = 93.36

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
    except Exception as e: print(f"  Ошибка: {e}")

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

def fetch_orders(token, marketplace=None):
    """Забирает все заказы за период"""
    orders = []
    offset = 0
    while True:
        params = {
            "lineItems.boughtAt.gte": DATE_FROM,
            "lineItems.boughtAt.lte": DATE_TO,
            "limit": 100,
            "offset": offset,
            "status": "READY_FOR_PROCESSING,PROCESSING,SENT,DELIVERED,CANCELLED",
        }
        if marketplace:
            params["marketplaceId"] = marketplace
        r = requests.get("https://api.allegro.pl/order/checkout-forms",
                         headers=hdrs(token), params=params)
        data = r.json()
        batch = data.get("checkoutForms", [])
        orders.extend(batch)
        if len(batch) < 100: break
        offset += 100
    return orders

token = get_token()
print(f"Токен: OK | {DATE_FROM[:10]} → {DATE_TO[:10]}\n")

# ── 1. Все заказы без фильтра ─────────────────────────────────
print("="*65)
print("1. Все заказы за январь (без фильтра marketplace)")
print("="*65)
all_orders = fetch_orders(token)
print(f"   Заказов: {len(all_orders)}")

# Суммируем по marketplace и валюте
from collections import defaultdict
by_mkt = defaultdict(float)
by_mkt_delivery = defaultdict(float)
by_mkt_items = defaultdict(float)
by_mkt_cur = {}
status_counts = defaultdict(int)

for o in all_orders:
    mkt = o.get("marketplaceId", "НЕТ")
    status = o.get("status","?")
    status_counts[status] += 1
    # Итого по заказу
    summary = o.get("summary", {})
    total_amt   = float(summary.get("totalToPay",{}).get("amount", 0))
    total_cur   = summary.get("totalToPay",{}).get("currency","PLN")
    # Доставка
    delivery    = o.get("delivery", {})
    del_amt     = float(delivery.get("cost",{}).get("amount", 0) if delivery else 0)
    # Товары
    items_total = total_amt - del_amt
    by_mkt[mkt]          += total_amt
    by_mkt_delivery[mkt] += del_amt
    by_mkt_items[mkt]    += items_total
    by_mkt_cur[mkt]       = total_cur

print(f"\n   Статусы заказов: {dict(status_counts)}")
print(f"\n   {'Маркетплейс':<25} {'Итого заказов':>15} {'в т.ч. доставка':>17} {'только товар':>14} {'Валюта':>6}")
print(f"   {'─'*25} {'─'*15} {'─'*17} {'─'*14} {'─'*6}")
for mkt in sorted(by_mkt):
    print(f"   {mkt:<25} {by_mkt[mkt]:>15.2f} {by_mkt_delivery[mkt]:>17.2f} {by_mkt_items[mkt]:>14.2f} {by_mkt_cur.get(mkt,'?'):>6}")

# ── 2. Только НЕОТМЕНЁННЫЕ заказы ─────────────────────────────
print(f"\n{'='*65}")
print("2. Только НЕ отменённые заказы (без CANCELLED)")
print("="*65)
active_orders = [o for o in all_orders if o.get("status") != "CANCELLED"]
print(f"   Заказов: {len(active_orders)}")

by_mkt2 = defaultdict(float)
by_mkt2_del = defaultdict(float)
for o in active_orders:
    mkt = o.get("marketplaceId","НЕТ")
    summary  = o.get("summary",{})
    delivery = o.get("delivery",{})
    total    = float(summary.get("totalToPay",{}).get("amount",0))
    deli     = float(delivery.get("cost",{}).get("amount",0) if delivery else 0)
    by_mkt2[mkt]     += total
    by_mkt2_del[mkt] += deli

print(f"\n   {'Маркетплейс':<25} {'Итого':>12} {'Доставка':>10} {'Товар':>12} {'Эталон UI':>12} {'Разница':>10}")
print(f"   {'─'*25} {'─'*12} {'─'*10} {'─'*12} {'─'*12} {'─'*10}")

ETALON = {"allegro-pl":33998.72,"allegro-cz":1613.00,"allegro-hu":3790.00,"allegro-sk":93.36}
pl_total = by_mkt2.get("allegro-pl",0) + by_mkt2.get("allegro-business-pl",0)
pl_del   = by_mkt2_del.get("allegro-pl",0) + by_mkt2_del.get("allegro-business-pl",0)

for mkt in ["allegro-pl","allegro-business-pl","allegro-cz","allegro-hu","allegro-sk"]:
    t = by_mkt2.get(mkt,0)
    d = by_mkt2_del.get(mkt,0)
    ref = ETALON.get(mkt)
    if ref:
        diff = t - ref
        ok = "✅" if abs(diff) < 1 else "❌"
        print(f"   {mkt:<25} {t:>12.2f} {d:>10.2f} {t-d:>12.2f} {ref:>12.2f} {diff:>+10.2f} {ok}")
    else:
        print(f"   {mkt:<25} {t:>12.2f} {d:>10.2f} {t-d:>12.2f} {'—':>12}")

print(f"\n   PL+business итого: {pl_total:.2f}")
print(f"   Эталон UI:         33998.72")
print(f"   Разница:           {pl_total-33998.72:+.2f}")
