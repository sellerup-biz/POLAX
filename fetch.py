import requests, json, os, base64
from datetime import datetime, timedelta, timezone
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

now_utc      = datetime.now(timezone.utc)
tz_offset    = 2 if 3 <= now_utc.month <= 10 else 1
polish_now   = now_utc + timedelta(hours=tz_offset)
yesterday_pl = polish_now - timedelta(days=1)
tz_str       = f"+0{tz_offset}:00"
date_from    = yesterday_pl.strftime("%Y-%m-%dT00:00:00") + tz_str
date_to      = yesterday_pl.strftime("%Y-%m-%dT23:59:59") + tz_str
date_key     = yesterday_pl.strftime("%Y-%m-%d")

MARKETPLACES = {"allegro-pl":"PLN","allegro-business-pl":"PLN","allegro-cz":"CZK","allegro-hu":"HUF","allegro-sk":"EUR"}

SHOPS = {}
for key, name, sname in [("SILA","Sila_Narzedzi","REFRESH_TOKEN_SILA"),
                          ("POLAX","PolaxEuroGroup","REFRESH_TOKEN_POLAX"),
                          ("MLOT","Mlot_i_Klucz","REFRESH_TOKEN_MLOT")]:
    if os.environ.get(f"CLIENT_ID_{key}") and os.environ.get(f"REFRESH_TOKEN_{key}"):
        SHOPS[name] = {"client_id":     os.environ[f"CLIENT_ID_{key}"],
                       "client_secret": os.environ[f"CLIENT_SECRET_{key}"],
                       "refresh_token": os.environ[f"REFRESH_TOKEN_{key}"],
                       "secret_name":   sname}

# ── МАППИНГ по type.id (получен из diagnose_billing.py) ──────
# Источник: реальные данные PolaxEuroGroup Январь 2026
# Обновляй этот словарь при появлении новых type.id в логах (Other)
BILLING_MAP = {
    # ОБOWIĄZKOWE — комиссия Allegro
    "SUC": "commission",   # Prowizja od sprzedaży
    "SUJ": "commission",   # Prowizja od sprzedaży (inne rynki)
    # Lokalna dopłata (HU/SK/CZ) — тоже Obowiązkowe
    "LDS": "commission",   # Lokalna dopłata od sprzedaży detalicznej

    # ZWROT PROWIZJI — уменьшает commission (всегда положительная сумма)
    "REF": "zwrot_commission",  # Zwrot kosztów (+124.11 → уменьшает SUC)

    # DOSTAWA — все виды доставки
    "HB4": "delivery",    # InPost
    "HB1": "delivery",    # DPD
    "DPB": "delivery",    # DPD Allegro Delivery
    "DXP": "delivery",    # One Kurier Allegro Delivery
    "HXO": "delivery",    # One Kurier Allegro Delivery (другой код)
    "HLB": "delivery",    # DHL Allegro Delivery
    "ORB": "delivery",    # ORLEN Paczka Allegro Delivery
    "DHR": "delivery",    # Opłata dodatkowa za dostawę DHL
    "GLS": "delivery",    # GLS (если появится)
    "UPS": "delivery",    # UPS (если появится)

    # REKLAMA I PROMOWANIE
    "NSP": "ads",          # Opłata za kampanię Ads (CPC/Ads)
    "DPG": "ads",          # Opłata za promowanie na stronie działu
    "WYR": "ads",          # Wyróżnienie
    "POD": "ads",          # Podświetlenie
    "BOL": "ads",          # Pogrubienie
    "EMF": "ads",          # Pakiet promo
    "CPC": "ads",          # CPC ogólny

    # ABONAMENT
    "SB2": "subscription", # Abonament profesjonalny
    "ABN": "subscription", # Abonament (inne)

    # RABATY OD ALLEGRO (положительные суммы)
    "RET": "discount",     # Rozliczenie akcji promocyjnej (+36.52)
    "PS1": "discount",     # Wyrównanie w programie Allegro Ceny (+10.02)

    # IGNORE — технические типы, не влияют на расходы
    "PAD": "IGNORE",       # Pobranie opłat z wpływów (Allegro списывает из поступлений)
}

