"""
fetch_emag_history.py — сбор данных eMAG (RO/BG/HU) → data.json
- Январь и Февраль: месячные агрегаты (как в Allegro)
- Март: по каждому дню (т.к. в data.json уже дневные записи)

Запуск: python3 fetch_emag_history.py
"""

import requests
import json
import os
from base64 import b64encode
from datetime import date, timedelta
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*a, **k): pass  # CI: env vars приходят напрямую

load_dotenv()

USERNAME  = os.getenv("EMAG_USERNAME") or "sellerup@foks.ai"
PASSWORD  = os.getenv("EMAG_PASSWORD") or "OURDgAI"
DATA_FILE = "data.json"

HISTORY_FROM = os.getenv("HISTORY_FROM", "2026-01-01")
HISTORY_TO   = os.getenv("HISTORY_TO",   "2026-03-31")

MARKETS = {
    "emag-ro": "https://marketplace-api.emag.ro/api-3",
    "emag-bg": "https://marketplace-api.emag.bg/api-3",
    "emag-hu": "https://marketplace-api.emag.hu/api-3",
}

CURRENCY_MAP = {
    "emag-ro": "ron",
    "emag-bg": "eur",   # eMAG Bulgaria торгует в EUR, не в BGN
    "emag-hu": "huf",
}

# ---------- HELPERS ----------

def auth_header():
    token = b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

