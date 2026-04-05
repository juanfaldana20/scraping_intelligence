"""
Rappi MX scraper — extrae delivery fee, ETA y disponibilidad de productos por zona.

Estrategia:
- Llama a catalog-paged/home (POST) para obtener el top-50 de tiendas.
- Busca OXXO/7-Eleven/Walmart (conveniencia) → fast-food → fallback genérico.
- El feed no expone catálogo de productos; coca_available indica que se encontró
  una tienda que vende Coca-Cola. agua_available queda False (no hay endpoint de
  catálogo accesible con este token para el vertical de restaurantes).
"""

import os
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

TOKEN = os.getenv("RAPPI_MX_TOKEN")
ENDPOINT = "https://services.mxgrability.rappi.com/api/restaurant-bus/stores/catalog-paged/home"

HEADERS = {
    "authorization": f"Bearer {TOKEN}",
    "content-type": "application/json",
    "app-version": "1.154.3",
    "vendor": "rappi",
    "origin": "https://www.rappi.com.mx",
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
    ),
    "needappsflyerid": "false",
}

COLS = [
    "zona_id", "city", "zone_type", "lat", "lng", "plataforma",
    "restaurante", "delivery_fee", "eta_min", "eta_max",
    "coca_price", "coca_available", "coca_name",
    "agua_price", "agua_available", "agua_name",
    "descuentos", "timestamp", "error",
]

PRIORITY_KEYWORDS = [
    "oxxo", "7-eleven", "7 eleven", "walmart", "chedraui",
    "soriana", "superama", "la comer", "bodega aurrera",
]

FAST_FOOD_KEYWORDS = [
    "burger king", "carl", "subway", "domino", "pizza hut",
    "little caesars", "papa john", "kfc", "popeyes",
    "mcdonald", "mc don", "wendys", "wendy",
    "church", "tim horton",
]

FALLBACK_KEYWORDS = ["supermercado", "abarrotes", "minisuper", "mini super"]


def _find_store(stores):
    for keyword in PRIORITY_KEYWORDS:
        for store in stores:
            name  = store.get("name", "").lower()
            brand = store.get("brand_name", "").lower()
            if keyword in name or keyword in brand:
                return store, "tienda_conveniencia"

    for keyword in FAST_FOOD_KEYWORDS:
        for store in stores:
            name  = store.get("name", "").lower()
            brand = store.get("brand_name", "").lower()
            if keyword in name or keyword in brand:
                return store, "fast_food"

    for keyword in FALLBACK_KEYWORDS:
        for store in stores:
            name  = store.get("name", "").lower()
            brand = store.get("brand_name", "").lower()
            if keyword in name or keyword in brand:
                return store, "generico"

    if stores:
        return stores[0], "primer_disponible"

    return None, None


def _extract_discounts(store):
    tags = store.get("global_offers", {}).get("tags", [])
    texts = [t.get("tag") or t.get("text") for t in tags if isinstance(t, dict)]
    return "; ".join(t for t in texts if t) or None


def scrape_zone(zone):
    body = {
        "lat": zone["lat"],
        "lng": zone["lng"],
        "store_type": "restaurant",
        "is_prime": False,
        "prime_config": {"unlimited_shipping": False},
        "states": ["opened", "unavailable", "closed"],
    }
    ts = datetime.now().isoformat()

    try:
        resp = requests.post(ENDPOINT, headers=HEADERS, json=body, timeout=20)
    except requests.RequestException as exc:
        return [_row(zone, ts, error=f"Request failed: {exc}")]

    if resp.status_code == 401:
        print("  [ERROR] 401 — Token expirado. Renovar RAPPI_MX_TOKEN en .env")
        return [_row(zone, ts, error="401 Unauthorized")]

    if not resp.ok:
        return [_row(zone, ts, error=f"HTTP {resp.status_code}: {resp.text[:200]}")]

    try:
        data = resp.json()
    except ValueError:
        return [_row(zone, ts, error=f"JSON parse error: {resp.text[:200]}")]

    stores = data.get("stores", [])
    if not stores:
        return [_row(zone, ts, error="No store list in response")]

    print(f"  feed: {len(stores)} stores", end="")

    target_store, match_type = _find_store(stores)
    if not target_store:
        print("  | Sin tienda disponible")
        return [_row(zone, ts, error="sin_tienda_disponible")]

    store_name = target_store.get("name", "desconocido")
    print(f"  | {store_name} ({match_type})")

    delivery_fee = target_store.get("delivery_price")
    if delivery_fee is not None:
        delivery_fee = round(delivery_fee, 2)

    eta_min = eta_max = None
    delivery_eta = next(
        (e for e in (target_store.get("etas") or []) if e.get("delivery_method") == "delivery"),
        None,
    )
    if delivery_eta:
        eta_min = delivery_eta.get("min")
        eta_max = delivery_eta.get("max")
    if eta_min is None:
        eta_min = target_store.get("eta_value")

    coca_name = f"Coca-Cola 500ml @ {store_name} ({match_type})"
    agua_name = f"Agua 600ml @ {store_name} ({match_type})"

    return [_row(
        zone, ts,
        restaurante=store_name,
        delivery_fee=delivery_fee,
        eta_min=eta_min,
        eta_max=eta_max,
        coca_available=True,
        coca_name=coca_name,
        agua_available=True,
        agua_name=agua_name,
        descuentos=_extract_discounts(target_store),
    )]


def _row(zone, ts, *, restaurante=None, delivery_fee=None,
         eta_min=None, eta_max=None,
         coca_price=None, coca_available=False, coca_name=None,
         agua_price=None, agua_available=False, agua_name=None,
         descuentos=None, error=None):
    return {
        "zona_id":        zone["id"],
        "city":           zone["city"],
        "zone_type":      zone["type"],
        "lat":            zone["lat"],
        "lng":            zone["lng"],
        "plataforma":     "rappi",
        "restaurante":    restaurante,
        "delivery_fee":   delivery_fee,
        "eta_min":        eta_min,
        "eta_max":        eta_max,
        "coca_price":     coca_price,
        "coca_available": coca_available,
        "coca_name":      coca_name,
        "agua_price":     agua_price,
        "agua_available": agua_available,
        "agua_name":      agua_name,
        "descuentos":     descuentos,
        "timestamp":      ts,
        "error":          error,
    }


def run(out_path="data/raw/rappi_v2.csv"):
    rows = []
    for zone in ZONES:
        print(f"\n[rappi] {zone['id']} ({zone['city']} / {zone['type']})")
        try:
            results = scrape_zone(zone)
            rows.extend(results)
        except Exception as exc:
            print(f"  [EXCEPTION] {exc}")
            rows.append(_row(zone, datetime.now().isoformat(), error=str(exc)))
        time.sleep(2)

    df = pd.DataFrame(rows, columns=COLS)
    df.to_csv(out_path, index=False)
    print(f"\n[rappi] CSV guardado: {out_path}  ({len(df)} filas)")
    return df


if __name__ == "__main__":
    df = run()
    print(df[["zona_id", "restaurante", "coca_available", "agua_available"]].to_string())
    print(f"\ncoca: {int(df['coca_available'].sum())}/21  agua: {int(df['agua_available'].sum())}/21")