def get_billing_cat(type_id, type_name, amount):
    """Определяет категорию записи. Сначала по ID, потом по имени."""
    # 1. По type.id — самый надёжный способ
    if type_id in BILLING_MAP:
        return BILLING_MAP[type_id]
    # 2. По type.name — фолбэк для новых типов
    n = type_name.lower()
    if any(x in n for x in ["prowizja","lokalna dopłata","opłata transakcyjna"]): return "commission"
    if any(x in n for x in ["dostawa","kurier","inpost","dpd","gls","ups","orlen","poczta",
                              "przesyłka","fulfillment","one kurier","allegro delivery"]): return "delivery"
    if any(x in n for x in ["kampani","reklam","promowanie","wyróżnienie","pogrubienie",
                              "podświetlenie","strona działu","pakiet promo","cpc","ads"]): return "ads"
    if any(x in n for x in ["abonament","smart"]): return "subscription"
    if any(x in n for x in ["rozliczenie akcji","wyrównanie w programie allegro","rabat"]): return "discount"
    if any(x in n for x in ["zwrot kosztów","zwrot prowizji"]): return "zwrot_commission"
    if any(x in n for x in ["pobranie opłat z wpływów"]): return "IGNORE"
    return "other"

# ── NBP курсы ─────────────────────────────────────────────────
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

# ── GitHub secrets ────────────────────────────────────────────
def get_gh_pk():
    r = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
                     headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"})
    return r.json()

def update_gh_secret(name, val, key_id, key_val):
    pk  = public.PublicKey(key_val.encode(), encoding.Base64Encoder())
    enc = base64.b64encode(public.SealedBox(pk).encrypt(val.encode())).decode()
    r   = requests.put(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{name}",
                       headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
                       json={"encrypted_value": enc, "key_id": key_id})
    return r.status_code in (201, 204)

