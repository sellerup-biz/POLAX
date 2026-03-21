"""
POLAX — Сбор исторических данных юнит-экономики по офферам

Что делает:
  • Для каждого дня в диапазоне UNIT_FROM..UNIT_TO (только польский рынок):
      – /payments/payment-operations  → revenue + кол-во транзакций по offer.id
      – /billing/billing-entries      → fees + ads + promo по offer.id
  • Записывает unit_data/YYYY-MM.json для каждого месяца
  • Хранит ВСЕ офферы с активностью (не только из products.json)

Запуск:
  python fetch_unit_history.py               (локально, .env)
  unit_history.yml → workflow_dispatch       (GitHub Actions)

Env:
  UNIT_FROM = 2026-01-01
  UNIT_TO   = 2026-03-20
  CLIENT_ID_*  /  CLIENT_SECRET_*  /  REFRESH_TOKEN_*  (x3)
  GH_TOKEN

unit_data/YYYY-MM.json  — структура:
{
  "month": "2026-03",
  "days": {
    "2026-03-01": {
      "Mlot_i_Klucz": {
        "12348901": [sales, revenue, fees, ads, promo]
      },
      ...
    }
  }
}
Индексы: 0=sales(кол-во транзакций), 1=revenue(PLN), 2=fees, 3=ads(CPC), 4=promo
"""

import requests, json, os, base64, calendar, time
from datetime import datetime, timedelta, date
from collections import defaultdict
from nacl import encoding, public

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Env ───────────────────────────────────────────────────────
REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"
UNIT_FROM    = os.environ.get("UNIT_FROM", "2026-01-01")
UNIT_TO      = os.environ.get("UNIT_TO",   "2026-03-20")

SHOPS = {
    "Mlot_i_Klucz": {
        "client_id":     os.environ.get("CLIENT_ID_MLOT", ""),
        "client_secret": os.environ.get("CLIENT_SECRET_MLOT", ""),
        "refresh_token": os.environ.get("REFRESH_TOKEN_MLOT", ""),
        "secret_name":   "REFRESH_TOKEN_MLOT",
    },
    "PolaxEuroGroup": {
        "client_id":     os.environ.get("CLIENT_ID_POLAX", ""),
        "client_secret": os.environ.get("CLIENT_SECRET_POLAX", ""),
        "refresh_token": os.environ.get("REFRESH_TOKEN_POLAX", ""),
        "secret_name":   "REFRESH_TOKEN_POLAX",
    },
    "Sila_Narzedzi": {
        "client_id":     os.environ.get("CLIENT_ID_SILA", ""),
        "client_secret": os.environ.get("CLIENT_SECRET_SILA", ""),
        "refresh_token": os.environ.get("REFRESH_TOKEN_SILA", ""),
        "secret_name":   "REFRESH_TOKEN_SILA",
    },
}

# ── Billing map for unit economics (PL market only) ───────────
# Two types of ad spend:
#   ads   = CPC performance ads (cost per click / sponsored products)
#   promo = offer visibility promotions (wyróżnienie, podświetlenie, etc.)
UNIT_BILLING_MAP = {
    # Комиссия → fees
    "SUC": "fees",   "SUJ": "fees",   "LDS": "fees",   "HUN": "fees",
    "REF": "zwrot_fees",
    # CPC реклама → ads
    "NSP": "ads",    "CPC": "ads",
    # Промование листинга → promo
    "WYR": "promo",  "POD": "promo",  "BOL": "promo",
    "DPG": "promo",  "EMF": "promo",  "FEA": "promo",
    "BRG": "promo",  "FSF": "promo",
    # Игнорируем
    "PAD": "IGNORE", "SUM": "IGNORE",
    "SB2": "IGNORE", "ABN": "IGNORE",
    "RET": "IGNORE", "PS1": "IGNORE",
    # Доставка — не в юнит-экономике
    "HB4":"IGNORE","HB1":"IGNORE","HB8":"IGNORE","HB9":"IGNORE",
    "DPB":"IGNORE","DXP":"IGNORE","HXO":"IGNORE","HLB":"IGNORE",
    "ORB":"IGNORE","DHR":"IGNORE","DAP":"IGNORE","DKP":"IGNORE","DPP":"IGNORE",
    "GLS":"IGNORE","UPS":"IGNORE","UPD":"IGNORE","DTR":"IGNORE",
    "DPA":"IGNORE","ITR":"IGNORE","HLA":"IGNORE","DDP":"IGNORE",
    "HB3":"IGNORE","DPS":"IGNORE","UTR":"IGNORE",
}


