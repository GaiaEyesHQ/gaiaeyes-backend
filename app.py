import os
import json
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

# ----------------------
# APP INIT
# ----------------------
app = FastAPI(title="GaiaEyes Backend", version="1.0")

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

users = load_users()

templates = Jinja2Templates(directory="templates")

# ----------------------
# MODELS
# ----------------------
class SchumannResponse(BaseModel):
    timestamp: str
    frequency: float
    amplitude: float
    status: str
    elf_level: str

class IonosphereResponse(BaseModel):
    timestamp: str
    station: str
    foF2_MHz: float
    status: str

# ----------------------
# UTILITIES: Mock Scrapers
# ----------------------
def fetch_schumann_data():
    # Mocked numeric data (replace with real scraper later)
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "frequency": 7.83,
        "amplitude": 33.5,
        "status": "Moderate activity",
        "elf_level": "Normal"
    }

def fetch_ionosphere_data():
    # Mocked numeric data (replace with real scraper later)
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "station": "Moscow",
        "foF2_MHz": 8.4,
        "status": "Quiet"
    }

SCHUMANN_CHART_URL = "http://sosrff.tsu.ru/new/shm.jpg"  # Example TSU Schumann chart
IONOSPHERE_CHART_URL = "http://www.sws.bom.gov.au/Images/HFSystems/obs/ionogram.gif"  # Example ionogram

# ----------------------
# PUBLIC ENDPOINTS
# ----------------------
@app.get("/news")
def get_news(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"data": "Space weather data placeholder"}

@app.get("/vip")
def get_vip(api_key: str):
    if api_key not in users or users[api_key] != "vip":
        return {"error": "Invalid or missing API key"}
    return {"vip_content": "Exclusive solar analysis for VIPs."}

@app.get("/schumann-resonance", response_model=SchumannResponse)
def get_schumann_resonance(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return fetch_schumann_data()

@app.get("/schumann-chart")
def schumann_chart(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    r = requests.get(SCHUMANN_CHART_URL)
    return Response(content=r.content, media_type="image/jpeg")

@app.get("/ionosphere", response_model=IonosphereResponse)
def get_ionosphere(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return fetch_ionosphere_data()

@app.get("/ionosphere-chart")
def ionosphere_chart(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    r = requests.get(IONOSPHERE_CHART_URL)
    return Response(content=r.content, media_type="image/gif")

# ----------------------
# ADMIN ENDPOINTS
# ----------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if request.session.get("logged_in"):
        return templates.TemplateResponse("dashboard.html", {"request": request, "users": users})
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/admin/login")
async def admin_login(request: Request, password: str = Form(...)):
    if password == os.getenv("ADMIN_PASSWORD", "admin123"):
        request.session["logged_in"] = True
        return RedirectResponse(url="/admin", status_code=303)
    return HTMLResponse("<h3>Wrong password. <a href='/admin'>Try again</a></h3>")

@app.post("/admin/add-vip")
async def add_vip(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    users[key] = "vip"
    save_users(users)
    return {"message": f"{key} added as VIP"}

@app.post("/admin/delete-vip")
async def delete_vip(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if key in users:
        del users[key]
        save_users(users)
        return {"message": f"{key} deleted"}
    raise HTTPException(status_code=404, detail="User not found")
