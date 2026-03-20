"""
POLAX — ТЕСТ ПРОДАЖ: Янв / Фев / Мар 2026
Только чтение данных из API. data.json НЕ изменяется.
Запуск: test_sales.yml (workflow_dispatch) на GitHub Actions.

Выводит:
  • по каждому магазину × каждому месяцу: суммы per маркетплейс + кол-во операций
  • сводную таблицу (все магазины × все месяцы) в каждой валюте отдельно
"""
import requests, os, base64, calendar
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
GH_REPO      = "sellerup-biz/POLAX"

MONTHS_TO_CHECK = [
    (2026, 1, "Янв 2026"),
    (2026, 2, "Фев 2026"),
    (2026, 3, "Мар 2026"),
]

# allegro-business-pl суммируется с allegro-pl → одно число PLN
MARKETPLACES = ["allegro-pl", "allegro-business-pl", "allegro-cz", "allegro-hu", "allegro-sk"]

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

# ── helpers ───────────────────────────────────────────────────

def get_gh_pubkey():
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
        headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"},
    )
    return r.json()


def save_token(secret_name, new_rt, pubkey):
    """Сохраняем новый refresh_token в GitHub Secrets (обязательно после каждого get_token)."""
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
    """Польское смещение: летом +2, зимой +1."""
    return 2 if 3 <= month <= 10 else 1


def get_sales_for_month(token, year, month):
    """
    Запрашивает продажи по каждому маркетплейсу отдельно.
    Возвращает dict:
      {
        mkt: {"amount": float, "count": int},
        ...
      }
    Пагинация по 50 операций.
    """
    last_day = calendar.monthrange(year, month)[1]
    tz = get_tz(month)
    date_from = f"{year}-{month:02d}-01T00:00:00+0{tz}:00"
    date_to   = f"{year}-{month:02d}-{last_day:02d}T23:59:59+0{tz}:00"

    results = {}
    for mkt in MARKETPLACES:
        total_amount = 0.0
        total_count  = 0
        offset       = 0
        while True:
            resp = requests.get(
                "https://api.allegro.pl/payments/payment-operations",
                headers=hdrs(token),
                params={
                    "group":            "INCOME",
                    "occurredAt.gte":   date_from,
                    "occurredAt.lte":   date_to,
                    "marketplaceId":    mkt,
                    "limit":            50,
                    "offset":           offset,
                },
            )
            data = resp.json()
            if resp.status_code != 200:
                print(f"      ⚠ {mkt}: HTTP {resp.status_code} → {data}")
                break
            ops = data.get("paymentOperations", [])
            for op in ops:
                try:
                    total_amount += float(op["value"]["amount"])
                    total_count  += 1
                except Exception:
                    pass
            if len(ops) < 50:
                break
            offset += 50
        results[mkt] = {"amount": round(total_amount, 2), "count": total_count}
    return results


def fmt_num(n):
    return f"{n:>13,.2f}"


# ── MAIN ──────────────────────────────────────────────────────

print("=" * 72)
print("  POLAX — ТЕСТ ПРОДАЖ: Янв / Фев / Мар 2026")
print("  data.json НЕ изменяется")
print("=" * 72)

pubkey      = get_gh_pubkey()
all_results = {}   # all_results[shop_name][label] = {mkt: {amount, count}}

for shop_name, shop in SHOPS.items():
    print(f"\n{'━' * 60}")
    print(f"  МАГАЗИН: {shop_name}")
    print(f"{'━' * 60}")

    token, new_rt = get_token(shop)
    if not token:
        print("  ❌ Не удалось получить токен — пропускаем магазин")
        continue
    # ОБЯЗАТЕЛЬНО сохраняем токен сразу после получения
    save_token(shop["secret_name"], new_rt, pubkey)

    shop_results = {}
    for year, month, label in MONTHS_TO_CHECK:
        print(f"\n  {label}:")
        sales = get_sales_for_month(token, year, month)
        shop_results[label] = sales

        pl_amount = sales["allegro-pl"]["amount"] + sales["allegro-business-pl"]["amount"]
        pl_count  = sales["allegro-pl"]["count"]  + sales["allegro-business-pl"]["count"]

        print(f"    allegro-pl + business: {fmt_num(pl_amount)} PLN"
              f"  ({sales['allegro-pl']['count']} + {sales['allegro-business-pl']['count']} = {pl_count} ops)")
        print(f"    allegro-cz:            {fmt_num(sales['allegro-cz']['amount'])} CZK"
              f"  ({sales['allegro-cz']['count']} ops)")
        print(f"    allegro-hu:            {fmt_num(sales['allegro-hu']['amount'])} HUF"
              f"  ({sales['allegro-hu']['count']} ops)")
        print(f"    allegro-sk:            {fmt_num(sales['allegro-sk']['amount'])} EUR"
              f"  ({sales['allegro-sk']['count']} ops)")
        print(f"    {'─'*56}")
        print(f"    PLN (только PL):       {fmt_num(pl_amount)} PLN  ← в data.json")

    all_results[shop_name] = shop_results

