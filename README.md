# Competitive Intelligence — Rappi vs Uber Eats México

Sistema de scraping que recolecta datos de precios, delivery fees y tiempos de entrega de Rappi y Uber Eats en 21 zonas de México (CDMX, Guadalajara y Monterrey). Genera un dashboard interactivo con análisis comparativo e insights accionables para equipos de Strategy y Pricing.

---

## Plataformas analizadas

| Plataforma | Método | Zonas | Estado |
|---|---|---|---|
| Rappi MX | API interna (reverse engineering) | 21 / 21 | ✅ Operativo |
| Uber Eats MX | API interna (reverse engineering) | 21 / 21 | ✅ Operativo |
| DiDi Food MX | — | — | ❌ Fuera de scope (ver [Limitaciones](#limitaciones-conocidas)) |

---

## Stack tecnológico

| Componente | Tecnología | Uso |
|---|---|---|
| Lenguaje | Python 3.11+ | Base del proyecto |
| Scraping | `requests` | Llamadas directas a APIs internas |
| Análisis | `pandas` | Procesamiento y análisis de datos |
| Dashboard | `Streamlit` | Visualización interactiva |
| Gráficos | `Plotly` | Visualizaciones comparativas |
| Config | `python-dotenv` | Manejo de credenciales |

---

## Instalación

**Paso 1 — Clonar el repositorio**

```bash
git clone <url-del-repo>
cd scraping_intelligence
```

**Paso 2 — Instalar dependencias**

```bash
pip install -r requirements.txt
```

**Paso 3 — Configurar credenciales**

```bash
cp .env.example .env
```

Editar `.env` con las siguientes variables:

```
RAPPI_MX_TOKEN=<bearer_token>
UBER_COOKIES=<cookie_string>
```

**Cómo obtener `RAPPI_MX_TOKEN`:**
1. Abrir [rappi.com.mx](https://www.rappi.com.mx) en Chrome
2. DevTools → pestaña **Network** → filtrar por `catalog-paged`
3. Seleccionar cualquier request a `catalog-paged/home`
4. En **Request Headers** → copiar el valor de `authorization` (sin el prefijo `Bearer `)

**Cómo obtener `UBER_COOKIES`:**
1. Abrir [ubereats.com/mx](https://www.ubereats.com/mx) en Chrome con sesión iniciada
2. DevTools → pestaña **Network** → filtrar por `getFeedV1`
3. Seleccionar cualquier request a `getFeedV1`
4. En **Request Headers** → copiar el string completo del campo `cookie`

---

## Cómo ejecutar

**Scraping completo (ambas plataformas, 21 zonas):**

```bash
python src/run_all.py
```

- Tiempo estimado: ~3 minutos
- Output: `data/raw/combined.csv`, `data/raw/rappi_full.csv`, `data/raw/ubereats_full.csv`

**Dashboard interactivo:**

```bash
streamlit run src/ui/app.py
```

Abrir en el navegador: [http://localhost:8501](http://localhost:8501)

---

## Cobertura geográfica

21 zonas distribuidas en 3 ciudades, clasificadas por nivel socioeconómico:

| zona_id | Ciudad | Tipo |
|---|---|---|
| cdmx_polanco | CDMX | wealthy |
| cdmx_roma | CDMX | wealthy |
| cdmx_condesa | CDMX | wealthy |
| cdmx_coyoacan | CDMX | middle |
| cdmx_iztapalapa | CDMX | middle |
| cdmx_ecatepec | CDMX | peripheral |
| cdmx_chalco | CDMX | peripheral |
| gdl_chapultepec | Guadalajara | wealthy |
| gdl_providencia | Guadalajara | wealthy |
| gdl_centro | Guadalajara | middle |
| gdl_zapopan | Guadalajara | middle |
| gdl_tlaquepaque | Guadalajara | middle |
| gdl_tonala | Guadalajara | peripheral |
| gdl_periferico | Guadalajara | peripheral |
| mty_san_pedro | Monterrey | wealthy |
| mty_centro | Monterrey | wealthy |
| mty_obispado | Monterrey | middle |
| mty_cumbres | Monterrey | middle |
| mty_apodaca | Monterrey | peripheral |
| mty_juarez | Monterrey | peripheral |
| mty_escobedo | Monterrey | peripheral |

---

## Decisiones técnicas

### Reverse engineering de APIs

En lugar de usar Playwright o Selenium para automatizar el browser, se interceptaron las APIs internas de cada plataforma con Chrome DevTools y se llaman directamente con `requests`. Esto tiene tres ventajas sobre el scraping de DOM:

- **Velocidad:** una llamada HTTP directa tarda ~1s vs ~10s de un browser headless
- **Estabilidad:** no depende del layout del HTML ni de cambios de UI
- **Resiliencia:** más difícil de bloquear que un WebDriver con fingerprint conocido

### Producto de referencia — Coca-Cola 500ml

Se eligió Coca-Cola 500ml como producto de referencia en lugar del Big Mac porque está disponible en múltiples tipos de tiendas (conveniencia, supermercados, fast food) en todas las zonas geográficas analizadas. McDonald's solo aparecía en el top-50 del feed de Rappi en el 19% de las zonas (4/21), ya que el algoritmo de ranking de Rappi prioriza restaurantes locales en zonas upscale. La Coca-Cola 500ml garantiza cobertura del 100%.

### DiDi Food — fuera de scope

DiDi Food implementa firmas criptográficas dinámicas (`wsgsig`) generadas en el cliente que varían en cada request. Reproducirlas requiere hacer reverse engineering del algoritmo de firma embebido en su app o JS bundle, lo cual está fuera del alcance de este proyecto. La arquitectura del sistema está diseñada para agregar nuevas plataformas fácilmente (un nuevo archivo en `src/scrapers/`) cuando se resuelva este blocker.

---

## Limitaciones conocidas

| Limitación | Detalle |
|---|---|
| Expiración de credenciales | `RAPPI_MX_TOKEN` dura días o semanas según la sesión. `UBER_COOKIES` (específicamente `jwt-session`) expira en ~24 horas y debe renovarse desde DevTools. |
| DiDi Food no incluido | Firma criptográfica dinámica (`wsgsig`) impide reproducir las llamadas. |
| Snapshot, no tiempo real | Los datos reflejan el momento del scraping. Para monitoreo continuo se requiere un scheduler (cron, Airflow, etc.). |
| Delivery fee de Uber Eats | La plataforma no expone el delivery fee en el endpoint público de feed (`getFeedV1`). El campo aparece como `null` en el CSV. |
| Resolución geográfica de Uber Eats | La cookie `uev2.loc` tiene hardcoded una ubicación CDMX. Uber Eats puede retornar la misma tienda para todas las zonas si la cookie domina sobre los headers `x-uber-target-location-*`. Para resolución por ciudad se necesitan cookies capturadas desde GDL y MTY. |

---

## Estructura del CSV de output

El archivo `data/raw/combined.csv` consolida los datos de ambas plataformas con las siguientes columnas:

| Columna | Tipo | Descripción |
|---|---|---|
| `zona_id` | string | Identificador único de la zona (ej. `cdmx_polanco`) |
| `city` | string | Ciudad (`CDMX`, `Guadalajara`, `Monterrey`) |
| `zone_type` | string | Clasificación socioeconómica (`wealthy`, `middle`, `peripheral`) |
| `lat` | float | Latitud del punto de consulta |
| `lng` | float | Longitud del punto de consulta |
| `plataforma` | string | Plataforma scrapeada (`rappi`, `uber_eats`) |
| `restaurante` | string | Nombre de la tienda encontrada en el feed |
| `delivery_fee` | float | Costo de envío en MXN (null si no disponible) |
| `eta_min` | int | Tiempo de entrega mínimo estimado (minutos) |
| `eta_max` | float | Tiempo de entrega máximo estimado (minutos) |
| `product_price` | float | Precio del producto de referencia en MXN (null en Rappi) |
| `product_available` | bool | Si se encontró un producto de referencia en esa zona |
| `product_name` | string | Nombre exacto del producto y tienda encontrados |
| `descuentos` | string | Texto de promociones activas (null si no hay) |
| `timestamp` | string | ISO 8601 del momento del scraping |
| `error` | string | Mensaje de error si la zona falló (null si exitosa) |

---

## Estructura del proyecto

```
scraping_intelligence/
├── data/raw/
│   ├── combined.csv          ← datos de ambas plataformas combinados (42 filas)
│   ├── rappi_full.csv        ← datos completos de Rappi (21 zonas)
│   ├── rappi_test.csv        ← datos de prueba iniciales (3 zonas)
│   ├── ubereats_full.csv     ← datos completos de Uber Eats (21 zonas)
│   └── ubereats_test.csv     ← datos de prueba iniciales (3 zonas)
├── src/
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── rappi.py          ← scraper de Rappi MX via API interna
│   │   └── uber_eats.py      ← scraper de Uber Eats MX via API interna
│   ├── ui/
│   │   └── app.py            ← dashboard Streamlit (4 tabs)
│   ├── __init__.py
│   ├── config.py             ← 21 zonas definidas (CDMX, GDL, MTY)
│   └── run_all.py            ← orquestador: ejecuta scrapers y genera combined.csv
├── .env                      ← credenciales (no incluir en repo)
├── .env.example              ← template de variables requeridas
├── README.md
└── requirements.txt
```

---

## Costo estimado

**$0** — El sistema consume APIs públicas no oficiales sin uso de proxies, servicios de scraping de pago ni infraestructura cloud. El único costo potencial es el tiempo de renovación manual de credenciales (~5 min cada 24h para Uber Eats).

---

> Desarrollado como prueba técnica para Rappi — Abril 2026
