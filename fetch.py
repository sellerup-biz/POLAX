"""
POLAX — ежедневный сбор данных (все 3 магазина)
Запускается каждую ночь в 03:00 UTC через fetch.yml

За один запуск собирает:
  1. Вчера  — полные данные (complete)
  2. Сегодня — накопленные данные с начала дня (partial: true)

  + Юнит-экономика по офферам (только польский рынок):
  3. Вчера  — per-offer: revenue, fees, ads, promo → unit_data/YYYY-MM.json
  4. Сегодня — partial → unit_data/YYYY-MM.json
  Токен ротируется один раз для всех четырёх фаз.
"""
import requests, json, os, base64, calendar, time
from datetime import datetime, timedelta, timezone
from nacl import encoding, public
from collections import defaultdict

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

MONTH_RU = {1:"Янв",2:"Фев",3:"Мар",4:"Апр",5:"Май",6:"Июн",
            7:"Июл",8:"Авг",9:"Сен",10:"Окт",11:"Ноя",12:"Дек"}

SHOPS = {
    "Mlot_i_Klucz":   {
        "client_id":     os.environ.get("CLIENT_ID_MLOT",""),
        "client_secret": os.environ.get("CLIENT_SECRET_MLOT",""),
        "refresh_token": os.environ.get("REFRESH_TOKEN_MLOT",""),
        "secret_name":   "REFRESH_TOKEN_MLOT",
    },
    "PolaxEuroGroup": {
        "client_id":     os.environ.get("CLIENT_ID_POLAX",""),
        "client_secret": os.environ.get("CLIENT_SECRET_POLAX",""),
        "refresh_token": os.environ.get("REFRESH_TOKEN_POLAX",""),
        "secret_name":   "REFRESH_TOKEN_POLAX",
    },
    "Sila_Narzedzi":  {
        "client_id":     os.environ.get("CLIENT_ID_SILA",""),
        "client_secret": os.environ.get("CLIENT_SECRET_SILA",""),
        "refresh_token": os.environ.get("REFRESH_TOKEN_SILA",""),
        "secret_name":   "REFRESH_TOKEN_SILA",
    },
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
    "SUM":"IGNORE",
}

COST_CATS = ["commission","delivery","ads","subscription","discount"]

# ── eMAG ──────────────────────────────────────────────────────
EMAG_USERNAME = os.environ.get("EMAG_USERNAME", "")
EMAG_PASSWORD = os.environ.get("EMAG_PASSWORD", "")

EMAG_MARKETS = {
    "emag-ro": "https://marketplace-api.emag.ro/api-3",
    "emag-bg": "https://marketplace-api.emag.bg/api-3",
    "emag-hu": "https://marketplace-api.emag.hu/api-3",
}
EMAG_CURRENCY = {"emag-ro": "RON", "emag-bg": "BGN", "emag-hu": "HUF"}


def get_billing_cat(tid, tnam):
    if tid in BILLING_MAP:
        return BILLING_MAP[tid]
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


# ── AUTH & GITHUB ─────────────────────────────────────────────

def get_gh_pubkey():
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
        headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"})
    return r.json()


def save_token(secret_name, new_rt, pubkey):
    if not new_rt or not GH_TOKEN: return
    try:
        pk  = public.PublicKey(pubkey["key"].encode(), encoding.Base64Encoder())
        enc = base64.b64encode(public.SealedBox(pk).encrypt(new_rt.encode())).decode()
        resp = requests.put(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
            headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"},
            json={"encrypted_value":enc,"key_id":pubkey["key_id"]})
        if resp.status_code in (201, 204):
            print(f"  ✅ Токен {secret_name} сохранён")
        else:
            print(f"  ⚠ Токен {secret_name}: статус {resp.status_code}")
    except Exception as e:
        print(f"  ⚠ Ошибка токена {secret_name}: {e}")


