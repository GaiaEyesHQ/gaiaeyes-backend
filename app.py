import os
import json
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="GaiaEyes Backend API",
    description="API for GaiaEyes MVP: Space Weather, News, VIP Access, and Schumann Resonance",
    version="1.0.0"
)

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

# -----------------------
# Response Models
# -----------------------

class SchumannResponse(BaseModel):
    amplitude: float
    frequency: float
    status: str
    timestamp: str

# -----------------------
# Public Endpoints
# -----------------------

@app.get("/news", summary="Get Latest News")
def get_news(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather", summary="Get Space Weather Data")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"solar_wind": 500, "kp_index": 5, "geomagnetic_storm": "Moderate"}

@app.get("/vip", summary="Check VIP Status")
def get_vip(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"status": f"API key {api_key} is valid for role: {users[api_key]}"}

@app.get(
    "/schumann-resonance",
    response_model=SchumannResponse,
    summary="Get Schumann Resonance Data",
    description="Returns the latest Schumann resonance amplitude and frequency data. Currently mock data for MVP."
)
def get_schumann_resonance(api_key: str):
    """
    Fetch Schumann Resonance mock data for MVP.
    Requires a valid API key.
    """
    if api_key not in users:
        return {"error": "Invalid or missing API key"}

    return {
        "amplitude": 35,
        "frequency": 7.83,
        "status": "Elevated activity detected",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

# -----------------------
# Admin Dashboard
# -----------------------

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
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    users[key] = "vip"
    save_users(users)
    return {"message": f"VIP user {key} added successfully."}

@app.post("/admin/delete-vip")
async def delete_vip_user(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if key in users:
        del users[key]
        save_users(users)
        return {"message": f"VIP user {key} deleted successfully."}
    return {"error": f"VIP user {key} not found."}