# ── СВОДНАЯ ТАБЛИЦА ───────────────────────────────────────────

print(f"\n\n{'=' * 72}")
print(f"  СВОДНАЯ ТАБЛИЦА — все магазины × все месяцы")
print(f"{'=' * 72}")

COL = 14

for year, month, label in MONTHS_TO_CHECK:
    print(f"\n  {label}")
    header = f"  {'Магазин':<22} {'PLN (PL+biz)':>{COL}} {'CZK':>{COL}} {'HUF':>{COL}} {'EUR (SK)':>{COL}}"
    sep    = f"  {'─'*22} {'─'*COL} {'─'*COL} {'─'*COL} {'─'*COL}"
    print(header)
    print(sep)

    total_pln = 0.0
    total_czk = 0.0
    total_huf = 0.0
    total_eur = 0.0

    for shop_name in SHOPS:
        if shop_name not in all_results or label not in all_results[shop_name]:
            print(f"  {shop_name:<22} {'нет данных':>{COL}}")
            continue
        s   = all_results[shop_name][label]
        pln = round(s["allegro-pl"]["amount"] + s["allegro-business-pl"]["amount"], 2)
        czk = s["allegro-cz"]["amount"]
        huf = s["allegro-hu"]["amount"]
        eur = s["allegro-sk"]["amount"]
        total_pln += pln
        total_czk += czk
        total_huf += huf
        total_eur += eur
        print(f"  {shop_name:<22} {pln:>{COL},.2f} {czk:>{COL},.2f} {huf:>{COL},.2f} {eur:>{COL},.2f}")

    print(sep)
    print(f"  {'ИТОГО':<22} {total_pln:>{COL},.2f} {total_czk:>{COL},.2f} {total_huf:>{COL},.2f} {total_eur:>{COL},.2f}")

# ── ОБЩИЙ ИТОГ ПО ВСЕМ МЕСЯЦАМ ───────────────────────────────

print(f"\n{'─' * 72}")
print(f"  ИТОГО ЗА ВСЕ 3 МЕСЯЦА")
print(f"{'─' * 72}")

grand_pln = grand_czk = grand_huf = grand_eur = 0.0
for shop_name, shop_data in all_results.items():
    shop_pln = shop_czk = shop_huf = shop_eur = 0.0
    for _, _, label in MONTHS_TO_CHECK:
        if label not in shop_data:
            continue
        s = shop_data[label]
        shop_pln += s["allegro-pl"]["amount"] + s["allegro-business-pl"]["amount"]
        shop_czk += s["allegro-cz"]["amount"]
        shop_huf += s["allegro-hu"]["amount"]
        shop_eur += s["allegro-sk"]["amount"]
    grand_pln += shop_pln
    grand_czk += shop_czk
    grand_huf += shop_huf
    grand_eur += shop_eur
    print(f"  {shop_name:<22} PLN {shop_pln:>12,.2f}  CZK {shop_czk:>10,.2f}  HUF {shop_huf:>10,.2f}  EUR {shop_eur:>9,.2f}")

print(f"{'─' * 72}")
print(f"  {'ВСЕ МАГАЗИНЫ':<22} PLN {grand_pln:>12,.2f}  CZK {grand_czk:>10,.2f}  HUF {grand_huf:>10,.2f}  EUR {grand_eur:>9,.2f}")

print(f"\n{'=' * 72}")
print(f"  ✅ Тест завершён. data.json НЕ изменён.")
print(f"{'=' * 72}")
