"""
Step 1 - Hourly station weights.

For every line and hour of the day, computes each station's share of the
line's passengers. A weight of 0.25 means that a quarter of the people who
enter that line during that hour enter at this station.

Input  : data/rayli_sistem_temiz.csv
Output : results/hourly_station_weights.csv
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = ROOT / "data" / "rayli_sistem_temiz.csv"
OUTPUT_FILE = ROOT / "results" / "hourly_station_weights.csv"


def main():
    df = pd.read_csv(INPUT_FILE, dtype={"hat_adi": "category", "durak_adi": "category"})

    # Total passengers per line, station and hour of day over the whole period.
    # observed=True stops pandas from creating line/station pairs that do not exist.
    profile = (
        df.groupby(["hat_adi", "durak_adi", "saat"], observed=True)["toplam_yolcu"]
        .sum()
        .reset_index()
    )
    profile = profile[profile["toplam_yolcu"] > 0]

    line_hour_total = profile.groupby(["hat_adi", "saat"], observed=True)["toplam_yolcu"].transform("sum")
    profile["weight"] = (profile["toplam_yolcu"] / line_hour_total).round(4)

    profile[["hat_adi", "durak_adi", "saat", "weight"]].to_csv(OUTPUT_FILE, index=False)
    print(f"Saved {len(profile):,} rows -> {OUTPUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
