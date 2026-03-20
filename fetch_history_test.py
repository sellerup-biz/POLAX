"""
Тест PolaxEuroGroup — Январь + Февраль 2026
Продажи: GET /order/checkout-forms (READY_FOR_PROCESSING, totalToPay)
Расходы: GET /billing/billing-entries (по каждому маркетплейсу)
allegro-business-pl → объединяется с allegro-pl
"""
import requests, json, os, base64
from datetime import datetime
from nacl import encoding, public
from collections import defaultdict

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN","")
GH_REPO      = "sellerup-biz/POLAX"
ALL_SHOPS    = ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"]

MARKETPLACES_BILLING = {
    "allegro-pl":  "PLN",
    "allegro-cz":  "CZK",
    "allegro-hu":  "HUF",
    "allegro-sk":  "EUR",
}

BILLING_MAP = {
    "SUC":"commission","SUJ":"commission","LDS":"commission","HUN":"commission",
    "REF":"zwrot_commission",
    "HB4":"delivery","HB1":"delivery","HB8":"delivery","HB9":"delivery",
    "DPB":"delivery","DXP":"delivery","HXO":"delivery","HLB":"delivery",
    "ORB":"delivery","DHR":"delivery","DAP":"delivery","DKP":"delivery","DPP":"delivery",
    "GLS":"delivery","UPS":"delivery",
    "NSP":"ads","DPG":"ads","WYR":"ads","POD":"ads","BOL":"ads","EMF":"ads","CPC":"ads",
    "SB2":"subscription","ABN":"subscription",
    "RET":"discount","PS1":"discount",
    "PAD":"IGNORE",
}

def get_billing_cat(tid, tnam):
    if tid in BILLING_MAP: return BILLING_MAP[tid]
    n = tnam.lower()
    if any(x in n for x in ["prowizja","lokalna dopłata","opłata transakcyjna"]): return "commission"
    if any(x in n for x in ["dostawa","kurier","inpost","dpd","gls","ups","orlen","poczta",
                              "przesyłka","fulfillment","one kurier","allegro delivery",
                              "packeta","international"]): return "delivery"
    if any(x in n for x in ["kampani","reklam","promowanie","wyróżnienie","pogrubienie",
                              "podświetlenie","strona działu","pakiet promo","cpc"]): return "ads"
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

# ── ПРОДАЖИ через заказы (READY_FOR_PROCESSING) ──────────────
def get_sales_for_month(token, year, month):
    """Продажи по заказам в локальной валюте каждого маркетплейса"""
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    date_from = f"{year}-{month:02d}-01T00:00:00.000Z"
    date_to   = f"{year}-{month:02d}-{last_day:02d}T23:59:59.999Z"

    orders = []
    offset = 0
    while True:
        params = {"lineItems.boughtAt.gte":date_from,"lineItems.boughtAt.lte":date_to,
                  "limit":100,"offset":offset}
        data = requests.get("https://api.allegro.pl/order/checkout-forms",
                            headers=hdrs(token), params=params).json()
        if "checkoutForms" not in data:
            print(f"  Ошибка orders: {data}"); break
        batch = data.get("checkoutForms",[])
        orders.extend(batch)
        if len(batch) < 100: break
        offset += 100

    # Только оплаченные заказы
    active = [o for o in orders if o.get("status") == "READY_FOR_PROCESSING"]

    # Суммируем по маркетплейсам в локальной валюте
    by_mkt = defaultdict(float)
    for o in active:
        mkt   = o.get("marketplace",{}).get("id","НЕТ")
        total = float(((o.get("summary") or {}).get("totalToPay") or {}).get("amount",0) or 0)
        by_mkt[mkt] += total

    # Объединяем PL + business-PL → PL
    pl_total = round(by_mkt.get("allegro-pl",0) + by_mkt.get("allegro-business-pl",0), 2)
    return {
        "allegro-pl":  pl_total,
        "allegro-cz":  round(by_mkt.get("allegro-cz",0), 2),
        "allegro-hu":  round(by_mkt.get("allegro-hu",0), 2),
        "allegro-sk":  round(by_mkt.get("allegro-sk",0), 2),
    }

# ── РАСХОДЫ через billing по маркетплейсу ────────────────────
def get_costs_for_month(token, year, month):
    """Расходы в локальной валюте каждого маркетплейса"""
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    tz = get_tz(month)
    df = f"{year}-{month:02d}-01T00:00:00+0{tz}:00"
    dt = f"{year}-{month:02d}-{last_day:02d}T23:59:59+0{tz}:00"

    result = {}
    for mkt in MARKETPLACES_BILLING:
        costs   = {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0,"other":0.0}
        unknown = {}
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
            print(f"  ⚠ НОВЫЕ ТИПЫ [{mkt}]: {unknown}")
        result[mkt] = {k: round(v,2) for k,v in costs.items()}
    return result

