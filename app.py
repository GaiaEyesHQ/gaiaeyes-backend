import os, json, requests, asyncio
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, Form, Response, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(title="GaiaEyes Backend", version="2.0")

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))
templates = Jinja2Templates(directory="templates")

USERS_FILE = "users.json"
users = {}

# -------------------------
# USER MANAGEMENT
# -------------------------
def load_users():
    global users
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
    else:
        users = {}
    return users

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

users = load_users()

# -------------------------
# CACHED DATA
# -------------------------
cache = {
    "schumann": {},
    "ionosphere": {},
    "space_weather": {}
}

SCHUMANN_CHART = "http://sosrff.tsu.ru/new/shm.jpg"
IONO_BASE = "https://www.sws.bom.gov.au/Images/HFSystems/obs/ionogram/{}.gif"

# -------------------------
# DATA FETCH FUNCTIONS
# -------------------------
def fetch_schumann():
    # Example: mock values; replace with real scraping/parsing
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "frequency": 7.83,
        "amplitude": 32.1,
        "status": "Moderate activity"
    }

def fetch_ionosphere():
    # Example static station
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "station": "Sydney",
        "foF2_MHz": 8.2,
        "status": "Quiet"
    }

def fetch_space_weather():
    try:
        swpc = requests.get("https://services.swpc.noaa.gov/products/summary.json", timeout=10)
        data = swpc.json() if swpc.status_code == 200 else {}
    except:
        data = {}
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "kp_index": data.get("kp_index", "N/A"),
        "solar_wind": data.get("solar_wind_speed", "N/A"),
        "status": "OK" if data else "Offline"
    }

# -------------------------
# BACKGROUND REFRESH
# -------------------------
async def refresh_cache():
    while True:
        cache["schumann"] = fetch_schumann()
        cache["ionosphere"] = fetch_ionosphere()
        cache["space_weather"] = fetch_space_weather()
        await asyncio.sleep(600)  # refresh every 10 min

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(refresh_cache())

# -------------------------
# ENDPOINTS
# -------------------------
@app.get("/news")
def get_news(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return cache["space_weather"]

@app.get("/vip")
def get_vip(api_key: str):
    if api_key not in users or users[api_key] != "vip":
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return {
        "schumann": cache["schumann"],
        "ionosphere": cache["ionosphere"],
        "space_weather": cache["space_weather"]
    }

@app.get("/schumann-resonance")
def get_schumann_resonance(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return cache["schumann"]

@app.get("/schumann-chart")
def schumann_chart(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    r = requests.get(SCHUMANN_CHART)
    return Response(content=r.content, media_type="image/jpeg")

@app.get("/ionosphere")
def get_ionosphere(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return cache["ionosphere"]

@app.get("/ionosphere-chart")
def ionosphere_chart(api_key: str, station: str = Query("sydney")):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    url = IONO_BASE.format(station.lower())
    r = requests.get(url)
    return Response(content=r.content, media_type="image/gif")

# -------------------------
# ADMIN ENDPOINTS
# -------------------------
@app.post("/admin/add-vip")
async def add_vip(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    users[key] = "vip"
    save_users()
    return {"message": f"{key} added as VIP"}

@app.post("/admin/delete-vip")
async def delete_vip(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if key in users:
        del users[key]
        save_users()
        return {"message": f"{key} deleted"}
    raise HTTPException(status_code=404, detail="User not found")
