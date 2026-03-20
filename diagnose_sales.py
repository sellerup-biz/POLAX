"""
Диагностика продаж — ищем где теряются транзакции.
Сравниваем разные периоды запросов для PolaxEuroGroup.
Эталон Allegro UI: 33998.72 PLN только по Польше за январь.
"""
import requests, os
from datetime import datetime, timedelta

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
CLIENT_ID     = os.environ["CLIENT_ID_POLAX"]
CLIENT_SECRET = os.environ["CLIENT_SECRET_POLAX"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN_POLAX"]

def get_token():
    r = requests.post("https://allegro.pl/auth/oauth/token",
                      auth=(CLIENT_ID, CLIENT_SECRET),
                      data={"grant_type":"refresh_token","refresh_token":REFRESH_TOKEN,"redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d: print(f"ОШИБКА: {d}"); exit(1)
    return d["access_token"]

def hdrs(t):
    return {"Authorization": f"Bearer {t}", "Accept": "application/vnd.allegro.public.v1+json"}

def get_income(token, df, dt, marketplace=None):
    """Суммирует все INCOME операции за период"""
    total = 0.0
    by_currency = {}
    count = 0
    offset = 0
    params = {"group":"INCOME","occurredAt.gte":df,"occurredAt.lte":dt,"limit":100,"offset":offset}
    if marketplace:
        params["marketplaceId"] = marketplace
    while True:
        params["offset"] = offset
        r = requests.get("https://api.allegro.pl/payments/payment-operations",
                         headers=hdrs(token), params=params)
        ops = r.json().get("paymentOperations", [])
        for op in ops:
            try:
                amt = float(op["value"]["amount"])
                cur = op["value"]["currency"]
                by_currency[cur] = by_currency.get(cur, 0) + amt
                total += amt  # без конвертации — только PLN сначала
                count += 1
            except: pass
        if len(ops) < 100: break
        offset += 100
    return total, by_currency, count

token = get_token()
print("Токен: OK\n")
print(f"ЭТАЛОН Allegro UI: 33998.72 PLN (только PL, период 31дек→30янв)")
print(f"{'='*70}")

# Тестируем разные периоды
periods = [
    ("Allegro период: 31дек→30янв UTC+1", "2025-12-31T00:00:00+01:00", "2026-01-30T23:59:59+01:00"),
    ("Январь UTC+1:   01янв→31янв",        "2026-01-01T00:00:00+01:00", "2026-01-31T23:59:59+01:00"),
    ("Январь UTC:     01янв→31янв",        "2026-01-01T00:00:00Z",      "2026-01-31T23:59:59Z"),
    ("Шире:           31дек→31янв UTC+1",  "2025-12-31T00:00:00+01:00", "2026-01-31T23:59:59+01:00"),
]

for label, df, dt in periods:
    # Без фильтра marketplace
    total_all, by_cur, cnt = get_income(token, df, dt)
    # Только PL
    total_pl, by_cur_pl, cnt_pl = get_income(token, df, dt, "allegro-pl")
    
    print(f"\n{label}")
    print(f"  Без фильтра: {total_all:.2f} PLN ({cnt} операций) | валюты: {by_cur}")
    print(f"  Только PL:   {total_pl:.2f} PLN ({cnt_pl} операций)")
    diff = total_pl - 33998.72
    print(f"  Разница с эталоном PL: {diff:+.2f}")

# Дополнительно — проверяем 31 декабря отдельно
print(f"\n{'='*70}")
print("31 декабря 2025 (отдельно):")
t31, c31, n31 = get_income(token, "2025-12-31T00:00:00+01:00", "2025-12-31T23:59:59+01:00")
print(f"  Всего: {t31:.2f} PLN ({n31} операций) | {c31}")

# 1 января
print("1 января 2026:")
t1, c1, n1 = get_income(token, "2026-01-01T00:00:00+01:00", "2026-01-01T23:59:59+01:00")
print(f"  Всего: {t1:.2f} PLN ({n1} операций) | {c1}")

# Также проверяем тип операций — может есть не CONTRIBUTION
print(f"\n{'='*70}")
print("Типы операций за январь (без фильтра group=INCOME):")
offset = 0
types_count = {}
types_total = {}
while True:
    r = requests.get("https://api.allegro.pl/payments/payment-operations",
                     headers=hdrs(token),
                     params={"occurredAt.gte":"2026-01-01T00:00:00+01:00",
                             "occurredAt.lte":"2026-01-31T23:59:59+01:00",
                             "limit":100,"offset":offset})
    ops = r.json().get("paymentOperations", [])
    for op in ops:
        t = op.get("type","?")
        g = op.get("group","?")
        key = f"{g}/{t}"
        types_count[key] = types_count.get(key, 0) + 1
        try: types_total[key] = types_total.get(key, 0.0) + float(op["value"]["amount"])
        except: pass
    if len(ops) < 100: break
    offset += 100

for key in sorted(types_total, key=lambda x: -abs(types_total[x])):
    print(f"  {key:<30} {types_total[key]:>12.2f} PLN  ({types_count[key]} шт)")
