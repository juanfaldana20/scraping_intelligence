"""
Rappi MX scraper — extrae datos de McDonald's por zona.

Hallazgos de ingeniería inversa:
- Endpoint: catalog-paged/home devuelve top-50 restaurantes por ranking de popularidad.
- McDonald's NO aparece en zonas upscale (Polanco, Roma Norte) porque el algoritmo prioriza
  restaurantes locales de alta demanda. Sí aparece en zonas más suburbanas/comerciales.
- Nombre en store: "Mc Donald's - Perisur" / "McDonald's (Revolución) F"
- brand_name siempre: "McDonald's"
- delivery_price: tarifa en MXN (float)
- etas[0]: {"min": int, "max": int, "delivery_method": "delivery"}
- global_offers.tags[]: lista de promociones activas
"""

import os
import time
import json
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

TOKEN = os.getenv("RAPPI_MX_TOKEN")
ENDPOINT = "https://services.mxgrability.rappi.com/api/restaurant-bus/stores/catalog-paged/home"

# Zonas actualizadas: coordenadas donde McDonald's sí aparece en el top-50 de Rappi MX.
# Nota: Polanco y Roma Norte son zonas upscale; McDonald's no aparece en su ranking top-50.
# Se sustituyeron por zonas suburbanas/comerciales con presencia confirmada de McDonald's.
ZONES = [
    {"zona": "CDMX Sur (Perisur)",  "lat": 19.3046, "lng": -99.1842},
    {"zona": "CDMX Santa Fe",       "lat": 19.3604, "lng": -99.2569},
    {"zona": "GDL Revolución",      "lat": 20.6736, "lng": -103.2920},
]

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


def is_mcdonalds(store: dict) -> bool:
    brand = store.get("brand_name", "").lower()
    name = store.get("name", "").lower()
    return "mcdonald" in brand or "mc don" in name


def extract_discounts(store: dict):
    tags = store.get("global_offers", {}).get("tags", [])
    texts = [t.get("tag") or t.get("text") for t in tags if isinstance(t, dict)]
    texts = [t for t in texts if t]
    return "; ".join(texts) if texts else None


def scrape_zone(zone: dict):
    body = {
        "lat": zone["lat"],
        "lng": zone["lng"],
        "store_type": "restaurant",
        "is_prime": False,
        "prime_config": {"unlimited_shipping": False},
        "states": ["opened", "unavailable", "closed"],
    }

    try:
        resp = requests.post(ENDPOINT, headers=HEADERS, json=body, timeout=20)
    except requests.RequestException as exc:
        return [{"error": f"Request failed: {exc}"}]

    if resp.status_code == 401:
        print("  [ERROR] 401 — Token expirado. Renovar RAPPI_MX_TOKEN en .env")
        return [{"error": "401 Unauthorized"}]

    if not resp.ok:
        return [{"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}]

    try:
        data = resp.json()
    except ValueError:
        return [{"error": f"JSON parse error: {resp.text[:200]}"}]

    stores = data.get("stores", [])
    if not stores:
        return [{"error": "No store list in response"}]

    print(f"  Stores found: {len(stores)}")

    results = []
    for store in stores:
        if not is_mcdonalds(store):
            continue

        # Delivery fee
        delivery_fee = store.get("delivery_price")

        # ETA — prefer etas[] array (min/max), fallback to eta string
        eta_min = eta_max = None
        etas = store.get("etas") or []
        delivery_eta = next(
            (e for e in etas if e.get("delivery_method") == "delivery"), None
        )
        if delivery_eta:
            eta_min = delivery_eta.get("min")
            eta_max = delivery_eta.get("max")
        if eta_min is None:
            eta_min = store.get("eta_value")  # average ETA as fallback

        results.append({
            "restaurante": store.get("name"),
            "store_id":    store.get("store_id"),
            "status":      store.get("status"),
            "delivery_fee": round(delivery_fee, 2) if delivery_fee is not None else None,
            "eta_min":     eta_min,
            "eta_max":     eta_max,
            "descuentos":  extract_discounts(store),
            "error":       None,
        })

    if not results:
        return [{"error": "No McDonald's in top-50 for this zone"}]

    print(f"  McDonald's encontrados: {len(results)}")
    return results


def main():
    rows = []

    for zone in ZONES:
        print(f"\nZona: {zone['zona']} ({zone['lat']}, {zone['lng']})")
        results = scrape_zone(zone)

        for r in results:
            rows.append({
                "zona":         zone["zona"],
                "lat":          zone["lat"],
                "lng":          zone["lng"],
                "restaurante":  r.get("restaurante"),
                "store_id":     r.get("store_id"),
                "status":       r.get("status"),
                "delivery_fee": r.get("delivery_fee"),
                "eta_min":      r.get("eta_min"),
                "eta_max":      r.get("eta_max"),
                "descuentos":   r.get("descuentos"),
                "error":        r.get("error"),
            })

        time.sleep(2)

    df = pd.DataFrame(rows, columns=[
        "zona", "lat", "lng", "restaurante", "store_id", "status",
        "delivery_fee", "eta_min", "eta_max", "descuentos", "error"
    ])
    out_path = "data/raw/rappi_test.csv"
    df.to_csv(out_path, index=False)
    print(f"\nCSV guardado en {out_path}")
    print(df.to_string())

    success = df["delivery_fee"].notna().any()
    print(
        "\n[RESULTADO]",
        "OK — datos reales obtenidos." if success else
        "FALLO — todas las filas tienen error. Token expirado o headers incorrectos."
    )


if __name__ == "__main__":
    main()