# ── OAuth ─────────────────────────────────────────────────────
def get_token(cid, cs, rt):
    r = requests.post("https://allegro.pl/auth/oauth/token", auth=(cid, cs),
                      data={"grant_type":"refresh_token","refresh_token":rt,"redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d: print(f"  Ошибка: {d}"); return None, None
    return d["access_token"], d.get("refresh_token", rt)

def hdrs(t):
    return {"Authorization": f"Bearer {t}", "Accept": "application/vnd.allegro.public.v1+json"}

# ── ПРОДАЖИ ───────────────────────────────────────────────────
def get_sales(token, df, dt, date_key):
    # Общий итог без фильтра
    total = 0.0
    offset = 0
    while True:
        ops = requests.get("https://api.allegro.pl/payments/payment-operations", headers=hdrs(token),
                           params={"group":"INCOME","occurredAt.gte":df,"occurredAt.lte":dt,
                                   "limit":100,"offset":offset}).json().get("paymentOperations",[])
        for op in ops:
            try: total += float(op["value"]["amount"]) * get_rate(op["value"]["currency"], date_key)
            except: pass
        if len(ops) < 100: break
        offset += 100

    # По странам
    countries = {k: 0.0 for k in MARKETPLACES}
    for mkt in MARKETPLACES:
        offset = 0
        while True:
            ops = requests.get("https://api.allegro.pl/payments/payment-operations", headers=hdrs(token),
                               params={"group":"INCOME","occurredAt.gte":df,"occurredAt.lte":dt,
                                       "marketplaceId":mkt,"limit":100,"offset":offset}).json().get("paymentOperations",[])
            for op in ops:
                try: countries[mkt] += float(op["value"]["amount"]) * get_rate(op["value"]["currency"], date_key)
                except: pass
            if len(ops) < 100: break
            offset += 100
        countries[mkt] = round(countries[mkt], 2)

    return countries, round(total, 2)

# ── РАСХОДЫ ───────────────────────────────────────────────────
def get_costs(token, df, dt):
    costs   = {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0,"other":0.0}
    unknown = {}
    offset  = 0
    while True:
        entries = requests.get("https://api.allegro.pl/billing/billing-entries", headers=hdrs(token),
                               params={"occurredAt.gte":df,"occurredAt.lte":dt,
                                       "limit":100,"offset":offset}).json().get("billingEntries",[])
        for e in entries:
            try:
                amt  = float(e["value"]["amount"])
                tid  = e["type"]["id"]
                tnam = e["type"]["name"]
                cat  = get_billing_cat(tid, tnam, amt)
                if cat == "IGNORE": continue
                if amt < 0:
                    if cat in costs: costs[cat] += abs(amt)
                    if cat == "other":
                        unknown[tid] = tnam
                elif amt > 0:
                    if cat == "zwrot_commission": costs["commission"] = max(0, costs["commission"] - amt)
                    elif cat == "delivery":       costs["delivery"]   = max(0, costs["delivery"]   - amt)
                    elif cat == "discount":       costs["discount"]   += amt
                    elif cat == "other":
                        unknown[tid] = tnam
            except: pass
        if len(entries) < 100: break
        offset += 100
    if unknown:
        print(f"  ⚠ НОВЫЕ ТИПЫ (добавь в BILLING_MAP): {unknown}")
    return {k: round(v, 2) for k, v in costs.items()}

# ── ОСНОВНОЙ ЦИКЛ ─────────────────────────────────────────────
print(f"Дата: {date_key} UTC+{tz_offset} | {date_from} → {date_to}")

gh_key    = get_gh_pk()
gh_key_id  = gh_key.get("key_id")
gh_key_val = gh_key.get("key")

try:
    with open("data.json") as f: data = json.load(f)
except:
    data = {"days": [], "months": []}
if "months" not in data: data["months"] = []

existing = next((d for d in data["days"] if d["date"] == date_key), None)
if not existing:
    existing = {"date": date_key, "Mlot_i_Klucz":0, "PolaxEuroGroup":0, "Sila_Narzedzi":0,
                "countries":{k:0 for k in MARKETPLACES},
                "costs":{"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0,"other":0}}
    data["days"].append(existing)

all_countries = {k: 0.0 for k in MARKETPLACES}
all_costs     = {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0,"other":0.0}

for shop, creds in SHOPS.items():
    print(f"\n--- {shop} ---")
    token, new_rt = get_token(creds["client_id"], creds["client_secret"], creds["refresh_token"])
    if not token: continue
    if new_rt and gh_key_id and gh_key_val:
        ok = update_gh_secret(creds["secret_name"], new_rt, gh_key_id, gh_key_val)
        print(f"  Токен: {'OK' if ok else 'ERR'}")

    countries, total = get_sales(token, date_from, date_to, date_key)
    costs            = get_costs(token, date_from, date_to)

    existing[shop] = total
    for k, v in countries.items(): all_countries[k] = round(all_countries[k] + v, 2)
    for k, v in costs.items():     all_costs[k]     = round(all_costs[k] + v, 2)

    c = costs
    print(f"  Продажи: {total:.2f} PLN")
    print(f"  Obowiązkowe: -{c['commission']:.2f} | Dostawa: -{c['delivery']:.2f} | "
          f"Reklama: -{c['ads']:.2f} | Abonament: -{c['subscription']:.2f} | "
          f"Rabaty: +{c['discount']:.2f}")
    if c["other"] > 0: print(f"  ⚠ Other: {c['other']:.2f}")

existing["countries"] = {k: round(v, 2) for k, v in all_countries.items()}
existing["costs"]     = {k: round(v, 2) for k, v in all_costs.items()}

# ── Пересчёт месяцев ──────────────────────────────────────────
months_ru = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
monthly   = {}
for day in data["days"]:
    mk  = day["date"][:7]
    dt  = datetime.strptime(mk, "%Y-%m")
    lbl = f"{months_ru[dt.month-1]} {dt.year}"
    if lbl not in monthly:
        monthly[lbl] = {"month":lbl,"_o":mk,"Mlot_i_Klucz":0,"PolaxEuroGroup":0,"Sila_Narzedzi":0,
                        "countries":{k:0.0 for k in MARKETPLACES},
                        "costs":{"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0,"other":0.0}}
    m = monthly[lbl]
    for s in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"]:
        m[s] = round(m[s] + day.get(s, 0), 2)
    for k in MARKETPLACES:
        m["countries"][k] = round(m["countries"][k] + day.get("countries",{}).get(k, 0), 2)
    for k in ["commission","delivery","ads","subscription","discount","other"]:
        m["costs"][k] = round(m["costs"][k] + day.get("costs",{}).get(k, 0), 2)

data["months"] = sorted(
    [{k: v for k, v in m.items() if k != "_o"} for m in monthly.values()],
    key=lambda x: monthly[x["month"]]["_o"]
)
with open("data.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\nОК: {json.dumps(existing, ensure_ascii=False)}")
