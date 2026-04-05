"""
Configuración de zonas geográficas para el sistema de scraping.

Define las 21 zonas distribuidas en 3 ciudades de México:
- CDMX (7 zonas): Polanco, Roma, Condesa, Coyoacán, Iztapalapa, Ecatepec, Chalco
- Guadalajara (7 zonas): Chapultepec, Providencia, Centro, Zapopan, Tlaquepaque, Tonalá, Periférico
- Monterrey (7 zonas): San Pedro, Centro, Obispado, Cumbres, Apodaca, Juárez, Escobedo

Cada zona está clasificada por nivel socioeconómico:
- wealthy:    Zonas de alto poder adquisitivo (ej: Polanco, San Pedro)
- middle:     Zonas de clase media (ej: Coyoacán, Zapopan)
- peripheral: Zonas periféricas de menor ingreso (ej: Ecatepec, Apodaca)

Esta clasificación permite analizar si las plataformas de delivery
aplican pricing diferenciado según el nivel socioeconómico de la zona.
"""

ZONES = [
    # ── CDMX (7 zonas) ───────────────────────────────────────────────────────
    {"id": "cdmx_polanco",    "city": "CDMX",         "type": "wealthy",    "lat": 19.4326, "lng": -99.1950},
    {"id": "cdmx_roma",       "city": "CDMX",         "type": "wealthy",    "lat": 19.4195, "lng": -99.1575},
    {"id": "cdmx_condesa",    "city": "CDMX",         "type": "wealthy",    "lat": 19.4127, "lng": -99.1721},
    {"id": "cdmx_coyoacan",   "city": "CDMX",         "type": "middle",     "lat": 19.3467, "lng": -99.1617},
    {"id": "cdmx_iztapalapa", "city": "CDMX",         "type": "middle",     "lat": 19.3557, "lng": -99.0629},
    {"id": "cdmx_ecatepec",   "city": "CDMX",         "type": "peripheral", "lat": 19.6016, "lng": -99.0600},
    {"id": "cdmx_chalco",     "city": "CDMX",         "type": "peripheral", "lat": 19.2620, "lng": -98.8990},

    # ── Guadalajara (7 zonas) ─────────────────────────────────────────────────
    {"id": "gdl_chapultepec", "city": "Guadalajara",   "type": "wealthy",    "lat": 20.6736, "lng": -103.3820},
    {"id": "gdl_providencia", "city": "Guadalajara",   "type": "wealthy",    "lat": 20.6891, "lng": -103.3849},
    {"id": "gdl_centro",      "city": "Guadalajara",   "type": "middle",     "lat": 20.6767, "lng": -103.3475},
    {"id": "gdl_zapopan",     "city": "Guadalajara",   "type": "middle",     "lat": 20.7214, "lng": -103.3916},
    {"id": "gdl_tlaquepaque", "city": "Guadalajara",   "type": "middle",     "lat": 20.6418, "lng": -103.3117},
    {"id": "gdl_tonala",      "city": "Guadalajara",   "type": "peripheral", "lat": 20.6238, "lng": -103.2341},
    {"id": "gdl_periferico",  "city": "Guadalajara",   "type": "peripheral", "lat": 20.6102, "lng": -103.4089},

    # ── Monterrey (7 zonas) ───────────────────────────────────────────────────
    {"id": "mty_san_pedro",   "city": "Monterrey",     "type": "wealthy",    "lat": 25.6577, "lng": -100.3639},
    {"id": "mty_centro",      "city": "Monterrey",     "type": "wealthy",    "lat": 25.6714, "lng": -100.3090},
    {"id": "mty_obispado",    "city": "Monterrey",     "type": "middle",     "lat": 25.6791, "lng": -100.3558},
    {"id": "mty_cumbres",     "city": "Monterrey",     "type": "middle",     "lat": 25.7484, "lng": -100.3697},
    {"id": "mty_apodaca",     "city": "Monterrey",     "type": "peripheral", "lat": 25.7797, "lng": -100.1879},
    {"id": "mty_juarez",      "city": "Monterrey",     "type": "peripheral", "lat": 25.6500, "lng": -100.1100},
    {"id": "mty_escobedo",    "city": "Monterrey",     "type": "peripheral", "lat": 25.7964, "lng": -100.3167},
]
