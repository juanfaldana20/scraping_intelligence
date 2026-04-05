"""
Uber Eats MX scraper — extrae delivery fee, ETA y Coca-Cola 500ml de tiendas de conveniencia.

Flujo por zona:
  1. getFeedV1 (coords en headers) → feedItems[].carousel.stores[]
     - Busca OXXO, 7-Eleven, Walmart, etc.; fallback a fast-food / primer restaurante.
     - ETA   → tracking.storePayload.etdInfo.dropoffETARange.{min, max}
     - Promos → signposts[].text
  2. getStoreV1 (storeUuid del paso 1) → detalle + menú
     - Delivery fee → modalityInfo.modalityOptions[DELIVERY] (puede ser None en tiendas)
     - Coca-Cola 500ml → catalogSectionsMap, buscar "coca" + "500" en título

NOTA: la cookie uev2.loc lleva hardcoded una ubicación CDMX. Las 21 zonas mandan
headers diferentes pero pueden retornar la misma tienda si la cookie domina.
"""

import os
import re
import sys
import time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

_ROOT = os.path.join(os.path.dirname(__file__), "../..")
load_dotenv(dotenv_path=os.path.join(_ROOT, ".env"))
sys.path.insert(0, os.path.join(_ROOT, "src"))
from config import ZONES  # noqa: E402

COOKIES   = os.getenv("UBER_COOKIES", "")
FEED_URL  = "https://www.ubereats.com/_p/api/getFeedV1?localeCode=mx"
STORE_URL = "https://www.ubereats.com/_p/api/getStoreV1?localeCode=mx"

FEED_BODY = {
    "billboardUuid": "", "carouselId": "", "date": "", "feedProvider": "",
    "isUserInitiatedRefresh": False, "keyName": "", "promotionUuid": "",
    "searchSource": "", "searchType": "", "selectedSectionUUID": "",
    "serializedRequestContext": "", "sortAndFilters": [],
    "startTime": 0, "endTime": 0, "targetingStoreTag": "",
    "userQuery": "", "venueUUID": "", "vertical": "",
}

COLS = [
    "zona_id", "city", "zone_type", "lat", "lng", "plataforma",
    "restaurante", "delivery_fee", "eta_min", "eta_max",
    "product_price", "product_available", "product_name",
    "descuentos", "timestamp", "error",
]

# Tiendas a buscar en orden de prioridad
STORE_KEYWORDS = [
    "oxxo", "7-eleven", "7 eleven", "walmart", "chedraui",
    "soriana", "superama", "la comer", "bodega aurrera",
]

# Cadenas de fast-food (todas venden Coca-Cola)
FAST_FOOD_KEYWORDS = [
    "burger king", "carl", "subway", "domino", "pizza hut",
    "little caesars", "papa john", "kfc", "popeyes",
    "mcdonald", "mc don", "wendys", "wendy",
    "church", "tim horton",
]

# Fallback genérico
FALLBACK_KEYWORDS = ["supermercado", "abarrotes", "minisuper", "mini super"]


# ── network helpers ───────────────────────────────────────────────────────────

def _headers(lat, lng):
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://www.ubereats.com",
        "x-csrf-token": "x",
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"iOS"',
        "user-agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.5 Mobile/15E148 Safari/604.1"
        ),
        "x-uber-target-location-latitude": str(lat),
        "x-uber-target-location-longitude": str(lng),
        "referer": "https://www.ubereats.com/mx/feed?diningMode=DELIVERY",
        "cookie": COOKIES,
    }


def _check_auth(resp):
    if resp.status_code in (401, 403):
        print("  [ERROR] Cookies de Uber Eats expiradas. Renovar UBER_COOKIES en .env desde DevTools")
        return False
    return True


# ── parsers ───────────────────────────────────────────────────────────────────

def _item_title(it):
    t = it.get("title", "")
    return t.get("text", "") if isinstance(t, dict) else str(t)


