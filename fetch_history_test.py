import requests, json, os, base64
from datetime import datetime, timedelta, timezone
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO  = "sellerup-biz/POLAX"
MARKETPLACES = {"allegro-pl": "PLN", "allegro-cz": "CZK", "allegro-hu": "HUF", "allegro-sk": "EUR"}

# ── ТЕСТ: только PolaxEuroGroup, только Январь и Февраль 2026 ──
TEST_SHOP = "PolaxEuroGroup"
TEST_DATES = []
for month in [1, 2]:
    days_in = 31 if month == 1 else 28
    for day in range(1, days_in + 1):
        TEST_DATES.append(f"2026-{month:02d}-{day:02d}")

SHOPS = {}
if os.environ.get("CLIENT_ID_POLAX") and os.environ.get("REFRESH_TOKEN_POLAX"):
    SHOPS[TEST_SHOP] = {
        "client_id": os.environ["CLIENT_ID_POLAX"],
        "client_secret": os.environ["CLIENT_SECRET_POLAX"],
        "refresh_token": os.environ["REFRESH_TOKEN_POLAX"],
        "secret_name": "REFRESH_TOKEN_POLAX"
    }

# Глобальный сбор неизвестных типов за весь период
UNKNOWN_TYPES_LOG = {}  # {type_id: {"name": ..., "total": ...}}
POSITIVE_TYPES_LOG = {} # положительные суммы не в discount

def cat_by_name(name):
    n = name.lower()
    if any(x in n for x in ["prowizja","obowiązkow","opłata transakcyjna",
                              "lokalna dopłata","dopłata od sprzedaży detalicznej"]): return "commission"
    if any(x in n for x in ["dostawa","wysyłka","kurier","paczka","inpost","dpd","gls","ups",
                              "przesyłka","odbiór","orlen","poczta","allegro one","one fulfillment",
                              "fulfillment","shipping","delivery","logistyk"]): return "delivery"
    if any(x in n for x in ["reklama","kampania","cpc","ads","promowanie","wyróżnienie","pogrubienie",
                              "podświetlenie","strona działu","pakiet promo","brand zone"]): return "ads"
    if any(x in n for x in ["abonament","smart"]): return "subscription"
    # Все zwroty (возвраты) и rabaty — это положительные суммы, снижающие расходы
    if any(x in n for x in ["rabat","zwrot","korekta"]): return "discount"
    return "other"

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

def get_gh_pk():
    r = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
                     headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"})
    return r.json()

def update_gh_secret(name, val, key_id, key_val):
    pk = public.PublicKey(key_val.encode(), encoding.Base64Encoder())
    enc = base64.b64encode(public.SealedBox(pk).encrypt(val.encode())).decode()
    r = requests.put(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{name}",
                     headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
                     json={"encrypted_value": enc, "key_id": key_id})
    return r.status_code in (201, 204)

def get_token(cid, cs, rt):
    r = requests.post("https://allegro.pl/auth/oauth/token", auth=(cid, cs),
                      data={"grant_type": "refresh_token", "refresh_token": rt, "redirect_uri": REDIRECT_URI})
    d = r.json()
    if "access_token" not in d: return None, None
    return d["access_token"], d.get("refresh_token", rt)

