"""
fetch_emag_daily.py — ежедневное обновление eMAG → data.json

Что делает:
  1. Собирает вчера (complete) + сегодня (partial) с eMAG API
  2. Патчит ТОЛЬКО поля EMAG + emag-ro/bg/hu в существующих записях data.json
     (данные Allegro не трогает)
  3. Пересчитывает months[]
  4. git pull → git commit → git push

Запуск: python3 fetch_emag_daily.py
"""

import requests, json, os, subprocess
from base64 import b64encode
from datetime import date, timedelta, datetime, timezone
from dotenv import load_dotenv

load_dotenv()

USERNAME  = os.getenv("EMAG_USERNAME", "sellerup@foks.ai")
PASSWORD  = os.getenv("EMAG_PASSWORD", "OURDgAI")
DATA_FILE = "data.json"

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

MONTH_NAMES = {
    1:"Янв",2:"Фев",3:"Мар",4:"Апр",5:"Май",6:"Июн",
    7:"Июл",8:"Авг",9:"Сен",10:"Окт",11:"Ноя",12:"Дек"
}

# ── HELPERS ───────────────────────────────────────────────────

def auth_header():
    token = b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

def safe_float(v):
    try:    return float(v or 0)
    except: return 0.0

# ── NBP ───────────────────────────────────────────────────────

def get_nbp_rates():
    """Текущий курс НБП: ron/eur/huf → PLN."""
    rates = {"ron": 0.0, "eur": 0.0, "huf": 0.0}
    try:
        r = requests.get("https://api.nbp.pl/api/exchangerates/tables/a/?format=json", timeout=15)
        if r.status_code == 200:
            for entry in r.json()[0]["rates"]:
                code = entry["code"].lower()
                if code in rates:
                    rates[code] = entry["mid"]
        print(f"  НБП: RON={rates['ron']:.4f}  EUR={rates['eur']:.4f}  HUF={rates['huf']:.6f}")
    except Exception as e:
        print(f"  ⚠ НБП недоступен: {e}")
    return rates

# ── eMAG ORDERS ───────────────────────────────────────────────

def get_day_total(base_url, day_str):
    """
    Суммарная выручка eMAG за один день (sale_price × qty × (1+vat)).
    Возвращает native amount в валюте страны.
    """
    headers = auth_header()
    fr = day_str + " 00:00:00"
    to = day_str + " 23:59:59"
    total = 0.0
    count = 0
    page  = 1
    while True:
        try:
            r = requests.post(
                f"{base_url}/order/read", headers=headers,
                json={"currentPage": page, "itemsPerPage": 100,
                      "createdAfter": fr, "createdBefore": to, "status": 4},
                timeout=20)
            orders = r.json().get("results", [])
        except Exception as e:
            print(f"    ⚠ eMAG {base_url}: {e}")
            break
        if not isinstance(orders, list) or not orders:
            break
        for o in orders:
            order_total = sum(
                safe_float(p.get("sale_price")) * int(p.get("quantity") or 1) * (1 + safe_float(p.get("vat")))
                for p in o.get("products", [])
            )
            total += order_total
            count += 1
        if len(orders) < 100:
            break
        page += 1
    return round(total, 2), count


def collect_emag_day(day_str, nbp):
    """
    Собирает eMAG по всем 3 странам за один день.
    Возвращает dict для патча записи data.json.
    """
    print(f"  Сбор eMAG за {day_str}...")
    market_data = {}
    for market_id, base_url in MARKETS.items():
        native, cnt = get_day_total(base_url, day_str)
        market_data[market_id] = native
        currency = CURRENCY_MAP[market_id]
        pln = native * nbp.get(currency, 0)
        print(f"    {market_id}: {cnt} заказов = {native:.2f} → {pln:.2f} PLN")

    total_pln = round(sum(
        market_data[mid] * nbp.get(CURRENCY_MAP[mid], 0)
        for mid in MARKETS
    ), 2)
    print(f"    ИТОГО eMAG: {total_pln:.2f} PLN")

    return {
        "EMAG":     total_pln,
        "emag-ro":  market_data["emag-ro"],
        "emag-bg":  market_data["emag-bg"],
        "emag-hu":  market_data["emag-hu"],
    }

# ── DATA.JSON ─────────────────────────────────────────────────

def load_data():
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

