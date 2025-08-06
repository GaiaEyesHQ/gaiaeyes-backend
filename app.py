import os
import json
import re
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from bs4 import BeautifulSoup
import io

app = FastAPI()
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

# --- Cache for live data ---
cache = {
    "schumann": None,
    "ionosphere": None,
    "space_weather": None,
    "last_update": None
}

def fetch_schumann():
    try:
        img_url = "http://sosrff.tsu.ru/new/shm.jpg"
        html_url = "http://sosrff.tsu.ru/?page_id=7"

        html_req = requests.get(html_url, timeout=10)
        soup = BeautifulSoup(html_req.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        freq_match = re.search(r"(\d+\.\d+)\s*Hz", text)
        amp_match = re.search(r"(\d+\.\d+)\s*dB", text)

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "frequency_Hz": float(freq_match.group(1)) if freq_match else 7.83,
            "amplitude_dB": float(amp_match.group(1)) if amp_match else None,
            "image_url": img_url,
            "status": "OK"
        }
    except:
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "frequency_Hz": None,
            "amplitude_dB": None,
            "image_url": None,
            "status": "Offline"
        }

def fetch_ionosphere():
    try:
        html_url = "https://www.sws.bom.gov.au/HF_Systems/1/1"
        html_req = requests.get(html_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(html_req.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        fof2_match = re.search(r"foF2\s*=?\s*(\d+\.\d+)", text)

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "station": "Sydney",
            "foF2_MHz": float(fof2_match.group(1)) if fof2_match else None,
            "image_url": "https://www.sws.bom.gov.au/Images/HF/WorldIono/sydney.gif",
            "status": "OK"
        }
    except:
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "station": "Sydney",
            "foF2_MHz": None,
            "image_url": None,
            "status": "Offline"
        }

def fetch_space_weather():
    try:
        # Kp Index
        kp_data = requests.get(
            "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json", timeout=10
        ).json()
        kp_index = kp_data[-1]["kp_index"] if kp_data else None

        # Solar wind
        sw_data = requests.get(
            "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json", timeout=10
        ).json()
        sw_speed = sw_data[-1][1] if len(sw_data) > 1 else None

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "kp_index": kp_index,
            "solar_wind_speed_kms": sw_speed,
            "status": "OK"
        }
    except:
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "kp_index": None,
            "solar_wind_speed_kms": None,
            "status": "Offline"
        }

def update_cache():
    cache["schumann"] = fetch_schumann()
    cache["ionosphere"] = fetch_ionosphere()
    cache["space_weather"] = fetch_space_weather()
    cache["last_update"] = datetime.utcnow()

def get_cached_data():
    if not cache["last_update"] or (datetime.utcnow() - cache["last_update"]) > timedelta(minutes=10):
        update_cache()
    return cache

# --- Public Endpoints ---

@app.get("/news")
def get_news(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return get_cached_data()["space_weather"]

@app.get("/schumann-resonance")
def get_schumann(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return get_cached_data()["schumann"]

@app.get("/ionosphere")
def get_ionosphere(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return get_cached_data()["ionosphere"]

@app.get("/ionosphere-chart")
def ionosphere_chart(api_key: str, station: str = "sydney"):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    url = f"https://www.sws.bom.gov.au/Images/HF/WorldIono/{station}.gif"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.sws.bom.gov.au/"
    }
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch ionosphere chart")
    return StreamingResponse(io.BytesIO(r.content), media_type="image/gif")

# --- VIP Combined Endpoint ---
@app.get("/vip")
def vip_data(api_key: str):
    if api_key not in users or users[api_key] != "vip":
        return {"error": "Invalid or missing API key"}
    data = get_cached_data()
    return {
        "schumann": data["schumann"],
        "ionosphere": data["ionosphere"],
        "space_weather": data["space_weather"]
    }

# --- Admin Endpoints ---
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
async def add_vip_user(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    users[key] = "vip"
    save_users(users)
    return {"message": f"VIP user {key} added"}

@app.post("/admin/delete-vip")
async def delete_vip_user(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if key in users:
        del users[key]
        save_users(users)
    return {"message": f"VIP user {key} deleted"}
