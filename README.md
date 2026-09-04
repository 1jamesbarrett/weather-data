# Weather Data

Downloads historical daily weather data for a set of U.S. cities from the
[Open-Meteo Historical Weather API](https://open-meteo.com) and saves it as a
single consolidated Parquet file.

## What it pulls

- **Cities**: Virginia Beach VA, Arlington MA, Boston MA, Tampa FL,
  Richmond VA, Washington DC, New York City NY
- **Date range**: 2016-01-01 through today
- **Daily fields**: max/min temperature (°F), precipitation (in), snowfall
  (in), average humidity (%), average dew point (°F), sea-level pressure
  (hPa), WMO weather code with a human-readable description, and sunshine
  duration (hours)

All of the above are editable in the `CONFIG` block at the top of `main.py`.

## Requirements

- Python 3.x
- `pandas`
- `requests`
- A Parquet engine: `fastparquet` or `pyarrow`
  (`pyarrow` currently has no prebuilt wheel for Windows on ARM64 —
  `fastparquet` is the tested fallback for that platform)

## Setup

```
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/Mac
pip install pandas requests fastparquet
```

## Usage

```
python main.py
```

Progress and per-step timing print to the console. On completion, a combined
dataset is written to `described_city_weather_history.parquet` in the project
directory (one row per city per date). This output file is not committed to
the repo — it's fully reproducible by re-running the script.

## Notes

- No API key is required for Open-Meteo's free tier.
- Requests are paced with a 1s delay between cities and automatically retry
  (up to 3 times, with a 60s backoff) on HTTP 429 rate-limit responses.