def _find_items_by_keyword(obj, keyword, depth=0):
    results = []
    if depth > 8:
        return results
    if isinstance(obj, dict):
        if keyword in _item_title(obj).lower() and obj.get("price") is not None:
            results.append(obj)
        for v in obj.values():
            results.extend(_find_items_by_keyword(v, keyword, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_find_items_by_keyword(item, keyword, depth + 1))
    return results


def _parse_delivery_fee(data):
    # modalityInfo puede ser None (key existe con valor None) en tiendas de conveniencia
    modality_opts = (data.get("modalityInfo") or {}).get("modalityOptions", [])
    delivery_opt = next(
        (o for o in modality_opts if o.get("diningMode") == "DELIVERY"), None
    )
    if not delivery_opt:
        return None
    for elem in delivery_opt.get("priceTitleRichText", {}).get("richTextElements", []):
        if elem.get("type") == "text":
            txt = (elem.get("text") or {}).get("text", {})
            if isinstance(txt, dict):
                txt = txt.get("text", "")
            m = re.search(r"MXN\s*(\d+(?:\.\d+)?)", str(txt))
            if m:
                return float(m.group(1))
    return None


def _find_coca_cola_500(data):
    """Busca Coca-Cola 500ml en el menú del store."""
    # Primero buscar todos los items con "coca" en el título
    items = _find_items_by_keyword(data, "coca")

    if not items:
        return None, False, None

    # Filtrar los que tengan "500" en el título (500ml)
    coca_500 = [it for it in items if "500" in _item_title(it).lower()]
    if coca_500:
        cheapest = min(coca_500, key=lambda x: x.get("price", 999_999_99))
        title = _item_title(cheapest)
        price = round(cheapest["price"] / 100, 2)
        return price, True, title

    # Si no hay 500ml específico, tomar la Coca-Cola más barata disponible
    cheapest = min(items, key=lambda x: x.get("price", 999_999_99))
    title = _item_title(cheapest)
    price = round(cheapest["price"] / 100, 2)
    return price, True, f"{title} (no 500ml exacto)"


def _parse_discounts(store):
    texts = [sp.get("text", "") for sp in store.get("signposts", []) if sp.get("text")]
    return "; ".join(texts) or None


# ── feed: find store ──────────────────────────────────────────────────────────

def _find_store_in_feed(all_stores):
    """Busca la mejor tienda en el feed. Prioridad:
    1. Tienda de conveniencia/supermercado
    2. Cadena de fast-food (todas venden Coca-Cola)
    3. Fallback genérico
    4. Primer restaurante disponible
    """
    def _get_name(store):
        title = store.get("title", {})
        return title.get("text", "").lower() if isinstance(title, dict) else str(title).lower()

    # 1. Tiendas de conveniencia
    for keyword in STORE_KEYWORDS:
        for store in all_stores:
            if keyword in _get_name(store):
                return store, "tienda_conveniencia"

    # 2. Fast-food
    for keyword in FAST_FOOD_KEYWORDS:
        for store in all_stores:
            if keyword in _get_name(store):
                return store, "fast_food"

    # 3. Fallback genérico
    for keyword in FALLBACK_KEYWORDS:
        for store in all_stores:
            if keyword in _get_name(store):
                return store, "generico"

    # 4. Primer disponible
    if all_stores:
        return all_stores[0], "primer_disponible"

    return None, None


# ── API calls ─────────────────────────────────────────────────────────────────

def _get_feed(zone):
    hdrs = _headers(zone["lat"], zone["lng"])
    try:
        resp = requests.post(FEED_URL, headers=hdrs, json=FEED_BODY, timeout=20)
    except requests.RequestException as exc:
        return {"error": f"getFeedV1 failed: {exc}"}

    if not _check_auth(resp):
        return {"error": "Cookies expiradas"}

    try:
        d = resp.json()
    except Exception:
        return {"error": f"getFeedV1 JSON parse error (HTTP {resp.status_code})"}

    feed_items = d.get("data", {}).get("feedItems", [])
    if not feed_items:
        keys = list(d.get("data", {}).keys())
        print(f"  [WARN] feedItems vacío. data keys: {keys[:3]}")
        return {"error": "feedItems vacío"}

    all_stores = []
    for item in feed_items:
        all_stores.extend(item.get("carousel", {}).get("stores", []))

    print(f"  feed: {len(all_stores)} stores", end="")

    target_store, match_type = _find_store_in_feed(all_stores)
    if target_store:
        title = target_store.get("title", {})
        store_name = title.get("text", "") if isinstance(title, dict) else str(title)
        print(f"  | Tienda: {store_name} ({match_type})")
    else:
        print(f"  | Sin tienda disponible")
        return {"error": "sin_tienda_disponible"}

    eta_range = (
        target_store.get("tracking", {})
             .get("storePayload", {})
             .get("etdInfo", {})
             .get("dropoffETARange", {})
    )
    title = target_store.get("title", {})
    store_name = title.get("text", "") if isinstance(title, dict) else str(title)
    return {
        "storeUuid":   target_store.get("storeUuid"),
        "restaurante": store_name,
        "match_type":  match_type,
        "eta_min":     eta_range.get("min"),
        "eta_max":     eta_range.get("max"),
        "descuentos":  _parse_discounts(target_store),
    }


def _get_store_detail(zone, store_uuid):
    hdrs = _headers(zone["lat"], zone["lng"])
    body = {"storeUuid": store_uuid, "diningMode": "DELIVERY",
            "time": {"asap": True}, "cbType": "EATER_ENDORSED"}
    try:
        resp = requests.post(STORE_URL, headers=hdrs, json=body, timeout=20)
    except requests.RequestException as exc:
        return {"error": f"getStoreV1 failed: {exc}"}

    if not _check_auth(resp):
        return {"error": "Cookies expiradas"}

    try:
        data = resp.json().get("data", {})
    except Exception:
        return {"error": f"getStoreV1 JSON parse error (HTTP {resp.status_code})"}

    if not data:
        return {"error": "getStoreV1 returned empty data"}

    product_price, product_available, product_title = _find_coca_cola_500(data)

    return {
        "delivery_fee":      _parse_delivery_fee(data),
        "product_price":     product_price,
        "product_available": product_available,
        "product_name":      product_title,
    }


# ── zone orchestration ────────────────────────────────────────────────────────

def scrape_zone(zone):
    ts = datetime.now().isoformat()
    feed = _get_feed(zone)
    if "error" in feed:
        return _row(zone, ts, error=feed["error"])

    store_uuid = feed.get("storeUuid")
    if not store_uuid:
        return _row(zone, ts, error="No storeUuid in feed")

    detail = _get_store_detail(zone, store_uuid)
    if "error" in detail:
        return _row(zone, ts,
                    restaurante=feed.get("restaurante"),
                    eta_min=feed.get("eta_min"),
                    eta_max=feed.get("eta_max"),
                    descuentos=feed.get("descuentos"),
                    error=detail["error"])

    product_name = detail.get("product_name")
    match_type = feed.get("match_type", "")
    store_name = feed.get("restaurante", "N/A")
    if product_name:
        product_name = f"{product_name} @ {store_name} ({match_type})"
    else:
        product_name = f"Coca-Cola 500ml (no encontrada en menú) @ {store_name} ({match_type})"

    return _row(zone, ts,
                restaurante=feed.get("restaurante"),
                eta_min=feed.get("eta_min"),
                eta_max=feed.get("eta_max"),
                descuentos=feed.get("descuentos"),
                delivery_fee=detail.get("delivery_fee"),
                product_price=detail.get("product_price"),
                product_available=detail.get("product_available", False),
                product_name=product_name)


def _row(zone, ts, *, restaurante=None, delivery_fee=None,
         eta_min=None, eta_max=None,
         product_price=None, product_available=False, product_name=None,
         descuentos=None, error=None):
    return {
        "zona_id":           zone["id"],
        "city":              zone["city"],
        "zone_type":         zone["type"],
        "lat":               zone["lat"],
        "lng":               zone["lng"],
        "plataforma":        "uber_eats",
        "restaurante":       restaurante,
        "delivery_fee":      delivery_fee,
        "eta_min":           eta_min,
        "eta_max":           eta_max,
        "product_price":     product_price,
        "product_available": product_available,
        "product_name":      product_name,
        "descuentos":        descuentos,
        "timestamp":         ts,
        "error":             error,
    }


# ── entry points ──────────────────────────────────────────────────────────────

def run(out_path="data/raw/ubereats_full.csv"):
    rows = []
    for zone in ZONES:
        print(f"\n[uber_eats] {zone['id']} ({zone['city']} / {zone['type']})")
        try:
            rows.append(scrape_zone(zone))
        except Exception as exc:
            print(f"  [EXCEPTION] {exc}")
            rows.append(_row(zone, datetime.now().isoformat(), error=str(exc)))
        time.sleep(2)

    df = pd.DataFrame(rows, columns=COLS)
    df.to_csv(out_path, index=False)
    print(f"\n[uber_eats] CSV guardado: {out_path}  ({len(df)} filas)")
    return df


if __name__ == "__main__":
    df = run()
    print(df.to_string())
    success = int(df["product_available"].sum())
    total = len(df)
    print(f"\n[RESULTADO] {success}/{total} zonas con Coca-Cola 500ml encontrada")
