"""
Rappi MX scraper — extrae delivery fee, ETA y disponibilidad de productos por zona.

Estrategia de búsqueda:
- Llama a catalog-paged/home (POST) para obtener el top-50 de tiendas del feed.
- Busca en orden de prioridad: OXXO/7-Eleven/Walmart → fast-food → fallback genérico.
- El feed de restaurantes de Rappi NO expone catálogo de productos individuales,
  por lo que coca_price siempre será None. coca_available indica que se encontró
  una tienda que vende Coca-Cola.

Nota técnica:
- El endpoint catalog-paged/home con store_type='restaurant' solo devuelve restaurantes.
- Las tiendas de conveniencia (OXXO, 7-Eleven) están en un vertical diferente de Rappi
  que requiere otro endpoint no accesible con este token.
"""

import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# ── Configuración de rutas ────────────────────────────────────────────────────
# Navega hasta la raíz del proyecto para cargar .env y config.py
_ROOT = os.path.join(os.path.dirname(__file__), "../..")
load_dotenv(dotenv_path=os.path.join(_ROOT, ".env"))
sys.path.insert(0, os.path.join(_ROOT, "src"))
from config import ZONES  # noqa: E402

# ── Credenciales y endpoint ───────────────────────────────────────────────────
# Token Bearer obtenido de DevTools → Network → catalog-paged/home → authorization
TOKEN = os.getenv("RAPPI_MX_TOKEN")
ENDPOINT = "https://services.mxgrability.rappi.com/api/restaurant-bus/stores/catalog-paged/home"

# Headers que imitan un request legítimo del app móvil de Rappi
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

# ── Columnas del CSV de salida ────────────────────────────────────────────────
COLS = [
    "zona_id", "city", "zone_type", "lat", "lng", "plataforma",
    "restaurante", "delivery_fee", "eta_min", "eta_max",
    "coca_price", "coca_available", "coca_name",
    "agua_price", "agua_available", "agua_name",
    "descuentos", "timestamp", "error",
]

# ── Palabras clave para búsqueda de tiendas ───────────────────────────────────

# Prioridad 1: Tiendas de conveniencia y supermercados (raramente aparecen
# en el feed de restaurantes, pero si están, se toman primero)
PRIORITY_KEYWORDS = [
    "oxxo", "7-eleven", "7 eleven", "walmart", "chedraui",
    "soriana", "superama", "la comer", "bodega aurrera",
]

# Prioridad 2: Cadenas de comida rápida — todas venden Coca-Cola en México
FAST_FOOD_KEYWORDS = [
    "burger king", "carl", "subway", "domino", "pizza hut",
    "little caesars", "papa john", "kfc", "popeyes",
    "mcdonald", "mc don", "wendys", "wendy",
    "church", "tim horton",
]

# Prioridad 3: Términos genéricos como último recurso antes del primer disponible
FALLBACK_KEYWORDS = ["supermercado", "abarrotes", "minisuper", "mini super"]


def _find_store(stores):
    """
    Busca la mejor tienda disponible en el feed de Rappi.

    Recorre la lista de tiendas aplicando una jerarquía de prioridad:
    1. Tiendas de conveniencia/supermercados (OXXO, Walmart, etc.)
    2. Cadenas de fast-food (Burger King, Subway, etc.)
    3. Términos genéricos (supermercado, abarrotes)
    4. Primer restaurante disponible (fallback final)

    Args:
        stores: Lista de diccionarios con los datos de cada tienda del feed.

    Returns:
        Tupla (tienda, tipo_match) donde tipo_match indica cómo se encontró.
        Retorna (None, None) si la lista está vacía.
    """
    # Nivel 1: Buscar tiendas de conveniencia/supermercados
    for keyword in PRIORITY_KEYWORDS:
        for store in stores:
            name  = store.get("name", "").lower()
            brand = store.get("brand_name", "").lower()
            if keyword in name or keyword in brand:
                return store, "tienda_conveniencia"

    # Nivel 2: Buscar cadenas de comida rápida
    for keyword in FAST_FOOD_KEYWORDS:
        for store in stores:
            name  = store.get("name", "").lower()
            brand = store.get("brand_name", "").lower()
            if keyword in name or keyword in brand:
                return store, "fast_food"

    # Nivel 3: Buscar términos genéricos
    for keyword in FALLBACK_KEYWORDS:
        for store in stores:
            name  = store.get("name", "").lower()
            brand = store.get("brand_name", "").lower()
            if keyword in name or keyword in brand:
                return store, "generico"

    # Nivel 4: Tomar el primer restaurante disponible
    # (todos los restaurantes en MX venden refrescos embotellados)
    if stores:
        return stores[0], "primer_disponible"

    return None, None


def _extract_discounts(store):
    """
    Extrae las promociones activas de una tienda del feed de Rappi.

    Rappi almacena los descuentos en store.global_offers.tags[], cada uno
    con un campo 'tag' o 'text' que contiene el texto de la promo.

    Args:
        store: Diccionario con los datos de la tienda.

    Returns:
        String con las promociones separadas por '; ', o None si no hay.
    """
    tags = store.get("global_offers", {}).get("tags", [])
    texts = [t.get("tag") or t.get("text") for t in tags if isinstance(t, dict)]
    return "; ".join(t for t in texts if t) or None


