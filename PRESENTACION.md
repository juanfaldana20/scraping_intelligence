# 📦 Scraping Intelligence — Presentación del Proyecto

## Competitive Intelligence: Rappi vs Uber Eats México

> **Autor:** Juan Faldaña  
> **Fecha:** Abril 2026  
> **Stack:** Python · Requests · Pandas · Streamlit · Plotly

---

## 1. ¿Qué es este proyecto?

Un sistema automatizado de **inteligencia competitiva** que recolecta datos en tiempo real
de las plataformas de delivery más grandes de México: **Rappi** y **Uber Eats**.

El sistema scrapea **21 zonas geográficas** distribuidas en 3 ciudades (CDMX, Guadalajara
y Monterrey) y extrae:

| Dato recolectado | Rappi | Uber Eats |
|---|:---:|:---:|
| Delivery fee (costo de envío) | ✅ | ⚠️ No expuesto en API |
| ETA (tiempo estimado de entrega) | ✅ | ✅ |
| Precio Coca-Cola 500ml | ❌ Feed no incluye catálogo | ✅ $29 MXN |
| Precio Agua 1L | ❌ Feed no incluye catálogo | ✅ |
| Descuentos y promociones activas | ✅ | ✅ |
| Tienda/restaurante encontrado | ✅ | ✅ |

**Resultado final:** Un CSV combinado de **42 filas** (21 zonas × 2 plataformas) y un
**dashboard interactivo** con insights accionables.

---

## 2. ¿Qué problema resuelve?

Los equipos de **Strategy**, **Pricing** y **Growth** necesitan responder preguntas como:

- *¿Cuánto cobra Rappi vs Uber Eats por delivery en zonas periféricas de CDMX?*
- *¿Qué plataforma tiene mejor ETA en Monterrey?*
- *¿Las zonas ricas pagan menos delivery fee que las periféricas?*
- *¿Qué descuentos están ofreciendo los competidores?*

Obtener estas respuestas manualmente tomaría horas. Este sistema lo hace en **~3 minutos**.

---

## 3. Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                      run_all.py (Orquestador)                   │
│  Ejecuta ambos scrapers → Genera combined_v2.csv → Resumen     │
└─────────────┬──────────────────────────────┬────────────────────┘
              │                              │
              ▼                              ▼
┌──────────────────────┐      ┌───────────────────────────┐
│   rappi.py           │      │   uber_eats.py            │
│                      │      │                           │
│  API: catalog-paged  │      │  API: getFeedV1 (feed)    │
│       /home (POST)   │      │       getStoreV1 (menú)   │
│                      │      │                           │
│  • Top-50 tiendas    │      │  • 200+ tiendas en feed   │
│  • Delivery fee      │      │  • OXXO en 21/21 zonas   │
│  • ETA               │      │  • Precio Coca-Cola       │
│  • Descuentos        │      │  • ETA + descuentos       │
└──────────┬───────────┘      └──────────┬────────────────┘
           │                             │
           ▼                             ▼
┌──────────────────────┐      ┌───────────────────────────┐
│  rappi_v2.csv        │      │  ubereats_v2.csv          │
│  (21 filas)          │      │  (21 filas)               │
└──────────┬───────────┘      └──────────┬────────────────┘
           │                             │
           └──────────┬──────────────────┘
                      ▼
           ┌─────────────────────┐
           │  combined_v2.csv    │
           │  (42 filas, 19 col) │
           └──────────┬──────────┘
                      │
                      ▼
           ┌─────────────────────┐
           │  app.py (Dashboard) │
           │  Streamlit + Plotly │
           │  4 tabs interactivos│
           └─────────────────────┘
