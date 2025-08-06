import os
import json
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# -----------------------
# App Initialization
# -----------------------
app = FastAPI(title="GaiaEyes API", description="FastAPI backend with VIP and admin functionality")

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: (HTMLResponse("Too Many Requests", status_code=429)))

# Secret key for sessions
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

# -----------------------
# User Data
# -----------------------
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
# Templates
# -----------------------
templates = Jinja2Templates(directory="templates")

# -----------------------
# Public Endpoints
# -----------------------

@app.get("/news")
@limiter.limit("5/minute")
def get_news(request: Request, api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}


@app.get("/space-weather")
@limiter.limit("5/minute")
def get_space_weather(request: Request, api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"space_weather": {"solar_activity": "Moderate", "aurora_index": 5}}


@app.get("/vip")
@limiter.limit("5/minute")
def get_vip_content(request: Request, api_key: str):
    if api_key not in users or users[api_key] != "vip":
        return {"error": "VIP access required or invalid API key"}
    return {"vip_content": ["Secret aurora forecasts", "Advanced space weather predictions"]}

from datetime import datetime

@app.get("/schumann-resonance")
def get_schumann_resonance(api_key: str):
    # Validate API key
    if api_key not in users:
        return {"error": "Invalid or missing API key"}

    # Mock response for now (replace with live data later)
    response = {
        "amplitude": 35,  # Example amplitude
        "frequency": 7.83,  # Fundamental Schumann frequency in Hz
        "status": "Elevated activity detected",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    return response


# -----------------------
# Admin Dashboard (HTML)
# -----------------------

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

# -----------------------
# Admin API Endpoints
# -----------------------

@app.post("/admin/add-vip")
async def add_vip_user(request: Request):
    data = await request.json()
    key = data.get("key")
    admin_password = data.get("admin_password")

    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Forbidden: wrong admin password")

    users[key] = "vip"
    save_users(users)
    return {"message": f"VIP user {key} added successfully."}


@app.post("/admin/delete-vip")
async def delete_vip_user(request: Request):
    data = await request.json()
    key = data.get("key")
    admin_password = data.get("admin_password")

    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Forbidden: wrong admin password")

    if key in users:
        del users[key]
        save_users(users)
        return {"message": f"VIP user {key} deleted successfully."}
    else:
        raise HTTPException(status_code=404, detail="User not found")

