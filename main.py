"""
================================================================================
OPEN-METEO HISTORICAL WEATHER API REFERENCE DIRECTORY
================================================================================
The following data fields can be passed into the "daily" or "hourly" arrays
within Open-Meteo's Historical Weather API endpoint.
 GENERAL ATMOSPHERIC & COMFORT METRICS:
    - temperature_2m_max / _min / _mean : Air temperature (2m above ground)
    - apparent_temperature_max / _min / _mean : "Feels like" temp (humidity + wind chill)
    - dew_point_2m_max / _min / _mean : Dew point saturation threshold
    - relative_humidity_2m_mean : Average relative humidity percentage
    - pressure_msl_mean : Mean atmospheric pressure reduced to sea level (hPa)
    - weather_code : World Meteorological Organization (WMO) structural index code
 PRECIPITATION & HYDROLOGY:
    - precipitation_sum : Total daily water equivalent sum (rain + snow + showers)
    - rain_sum / snowfall_sum : Split individual liquid rain vs loose snow totals
    - snow_depth : Daily accumulated depth of snowpack on the ground
 RADIATION & WIND ENERGY FIELDS:
    - shortwave_radiation_sum : Total global solar energy influx (MJ/m²)
    - sunshine_duration : Total seconds per day with direct sunlight irradiance
    - wind_speed_10m_max / wind_gusts_10m_max : Surface level wind velocity limits
    - wind_direction_10m_dominant : Primary meteorological wind direction grid (degrees)
 UNDERGROUND AGRISCIENCE DYNAMICS (Root Zone Profiles):
    - soil_temperature_0_to_7cm   / _7_to_28cm   / _28_to_100cm   / _100_to_255cm
    - soil_moisture_0_to_7cm      / _7_to_28cm   / _28_to_100cm   / _100_to_255cm
================================================================================
"""

from datetime import datetime
import time

import pandas as pd  # required: builds per-city tables and writes the output Parquet file
import requests  # required: HTTP client for the API (stdlib urllib works as a dependency-free fallback)
# pandas.to_parquet also needs a Parquet engine installed: fastparquet (used here; pyarrow has no
# prebuilt wheel yet for Python 3.14 on win_arm64) or pyarrow if available on your platform

# ===== CONFIG =====
# Cities to pull historical daily weather for (name + coordinates)
CITIES = [
    {"name": "Virginia Beach, VA", "latitude": 36.8529, "longitude": -75.9780},
    {"name": "Arlington, MA", "latitude": 42.4154, "longitude": -71.1564},
    {"name": "Boston, MA", "latitude": 42.3601, "longitude": -71.0589},
    {"name": "Tampa, FL", "latitude": 27.9506, "longitude": -82.4572},
    {"name": "Richmond, VA", "latitude": 37.5407, "longitude": -77.4360},
    {"name": "Washington, DC", "latitude": 38.9072, "longitude": -77.0369},
    {"name": "New York City, NY", "latitude": 40.7128, "longitude": -74.0060},
]

START_DATE = "2016-01-01"
END_DATE = datetime.today().strftime("%Y-%m-%d")  # pulls through today by default

# Daily fields requested from the API for each city (see reference directory above)
DAILY_FIELDS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "snowfall_sum",
    "relative_humidity_2m_mean",
    "dew_point_2m_mean",
    "pressure_msl_mean",
    "weather_code",
    "sunshine_duration",
]

TEMPERATURE_UNIT = "fahrenheit"
PRECIPITATION_UNIT = "inch"
TIMEZONE = "America/New_York"

API_URL = "https://archive-api.open-meteo.com/v1/archive"
REQUEST_TIMEOUT_SECONDS = 30
SLEEP_BETWEEN_REQUESTS_SECONDS = 1  # API safety pacing between per-city requests
MAX_RETRIES = 3  # retries on HTTP 429 (rate limit) before giving up on a city
RATE_LIMIT_BACKOFF_SECONDS = 60  # Open-Meteo's free tier limit resets on a per-minute window

OUTPUT_FILENAME = "described_city_weather_history.parquet"

# ===== REFERENCE DATA: WMO WEATHER CODE MAP =====
# Maps Open-Meteo's WMO weather_code values to human-readable descriptions
WMO_CODE_MAP = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing Rime Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    56: "Light Freezing Drizzle",
    57: "Dense Freezing Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    66: "Light Freezing Rain",
    67: "Heavy Freezing Rain",
    71: "Slight Snowfall",
    73: "Moderate Snowfall",
    75: "Heavy Snowfall",
    77: "Snow Grains",
    80: "Slight Rain Showers",
    81: "Moderate Rain Showers",
    82: "Violent Rain Showers",
    85: "Slight Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm with Slight Hail",
    99: "Thunderstorm with Heavy Hail",
}