def get_token(shop):
    r = requests.post(
        "https://allegro.pl/auth/oauth/token",
        auth=(shop["client_id"], shop["client_secret"]),
        data={"grant_type":"refresh_token",
              "refresh_token":shop["refresh_token"],
              "redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d:
        print(f"  ОШИБКА токена: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token","")


def hdrs(t):
    return {"Authorization":f"Bearer {t}","Accept":"application/vnd.allegro.public.v1+json"}


def get_tz(month):
    return 2 if 3 <= month <= 10 else 1


# ── НБП КУРСЫ ─────────────────────────────────────────────────

def get_nbp_rates():
    rates = {"CZK": 0.0, "HUF": 0.0, "EUR": 0.0, "RON": 0.0, "BGN": 0.0}
    try:
        resp = requests.get(
            "https://api.nbp.pl/api/exchangerates/tables/a/?format=json",
            timeout=15)
        if resp.status_code == 200:
            for r in resp.json()[0]["rates"]:
                if r["code"] in rates:
                    rates[r["code"]] = r["mid"]
            print(f"  НБП: CZK={rates['CZK']:.4f}  HUF={rates['HUF']:.6f}  EUR={rates['EUR']:.4f}  RON={rates['RON']:.4f}")
        else:
            print(f"  ⚠ НБП: HTTP {resp.status_code}")
    except Exception as e:
        print(f"  ⚠ НБП недоступен: {e}")
    # BGN нет в таблице A — отдельный запрос
    if rates["BGN"] == 0.0:
        try:
            r = requests.get("https://api.nbp.pl/api/exchangerates/rates/a/bgn/?format=json", timeout=10)
            if r.status_code == 200:
                rates["BGN"] = r.json()["rates"][0]["mid"]
        except Exception:
            pass
    print(f"  НБП BGN={rates['BGN']:.4f}")
    return rates


# ── eMAG ПРОДАЖИ ──────────────────────────────────────────────

def get_emag_day(date_str, nbp):
    """
    Собирает продажи eMAG за один день по всем 3 странам.
    Возвращает {"emag-ro": native, "emag-bg": native, "emag-hu": native, "EMAG": pln_total}
    """
    if not EMAG_USERNAME or not EMAG_PASSWORD:
        return {}
    from base64 import b64encode
    token = b64encode(f"{EMAG_USERNAME}:{EMAG_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
    fr = date_str + " 00:00:00"
    to = date_str + " 23:59:59"

    result = {}
    total_pln = 0.0
    for market_id, base_url in EMAG_MARKETS.items():
        market_total = 0.0
        page = 1
        while True:
            try:
                resp = requests.post(
                    f"{base_url}/order/read", headers=headers,
                    json={"currentPage": page, "itemsPerPage": 100,
                          "createdAfter": fr, "createdBefore": to, "status": 4},
                    timeout=20)
                orders = resp.json().get("results", [])
            except Exception as e:
                print(f"    ⚠ eMAG {market_id}: {e}")
                break
            if not isinstance(orders, list) or not orders:
                break
            for o in orders:
                try:
                    market_total += float(o.get("cashed_co") or 0) + float(o.get("cashed_cod") or 0)
                except Exception:
                    pass
            if len(orders) < 100:
                break
            page += 1
        result[market_id] = round(market_total, 2)
        cur = EMAG_CURRENCY[market_id]
        rate = nbp.get(cur, 0.0)
        total_pln += market_total * rate

    result["EMAG"] = round(total_pln, 2)
    print(f"    eMAG: RO={result['emag-ro']:.2f} BG={result['emag-bg']:.2f} "
          f"HU={result['emag-hu']:.0f} → {result['EMAG']:.2f} PLN")
    return result


# ── ПРОДАЖИ ───────────────────────────────────────────────────

def get_sales_for_day(token, date_str):
    dt     = datetime.strptime(date_str, "%Y-%m-%d")
    tz     = get_tz(dt.month)
    d_from = f"{date_str}T00:00:00+0{tz}:00"
    d_to   = f"{date_str}T23:59:59+0{tz}:00"
    by_mkt = defaultdict(float)

    for mkt in ["allegro-pl","allegro-business-pl","allegro-cz","allegro-hu","allegro-sk"]:
        offset = 0
        while True:
            resp = requests.get(
                "https://api.allegro.pl/payments/payment-operations",
                headers=hdrs(token),
                params={"group":"INCOME","occurredAt.gte":d_from,"occurredAt.lte":d_to,
                        "marketplaceId":mkt,"limit":50,"offset":offset})
            if resp.status_code != 200:
                print(f"    ⚠ payments {mkt}: HTTP {resp.status_code}")
                break
            ops = resp.json().get("paymentOperations",[])
            for op in ops:
                try: by_mkt[mkt] += float(op["value"]["amount"])
                except Exception: pass
            if len(ops) < 50: break
            offset += 50

    return {
        "allegro-pl": round(by_mkt["allegro-pl"] + by_mkt["allegro-business-pl"], 2),
        "allegro-cz": round(by_mkt["allegro-cz"], 2),
        "allegro-hu": round(by_mkt["allegro-hu"], 2),
        "allegro-sk": round(by_mkt["allegro-sk"], 2),
    }


# ── РАСХОДЫ ───────────────────────────────────────────────────

def get_billing_for_day(token, date_str, marketplace_id=None):
    dt     = datetime.strptime(date_str, "%Y-%m-%d")
    tz     = get_tz(dt.month)
    d_from = f"{date_str}T00:00:00+0{tz}:00"
    d_to   = f"{date_str}T23:59:59+0{tz}:00"
    costs  = {cat: 0.0 for cat in COST_CATS}
    offset = 0
    params = {"occurredAt.gte":d_from,"occurredAt.lte":d_to,"limit":100}
    if marketplace_id:
        params["marketplaceId"] = marketplace_id

    while True:
        params["offset"] = offset
        resp = requests.get(
            "https://api.allegro.pl/billing/billing-entries",
            headers=hdrs(token), params=params)
        if resp.status_code != 200:
            print(f"    ⚠ billing {marketplace_id or 'pl'}: HTTP {resp.status_code}")
            break
        entries = resp.json().get("billingEntries",[])
        for e in entries:
            try:
                amt  = float(e["value"]["amount"])
                cat  = get_billing_cat(e["type"]["id"], e["type"]["name"])
                if cat == "IGNORE": continue
                if cat == "other":
                    print(f"    ⚠ UNKNOWN: {e['type']['id']} '{e['type']['name']}' {amt:.2f}")
                    continue
                if amt < 0:
                    if cat in costs: costs[cat] += abs(amt)
                elif amt > 0:
                    if cat == "zwrot_commission": costs["commission"] = max(0.0, costs["commission"]-amt)
                    elif cat == "delivery":       costs["delivery"]   = max(0.0, costs["delivery"]-amt)
                    elif cat == "discount":       costs["discount"]  += amt
            except Exception: pass
        if len(entries) < 100: break
        offset += 100

    return {k: round(v, 2) for k, v in costs.items()}


# ══════════════════════════════════════════════════════════════
# ЮНИТ-ЭКОНОМИКА PER-OFFER (только польский рынок: PL + biz-PL)
# ══════════════════════════════════════════════════════════════
#   ads   = CPC / Sponsored Products (performance, оплата за клик)
#   promo = Wyróżnienie, Podświetlenie, Pogrubienie и др. (видимость)

UNIT_BILLING_MAP = {
    "SUC":"fees","SUJ":"fees","LDS":"fees","HUN":"fees",
    "REF":"zwrot_fees",
    "NSP":"ads","CPC":"ads",
    "WYR":"promo","POD":"promo","BOL":"promo",
    "DPG":"promo","EMF":"promo","FEA":"promo","BRG":"promo","FSF":"promo",
    "PAD":"IGNORE","SUM":"IGNORE","SB2":"IGNORE","ABN":"IGNORE",
    "RET":"IGNORE","PS1":"IGNORE",
    "HB4":"IGNORE","HB1":"IGNORE","HB8":"IGNORE","HB9":"IGNORE",
    "DPB":"IGNORE","DXP":"IGNORE","HXO":"IGNORE","HLB":"IGNORE",
    "ORB":"IGNORE","DHR":"IGNORE","DAP":"IGNORE","DKP":"IGNORE","DPP":"IGNORE",
    "GLS":"IGNORE","UPS":"IGNORE","UPD":"IGNORE","DTR":"IGNORE",
    "DPA":"IGNORE","ITR":"IGNORE","HLA":"IGNORE","DDP":"IGNORE",
    "HB3":"IGNORE","DPS":"IGNORE","UTR":"IGNORE",
}


def get_unit_bcat(tid, tname):
    if tid in UNIT_BILLING_MAP: return UNIT_BILLING_MAP[tid]
    n = tname.lower()
    if any(x in n for x in ["kampani","cpc","sponsored"]):               return "ads"
    if any(x in n for x in ["wyróżnienie","podświetlenie","pogrubienie",
                              "featured","branding","display"]):          return "promo"
    if any(x in n for x in ["prowizja","lokalna dopłata"]):               return "fees"
    if "zwrot prowizji" in n:                                              return "zwrot_fees"
    return "IGNORE"


_unit_nbp_cache = {}  # "YYYY-MM-DD:CUR" -> rate

def get_unit_nbp_rate(date_str, currency):
    """Historical NBP rate for CZK/HUF/EUR on a given date."""
    cur = currency.upper()
    if cur == "PLN":
        return 1.0
    key = f"{date_str}:{cur}"
    if key in _unit_nbp_cache:
        return _unit_nbp_cache[key]
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    for delta in range(0, 5):
        d = (dt - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            r = requests.get(
                f"https://api.nbp.pl/api/exchangerates/rates/a/{cur.lower()}/{d}/?format=json",
                timeout=10)
            if r.status_code == 200:
                rate = r.json()["rates"][0]["mid"]
                _unit_nbp_cache[key] = rate
                return rate
        except Exception:
            pass
    fallback = {"CZK": 0.16, "HUF": 0.01, "EUR": 4.25}
    rate = fallback.get(cur, 1.0)
    _unit_nbp_cache[key] = rate
    return rate


def get_unit_sales_by_offer(token, date_str):
    """checkout-forms (lineItems.boughtAt) → {offer_id: [qty, revenue_pln]}
    Includes all marketplaces (PL, CZ, HU, SK).
    Non-PLN prices converted to PLN via NBP historical rates."""
    result = defaultdict(lambda: [0, 0.0])
    offset = 0
    d_from = f"{date_str}T00:00:00.000Z"
    d_to   = f"{date_str}T23:59:59.999Z"
    while True:
        resp = requests.get(
            "https://api.allegro.pl/order/checkout-forms",
            headers=hdrs(token),
            params={"lineItems.boughtAt.gte":d_from,"lineItems.boughtAt.lte":d_to,
                    "limit":100,"offset":offset},
            timeout=30)
        if resp.status_code != 200: break
        forms = resp.json().get("checkoutForms", [])
        for form in forms:
            if form.get("status") == "CANCELLED": continue
            for item in form.get("lineItems", []):
                try:
                    oid      = item["offer"]["id"]
                    qty      = int(item.get("quantity", 1))
                    price    = float(item["price"]["amount"])
                    currency = item["price"].get("currency", "PLN").upper()
                    if currency != "PLN":
                        price = price * get_unit_nbp_rate(date_str, currency)
                    result[oid][0] += qty
                    result[oid][1] += qty * price
                except Exception: pass
        if len(forms) < 100: break
        offset += 100
        time.sleep(0.05)
    return {oid: [v[0], round(v[1], 2)] for oid, v in result.items()}


def get_unit_costs_by_offer(token, date_str):
    """billing-entries (no mktId → PL+biz) → {offer_id: [fees, ads, promo]}"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    tz = get_tz(dt.month)
    d_from = f"{date_str}T00:00:00+0{tz}:00"
    d_to   = f"{date_str}T23:59:59+0{tz}:00"
    result = defaultdict(lambda: [0.0, 0.0, 0.0])
    offset = 0
    while True:
        resp = requests.get(
            "https://api.allegro.pl/billing/billing-entries",
            headers=hdrs(token),
            params={"occurredAt.gte":d_from,"occurredAt.lte":d_to,
                    "limit":100,"offset":offset},
            timeout=30)
        if resp.status_code != 200: break
        entries = resp.json().get("billingEntries", [])
        for e in entries:
            oid = (e.get("offer") or {}).get("id")
            if not oid: continue
            cat = get_unit_bcat(e["type"]["id"], e.get("type", {}).get("name", ""))
            if cat == "IGNORE": continue
            try:
                amt = float(e["value"]["amount"])
                if cat == "fees"        and amt < 0: result[oid][0] += abs(amt)
                elif cat == "zwrot_fees" and amt > 0: result[oid][0] = max(0.0, result[oid][0]-amt)
                elif cat == "ads"       and amt < 0: result[oid][1] += abs(amt)
                elif cat == "promo"     and amt < 0: result[oid][2] += abs(amt)
            except Exception: pass
        if len(entries) < 100: break
        offset += 100
        time.sleep(0.05)
    return {oid: [round(v[0],2), round(v[1],2), round(v[2],2)] for oid, v in result.items()}


def load_unit_month(ym):
    os.makedirs("unit_data", exist_ok=True)
    try:
        with open(f"unit_data/{ym}.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"month": ym, "days": {}}


def save_unit_month(ym, data):
    with open(f"unit_data/{ym}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def collect_unit_day(access_tokens, date_str, partial=False):
    """
    Collect per-offer unit data for one day.
    Saves to unit_data/YYYY-MM.json. Reuses access_tokens (no new rotation).
    Data format: offer_id → [sales, revenue, fees, ads, promo]
    """
    ym = date_str[:7]
    md = load_unit_month(ym)
    md["days"].pop(date_str, None)   # remove existing (re-collect)

    day_entry = {}
    if partial:
        day_entry["_partial"] = True

    for shop_name, token in access_tokens.items():
        if not token: continue
        print(f"    [unit] {shop_name}...", end=" ", flush=True)

        sales     = get_unit_sales_by_offer(token, date_str)
        costs     = get_unit_costs_by_offer(token, date_str)
        shop_data = {}

        for oid in set(sales) | set(costs):
            s = sales.get(oid, [0, 0.0])
            c = costs.get(oid, [0.0, 0.0, 0.0])
            if s[1] == 0.0 and c == [0.0, 0.0, 0.0]: continue
            shop_data[oid] = [s[0], s[1], c[0], c[1], c[2]]

        day_entry[shop_name] = shop_data
        n   = len(shop_data)
        rev = sum(v[1] for v in shop_data.values())
        print(f"{n} офферов  rev={rev:,.0f} PLN")

    md["days"][date_str] = day_entry
    save_unit_month(ym, md)


# ── СБОР ДАННЫХ ЗА ОДИН ДЕНЬ ─────────────────────────────────

def collect_day(access_tokens, date_str, nbp, partial=False):
    """
    Собирает продажи и расходы за date_str по всем магазинам.
    access_tokens: {shop_name: token} — переиспользуем без ротации.
    Возвращает готовую запись для data.days.
    """
    entry = {
        "date":          date_str,
        "Mlot_i_Klucz":  0.0,
        "PolaxEuroGroup":0.0,
        "Sila_Narzedzi": 0.0,
        "EMAG":          0.0,
        "countries":     {"allegro-pl":0.0,"allegro-cz":0.0,"allegro-hu":0.0,"allegro-sk":0.0,
                          "emag-ro":0.0,"emag-bg":0.0,"emag-hu":0.0},
        "costs":         {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0},
        "shop_costs":    {
            "Mlot_i_Klucz":   {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0},
            "PolaxEuroGroup":  {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0},
            "Sila_Narzedzi":   {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0},
        },
    }
    if partial:
        entry["partial"] = True

    for shop_name, token in access_tokens.items():
        if not token:
            continue
        print(f"    {shop_name}...", end=" ", flush=True)

        # Продажи
        sales = get_sales_for_day(token, date_str)
        for mkt in ["allegro-pl","allegro-cz","allegro-hu","allegro-sk"]:
            entry["countries"][mkt] = round(entry["countries"][mkt] + sales.get(mkt, 0.0), 2)

        czk_pln = round(sales["allegro-cz"] * nbp["CZK"], 2)
        huf_pln = round(sales["allegro-hu"] * nbp["HUF"], 2)
        eur_pln = round(sales["allegro-sk"] * nbp["EUR"], 2)
        total   = round(sales["allegro-pl"] + czk_pln + huf_pln + eur_pln, 2)
        entry[shop_name] = round(entry[shop_name] + total, 2)

        # Расходы (все маркетплейсы → PLN)
        costs_pln = {cat: 0.0 for cat in COST_CATS}
        c_pl = get_billing_for_day(token, date_str, None)
        for cat in COST_CATS: costs_pln[cat] += c_pl.get(cat, 0.0)

        if nbp["CZK"] > 0:
            c_cz = get_billing_for_day(token, date_str, "allegro-cz")
            for cat in COST_CATS: costs_pln[cat] += c_cz.get(cat, 0.0) * nbp["CZK"]

        if nbp["HUF"] > 0:
            c_hu = get_billing_for_day(token, date_str, "allegro-hu")
            for cat in COST_CATS: costs_pln[cat] += c_hu.get(cat, 0.0) * nbp["HUF"]

        if nbp["EUR"] > 0:
            c_sk = get_billing_for_day(token, date_str, "allegro-sk")
            for cat in COST_CATS: costs_pln[cat] += c_sk.get(cat, 0.0) * nbp["EUR"]

        for cat in COST_CATS:
            entry["costs"][cat] = round(entry["costs"][cat] + costs_pln.get(cat, 0.0), 2)
            entry["shop_costs"][shop_name][cat] = round(costs_pln.get(cat, 0.0), 2)

        total_costs = sum(v for k,v in costs_pln.items() if k != "discount")
        print(f"PLN={total:,.2f}  costs={total_costs:,.2f}")

    # Финальное округление
    for mkt in entry["countries"]: entry["countries"][mkt] = round(entry["countries"][mkt], 2)
    for cat in entry["costs"]:     entry["costs"][cat]     = round(entry["costs"][cat], 2)
    for s in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi","EMAG"]: entry[s] = round(entry[s], 2)
    return entry


# ── DATA.JSON ─────────────────────────────────────────────────

def load_data():
    try:
        with open("data.json") as f: return json.load(f)
    except Exception: return {"days":[],"months":[]}


def save_data(data):
    with open("data.json","w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",",":"))


def update_months(data):
    def empty_costs():
        return {"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0}
    def empty_shop_costs():
        return {"Mlot_i_Klucz":empty_costs(),"PolaxEuroGroup":empty_costs(),"Sila_Narzedzi":empty_costs()}
    months_map = defaultdict(lambda:{
        "Mlot_i_Klucz":0,"PolaxEuroGroup":0,"Sila_Narzedzi":0,"EMAG":0,
        "countries":{"allegro-pl":0,"allegro-cz":0,"allegro-hu":0,"allegro-sk":0,
                     "emag-ro":0,"emag-bg":0,"emag-hu":0},
        "costs":empty_costs(),
        "shop_costs":empty_shop_costs(),
    })
    for day in data["days"]:
        raw = day["date"][:7]
        y, mo = int(raw[:4]), int(raw[5:7])
        mk = MONTH_RU[mo] + " " + str(y)
        for shop in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi","EMAG"]:
            months_map[mk][shop] = round(months_map[mk][shop] + day.get(shop, 0), 2)
        for c in ["allegro-pl","allegro-cz","allegro-hu","allegro-sk",
                  "emag-ro","emag-bg","emag-hu"]:
            months_map[mk]["countries"][c] = round(
                months_map[mk]["countries"][c] + day.get("countries",{}).get(c, 0), 2)
        for cat in COST_CATS:
            months_map[mk]["costs"][cat] = round(
                months_map[mk]["costs"][cat] + day.get("costs",{}).get(cat, 0), 2)
        for shop in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi"]:
            sc = day.get("shop_costs", {}).get(shop, {})
            for cat in COST_CATS:
                months_map[mk]["shop_costs"][shop][cat] = round(
                    months_map[mk]["shop_costs"][shop][cat] + sc.get(cat, 0), 2)
    MONTH_RU_REV = {v:k for k,v in MONTH_RU.items()}
    data["months"] = [
        {"month":k,**v}
        for k,v in sorted(
            months_map.items(),
            key=lambda x: (int(x[0][-4:]), MONTH_RU_REV[x[0][:3]])
        )
    ]


# ── MAIN ──────────────────────────────────────────────────────

now       = datetime.now(timezone.utc)
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
today_str = now.strftime("%Y-%m-%d")

print(f"Вчера:   {yesterday}")
print(f"Сегодня: {today_str}")

data        = load_data()
existing    = {d["date"]: d for d in data["days"]}

# Нужно ли собирать вчера?
# Пропускаем только если вчера уже есть как ПОЛНАЯ (не partial) запись
collect_yesterday = not (
    yesterday in existing and not existing[yesterday].get("partial", False)
)

if not collect_yesterday:
    print(f"\n{yesterday} уже есть (полный) — пропускаем вчера")

print("\n── НБП курсы ────────────────────────────────────────────")
nbp    = get_nbp_rates()
pubkey = get_gh_pubkey()

# ── ШАГ 1: Получаем токены (один раз на все операции) ─────────
print("\n── Авторизация ──────────────────────────────────────────")
access_tokens = {}  # {shop_name: access_token}

for shop_name, shop in SHOPS.items():
    token, new_rt = get_token(shop)
    if not token:
        print(f"  ❌ {shop_name}: токен не получен")
        continue
    save_token(shop["secret_name"], new_rt, pubkey)
    access_tokens[shop_name] = token

# ── ШАГ 2: Вчера (complete) ────────────────────────────────────
if collect_yesterday and access_tokens:
    print(f"\n── Вчера: {yesterday} ───────────────────────────────────")
    if yesterday in existing and existing[yesterday].get("partial", False):
        print(f"  Была partial-запись — перезаписываем")
    # Удаляем существующую запись за вчера (если была partial)
    data["days"] = [d for d in data["days"] if d["date"] != yesterday]

    yest_entry = collect_day(access_tokens, yesterday, nbp, partial=False)
    data["days"].append(yest_entry)

    total_yest = yest_entry["Mlot_i_Klucz"]+yest_entry["PolaxEuroGroup"]+yest_entry["Sila_Narzedzi"]
    print(f"  ✅ {yesterday}: {total_yest:,.2f} PLN")

# ── ШАГ 3: Сегодня (partial) ─────────────────────────────────
# Переиспользуем те же access_tokens — ротация уже прошла на шаге 1
if access_tokens:
    print(f"\n── Сегодня: {today_str} (partial) ───────────────────────")
    # Всегда перезаписываем сегодняшнюю partial-запись свежими данными
    data["days"] = [d for d in data["days"] if d["date"] != today_str]

    today_entry = collect_day(access_tokens, today_str, nbp, partial=True)
    data["days"].append(today_entry)

    total_today = today_entry["Mlot_i_Klucz"]+today_entry["PolaxEuroGroup"]+today_entry["Sila_Narzedzi"]
    print(f"  ✅ {today_str}: {total_today:,.2f} PLN (неполный день)")

# ── СОХРАНЯЕМ ─────────────────────────────────────────────────
data["days"].sort(key=lambda x: x["date"])
update_months(data)
save_data(data)

cur_month_key = MONTH_RU[now.month] + " " + str(now.year)
cur_month = next((m for m in data["months"] if m["month"] == cur_month_key), None)
if cur_month:
    cur_total = (cur_month.get("Mlot_i_Klucz",0)
                +cur_month.get("PolaxEuroGroup",0)
                +cur_month.get("Sila_Narzedzi",0)
                +cur_month.get("EMAG",0))
    print(f"\n📊 {cur_month_key} — текущий итог: {cur_total:,.2f} PLN  "
          f"(цель 200 000, выполнено {cur_total/200000*100:.1f}%)")

print(f"\n✅ Готово. Дней в data.json: {len(data['days'])}")

# ── ШАГ 4: Юнит-экономика — вчера (complete) ─────────────────
if access_tokens and collect_yesterday:
    print(f"\n── Юнит-экономика: {yesterday} ─────────────────────────")
    collect_unit_day(access_tokens, yesterday, partial=False)
    print(f"  ✅ unit {yesterday} сохранён")

# ── ШАГ 5: Юнит-экономика — сегодня (partial) ────────────────
if access_tokens:
    print(f"\n── Юнит-экономика: {today_str} (partial) ───────────────")
    collect_unit_day(access_tokens, today_str, partial=True)
    print(f"  ✅ unit {today_str} (partial) сохранён")

print(f"\n✅ Всё готово.")
