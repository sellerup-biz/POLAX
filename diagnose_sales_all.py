"""
Полная диагностика продаж PolaxEuroGroup за январь 2026.
Забираем ВСЕ возможные данные из payments API.
"""
import requests, json, os, base64
from nacl import encoding, public

REDIRECT_URI = "https://sellerup-biz.github.io/POLAX/callback.html"
GH_TOKEN     = os.environ.get("GH_TOKEN","")
GH_REPO      = "sellerup-biz/POLAX"

DATE_FROM = "2026-01-01T00:00:00+01:00"
DATE_TO   = "2026-01-31T23:59:59+01:00"

ETALON = {
    "allegro-pl":   33998.72,
    "allegro-cz":   1613.00,
    "allegro-hu":   3790.00,
    "allegro-sk":   93.36,
}

def save_token(new_rt):
    if not new_rt or not GH_TOKEN: return
    try:
        r   = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
                           headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"})
        key = r.json()
        pk  = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
        enc = base64.b64encode(public.SealedBox(pk).encrypt(new_rt.encode())).decode()
        requests.put(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/REFRESH_TOKEN_POLAX",
                     headers={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"},
                     json={"encrypted_value":enc,"key_id":key["key_id"]})
        print("  Токен сохранён")
    except Exception as e: print(f"  Ошибка: {e}")

def get_token():
    r = requests.post("https://allegro.pl/auth/oauth/token",
                      auth=(os.environ["CLIENT_ID_POLAX"], os.environ["CLIENT_SECRET_POLAX"]),
                      data={"grant_type":"refresh_token",
                            "refresh_token":os.environ["REFRESH_TOKEN_POLAX"],
                            "redirect_uri":REDIRECT_URI})
    d = r.json()
    if "access_token" not in d: print(f"ОШИБКА: {d}"); exit(1)
    save_token(d.get("refresh_token",""))
    return d["access_token"]

def hdrs(t):
    return {"Authorization":f"Bearer {t}","Accept":"application/vnd.allegro.public.v1+json"}

def fetch_all_ops(token, params_extra={}):
    """Забирает все операции, проверяет totalCount"""
    ops    = []
    offset = 0
    total_count = None
    base_params = {"occurredAt.gte":DATE_FROM,"occurredAt.lte":DATE_TO,"limit":50}
    base_params.update(params_extra)
    while True:
        base_params["offset"] = offset
        resp  = requests.get("https://api.allegro.pl/payments/payment-operations",
                             headers=hdrs(token), params=base_params).json()
        batch = resp.get("paymentOperations",[])
        if total_count is None:
            total_count = resp.get("totalCount", "?")
        ops.extend(batch)
        if len(batch) < 50: break
        offset += 50
        if offset >= 10000: print("  ⚠ Достигнут лимит offset=10000!"); break
    return ops, total_count

token = get_token()
print(f"Токен: OK\n")

# ── 1. БЕЗ ФИЛЬТРОВ — все операции все группы ────────────────
print("="*70)
print("1. ВСЕ операции без фильтров (все группы, все кошельки)")
print("="*70)
ops_all, tc = fetch_all_ops(token)
print(f"   Получено: {len(ops_all)} | totalCount: {tc}")
by_group_type = {}
for op in ops_all:
    key = f"{op.get('group','?')}/{op.get('type','?')}"
    amt = float(op["value"]["amount"])
    cur = op["value"]["currency"]
    mkt = op.get("marketplaceId","НЕТ")
    if key not in by_group_type:
        by_group_type[key] = {"total_pln":0,"cnt":0,"cur":cur,"mkts":set()}
    by_group_type[key]["total_pln"] += amt
    by_group_type[key]["cnt"] += 1
    by_group_type[key]["mkts"].add(mkt or "НЕТ")
for key in sorted(by_group_type, key=lambda x:-abs(by_group_type[x]["total_pln"])):
    v = by_group_type[key]
    mkts = ",".join(sorted(v["mkts"]))
    print(f"  {key:<35} {v['total_pln']:>12.2f} {v['cur']}  ({v['cnt']} шт) mkts:{mkts}")

# ── 2. ТОЛЬКО INCOME — каждый маркетплейс ─────────────────────
print(f"\n{'='*70}")
print("2. INCOME по маркетплейсам в локальной валюте")
print("="*70)
print(f"  {'Маркетплейс':<25} {'НАШИ':>12} {'totalCount':>12} {'ЭТАЛОН':>12} {'РАЗНИЦА':>10}")
print(f"  {'─'*25} {'─'*12} {'─'*12} {'─'*12} {'─'*10}")

results = {}
for mkt in ["allegro-pl","allegro-business-pl","allegro-cz","allegro-hu","allegro-sk"]:
    ops, tc = fetch_all_ops(token, {"group":"INCOME","marketplaceId":mkt})
    # Суммируем в локальной валюте (без конвертации)
    total_local = round(sum(float(op["value"]["amount"]) for op in ops), 2)
    results[mkt] = {"total":total_local,"ops":ops,"tc":tc}
    ref = ETALON.get(mkt)
    if ref:
        diff = total_local - ref
        ok   = "✅" if abs(diff) < 1 else "❌"
        print(f"  {mkt:<25} {total_local:>12.2f} {str(tc):>12} {ref:>12.2f} {diff:>+10.2f}  {ok}")
    else:
        print(f"  {mkt:<25} {total_local:>12.2f} {str(tc):>12} {'—':>12}")

# ── 3. Типы операций по CZ — откуда +302 ──────────────────────
print(f"\n{'='*70}")
print("3. Детали CZ — ищем откуда +302 CZK лишних")
print("="*70)
cz_ops = results["allegro-cz"]["ops"]
by_type = {}
for op in cz_ops:
    key = f"{op.get('group','?')}/{op.get('type','?')}"
    amt = float(op["value"]["amount"])
    if key not in by_type: by_type[key] = 0.0
    by_type[key] += amt
for key, amt in sorted(by_type.items(), key=lambda x:-abs(x[1])):
    print(f"  {key:<35} {amt:>12.2f} CZK")

# ── 4. Типы операций по PL + business-PL ─────────────────────
print(f"\n{'='*70}")
print("4. Детали PL — все типы операций")
print("="*70)
for mkt in ["allegro-pl","allegro-business-pl"]:
    ops = results[mkt]["ops"]
    by_type = {}
    for op in ops:
        key = f"{op.get('group','?')}/{op.get('type','?')}"
        amt = float(op["value"]["amount"])
        if key not in by_type: by_type[key] = 0.0
        by_type[key] += amt
    total = sum(by_type.values())
    print(f"\n  {mkt}: {total:.2f} PLN")
    for key, amt in sorted(by_type.items(), key=lambda x:-abs(x[1])):
        print(f"    {key:<35} {amt:>12.2f} PLN")

# ── 5. Операции БЕЗ marketplaceId ────────────────────────────
print(f"\n{'='*70}")
print("5. Операции БЕЗ marketplaceId (INCOME, не привязаны к стране)")
print("="*70)
ops_no_mkt = [op for op in ops_all
              if op.get("group")=="INCOME" and not op.get("marketplaceId")]
total_no_mkt = round(sum(float(op["value"]["amount"]) for op in ops_no_mkt), 2)
print(f"  Количество: {len(ops_no_mkt)} | Сумма: {total_no_mkt:.2f}")
by_type = {}
for op in ops_no_mkt:
    key = op.get("type","?")
    amt = float(op["value"]["amount"])
    if key not in by_type: by_type[key] = 0.0
    by_type[key] += amt
for key, amt in sorted(by_type.items(), key=lambda x:-abs(x[1])):
    print(f"  {key:<35} {amt:>12.2f}")

# ── 6. ИТОГ ───────────────────────────────────────────────────
print(f"\n{'='*70}")
print("6. ИТОГ — сумма всех PL маркетплейсов")
print("="*70)
pl  = results["allegro-pl"]["total"]
biz = results["allegro-business-pl"]["total"]
print(f"  allegro-pl:          {pl:>12.2f} PLN")
print(f"  allegro-business-pl: {biz:>12.2f} PLN")
print(f"  ИТОГО:               {pl+biz:>12.2f} PLN")
print(f"  Эталон:              {'33998.72':>12} PLN")
print(f"  Разница:             {(pl+biz)-33998.72:>+12.2f} PLN")
