import os
import json
import logging
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gaiaeyes-backend")

app = FastAPI()

# Secret key for session handling (set your own in Render)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

# Load users from JSON
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

# --- Utility: Mask API keys in logs ---
def mask_key(key: str):
    if len(key) > 4:
        return key[:2] + "*"*(len(key)-4) + key[-2:]
    return key

def log_request(endpoint: str, key: str):
    logger.info(f"[{datetime.utcnow()}] Endpoint: {endpoint}, API Key: {mask_key(key)}")

# --- Public Endpoints ---
@app.get("/news")
def get_news(api_key: str):
    log_request("/news", api_key)
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    log_request("/space-weather", api_key)
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"space_weather": ["KP Index: 5", "Solar wind speed: 450 km/s"]}

@app.get("/vip")
def get_vip_content(api_key: str):
    log_request("/vip", api_key)
    if api_key not in users or users[api_key] != "vip":
        return {"error": "VIP access only"}
    return {"vip_data": ["Exclusive aurora forecast map", "Real-time geomagnetic alerts"]}

# --- Admin Dashboard ---
templates = Jinja2Templates(directory="templates")

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
    logger.info(f"=== ADD VIP ATTEMPT ===\nReceived: key={key}, admin_password={admin_password}")
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    users[key] = "vip"
    save_users(users)
    logger.info(f"VIP User Added: {key}")
    return {"message": f"VIP user {key} added."}

@app.post("/admin/delete-vip")
async def delete_vip_user(key: str = Form(...), admin_password: str = Form(...)):
    logger.info(f"=== DELETE VIP ATTEMPT ===\nReceived: key={key}, admin_password={admin_password}")
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if key in users:
        del users[key]
        save_users(users)
        logger.info(f"VIP User Deleted: {key}")
        return {"message": f"VIP user {key} deleted."}
    raise HTTPException(status_code=404, detail="User not found")

# --- Root Page ---
@app.get("/", response_class=HTMLResponse)
def home_page():
    return "<h1>GaiaEyes API is running!</h1><p>Use /news, /space-weather, or /vip endpoints.</p>"