def update_months(days):
    """Пересчитывает months[] из days[]."""
    from collections import defaultdict
    monthly = defaultdict(lambda: {
        "Mlot_i_Klucz": 0, "PolaxEuroGroup": 0, "Sila_Narzedzi": 0, "EMAG": 0,
        "countries": {},
        "costs": {"commission":0,"delivery":0,"ads":0,"subscription":0,"discount":0},
        "shop_costs": {}
    })
    for day in days:
        d = date.fromisoformat(day["date"])
        key = (d.year, d.month)
        for shop in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi","EMAG"]:
            monthly[key][shop] = monthly[key].get(shop, 0) + (day.get(shop) or 0)
        for k, v in (day.get("countries") or {}).items():
            monthly[key]["countries"][k] = monthly[key]["countries"].get(k, 0) + v
        for k, v in (day.get("costs") or {}).items():
            monthly[key]["costs"][k] = monthly[key]["costs"].get(k, 0) + v
        for shop, sc in (day.get("shop_costs") or {}).items():
            if shop not in monthly[key]["shop_costs"]:
                monthly[key]["shop_costs"][shop] = {}
            for k, v in sc.items():
                monthly[key]["shop_costs"][shop][k] = monthly[key]["shop_costs"][shop].get(k, 0) + v

    result = []
    for (year, month) in sorted(monthly.keys()):
        m = monthly[(year, month)]
        result.append({
            "month":          f"{MONTH_NAMES[month]} {year}",
            "Mlot_i_Klucz":   round(m["Mlot_i_Klucz"], 2),
            "PolaxEuroGroup": round(m["PolaxEuroGroup"], 2),
            "Sila_Narzedzi":  round(m["Sila_Narzedzi"], 2),
            "EMAG":           round(m.get("EMAG", 0), 2),
            "countries":      {k: round(v, 2) for k, v in m["countries"].items()},
            "costs":          {k: round(v, 2) for k, v in m["costs"].items()},
            "shop_costs":     {
                shop: {k: round(v, 2) for k, v in costs.items()}
                for shop, costs in m["shop_costs"].items()
            },
        })
    return result

def patch_day(days_map, day_str, emag_data, partial=False):
    """
    Патчит запись day_str в days_map данными eMAG.
    Если записи нет — создаёт минимальную (Allegro ещё не собран за этот день).
    """
    if day_str not in days_map:
        # Запись ещё не создана GitHub Actions (например, если запускаем раньше 03:00 UTC)
        days_map[day_str] = {
            "date": day_str,
            "Mlot_i_Klucz": 0.0, "PolaxEuroGroup": 0.0, "Sila_Narzedzi": 0.0,
            "EMAG": 0.0,
            "countries": {"allegro-pl":0.0,"allegro-cz":0.0,"allegro-hu":0.0,"allegro-sk":0.0,
                          "emag-ro":0.0,"emag-bg":0.0,"emag-hu":0.0},
            "costs": {"commission":0.0,"delivery":0.0,"ads":0.0,"subscription":0.0,"discount":0.0},
        }
        print(f"  ⚠ Записи {day_str} нет в data.json — создана пустая (Allegro обновится ночью)")

    entry = days_map[day_str]
    entry["EMAG"] = emag_data["EMAG"]
    if "countries" not in entry:
        entry["countries"] = {}
    entry["countries"]["emag-ro"] = emag_data["emag-ro"]
    entry["countries"]["emag-bg"] = emag_data["emag-bg"]
    entry["countries"]["emag-hu"] = emag_data["emag-hu"]
    if partial:
        entry["partial"] = True
    elif "partial" in entry:
        # вчера — убираем partial если был
        del entry["partial"]

# ── GIT ───────────────────────────────────────────────────────

def git_push(yesterday, today_str):
    try:
        subprocess.run(["git", "stash"], capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        subprocess.run(["git", "stash", "pop"], capture_output=True)
        subprocess.run(["git", "add", "data.json"], check=True)
        result = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if result.returncode == 0:
            print("  git: нет изменений для коммита")
            return
        msg = f"eMAG daily update: {yesterday} (complete) + {today_str} (partial)"
        subprocess.run(["git", "commit", "-m", msg], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("  ✅ Запушено в GitHub")
    except subprocess.CalledProcessError as e:
        print(f"  ⚠ git ошибка: {e}")

# ── MAIN ──────────────────────────────────────────────────────

if __name__ == "__main__":
    now       = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today_str = now.strftime("%Y-%m-%d")

    print("🛒 eMAG Daily Update")
    print(f"   Вчера:   {yesterday} (complete)")
    print(f"   Сегодня: {today_str} (partial)")
    print(f"   User:    {USERNAME}")

    # НБП курсы
    print("\n── НБП курсы ────────────────────────────────────────────")
    nbp = get_nbp_rates()
    if not any(nbp.values()):
        print("  ⚠ НБП недоступен — конвертация будет 0. Прерываем.")
        exit(1)

    # Сбор eMAG
    print("\n── Сбор eMAG ────────────────────────────────────────────")
    yest_emag  = collect_emag_day(yesterday, nbp)
    today_emag = collect_emag_day(today_str, nbp)

    # Патч data.json
    print("\n── Обновление data.json ─────────────────────────────────")
    data = load_data()
    days_map = {d["date"]: d for d in data["days"]}

    patch_day(days_map, yesterday, yest_emag,  partial=False)
    patch_day(days_map, today_str, today_emag, partial=True)

    data["days"] = sorted(days_map.values(), key=lambda x: x["date"])
    data["months"] = update_months(data["days"])
    save_data(data)

    # Итог
    print("\n── Итог по месяцам ──────────────────────────────────────")
    for m in data["months"]:
        total = sum(m.get(s, 0) for s in ["Mlot_i_Klucz","PolaxEuroGroup","Sila_Narzedzi","EMAG"])
        print(f"  {m['month']}: EMAG={m.get('EMAG',0):.2f} PLN  |  Всего={total:.2f} PLN")

    # Git push
    print("\n── Git push ──────────────────────────────────────────────")
    git_push(yesterday, today_str)

    print(f"\n✅ Готово.")
