"""Runs every step of the project in order. Needs data/rayli_sistem_temiz.csv (see data/README.md)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    "01_station_weights.py",
    "02_estimate_od_matrix.py",
    "03_operational_effort.py",
    "04_baseline_load_ratios.py",
    "05_match_day_demand.py",
    "06_optimize_trips.py",
    "07_make_figures.py",
]


def main():
    if not (ROOT / "data" / "rayli_sistem_temiz.csv").exists():
        sys.exit("data/rayli_sistem_temiz.csv is missing. See data/README.md for how to build it.")
    (ROOT / "results" / "figures").mkdir(parents=True, exist_ok=True)
    for step in STEPS:
        print(f"\n===== {step} =====", flush=True)
        subprocess.run([sys.executable, str(ROOT / "src" / step)], check=True,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    print("\nAll steps finished. Results are in results/.")


if __name__ == "__main__":
    main()