def get_unit_billing_cat(tid, tname):
    if tid in UNIT_BILLING_MAP:
        return UNIT_BILLING_MAP[tid]
    n = tname.lower()
    if any(x in n for x in ["kampani", "cpc", "sponsored", "promowanie wyniki"]):
        return "ads"
    if any(x in n for x in ["wyróżnienie", "podświetlenie", "pogrubienie", "strona działu",
                              "featured", "branding", "display"]):
        return "promo"
    if any(x in n for x in ["prowizja", "lokalna dopłata", "opłata transakcyjna"]):
        return "fees"
    if "zwrot prowizji" in n:
        return "zwrot_fees"
    return "IGNORE"


# ── Auth & helpers ────────────────────────────────────────────

def get_gh_pubkey():
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
        headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"})
    return r.json() if r.status_code == 200 else {}


def save_token(secret_name, new_rt, pubkey):
    if not new_rt or not GH_TOKEN or not pubkey.get("key"):
        return
    try:
        pk  = public.PublicKey(pubkey["key"].encode(), encoding.Base64Encoder())
        enc = base64.b64encode(public.SealedBox(pk).encrypt(new_rt.encode())).decode()
        resp = requests.put(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
            headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
            json={"encrypted_value": enc, "key_id": pubkey["key_id"]})
        status = "✅" if resp.status_code in (201, 204) else f"⚠ HTTP {resp.status_code}"
        print(f"    {status} Токен {secret_name}")
    except Exception as e:
        print(f"    ⚠ save_token: {e}")


def get_token(shop):
    r = requests.post(
        "https://allegro.pl/auth/oauth/token",
        auth=(shop["client_id"], shop["client_secret"]),
        data={"grant_type": "refresh_token", "refresh_token": shop["refresh_token"],
              "redirect_uri": REDIRECT_URI},
        timeout=30)
    d = r.json()
    if "access_token" not in d:
        print(f"    ❌ ОШИБКА токена: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token", "")


def hdrs(token):
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.allegro.public.v1+json"}


def get_tz(month):
    """Warsaw timezone offset: +2 summer (Mar-Oct), +1 winter."""
    return 2 if 3 <= month <= 10 else 1


