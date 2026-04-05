"""
run_all.py — ejecuta Rappi y Uber Eats sobre las 21 zonas y genera combined_v2.csv.

Uso:
    python src/run_all.py

Salida:
    data/raw/rappi_v2.csv
    data/raw/ubereats_v2.csv
    data/raw/combined_v2.csv
"""

import os
import sys
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from scrapers.rappi     import run as run_rappi
from scrapers.uber_eats import run as run_uber_eats

COMBINED_PATH = "data/raw/combined_v2.csv"


def main():
    start = datetime.now()
    print("=" * 60)
    print(f"  Competitive Intelligence — run started {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── Rappi ──────────────────────────────────────────────────
    print("\n>>> RAPPI (21 zonas)")
    print("-" * 60)
    df_rappi = run_rappi("data/raw/rappi_v2.csv")

    # ── Uber Eats ──────────────────────────────────────────────
    print("\n>>> UBER EATS (21 zonas)")
    print("-" * 60)
    df_uber = run_uber_eats("data/raw/ubereats_v2.csv")

    # ── Combined ───────────────────────────────────────────────
    df_combined = pd.concat([df_rappi, df_uber], ignore_index=True)
    df_combined.to_csv(COMBINED_PATH, index=False)

    elapsed = (datetime.now() - start).seconds

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RESUMEN FINAL")
    print("=" * 60)

    for plataforma, df in [("rappi", df_rappi), ("uber_eats", df_uber)]:
        total    = len(df)
        with_fee = int(df["delivery_fee"].notna().sum())
        errors   = int(df["error"].notna().sum())
        n_coca = int(df["coca_available"].sum()) if "coca_available" in df.columns else 0
        n_agua = int(df["agua_available"].sum()) if "agua_available" in df.columns else 0

        print(f"\n  {plataforma.upper()}")
        print(f"    Zonas totales:      {total}")
        print(f"    Con delivery_fee:   {with_fee}/{total}")
        print(f"    Coca-Cola 500ml:    {n_coca}/{total}")
        print(f"    Agua 1L:            {n_agua}/{total}")
        print(f"    Zonas con error:    {errors}/{total}")

        if "restaurante" in df.columns:
            stores_found = df[df["restaurante"].notna()]["restaurante"].value_counts().head(3)
            if not stores_found.empty:
                print(f"    Top tiendas:")
                for name, count in stores_found.items():
                    print(f"      • {name}: {count} zonas")

    print(f"\n  COMBINED.CSV")
    print(f"    Total filas:     {len(df_combined)}")
    print(f"    Columnas:        {list(df_combined.columns)}")

    # Desglose por ciudad
    city_summary = (
        df_combined.groupby(["city", "plataforma"])
        .agg(
            filas    =("zona_id",        "count"),
            con_fee  =("delivery_fee",   lambda x: x.notna().sum()),
            coca_cola=("coca_available", "sum"),
            agua     =("agua_available", "sum"),
        )
        .reset_index()
    )
    print(f"\n  Desglose por ciudad:")
    print(city_summary.to_string(index=False))

    print(f"\n  Tiempo total: {elapsed}s")
    print("=" * 60)

    # Resumen compacto
    r_coca = int(df_rappi["coca_available"].sum())
    r_agua = int(df_rappi["agua_available"].sum())
    u_coca = int(df_uber["coca_available"].sum())
    u_agua = int(df_uber["agua_available"].sum())
    total  = 21

    print(f"\n  Rappi    — Coca-Cola: {r_coca}/{total} | Agua: {r_agua}/{total}")
    print(f"  UberEats — Coca-Cola: {u_coca}/{total} | Agua: {u_agua}/{total}")

    if len(df_combined) >= 30:
        print(f"\n  [OK] combined_v2.csv tiene {len(df_combined)} filas. Validación superada.")
    else:
        print(f"\n  [WARN] combined_v2.csv solo tiene {len(df_combined)} filas (mínimo 30).")

    return df_combined


if __name__ == "__main__":
    main()
