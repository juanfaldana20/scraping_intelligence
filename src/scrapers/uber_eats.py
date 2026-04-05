"""
Uber Eats MX scraper — extrae delivery fee, ETA y precios de productos de referencia.

Flujo de scraping por zona (2 pasos):
  Paso 1: getFeedV1 (coordenadas en headers)
     - Retorna feedItems[].carousel.stores[] con 200+ tiendas
     - Busca OXXO, 7-Eleven, Walmart, etc.; fallback a fast-food / primer restaurante
     - Extrae: ETA → tracking.storePayload.etdInfo.dropoffETARange.{min, max}
     - Extrae: Promos → signposts[].text

  Paso 2: getStoreV1 (storeUuid obtenido del paso 1)
     - Retorna detalle completo + catálogo de productos de la tienda
     - Delivery fee → modalityInfo.modalityOptions[DELIVERY] (puede ser None en tiendas)
     - Coca-Cola 500ml → buscar "coca" + "500" en título del item
     - Agua 1L → buscar "ciel", "agua natural 1l", "agua purificada 1l", etc.

NOTA TÉCNICA:
La cookie uev2.loc lleva hardcoded una ubicación CDMX. Uber Eats puede rankear tiendas
por esa ubicación ignorando los headers x-uber-target-location-*. Las 21 zonas mandan
coordenadas diferentes pero pueden retornar la misma tienda si la cookie domina.
Para resolución por ciudad se necesitan cookies capturadas desde GDL y MTY.
"""

import os
import re
import sys
import time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# ── Configuración de rutas ────────────────────────────────────────────────────
_ROOT = os.path.join(os.path.dirname(__file__), "../..")
load_dotenv(dotenv_path=os.path.join(_ROOT, ".env"))
sys.path.insert(0, os.path.join(_ROOT, "src"))
from config import ZONES  # noqa: E402

# ── Credenciales y endpoints ─────────────────────────────────────────────────
# Cookies de sesión copiadas de DevTools → Network → getFeedV1 → cookie
COOKIES   = os.getenv("UBER_COOKIES", "")

# Endpoint del feed principal (lista de tiendas por ubicación)
FEED_URL  = "https://www.ubereats.com/_p/api/getFeedV1?localeCode=mx"

# Endpoint de detalle de tienda (catálogo de productos + delivery fee)
STORE_URL = "https://www.ubereats.com/_p/api/getStoreV1?localeCode=mx"

# Cuerpo base para el request del feed (campos requeridos, la mayoría vacíos)
FEED_BODY = {
    "billboardUuid": "", "carouselId": "", "date": "", "feedProvider": "",
    "isUserInitiatedRefresh": False, "keyName": "", "promotionUuid": "",
    "searchSource": "", "searchType": "", "selectedSectionUUID": "",
    "serializedRequestContext": "", "sortAndFilters": [],
    "startTime": 0, "endTime": 0, "targetingStoreTag": "",
    "userQuery": "", "venueUUID": "", "vertical": "",
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

# Prioridad 1: Tiendas de conveniencia y supermercados
STORE_KEYWORDS = [
    "oxxo", "7-eleven", "7 eleven", "walmart", "chedraui",
    "soriana", "superama", "la comer", "bodega aurrera",
]

# Prioridad 2: Cadenas de comida rápida (todas venden Coca-Cola en MX)
FAST_FOOD_KEYWORDS = [
    "burger king", "carl", "subway", "domino", "pizza hut",
    "little caesars", "papa john", "kfc", "popeyes",
    "mcdonald", "mc don", "wendys", "wendy",
    "church", "tim horton",
]

# Prioridad 3: Términos genéricos como fallback
FALLBACK_KEYWORDS = ["supermercado", "abarrotes", "minisuper", "mini super"]


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS DE RED
# ═══════════════════════════════════════════════════════════════════════════════

def _headers(lat, lng):
    """
    Genera los headers HTTP para un request a Uber Eats.

    Incluye las coordenadas de la zona en headers custom de Uber
    (x-uber-target-location-*) y las cookies de sesión.

    Args:
        lat: Latitud de la zona a consultar.
        lng: Longitud de la zona a consultar.

    Returns:
        Diccionario de headers listo para usar con requests.post().
    """
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
        # Headers custom de Uber para geolocalización
        "x-uber-target-location-latitude": str(lat),
        "x-uber-target-location-longitude": str(lng),
        "referer": "https://www.ubereats.com/mx/feed?diningMode=DELIVERY",
        "cookie": COOKIES,
    }


