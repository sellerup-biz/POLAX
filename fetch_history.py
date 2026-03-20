"""
POLAX — загрузка истории (все 3 магазина, все месяцы)
Период задаётся через переменные HISTORY_FROM и HISTORY_TO
Запускается вручную через history.yml
"""
import requests, json, os, base64, calendar
from datetime import datetime
from nacl import encoding, public
from collections import defaultdict

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

# Период задаётся через env или по умолчанию
HISTORY_FROM = os.environ.get("HISTORY_FROM", "2026-01-01")
HISTORY_TO   = os.environ.get("HISTORY_TO",   "2026-03-20")

MONTH_RU = {1:"Янв",2:"Фев",3:"Мар",4:"Апр",5:"Май",6:"Июн",
            7:"Июл",8:"Авг",9:"Сен",10:"Окт",11:"Ноя",12:"Дек"}

SHOPS = {
    "Mlot_i_Klucz":   {"client_id": os.environ.get("CLIENT_ID_MLOT",""),    "client_secret": os.environ.get("CLIENT_SECRET_MLOT",""),    "refresh_token": os.environ.get("REFRESH_TOKEN_MLOT",""),    "secret_name": "REFRESH_TOKEN_MLOT"},
    "PolaxEuroGroup": {"client_id": os.environ.get("CLIENT_ID_POLAX",""),   "client_secret": os.environ.get("CLIENT_SECRET_POLAX",""),   "refresh_token": os.environ.get("REFRESH_TOKEN_POLAX",""),   "secret_name": "REFRESH_TOKEN_POLAX"},
    "Sila_Narzedzi":  {"client_id": os.environ.get("CLIENT_ID_SILA",""),    "client_secret": os.environ.get("CLIENT_SECRET_SILA",""),    "refresh_token": os.environ.get("REFRESH_TOKEN_SILA",""),    "secret_name": "REFRESH_TOKEN_SILA"},
}

BILLING_MAP = {
    "SUC":"commission","SUJ":"commission","LDS":"commission","HUN":"commission",
    "REF":"zwrot_commission",
    "HB4":"delivery","HB1":"delivery","HB8":"delivery","HB9":"delivery",
    "DPB":"delivery","DXP":"delivery","HXO":"delivery","HLB":"delivery",
    "ORB":"delivery","DHR":"delivery","DAP":"delivery","DKP":"delivery","DPP":"delivery",
    "GLS":"delivery","UPS":"delivery","UPD":"delivery",
    "DTR":"delivery","DPA":"delivery","ITR":"delivery","HLA":"delivery",
    "DDP":"delivery","HB3":"delivery","DPS":"delivery","UTR":"delivery",
    "NSP":"ads","DPG":"ads","WYR":"ads","POD":"ads","BOL":"ads","EMF":"ads","CPC":"ads",
    "FEA":"ads","BRG":"ads","FSF":"ads",
    "SB2":"subscription","ABN":"subscription",
    "RET":"discount","PS1":"discount",
    "PAD":"IGNORE",
}

def get_billing_cat(tid, tnam):
    if tid in BILLING_MAP: return BILLING_MAP[tid]
    n = tnam.lower()
    if "kampanii" in n or "kampania" in n: return "ads"
    if any(x in n for x in ["prowizja","lokalna dopłata","opłata transakcyjna"]): return "commission"
    if any(x in n for x in ["dostawa","kurier","inpost","dpd","gls","ups","orlen","poczta",
                              "przesyłka","fulfillment","one kurier","allegro delivery",
                              "packeta","international","dodatkowa za dostawę"]): return "delivery"
    if any(x in n for x in ["kampani","reklam","promowanie","wyróżnienie","pogrubienie",
                              "podświetlenie","strona działu","pakiet promo","cpc","ads"]): return "ads"
    if any(x in n for x in ["abonament","smart"]): return "subscription"
    if any(x in n for x in ["rozliczenie akcji","wyrównanie w programie allegro","rabat"]): return "discount"
    if any(x in n for x in ["zwrot kosztów","zwrot prowizji"]): return "zwrot_commission"
    if "pobranie opłat z wpływów" in n: return "IGNORE"
    return "other"

def get_gh_pubkey():
    r = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
                     headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"})
    return r.json()

