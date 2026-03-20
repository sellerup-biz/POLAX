"""
POLAX — ТЕСТ РАСХОДОВ: Янв / Фев / Мар 2026
Только чтение данных из API. data.json НЕ изменяется.
Запуск: test_costs.yml (workflow_dispatch) на GitHub Actions.

Запрашивает биллинг по каждому маркетплейсу отдельно:
  • allegro-pl        → PLN (без marketplaceId, включает business-pl)
  • allegro-cz        → CZK (с marketplaceId=allegro-cz)
  • allegro-hu        → HUF (с marketplaceId=allegro-hu)
  • allegro-sk        → EUR (с marketplaceId=allegro-sk)

Выводит:
  • расходы по каждому магазину × месяцу в каждой валюте
  • неизвестные type.id для пополнения BILLING_MAP
  • сводную таблицу по всем магазинам
"""
import requests, os, base64, calendar
from nacl import encoding, public
from collections import defaultdict

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

MONTHS_TO_CHECK = [
    (2026, 1, "Янв 2026"),
    (2026, 2, "Фев 2026"),
    (2026, 3, "Мар 2026"),
]

# PL: без marketplaceId (включает business автоматически)
# CZ/HU/SK: с marketplaceId → возвращает расходы в локальной валюте
BILLING_MARKETS = [
    ("pl",  None,            "PLN"),
    ("cz",  "allegro-cz",   "CZK"),
    ("hu",  "allegro-hu",   "HUF"),
    ("sk",  "allegro-sk",   "EUR"),
]

SHOPS = {
    "Mlot_i_Klucz":   {
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
    "Sila_Narzedzi":  {
        "client_id":     os.environ.get("CLIENT_ID_SILA", ""),
        "client_secret": os.environ.get("CLIENT_SECRET_SILA", ""),
        "refresh_token": os.environ.get("REFRESH_TOKEN_SILA", ""),
        "secret_name":   "REFRESH_TOKEN_SILA",
    },
}

BILLING_MAP = {
    "SUC": "commission", "SUJ": "commission", "LDS": "commission", "HUN": "commission",
    "REF": "zwrot_commission",
    "HB4": "delivery", "HB1": "delivery", "HB8": "delivery", "HB9": "delivery",
    "DPB": "delivery", "DXP": "delivery", "HXO": "delivery", "HLB": "delivery",
    "ORB": "delivery", "DHR": "delivery", "DAP": "delivery", "DKP": "delivery", "DPP": "delivery",
    "GLS": "delivery", "UPS": "delivery", "UPD": "delivery",
    "DTR": "delivery", "DPA": "delivery", "ITR": "delivery", "HLA": "delivery",
    "DDP": "delivery", "HB3": "delivery", "DPS": "delivery", "UTR": "delivery",
    "NSP": "ads", "DPG": "ads", "WYR": "ads", "POD": "ads", "BOL": "ads", "EMF": "ads",
    "CPC": "ads", "FEA": "ads", "BRG": "ads", "FSF": "ads",
    "SB2": "subscription", "ABN": "subscription",
    "RET": "discount", "PS1": "discount",
    "PAD": "IGNORE",
    "SUM": "IGNORE",   # Podsumowanie miesiąca — всегда 0.00, просто итоговая запись
}

COST_CATS = ["commission", "delivery", "ads", "subscription", "discount"]


def get_billing_cat(tid, tnam):
    if tid in BILLING_MAP:
        return BILLING_MAP[tid]
    n = tnam.lower()
    if "kampanii" in n or "kampania" in n:
        return "ads"
    if any(x in n for x in ["prowizja", "lokalna dopłata", "opłata transakcyjna"]):
        return "commission"
    if any(x in n for x in ["dostawa", "kurier", "inpost", "dpd", "gls", "ups", "orlen",
                              "poczta", "przesyłka", "fulfillment", "one kurier",
                              "allegro delivery", "packeta", "international",
                              "dodatkowa za dostawę"]):
        return "delivery"
    if any(x in n for x in ["kampani", "reklam", "promowanie", "wyróżnienie", "pogrubienie",
                              "podświetlenie", "strona działu", "pakiet promo", "cpc", "ads"]):
        return "ads"
    if any(x in n for x in ["abonament", "smart"]):
        return "subscription"
    if any(x in n for x in ["rozliczenie akcji", "wyrównanie w programie allegro", "rabat"]):
        return "discount"
    if any(x in n for x in ["zwrot kosztów", "zwrot prowizji"]):
        return "zwrot_commission"
    if "pobranie opłat z wpływów" in n:
        return "IGNORE"
    return "other"


# ── helpers ───────────────────────────────────────────────────

def get_gh_pubkey():
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
        headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
    )
    return r.json()


