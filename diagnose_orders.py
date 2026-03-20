"""
Диагностика заказов PolaxEuroGroup за январь 2026.
Документация: GET /order/checkout-forms
Параметры даты: lineItems.boughtAt.gte / lineItems.boughtAt.lte
Параметр маркетплейса: marketplace.id
Поле в ответе: marketplace.id, summary.totalToPay, delivery.cost
"""
import requests, json, os, base64
from datetime import datetime
from nacl import encoding, public
from collections import defaultdict

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN","")
GH_REPO      = "sellerup-biz/POLAX"

# UTC формат — без timezone offset
DATE_FROM = "2026-01-01T00:00:00.000Z"
DATE_TO   = "2026-01-31T23:59:59.999Z"

ETALON = {
    "allegro-pl":           33998.72,
    "allegro-business-pl":  None,
    "allegro-cz":           1613.00,
    "allegro-hu":           3790.00,
    "allegro-sk":           93.36,
}

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

def fetch_orders(token):
    """Забирает все заказы с фильтром по дате"""
    orders = []
    offset = 0
    while True:
        params = {
            "lineItems.boughtAt.gte": DATE_FROM,
            "lineItems.boughtAt.lte": DATE_TO,
            "limit": 100,
            "offset": offset,
        }
        r    = requests.get("https://api.allegro.pl/order/checkout-forms",
                            headers=hdrs(token), params=params)
        data = r.json()
        if "checkoutForms" not in data:
            print(f"  ОШИБКА: {data}")
            break
        batch = data.get("checkoutForms", [])
        total = data.get("totalCount", "?")
        orders.extend(batch)
        if offset == 0:
            print(f"  totalCount из API: {total}")
        if len(batch) < 100: break
        offset += 100
        if offset > 10000:
            print("  ⚠ Достигнут лимит offset=10000")
            break
    return orders

token = get_token()
print(f"Токен: OK | {DATE_FROM[:10]} → {DATE_TO[:10]}\n")

# ── 1. Структура первого заказа ───────────────────────────────
print("="*65)
print("1. Структура первого заказа (для отладки)")
print("="*65)
params = {"lineItems.boughtAt.gte": DATE_FROM, "lineItems.boughtAt.lte": DATE_TO, "limit": 1}
r = requests.get("https://api.allegro.pl/order/checkout-forms", headers=hdrs(token), params=params)
data = r.json()
total = data.get("totalCount","?")
print(f"  totalCount (январь): {total}")
if data.get("checkoutForms"):
    o = data["checkoutForms"][0]
    print(f"  marketplace: {o.get('marketplace')}")
    print(f"  status: {o.get('status')}")
    print(f"  summary.totalToPay: {o.get('summary',{}).get('totalToPay')}")
    print(f"  delivery.cost: {o.get('delivery',{}).get('cost')}")
    li = o.get("lineItems",[])
    if li:
        print(f"  lineItems[0].boughtAt: {li[0].get('boughtAt')}")
        print(f"  lineItems[0].price: {li[0].get('price')}")
    print(f"\n  Полный JSON первого заказа:")
    print(json.dumps(o, indent=2, ensure_ascii=False)[:2000])

# ── 2. Все заказы за январь ───────────────────────────────────
print(f"\n{'='*65}")
print("2. Суммы заказов за январь по маркетплейсам")
print("="*65)

all_orders = fetch_orders(token)
print(f"  Загружено: {len(all_orders)} заказов")

# Фильтруем — только READY_FOR_PROCESSING (оплаченные)
# FILLED_IN = форма заполнена но оплата не завершена — не считаем
# BOUGHT = без формы — не считаем
# CANCELLED = отменённые — не считаем
by_status = defaultdict(int)
for o in all_orders:
    by_status[o.get("status","?")] += 1
print(f"\n  Статусы: {dict(by_status)}")

active = [o for o in all_orders if o.get("status") == "READY_FOR_PROCESSING"]
print(f"  Только READY_FOR_PROCESSING: {len(active)}")

# Суммируем по маркетплейсам
by_mkt       = defaultdict(float)
by_mkt_del   = defaultdict(float)
by_mkt_cur   = {}
by_mkt_cnt   = defaultdict(int)
by_mkt_paid  = defaultdict(float)

for o in active:
    mkt = o.get("marketplace",{}).get("id","НЕТ")
    summary  = o.get("summary",{})
    delivery = o.get("delivery",{})
    payment  = o.get("payment",{})
    total    = float(summary.get("totalToPay",{}).get("amount",0))
    paid     = float(payment.get("paidAmount",{}).get("amount",0)) if payment else 0
    cur      = summary.get("totalToPay",{}).get("currency","PLN")
    deli     = float(delivery.get("cost",{}).get("amount",0)) if delivery else 0
    by_mkt[mkt]     += total
    by_mkt_del[mkt] += deli
    by_mkt_cur[mkt]  = cur
    by_mkt_cnt[mkt] += 1
    by_mkt_paid[mkt] += paid

print(f"\n  {'Маркетплейс':<25} {'Кол':>5} {'totalToPay':>12} {'paidAmount':>12} {'Доставка':>10} {'Валюта':>6}")
print(f"  {'─'*25} {'─'*5} {'─'*12} {'─'*12} {'─'*10} {'─'*6}")
for mkt in sorted(by_mkt):
    t = by_mkt[mkt]
    p = by_mkt_paid[mkt]
    d = by_mkt_del[mkt]
    c = by_mkt_cur.get(mkt,"?")
    n = by_mkt_cnt[mkt]
    print(f"  {mkt:<25} {n:>5} {t:>12.2f} {p:>12.2f} {d:>10.2f} {c:>6}")

# ── 3. Сравнение с эталоном ───────────────────────────────────
print(f"\n{'='*65}")
print("3. Сравнение с эталоном Allegro UI")
print("="*65)
print(f"  {'Маркетплейс':<25} {'totalToPay':>12} {'paidAmount':>12} {'ЭТАЛОН':>12}")
print(f"  {'─'*25} {'─'*12} {'─'*12} {'─'*12}")

pl_total = by_mkt.get("allegro-pl",0) + by_mkt.get("allegro-business-pl",0)
pl_paid  = by_mkt_paid.get("allegro-pl",0) + by_mkt_paid.get("allegro-business-pl",0)
print(f"  allegro-pl + business: {pl_total:>9.2f}  {pl_paid:>9.2f}  эталон: 33998.72  diff_total:{pl_total-33998.72:+.2f}  diff_paid:{pl_paid-33998.72:+.2f}")

for mkt in ["allegro-cz","allegro-hu","allegro-sk"]:
    t   = by_mkt.get(mkt,0)
    p   = by_mkt_paid.get(mkt,0)
    ref = ETALON.get(mkt)
    if ref:
        print(f"  {mkt:<25} {t:>12.2f} {p:>12.2f} {ref:>12.2f}  diff:{t-ref:+.2f}")
