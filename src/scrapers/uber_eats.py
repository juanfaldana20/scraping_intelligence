"""
Uber Eats MX scraper — extrae delivery fee, ETA y precio Big Mac de McDonald's.

Flujo:
  1. getFeedV1 (headers llevan las coordenadas) → lista de restaurantes
     - McDonald's vive en feedItems[].carousel.stores[]
     - ETA → tracking.storePayload.etdInfo.dropoffETARange.{min, max}
     - Descuentos → signposts[].text
  2. getStoreV1 (con storeUuid del paso 1) → detalle del restaurante + menú
     - Delivery fee → modalityInfo.modalityOptions[DELIVERY].priceTitleRichText
       (texto tipo "Costo de envío a MXN15" → parsear número)
     - Big Mac → catalogSectionsMap buscar item con title exacto "Big Mac"
       precio en centavos, dividir entre 100 para MXN

Si cookies expiran: el status puede ser 200 con redirect a login,
o directamente 401/403.
"""

import os
import re
import time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

COOKIES = os.getenv("UBER_COOKIES", "")

FEED_URL  = "https://www.ubereats.com/_p/api/getFeedV1?localeCode=mx"
STORE_URL = "https://www.ubereats.com/_p/api/getStoreV1?localeCode=mx"

ZONES = [
    {"zona": "CDMX Polanco",    "lat": 19.4326, "lng": -99.1950},
    {"zona": "CDMX Roma Norte", "lat": 19.4195, "lng": -99.1575},
    {"zona": "GDL Chapultepec", "lat": 20.6736, "lng": -103.3820},
]

FEED_BODY = {
    "billboardUuid": "", "carouselId": "", "date": "", "feedProvider": "",
    "isUserInitiatedRefresh": False, "keyName": "", "promotionUuid": "",
    "searchSource": "", "searchType": "", "selectedSectionUUID": "",
    "serializedRequestContext": "", "sortAndFilters": [],
    "startTime": 0, "endTime": 0, "targetingStoreTag": "",
    "userQuery": "", "venueUUID": "", "vertical": "",
}


def _headers(lat: float, lng: float) -> dict:
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://www.ubereats.com",
        "x-csrf-token": "x",
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"iOS"',
        "user-agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
        ),
        "x-uber-target-location-latitude": str(lat),
        "x-uber-target-location-longitude": str(lng),
        "referer": "https://www.ubereats.com/mx/feed?diningMode=DELIVERY",
        "cookie": COOKIES,
    }


def _check_auth(resp) -> bool:
    """Returns False and prints message if session looks expired."""
    if resp.status_code in (401, 403):
        print("  [ERROR] Cookies de Uber Eats expiradas. Renovar UBER_COOKIES en .env desde DevTools")
        return False
    if resp.status_code == 200:
        try:
            d = resp.json()
        except Exception:
            return True
        # Redirect / empty data can mean expired session
        if d.get("status") == "success" and not d.get("data"):
            print("  [WARN] Response vacío — posible sesión expirada.")
        return True
    return True


# ── helpers ──────────────────────────────────────────────────────────────────