def safe_float(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0

# ---------- NBP ----------

def get_nbp_monthly_rate(currency, year, month):
    """Среднемесячный курс NBP для валюты (ron/bgn/huf/eur/czk)."""
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    fr = f"{year}-{month:02d}-01"
    to = f"{year}-{month:02d}-{last_day:02d}"
    url = f"https://api.nbp.pl/api/exchangerates/rates/a/{currency}/{fr}/{to}/?format=json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            rates = r.json()["rates"]
            avg = sum(x["mid"] for x in rates) / len(rates)
            print(f"  NBP {currency.upper()} {year}-{month:02d}: avg={avg:.4f} ({len(rates)} дней)")
            return avg
        print(f"  NBP {currency.upper()} HTTP {r.status_code}")
    except Exception as e:
        print(f"  NBP error: {e}")
    return None

def get_nbp_current_rate(currency):
    """Текущий курс NBP."""
    url = f"https://api.nbp.pl/api/exchangerates/rates/a/{currency}/?format=json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            rate = r.json()["rates"][0]["mid"]
            print(f"  NBP {currency.upper()} current: {rate:.4f}")
            return rate
    except Exception as e:
        print(f"  NBP error: {e}")
    return None

# ---------- EMAG ORDERS ----------

def get_orders_total(base_url, date_from, date_to):
    """
    Возвращает суммарную выручку за период (cashed_co + cashed_cod)
    для финализированных заказов (status=4).
    """
    headers = auth_header()
    total = 0.0
    count = 0
    page  = 1
    while True:
        # EMAG фильтр: createdBefore эксклюзивный,
        # поэтому добавляем время для точного захвата дня
        fr = date_from if " " in date_from else date_from + " 00:00:00"
        to = date_to   if " " in date_to   else date_to   + " 23:59:59"
        payload = {
            "currentPage": page,
            "itemsPerPage": 100,
            "createdAfter":  fr,
            "createdBefore": to,
            "status": 4,
        }
        try:
            r = requests.post(f"{base_url}/order/read", headers=headers, json=payload, timeout=20)
            orders = r.json().get("results", [])
        except Exception as e:
            print(f"    ОШИБКА: {e}")
            break

        if not isinstance(orders, list) or not orders:
            break

        for o in orders:
            # sale_price × qty × (1+vat) = цена для покупателя с НДС = совпадает с кабинетом eMAG
            order_total = sum(
                safe_float(p.get("sale_price")) * int(p.get("quantity") or 1) * (1 + safe_float(p.get("vat")))
                for p in o.get("products", [])
            )
            total += order_total
            count += 1

        if len(orders) < 100:
            break
        page += 1

    return total, count

# ---------- MAIN LOGIC ----------

def collect_months():
    """
    Собирает EMAG данные за период HISTORY_FROM..HISTORY_TO.
    Возвращает dict: {
      "YYYY-MM-DD": {
        "emag-ro": native_amount,
        "emag-bg": native_amount,
        "emag-hu": native_amount,
        "EMAG_pln": total_in_pln,
        "nbp": {"ron": rate, "bgn": rate, "huf": rate}
      }
    }
    """
    from datetime import datetime

    result = {}

    # Определяем уникальные месяцы в диапазоне
    d_from = date.fromisoformat(HISTORY_FROM)
    d_to   = date.fromisoformat(HISTORY_TO)

    months = set()
    cur = d_from.replace(day=1)
    while cur <= d_to:
        months.add((cur.year, cur.month))
        # next month
        if cur.month == 12:
            cur = cur.replace(year=cur.year+1, month=1)
        else:
            cur = cur.replace(month=cur.month+1)

    today = date.today()

    for (year, month) in sorted(months):
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        month_start = date(year, month, 1)
        month_end   = date(year, month, last_day)

        print(f"\n=== {year}-{month:02d} ===")

        # NBP курсы для этого месяца
        nbp = {}
        for cur_name in ["ron", "eur", "huf"]:
            rate = get_nbp_monthly_rate(cur_name, year, month)
            if rate is None:
                rate = get_nbp_current_rate(cur_name) or 1.0
            nbp[cur_name] = rate

        # Проверяем: этот месяц нужно разбить по дням или взять целиком
        # Разбиваем по дням если в data.json есть дневные записи для этого месяца
        # (определяем позже при патчинге data.json)

        # Собираем данные по странам
        market_data = {}
        for market_id, base_url in MARKETS.items():
            currency = CURRENCY_MAP[market_id]
            # Считаем весь месяц целиком
            fr_str = month_start.isoformat()
            to_str = month_end.isoformat()
            total_native, cnt = get_orders_total(base_url, fr_str, to_str)
            market_data[market_id] = total_native
            rate = nbp[currency]
            total_pln = total_native * rate
            print(f"  {market_id}: {cnt} заказов = {total_native:.2f} → {total_pln:.2f} PLN")

        total_pln = sum(
            market_data[mid] * nbp[CURRENCY_MAP[mid]]
            for mid in MARKETS
        )

        key = month_start.isoformat()  # "YYYY-MM-01"
        result[key] = {
            "emag-ro": market_data["emag-ro"],
            "emag-bg": market_data["emag-bg"],
            "emag-hu": market_data["emag-hu"],
            "EMAG_pln": round(total_pln, 2),
            "nbp": nbp,
        }

    return result


def collect_days_in_month(year, month, nbp):
    """
    Собирает EMAG данные по каждому дню месяца.
    Возвращает dict: {"YYYY-MM-DD": {"emag-ro":..., "emag-bg":..., "emag-hu":..., "EMAG_pln":...}}
    """
    import calendar
    today = date.today()
    last_day = min(calendar.monthrange(year, month)[1], (date(year, month, today.day) if (year == today.year and month == today.month) else date(year, month, calendar.monthrange(year, month)[1])).day)

    result = {}
    cur = date(year, month, 1)
    end = date(year, month, last_day)

    while cur <= end:
        day_str = cur.isoformat()
        market_data = {}
        for market_id, base_url in MARKETS.items():
            total_native, _ = get_orders_total(base_url, day_str, day_str)
            market_data[market_id] = total_native

        total_pln = sum(
            market_data[mid] * nbp[CURRENCY_MAP[mid]]
            for mid in MARKETS
        )

        result[day_str] = {
            "emag-ro": market_data["emag-ro"],
            "emag-bg": market_data["emag-bg"],
            "emag-hu": market_data["emag-hu"],
            "EMAG_pln": round(total_pln, 2),
        }
        print(f"  {day_str}: RO={market_data['emag-ro']:.2f} BG={market_data['emag-bg']:.2f} HU={market_data['emag-hu']:.0f} → {total_pln:.2f} PLN")
        cur += timedelta(days=1)

    return result


def update_months(days):
    """Пересчитывает months[] из days[]."""
    from collections import defaultdict

    monthly = defaultdict(lambda: {
        "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0, "EMAG": 0,
        "countries": {},
        "costs": {"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0},
        "shop_costs": {}
    })

    MONTH_NAMES = {
        1:"Янв",2:"Фев",3:"Мар",4:"Апр",5:"Май",6:"Июн",
        7:"Июл",8:"Авг",9:"Сен",10:"Окт",11:"Ноя",12:"Дек"
    }

    for day in days:
        d = date.fromisoformat(day["date"])
        key = (d.year, d.month)

        for shop in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi","EMAG"]:
            monthly[key][shop] = monthly[key].get(shop, 0) + (day.get(shop) or 0)

        # countries
        for k, v in (day.get("countries") or {}).items():
            monthly[key]["countries"][k] = monthly[key]["countries"].get(k, 0) + v

        # costs
        for k, v in (day.get("costs") or {}).items():
            monthly[key]["costs"][k] = monthly[key]["costs"].get(k, 0) + v

        # shop_costs
        for shop, sc in (day.get("shop_costs") or {}).items():
            if shop not in monthly[key]["shop_costs"]:
                monthly[key]["shop_costs"][shop] = {}
            for k, v in sc.items():
                monthly[key]["shop_costs"][shop][k] = monthly[key]["shop_costs"][shop].get(k, 0) + v

    result = []
    for (year, month) in sorted(monthly.keys()):
        m = monthly[(year, month)]
        result.append({
            "month": f"{MONTH_NAMES[month]} {year}",
            "Mlot_i_Klucz":   round(m["Mlot_i_Klucz"], 2),
            "PolaxEuroGroup": round(m["PolaxEuroGroup"], 2),
            "Sila_Narzedzi":  round(m["Sila_Narzedzi"], 2),
            "EMAG":           round(m.get("EMAG", 0), 2),
            "countries":      {k: round(v,2) for k,v in m["countries"].items()},
            "costs":          {k: round(v,2) for k,v in m["costs"].items()},
            "shop_costs":     {
                shop: {k: round(v,2) for k,v in costs.items()}
                for shop, costs in m["shop_costs"].items()
            },
        })
    return result


def patch_data_json(monthly_data):
    """
    Добавляет EMAG данные в data.json.
    - Для monthly записей (2026-01-01, 2026-02-01): добавляет EMAG напрямую
    - Для дневных записей текущего месяца: собирает по дням отдельно
    """
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    days = data["days"]

    # Определяем какие даты есть как дневные записи (несколько записей в одном месяце)
    from collections import Counter
    month_counts = Counter()
    for d in days:
        dt = date.fromisoformat(d["date"])
        month_counts[(dt.year, dt.month)] += 1

    # Месяцы с дневными данными (более 1 записи)
    daily_months = {k for k, v in month_counts.items() if v > 1}
    print(f"\nМесяцы с дневными данными: {sorted(daily_months)}")

    # Патчим monthly записи
    for day in days:
        dt = date.fromisoformat(day["date"])
        month_key = (dt.year, dt.month)

        if month_key not in daily_months:
            # Это monthly aggregate запись
            record_key = day["date"]  # "YYYY-MM-01"
            if record_key in monthly_data:
                md = monthly_data[record_key]
                day["EMAG"] = md["EMAG_pln"]
                # Добавляем нативные суммы в countries
                if "countries" not in day:
                    day["countries"] = {}
                day["countries"]["emag-ro"] = md["emag-ro"]
                day["countries"]["emag-bg"] = md["emag-bg"]
                day["countries"]["emag-hu"] = md["emag-hu"]
                print(f"  Патч monthly {record_key}: EMAG={md['EMAG_pln']:.2f} PLN")

    # Для дневных месяцев — нужно собрать данные по дням
    for (year, month) in daily_months:
        month_first = date(year, month, 1).isoformat()
        if month_first not in monthly_data:
            print(f"\nПропускаем дневной месяц {year}-{month:02d} (нет в HISTORY диапазоне)")
            continue

        print(f"\nСбор дневных данных EMAG для {year}-{month:02d}...")
        nbp = monthly_data[month_first]["nbp"]
        daily_emag = collect_days_in_month(year, month, nbp)

        for day in days:
            if day["date"] in daily_emag:
                de = daily_emag[day["date"]]
                day["EMAG"] = de["EMAG_pln"]
                if "countries" not in day:
                    day["countries"] = {}
                day["countries"]["emag-ro"] = de["emag-ro"]
                day["countries"]["emag-bg"] = de["emag-bg"]
                day["countries"]["emag-hu"] = de["emag-hu"]

    # Пересчёт months[]
    print("\nПересчёт months[]...")
    data["months"] = update_months(days)
    data["days"] = days

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n✅ data.json обновлён")
    print("\nИтого по месяцам (EMAG):")
    for m in data["months"]:
        print(f"  {m['month']}: EMAG={m.get('EMAG',0):.2f} PLN  |  "
              f"Всего={sum(m.get(s,0) for s in ['Mlot_i_Klucz','PolaxEuroGroup','Sila_Narzedzi','EMAG']):.2f} PLN")


if __name__ == "__main__":
    print("🛒 EMAG History Collector")
    print(f"   Username: {USERNAME}")
    print(f"   Период: {HISTORY_FROM} → {HISTORY_TO}")

    # Шаг 1: Сбор monthly данных
    print("\n--- Шаг 1: Сбор EMAG данных по месяцам ---")
    monthly_data = collect_months()

    # Шаг 2: Патчинг data.json
    print("\n--- Шаг 2: Обновление data.json ---")
    patch_data_json(monthly_data)
