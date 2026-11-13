"""
Step 4 - Baseline load ratios.

Compares how many passengers enter each line per hour with how many the
scheduled trains can carry:

    load ratio = average hourly demand / (scheduled trips x train capacity)

A ratio above 1 means the line is over capacity in that hour on an average day.

M1A and M1B stay separate lines. They only share the M1 row of the capacity
table, because both branches use the same train type.

Inputs : data/rayli_sistem_temiz.csv
         data/hourly_metro_train_numbers.csv
         results/operational_effort_coefficients.csv
Output : results/baseline_load_ratios.csv
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEMAND_FILE = ROOT / "data" / "rayli_sistem_temiz.csv"
TRAIN_FILE = ROOT / "data" / "hourly_metro_train_numbers.csv"
EFFORT_FILE = ROOT / "results" / "operational_effort_coefficients.csv"
OUTPUT_FILE = ROOT / "results" / "baseline_load_ratios.csv"

OUTPUT_COLUMNS = [
    "hat_adi",
    "capacity_line_key",
    "saat",
    "avg_hourly_demand",
    "median_hourly_demand",
    "max_hourly_demand",
    "observed_day_count",
    "sefer_sayisi",
    "standard_capacity_passengers",
    "baseline_capacity_passengers",
    "baseline_load_ratio",
    "effort_per_extra_trip",
    "baseline_operational_effort",
]


def normalize_line_column(df, col):
    df[col] = df[col].astype(str).str.strip().str.upper()
    return df


def capacity_key(line):
    return "M1" if line in ("M1A", "M1B") else line


def main():
    demand = normalize_line_column(pd.read_csv(DEMAND_FILE), "hat_adi")
    trains = normalize_line_column(pd.read_csv(TRAIN_FILE), "hat_adi")
    effort = normalize_line_column(pd.read_csv(EFFORT_FILE), "line")

    demand["saat"] = pd.to_numeric(demand["saat"], errors="coerce")
    demand["toplam_yolcu"] = pd.to_numeric(demand["toplam_yolcu"], errors="coerce")
    trains["saat"] = pd.to_numeric(trains["saat"], errors="coerce")
    trains["sefer_sayisi"] = pd.to_numeric(trains["sefer_sayisi"], errors="coerce")

    # Sum all stations of a line for each date and hour, then average over dates.
    daily_line_hour = (
        demand.dropna(subset=["hat_adi", "tarih", "saat", "toplam_yolcu"])
        .groupby(["hat_adi", "tarih", "saat"], as_index=False)["toplam_yolcu"]
        .sum()
        .rename(columns={"toplam_yolcu": "daily_hourly_demand"})
    )
    avg_demand = daily_line_hour.groupby(["hat_adi", "saat"], as_index=False).agg(
        avg_hourly_demand=("daily_hourly_demand", "mean"),
        median_hourly_demand=("daily_hourly_demand", "median"),
        max_hourly_demand=("daily_hourly_demand", "max"),
        observed_day_count=("daily_hourly_demand", "count"),
    )

    trains_clean = (
        trains.dropna(subset=["hat_adi", "saat", "sefer_sayisi"])
        .groupby(["hat_adi", "saat"], as_index=False)["sefer_sayisi"]
        .sum()
    )
    trains_clean["capacity_line_key"] = trains_clean["hat_adi"].map(capacity_key)

    effort_small = effort[["line", "standard_capacity_passengers", "effort_per_extra_trip"]].rename(
        columns={"line": "capacity_line_key"}
    )
    baseline = trains_clean.merge(effort_small, on="capacity_line_key", how="left").merge(
        avg_demand, on=["hat_adi", "saat"], how="left"
    )

    baseline["baseline_capacity_passengers"] = baseline["sefer_sayisi"] * baseline["standard_capacity_passengers"]
    baseline["baseline_operational_effort"] = baseline["sefer_sayisi"] * baseline["effort_per_extra_trip"]
    baseline["baseline_load_ratio"] = baseline["avg_hourly_demand"] / baseline["baseline_capacity_passengers"]

    # Keep only line-hours where demand exists and trains actually run.
    valid = baseline[
        baseline["avg_hourly_demand"].notna()
        & baseline["standard_capacity_passengers"].notna()
        & (baseline["baseline_capacity_passengers"] > 0)
    ][OUTPUT_COLUMNS]
    valid.to_csv(OUTPUT_FILE, index=False)

    no_demand = sorted(baseline.loc[baseline["avg_hourly_demand"].isna(), "hat_adi"].unique())
    over = int((valid["baseline_load_ratio"] > 1).sum())
    print(f"Saved {len(valid)} line-hours -> {OUTPUT_FILE.relative_to(ROOT)}")
    print("Lines covered:", ", ".join(sorted(valid["hat_adi"].unique())))
    print("Lines with a timetable but no matching demand (left out):", ", ".join(no_demand) or "none")
    print(f"Line-hours over capacity: {over} of {len(valid)}")


if __name__ == "__main__":
    main()