def day_range(date_str):
    """Return (gte, lte) timestamps for full day in Warsaw time."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    tz = get_tz(dt.month)
    return (f"{date_str}T00:00:00+0{tz}:00",
            f"{date_str}T23:59:59+0{tz}:00")


# ── API calls ─────────────────────────────────────────────────

def get_sales_by_offer(token, date_str):
    """
    GET /payments/payment-operations (allegro-pl, one day)
    Returns: {offer_id: [sales_count, revenue_pln]}

    Note: sales_count = number of payment operations (≈ order line count).
    Revenue includes allegro-pl + allegro-business-pl (business ops appear on
    allegro-pl marketplace query because they share the PLN settlement).
    """
    d_from, d_to = day_range(date_str)
    by_offer = defaultdict(lambda: [0, 0.0])
    offset   = 0

    while True:
        resp = requests.get(
            "https://api.allegro.pl/payments/payment-operations",
            headers=hdrs(token),
            params={
                "group":           "INCOME",
                "occurredAt.gte":  d_from,
                "occurredAt.lte":  d_to,
                "marketplaceId":   "allegro-pl",  # includes business-pl
                "limit":           50,
                "offset":          offset,
            },
            timeout=30)

        if resp.status_code != 200:
            print(f"\n  ⚠ payment-operations {date_str}: HTTP {resp.status_code}")
            break

        ops = resp.json().get("paymentOperations", [])
        for op in ops:
            try:
                oid = op.get("offer", {}).get("id")
                if not oid:
                    continue
                amt = float(op["value"]["amount"])
                by_offer[oid][0] += 1      # count (transactions)
                by_offer[oid][1] += amt    # revenue (may be negative = refund)
            except Exception:
                pass

        if len(ops) < 50:
            break
        offset += 50
        time.sleep(0.05)

    # Round revenue
    return {oid: [v[0], round(v[1], 2)] for oid, v in by_offer.items()}


def get_costs_by_offer(token, date_str):
    """
    GET /billing/billing-entries (no marketplaceId → PL + business-PL)
    Returns: {offer_id: [fees, ads, promo]}
    Entries without offer.id are skipped (account-level costs).
    """
    d_from, d_to = day_range(date_str)
    by_offer = defaultdict(lambda: [0.0, 0.0, 0.0])  # [fees, ads, promo]
    offset   = 0

    while True:
        resp = requests.get(
            "https://api.allegro.pl/billing/billing-entries",
            headers=hdrs(token),
            params={
                "occurredAt.gte": d_from,
                "occurredAt.lte": d_to,
                "limit":          100,
                "offset":         offset,
            },
            timeout=30)

        if resp.status_code != 200:
            print(f"\n  ⚠ billing-entries {date_str}: HTTP {resp.status_code}")
            break

        entries = resp.json().get("billingEntries", [])
        for e in entries:
            try:
                oid = (e.get("offer") or {}).get("id")
                if not oid:
                    continue   # account-level entry

                cat = get_unit_billing_cat(
                    e["type"]["id"], e.get("type", {}).get("name", ""))
                if cat == "IGNORE":
                    continue

                amt = float(e["value"]["amount"])

                if cat == "fees":
                    if amt < 0:
                        by_offer[oid][0] += abs(amt)
                elif cat == "zwrot_fees":
                    if amt > 0:
                        by_offer[oid][0] = max(0.0, by_offer[oid][0] - amt)
                elif cat == "ads":
                    if amt < 0:
                        by_offer[oid][1] += abs(amt)
                elif cat == "promo":
                    if amt < 0:
                        by_offer[oid][2] += abs(amt)

            except Exception:
                pass

        if len(entries) < 100:
            break
        offset += 100
        time.sleep(0.05)

    return {oid: [round(v[0], 2), round(v[1], 2), round(v[2], 2)]
            for oid, v in by_offer.items()}


# ── unit_data I/O ─────────────────────────────────────────────

def load_month_data(ym):
    """Load unit_data/YYYY-MM.json or return empty structure."""
    os.makedirs("unit_data", exist_ok=True)
    path = f"unit_data/{ym}.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"month": ym, "days": {}}


def save_month_data(ym, data):
    path = f"unit_data/{ym}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


# ── Per-day collection ────────────────────────────────────────

def collect_unit_day(access_tokens, date_str, month_cache, partial=False):
    """
    Collect per-offer unit data for one day.
    Merges results into month_cache[month_str]["days"][date_str].
    month_cache: {ym_str: month_data_dict}  — in-memory, saved later.
    """
    ym = date_str[:7]
    if ym not in month_cache:
        month_cache[ym] = load_month_data(ym)

    md = month_cache[ym]

    # Remove existing entry for this date (re-collect)
    if date_str in md["days"]:
        del md["days"][date_str]

    day_entry = {}
    if partial:
        day_entry["_partial"] = True

    for shop_name, token in access_tokens.items():
        if not token:
            continue

        print(f"    {shop_name}...", end=" ", flush=True)
        sales  = get_sales_by_offer(token, date_str)
        costs  = get_costs_by_offer(token, date_str)

        # Merge into shop dict: offer_id → [sales, revenue, fees, ads, promo]
        all_offers = set(sales) | set(costs)
        shop_data  = {}

        for oid in all_offers:
            s = sales.get(oid, [0, 0.0])
            c = costs.get(oid, [0.0, 0.0, 0.0])
            rev = s[1]
            if rev == 0.0 and all(x == 0.0 for x in c):
                continue   # skip empty entries
            shop_data[oid] = [s[0], s[1], c[0], c[1], c[2]]

        day_entry[shop_name] = shop_data
        n_offers  = len(shop_data)
        total_rev = sum(v[1] for v in shop_data.values())
        print(f"{n_offers} офферов  rev={total_rev:,.0f} PLN")
        time.sleep(0.1)

    md["days"][date_str] = day_entry


# ── Date range helpers ────────────────────────────────────────

def dates_in_range(from_str, to_str):
    """Yield 'YYYY-MM-DD' strings for each day from from_str to to_str inclusive."""
    d = datetime.strptime(from_str, "%Y-%m-%d").date()
    e = datetime.strptime(to_str,   "%Y-%m-%d").date()
    while d <= e:
        yield d.strftime("%Y-%m-%d")
        d += timedelta(days=1)


def months_in_range(from_str, to_str):
    """Yield 'YYYY-MM' strings for each calendar month in range."""
    seen = set()
    for ds in dates_in_range(from_str, to_str):
        ym = ds[:7]
        if ym not in seen:
            seen.add(ym)
            yield ym


# ── MAIN ──────────────────────────────────────────────────────

print("=" * 65)
print("  POLAX — История юнит-экономики по офферам")
print(f"  Период: {UNIT_FROM} → {UNIT_TO}")
print("=" * 65)

# Count days
all_dates = list(dates_in_range(UNIT_FROM, UNIT_TO))
print(f"  Дней для сбора: {len(all_dates)}")

# Auth
print("\n── Авторизация ──────────────────────────────────────────")
pubkey        = get_gh_pubkey()
access_tokens = {}

for shop_name, shop in SHOPS.items():
    token, new_rt = get_token(shop)
    if not token:
        print(f"  ❌ {shop_name}: токен не получен")
        continue
    save_token(shop["secret_name"], new_rt, pubkey)
    access_tokens[shop_name] = token
    print(f"  ✅ {shop_name}")

if not access_tokens:
    print("❌ Нет активных токенов. Выход.")
    exit(1)

# Collect day by day
month_cache = {}   # ym → month_data (in memory, flush per month)
current_ym  = None
processed   = 0
today_str   = datetime.utcnow().strftime("%Y-%m-%d")

print(f"\n── Сбор данных ──────────────────────────────────────────")

for date_str in all_dates:
    ym = date_str[:7]

    # New month — save previous
    if current_ym and ym != current_ym and current_ym in month_cache:
        save_month_data(current_ym, month_cache[current_ym])
        n_days = len(month_cache[current_ym]["days"])
        print(f"  💾 {current_ym}.json сохранён ({n_days} дней)")

    current_ym = ym
    partial    = (date_str == today_str)

    print(f"\n  {date_str}{' (partial)' if partial else ''}:")
    collect_unit_day(access_tokens, date_str, month_cache, partial=partial)
    processed += 1

# Save last month
if current_ym and current_ym in month_cache:
    save_month_data(current_ym, month_cache[current_ym])
    n_days = len(month_cache[current_ym]["days"])
    print(f"\n  💾 {current_ym}.json сохранён ({n_days} дней)")

# Summary
print(f"\n── Итог ────────────────────────────────────────────────")
print(f"  Обработано дней: {processed}")
for ym in sorted(month_cache.keys()):
    n = len(month_cache[ym]["days"])
    print(f"  {ym}: {n} дней")

print("\n✅ Готово.")
