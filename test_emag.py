"""
test_emag.py — проверка подключения к EMAG API (RO / BG / HU)
Запуск: python test_emag.py
"""

import requests
import json
from base64 import b64encode
from dotenv import load_dotenv
import os

load_dotenv()

USERNAME = os.getenv("EMAG_USERNAME", "sellerup@foks.ai")
PASSWORD = os.getenv("EMAG_PASSWORD", "OURDgAI")

MARKETS = {
    "RO": "https://marketplace-api.emag.ro/api-3",
    "BG": "https://marketplace-api.emag.bg/api-3",
    "HU": "https://marketplace-api.emag.hu/api-3",
}

def basic_auth_header(username, password):
    token = b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

def test_orders(country, base_url):
    """Пробуем прочитать последние 5 заказов"""
    url = f"{base_url}/order/read"
    payload = {
        "currentPage": 1,
        "itemsPerPage": 5,
    }
    headers = basic_auth_header(USERNAME, PASSWORD)

    print(f"\n{'='*50}")
    print(f"  eMAG.{country.lower()} — тест подключения")
    print(f"  URL: {url}")
    print(f"{'='*50}")

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        print(f"  HTTP статус: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            print(f"  isError: {data.get('isError')}")
            print(f"  messages: {data.get('messages', [])}")

            orders = data.get("results", [])
            if isinstance(orders, list):
                print(f"  Заказов в ответе: {len(orders)}")
                for o in orders[:3]:
                    oid   = o.get("id") or o.get("order_id") or "?"
                    date  = o.get("date") or o.get("date_created") or "?"
                    total = o.get("grand_total") or o.get("total_amount") or "?"
                    cur   = o.get("currency", "")
                    status = o.get("status", "?")
                    print(f"    • ID={oid}  дата={date}  сумма={total} {cur}  статус={status}")
            elif isinstance(orders, dict):
                # Иногда EMAG возвращает dict с вложенными данными
                print(f"  results (dict keys): {list(orders.keys())}")
        else:
            print(f"  Ответ: {resp.text[:500]}")

    except requests.exceptions.ConnectionError as e:
        print(f"  ОШИБКА СОЕДИНЕНИЯ: {e}")
    except requests.exceptions.Timeout:
        print(f"  ОШИБКА: timeout (15 сек)")
    except Exception as e:
        print(f"  ОШИБКА: {e}")

def test_order_count(country, base_url):
    """Пробуем узнать общее количество заказов"""
    url = f"{base_url}/order/count"
    payload = {}
    headers = basic_auth_header(USERNAME, PASSWORD)

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  /order/count → {data}")
        else:
            print(f"  /order/count HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  /order/count ОШИБКА: {e}")

def test_sales_by_date(country, base_url, date_from="2026-01-01", date_to="2026-01-31"):
    """Пробуем фильтровать заказы по дате"""
    url = f"{base_url}/order/read"
    payload = {
        "currentPage": 1,
        "itemsPerPage": 10,
        "dateCreated": {
            "start": date_from,
            "end": date_to,
        }
    }
    headers = basic_auth_header(USERNAME, PASSWORD)

    print(f"\n  Тест фильтрации по дате ({date_from} → {date_to}):")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            orders = data.get("results", [])
            if isinstance(orders, list):
                print(f"  Заказов за период: {len(orders)}")
                total = sum(
                    float(o.get("grand_total") or o.get("total_amount") or 0)
                    for o in orders
                    if int(o.get("status", -1)) in [4]  # только finalized
                )
                print(f"  Сумма finalized заказов: {total:.2f}")
            else:
                print(f"  results: {json.dumps(orders, indent=2)[:300]}")
        else:
            print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
    except Exception as e:
        print(f"  ОШИБКА: {e}")

if __name__ == "__main__":
    print("\n🔍 EMAG API — тест подключения")
    print(f"   Username: {USERNAME}")
    print(f"   Password: {'*' * len(PASSWORD)}")

    for country, base_url in MARKETS.items():
        test_orders(country, base_url)
        test_order_count(country, base_url)
        test_sales_by_date(country, base_url, "2026-01-01", "2026-01-31")

    print("\n✅ Тест завершён")