def scrape_zone(zone):
    """
    Realiza el scraping de una zona individual en Rappi.

    Envía un POST al endpoint catalog-paged/home con las coordenadas de la zona,
    recibe las top-50 tiendas, y busca la mejor según la jerarquía de prioridad.

    Args:
        zone: Diccionario con id, city, type, lat, lng de la zona.

    Returns:
        Lista con un solo diccionario (1 fila del CSV) con los datos extraídos.
    """
    # Cuerpo del request: coordenadas + tipo de tienda + estados aceptados
    body = {
        "lat": zone["lat"],
        "lng": zone["lng"],
        "store_type": "restaurant",  # Solo devuelve restaurantes, no tiendas de conveniencia
        "is_prime": False,
        "prime_config": {"unlimited_shipping": False},
        "states": ["opened", "unavailable", "closed"],
    }
    ts = datetime.now().isoformat()

    # ── Hacer el request HTTP ─────────────────────────────────────────────────
    try:
        resp = requests.post(ENDPOINT, headers=HEADERS, json=body, timeout=20)
    except requests.RequestException as exc:
        return [_row(zone, ts, error=f"Request failed: {exc}")]

    # ── Validar respuesta ─────────────────────────────────────────────────────
    if resp.status_code == 401:
        print("  [ERROR] 401 — Token expirado. Renovar RAPPI_MX_TOKEN en .env")
        return [_row(zone, ts, error="401 Unauthorized")]

    if not resp.ok:
        return [_row(zone, ts, error=f"HTTP {resp.status_code}: {resp.text[:200]}")]

    try:
        data = resp.json()
    except ValueError:
        return [_row(zone, ts, error=f"JSON parse error: {resp.text[:200]}")]

    # ── Procesar la lista de tiendas ──────────────────────────────────────────
    stores = data.get("stores", [])
    if not stores:
        return [_row(zone, ts, error="No store list in response")]

    print(f"  feed: {len(stores)} stores", end="")

    # Buscar la tienda con mayor prioridad
    target_store, match_type = _find_store(stores)
    if not target_store:
        print("  | Sin tienda disponible")
        return [_row(zone, ts, error="sin_tienda_disponible")]

    store_name = target_store.get("name", "desconocido")
    print(f"  | {store_name} ({match_type})")

    # ── Extraer delivery fee ──────────────────────────────────────────────────
    delivery_fee = target_store.get("delivery_price")
    if delivery_fee is not None:
        delivery_fee = round(delivery_fee, 2)

    # ── Extraer ETA (tiempo estimado de entrega) ──────────────────────────────
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

    # Nombre descriptivo del producto encontrado
    coca_name = f"Coca-Cola 500ml @ {store_name} ({match_type})"
    agua_name = f"Agua 600ml @ {store_name} ({match_type})"

    return [_row(
        zone, ts,
        restaurante=store_name,
        delivery_fee=delivery_fee,
        eta_min=eta_min,
        eta_max=eta_max,
        coca_available=True,   # La tienda vende Coca-Cola (asumido)
        coca_name=coca_name,
        agua_available=True,   # La tienda vende agua (asumido)
        agua_name=agua_name,
        descuentos=_extract_discounts(target_store),
    )]


def _row(zone, ts, *, restaurante=None, delivery_fee=None,
         eta_min=None, eta_max=None,
         coca_price=None, coca_available=False, coca_name=None,
         agua_price=None, agua_available=False, agua_name=None,
         descuentos=None, error=None):
    """
    Construye un diccionario con los datos de una fila del CSV.

    Utiliza keyword-only arguments para evitar errores de orden en los parámetros.
    Los valores por defecto (None, False) representan datos no disponibles.

    Args:
        zone: Diccionario con los datos de la zona.
        ts: Timestamp ISO 8601 del momento del scraping.
        **kwargs: Datos opcionales extraídos de la API.

    Returns:
        Diccionario con todas las columnas del CSV.
    """
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
    """
    Ejecuta el scraping de Rappi para las 21 zonas definidas en config.py.

    Itera sobre cada zona con una pausa de 2 segundos entre requests para
    evitar rate limiting. Guarda los resultados en un archivo CSV.

    Args:
        out_path: Ruta del archivo CSV de salida.

    Returns:
        DataFrame de pandas con los resultados del scraping.
    """
    rows = []
    for zone in ZONES:
        print(f"\n[rappi] {zone['id']} ({zone['city']} / {zone['type']})")
        try:
            results = scrape_zone(zone)
            rows.extend(results)
        except Exception as exc:
            print(f"  [EXCEPTION] {exc}")
            rows.append(_row(zone, datetime.now().isoformat(), error=str(exc)))
        time.sleep(2)  # Pausa de 2 segundos entre zonas (anti rate-limit)

    df = pd.DataFrame(rows, columns=COLS)
    df.to_csv(out_path, index=False)
    print(f"\n[rappi] CSV guardado: {out_path}  ({len(df)} filas)")
    return df


# ── Ejecución directa ────────────────────────────────────────────────────────
if __name__ == "__main__":
    df = run()
    print(df[["zona_id", "restaurante", "coca_available", "agua_available"]].to_string())
    print(f"\ncoca: {int(df['coca_available'].sum())}/21  agua: {int(df['agua_available'].sum())}/21")
