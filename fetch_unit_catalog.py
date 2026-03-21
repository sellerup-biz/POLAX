"""
POLAX — Импорт каталога товаров из Allegro (польский рынок)

Что делает:
  • Обходит все активные офферы каждого магазина (allegro-pl)
  • Определяет польские названия категорий через Allegro API
  • Объединяет офферы разных магазинов по EAN / SKU (external.id)
  • Сохраняет products.json  — каталог товаров с COG=null
  • Сохраняет unit_data/categories.json — кэш id→название (польский)

Запуск:
  python fetch_unit_catalog.py                   (локально, .env)
  unit_catalog.yml → workflow_dispatch           (GitHub Actions)

Env:
  CATALOG_LIMIT   = 50   (0 = все офферы без ограничений)
  CATALOG_SHOP    = all  (all | Mlot_i_Klucz | PolaxEuroGroup | Sila_Narzedzi)
  CLIENT_ID_*  /  CLIENT_SECRET_*  /  REFRESH_TOKEN_*  (x3 магазина)
  GH_TOKEN — для сохранения ротированных refresh_token
"""

import requests, json, os, base64, time
from datetime import datetime
from nacl import encoding, public

# ── Env ───────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REDIRECT_URI  = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN      = os.environ.get("GH_TOKEN", "")
GH_REPO       = "sellerup-biz/POLAX"
CATALOG_LIMIT = int(os.environ.get("CATALOG_LIMIT", "0"))
CATALOG_SHOP  = os.environ.get("CATALOG_SHOP", "all")

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


# ── Auth ──────────────────────────────────────────────────────

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
        print(f"  {status} Токен {secret_name}")
    except Exception as e:
        print(f"  ⚠ save_token {secret_name}: {e}")


def get_token(shop):
    r = requests.post(
        "https://allegro.pl/auth/oauth/token",
        auth=(shop["client_id"], shop["client_secret"]),
        data={"grant_type": "refresh_token", "refresh_token": shop["refresh_token"],
              "redirect_uri": REDIRECT_URI},
        timeout=30)
    d = r.json()
    if "access_token" not in d:
        print(f"  ❌ ОШИБКА токена: {d}")
        return None, None
    return d["access_token"], d.get("refresh_token", "")


def hdrs(token):
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.allegro.public.v1+json"}


# ── Categories cache ──────────────────────────────────────────

