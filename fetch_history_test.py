"""
Тест PolaxEuroGroup — Апрель-Август 2025
Продажи: payments/payment-operations (INCOME, локальная валюта)
Расходы: billing/billing-entries (по каждому маркетплейсу)
Эталон: из CSV файлов Allegro UI
"""
import requests, os, base64
from nacl import encoding, public
from collections import defaultdict
import calendar

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN","")
GH_REPO      = "sellerup-biz/POLAX"

BILLING_MAP = {
    "SUC":"commission","SUJ":"commission","LDS":"commission","HUN":"commission",
    "REF":"zwrot_commission",
    "HB4":"delivery","HB1":"delivery","HB8":"delivery","HB9":"delivery",
    "DPB":"delivery","DXP":"delivery","HXO":"delivery","HLB":"delivery",
    "ORB":"delivery","DHR":"delivery","DAP":"delivery","DKP":"delivery","DPP":"delivery",
    "GLS":"delivery","UPS":"delivery","UPD":"delivery",
    "DTR":"delivery","DPA":"delivery","ITR":"delivery","HLA":"delivery",
    "NSP":"ads","DPG":"ads","WYR":"ads","POD":"ads","BOL":"ads","EMF":"ads","CPC":"ads",
    "SB2":"subscription","ABN":"subscription",
    "RET":"discount","PS1":"discount",
    "PAD":"IGNORE",
}

def get_billing_cat(tid, tnam):
    if tid in BILLING_MAP: return BILLING_MAP[tid]
    n = tnam.lower()
    # Prowizja od sprzedaży w Kampanii → ads (не commission!)
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

def get_tz(month): return 2 if 3 <= month <= 10 else 1

def get_sales(token, year, month):
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
        "PLN": round(by_mkt["allegro-pl"] + by_mkt["allegro-business-pl"], 2),
        "CZK": round(by_mkt["allegro-cz"], 2),
        "HUF": round(by_mkt["allegro-hu"], 2),
        "EUR": round(by_mkt["allegro-sk"], 2),
    }

def get_costs(token, year, month):
    last_day = calendar.monthrange(year, month)[1]
    tz = get_tz(month)
    df = f"{year}-{month:02d}-01T00:00:00+0{tz}:00"
    dt = f"{year}-{month:02d}-{last_day:02d}T23:59:59+0{tz}:00"
    # allegro-pl + allegro-business-pl → PLN (суммируем вместе)
    # allegro-cz → CZK, allegro-hu → HUF, allegro-sk → EUR
    MKT_GROUPS = {
        "PLN": ["allegro-pl", "allegro-business-pl"],
        "CZK": ["allegro-cz"],
        "HUF": ["allegro-hu"],
        "EUR": ["allegro-sk"],
    }
    result = {}
    for cur, mkts in MKT_GROUPS.items():
        costs   = {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0,"other":0.0}
        unknown = {}
        for mkt in mkts:
            offset  = 0
            while True:
                entries = requests.get("https://api.allegro.pl/billing/billing-entries",
                                       headers=hdrs(token),
                                       params={"occurredAt.gte":df,"occurredAt.lte":dt,
                                               "marketplaceId":mkt,"limit":100,"offset":offset}
                                       ).json().get("billingEntries",[])
                for e in entries:
                    try:
                        amt  = float(e["value"]["amount"])
                        tid  = e["type"]["id"]
                        tnam = e["type"]["name"]
                        cat  = get_billing_cat(tid, tnam)
                        if cat == "IGNORE": continue
                        if amt < 0:
                            if cat in costs: costs[cat] += abs(amt)
                            if cat == "other": unknown[tid] = tnam
                        elif amt > 0:
                            if cat == "zwrot_commission": costs["commission"] = max(0, costs["commission"] - amt)
                            elif cat == "delivery":       costs["delivery"]   = max(0, costs["delivery"] - amt)
                            elif cat == "discount":       costs["discount"]   += amt
                    except: pass
                if len(entries) < 100: break
                offset += 100
        if unknown:
            print(f"    ⚠ [{cur}] НОВЫЕ ТИПЫ: {unknown}")
        result[cur] = {k: round(v,2) for k,v in costs.items()}
    return result

