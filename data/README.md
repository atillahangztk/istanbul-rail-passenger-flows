# Data

| File | Contents | Source |
| --- | --- | --- |
| `rail_fleet_capacity.csv` | Train type, capacity per train, fleet size and average speed for each line | Collected by the team from operator pages; each row links its source |
| `hourly_metro_train_numbers.csv` | Scheduled trips per hour for each metro line and Marmaray | Collected by the team from published timetables |
| `big3_match_schedule.csv` | Dates and kick-off times of Beşiktaş, Fenerbahçe and Galatasaray matches, November 2022 to October 2024 | Web-scraped, see `notebooks/match_schedule_scraping.ipynb` |
| `rayli_sistem_temiz.csv` | Cleaned hourly station entries, 3.45 million rows (**not in the repository**) | Built from Istanbul open data, see below |

## Getting `rayli_sistem_temiz.csv`

The file is about 110 MB, so it is not stored here. It has one row per line, station, date and hour:

```
hat_adi,durak_adi,tarih,saat,toplam_yolcu
F1,KABATAS,2022-11-01,05,2
```

To rebuild it, download the monthly "hourly public transport" files from the
[Istanbul Metropolitan Municipality open data portal](https://data.ibb.gov.tr/) and follow
`notebooks/data_cleaning_aggregation.ipynb`. The notebook keeps the rail rows, merges the different
spellings of each station name, and sums the passengers per line, station, date and hour.

Place the result in this folder and run `python run_pipeline.py` from the repository root.