def save_token(secret_name, new_rt, pubkey):
    if not new_rt or not GH_TOKEN: return
    try:
        pk  = public.PublicKey(pubkey["key"].encode(), encoding.Base64Encoder())
        enc = base64.b64encode(public.SealedBox(pk).encrypt(new_rt.encode())).decode()
        requests.put(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
                     headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"},
                     json={"encrypted_value":enc,"key_id":pubkey["key_id"]})
        print(f"    Токен {secret_name} сохранён")
    except Exception as e:
        print(f"    ⚠ Ошибка токена {secret_name}: {e}")

def get_token(shop):
    r = requests.post("https://allegro.pl/auth/oauth/token",
                      auth=(shop["client_id"], shop["client_secret"]),
                      data={"grant_type":"refresh_token",
                            "refresh_token":shop["refresh_token"],
                            "redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d:
        print(f"    ОШИБКА: {d}"); return None, None
    return d["access_token"], d.get("refresh_token","")

def hdrs(t):
    return {"Authorization":f"Bearer {t}","Accept":"application/vnd.allegro.public.v1+json"}

def get_tz(month): return 2 if 3 <= month <= 10 else 1

def get_months_in_range(date_from, date_to):
    """Список месяцев в диапазоне"""
    months = []
    df = datetime.strptime(date_from, "%Y-%m-%d")
    dt = datetime.strptime(date_to,   "%Y-%m-%d")
    cur = datetime(df.year, df.month, 1)
    while cur <= dt:
        months.append((cur.year, cur.month))
        if cur.month == 12: cur = datetime(cur.year+1, 1, 1)
        else:               cur = datetime(cur.year, cur.month+1, 1)
    return months

def get_sales_for_month(token, year, month):
    last_day = calendar.monthrange(year, month)[1]
    tz = get_tz(month)
    df = f"{year}-{month:02d}-01T00:00:00+0{tz}:00"
    dt = f"{year}-{month:02d}-{last_day:02d}T23:59:59+0{tz}:00"
    by_mkt = defaultdict(float)
    for mkt in ["allegro-pl","allegro-business-pl","allegro-cz","allegro-hu","allegro-sk"]:
        offset = 0
        while True:
            ops = requests.get("https://api.allegro.pl/payments/payment-operations",
                               headers=hdrs(token),
                               params={"group":"INCOME","occurredAt.gte":df,"occurredAt.lte":dt,
                                       "marketplaceId":mkt,"limit":50,"offset":offset}
                               ).json().get("paymentOperations",[])
            for op in ops:
                try: by_mkt[mkt] += float(op["value"]["amount"])
                except: pass
            if len(ops) < 50: break
            offset += 50
    return {
        "allegro-pl":  round(by_mkt["allegro-pl"] + by_mkt["allegro-business-pl"], 2),
        "allegro-cz":  round(by_mkt["allegro-cz"], 2),
        "allegro-hu":  round(by_mkt["allegro-hu"], 2),
        "allegro-sk":  round(by_mkt["allegro-sk"], 2),
    }

def get_costs_for_month(token, year, month):
    last_day = calendar.monthrange(year, month)[1]
    tz = get_tz(month)
    df = f"{year}-{month:02d}-01T00:00:00+0{tz}:00"
    dt = f"{year}-{month:02d}-{last_day:02d}T23:59:59+0{tz}:00"
    costs = {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0}
    offset = 0
    while True:
        entries = requests.get("https://api.allegro.pl/billing/billing-entries",
                               headers=hdrs(token),
                               params={"occurredAt.gte":df,"occurredAt.lte":dt,
                                       "limit":100,"offset":offset}
                               ).json().get("billingEntries",[])
        for e in entries:
            try:
                amt = float(e["value"]["amount"])
                cat = get_billing_cat(e["type"]["id"], e["type"]["name"])
                if cat == "IGNORE": continue
                if amt < 0:
                    if cat in costs: costs[cat] += abs(amt)
                elif amt > 0:
                    if cat == "zwrot_commission": costs["commission"] = max(0, costs["commission"] - amt)
                    elif cat == "delivery":       costs["delivery"]   = max(0, costs["delivery"] - amt)
                    elif cat == "discount":       costs["discount"]   += amt
            except: pass
        if len(entries) < 100: break
        offset += 100
    return {k: round(v,2) for k,v in costs.items()}

def load_data():
    try:
        with open("data.json") as f: return json.load(f)
    except:
        return {"days":[],"months":[]}

def save_data(data):
    with open("data.json","w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",",":"))

def update_months(data):
    months_map = defaultdict(lambda:{
        "Mlot_i_Klucz":0,"PolaxEuroGroup":0,"Sila_Narzedzi":0,
        "countries":{"allegro-pl":0,"allegro-cz":0,"allegro-hu":0,"allegro-sk":0},
        "costs":{"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0}
    })
    for day in data["days"]:
        raw_mk = day["date"][:7]
        y,mo = int(raw_mk[:4]), int(raw_mk[5:7])
        mk = MONTH_RU[mo] + " " + str(y)
        for shop in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"]:
            months_map[mk][shop] = round(months_map[mk][shop] + day.get(shop,0), 2)
        for c in ["allegro-pl","allegro-cz","allegro-hu","allegro-sk"]:
            months_map[mk]["countries"][c] = round(
                months_map[mk]["countries"][c] + day.get("countries",{}).get(c,0), 2)
        for cat in ["commission","delivery","ads","subscription","discount"]:
            months_map[mk]["costs"][cat] = round(
                months_map[mk]["costs"][cat] + day.get("costs",{}).get(cat,0), 2)
    data["months"] = [{"month":k,**v} for k,v in sorted(months_map.items())]

# ── MAIN ─────────────────────────────────────────────────────
print(f"История: {HISTORY_FROM} → {HISTORY_TO}")
months = get_months_in_range(HISTORY_FROM, HISTORY_TO)
print(f"Месяцев: {len(months)}")

data    = load_data()
pubkey  = get_gh_pubkey()

# Собираем данные по каждому магазину по месяцам
# Структура: month_data[month_key][shop] = {sales_by_country, costs}
month_data = defaultdict(lambda:{
    "Mlot_i_Klucz":   {"sales":{},"total":0},
    "PolaxEuroGroup": {"sales":{},"total":0,"costs":{}},
    "Sila_Narzedzi":  {"sales":{},"total":0},
})

for shop_name, shop in SHOPS.items():
    print(f"\n{'='*50}")
    print(f"  {shop_name}")
    print(f"{'='*50}")
    token, new_rt = get_token(shop)
    if not token: continue
    save_token(shop["secret_name"], new_rt, pubkey)

    for year, month in months:
        mk = MONTH_RU[month] + " " + str(year)
        print(f"  {mk}...", end=" ", flush=True)
        sales = get_sales_for_month(token, year, month)
        total = sum(sales.values())
        month_data[mk][shop_name]["sales"]  = sales
        month_data[mk][shop_name]["total"]  = total
        print(f"продажи={total:.2f}", end=" ")

        if shop_name == "PolaxEuroGroup":
            costs = get_costs_for_month(token, year, month)
            month_data[mk][shop_name]["costs"] = costs
            print(f"расходы OK", end="")
        print()

# Конвертируем в дни (по одному фиктивному дню на месяц = 1-е число)
# Убираем старые данные за период и добавляем новые
date_set = {f"{y}-{m:02d}" for y,m in months}

# Удаляем существующие дни за период
data["days"] = [d for d in data["days"]
                if d["date"][:7] not in date_set]

# Обратная карта: "Янв 2026" -> (2026, 1)
MONTH_RU_REV = {v:k for k,v in MONTH_RU.items()}

# Добавляем новые дни
for mk in sorted(month_data.keys(), key=lambda x: (int(x[-4:]), MONTH_RU_REV[x[:3]])):
    d  = month_data[mk]
    pl = d["PolaxEuroGroup"]
    ml = d["Mlot_i_Klucz"]
    si = d["Sila_Narzedzi"]

    # Восстанавливаем год и месяц из ключа "Янв 2026"
    mk_year  = int(mk[-4:])
    mk_month = MONTH_RU_REV[mk[:3]]

    # Суммируем продажи по странам по всем магазинам
    countries = {"allegro-pl":0,"allegro-cz":0,"allegro-hu":0,"allegro-sk":0}
    for shop_d in [pl, ml, si]:
        for mkt, val in shop_d.get("sales",{}).items():
            if mkt in countries:
                countries[mkt] = round(countries[mkt] + val, 2)

    day_entry = {
        "date":          f"{mk_year:04d}-{mk_month:02d}-01",
        "Mlot_i_Klucz":  round(ml["total"], 2),
        "PolaxEuroGroup":round(pl["total"], 2),
        "Sila_Narzedzi": round(si["total"], 2),
        "countries":     countries,
        "costs":         pl.get("costs", {"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0}),
    }
    data["days"].append(day_entry)

data["days"].sort(key=lambda x: x["date"])
update_months(data)
save_data(data)
print(f"\n✅ Готово! Месяцев сохранено: {len(months)}")
print(f"   Всего дней в data.json: {len(data['days'])}")
print(f"   Всего месяцев в data.json: {len(data['months'])}")