```

---

## 4. Estructura de Archivos

```
scraping_intelligence/
│
├── 📂 src/                          ← Código fuente principal
│   ├── config.py                    ← Definición de las 21 zonas geográficas
│   ├── run_all.py                   ← Orquestador: ejecuta scrapers y combina datos
│   │
│   ├── 📂 scrapers/                 ← Módulo de scrapers
│   │   ├── __init__.py
│   │   ├── rappi.py                 ← Scraper de Rappi MX (API interna)
│   │   └── uber_eats.py            ← Scraper de Uber Eats MX (API interna)
│   │
│   └── 📂 ui/                       ← Dashboard interactivo
│       └── app.py                   ← Aplicación Streamlit (4 tabs)
│
├── 📂 data/raw/                     ← Datos generados por los scrapers
│   ├── rappi_v2.csv                 ← Datos completos de Rappi (21 zonas)
│   ├── ubereats_v2.csv              ← Datos completos de Uber Eats (21 zonas)
│   └── combined_v2.csv              ← Datos combinados (42 filas)
│
├── .env                             ← Credenciales (NO se sube al repo)
├── .env.example                     ← Template de variables requeridas
├── requirements.txt                 ← Dependencias del proyecto
├── README.md                        ← Documentación técnica
└── PRESENTACION.md                  ← Este archivo
```

---

## 5. ¿Qué hace cada archivo?

### 📄 `src/config.py` — Configuración de Zonas

Define las **21 zonas geográficas** donde se realizan las consultas. Cada zona incluye:
- **ID único** (`cdmx_polanco`, `gdl_centro`, `mty_cumbres`, etc.)
- **Ciudad** (CDMX, Guadalajara, Monterrey)
- **Tipo socioeconómico** (`wealthy`, `middle`, `peripheral`)
- **Coordenadas GPS** (latitud y longitud)

```python
ZONES = [
    {"id": "cdmx_polanco", "city": "CDMX", "type": "wealthy", "lat": 19.4326, "lng": -99.1950},
    # ... 21 zonas total
]
```

**¿Por qué 3 tipos de zona?** Para analizar si las plataformas cobran diferente según
el nivel socioeconómico de la zona.

---

### 📄 `src/scrapers/rappi.py` — Scraper de Rappi

**Endpoint:** `POST /api/restaurant-bus/stores/catalog-paged/home`  
**Autenticación:** Bearer token (obtenido de DevTools)

#### Flujo:

```
1. Para cada zona → Envía lat/lng al endpoint
2. Recibe las top-50 tiendas del feed
3. Busca la mejor tienda con este algoritmo de prioridad:
   │
   ├─ Prioridad 1: Tiendas de conveniencia (OXXO, 7-Eleven, Walmart...)
   ├─ Prioridad 2: Cadenas de fast-food (Burger King, Carl's Jr., Subway...)
   ├─ Prioridad 3: Términos genéricos (supermercado, abarrotes)
   └─ Prioridad 4: Primer restaurante disponible
4. Extrae: delivery_fee, ETA, descuentos
5. Guarda resultado en CSV
```

#### Funciones principales:

| Función | Propósito |
|---|---|
| `_find_store()` | Busca la tienda ideal en el feed según la jerarquía de prioridad |
| `_extract_discounts()` | Extrae promociones activas de los tags de la tienda |
| `scrape_zone()` | Orquesta el scraping de una zona individual |
| `_row()` | Construye el diccionario de una fila del CSV |
| `run()` | Ejecuta el scraping de las 21 zonas con pausa de 2 segundos |

#### Hallazgo clave:
> El feed de Rappi con `store_type=restaurant` **solo devuelve restaurantes**, no tiendas
> de conveniencia. OXXO y 7-Eleven están en un vertical diferente de Rappi no accesible
> con este endpoint. Por eso el fallback a cadenas de fast-food es esencial.

---

### 📄 `src/scrapers/uber_eats.py` — Scraper de Uber Eats

**Endpoints:**
1. `POST /api/getFeedV1` → Feed con 200+ tiendas
2. `POST /api/getStoreV1` → Detalle + menú de una tienda

**Autenticación:** Cookies de sesión (copiadas de DevTools)

#### Flujo (2 pasos por zona):

```
Paso 1: getFeedV1
   └─ Busca OXXO / 7-Eleven / fast-food en el carousel de stores
   └─ Extrae: nombre, ETA, descuentos, storeUuid

Paso 2: getStoreV1 (con el storeUuid del paso 1)
   └─ Obtiene el catálogo de productos de la tienda
   └─ Busca Coca-Cola 500ml → filtro por "coca" + "500" en título
   └─ Busca Agua 1L → filtro por "ciel", "agua natural", etc.
   └─ Extrae: delivery_fee, precio del producto
```

#### Funciones principales:

| Función | Propósito |
|---|---|
| `_headers()` | Genera headers HTTP con las coordenadas de la zona |
| `_check_auth()` | Verifica si la sesión está activa (401/403) |
| `_item_title()` | Extrae el título de un item del menú (maneja dict y string) |
| `_find_items_by_keyword()` | Búsqueda recursiva en el JSON del menú hasta profundidad 8 |
| `_parse_delivery_fee()` | Parsea el costo de envío desde `modalityInfo` |
| `_find_coca_cola()` | Busca Coca-Cola 500ml en el catálogo |
| `_find_agua_1l()` | Busca Agua 1L (Ciel, agua natural, etc.) |
| `_find_store_in_feed()` | Busca la mejor tienda en el feed con prioridad |
| `_get_feed()` | Llama a getFeedV1 y encuentra la tienda target |
| `_get_store_detail()` | Llama a getStoreV1 y extrae precios de productos |
| `scrape_zone()` | Orquesta ambos pasos (feed + detail) |
| `run()` | Ejecuta las 21 zonas con pausa de 2 segundos |

#### Hallazgo clave:
> OXXO aparece en **21 de 21 zonas** de Uber Eats. Es el primer resultado consistente
> en todas las geografías. Sin embargo, la cookie `uev2.loc` puede hacer que todas las
> zonas retornen la misma tienda OXXO (sesión hardcoded a CDMX).

---

### 📄 `src/run_all.py` — Orquestador

Ejecuta ambos scrapers secuencialmente y genera el archivo combinado.

```python
python src/run_all.py
```

#### Qué hace:
1. Ejecuta `rappi.py` → genera `rappi_v2.csv`
2. Ejecuta `uber_eats.py` → genera `ubereats_v2.csv`
3. Concatena ambos DataFrames → genera `combined_v2.csv`
4. Imprime un resumen con estadísticas:
   - Zonas con datos / con error
   - Cobertura de Coca-Cola y Agua
   - Top tiendas encontradas
   - Desglose por ciudad

---

### 📄 `src/ui/app.py` — Dashboard Streamlit

Dashboard interactivo con **4 tabs**:

| Tab | Contenido |
|---|---|
| 📊 **Overview** | Métricas globales + 3 gráficas (delivery fee, ETA comparado, scatter por zona) |
| 🗺️ **Por Zona** | Tabla filtrable + detalle por zona con métricas específicas |
| 💡 **Top 5 Insights** | Insights calculados en tiempo real con Finding/Impacto/Recomendación |
| 📋 **Datos Raw** | Tabla completa + botón de descarga CSV |

#### Funcionalidades del sidebar:
- **▶ Ejecutar Scraping:** Botón para lanzar `run_all.py` desde la UI
- **Filtros:** Por ciudad y tipo de zona
- **🔑 Renovar credenciales:** Formulario para actualizar tokens sin tocar el `.env`

---

### 📄 `.env` / `.env.example` — Credenciales

```bash
# Rappi — Token Bearer (dura días/semanas)
RAPPI_MX_TOKEN=ft.gAAAAA...

# Uber Eats — String de cookies (expira ~24h)
UBER_COOKIES=uev2.id.session=...; jwt-session=...
```

**Cómo renovar:**
1. Abrir la plataforma en Chrome
2. DevTools → Network → Buscar el request relevante
3. Copiar el header de autorización/cookies
4. Pegar en `.env` o usar el formulario del dashboard

---

## 6. Decisiones Técnicas Clave

### 🔧 API Reverse Engineering vs Web Scraping

| Aspecto | Reverse Engineering (lo que usamos) | Web Scraping (Selenium/Playwright) |
|---|---|---|
| **Velocidad** | ~1 segundo por request | ~10 segundos por página |
| **Estabilidad** | No depende del HTML/CSS | Se rompe si cambia la UI |
| **Detección** | Más difícil de detectar | WebDriver tiene fingerprint conocido |
| **Mantenimiento** | Solo actualizar endpoints | Mantener selectores CSS |

### 🥤 ¿Por qué Coca-Cola 500ml en lugar de Big Mac?

| Criterio | Big Mac (McDonald's) | Coca-Cola 500ml |
|---|---|---|
| Cobertura en Rappi | 4/21 zonas (19%) | 21/21 zonas (100%) |
| Disponibilidad | Solo McDonald's | OXXO, BK, Subway, tiendas... |
| Precio estándar | Varía por sucursal | $29 MXN nacional |

McDonald's no aparecía en el feed de Rappi en zonas como Polanco, Roma o Condesa porque
el algoritmo de ranking prioriza restaurantes locales. Coca-Cola está disponible en
prácticamente cualquier tienda o restaurante de México.

### 🔐 ¿Por qué no DiDi Food?

DiDi Food implementa una **firma criptográfica dinámica** (`wsgsig`) generada en el cliente
que cambia en cada request. Reproducirla requiere hacer reverse engineering del algoritmo
de firma embebido en su JavaScript bundle, lo cual está fuera del alcance de este proyecto.

---

## 7. Cobertura Geográfica

```
        CDMX (7 zonas)              Guadalajara (7 zonas)       Monterrey (7 zonas)
┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────────┐
│  🔵 Polanco    (wealthy)  │  │  🔵 Chapultepec (wealthy)│  │  🔵 San Pedro  (wealthy) │
│  🔵 Roma       (wealthy)  │  │  🔵 Providencia (wealthy)│  │  🔵 Centro     (wealthy) │
│  🟠 Coyoacán   (middle)   │  │  🟠 Centro      (middle) │  │  🟠 Obispado   (middle)  │
│  🟠 Iztapalapa (middle)   │  │  🟠 Zapopan     (middle) │  │  🟠 Cumbres    (middle)  │
│  🔴 Ecatepec   (peripheral)│ │  🟠 Tlaquepaque (middle) │  │  🔴 Apodaca    (peripheral)│
│  🔴 Chalco     (peripheral)│ │  🔴 Tonalá      (peripheral)││  🔴 Juárez     (peripheral)│
│                            │ │  🔴 Periférico  (peripheral)││  🔴 Escobedo   (peripheral)│
└──────────────────────────┘  └──────────────────────────┘  └──────────────────────────┘
```

---

## 8. Columnas del CSV de Output

El archivo `combined_v2.csv` contiene **19 columnas**:

| Columna | Tipo | Descripción |
|---|---|---|
| `zona_id` | string | Identificador único de la zona (`cdmx_polanco`) |
| `city` | string | Ciudad (`CDMX`, `Guadalajara`, `Monterrey`) |
| `zone_type` | string | Nivel socioeconómico (`wealthy`, `middle`, `peripheral`) |
| `lat` / `lng` | float | Coordenadas GPS del punto de consulta |
| `plataforma` | string | `rappi` o `uber_eats` |
| `restaurante` | string | Nombre de la tienda encontrada |
| `delivery_fee` | float | Costo de envío en MXN |
| `eta_min` / `eta_max` | int | Rango de tiempo estimado de entrega (minutos) |
| `coca_price` | float | Precio Coca-Cola 500ml en MXN |
| `coca_available` | bool | Si se encontró Coca-Cola en esa zona |
| `coca_name` | string | Nombre exacto del producto y tienda |
| `agua_price` | float | Precio Agua 1L en MXN |
| `agua_available` | bool | Si se encontró Agua en esa zona |
| `agua_name` | string | Nombre exacto del agua encontrada |
| `descuentos` | string | Promociones activas |
| `timestamp` | string | Momento del scraping (ISO 8601) |
| `error` | string | Descripción del error (null si exitosa) |

---

## 9. Resultados Obtenidos

### Cobertura de zonas

| Plataforma | Zonas exitosas | Error | Tienda encontrada |
|---|:---:|:---:|---|
| **Rappi** | **21/21** ✅ | 0 | Burger King, Carl's Jr., Subway, Walmart |
| **Uber Eats** | **21/21** ✅ | 0 | OXXO (21/21 zonas) |

### Datos de precios (Uber Eats — OXXO)

| Producto | Precio | Disponibilidad |
|---|---|---|
| Coca-Cola · Refresco sin azúcar (500 ml) | **$29.00 MXN** | 21/21 zonas |
| Coca-Cola · Refresco original (355 ml) | $29.50 MXN | 21/21 zonas |

### Delivery Fee (Rappi)

| Tipo de zona | Fee promedio |
|---|---|
| Wealthy (Polanco, San Pedro) | Variable por zona |
| Middle (Coyoacán, Cumbres) | Variable por zona |
| Peripheral (Ecatepec, Chalco) | Tiende a ser más alto |

---

## 10. Limitaciones Conocidas

| Limitación | Detalle | Impacto |
|---|---|---|
| **Credenciales expiran** | Rappi: días/semanas. Uber Eats: ~24 horas | Requiere renovación manual |
| **DiDi Food excluido** | Firma criptográfica `wsgsig` dinámica | No se puede reproducir el request |
| **Snapshot, no real-time** | Los datos son del momento del scraping | Para monitoreo continuo: cron/Airflow |
| **Uber Eats delivery fee** | No expuesto en la API pública | Columna queda null en el CSV |
| **Cookie de Uber Eats** | `uev2.loc` hardcoded a CDMX | Todas las zonas pueden devolver la misma tienda |
| **Rappi no muestra menú** | El feed no incluye catálogo de productos | `coca_price` queda null en Rappi |

---

## 11. Cómo ejecutar el proyecto

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Configurar credenciales
cp .env.example .env
# Editar .env con los tokens obtenidos de DevTools

# 3. Ejecutar el scraping completo (~3 minutos)
python src/run_all.py

# 4. Abrir el dashboard interactivo
streamlit run src/ui/app.py
```

---

## 12. Tecnologías y Dependencias

| Librería | Versión | Uso |
|---|---|---|
| `requests` | — | Llamadas HTTP a las APIs internas |
| `pandas` | — | Procesamiento y análisis de datos |
| `python-dotenv` | — | Carga de credenciales desde `.env` |
| `streamlit` | — | Dashboard web interactivo |
| `plotly` | — | Gráficas interactivas (barras, scatter) |

**Costo total del sistema: $0** — No utiliza proxies, servicios de scraping de pago
ni infraestructura cloud.

---

## 13. Posibles Mejoras Futuras

1. **Scheduler automático** — Cron job o Airflow para ejecutar el scraping cada X horas
2. **Base de datos** — PostgreSQL para almacenar datos históricos y detectar tendencias
3. **Alertas** — Notificación por Slack/email si un competidor cambia precios
4. **Más plataformas** — Agregar PedidosYa cuando se resuelva el captcha PerimeterX
5. **Resolución geográfica real** — Cookies por ciudad para Uber Eats (GDL, MTY)
6. **ML/Forecasting** — Predicción de precios o patrones estacionales con los datos históricos

---

> **Desarrollado como prueba técnica para Rappi — Abril 2026**