def hdrs(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"}

def get_tz(month): return 2 if 3 <= month <= 10 else 1

def get_sales_for_day(token, date_key):
    month = int(date_key[5:7])
    tz = get_tz(month)
    df = date_key + f"T00:00:00+0{tz}:00"
    dt = date_key + f"T23:59:59+0{tz}:00"

    # ИТОГО без фильтра marketplaceId
    total_pln = 0.0
    offset = 0
    while True:
        r = requests.get("https://api.allegro.pl/payments/payment-operations", headers=hdrs(token),
                         params={"group": "INCOME", "occurredAt.gte": df, "occurredAt.lte": dt,
                                 "limit": 100, "offset": offset})
        ops = r.json().get("paymentOperations", [])
        for op in ops:
            try: total_pln += float(op["value"]["amount"]) * get_rate(op["value"]["currency"], date_key)
            except: pass
        if len(ops) < 100: break
        offset += 100

    # Разбивка по странам
    countries = {k: 0.0 for k in MARKETPLACES}
    for mkt in MARKETPLACES:
        offset = 0
        while True:
            r = requests.get("https://api.allegro.pl/payments/payment-operations", headers=hdrs(token),
                             params={"group": "INCOME", "occurredAt.gte": df, "occurredAt.lte": dt,
                                     "marketplaceId": mkt, "limit": 100, "offset": offset})
            ops = r.json().get("paymentOperations", [])
            for op in ops:
                try: countries[mkt] += float(op["value"]["amount"]) * get_rate(op["value"]["currency"], date_key)
                except: pass
            if len(ops) < 100: break
            offset += 100
        countries[mkt] = round(countries[mkt], 2)

    return countries, round(total_pln, 2)

def get_costs_for_day(token, date_key):
    month = int(date_key[5:7])
    tz = get_tz(month)
    df = date_key + f"T00:00:00+0{tz}:00"
    dt = date_key + f"T23:59:59+0{tz}:00"
    costs = {"commission": 0.0, "delivery": 0.0, "ads": 0.0, "subscription": 0.0, "discount": 0.0, "other": 0.0}
    unknown = {}
    offset = 0
    while True:
        r = requests.get("https://api.allegro.pl/billing/billing-entries", headers=hdrs(token),
                         params={"occurredAt.gte": df, "occurredAt.lte": dt, "limit": 100, "offset": offset})
        entries = r.json().get("billingEntries", [])
        for e in entries:
            try:
                amount    = float(e["value"]["amount"])
                type_name = e["type"]["name"]
                type_id   = e["type"]["id"]
                cat       = cat_by_name(type_name)

                if amount < 0:
                    # Расход — добавляем в соответствующую категорию
                    if cat == "discount":
                        # Отрицательный discount = увеличение скидки (редко, но может быть)
                        costs["discount"] += abs(amount)
                    else:
                        costs[cat] += abs(amount)
                    if cat == "other":
                        unknown[type_id] = type_name
                        if type_id not in UNKNOWN_TYPES_LOG:
                            UNKNOWN_TYPES_LOG[type_id] = {"name": type_name, "total": 0.0}
                        UNKNOWN_TYPES_LOG[type_id]["total"] += abs(amount)

                elif amount > 0:
                    # Положительная сумма = возврат/скидка от Allegro
                    # "Zwroty" под prowizja = возврат комиссии → уменьшает commission
                    # "Rabaty od Allegro" = скидка → discount
                    if cat == "commission":
                        # Zwroty prowizji — вычитаем из комиссии
                        costs["commission"] -= amount
                        if costs["commission"] < 0: costs["commission"] = 0
                    elif cat == "discount":
                        costs["discount"] += amount
                    else:
                        # Логируем неизвестные положительные типы
                        if type_id not in POSITIVE_TYPES_LOG:
                            POSITIVE_TYPES_LOG[type_id] = {"name": type_name, "total": 0.0}
                        POSITIVE_TYPES_LOG[type_id]["total"] += amount

            except: pass
        if len(entries) < 100: break
        offset += 100
    if unknown:
        print(f"    ⚠ OTHER: {unknown}")
    return {k: round(v, 2) for k, v in costs.items()}

# ── ОСНОВНОЙ ЦИКЛ ─────────────────────────────────────────────
print(f"ТЕСТ: {TEST_SHOP} | Январь + Февраль 2026 | {len(TEST_DATES)} дней")

gh_key = get_gh_pk()
gh_key_id, gh_key_val = gh_key.get("key_id"), gh_key.get("key")

tokens = {}
for shop, creds in SHOPS.items():
    t, nr = get_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if t:
        tokens[shop] = t
        if nr and gh_key_id and gh_key_val:
            ok = update_gh_secret(creds["secret_name"], nr, gh_key_id, gh_key_val)
            print(f"  Токен {shop}: {'OK' if ok else 'ERR'}")
    else:
        print(f"  ОШИБКА токена {shop}")

# Структура: все дни + все магазины (остальные будут нулями)
ALL_SHOPS = ["Mlot_i_Klucz", "PolaxEuroGroup", "Sila_Narzedzi"]
days_data = {date: {"date": date, "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0,
                    "countries": {k: 0 for k in MARKETPLACES},
                    "costs": {"commission": 0, "delivery": 0, "ads": 0, "subscription": 0, "discount": 0, "other": 0}}
             for date in TEST_DATES}

for shop, token in tokens.items():
    print(f"\n=== {shop} ===")
    
    # Месячные аккумуляторы для итогового отчёта
    month_totals = {}
    
    for date_key in TEST_DATES:
        month_key = date_key[:7]
        if month_key not in month_totals:
            month_totals[month_key] = {
                "sales_total": 0.0,
                "countries_local": {"allegro-pl": 0.0, "allegro-cz": 0.0, "allegro-hu": 0.0, "allegro-sk": 0.0},
                "countries_pln":   {"allegro-pl": 0.0, "allegro-cz": 0.0, "allegro-hu": 0.0, "allegro-sk": 0.0},
                "costs": {"commission": 0.0, "delivery": 0.0, "ads": 0.0, "subscription": 0.0, "discount": 0.0, "other": 0.0},
                # расходы по странам в локальной валюте (billing всегда в PLN для PL, но для CZ/HU/SK в локальной)
            }
        
        countries, total = get_sales_for_day(token, date_key)
        costs            = get_costs_for_day(token, date_key)
        
        days_data[date_key][shop] = total
        
        # Аккумулируем продажи по странам в PLN
        for k in countries:
            days_data[date_key]["countries"][k] = round(days_data[date_key]["countries"][k] + countries[k], 2)
            month_totals[month_key]["countries_pln"][k] += countries[k]
        
        month_totals[month_key]["sales_total"] += total
        
        # Аккумулируем продажи по странам в ЛОКАЛЬНОЙ валюте (оригинал до конвертации)
        tz = get_tz(int(date_key[5:7]))
        df = date_key + f"T00:00:00+0{tz}:00"
        dt = date_key + f"T23:59:59+0{tz}:00"
        for mkt, cur in MARKETPLACES.items():
            offset = 0
            while True:
                r = requests.get("https://api.allegro.pl/payments/payment-operations", headers=hdrs(token),
                                 params={"group": "INCOME", "occurredAt.gte": df, "occurredAt.lte": dt,
                                         "marketplaceId": mkt, "limit": 100, "offset": offset})
                ops = r.json().get("paymentOperations", [])
                for op in ops:
                    try: month_totals[month_key]["countries_local"][mkt] += float(op["value"]["amount"])
                    except: pass
                if len(ops) < 100: break
                offset += 100
        
        for k in costs:
            days_data[date_key]["costs"][k] = round(days_data[date_key]["costs"][k] + costs[k], 2)
            month_totals[month_key]["costs"][k] += costs[k]
        
        total_costs = sum(v for k,v in costs.items() if k != "discount")
        if total > 0 or total_costs > 0:
            print(f"  {date_key}: продажи={total:.2f} PLN | расходы={total_costs:.2f} PLN")

days_list = [days_data[d] for d in sorted(days_data)]

# Месяцы
months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
monthly = {}
for day in days_list:
    mk = day["date"][:7]
    dt = datetime.strptime(mk, "%Y-%m")
    label = f"{months_ru[dt.month-1]} {dt.year}"
    if label not in monthly:
        monthly[label] = {"month": label, "_o": mk, "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0,
                          "countries": {k: 0.0 for k in MARKETPLACES},
                          "costs": {"commission": 0.0, "delivery": 0.0, "ads": 0.0, "subscription": 0.0, "discount": 0.0, "other": 0.0}}
    m = monthly[label]
    for s in ALL_SHOPS:
        m[s] = round(m[s] + day.get(s, 0), 2)
    for k in MARKETPLACES:
        m["countries"][k] = round(m["countries"][k] + day.get("countries", {}).get(k, 0), 2)
    for k in ["commission","delivery","ads","subscription","discount","other"]:
        m["costs"][k] = round(m["costs"][k] + day.get("costs", {}).get(k, 0), 2)

months_list = sorted(
    [{k: v for k, v in m.items() if k != "_o"} for m in monthly.values()],
    key=lambda x: monthly[x["month"]]["_o"]
)

result = {"days": days_list, "months": months_list}
with open("data.json", "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

# ── ЭТАЛОН ────────────────────────────────────────────────────
ETALON = {
    "2026-01": {
        "sales_local": {"allegro-pl":(33998.72,"PLN"),"allegro-cz":(1613.00,"CZK"),"allegro-hu":(3790.00,"HUF"),"allegro-sk":(93.36,"EUR")},
        "costs_pln": {
            "commission":   4727.83,
            "delivery":     1793.56,
            "ads":          8968.75,
            "subscription": 199.00,
            "discount":     46.54,
        }
    }
}
COST_NAMES = {"commission":"Obowiązkowe","delivery":"Dostawa","ads":"Reklama i promowanie","subscription":"Abonament","discount":"Rabaty od Allegro"}

print(f"\n{'='*90}")
print(f"  СРАВНЕНИЕ С ЭТАЛОНОМ ALLEGRO — {TEST_SHOP}")
print(f"{'='*90}")

for mk, mt in sorted(month_totals.items()):
    et = ETALON.get(mk)
    label = months_ru[int(mk[5:7])-1] + " " + mk[:4]
    print(f"\n  {'─'*86}")
    print(f"  {label}")
    print(f"  {'─'*86}")

    # ПРОДАЖИ по странам в локальной валюте
    print(f"\n  {'ПРОДАЖИ по странам (локальная валюта)':}")
    print(f"  {'Страна':<12} {'Валюта':<6} {'НАШИ':>16} {'ALLEGRO':>16} {'РАЗНИЦА':>14} {'СТАТУС':>8}")
    print(f"  {'─'*12} {'─'*6} {'─'*16} {'─'*16} {'─'*14} {'─'*8}")
    for mkt, cur in [("allegro-pl","PLN"),("allegro-cz","CZK"),("allegro-hu","HUF"),("allegro-sk","EUR")]:
        our = mt["countries_local"][mkt]
        flag = {"allegro-pl":"PL","allegro-cz":"CZ","allegro-hu":"HU","allegro-sk":"SK"}[mkt]
        if et:
            ref, _ = et["sales_local"][mkt]
            diff = our - ref
            pct  = (diff/ref*100) if ref else 0
            ok   = "OK" if abs(pct) < 1 else ("~OK" if abs(pct) < 5 else "ОШИБКА")
            print(f"  {flag:<12} {cur:<6} {our:>16.2f} {ref:>16.2f} {diff:>+14.2f} {ok:>8}")
        else:
            print(f"  {flag:<12} {cur:<6} {our:>16.2f} {'—':>16} {'—':>14} {'—':>8}")

    print(f"\n  {'Итого (PLN)':18} {mt['sales_total']:>16.2f}")

    # РАСХОДЫ в PLN
    print(f"\n  {'РАСХОДЫ (billing API → PLN)':}")
    print(f"  {'Категория':<28} {'НАШИ PLN':>16} {'ALLEGRO PLN':>16} {'РАЗНИЦА':>14} {'СТАТУС':>8}")
    print(f"  {'─'*28} {'─'*16} {'─'*16} {'─'*14} {'─'*8}")
    for cat in ["commission","delivery","ads","subscription","discount"]:
        our = mt["costs"][cat]
        if et:
            ref = et["costs_pln"][cat]
            diff = our - ref
            ok   = "OK" if abs(diff) < 5 else ("~OK" if abs(diff) < 50 else "ОШИБКА")
            sign = "+" if cat == "discount" else "-"
            print(f"  {COST_NAMES[cat]:<28} {sign}{our:>15.2f} {sign}{ref:>15.2f} {diff:>+14.2f} {ok:>8}")
        else:
            sign = "+" if cat == "discount" else "-"
            print(f"  {COST_NAMES[cat]:<28} {sign}{our:>15.2f} {'—':>16} {'—':>14} {'—':>8}")
    if mt["costs"]["other"] > 0:
        print(f"  {'⚠ Other (НЕИЗВЕСТНЫЕ)':<28} -{mt['costs']['other']:>15.2f} {'—':>16} {'—':>14} {'ИСПРАВИТЬ':>8}")

print(f"\n{'='*90}")
print("НЕИЗВЕСТНЫЕ ТИПЫ billing (попали в Other):")
if UNKNOWN_TYPES_LOG:
    for tid, v in sorted(UNKNOWN_TYPES_LOG.items(), key=lambda x: -x[1]["total"]):
        print(f"  [{tid}]  {v['name']:<50} = {v['total']:.2f} PLN")
else:
    print("  Пусто — отлично!")

print(f"\nПОЛОЖИТЕЛЬНЫЕ ТИПЫ (не попали в Rabaty — нужно добавить в маппинг):")
if POSITIVE_TYPES_LOG:
    for tid, v in sorted(POSITIVE_TYPES_LOG.items(), key=lambda x: -x[1]["total"]):
        print(f"  [{tid}]  {v['name']:<50} = +{v['total']:.2f} PLN")
else:
    print("  Пусто")