def save_token(secret_name, new_rt, pubkey):
    if not new_rt or not GH_TOKEN:
        return
    try:
        pk  = public.PublicKey(pubkey["key"].encode(), encoding.Base64Encoder())
        enc = base64.b64encode(public.SealedBox(pk).encrypt(new_rt.encode())).decode()
        resp = requests.put(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
            headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
            json={"encrypted_value": enc, "key_id": pubkey["key_id"]},
        )
        if resp.status_code in (201, 204):
            print(f"    ✅ Токен {secret_name} сохранён")
        else:
            print(f"    ⚠ Токен {secret_name}: статус {resp.status_code}")
    except Exception as e:
        print(f"    ⚠ Ошибка сохранения токена {secret_name}: {e}")


def get_token(shop):
    r = requests.post(
        "https://allegro.pl/auth/oauth/token",
        auth=(shop["client_id"], shop["client_secret"]),
        data={
            "grant_type":    "refresh_token",
            "refresh_token": shop["refresh_token"],
            "redirect_uri":  REDIRECT_URI,
        },
    )
    d = r.json()
    if "access_token" not in d:
        print(f"    ОШИБКА получения токена: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token", "")


def hdrs(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.allegro.public.v1+json",
    }


def get_tz(month):
    return 2 if 3 <= month <= 10 else 1


def fetch_billing(token, year, month, marketplace_id=None):
    """
    Запрашивает /billing/billing-entries.
    marketplace_id=None  → allegro-pl (без фильтра, включает business)
    marketplace_id=str   → конкретный рынок в его валюте
    Возвращает (costs, unknowns, pad_total, raw_count).
    """
    last_day  = calendar.monthrange(year, month)[1]
    tz        = get_tz(month)
    date_from = f"{year}-{month:02d}-01T00:00:00+0{tz}:00"
    date_to   = f"{year}-{month:02d}-{last_day:02d}T23:59:59+0{tz}:00"

    costs     = {cat: 0.0 for cat in COST_CATS}
    unknowns  = []
    pad_total = 0.0
    raw_count = 0
    offset    = 0

    params = {
        "occurredAt.gte": date_from,
        "occurredAt.lte": date_to,
        "limit":          100,
        "offset":         offset,
    }
    if marketplace_id:
        params["marketplaceId"] = marketplace_id

    while True:
        params["offset"] = offset
        resp = requests.get(
            "https://api.allegro.pl/billing/billing-entries",
            headers=hdrs(token),
            params=params,
        )
        if resp.status_code != 200:
            print(f"      ⚠ Billing HTTP {resp.status_code} ({marketplace_id or 'pl'}): {resp.text[:200]}")
            break

        entries = resp.json().get("billingEntries", [])
        raw_count += len(entries)

        for e in entries:
            try:
                amt  = float(e["value"]["amount"])
                tid  = e["type"]["id"]
                tnam = e["type"]["name"]
                cat  = get_billing_cat(tid, tnam)

                if cat == "IGNORE":
                    pad_total += abs(amt)
                    continue
                if cat == "other":
                    unknowns.append({"id": tid, "name": tnam, "amount": amt})
                    continue

                if amt < 0:
                    if cat in costs:
                        costs[cat] += abs(amt)
                elif amt > 0:
                    if cat == "zwrot_commission":
                        costs["commission"] = max(0.0, costs["commission"] - amt)
                    elif cat == "delivery":
                        costs["delivery"]   = max(0.0, costs["delivery"] - amt)
                    elif cat == "discount":
                        costs["discount"]  += amt
            except Exception as ex:
                print(f"      ⚠ Ошибка записи: {ex}")

        if len(entries) < 100:
            break
        offset += 100

    return (
        {k: round(v, 2) for k, v in costs.items()},
        unknowns,
        round(pad_total, 2),
        raw_count,
    )


def print_costs(costs, currency, raw_count, pad_total, unknowns, indent="    "):
    net = sum(costs.values()) - costs["discount"]
    print(f"{indent}Записей: {raw_count}  |  PAD/SUM ignored: {pad_total:,.2f} {currency}")
    print(f"{indent}commission:   {costs['commission']:>10,.2f} {currency}")
    print(f"{indent}delivery:     {costs['delivery']:>10,.2f} {currency}")
    print(f"{indent}ads:          {costs['ads']:>10,.2f} {currency}")
    print(f"{indent}subscription: {costs['subscription']:>10,.2f} {currency}")
    print(f"{indent}discount:     {costs['discount']:>10,.2f} {currency}")
    print(f"{indent}{'─'*42}")
    print(f"{indent}НЕТТО:        {net:>10,.2f} {currency}")
    if unknowns:
        seen = {}
        for u in unknowns:
            k = u["id"]
            if k not in seen:
                seen[k] = {"name": u["name"], "count": 0, "total": 0.0}
            seen[k]["count"] += 1
            seen[k]["total"] += u["amount"]
        print(f"{indent}⚠ UNKNOWN type.id:")
        for tid, info in sorted(seen.items()):
            print(f"{indent}  {tid:<8} {info['name']:<40} {info['count']} записей  {info['total']:,.2f} {currency}")


# ── MAIN ──────────────────────────────────────────────────────

print("=" * 72)
print("  POLAX — ТЕСТ РАСХОДОВ (мультивалюта): Янв / Фев / Мар 2026")
print("  data.json НЕ изменяется")
print("=" * 72)