def load_categories():
    os.makedirs("unit_data", exist_ok=True)
    try:
        with open("unit_data/categories.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_categories(cache):
    os.makedirs("unit_data", exist_ok=True)
    with open("unit_data/categories.json", "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"  💾 categories.json: {len(cache)} категорий")


def resolve_category(token, cat_id, cache):
    """Return Polish category name, fetching from API if not cached."""
    if not cat_id:
        return ""
    if cat_id in cache:
        return cache[cat_id]
    try:
        resp = requests.get(
            f"https://api.allegro.pl/sale/categories/{cat_id}",
            headers=hdrs(token), timeout=10)
        if resp.status_code == 200:
            name = resp.json().get("name", cat_id)
            cache[cat_id] = name
            return name
        else:
            cache[cat_id] = cat_id   # don't retry broken IDs
    except Exception as e:
        print(f"\n  ⚠ category {cat_id}: {e}")
    return cat_id


# ── EAN extraction ────────────────────────────────────────────

def extract_ean(offer):
    """
    Extract EAN/GTIN from offer parameters or productSet.
    Works on full offer detail (from GET /sale/offers/{id}).
    /sale/offers list does NOT return parameters — need individual fetch.
    """
    # 1. parameters array (standard)
    for param in offer.get("parameters", []):
        name_lc = param.get("name", "").lower()
        if "ean" in name_lc or "gtin" in name_lc:
            vals = param.get("values", [])
            if vals:
                v = str(vals[0]).strip()
                if v.isdigit() and 8 <= len(v) <= 14:
                    return v
    # 2. productSet → product.id (GTIN/EAN stored as product identifier)
    for ps in offer.get("productSet", []):
        prod = ps.get("product") or {}
        pid = prod.get("id", "")
        if pid and pid.isdigit() and 8 <= len(pid) <= 14:
            return pid
    return None


def fetch_offer_detail(token, offer_id):
    """Fetch full offer detail to get parameters (EAN etc.).
    Uses /sale/product-offers/{id} — the current supported endpoint.
    Old /sale/offers/{id} is deprecated and blocked since 2025."""
    resp = requests.get(
        f"https://api.allegro.pl/sale/product-offers/{offer_id}",
        headers=hdrs(token),
        timeout=30)
    if resp.status_code == 200:
        return resp.json()
    return {}


# ── Offers fetch ──────────────────────────────────────────────

def get_offers_for_shop(token, shop_name, cat_cache, limit=0):
    """
    Fetch all active allegro-pl offers for a shop.
    Step 1: /sale/offers list (id, name, sku, category, price)
    Step 2: /sale/offers/{id} detail per offer (to get parameters → EAN)
    Returns list of normalized dicts:
      {offerId, name, ean, sku, category, cat_id, price}
    """
    offers = []
    offset = 0
    page   = 100

    while True:
        resp = requests.get(
            "https://api.allegro.pl/sale/offers",
            headers=hdrs(token),
            params={
                "publication.status": "ACTIVE",
                "marketplaceId":      "allegro-pl",
                "limit":              page,
                "offset":             offset,
            },
            timeout=30)

        if resp.status_code != 200:
            print(f"\n  ⚠ /sale/offers offset={offset}: HTTP {resp.status_code} → {resp.text[:200]}")
            break

        data  = resp.json()
        batch = data.get("offers", [])
        total = data.get("totalCount", "?")

        for offer in batch:
            cat_id   = offer.get("category", {}).get("id", "")
            cat_name = resolve_category(token, cat_id, cat_cache)
            sku      = (offer.get("external") or {}).get("id", "")

            price_raw = (offer.get("sellingMode") or {}).get("price", {}).get("amount")
            price     = round(float(price_raw), 2) if price_raw else None

            offers.append({
                "offerId":  offer["id"],
                "name":     offer.get("name", "").strip(),
                "ean":      None,   # filled in step 2
                "sku":      sku.strip(),
                "category": cat_name,
                "cat_id":   cat_id,
                "price":    price,
            })

            if limit > 0 and len(offers) >= limit:
                print(f"  {shop_name}: ограничено до {limit} офферов")
                break

        print(f"  {shop_name}: {len(offers)}/{total} офферов...", end="\r")

        if limit > 0 and len(offers) >= limit:
            break
        if len(batch) < page:
            break
        offset += page
        time.sleep(0.15)

    # Step 2: fetch individual offer details to get EAN from parameters
    print(f"\n  {shop_name}: получаем EAN для {len(offers)} офферов...")
    ean_found = 0
    for i, o in enumerate(offers):
        detail = fetch_offer_detail(token, o["offerId"])
        ean = extract_ean(detail)
        if ean:
            o["ean"] = ean
            ean_found += 1
        time.sleep(0.1)
        if (i + 1) % 50 == 0:
            print(f"    {i+1}/{len(offers)} обработано, EAN найдено: {ean_found}")
    print(f"  {shop_name}: EAN найдено {ean_found}/{len(offers)}")

    print(f"  {shop_name}: итого {len(offers)} офферов              ")
    return offers


# ── Merge across shops ────────────────────────────────────────

def build_products(all_shop_offers, existing_products):
    """
    Merge offers from all shops into unified product entries.
    Merge key priority: EAN → SKU → offerId (as fallback).
    Preserves existing COG data from products.json.
    """
    # Build lookup for existing COG and SKU from current products.json
    existing_cog = {}   # key → {shop: cog}
    existing_sku = {}   # key → sku

    for p in existing_products:
        key = _product_key(p.get("ean", ""), p.get("sku", ""),
                           next((v for v in p.get("offers", {}).values() if v), ""))
        existing_cog[key] = p.get("cog", {})
        existing_sku[key] = p.get("sku", "")

    merged = {}   # key → product dict

    for shop_name, offers in all_shop_offers.items():
        for o in offers:
            key = _product_key(o["ean"], o["sku"], o["offerId"])

            if key not in merged:
                merged[key] = {
                    "ean":      o["ean"] or "",
                    "sku":      o["sku"] or "",
                    "name":     o["name"],
                    "category": o["category"],
                    "cog": {
                        "Mlot_i_Klucz":   None,
                        "PolaxEuroGroup": None,
                        "Sila_Narzedzi":  None,
                    },
                    "offers": {
                        "Mlot_i_Klucz":   None,
                        "PolaxEuroGroup": None,
                        "Sila_Narzedzi":  None,
                    },
                    "price": {},
                }
                # Restore existing COG
                if key in existing_cog:
                    for s, v in existing_cog[key].items():
                        if v is not None:
                            merged[key]["cog"][s] = v

            merged[key]["offers"][shop_name] = o["offerId"]
            if o["price"]:
                merged[key]["price"][shop_name] = o["price"]
            # Fill gaps
            if not merged[key]["ean"] and o["ean"]:
                merged[key]["ean"] = o["ean"]
            if not merged[key]["sku"] and o["sku"]:
                merged[key]["sku"] = o["sku"]
            if not merged[key]["name"] and o["name"]:
                merged[key]["name"] = o["name"]

    return list(merged.values())


def _product_key(ean, sku, offer_id):
    if ean:
        return f"ean:{ean}"
    if sku:
        return f"sku:{sku}"
    return f"offer:{offer_id}"


# ── products.json I/O ─────────────────────────────────────────

def load_products():
    try:
        with open("products.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"updated": "", "products": []}


def save_products(products_list):
    data = {
        "updated":  datetime.utcnow().strftime("%Y-%m-%d"),
        "count":    len(products_list),
        "products": products_list,
    }
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n💾 products.json: {len(products_list)} товаров")


# ── MAIN ──────────────────────────────────────────────────────

print("=" * 65)
print("  POLAX — Импорт каталога товаров из Allegro")
limit_str = f"LIMIT={CATALOG_LIMIT}" if CATALOG_LIMIT else "без лимита"
shop_str  = CATALOG_SHOP if CATALOG_SHOP != "all" else "все магазины"
print(f"  {shop_str} · {limit_str}")
print("=" * 65)

cat_cache = load_categories()
existing  = load_products()
existing_products = existing.get("products", [])
print(f"  Существующих товаров в products.json: {len(existing_products)}")
print(f"  Кэш категорий: {len(cat_cache)} записей")

pubkey         = get_gh_pubkey()
all_shop_offers = {}

# ── Определяем магазины для обхода ───────────────────────────
shops_to_run = (
    {k: v for k, v in SHOPS.items() if k == CATALOG_SHOP}
    if CATALOG_SHOP != "all"
    else SHOPS
)

# ── Получаем токены и загружаем офферы ───────────────────────
for shop_name, shop in shops_to_run.items():
    print(f"\n── {shop_name} ──────────────────────────────────────────")
    token, new_rt = get_token(shop)
    if not token:
        print(f"  ❌ Пропускаем {shop_name}")
        continue
    save_token(shop["secret_name"], new_rt, pubkey)

    offers = get_offers_for_shop(token, shop_name, cat_cache, limit=CATALOG_LIMIT)
    all_shop_offers[shop_name] = offers
    save_categories(cat_cache)   # save after each shop (incremental)

# ── Объединяем и сохраняем ────────────────────────────────────
if all_shop_offers:
    products = build_products(all_shop_offers, existing_products)
    save_products(products)

    # Summary
    print("\n── Итог ────────────────────────────────────────────────")
    for shop in SHOPS:
        n = sum(1 for p in products if p["offers"].get(shop))
        print(f"  {shop:<22} {n:>4} офферов")
    cats = sorted({p["category"] for p in products if p["category"]})
    print(f"\n  Категорий: {len(cats)}")
    for c in cats[:20]:
        print(f"    • {c}")
    if len(cats) > 20:
        print(f"    … и ещё {len(cats)-20}")
else:
    print("⚠ Нет данных для сохранения")

print("\n✅ Каталог импортирован.")
