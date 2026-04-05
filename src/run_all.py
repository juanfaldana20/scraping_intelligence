"""
run_all.py — ejecuta Rappi y Uber Eats sobre las 21 zonas y genera combined.csv.

Uso:
    python src/run_all.py

Salida:
    data/raw/rappi_full.csv
    data/raw/ubereats_full.csv
    data/raw/combined.csv
"""

import os
import sys
import pandas as pd
from datetime import datetime

# Allow imports from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from scrapers.rappi     import run as run_rappi
from scrapers.uber_eats import run as run_uber_eats

COMBINED_PATH = "data/raw/combined.csv"


def main():
    start = datetime.now()
    print("=" * 60)
    print(f"  Competitive Intelligence — run started {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── Rappi ──────────────────────────────────────────────────
    print("\n>>> RAPPI (21 zonas)")
    print("-" * 60)
    df_rappi = run_rappi("data/raw/rappi_full.csv")

    # ── Uber Eats ──────────────────────────────────────────────
    print("\n>>> UBER EATS (21 zonas)")
    print("-" * 60)
    df_uber = run_uber_eats("data/raw/ubereats_full.csv")

    # ── Combined ───────────────────────────────────────────────
    df_combined = pd.concat([df_rappi, df_uber], ignore_index=True)
    df_combined.to_csv(COMBINED_PATH, index=False)

    elapsed = (datetime.now() - start).seconds

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RESUMEN FINAL")
    print("=" * 60)

    for plataforma, df in [("rappi", df_rappi), ("uber_eats", df_uber)]:
        total       = len(df)
        with_data   = df["delivery_fee"].notna().sum()
        errors      = df["error"].notna().sum()
        with_product = int(df["product_available"].sum()) if "product_available" in df.columns else 0
        with_price   = df["product_price"].notna().sum() if "product_price" in df.columns else 0

        print(f"\n  {plataforma.upper()}")
        print(f"    Zonas totales:            {total}")
        print(f"    Zonas con delivery_fee:   {with_data}")
        print(f"    Zonas con tienda/producto:{with_product}")
        if plataforma == "uber_eats":
            print(f"    Zonas con precio producto:{int(with_price)}")
        print(f"    Zonas con error:          {errors}")

        # Mostrar tiendas encontradas
        if "restaurante" in df.columns:
            stores_found = df[df["restaurante"].notna()]["restaurante"].value_counts().head(5)
            if not stores_found.empty:
                print(f"    Top tiendas encontradas:")
                for name, count in stores_found.items():
                    print(f"      • {name}: {count} zonas")

    print(f"\n  COMBINED.CSV")
    print(f"    Total filas:     {len(df_combined)}")
    print(f"    Columnas:        {list(df_combined.columns)}")

    # City breakdown
    city_summary = (
        df_combined.groupby(["city", "plataforma"])
        .agg(filas=("zona_id", "count"),
             con_fee=("delivery_fee", lambda x: x.notna().sum()),
             con_producto=("product_available", "sum"))
        .reset_index()
    )
    print(f"\n  Desglose por ciudad:")
    print(city_summary.to_string(index=False))

    print(f"\n  Tiempo total: {elapsed}s")
    print("=" * 60)

    if len(df_combined) >= 30:
        print("\n  [OK] combined.csv tiene >= 30 filas. Validación superada.")
    else:
        print(f"\n  [WARN] combined.csv solo tiene {len(df_combined)} filas (mínimo 30).")

    return df_combined


if __name__ == "__main__":
    main()