# ── ЭТАЛОН из скриншотов ──────────────────────────────────────
ETALON = {
    "2026-01": {
        "allegro-pl": {"cur":"PLN","sales":33998.72,"commission":-4727.83,"delivery":-1793.56,"ads":-8968.75,"subscription":-199.00,"discount":46.54},
        "allegro-cz": {"cur":"CZK","sales":1613.00, "commission":-253.44, "delivery":-454.98, "ads":0,       "subscription":0,     "discount":0},
        "allegro-hu": {"cur":"HUF","sales":3790.00, "commission":-662.79, "delivery":-2570.00,"ads":0,       "subscription":0,     "discount":0},
        "allegro-sk": {"cur":"EUR","sales":93.36,   "commission":-11.66,  "delivery":-9.26,   "ads":0,       "subscription":0,     "discount":0},
    },
    "2026-02": {
        "allegro-pl": {"cur":"PLN","sales":20285.89,"commission":-3491.13,"delivery":-1180.09,"ads":-2790.42,"subscription":-199.00,"discount":116.94},
        "allegro-cz": {"cur":"CZK","sales":11186.00,"commission":-1667.61,"delivery":-2700.81,"ads":0,       "subscription":0,     "discount":8.00},
        "allegro-hu": {"cur":"HUF","sales":132115.00,"commission":-23508.13,"delivery":-14220.00,"ads":0,    "subscription":0,     "discount":0},
        "allegro-sk": {"cur":"EUR","sales":253.63,  "commission":-33.69,  "delivery":-39.41,  "ads":0,       "subscription":0,     "discount":0},
    },
}

MKT_LABEL = {"allegro-pl":"🇵🇱 PL","allegro-cz":"🇨🇿 CZ","allegro-hu":"🇭🇺 HU","allegro-sk":"🇸🇰 SK"}

def ok(our, ref):
    if ref == 0 and our == 0: return "OK"
    if ref == 0: return "—"
    return "OK" if abs(our - abs(ref)) < 2 else "ОШИБКА"

# ── ОСНОВНОЙ ЦИКЛ ─────────────────────────────────────────────
print(f"ТЕСТ: PolaxEuroGroup | Январь + Февраль 2026")
token = get_token()
print(f"Токен: OK\n")

for year, month in [(2026,1),(2026,2)]:
    mk  = f"{year}-{month:02d}"
    lbl = ["","Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"][month]
    print(f"\n{'='*70}")
    print(f"  {lbl} {year} — PolaxEuroGroup")
    print(f"{'='*70}")

    print(f"\n  Загружаю продажи...")
    sales = get_sales_for_month(token, year, month)
    print(f"  Загружаю расходы...")
    costs = get_costs_for_month(token, year, month)

    et = ETALON.get(mk, {})

    for mkt in ["allegro-pl","allegro-cz","allegro-hu","allegro-sk"]:
        cur = MARKETPLACES_BILLING[mkt]
        e   = et.get(mkt, {})
        s   = sales.get(mkt, 0)
        c   = costs.get(mkt, {})

        print(f"\n  {MKT_LABEL[mkt]} ({cur})")
        print(f"  {'─'*60}")

        # Продажи
        if e:
            ref_s = e["sales"]
            diff  = s - ref_s
            status = "OK" if abs(diff) < 2 else "ОШИБКА"
            print(f"  {'Wartość sprzedaży':<22} {s:>12.2f}  эталон:{ref_s:>10.2f}  разница:{diff:>+8.2f}  {status}")
        else:
            print(f"  {'Wartość sprzedaży':<22} {s:>12.2f}")

        # Расходы
        for cat in ["commission","delivery","ads","subscription","discount"]:
            our = c.get(cat, 0)
            if our == 0 and (not e or e.get(cat,0) == 0): continue
            sign = "+" if cat == "discount" else "-"
            names = {"commission":"Obowiązkowe","delivery":"Dostawa","ads":"Reklama i prom.",
                     "subscription":"Abonament","discount":"Rabaty od Allegro"}
            if e:
                ref_c = e.get(cat, 0)
                diff  = our - abs(ref_c)
                status = ok(our, ref_c)
                print(f"  {names[cat]:<22} {sign}{our:>11.2f}  эталон:{ref_c:>+10.2f}  разница:{diff:>+8.2f}  {status}")
            else:
                print(f"  {names[cat]:<22} {sign}{our:>11.2f}")
        if c.get("other",0) > 0:
            print(f"  ⚠ other:               -{c['other']:.2f}  ← добавить в BILLING_MAP!")

print(f"\n{'='*70}")
print("ГОТОВО!")