def fetch_city_weather(city):
    """Fetch daily historical weather for one city from the Open-Meteo archive API.

    Inputs:
        city: dict with 'name', 'latitude', 'longitude' keys (see CITIES config)
    Outputs:
        pandas.DataFrame with one row per date and columns: Date, City,
        Max_Temp_F, Min_Temp_F, Precipitation_Inches, Snowfall_Inches,
        Avg_Humidity_Percent, Avg_Dew_Point_F, Sea_Level_Pressure_hPa,
        WMO_Weather_Code, Weather_Description, Sunshine_Hours
    Raises:
        requests.RequestException on a network/HTTP failure, KeyError if the
        response is missing expected fields (e.g. an unexpected error payload)
    """
    params = {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "start_date": START_DATE,
        "end_date": END_DATE,
        "daily": DAILY_FIELDS,
        "temperature_unit": TEMPERATURE_UNIT,
        "precipitation_unit": PRECIPITATION_UNIT,
        "timezone": TIMEZONE,
    }

    # Retry on HTTP 429 (rate limit) — Open-Meteo's free tier caps requests per minute
    for attempt in range(MAX_RETRIES + 1):
        response = requests.get(API_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code == 429 and attempt < MAX_RETRIES:
            print(
                f"    Rate limited — waiting {RATE_LIMIT_BACKOFF_SECONDS}s "
                f"(retry {attempt + 1}/{MAX_RETRIES})..."
            )
            time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
            continue
        response.raise_for_status()
        break

    daily_data = response.json()["daily"]

    # Convert sunshine duration from seconds into total hours
    sunshine_hours = [
        round(sec / 3600, 2) if sec is not None else 0
        for sec in daily_data["sunshine_duration"]
    ]

    # Convert WMO codes into human-readable descriptions
    weather_descriptions = [
        WMO_CODE_MAP.get(code, f"Unknown ({code})")
        for code in daily_data["weather_code"]
    ]

    return pd.DataFrame(
        {
            "Date": daily_data["time"],
            "City": city["name"],
            "Max_Temp_F": daily_data["temperature_2m_max"],
            "Min_Temp_F": daily_data["temperature_2m_min"],
            "Precipitation_Inches": daily_data["precipitation_sum"],
            "Snowfall_Inches": daily_data["snowfall_sum"],
            "Avg_Humidity_Percent": daily_data["relative_humidity_2m_mean"],
            "Avg_Dew_Point_F": daily_data["dew_point_2m_mean"],
            "Sea_Level_Pressure_hPa": daily_data["pressure_msl_mean"],
            "WMO_Weather_Code": daily_data["weather_code"],
            "Weather_Description": weather_descriptions,
            "Sunshine_Hours": sunshine_hours,
        }
    )


def main():
    """Download historical daily weather for all configured cities and save one combined CSV."""
    script_start = time.perf_counter()
    print(f"Executing historical download ({START_DATE} to {END_DATE})...")

    # ===== STEP 1/2: DOWNLOAD HISTORICAL WEATHER DATA =====
    step1_start = time.perf_counter()
    print("[Step 1/2] Download historical weather data — started")

    all_city_dfs = []
    for city in CITIES:
        print(f"  Requesting expanded profile for {city['name']}...")
        try:
            all_city_dfs.append(fetch_city_weather(city))
        except Exception as e:
            print(f"  Error compiling {city['name']}: {type(e).__name__}: {e}")
        time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    step1_elapsed = time.perf_counter() - step1_start
    print(f"[Step 1/2] Download historical weather data — completed in {step1_elapsed:.1f}s")

    # ===== STEP 2/2: SAVE CONSOLIDATED DATASET =====
    step2_start = time.perf_counter()
    print("[Step 2/2] Save consolidated dataset — started")

    if all_city_dfs:
        final_dataset = pd.concat(all_city_dfs, ignore_index=True)
        final_dataset.to_parquet(OUTPUT_FILENAME, index=False)
        print(f"Dataset saved to '{OUTPUT_FILENAME}'.")
        print(
            final_dataset[
                ["Date", "City", "WMO_Weather_Code", "Weather_Description"]
            ].head(5)
        )
    else:
        print("Download execution yielded 0 results.")

    step2_elapsed = time.perf_counter() - step2_start
    print(f"[Step 2/2] Save consolidated dataset — completed in {step2_elapsed:.1f}s")

    total_elapsed = time.perf_counter() - script_start
    print(f"\nTotal script runtime: {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
