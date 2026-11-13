"""
Step 5 - Match-day demand.

Measures how station entries change around football matches of Beşiktaş,
Fenerbahçe and Galatasaray, from 12 hours before to 12 hours after kick-off.

For each match and hour offset, the passengers observed at a station are
compared with that station's normal level for the same weekday and hour,
computed from days without any match.

Inputs : data/rayli_sistem_temiz.csv
         data/big3_match_schedule.csv
         data/rail_fleet_capacity.csv
Outputs: results/match_station_offset_features.csv   change per team, line, station and hour offset
         results/match_day_extra_demand.csv           extra passengers per team, line and hour offset
         results/match_day_extra_trains.csv           rule-of-thumb extra trains per team and line
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
METRO_FILE = ROOT / "data" / "rayli_sistem_temiz.csv"
MATCHES_FILE = ROOT / "data" / "big3_match_schedule.csv"
FLEET_FILE = ROOT / "data" / "rail_fleet_capacity.csv"
STATION_FILE = ROOT / "results" / "match_station_offset_features.csv"
LINE_HOUR_FILE = ROOT / "results" / "match_day_extra_demand.csv"
TRAINS_FILE = ROOT / "results" / "match_day_extra_trains.csv"

OFFSET_RANGE = (-12, 12)
ROUND_UP_FROM = 0.30  # a leftover of 30% of a train or more justifies one more train


def load_metro(path):
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"hat_adi": "string", "durak_adi": "string"})
    df = df.rename(columns={
        "hat_adi": "line", "durak_adi": "station", "tarih": "date",
        "saat": "hour", "toplam_yolcu": "passengers",
    })
    # Two lines have a station literally named "NAN"; drop those and real gaps.
    bad = (
        df["station"].isna() | df["line"].isna()
        | df["station"].str.upper().eq("NAN") | df["line"].str.upper().eq("NAN")
    )
    df = df[~bad].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["hour"] = pd.to_numeric(df["hour"], errors="coerce").astype("Int8")
    df["passengers"] = pd.to_numeric(df["passengers"], errors="coerce").fillna(0).astype("int32")
    df = df.dropna(subset=["date", "hour"])
    df["datetime"] = df["date"] + pd.to_timedelta(df["hour"].astype("int8"), unit="h")
    df["line"] = df["line"].astype("category")
    df["station"] = df["station"].astype("category")
    return df[["line", "station", "datetime", "passengers"]].reset_index(drop=True)


def load_matches(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.rename(columns={"Team": "team", "Date": "date", "Time": "time"})
    df["team"] = df["team"].str.strip().str.lower()
    df["match_datetime"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), errors="coerce")
    df = df.dropna(subset=["match_datetime"])
    df["match_hour_bucket"] = df["match_datetime"].dt.floor("h")
    return df[["team", "match_datetime", "match_hour_bucket"]].reset_index(drop=True)


def build_baseline(metro, match_dates):
    """Normal passenger level per station, weekday and hour, from days without a match."""
    base = metro[~metro["datetime"].dt.normalize().isin(match_dates)]
    base = base.assign(
        weekday=base["datetime"].dt.weekday.astype("int8"),
        hour=base["datetime"].dt.hour.astype("int8"),
    )
    return (
        base.groupby(["line", "station", "weekday", "hour"], observed=True)["passengers"]
        .agg(baseline_mean="mean")
        .reset_index()
    )


def station_offset_features(metro, matches):
    baseline = build_baseline(metro, matches["match_datetime"].dt.normalize().unique())

    lo, hi = OFFSET_RANGE
    grid = matches.merge(pd.DataFrame({"hour_offset": np.arange(lo, hi + 1, dtype="int8")}), how="cross")
    grid["query_datetime"] = grid["match_hour_bucket"] + pd.to_timedelta(grid["hour_offset"].astype("int16"), unit="h")

    merged = grid.merge(metro, left_on="query_datetime", right_on="datetime", how="inner").drop(columns=["datetime"])
    merged = merged.assign(
        weekday=merged["query_datetime"].dt.weekday.astype("int8"),
        hour=merged["query_datetime"].dt.hour.astype("int8"),
    ).merge(baseline, on=["line", "station", "weekday", "hour"], how="left")
    merged["change"] = merged["passengers"] - merged["baseline_mean"]

    feat = (
        merged.groupby(["team", "line", "station", "hour_offset"], observed=True)
        .agg(mean_change=("change", "mean"))
        .reset_index()
    )
    feat["mean_change"] = feat["mean_change"].round(2)
    return feat.sort_values(["team", "line", "station", "hour_offset"]).reset_index(drop=True)


def round_trains(value):
    """Round up when the leftover is at least ROUND_UP_FROM of a train, otherwise down."""
    return math.ceil(value) if value % 1 >= ROUND_UP_FROM else math.floor(value)


def main():
    metro = load_metro(METRO_FILE)
    matches = load_matches(MATCHES_FILE)

    feat = station_offset_features(metro, matches)
    feat.to_csv(STATION_FILE, index=False, encoding="utf-8-sig")
    print(f"Saved {len(feat):,} rows -> {STATION_FILE.relative_to(ROOT)}")

    # Only increases matter for planning extra service, so negative changes count as zero.
    feat["extra"] = feat["mean_change"].clip(lower=0)

    line_hour = (
        feat.groupby(["team", "line", "hour_offset"], observed=True)["extra"].sum()
        .round(2).reset_index().rename(columns={"extra": "extra_demand"})
    )
    line_hour.to_csv(LINE_HOUR_FILE, index=False, encoding="utf-8-sig")
    print(f"Saved {len(line_hour):,} rows -> {LINE_HOUR_FILE.relative_to(ROOT)}")

    fleet = pd.read_csv(FLEET_FILE)[["Hat_Adi", "Set_Kapasitesi_Yolcu"]]
    trains = (
        feat.groupby(["team", "line"], observed=True)["extra"].sum().reset_index()
        .rename(columns={"extra": "extra_demand"})
        .merge(fleet, left_on="line", right_on="Hat_Adi", how="inner")
    )
    trains["extra_trains"] = (trains["extra_demand"] / trains["Set_Kapasitesi_Yolcu"]).apply(round_trains)
    trains["extra_demand"] = trains["extra_demand"].round(2)
    trains = trains[["team", "line", "extra_demand", "extra_trains"]]
    trains.to_csv(TRAINS_FILE, index=False, encoding="utf-8-sig")
    print(f"Saved {len(trains)} rows -> {TRAINS_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
