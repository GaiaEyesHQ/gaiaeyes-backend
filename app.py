from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
import os
import requests
import time

app = FastAPI(title="GaiaEyes Backend", description="Space Weather & News API", version="1.1")

# =========================
# CONFIG
# =========================
API_KEYS = os.getenv("GAIAEYES_API_KEYS", "testkey123").split(",")  

# Example: {"user_api_key": {"role": "free" or "vip", "requests": 0, "last_reset": timestamp}}
USER_DB = {
    "freeuser123": {"role": "free", "requests": 0, "last_reset": time.time()},
    "vipuser456": {"role": "vip", "requests": 0, "last_reset": time.time()},
}

FREE_USER_DAILY_LIMIT = 50  # e.g., 50 requests/day

NASA_KEY = os.getenv("NASA_API_KEY", "aGYhKBDmeDfGFM2JkWg2lnCimJn5XgUmwM5UkB3d")
WEATHER_KEY = os.getenv("OPENWEATHER_KEY", "0ab5dc524a2d5dc7f726017a2b98c687")
NEWS_KEY = os.getenv("NEWS_API_KEY", "c77748626e024b9b985f07e97826e4db")

# =========================
# Auth & Rate-Limit Logic
# =========================
def verify_api_key(request: Request):
    client_key = request.headers.get("x-api-key")
    if not client_key or client_key not in USER_DB:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    user = USER_DB[client_key]
    now = time.time()

    # Reset daily count every 24h for free users
    if now - user["last_reset"] > 86400:
        user["requests"] = 0
        user["last_reset"] = now

    if user["role"] == "free":
        if user["requests"] >= FREE_USER_DAILY_LIMIT:
            raise HTTPException(status_code=429, detail="Free user daily limit reached")
        user["requests"] += 1

    return user

# =========================
# Public Endpoint
# =========================
@app.get("/")
async def root():
    return {"message": "GaiaEyes Backend is running!"}

# =========================
# Protected Endpoints
# =========================

@app.get("/news")
async def get_news(user=Depends(verify_api_key)):
    url = f"https://newsapi.org/v2/top-headlines?category=science&apiKey={NEWS_KEY}"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch news")
    return resp.json()

@app.get("/space-weather")
async def get_space_weather(user=Depends(verify_api_key)):
    url = f"https://api.nasa.gov/DONKI/notifications?api_key={NASA_KEY}"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch space weather")
    return resp.json()

@app.get("/weather/{location}")
async def get_weather(location: str, user=Depends(verify_api_key)):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={location}&appid={WEATHER_KEY}&units=metric"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch weather")
    return resp.json()

# =========================
# Admin: Add/Update Users (Optional)
# =========================
@app.post("/admin/add-user")
async def add_user(request: Request):
    data = await request.json()
    key = data.get("key")
    role = data.get("role", "free")
    if not key:
        raise HTTPException(status_code=400, detail="Key is required")
    USER_DB[key] = {"role": role, "requests": 0, "last_reset": time.time()}
    return {"message": f"User {key} added with role {role}"}

# =========================
# Custom Error Handler
# =========================
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