pubkey = get_gh_pubkey()

# all_costs[shop][label][currency_code] = costs dict
all_costs   = defaultdict(lambda: defaultdict(dict))
all_unknown = []   # для итогового раздела

for shop_name, shop in SHOPS.items():
    print(f"\n{'━' * 68}")
    print(f"  МАГАЗИН: {shop_name}")
    print(f"{'━' * 68}")

    token, new_rt = get_token(shop)
    if not token:
        print("  ❌ Не удалось получить токен — пропускаем")
        continue
    save_token(shop["secret_name"], new_rt, pubkey)

    for year, month, label in MONTHS_TO_CHECK:
        print(f"\n  ── {label} ──")

        for mkt_key, mkt_id, currency in BILLING_MARKETS:
            costs, unknowns, pad_total, raw_count = fetch_billing(token, year, month, mkt_id)
            all_costs[shop_name][label][currency] = costs
            for u in unknowns:
                all_unknown.append({**u, "shop": shop_name, "month": label, "currency": currency})

            label_str = f"allegro-{mkt_key}" if mkt_id else "allegro-pl (+ business)"
            print(f"\n    [{currency}] {label_str}")
            print_costs(costs, currency, raw_count, pad_total, unknowns)


# ── СВОДНАЯ ТАБЛИЦА ───────────────────────────────────────────

print(f"\n\n{'=' * 72}")
print(f"  СВОДНАЯ ТАБЛИЦА — все магазины суммированы по месяцам")
print(f"{'=' * 72}")

for year, month, label in MONTHS_TO_CHECK:
    print(f"\n  {label}")
    for mkt_key, mkt_id, currency in BILLING_MARKETS:
        totals = {cat: 0.0 for cat in COST_CATS}
        for shop_name in SHOPS:
            c = all_costs[shop_name][label].get(currency, {})
            for cat in COST_CATS:
                totals[cat] += c.get(cat, 0.0)
        net = sum(totals.values()) - totals["discount"]
        print(f"    {currency}:  "
              f"commission {totals['commission']:>9,.2f}  "
              f"delivery {totals['delivery']:>9,.2f}  "
              f"ads {totals['ads']:>9,.2f}  "
              f"subscr {totals['subscription']:>7,.2f}  "
              f"discount {totals['discount']:>7,.2f}  "
              f"→ нетто {net:>9,.2f}")

# ── ИТОГ ЗА 3 МЕСЯЦА ─────────────────────────────────────────

print(f"\n{'─' * 72}")
print(f"  ИТОГО ЗА 3 МЕСЯЦА (все магазины + все месяцы)")
print(f"{'─' * 72}")

for mkt_key, mkt_id, currency in BILLING_MARKETS:
    grand = {cat: 0.0 for cat in COST_CATS}
    for shop_name in SHOPS:
        for _, _, label in MONTHS_TO_CHECK:
            c = all_costs[shop_name][label].get(currency, {})
            for cat in COST_CATS:
                grand[cat] += c.get(cat, 0.0)
    net = sum(grand.values()) - grand["discount"]
    print(f"  {currency}:  "
          f"commission {grand['commission']:>9,.2f}  "
          f"delivery {grand['delivery']:>9,.2f}  "
          f"ads {grand['ads']:>9,.2f}  "
          f"subscr {grand['subscription']:>7,.2f}  "
          f"discount {grand['discount']:>7,.2f}  "
          f"→ нетто {net:>9,.2f}")

# ── НЕИЗВЕСТНЫЕ type.id ───────────────────────────────────────

print(f"\n\n{'=' * 72}")
print(f"  НЕИЗВЕСТНЫЕ type.id (нужно добавить в BILLING_MAP)")
print(f"{'=' * 72}")

combined = defaultdict(lambda: {"name": "", "count": 0, "total": 0.0,
                                 "shops": set(), "currencies": set()})
for u in all_unknown:
    combined[u["id"]]["name"]       = u["name"]
    combined[u["id"]]["count"]     += 1
    combined[u["id"]]["total"]     += u["amount"]
    combined[u["id"]]["shops"].add(u["shop"])
    combined[u["id"]]["currencies"].add(u["currency"])

if combined:
    print(f"\n  {'type.id':<10} {'Название':<42} {'Кол':>5} {'Сумма':>10}  Магазины / Валюты")
    print(f"  {'─'*10} {'─'*42} {'─'*5} {'─'*10}  {'─'*30}")
    for tid, info in sorted(combined.items()):
        shops_str = ", ".join(sorted(info["shops"]))
        curr_str  = "/".join(sorted(info["currencies"]))
        print(f"  {tid:<10} {info['name']:<42} {info['count']:>5} {info['total']:>10,.2f}  {shops_str} [{curr_str}]")
    print(f"\n  ⚠ Добавь эти type.id в BILLING_MAP!")
else:
    print(f"\n  ✅ Все type.id распознаны — BILLING_MAP полный!")

print(f"\n{'=' * 72}")
print(f"  ✅ Тест завершён. data.json НЕ изменён.")
print(f"{'=' * 72}")
