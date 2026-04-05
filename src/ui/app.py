"""
Competitive Intelligence Dashboard — Rappi vs Uber Eats México
Run: streamlit run src/ui/app.py  (desde la raíz del proyecto)
"""

import subprocess
import pandas as pd
import plotly.express as px
import streamlit as st
from pathlib import Path

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CI Dashboard — Delivery México",
    page_icon="📦",
    layout="wide",
)

# ── color palettes ────────────────────────────────────────────────────────────
PLATFORM_COLORS  = {"rappi": "#FF441F", "uber_eats": "#000000"}
ZONE_TYPE_COLORS = {"wealthy": "#2196F3", "middle": "#FF9800", "peripheral": "#F44336"}

# ── helpers ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent  # scraping_intelligence/

def update_env_variable(key: str, value: str):
    env_path = ROOT / ".env"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"{key}={value}")
        env_path.write_text("\n".join(new_lines))
    else:
        env_path.write_text(f"{key}={value}")


# ── load data ─────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    path = ROOT / "data/raw/combined_v2.csv"
    if not path.exists():
        path = ROOT / "data/raw/combined.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    for col in ["delivery_fee", "coca_price", "agua_price", "eta_min", "eta_max"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # backwards compat: si viene product_price en lugar de coca_price
    if "product_price" in df.columns and "coca_price" not in df.columns:
        df["coca_price"] = pd.to_numeric(df["product_price"], errors="coerce")
    return df

df_all = load_data()

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:

    # ── control ──────────────────────────────────────────────────────────────
    st.subheader("⚙️ Control")

    if st.button("▶ Ejecutar Scraping", type="primary", use_container_width=True):
        with st.status("Ejecutando scraping...", expanded=True) as status:
            st.write("🔄 Scraping Rappi — 21 zonas...")
            st.write("🔄 Scraping Uber Eats — 21 zonas...")
            st.write("🔄 Generando combined_v2.csv...")
            result = subprocess.run(
                ["python3", str(ROOT / "src/run_all.py")],
                capture_output=True, text=True, cwd=str(ROOT)
            )
            if result.returncode == 0:
                st.write("✅ Rappi completado")
                st.write("✅ Uber Eats completado")
                st.write("✅ Datos actualizados")
                status.update(label="Scraping completado", state="complete")
                st.success("✅ Scraping completado exitosamente")
                st.cache_data.clear()
                st.rerun()
            else:
                status.update(label="Error en scraping", state="error")
                st.error(f"❌ Error:\n{result.stderr[-800:] if result.stderr else 'Sin detalle'}")

    # timestamp del último scraping
    combined_path = ROOT / "data/raw/combined_v2.csv"
    if combined_path.exists():
        try:
            ts_df = pd.read_csv(combined_path, usecols=["timestamp"], nrows=1)
            ts = pd.to_datetime(ts_df["timestamp"].iloc[0])
            st.caption(f"Último scraping: {ts.strftime('%d %b %Y %H:%M')}")
        except Exception:
            st.caption("Último scraping: fecha no disponible")
    else:
        st.caption("Sin datos — ejecuta el scraping")

    st.divider()

    # ── filtros ───────────────────────────────────────────────────────────────
    st.header("Filtros")

    if df_all.empty:
        st.warning("Sin datos. Ejecuta el scraping primero.")
        cities     = []
        zone_types = []
        sel_cities = []
        sel_types  = []
    else:
        cities     = sorted(df_all["city"].unique())
        zone_types = sorted(df_all["zone_type"].unique())
        sel_cities = st.multiselect("Ciudad", cities, default=cities)
        sel_types  = st.multiselect("Tipo de zona", zone_types, default=zone_types)

    st.caption("21 zonas · 2 plataformas")
    st.caption("CDMX · Guadalajara · Monterrey")

    st.divider()

    # ── credenciales ──────────────────────────────────────────────────────────
    with st.expander("🔑 Renovar credenciales", expanded=False):
        st.caption("Las credenciales expiran periódicamente. Actualízalas aquí sin tocar el código.")

        st.markdown("**Rappi MX Token**")
        st.caption("rappi.com.mx → DevTools → Network → catalog-paged/home → authorization (sin 'Bearer ')")
        rappi_token = st.text_area(
            "Token de Rappi", height=100,
            placeholder="ft.gAAAAA...",
            key="rappi_token_input",
        )
        if st.button("💾 Guardar token Rappi", key="save_rappi"):
            if rappi_token.strip():
                update_env_variable("RAPPI_MX_TOKEN", rappi_token.strip())
                st.success("✅ Token de Rappi actualizado")
                st.info("Ejecuta el scraping para obtener datos frescos")
            else:
                st.warning("El token no puede estar vacío")

        st.divider()

        st.markdown("**Uber Eats Cookies**")
        st.caption("ubereats.com/mx → DevTools → Network → getFeedV1 → Request Headers → cookie")
        uber_cookies = st.text_area(
            "Cookies de Uber Eats", height=100,
            placeholder="uev2.id.session=...; jwt-session=...",
            key="uber_cookies_input",
        )
        if st.button("💾 Guardar cookies Uber Eats", key="save_uber"):
            if uber_cookies.strip():
                update_env_variable("UBER_COOKIES", uber_cookies.strip())
                st.success("✅ Cookies de Uber Eats actualizadas")
                st.info("El jwt-session expira en ~24 horas")
            else:
                st.warning("Las cookies no pueden estar vacías")


