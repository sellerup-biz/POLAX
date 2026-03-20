"""
POLAX — ежедневный сбор данных (все 3 магазина, вчерашний день)
Запускается каждую ночь через fetch.yml
"""
import requests, json, os, base64, calendar
from datetime import datetime, timedelta, timezone
from nacl import encoding, public
from collections import defaultdict

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

MONTH_RU = {1:"Янв",2:"Фев",3:"Мар",4:"Апр",5:"Май",6:"Июн",
            7:"Июл",8:"Авг",9:"Сен",10:"Окт",11:"Ноя",12:"Дек"}

SHOPS = {
    "Mlot_i_Klucz":    {"client_id": os.environ.get("CLIENT_ID_MLOT",""),    "client_secret": os.environ.get("CLIENT_SECRET_MLOT",""),    "refresh_token": os.environ.get("REFRESH_TOKEN_MLOT",""),    "secret_name": "REFRESH_TOKEN_MLOT"},
    "PolaxEuroGroup":  {"client_id": os.environ.get("CLIENT_ID_POLAX",""),   "client_secret": os.environ.get("CLIENT_SECRET_POLAX",""),   "refresh_token": os.environ.get("REFRESH_TOKEN_POLAX",""),   "secret_name": "REFRESH_TOKEN_POLAX"},
    "Sila_Narzedzi":   {"client_id": os.environ.get("CLIENT_ID_SILA",""),    "client_secret": os.environ.get("CLIENT_SECRET_SILA",""),    "refresh_token": os.environ.get("REFRESH_TOKEN_SILA",""),    "secret_name": "REFRESH_TOKEN_SILA"},
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

def save_token(secret_name, new_rt, pubkey=None):
    if not new_rt or not GH_TOKEN: return
    try:
        if not pubkey: pubkey = get_gh_pubkey()
        pk  = public.PublicKey(pubkey["key"].encode(), encoding.Base64Encoder())
        enc = base64.b64encode(public.SealedBox(pk).encrypt(new_rt.encode())).decode()
        requests.put(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
                     headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"},
                     json={"encrypted_value":enc,"key_id":pubkey["key_id"]})
    except Exception as e:
        print(f"  ⚠ Ошибка сохранения токена {secret_name}: {e}")

def get_token(shop):
    r = requests.post("https://allegro.pl/auth/oauth/token",
                      auth=(shop["client_id"], shop["client_secret"]),
                      data={"grant_type":"refresh_token",
                            "refresh_token":shop["refresh_token"],
                            "redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d:
        print(f"  ОШИБКА токена: {d}"); return None, None
    return d["access_token"], d.get("refresh_token","")

def hdrs(t):
    return {"Authorization":f"Bearer {t}","Accept":"application/vnd.allegro.public.v1+json"}

def get_tz(month): return 2 if 3 <= month <= 10 else 1

def get_sales_for_day(token, date_str):
    """Продажи за один день по всем маркетплейсам"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    tz = get_tz(dt.month)
    df = f"{date_str}T00:00:00+0{tz}:00"
    dto= f"{date_str}T23:59:59+0{tz}:00"
    by_mkt = defaultdict(float)
    for mkt in ["allegro-pl","allegro-business-pl","allegro-cz","allegro-hu","allegro-sk"]:
        offset = 0
        while True:
            ops = requests.get("https://api.allegro.pl/payments/payment-operations",
                               headers=hdrs(token),
                               params={"group":"INCOME","occurredAt.gte":df,"occurredAt.lte":dto,
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

def get_costs_for_day(token, date_str):
    """Расходы за один день"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    tz = get_tz(dt.month)
    df = f"{date_str}T00:00:00+0{tz}:00"
    dto= f"{date_str}T23:59:59+0{tz}:00"
    costs = {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0}
    # PL — без фильтра marketplaceId
    entries_all = []
    offset = 0
    while True:
        batch = requests.get("https://api.allegro.pl/billing/billing-entries",
                             headers=hdrs(token),
                             params={"occurredAt.gte":df,"occurredAt.lte":dto,
                                     "limit":100,"offset":offset}
                             ).json().get("billingEntries",[])
        entries_all.extend(batch)
        if len(batch) < 100: break
        offset += 100
    for e in entries_all:
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
    """Пересчитываем месячные агрегаты из дневных данных"""
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

# ── MAIN ──────────────────────────────────────────────────────
yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
print(f"Дата: {yesterday}")

data = load_data()
existing_dates = {d["date"] for d in data["days"]}

if yesterday in existing_dates:
    print(f"  {yesterday} уже есть — пропускаем")
else:
    pubkey = get_gh_pubkey()
    day_entry = {"date": yesterday,
                 "Mlot_i_Klucz":0,"PolaxEuroGroup":0,"Sila_Narzedzi":0,
                 "countries":{"allegro-pl":0,"allegro-cz":0,"allegro-hu":0,"allegro-sk":0},
                 "costs":{"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0}}

    for shop_name, shop in SHOPS.items():
        print(f"\n  {shop_name}...")
        token, new_rt = get_token(shop)
        if not token: continue
        save_token(shop["secret_name"], new_rt, pubkey)

        # Продажи
        sales = get_sales_for_day(token, yesterday)
        total = sum(sales.values())
        day_entry[shop_name] = round(day_entry[shop_name] + total, 2)  # в PLN (приближённо)
        for mkt, val in sales.items():
            day_entry["countries"][mkt] = round(day_entry["countries"].get(mkt,0) + val, 2)

        # Расходы (только для PolaxEuroGroup — billing in PLN)
        if shop_name == "PolaxEuroGroup":
            costs = get_costs_for_day(token, yesterday)
            for cat, val in costs.items():
                day_entry["costs"][cat] = round(day_entry["costs"].get(cat,0) + val, 2)

        print(f"    Продажи: {total:.2f}")

    data["days"].append(day_entry)
    data["days"].sort(key=lambda x: x["date"])
    update_months(data)
    save_data(data)
    print(f"\n✅ {yesterday} сохранён")
