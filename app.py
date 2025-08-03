from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import requests
import os

# Load environment variables or API keys
NASA_API_KEY = os.getenv("NASA_API_KEY", "aGYhKBDmeDfGFM2JkWg2lnCimJn5XgUmwM5UkB3d")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "0ab5dc524a2d5dc7f726017a2b98c687")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "c77748626e024b9b985f07e97826e4db")

app = FastAPI(title="GaiaEyes Backend", version="1.0")

# Allow frontend and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------
# Root Endpoint
# ---------------------
@app.get("/")
async def root():
    return JSONResponse({"message": "GaiaEyes backend is running"})

# ---------------------
# NASA Example Endpoint
# ---------------------
@app.get("/space-weather")
async def get_space_weather():
    try:
        # Example: Fetch NASA APOD (Astronomy Picture of the Day)
        url = f"https://api.nasa.gov/planetary/apod?api_key={NASA_API_KEY}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------
# Weather Example Endpoint
# ---------------------
@app.get("/weather/{city}")
async def get_weather(city: str):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------
# News Example Endpoint
# ---------------------
@app.get("/news")
async def get_news():
    try:
        url = f"https://newsapi.org/v2/top-headlines?category=science&apiKey={NEWS_API_KEY}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
