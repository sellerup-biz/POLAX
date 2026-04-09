import pandas as pd
import json
from datetime import date

# ── Load XLS ──────────────────────────────────────────────────
df = pd.read_excel(
    '/Users/vladislavmykhailenko/Documents/POLAX/priceVAT.xls',
    header=0,
    dtype=str
)

# Skip row 0 (it's a config row with only % value)
df = df.iloc[1:].reset_index(drop=True)

COG_COL = 'Цена СС brutto (с VAT)'
SKU_COL = 'Numer katalogowy'
EAN_COL = 'KOD EAN13'

# Build lookup: sku → price and ean → price
# EAN may be stored in scientific notation, normalise to 13-digit string
def norm_ean(v):
    if pd.isna(v) or str(v).strip() in ('', 'nan'):
        return None
    try:
        return str(int(float(str(v).strip())))
    except:
        return str(v).strip()

def norm_sku(v):
    if pd.isna(v) or str(v).strip() in ('', 'nan'):
        return None
    return str(v).strip()

def norm_price(v):
    if pd.isna(v) or str(v).strip() in ('', 'nan'):
        return None
    try:
        return round(float(str(v).replace(',', '.')), 2)
    except:
        return None

sku_price = {}
ean_price = {}

for _, row in df.iterrows():
    price = norm_price(row.get(COG_COL))
    if price is None or price <= 0:
        continue
    sku = norm_sku(row.get(SKU_COL))
    ean = norm_ean(row.get(EAN_COL))
    if sku:
        sku_price[sku] = price
    if ean:
        ean_price[ean] = price

print(f"XLS: {len(sku_price)} SKU entries, {len(ean_price)} EAN entries with valid price")

# ── Load products.json ─────────────────────────────────────────
with open('/Users/vladislavmykhailenko/Documents/POLAX/products.json', 'r', encoding='utf-8') as f:
    catalog = json.load(f)

products = catalog['products']
shops = ['Mlot_i_Klucz', 'PolaxEuroGroup', 'Sila_Narzedzi']

matched_sku = 0
matched_ean = 0
not_found   = 0

for p in products:
    p_sku = norm_sku(p.get('sku'))
    p_ean = norm_ean(p.get('ean'))

    price = None
    method = None

    # Try SKU first
    if p_sku and p_sku in sku_price:
        price  = sku_price[p_sku]
        method = 'sku'
        matched_sku += 1
    # Then EAN
    elif p_ean and p_ean in ean_price:
        price  = ean_price[p_ean]
        method = 'ean'
        matched_ean += 1
    else:
        not_found += 1
        continue

    # Update COG for all shops
    if 'cog' not in p or not isinstance(p['cog'], dict):
        p['cog'] = {}
    for s in shops:
        p['cog'][s] = price

catalog['cog_updated'] = str(date.today())

with open('/Users/vladislavmykhailenko/Documents/POLAX/products.json', 'w', encoding='utf-8') as f:
    json.dump(catalog, f, ensure_ascii=False, separators=(',', ':'))

print(f"\n✅ Results:")
print(f"   Matched by SKU : {matched_sku}")
print(f"   Matched by EAN : {matched_ean}")
print(f"   Total updated  : {matched_sku + matched_ean} / {len(products)}")
print(f"   Not matched    : {not_found}")
print(f"\ncog_updated → {catalog['cog_updated']}")
