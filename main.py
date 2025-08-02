from fastapi import FastAPI
import requests
import os

app = FastAPI()

NASA_API_KEY = os.getenv("NASA_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")


@app.get("/")
def root():
    return {"status": "Gaia Eyes API running"}


@app.get("/space-weather")
def space_weather():
    """
    Fetches current space weather data from NOAA SWPC and NASA APIs.
    """
    try:
        # NOAA Space Weather Alerts (SWPC)
        noaa_url = "https://services.swpc.noaa.gov/products/alerts.json"
        noaa_data = requests.get(noaa_url, timeout=10).json()

        # NASA APOD (Astronomy Picture of the Day) as an example
        nasa_url = f"https://api.nasa.gov/planetary/apod?api_key={NASA_API_KEY}"
        nasa_data = requests.get(nasa_url, timeout=10).json()

        return {
            "source": "Gaia Eyes Live",
            "noaa_alerts": noaa_data[:5],  # first 5 alerts
            "nasa_daily_image": nasa_data
        }

    except Exception as e:
        return {"error": str(e)}