# ── ЭТАЛОН из CSV ─────────────────────────────────────────────
ETALON = {
    "2025-04": {
        "PLN": {"sales":47514.95,"commission":6169.66,"delivery":3002.50,"ads":10924.03,"subscription":199.00,"discount":221.06},
        "CZK": {"sales":29700.00,"commission":3593.98,"delivery":3821.48,"ads":6431.20, "subscription":0,    "discount":0},
        "EUR": {"sales":402.61,  "commission":50.22,  "delivery":78.25,  "ads":123.93,  "subscription":0,    "discount":0},
        "HUF": {"sales":0,       "commission":0,      "delivery":0,      "ads":0,       "subscription":0,    "discount":0},
    },
    "2025-05": {
        "PLN": {"sales":39980.06,"commission":5452.55,"delivery":2496.76,"ads":6783.43,"subscription":199.00,"discount":371.51},
        "CZK": {"sales":28506.00,"commission":3507.39,"delivery":4191.42,"ads":3609.84,"subscription":0,    "discount":0},
        "EUR": {"sales":160.81,  "commission":21.04,  "delivery":26.52,  "ads":42.35,  "subscription":0,    "discount":0},
        "HUF": {"sales":0,       "commission":0,      "delivery":0,      "ads":0,      "subscription":0,    "discount":0},
    },
    "2025-06": {
        "PLN": {"sales":45202.92,"commission":5961.35,"delivery":3155.08,"ads":6153.71,"subscription":199.00,"discount":337.32},
        "CZK": {"sales":23922.00,"commission":2822.41,"delivery":4329.88,"ads":2670.38,"subscription":0,    "discount":0},
        "EUR": {"sales":273.46,  "commission":31.55,  "delivery":35.73,  "ads":21.21,  "subscription":0,    "discount":0},
        "HUF": {"sales":14800.00,"commission":1638.40,"delivery":1840.00,"ads":0,       "subscription":0,    "discount":0},
    },
    "2025-07": {
        "PLN": {"sales":45126.79,"commission":6268.51,"delivery":4088.90,"ads":6999.44,"subscription":199.00,"discount":182.52},
        "CZK": {"sales":23529.00,"commission":3099.01,"delivery":6001.45,"ads":2997.75,"subscription":0,    "discount":0},
        "EUR": {"sales":212.90,  "commission":27.24,  "delivery":42.30,  "ads":19.62,  "subscription":0,    "discount":0},
        "HUF": {"sales":11415.00,"commission":1863.49,"delivery":690.00, "ads":0,       "subscription":0,    "discount":0},
    },
    "2025-08": {
        "PLN": {"sales":39887.85,"commission":5385.71,"delivery":2946.40,"ads":7934.64,"subscription":199.00,"discount":492.73},
        "CZK": {"sales":16559.00,"commission":2000.68,"delivery":7524.65,"ads":2862.00,"subscription":0,    "discount":0},
        "EUR": {"sales":240.57,  "commission":33.82,  "delivery":71.93,  "ads":25.04,  "subscription":0,    "discount":0},
        "HUF": {"sales":0,       "commission":0,      "delivery":0,      "ads":0,       "subscription":0,    "discount":0},
    },
}

MKT_LABEL = {"PLN":"🇵🇱 PL","CZK":"🇨🇿 CZ","EUR":"🇸🇰 SK","HUF":"🇭🇺 HU"}
MONTHS_RU = {4:"Апр",5:"Май",6:"Июн",7:"Июл",8:"Авг"}
PERIODS = [(2025,m) for m in range(4,9)]

def check(our, ref, tolerance=3):
    if ref == 0 and our == 0: return "—"
    if ref == 0: return f"NEW:{our:.2f}"
    diff = our - ref
    return f"OK {diff:+.2f}" if abs(diff) <= tolerance else f"❌ {diff:+.2f}"

# ── ОСНОВНОЙ ЦИКЛ ─────────────────────────────────────────────
print(f"ТЕСТ: PolaxEuroGroup | Апрель–Август 2025")
token = get_token()
print(f"Токен: OK\n")

# Собираем данные
all_sales = {}
all_costs = {}
for year, month in PERIODS:
    mk = f"{year}-{month:02d}"
    print(f"  Загружаю {MONTHS_RU[month]} {year}...")
    all_sales[mk] = get_sales(token, year, month)
    all_costs[mk] = get_costs(token, year, month)

# ── ТАБЛИЦА ПРОДАЖ ────────────────────────────────────────────
print(f"\n{'='*90}")
print("  ПРОДАЖИ (payments/payment-operations INCOME) в локальной валюте")
print(f"{'='*90}")
print(f"  {'':5} {'':5} {'НАШИ':>12} {'ЭТАЛОН':>12} {'СТАТУС':>12}")
print(f"  {'─'*5} {'─'*5} {'─'*12} {'─'*12} {'─'*15}")

for year, month in PERIODS:
    mk  = f"{year}-{month:02d}"
    lbl = MONTHS_RU[month]
    s   = all_sales[mk]
    et  = ETALON.get(mk,{})
    print(f"\n  {lbl} {year}:")
    for cur in ["PLN","CZK","EUR","HUF"]:
        our = s.get(cur,0)
        ref = et.get(cur,{}).get("sales",0)
        if our == 0 and ref == 0: continue
        st  = check(our, ref)
        print(f"    {MKT_LABEL[cur]:<10} {our:>12.2f} {ref:>12.2f}  {st}")

# ── ТАБЛИЦА РАСХОДОВ ──────────────────────────────────────────
print(f"\n{'='*90}")
print("  РАСХОДЫ (billing/billing-entries) в локальной валюте")
print(f"{'='*90}")

CATS = [("commission","Obowiązkowe"),("delivery","Dostawa"),
        ("ads","Reklama"),("subscription","Abonament"),("discount","Rabaty")]

for year, month in PERIODS:
    mk  = f"{year}-{month:02d}"
    lbl = MONTHS_RU[month]
    c   = all_costs[mk]
    et  = ETALON.get(mk,{})
    print(f"\n  {lbl} {year}:")
    print(f"    {'Страна':<10} {'Категория':<20} {'НАШИ':>10} {'ЭТАЛОН':>10} {'СТАТУС':>12}")
    print(f"    {'─'*10} {'─'*20} {'─'*10} {'─'*10} {'─'*15}")
    for cur in ["PLN","CZK","EUR","HUF"]:
        costs = c.get(cur,{})
        etalon_c = et.get(cur,{})
        for cat, name in CATS:
            our = costs.get(cat,0)
            ref = etalon_c.get(cat,0)
            if our == 0 and ref == 0: continue
            sign = "+" if cat == "discount" else "-"
            st   = check(our, ref)
            print(f"    {MKT_LABEL.get(cur,'?'):<10} {name:<20} {sign}{our:>9.2f} {sign}{ref:>9.2f}  {st}")
        if costs.get("other",0) > 0:
            print(f"    {MKT_LABEL.get(cur,'?'):<10} ⚠ OTHER              -{costs['other']:>9.2f}  ← добавить в BILLING_MAP!")

print(f"\n{'='*90}")
print("ГОТОВО!")