def _check_auth(resp):
    """
    Verifica si la sesión de Uber Eats sigue activa.

    Las cookies (especialmente jwt-session) expiran cada ~24 horas.
    Un 401 o 403 indica que deben renovarse.

    Args:
        resp: Objeto Response de requests.

    Returns:
        True si la autenticación es válida, False si expiró.
    """
    if resp.status_code in (401, 403):
        print("  [ERROR] Cookies de Uber Eats expiradas. Renovar UBER_COOKIES en .env desde DevTools")
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# PARSERS DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════

def _item_title(it):
    """
    Extrae el título de texto de un item del menú.

    Uber Eats puede enviar el título como string directo o como
    diccionario con una clave 'text'. Esta función maneja ambos casos.

    Args:
        it: Diccionario de un item del catálogo.

    Returns:
        String con el título del item.
    """
    t = it.get("title", "")
    return t.get("text", "") if isinstance(t, dict) else str(t)


def _find_items_by_keyword(obj, keyword, depth=0):
    """
    Búsqueda recursiva de items por palabra clave en todo el JSON del menú.

    Recorre toda la estructura JSON (dicts y listas) hasta profundidad 8,
    buscando items cuyo título contenga la palabra clave y tengan precio.

    Este enfoque es necesario porque Uber Eats anida los productos en
    estructuras complejas (catalogSectionsMap → payload → standardItemsPayload
    → catalogItems) que pueden variar entre tiendas.

    Args:
        obj: Objeto JSON (dict, list, u otro) a recorrer.
        keyword: Palabra clave a buscar (en minúsculas).
        depth: Profundidad actual de recursión (máximo 8).

    Returns:
        Lista de diccionarios de items que coinciden con la búsqueda.
    """
    results = []
    if depth > 8:
        return results
    if isinstance(obj, dict):
        # Si este dict tiene título que coincide y tiene precio, es un match
        if keyword in _item_title(obj).lower() and obj.get("price") is not None:
            results.append(obj)
        # Seguir buscando en los valores anidados
        for v in obj.values():
            results.extend(_find_items_by_keyword(v, keyword, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_find_items_by_keyword(item, keyword, depth + 1))
    return results


def _parse_delivery_fee(data):
    """
    Extrae el costo de envío del JSON de detalle de una tienda.

    La estructura en Uber Eats es:
    modalityInfo.modalityOptions[].priceTitleRichText.richTextElements[].text.text.text
    que contiene strings como "Costo de envío a MXN15".

    NOTA: modalityInfo puede ser None (no {}) cuando la key existe pero su valor
    es null — esto ocurre en tiendas de conveniencia como OXXO. Por eso usamos
    (data.get("modalityInfo") or {}) en vez de data.get("modalityInfo", {}).

    Args:
        data: Diccionario con los datos completos de la tienda (response.data).

    Returns:
        Float con el delivery fee en MXN, o None si no está disponible.
    """
    # IMPORTANTE: modalityInfo puede ser None (no {}), por eso usamos 'or {}'
    modality_opts = (data.get("modalityInfo") or {}).get("modalityOptions", [])
    delivery_opt = next(
        (o for o in modality_opts if o.get("diningMode") == "DELIVERY"), None
    )
    if not delivery_opt:
        return None

    # Recorrer los elementos de texto enriquecido buscando "MXN XX"
    for elem in delivery_opt.get("priceTitleRichText", {}).get("richTextElements", []):
        if elem.get("type") == "text":
            txt = (elem.get("text") or {}).get("text", {})
            if isinstance(txt, dict):
                txt = txt.get("text", "")
            # Extraer el número después de "MXN" (ej: "MXN15" → 15.0)
            m = re.search(r"MXN\s*(\d+(?:\.\d+)?)", str(txt))
            if m:
                return float(m.group(1))
    return None


def _cheapest(items):
    """
    Encuentra el item más barato de una lista de productos.

    Los precios en Uber Eats vienen en centavos (ej: 2900 = $29.00 MXN).
    Esta función los convierte a pesos.

    Args:
        items: Lista de diccionarios de items con campo 'price'.

    Returns:
        Tupla (precio_mxn, título) del item más barato.
    """
    it = min(items, key=lambda x: x.get("price", 999_999_99))
    return round(it["price"] / 100, 2), _item_title(it)


def _find_coca_cola(data):
    """
    Busca Coca-Cola 500ml en el catálogo de una tienda de Uber Eats.

    Estrategia de búsqueda:
    1. Buscar items con "coca" en el título
    2. Filtrar los que tengan "500" (500ml)
    3. Si no hay 500ml exacto, tomar la Coca-Cola más barata disponible

    La búsqueda es amplia ("coca") porque los títulos varían entre tiendas:
    - "Coca-Cola · Refresco sin azúcar (500 ml)"
    - "Coca-Cola Original 500ml"
    - "Coca Cola 500"

    Args:
        data: Diccionario con el JSON completo de la tienda.

    Returns:
        Tupla (precio, disponible, nombre) del producto encontrado.
    """
    items = _find_items_by_keyword(data, "coca")
    if not items:
        return None, False, None

    # Intentar filtrar por 500ml específicamente
    coca_500 = [it for it in items if "500" in _item_title(it).lower()]
    if coca_500:
        price, title = _cheapest(coca_500)
        return price, True, title

    # Fallback: tomar la Coca-Cola más barata sin importar presentación
    price, title = _cheapest(items)
    return price, True, f"{title} (no 500ml exacto)"


def _find_agua_1l(data):
    """
    Busca Agua 1L en el catálogo de una tienda de Uber Eats.

    Estrategia escalonada (se detiene en el primer match):
    1. Buscar términos específicos: "ciel agua natural", "ciel", "agua 1l", etc.
    2. Fallback: buscar cualquier "agua" que contenga "1" en el título (1L, 1lt)

    Args:
        data: Diccionario con el JSON completo de la tienda.

    Returns:
        Tupla (precio, disponible, nombre) del producto encontrado.
    """
    # Términos específicos en orden de preferencia
    for term in ["ciel agua natural", "ciel", "agua 1l", "agua natural 1l",
                 "agua purificada 1l", "agua 1 litro"]:
        items = _find_items_by_keyword(data, term)
        if items:
            price, title = _cheapest(items)
            return price, True, title

    # Fallback: cualquier "agua" con indicador de 1 litro en el título
    items = _find_items_by_keyword(data, "agua")
    agua_1 = [
        it for it in items
        if any(tok in _item_title(it).lower() for tok in ["1l", "1 l", "1lt", "1 litro", "1.0"])
    ]
    if agua_1:
        price, title = _cheapest(agua_1)
        return price, True, title

    return None, False, None


def _find_leche_lala(data):
    """
    Busca Leche Lala 1L en el catálogo de una tienda de Uber Eats.

    Nota: Esta función existe en el código pero no se usa actualmente
    en la generación del CSV. Está preparada para futuras expansiones
    del set de productos de referencia.

    Args:
        data: Diccionario con el JSON completo de la tienda.

    Returns:
        Tupla (precio, disponible, nombre) del producto encontrado.
    """
    for term in ["lala entera 1l", "lala entera", "lala 1l",
                 "leche lala 1l", "leche lala", "lala"]:
        items = _find_items_by_keyword(data, term)
        if items:
            # Preferir la presentación de 1L si hay varias opciones
            lala_1l = [it for it in items if any(
                tok in _item_title(it).lower() for tok in ["1l", "1 l", "1lt", "1 litro"]
            )]
            if lala_1l:
                price, title = _cheapest(lala_1l)
            else:
                price, title = _cheapest(items)
            return price, True, title

    return None, False, None


def _parse_discounts(store):
    """
    Extrae los descuentos y promociones visibles de una tienda en el feed.

    En Uber Eats, los descuentos aparecen en store.signposts[].text,
    por ejemplo: "Envío gratis", "2x1 en seleccionados".

    Args:
        store: Diccionario de la tienda del feed.

    Returns:
        String con los descuentos separados por '; ', o None si no hay.
    """
    texts = [sp.get("text", "") for sp in store.get("signposts", []) if sp.get("text")]
    return "; ".join(texts) or None


# ═══════════════════════════════════════════════════════════════════════════════
# BÚSQUEDA DE TIENDA EN EL FEED
# ═══════════════════════════════════════════════════════════════════════════════

def _find_store_in_feed(all_stores):
    """
    Busca la mejor tienda en el feed de Uber Eats para una zona.

    Aplica la misma jerarquía de prioridad que Rappi:
    1. Tienda de conveniencia/supermercado (OXXO, Walmart, etc.)
    2. Cadena de fast-food (Burger King, Subway, etc.)
    3. Fallback genérico (supermercado, abarrotes)
    4. Primer restaurante disponible

    Args:
        all_stores: Lista de todas las tiendas del feed.

    Returns:
        Tupla (tienda, tipo_match) o (None, None) si no hay tiendas.
    """
    def _get_name(store):
        """Extrae el nombre de la tienda del formato de título de Uber Eats."""
        title = store.get("title", {})
        return title.get("text", "").lower() if isinstance(title, dict) else str(title).lower()

    # Nivel 1: Tiendas de conveniencia
    for keyword in STORE_KEYWORDS:
        for store in all_stores:
            if keyword in _get_name(store):
                return store, "tienda_conveniencia"

    # Nivel 2: Fast-food
    for keyword in FAST_FOOD_KEYWORDS:
        for store in all_stores:
            if keyword in _get_name(store):
                return store, "fast_food"

    # Nivel 3: Fallback genérico
    for keyword in FALLBACK_KEYWORDS:
        for store in all_stores:
            if keyword in _get_name(store):
                return store, "generico"

    # Nivel 4: Primer disponible
    if all_stores:
        return all_stores[0], "primer_disponible"

    return None, None


# ═══════════════════════════════════════════════════════════════════════════════
# LLAMADAS A LA API
# ═══════════════════════════════════════════════════════════════════════════════

def _get_feed(zone):
    """
    Obtiene el feed de tiendas de Uber Eats para una zona.

    Llama a getFeedV1 con las coordenadas de la zona y busca la mejor
    tienda disponible según la jerarquía de prioridad.

    Args:
        zone: Diccionario con id, city, type, lat, lng de la zona.

    Returns:
        Diccionario con los datos de la tienda encontrada:
        - storeUuid, restaurante, match_type, eta_min, eta_max, descuentos
        O diccionario con clave 'error' si falló algo.
    """
    hdrs = _headers(zone["lat"], zone["lng"])

    # ── Request al feed ───────────────────────────────────────────────────────
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

    # ── Extraer tiendas de los carousels del feed ─────────────────────────────
    feed_items = d.get("data", {}).get("feedItems", [])
    if not feed_items:
        keys = list(d.get("data", {}).keys())
        print(f"  [WARN] feedItems vacío. data keys: {keys[:3]}")
        return {"error": "feedItems vacío"}

    # Cada feedItem tiene un carousel con una lista de stores
    all_stores = []
    for item in feed_items:
        all_stores.extend(item.get("carousel", {}).get("stores", []))

    print(f"  feed: {len(all_stores)} stores", end="")

    # ── Buscar la mejor tienda ────────────────────────────────────────────────
    target_store, match_type = _find_store_in_feed(all_stores)
    if target_store:
        title = target_store.get("title", {})
        store_name = title.get("text", "") if isinstance(title, dict) else str(title)
        print(f"  | Tienda: {store_name} ({match_type})")
    else:
        print(f"  | Sin tienda disponible")
        return {"error": "sin_tienda_disponible"}

    # ── Extraer ETA de la tienda ──────────────────────────────────────────────
    # La estructura es: tracking.storePayload.etdInfo.dropoffETARange.{min, max}
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
    """
    Obtiene el detalle y catálogo de productos de una tienda específica.

    Llama a getStoreV1 con el UUID de la tienda obtenido del feed.
    Busca el delivery fee y los productos de referencia (Coca-Cola 500ml, Agua 1L).

    Args:
        zone: Diccionario con los datos de la zona (para headers de ubicación).
        store_uuid: UUID de la tienda obtenido de _get_feed().

    Returns:
        Diccionario con delivery_fee, coca_price, coca_available, coca_name,
        agua_price, agua_available, agua_name. O dict con 'error' si falló.
    """
    hdrs = _headers(zone["lat"], zone["lng"])
    body = {
        "storeUuid": store_uuid,
        "diningMode": "DELIVERY",
        "time": {"asap": True},       # Pedir entrega inmediata
        "cbType": "EATER_ENDORSED",   # Tipo de catálogo estándar
    }

    # ── Request al detalle de tienda ──────────────────────────────────────────
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

    # ── Buscar productos de referencia en el catálogo ─────────────────────────
    coca_price, coca_available, coca_title = _find_coca_cola(data)
    agua_price, agua_available, agua_title = _find_agua_1l(data)

    return {
        "delivery_fee":   _parse_delivery_fee(data),
        "coca_price":     coca_price,
        "coca_available": coca_available,
        "coca_name":      coca_title,
        "agua_price":     agua_price,
        "agua_available": agua_available,
        "agua_name":      agua_title,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ORQUESTACIÓN POR ZONA
# ═══════════════════════════════════════════════════════════════════════════════

def scrape_zone(zone):
    """
    Realiza el scraping completo de una zona en Uber Eats (2 pasos).

    Paso 1: Obtener el feed y encontrar la mejor tienda
    Paso 2: Obtener el detalle de la tienda y buscar productos

    Si el paso 1 falla, retorna una fila con error.
    Si el paso 2 falla, retorna una fila parcial (con ETA y nombre, sin precios).

    Args:
        zone: Diccionario con id, city, type, lat, lng de la zona.

    Returns:
        Diccionario con los datos de la zona (una fila del CSV).
    """
    ts = datetime.now().isoformat()

    # ── Paso 1: Feed (buscar tienda) ──────────────────────────────────────────
    feed = _get_feed(zone)
    if "error" in feed:
        return _row(zone, ts, error=feed["error"])

    store_uuid = feed.get("storeUuid")
    if not store_uuid:
        return _row(zone, ts, error="No storeUuid in feed")

    # ── Paso 2: Detalle (buscar precios de productos) ─────────────────────────
    detail = _get_store_detail(zone, store_uuid)
    if "error" in detail:
        # Resultado parcial: tenemos ETA y restaurante del feed, pero sin precios
        return _row(zone, ts,
                    restaurante=feed.get("restaurante"),
                    eta_min=feed.get("eta_min"),
                    eta_max=feed.get("eta_max"),
                    descuentos=feed.get("descuentos"),
                    error=detail["error"])

    # ── Construir nombre descriptivo del producto ─────────────────────────────
    coca_available = detail.get("coca_available", False)
    match_type = feed.get("match_type", "")
    store_name = feed.get("restaurante", "N/A")
    coca_name = detail.get("coca_name")
    if coca_name:
        coca_name = f"{coca_name} @ {store_name} ({match_type})"
    else:
        coca_name = f"Coca-Cola 500ml (no encontrada) @ {store_name} ({match_type})"

    # Indicador visual en la terminal
    print(f"  coca={'✓' if coca_available else '✗'} "
          f"agua={'✓' if detail.get('agua_available') else '✗'}")

    return _row(zone, ts,
                restaurante=feed.get("restaurante"),
                eta_min=feed.get("eta_min"),
                eta_max=feed.get("eta_max"),
                descuentos=feed.get("descuentos"),
                delivery_fee=detail.get("delivery_fee"),
                coca_price=detail.get("coca_price"),
                coca_available=coca_available,
                coca_name=coca_name,
                agua_price=detail.get("agua_price"),
                agua_available=detail.get("agua_available", False),
                agua_name=detail.get("agua_name"))


def _row(zone, ts, *, restaurante=None, delivery_fee=None,
         eta_min=None, eta_max=None,
         coca_price=None, coca_available=False, coca_name=None,
         agua_price=None, agua_available=False, agua_name=None,
         descuentos=None, error=None):
    """
    Construye un diccionario con los datos de una fila del CSV.

    Utiliza keyword-only arguments (después del *) para evitar errores
    de orden al llamar la función con tantos parámetros opcionales.

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
        "plataforma":     "uber_eats",
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


# ═══════════════════════════════════════════════════════════════════════════════
# PUNTOS DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════════

def run(out_path="data/raw/ubereats_v2.csv"):
    """
    Ejecuta el scraping de Uber Eats para las 21 zonas definidas en config.py.

    Para cada zona:
    1. Llama a getFeedV1 (busca tienda)
    2. Llama a getStoreV1 (busca productos y precios)
    3. Espera 2 segundos antes de la siguiente zona (anti rate-limit)

    Args:
        out_path: Ruta del archivo CSV de salida.

    Returns:
        DataFrame de pandas con los resultados del scraping.
    """
    rows = []
    for zone in ZONES:
        print(f"\n[uber_eats] {zone['id']} ({zone['city']} / {zone['type']})")
        try:
            rows.append(scrape_zone(zone))
        except Exception as exc:
            print(f"  [EXCEPTION] {exc}")
            rows.append(_row(zone, datetime.now().isoformat(), error=str(exc)))
        time.sleep(2)  # Pausa de 2 segundos entre zonas (anti rate-limit)

    df = pd.DataFrame(rows, columns=COLS)
    df.to_csv(out_path, index=False)
    print(f"\n[uber_eats] CSV guardado: {out_path}  ({len(df)} filas)")
    return df


# ── Ejecución directa ────────────────────────────────────────────────────────
if __name__ == "__main__":
    df = run()
    print(df.to_string())
    success = int(df["coca_available"].sum())
    total = len(df)
    print(f"\n[RESULTADO] {success}/{total} zonas con Coca-Cola encontrada")
