"""
POLAX — Обновление COG (закупочная цена без НДС) из Excel-файла

Читает «без VAT.xls» (или файл из COG_FILE env),
сопоставляет с products.json по EAN (приоритет) → SKU,
обновляет поле cog для каждого магазина.

Правила:
  • Совпадение по EAN (приоритет) → берём цену
  • Совпадение по SKU (Kod dostawcy) → берём цену
  • Товар есть в Allegro, но НЕ найден в Excel → cog = 0 (для всех магазинов)
  • Название и категория товара ВСЕГДА берутся из Allegro (products.json)

Запуск:
  python update_cog.py
  COG_FILE="другой файл.xls" python update_cog.py  (другой файл)

Порядок работы:
  1. python fetch_unit_catalog.py   (создаёт products.json)
  2. python update_cog.py           (добавляет COG в products.json)
"""

import json, os, sys
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("❌ Установите pandas:  pip3 install pandas xlrd openpyxl")
    sys.exit(1)

SHOPS    = ["Mlot_i_Klucz", "PolaxEuroGroup", "Sila_Narzedzi"]
COG_FILE = os.environ.get("COG_FILE", "без VAT.xls")


# ── Читаем Excel ──────────────────────────────────────────────

def load_cog_from_excel(path):
    """
    Возвращает два словаря: ean_map {ean→cog}, sku_map {sku→cog}
    Структура файла:
      col 0: Towar (название — не используем, берём из Allegro)
      col 1: Kod dostawcy (SKU поставщика)
      col 2: koszt bez VAT (COG)
      col 3: KOD EAN13
    """
    try:
        df = pd.read_excel(path, header=None, dtype=str)
    except Exception as e:
        print(f"❌ Ошибка чтения {path}: {e}")
        sys.exit(1)

    # Строки с числовой ценой
    def to_float(v):
        try:
            return round(float(str(v).strip().replace(',', '.')), 2)
        except Exception:
            return None

    def clean_ean(v):
        s = str(v).strip().replace('\n', '').replace('\r', '').replace(' ', '')
        return s if s.isdigit() and len(s) >= 8 else ''

    def clean_sku(v):
        s = str(v).strip() if pd.notna(v) else ''
        return s if s not in ('', 'nan', 'None') else ''

    ean_map = {}
    sku_map = {}
    skipped = 0

    for _, row in df.iterrows():
        cog = to_float(row.get(2))
        if cog is None:
            skipped += 1
            continue

        ean = clean_ean(row.get(3, ''))
        sku = clean_sku(row.get(1, ''))

        if ean:
            ean_map[ean] = cog
        if sku:
            sku_map[sku] = cog

    print(f"  📄 {path}: {len(ean_map)} по EAN, {len(sku_map)} по SKU "
          f"({skipped} строк пропущено — заголовки/секции)")
    return ean_map, sku_map


# ── Читаем / сохраняем products.json ─────────────────────────

def load_products():
    if not os.path.exists("products.json"):
        print("❌ products.json не найден.")
        print("   Сначала запустите: python fetch_unit_catalog.py")
        sys.exit(1)
    with open("products.json", encoding="utf-8") as f:
        return json.load(f)


def save_products(data):
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


# ── Основная логика ───────────────────────────────────────────

print("=" * 60)
print("  POLAX — Обновление COG из Excel")
print(f"  Файл: {COG_FILE}")
print("=" * 60)

# 1. Загружаем цены из Excel
print("\n── Загрузка Excel ───────────────────────────────────────")
ean_map, sku_map = load_cog_from_excel(COG_FILE)

# 2. Загружаем каталог
print("\n── Загрузка products.json ───────────────────────────────")
catalog = load_products()
products = catalog.get("products", [])
print(f"  Товаров в каталоге: {len(products)}")

# 3. Сопоставление и обновление COG
print("\n── Сопоставление ────────────────────────────────────────")

stats = {"by_ean": 0, "by_sku": 0, "not_found": 0, "zero_set": 0}
unmatched = []  # products set to cog=0

for p in products:
    ean = (p.get("ean") or "").strip().replace('\n', '').replace('\r', '')
    sku = (p.get("sku") or "").strip()

    cog_value = None
    match_method = None

    # Приоритет 1: по EAN
    if ean and ean in ean_map:
        cog_value    = ean_map[ean]
        match_method = "EAN"
        stats["by_ean"] += 1

    # Приоритет 2: по SKU
    elif sku and sku in sku_map:
        cog_value    = sku_map[sku]
        match_method = "SKU"
        stats["by_sku"] += 1

    # Не найден → ставим 0
    else:
        cog_value = 0.0
        match_method = "—"
        stats["not_found"] += 1
        stats["zero_set"] += 1
        unmatched.append({"ean": ean, "sku": sku, "name": p.get("name", "")[:60]})

    # Применяем COG ко всем магазинам, у которых есть этот оффер
    for shop in SHOPS:
        has_offer = p.get("offers", {}).get(shop) is not None
        if has_offer:
            if "cog" not in p or not isinstance(p["cog"], dict):
                p["cog"] = {s: None for s in SHOPS}
            p["cog"][shop] = cog_value

# 4. Добавляем/обновляем дату обновления COG
catalog["cog_updated"] = datetime.utcnow().strftime("%Y-%m-%d")
catalog["products"]    = products

# 5. Сохраняем
save_products(catalog)

# ── Итог ─────────────────────────────────────────────────────
print(f"\n── Итог ────────────────────────────────────────────────")
print(f"  ✅ Совпало по EAN:    {stats['by_ean']:>4}")
print(f"  ✅ Совпало по SKU:    {stats['by_sku']:>4}")
print(f"  ⚠  Не найдено (→0):  {stats['not_found']:>4}")
print(f"  💾 products.json обновлён")

if unmatched:
    print(f"\n── Товары с COG=0 (нет в Excel) ───────────────────────")
    print(f"  {'EAN':<15} {'SKU':<12} {'Название'}")
    print(f"  {'-'*15} {'-'*12} {'-'*40}")
    for item in unmatched[:50]:
        print(f"  {item['ean']:<15} {item['sku']:<12} {item['name']}")
    if len(unmatched) > 50:
        print(f"  … и ещё {len(unmatched)-50} товаров")

print("\n✅ Готово.")
