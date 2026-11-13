# Istanbul Rail System: Hourly Passenger Flow Estimation

Estimates how many passengers travel between each pair of stations on Istanbul's rail network, hour by hour, from data that only records how many people enter each station. The result is the input for deciding where extra train trips are most needed.

Term project for YZV202E (Optimization for Data Science), Istanbul Technical University, Spring 2026.

## The problem

Istanbul's open ridership data counts entries at each station per hour. It does not say where those passengers get off. To plan train frequency against crowding, you need station-to-station flows, so they have to be estimated.

## What the project does

1. **Cleans the ridership data.** The raw file has 4.2 million rows in which the same physical station appears under several spellings. Station names are normalised with a manual map plus rules, reducing 348 station names to 266 and 4,222,304 rows to 3,455,244 while keeping the passenger total unchanged.
2. **Computes hourly station weights.** For every line and hour, each station's share of the line's passengers.
3. **Estimates station-to-station flows.** Morning entries at a station mirror evening exits and vice versa, so each station's daily profile indicates how attractive it is as a destination at a given hour. Flows are distributed in proportion to those weights, with every origin's flows adding up to its real entry count. Lines with one or two stations and hours with no passengers are handled as explicit special cases.
4. **Builds capacity and effort tables.** Train capacity per line and scheduled trips per hour give the baseline hourly capacity, and each extra trip is assigned a normalised operating effort. These are the inputs for a frequency optimisation model.
5. **Collects football match times.** Match schedules of the three big Istanbul clubs were scraped to study match-day demand peaks.

## Outputs

| File | Contents |
| --- | --- |
| `saatlik_durak_agirliklari.csv` | Hourly weight of each station within its line |
| `estimated_hourly_od_matrix.csv` | Estimated hourly flow for every station pair on each line (about 170,000 rows) |
| `operational_effort_coefficients.csv` | Capacity and effort per extra trip for each line |
| `baseline_hourly_capacity.csv` | Scheduled hourly capacity per line |

The network covered is 23 lines and 266 stations.

## Code

| File | Purpose |
| --- | --- |
| `data_cleaning_aggregation.ipynb` | Station name normalisation and aggregation (notes in Turkish) |
| `Progress_Report.ipynb` | Fleet constraints and the station weight calculation |
| `estimated_od_matrix_solver.py` | The station-to-station flow estimator |
| `operational_effort_rail_updated.ipynb`, `create_operational_effort_coefficients.py` | Effort coefficients per line |
| `create_baseline_hourly_capacity.py` | Baseline hourly capacity |
| `converting_webscrab_into_csv.ipynb` | Turns the scraped match schedule into a table |

## Running it

Python 3 with `pandas`, `numpy`, `duckdb` and `matplotlib`.

The cleaned ridership file (`rayli_sistem_temiz.csv`, 3.45 million rows) is too large for this repository. It is built from the hourly public transport data published on the [Istanbul Metropolitan Municipality open data portal](https://data.ibb.gov.tr/) by following `data_cleaning_aggregation.ipynb`. With that file in place:

```bash
python estimated_od_matrix_solver.py
python create_operational_effort_coefficients.py
python create_baseline_hourly_capacity.py
```

## Status

The data pipeline and the flow estimation are complete. The train frequency optimisation that uses these tables is not included yet.

## Team

- **Atillahan Gözütok**: proposed the project, data collection, flow estimation
- Emir Selim İslam
- Erdem Hasbek
- Huzeyfe Dut
