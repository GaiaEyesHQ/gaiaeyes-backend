import os
import json
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# --- App Setup ---
app = FastAPI(title="GaiaEyes API", version="2.0")

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: HTMLResponse("Rate limit exceeded", status_code=429))
app.add_middleware(SlowAPIMiddleware)

# Session Middleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

# CORS Middleware
origins = [
    "http://localhost:3000",  # Local development
    "https://your-frontend-domain.com"  # Replace with real domain
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# --- Users JSON Handling ---
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

# --- Public Endpoints ---
@app.get("/news")
@limiter.limit("10/minute")
def get_news(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
@limiter.limit("10/minute")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"space_weather": ["Kp Index: 5", "Geomagnetic storm watch in effect"]}

@app.get("/vip")
@limiter.limit("5/minute")
def get_vip(api_key: str):
    if api_key not in users or users[api_key] != "vip":
        return {"error": "Invalid or missing VIP API key"}
    return {"vip_content": ["Exclusive aurora forecast", "Advanced space weather insights"]}

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
async def add_vip(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    users[key] = "vip"
    save_users(users)
    return {"message": f"VIP user {key} added successfully."}

@app.post("/admin/delete-vip")
async def delete_vip(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    if key in users:
        del users[key]
        save_users(users)
        return {"message": f"VIP user {key} deleted successfully."}
    raise HTTPException(status_code=404, detail="User not found")
