"""
Диагностика продаж PolaxEuroGroup — январь 2026.
Цель: найти почему наш итог 33421 < Allegro PL 33998.
"""
import requests, os
from datetime import datetime, timedelta

REDIRECT_URI  = "https://sellerup-biz.github.io/POLAX/callback.html"
CLIENT_ID     = os.environ["CLIENT_ID_POLAX"]
CLIENT_SECRET = os.environ["CLIENT_SECRET_POLAX"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN_POLAX"]

_rates = {}
def get_rate(currency, date_str):
    if currency == "PLN": return 1.0
    key = f"{currency}_{date_str}"
    if key in _rates: return _rates[key]
    for delta in range(7):
        d = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            r = requests.get(f"https://api.nbp.pl/api/exchangerates/rates/a/{currency.lower()}/{d}/?format=json", timeout=5)
            if r.status_code == 200:
                rate = float(r.json()["rates"][0]["mid"])
                _rates[key] = rate
                return rate
        except: pass
    return 1.0

def get_token():
    r = requests.post("https://allegro.pl/auth/oauth/token",
                      auth=(CLIENT_ID, CLIENT_SECRET),
                      data={"grant_type":"refresh_token","refresh_token":REFRESH_TOKEN,"redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d: print(f"ОШИБКА: {d}"); exit(1)
    return d["access_token"]

def hdrs(t):
    return {"Authorization": f"Bearer {t}", "Accept": "application/vnd.allegro.public.v1+json"}

def fetch_all(token, df, dt, marketplace=None, group="INCOME"):
    """Забирает все операции, конвертирует в PLN"""
    total_pln = 0.0
    by_currency = {}
    by_mkt      = {}
    by_type     = {}
    count = 0
    offset = 0
    params = {"occurredAt.gte":df,"occurredAt.lte":dt,"limit":100}
    if group:      params["group"]         = group
    if marketplace: params["marketplaceId"] = marketplace
    while True:
        params["offset"] = offset
        ops = requests.get("https://api.allegro.pl/payments/payment-operations",
                           headers=hdrs(token), params=params).json().get("paymentOperations",[])
        for op in ops:
            try:
                amt  = float(op["value"]["amount"])
                cur  = op["value"]["currency"]
                mkt  = op.get("marketplaceId","НЕТ")
                typ  = op.get("type","?")
                grp  = op.get("group","?")
                date = op.get("occurredAt","")[:10]
                rate = get_rate(cur, date if date else "2026-01-15")
                pln  = amt * rate
                total_pln += pln
                by_currency[cur]     = by_currency.get(cur, 0.0)     + amt
                by_mkt[mkt]          = by_mkt.get(mkt, 0.0)          + pln
                by_type[f"{grp}/{typ}"] = by_type.get(f"{grp}/{typ}", 0.0) + pln
                count += 1
            except: pass
        if len(ops) < 100: break
        offset += 100
    return total_pln, by_currency, by_mkt, by_type, count

token = get_token()
print("Токен: OK")
print(f"\nЭТАЛОН Allegro UI (январь, только PL): 33 998.72 PLN")
print(f"{'='*70}")

# 1. Наш текущий период (1-31 января UTC+1)
df1 = "2026-01-01T00:00:00+01:00"
dt1 = "2026-01-31T23:59:59+01:00"
total, by_cur, by_mkt, by_type, cnt = fetch_all(token, df1, dt1)
print(f"\n1. Январь 1-31 UTC+1 | group=INCOME | {cnt} операций | ИТОГО: {total:.2f} PLN")
print(f"   По валютам (оригинал): {by_cur}")
print(f"   По marketplaceId (PLN): {by_mkt}")
print(f"   По типам (PLN): {by_type}")

# 2. Allegro период (31 дек - 30 янв UTC+1)
df2 = "2025-12-31T00:00:00+01:00"
dt2 = "2026-01-30T23:59:59+01:00"
total2, by_cur2, by_mkt2, by_type2, cnt2 = fetch_all(token, df2, dt2)
print(f"\n2. Allegro период 31дек-30янв UTC+1 | {cnt2} операций | ИТОГО: {total2:.2f} PLN")
print(f"   По marketplaceId (PLN): {by_mkt2}")

# 3. Без фильтра group (все операции)
total3, by_cur3, by_mkt3, by_type3, cnt3 = fetch_all(token, df1, dt1, group=None)
print(f"\n3. Январь 1-31 UTC+1 | БЕЗ фильтра group | {cnt3} операций | ИТОГО: {total3:.2f} PLN")
print(f"   По типам (PLN): {by_type3}")

# 4. Только PL — что реально приходит
total4, by_cur4, by_mkt4, by_type4, cnt4 = fetch_all(token, df1, dt1, marketplace="allegro-pl")
print(f"\n4. Январь 1-31 UTC+1 | только allegro-pl | {cnt4} операций | ИТОГО: {total4:.2f} PLN")
diff = total4 - 33998.72
print(f"   Разница с эталоном: {diff:+.2f} PLN")

print(f"\n{'='*70}")
print(f"ВЫВОД:")
print(f"  Наш итого ALL:  {total:.2f} PLN")
print(f"  Наш итого PL:   {total4:.2f} PLN")
print(f"  Эталон PL:      33998.72 PLN")
print(f"  Разница PL:     {total4-33998.72:+.2f} PLN")