# ── apply filters ─────────────────────────────────────────────────────────────
if df_all.empty or not sel_cities or not sel_types:
    st.title("Competitive Intelligence — Delivery México")
    st.info("Sin datos. Usa el botón **▶ Ejecutar Scraping** en el sidebar para comenzar.")
    st.stop()

df = df_all[
    df_all["city"].isin(sel_cities) &
    df_all["zone_type"].isin(sel_types)
].copy()

df_rappi = df[df["plataforma"] == "rappi"]
df_uber  = df[df["plataforma"] == "uber_eats"]

# ── header ────────────────────────────────────────────────────────────────────
st.title("Competitive Intelligence — Delivery México")
st.markdown(
    "**Rappi vs Uber Eats** &nbsp;|&nbsp; "
    "CDMX · Guadalajara · Monterrey &nbsp;|&nbsp; Abril 2026"
)
st.divider()

# ── tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 Overview", "🗺️ Por Zona", "💡 Top 5 Insights", "📋 Datos Raw"]
)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:

    # ── metrics row ──────────────────────────────────────────────────────────
    rappi_fee_avg = df_rappi["delivery_fee"].mean()
    rappi_eta_avg = df_rappi["eta_min"].mean()
    uber_eta_avg  = df_uber["eta_min"].mean()
    coca_price    = df_uber["coca_price"].mean() if "coca_price" in df_uber.columns else float("nan")
    agua_price    = df_uber["agua_price"].mean() if "agua_price" in df_uber.columns else float("nan")
    zones_w_desc  = int(df_rappi["descuentos"].notna().sum())

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric(
        "Fee promedio Rappi",
        f"${rappi_fee_avg:.1f} MXN" if not pd.isna(rappi_fee_avg) else "Sin datos",
    )
    c2.metric("Fee promedio Uber Eats", "Sin datos",
              help="Uber Eats no expone delivery fee en su API pública")
    c3.metric(
        "ETA promedio Rappi",
        f"{rappi_eta_avg:.0f} min" if not pd.isna(rappi_eta_avg) else "Sin datos",
    )
    c4.metric(
        "ETA promedio Uber Eats",
        f"{uber_eta_avg:.0f} min" if not pd.isna(uber_eta_avg) else "Sin datos",
    )
    c5.metric(
        "Coca-Cola (Uber Eats)",
        f"${coca_price:.0f} MXN" if not pd.isna(coca_price) else "Sin datos",
    )
    c6.metric("Zonas con descuento (Rappi)", f"{zones_w_desc} / {len(df_rappi)}")

    st.divider()

    # ── chart 1 — delivery fee rappi por ciudad ───────────────────────────────
    st.subheader("Delivery Fee Rappi por Ciudad y Tipo de Zona (MXN)")

    df_fee = (
        df_rappi[df_rappi["delivery_fee"].notna()]
        .groupby(["city", "zone_type"], as_index=False)["delivery_fee"]
        .mean()
        .round(2)
    )
    df_fee["city"] = pd.Categorical(
        df_fee["city"], categories=["CDMX", "Guadalajara", "Monterrey"], ordered=True
    )
    df_fee = df_fee.sort_values(["city", "zone_type"])

    fig1 = px.bar(
        df_fee,
        x="city", y="delivery_fee", color="zone_type",
        barmode="group",
        color_discrete_map=ZONE_TYPE_COLORS,
        labels={"delivery_fee": "Delivery Fee (MXN)", "city": "Ciudad", "zone_type": "Tipo de zona"},
        text_auto=".1f",
    )
    fig1.update_layout(
        legend_title="Tipo de zona",
        xaxis_title="Ciudad",
        yaxis_title="Delivery Fee promedio (MXN)",
        height=380,
    )
    st.plotly_chart(fig1, use_container_width=True)
    st.caption("⚠️ Uber Eats no expone el delivery fee en su API pública — dato no disponible para comparación directa.")

    st.divider()

    # ── chart 2 — ETA comparado ───────────────────────────────────────────────
    st.subheader("Tiempo de Entrega Promedio por Ciudad (minutos)")

    df_eta = (
        df.groupby(["city", "plataforma"], as_index=False)["eta_min"]
        .mean()
        .round(1)
    )
    df_eta["city"] = pd.Categorical(
        df_eta["city"], categories=["CDMX", "Guadalajara", "Monterrey"], ordered=True
    )
    df_eta = df_eta.sort_values("city")

    fig2 = px.bar(
        df_eta,
        x="city", y="eta_min", color="plataforma",
        barmode="group",
        color_discrete_map=PLATFORM_COLORS,
        labels={"eta_min": "ETA mínimo promedio (min)", "city": "Ciudad", "plataforma": "Plataforma"},
        text_auto=".1f",
    )
    fig2.update_layout(
        legend_title="Plataforma",
        xaxis_title="Ciudad",
        yaxis_title="ETA mínimo promedio (min)",
        height=380,
    )
    st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # ── chart 3 — fee por zona scatter ────────────────────────────────────────
    st.subheader("Variabilidad del Delivery Fee por Zona — Rappi")

    df_scatter = df_rappi[df_rappi["delivery_fee"].notna()].copy()
    df_scatter = df_scatter.sort_values(["city", "zone_type"])

    fig3 = px.scatter(
        df_scatter,
        x="zona_id", y="delivery_fee",
        color="zone_type", size_max=14,
        color_discrete_map=ZONE_TYPE_COLORS,
        hover_data=["city", "restaurante", "delivery_fee"],
        labels={"delivery_fee": "Delivery Fee (MXN)", "zona_id": "Zona", "zone_type": "Tipo"},
    )
    fig3.update_traces(marker=dict(size=14, opacity=0.85))
    fig3.update_layout(
        xaxis_tickangle=45,
        xaxis_title="Zona",
        yaxis_title="Delivery Fee (MXN)",
        height=420,
        legend_title="Tipo de zona",
    )
    st.plotly_chart(fig3, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — POR ZONA
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:

    all_zona_ids = sorted(df["zona_id"].unique())
    sel_zona = st.selectbox("Selecciona una zona para ver detalle", all_zona_ids)

    st.divider()

    col_table, col_detail = st.columns([3, 2])

    with col_table:
        st.subheader("Tabla de zonas")
        display_cols = [c for c in [
            "zona_id", "city", "zone_type", "plataforma",
            "delivery_fee", "eta_min", "restaurante",
            "coca_price", "agua_price", "descuentos"
        ] if c in df.columns]
        df_display = (
            df[display_cols]
            .sort_values(["city", "zone_type", "plataforma"])
            .reset_index(drop=True)
        )
        st.dataframe(df_display, use_container_width=True, height=520)

    with col_detail:
        st.subheader(f"Detalle — {sel_zona}")
        zona_df = df[df["zona_id"] == sel_zona]

        if zona_df.empty:
            st.info("Zona no disponible con los filtros actuales.")
        else:
            meta = zona_df.iloc[0]
            st.markdown(
                f"**Ciudad:** {meta['city']} &nbsp;|&nbsp; "
                f"**Tipo:** {meta['zone_type']} &nbsp;|&nbsp; "
                f"**Coords:** {meta['lat']}, {meta['lng']}"
            )
            st.divider()

            for _, row in zona_df.iterrows():
                plat = row["plataforma"]
                color = "#FF441F" if plat == "rappi" else "#000000"
                st.markdown(
                    f"<span style='color:{color}; font-weight:700; font-size:1.1em'>"
                    f"{'🟠 Rappi' if plat == 'rappi' else '⚫ Uber Eats'}</span>",
                    unsafe_allow_html=True,
                )
                m1, m2, m3 = st.columns(3)
                m1.metric(
                    "Delivery Fee",
                    f"${row['delivery_fee']:.1f}" if pd.notna(row["delivery_fee"]) else "N/D",
                )
                m2.metric(
                    "ETA",
                    f"{int(row['eta_min'])}–{int(row['eta_max'])} min"
                    if pd.notna(row.get("eta_min")) and pd.notna(row.get("eta_max"))
                    else (f"{int(row['eta_min'])} min" if pd.notna(row.get("eta_min")) else "N/D"),
                )
                coca_val = row.get("coca_price")
                m3.metric(
                    "Coca-Cola",
                    f"${coca_val:.0f}" if pd.notna(coca_val) else "N/D",
                )
                agua_val = row.get("agua_price")
                if pd.notna(agua_val):
                    st.caption(f"💧 Agua: ${agua_val:.0f} MXN")
                if pd.notna(row.get("restaurante")):
                    st.caption(f"🏪 {row['restaurante']}")
                if pd.notna(row.get("descuentos")):
                    st.caption(f"🏷️ {row['descuentos']}")
                st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — TOP 5 INSIGHTS
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("💡 Top 5 Insights — Competitive Intelligence")
    st.caption("Calculados en tiempo real sobre los datos filtrados.")
    st.divider()

    r_fee = df_rappi["delivery_fee"].dropna()
    u_eta = df_uber["eta_min"].dropna()
    r_eta = df_rappi["eta_min"].dropna()

    fee_max      = r_fee.max() if not r_fee.empty else 0
    fee_min      = r_fee.min() if not r_fee.empty else 0
    zone_max     = df_rappi.loc[df_rappi["delivery_fee"].idxmax(), "zona_id"] if not r_fee.empty else "N/A"
    zone_min     = df_rappi.loc[df_rappi["delivery_fee"].idxmin(), "zona_id"] if not r_fee.empty else "N/A"
    fee_diff_pct = ((fee_max - fee_min) / fee_min * 100) if fee_min > 0 else 0

    r_eta_avg = r_eta.mean() if not r_eta.empty else 0
    u_eta_avg = u_eta.mean() if not u_eta.empty else 0
    eta_diff  = r_eta_avg - u_eta_avg
    faster    = "Uber Eats" if eta_diff > 0 else "Rappi"
    slower    = "Rappi" if eta_diff > 0 else "Uber Eats"

    fee_by_type = df_rappi.groupby("zone_type")["delivery_fee"].mean().round(1)
    peri_fee    = fee_by_type.get("peripheral", 0)
    wealthy_fee = fee_by_type.get("wealthy", 0)
    peri_vs_w   = ((peri_fee - wealthy_fee) / wealthy_fee * 100) if wealthy_fee > 0 else 0

    city_eta     = df.groupby("city")["eta_min"].mean().round(1)
    fastest_city = city_eta.idxmin() if not city_eta.empty else "N/A"
    fastest_val  = city_eta.min() if not city_eta.empty else 0

    n_desc        = int(df_rappi["descuentos"].notna().sum())
    n_total_rappi = len(df_rappi)
    uber_desc     = int(df_uber["descuentos"].notna().sum())

    def insight_card(emoji, title, finding, impact, recommendation):
        st.markdown(
            f"""
<div style="background:#f8f9fa; border-left:4px solid #FF441F;
            padding:1rem 1.2rem; border-radius:6px; margin-bottom:1rem;">
  <p style="font-size:1.1em; margin:0 0 0.4rem 0">{emoji} <strong>{title}</strong></p>
  <p style="margin:0 0 0.3rem 0">📌 <em>Finding:</em> {finding}</p>
  <p style="margin:0 0 0.3rem 0">📈 <em>Impacto:</em> {impact}</p>
  <p style="margin:0">✅ <em>Recomendación:</em> {recommendation}</p>
</div>
""",
            unsafe_allow_html=True,
        )

    insight_card(
        "💸", "Delivery Fee: zona más cara vs más barata (Rappi)",
        f"La zona <strong>{zone_max}</strong> tiene el fee más alto "
        f"(${fee_max:.0f} MXN) y <strong>{zone_min}</strong> el más bajo "
        f"(${fee_min:.1f} MXN).",
        f"El fee máximo es <strong>{fee_diff_pct:.0f}% más caro</strong> que el mínimo — "
        f"brecha de ${fee_max - fee_min:.1f} MXN por pedido.",
        "Revisar el pricing en zonas periféricas con fee alto; "
        "una brecha de >" + str(round(fee_max - fee_min)) + " MXN puede inhibir la conversión.",
    )

    insight_card(
        "⚡", f"{faster} es más rápido que {slower}",
        f"{faster} entrega en promedio en <strong>{min(r_eta_avg, u_eta_avg):.0f} min</strong> "
        f"vs {slower} en <strong>{max(r_eta_avg, u_eta_avg):.0f} min</strong>.",
        f"Diferencia de <strong>{abs(eta_diff):.1f} minutos</strong> a favor de {faster} "
        f"en el dataset filtrado.",
        f"Rappi debe priorizar optimización de last-mile en CDMX donde la brecha es mayor.",
    )

    insight_card(
        "🗺️", "Periféricas pagan más delivery fee (Rappi)",
        f"Zonas <strong>periféricas</strong>: ${peri_fee:.1f} MXN promedio · "
        f"<strong>wealthy</strong>: ${wealthy_fee:.1f} MXN promedio.",
        f"Las periféricas pagan <strong>{peri_vs_w:+.0f}%</strong> más que las zonas ricas — "
        f"las regiones de menor ingreso asumen el mayor costo logístico.",
        "Considerar subsidio de tarifa en zonas periféricas o programa loyalty para "
        "reducir el churn por costo de envío.",
    )

    insight_card(
        "🏆", f"{fastest_city} es la ciudad más competitiva en tiempos",
        f"<strong>{fastest_city}</strong> tiene el menor ETA promedio combinado: "
        f"<strong>{fastest_val:.0f} min</strong> entre ambas plataformas.",
        f"Una operación más eficiente en {fastest_city} se traduce en mejor NPS "
        f"y mayor probabilidad de recompra.",
        f"Documentar el modelo operacional de {fastest_city} y replicarlo en las ciudades más lentas.",
    )

    insight_card(
        "🏷️", "Rappi tiene descuentos activos en todas las zonas",
        f"<strong>{n_desc} de {n_total_rappi}</strong> zonas Rappi muestran descuentos activos. "
        f"Uber Eats muestra descuentos en {uber_desc} zonas.",
        "Rappi usa una estrategia agresiva de descuentos para retener usuarios — "
        "costo de adquisición/retención elevado.",
        "Monitorear semanalmente si Uber Eats replica con descuentos similares; "
        "evaluar la rentabilidad del subsidio de envío vs el lifetime value del usuario.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — DATOS RAW
# ═══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader(f"Datos raw — {len(df)} filas · {len(df.columns)} columnas")
    st.dataframe(df, use_container_width=True, height=520)

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Descargar CSV filtrado",
        data=csv_bytes,
        file_name="competitive_intelligence_filtrado.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    pass