def _find_items_by_title(obj, keyword: str, depth: int = 0) -> list:
    """Recursively collect dicts that have a 'title' containing keyword and a 'price'."""
    results = []
    if depth > 8:
        return results
    if isinstance(obj, dict):
        title_raw = obj.get("title", "")
        title_text = title_raw.get("text", "") if isinstance(title_raw, dict) else str(title_raw)
        if keyword in title_text.lower() and obj.get("price") is not None:
            results.append(obj)
        for v in obj.values():
            results.extend(_find_items_by_title(v, keyword, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_find_items_by_title(item, keyword, depth + 1))
    return results


def _parse_delivery_fee(data: dict):
    """Extract delivery fee (MXN float) from modalityInfo rich text."""
    modality_opts = data.get("modalityInfo", {}).get("modalityOptions", [])
    delivery_opt = next(
        (o for o in modality_opts if o.get("diningMode") == "DELIVERY"), None
    )
    if not delivery_opt:
        return None
    price_rich = delivery_opt.get("priceTitleRichText", {})
    for elem in price_rich.get("richTextElements", []):
        if elem.get("type") == "text":
            txt = elem.get("text", {}).get("text", {}).get("text", "")
            # e.g. "Costo de envío a MXN0" or " Costo de envío MXN15"
            m = re.search(r"MXN\s*(\d+(?:\.\d+)?)", txt)
            if m:
                return float(m.group(1))
    return None


def _parse_big_mac_price(data: dict):
    """Return price in MXN of the standalone Big Mac (not a combo)."""
    bm_items = _find_items_by_title(data, "big mac")
    # Prefer exact title match (solo burger, not a combo/trio)
    exact = [
        it for it in bm_items
        if re.match(r"^big mac$", _item_title(it).strip(), re.IGNORECASE)
    ]
    candidates = exact if exact else bm_items
    if not candidates:
        return None
    # Pick the cheapest among candidates (most likely standalone)
    cheapest = min(candidates, key=lambda x: x.get("price", 999999))
    return round(cheapest["price"] / 100, 2)


def _item_title(it: dict) -> str:
    t = it.get("title", "")
    return t.get("text", "") if isinstance(t, dict) else str(t)


def _parse_discounts_feed(store: dict) -> str:
    """Extract promo text from signposts in feed store object."""
    texts = [sp.get("text", "") for sp in store.get("signposts", []) if sp.get("text")]
    return "; ".join(texts) if texts else None


# ── main steps ───────────────────────────────────────────────────────────────

def get_feed(zone: dict) -> dict:
    """Call getFeedV1 and return the first McDonald's store dict found, or error."""
    hdrs = _headers(zone["lat"], zone["lng"])
    try:
        resp = requests.post(FEED_URL, headers=hdrs, json=FEED_BODY, timeout=20)
    except requests.RequestException as exc:
        return {"error": f"getFeedV1 request failed: {exc}"}

    if not _check_auth(resp):
        return {"error": "Cookies expiradas — ver mensaje arriba"}

    try:
        d = resp.json()
    except Exception:
        return {"error": f"getFeedV1 JSON parse error (status {resp.status_code})"}

    feed_items = d.get("data", {}).get("feedItems", [])
    if not feed_items:
        keys = list(d.get("data", {}).keys())
        print(f"  [WARN] feedItems vacío. data keys: {keys[:3]}")
        return {"error": "feedItems vacío"}

    print(f"  feedItems: {len(feed_items)} carousels")

    all_stores = []
    for item in feed_items:
        all_stores.extend(item.get("carousel", {}).get("stores", []))

    print(f"  Total stores in feed: {len(all_stores)}")

    mcd = [s for s in all_stores if "mcdonald" in s.get("title", {}).get("text", "").lower()]
    print(f"  McDonald's found: {len(mcd)}")

    if not mcd:
        return {"error": "No McDonald's in feed for this zone"}

    store = mcd[0]
    eta_range = (
        store.get("tracking", {})
             .get("storePayload", {})
             .get("etdInfo", {})
             .get("dropoffETARange", {})
    )

    return {
        "storeUuid":   store.get("storeUuid"),
        "restaurante": store.get("title", {}).get("text"),
        "eta_min":     eta_range.get("min"),
        "eta_max":     eta_range.get("max"),
        "descuentos":  _parse_discounts_feed(store),
    }


def get_store_detail(zone: dict, store_uuid: str) -> dict:
    """Call getStoreV1 and return delivery_fee and big_mac_price."""
    hdrs = _headers(zone["lat"], zone["lng"])
    body = {
        "storeUuid":  store_uuid,
        "diningMode": "DELIVERY",
        "time":       {"asap": True},
        "cbType":     "EATER_ENDORSED",
    }
    try:
        resp = requests.post(STORE_URL, headers=hdrs, json=body, timeout=20)
    except requests.RequestException as exc:
        return {"error": f"getStoreV1 request failed: {exc}"}

    if not _check_auth(resp):
        return {"error": "Cookies expiradas — ver mensaje arriba"}

    try:
        data = resp.json().get("data", {})
    except Exception:
        return {"error": f"getStoreV1 JSON parse error (status {resp.status_code})"}

    return {
        "delivery_fee":   _parse_delivery_fee(data),
        "big_mac_price":  _parse_big_mac_price(data),
    }


# ── orchestration ─────────────────────────────────────────────────────────────

def scrape_zone(zone: dict) -> dict:
    feed = get_feed(zone)
    if "error" in feed:
        return {**feed, "delivery_fee": None, "big_mac_price": None}

    store_uuid = feed.get("storeUuid")
    if not store_uuid:
        return {**feed, "error": "No storeUuid in feed result", "delivery_fee": None, "big_mac_price": None}

    detail = get_store_detail(zone, store_uuid)
    return {**feed, **detail}


def main():
    rows = []

    for zone in ZONES:
        print(f"\nZona: {zone['zona']} ({zone['lat']}, {zone['lng']})")
        result = scrape_zone(zone)

        rows.append({
            "zona":          zone["zona"],
            "lat":           zone["lat"],
            "lng":           zone["lng"],
            "restaurante":   result.get("restaurante"),
            "delivery_fee":  result.get("delivery_fee"),
            "eta_min":       result.get("eta_min"),
            "eta_max":       result.get("eta_max"),
            "big_mac_price": result.get("big_mac_price"),
            "descuentos":    result.get("descuentos"),
            "error":         result.get("error"),
        })

        time.sleep(2)

    df = pd.DataFrame(rows, columns=[
        "zona", "lat", "lng", "restaurante", "delivery_fee",
        "eta_min", "eta_max", "big_mac_price", "descuentos", "error"
    ])
    out_path = "data/raw/ubereats_test.csv"
    df.to_csv(out_path, index=False)
    print(f"\nCSV guardado en {out_path}")
    print(df.to_string())

    success = df["delivery_fee"].notna().any()
    print(
        "\n[RESULTADO]",
        "OK — datos reales obtenidos." if success
        else "FALLO — todas las filas tienen error. Revisar cookies en .env"
    )


if __name__ == "__main__":
    main()
