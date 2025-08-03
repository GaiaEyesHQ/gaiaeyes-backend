import os
import json
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import logging

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FastAPI App ---
app = FastAPI()

# Secret for sessions
SESSION_SECRET = os.getenv("SESSION_SECRET", "supersecret")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# File for user storage
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

# --- Templates ---
templates = Jinja2Templates(directory="templates")

# --- Public API Endpoints ---
@app.get("/news")
def get_news(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return {"space_weather": ["KP Index: 5", "Geomagnetic storm watch"]}

@app.get("/vip")
def get_vip(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    if users[api_key] != "vip":
        raise HTTPException(status_code=403, detail="Access denied: VIP only")
    return {"vip_data": ["Exclusive aurora tracking", "Premium space alerts"]}

# --- Admin Pages ---
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if request.session.get("logged_in"):
        return templates.TemplateResponse("dashboard.html", {"request": request, "users": users})
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/admin/login")
async def admin_login(request: Request, password: str = Form(...)):
    expected_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if password == expected_password:
        request.session["logged_in"] = True
        return RedirectResponse(url="/admin", status_code=303)
    return HTMLResponse("<h3>Wrong password. <a href='/admin'>Try again</a></h3>")

@app.post("/admin/add-user")
async def add_user(request: Request, key: str = Form(...), role: str = Form(...)):
    if not request.session.get("logged_in"):
        raise HTTPException(status_code=403, detail="Not authorized")
    users[key] = role
    save_users(users)
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete-user")
async def delete_user(request: Request, key: str = Form(...)):
    if not request.session.get("logged_in"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if key in users:
        del users[key]
        save_users(users)
    return RedirectResponse(url="/admin", status_code=303)

# --- Root Route ---
@app.get("/")
def home():
    return {"message": "GaiaEyes API is running!"}
