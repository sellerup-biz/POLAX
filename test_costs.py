"""
POLAX — ТЕСТ РАСХОДОВ: Янв / Фев / Мар 2026
Только чтение данных из API. data.json НЕ изменяется.
Запуск: test_costs.yml (workflow_dispatch) на GitHub Actions.

Выводит:
  • по каждому магазину × каждому месяцу: суммы по категориям расходов
  • все неизвестные type.id (категория «other») → для пополнения BILLING_MAP
  • сводную таблицу (все магазины × все месяцы) с итогами
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


def get_costs_for_month(token, year, month):
    """
    Запрашивает /billing/billing-entries БЕЗ marketplaceId.
    Возвращает:
      costs     — dict по категориям (PLN)
      unknowns  — list of {id, name, amount} для неизвестных type.id
      pad_total — сумма проигнорированных PAD записей
      raw_count — сколько записей всего получено
    """
    last_day   = calendar.monthrange(year, month)[1]
    tz         = get_tz(month)
    date_from  = f"{year}-{month:02d}-01T00:00:00+0{tz}:00"
    date_to    = f"{year}-{month:02d}-{last_day:02d}T23:59:59+0{tz}:00"

    costs     = {cat: 0.0 for cat in COST_CATS}
    unknowns  = []         # [{id, name, amount}]
    pad_total = 0.0
    raw_count = 0
    offset    = 0

    while True:
        resp = requests.get(
            "https://api.allegro.pl/billing/billing-entries",
            headers=hdrs(token),
            params={
                "occurredAt.gte": date_from,
                "occurredAt.lte": date_to,
                "limit":          100,
                "offset":         offset,
            },
        )
        if resp.status_code != 200:
            print(f"      ⚠ Billing HTTP {resp.status_code}: {resp.text[:200]}")
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
                print(f"      ⚠ Ошибка записи: {ex} → {e}")

        if len(entries) < 100:
            break
        offset += 100

    return (
        {k: round(v, 2) for k, v in costs.items()},
        unknowns,
        round(pad_total, 2),
        raw_count,
    )


def fmt(n):
    return f"{n:>12,.2f}"


# ── MAIN ──────────────────────────────────────────────────────

print("=" * 72)
print("  POLAX — ТЕСТ РАСХОДОВ: Янв / Фев / Мар 2026")
print("  data.json НЕ изменяется")
print("=" * 72)

pubkey      = get_gh_pubkey()
all_costs   = {}   # all_costs[shop_name][label] = costs dict
all_unknown = defaultdict(lambda: defaultdict(list))  # [shop][label] = [{id,name,amt}]

for shop_name, shop in SHOPS.items():
    print(f"\n{'━' * 60}")
    print(f"  МАГАЗИН: {shop_name}")
    print(f"{'━' * 60}")

    token, new_rt = get_token(shop)
    if not token:
        print("  ❌ Не удалось получить токен — пропускаем магазин")
        continue
    save_token(shop["secret_name"], new_rt, pubkey)

    shop_costs = {}
    for year, month, label in MONTHS_TO_CHECK:
        print(f"\n  {label}:  ({year}-{month:02d})")
        costs, unknowns, pad_total, raw_count = get_costs_for_month(token, year, month)
        shop_costs[label] = costs
        all_unknown[shop_name][label] = unknowns

        print(f"    Записей из API:  {raw_count}")
        print(f"    PAD (ignored):  {fmt(pad_total)} PLN")
        print(f"    ─────────────────────────────────────────")
        print(f"    commission:     {fmt(costs['commission'])} PLN")
        print(f"    delivery:       {fmt(costs['delivery'])} PLN")
        print(f"    ads:            {fmt(costs['ads'])} PLN")
        print(f"    subscription:   {fmt(costs['subscription'])} PLN")
        print(f"    discount:       {fmt(costs['discount'])} PLN  (rabaty — уменьшают реальные расходы)")
        total_costs = sum(costs.values()) - costs["discount"]
        print(f"    ─────────────────────────────────────────")
        print(f"    ИТОГО расходов: {fmt(total_costs)} PLN  (без discount)")

        if unknowns:
            print(f"\n    ⚠ НЕИЗВЕСТНЫЕ type.id ({len(unknowns)} записей) → нужно добавить в BILLING_MAP:")
            seen = {}
            for u in unknowns:
                key = u["id"]
                if key not in seen:
                    seen[key] = {"name": u["name"], "count": 0, "total": 0.0}
                seen[key]["count"] += 1
                seen[key]["total"] += u["amount"]
            for tid, info in sorted(seen.items()):
                print(f"      {tid:<8} {info['name']:<45} {info['count']:>3} записей  {fmt(info['total'])} PLN")

    all_costs[shop_name] = shop_costs

# ── СВОДНАЯ ТАБЛИЦА ───────────────────────────────────────────

print(f"\n\n{'=' * 72}")
print(f"  СВОДНАЯ ТАБЛИЦА РАСХОДОВ — все магазины × все месяцы (PLN)")
print(f"{'=' * 72}")

COL = 13

for year, month, label in MONTHS_TO_CHECK:
    print(f"\n  {label}")
    print(f"  {'Магазин':<22} {'commission':>{COL}} {'delivery':>{COL}} {'ads':>{COL}} {'subscr':>{COL}} {'discount':>{COL}}")
    print(f"  {'─'*22} {'─'*COL} {'─'*COL} {'─'*COL} {'─'*COL} {'─'*COL}")

    totals = {cat: 0.0 for cat in COST_CATS}

    for shop_name in SHOPS:
        if shop_name not in all_costs or label not in all_costs[shop_name]:
            print(f"  {shop_name:<22} {'нет данных':>{COL}}")
            continue
        c = all_costs[shop_name][label]
        for cat in COST_CATS:
            totals[cat] += c[cat]
        print(f"  {shop_name:<22}"
              f" {c['commission']:>{COL},.2f}"
              f" {c['delivery']:>{COL},.2f}"
              f" {c['ads']:>{COL},.2f}"
              f" {c['subscription']:>{COL},.2f}"
              f" {c['discount']:>{COL},.2f}")

    print(f"  {'─'*22} {'─'*COL} {'─'*COL} {'─'*COL} {'─'*COL} {'─'*COL}")
    print(f"  {'ИТОГО':<22}"
          f" {totals['commission']:>{COL},.2f}"
          f" {totals['delivery']:>{COL},.2f}"
          f" {totals['ads']:>{COL},.2f}"
          f" {totals['subscription']:>{COL},.2f}"
          f" {totals['discount']:>{COL},.2f}")

# ── ИТОГ ЗА 3 МЕСЯЦА ─────────────────────────────────────────

print(f"\n{'─' * 72}")
print(f"  ИТОГО РАСХОДОВ ЗА ВСЕ 3 МЕСЯЦА (все магазины суммированы)")
print(f"{'─' * 72}")

grand = {cat: 0.0 for cat in COST_CATS}
for shop_name in SHOPS:
    if shop_name not in all_costs:
        continue
    shop_total = {cat: 0.0 for cat in COST_CATS}
    for _, _, label in MONTHS_TO_CHECK:
        if label not in all_costs[shop_name]:
            continue
        for cat in COST_CATS:
            shop_total[cat] += all_costs[shop_name][label].get(cat, 0.0)
    for cat in COST_CATS:
        grand[cat] += shop_total[cat]
    net = sum(shop_total.values()) - shop_total["discount"]
    print(f"  {shop_name:<22}  commission {shop_total['commission']:>9,.2f}  "
          f"delivery {shop_total['delivery']:>9,.2f}  "
          f"ads {shop_total['ads']:>9,.2f}  "
          f"subscr {shop_total['subscription']:>7,.2f}  "
          f"discount {shop_total['discount']:>7,.2f}  → нетто {net:>9,.2f}")

print(f"{'─' * 72}")
grand_net = sum(grand.values()) - grand["discount"]
print(f"  {'ВСЕ МАГАЗИНЫ':<22}  commission {grand['commission']:>9,.2f}  "
      f"delivery {grand['delivery']:>9,.2f}  "
      f"ads {grand['ads']:>9,.2f}  "
      f"subscr {grand['subscription']:>7,.2f}  "
      f"discount {grand['discount']:>7,.2f}  → нетто {grand_net:>9,.2f}")

# ── НЕИЗВЕСТНЫЕ type.id — общий список ───────────────────────

print(f"\n\n{'=' * 72}")
print(f"  НЕИЗВЕСТНЫЕ type.id (нужно добавить в BILLING_MAP)")
print(f"{'=' * 72}")

combined_unknown = defaultdict(lambda: {"name": "", "count": 0, "total": 0.0, "shops": set()})
for shop_name, months_data in all_unknown.items():
    for label, entries in months_data.items():
        for u in entries:
            combined_unknown[u["id"]]["name"]  = u["name"]
            combined_unknown[u["id"]]["count"] += 1
            combined_unknown[u["id"]]["total"] += u["amount"]
            combined_unknown[u["id"]]["shops"].add(shop_name)

if combined_unknown:
    print(f"\n  {'type.id':<10} {'Название':<45} {'Кол-во':>7} {'Сумма PLN':>12}  Магазины")
    print(f"  {'─'*10} {'─'*45} {'─'*7} {'─'*12}  {'─'*20}")
    for tid, info in sorted(combined_unknown.items()):
        shops_str = ", ".join(sorted(info["shops"]))
        print(f"  {tid:<10} {info['name']:<45} {info['count']:>7} {info['total']:>12,.2f}  {shops_str}")
    print(f"\n  ⚠ Добавь эти type.id в BILLING_MAP в fetch_history.py и fetch.py!")
else:
    print(f"\n  ✅ Все type.id распознаны — BILLING_MAP полный!")

print(f"\n{'=' * 72}")
print(f"  ✅ Тест завершён. data.json НЕ изменён.")
print(f"{'=' * 72}")
