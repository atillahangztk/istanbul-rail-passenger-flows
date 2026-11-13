"""
Step 3 - Capacity and operational effort per line.

Turns the fleet table into the per-line parameters the optimisation needs:
how many passengers one train carries, and how much effort one extra trip costs.

Effort is deliberately not a money figure. Reliable cost data per line is not
public, so every extra trip counts as one unit of operational effort.

Input  : data/rail_fleet_capacity.csv
Output : results/operational_effort_coefficients.csv
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = ROOT / "data" / "rail_fleet_capacity.csv"
OUTPUT_FILE = ROOT / "results" / "operational_effort_coefficients.csv"

REQUIRED_COLUMNS = [
    "Hat_Adi",
    "Set_Kapasitesi_Yolcu",
    "Toplam_Arac_Sayisi",
    "Ortalama_Hiz_km_h",
    "Set_Uzunlugu_Vagon",
]
NUMERIC_COLUMNS = [
    "standard_capacity_passengers",
    "total_vehicle_count",
    "avg_speed_kmh",
    "standard_wagon_count",
]


def classify_system_type(line: str) -> str:
    """Metro, funicular/cable or Marmaray. Tram lines return 'other' and are left out."""
    if line == "MARMARAY":
        return "marmaray"
    if re.match(r"^M\d+[A-Z]?$", line):
        return "metro"
    if re.match(r"^T?F\d+[A-Z]?$", line) or line in ("TUNEL", "TÜNEL"):
        return "funicular_or_cable"
    return "other"


def main():
    capacity = pd.read_csv(INPUT_FILE)

    missing = [c for c in REQUIRED_COLUMNS if c not in capacity.columns]
    if missing:
        raise ValueError(f"Missing columns in capacity file: {missing}")

    capacity["line"] = capacity["Hat_Adi"].astype(str).str.strip().str.upper()
    capacity["system_type"] = capacity["line"].apply(classify_system_type)
    rail = capacity[capacity["system_type"] != "other"].copy()

    rail = rail.rename(columns={
        "Set_Kapasitesi_Yolcu": "standard_capacity_passengers",
        "Toplam_Arac_Sayisi": "total_vehicle_count",
        "Ortalama_Hiz_km_h": "avg_speed_kmh",
        "Set_Uzunlugu_Vagon": "standard_wagon_count",
    })

    # The source table may hold numbers as text ("1.600", "40 km/h").
    for col in NUMERIC_COLUMNS:
        rail[col] = pd.to_numeric(
            rail[col].astype(str)
            .str.replace(",", ".", regex=False)
            .str.extract(r"([-+]?[0-9]*\.?[0-9]+)", expand=False),
            errors="coerce",
        )

    rail["effort_per_extra_trip"] = 1.00
    rail["effort_unit"] = "one additional standard trip"
    rail["cost_interpretation"] = "normalized operational effort, not monetary cost"

    out = rail[[
        "line",
        "system_type",
        "standard_capacity_passengers",
        "effort_per_extra_trip",
        "effort_unit",
        "cost_interpretation",
        "total_vehicle_count",
        "avg_speed_kmh",
        "standard_wagon_count",
    ]].sort_values(["system_type", "line"]).reset_index(drop=True)

    critical = out[["line", "standard_capacity_passengers", "effort_per_extra_trip"]].isna().sum()
    if critical.sum() > 0:
        raise ValueError(f"Critical missing values found:\n{critical}")

    out.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved {len(out)} lines -> {OUTPUT_FILE.relative_to(ROOT)}")
    print("Lines:", ", ".join(out["line"]))


if __name__ == "__main__":
    main()
