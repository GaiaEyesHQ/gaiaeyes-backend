import os
import json
from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(
    title="GaiaEyes Backend API",
    description="API for News, Space Weather, VIP Management",
    version="1.0.0"
)

# Session middleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

# Users JSON
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

# -----------------------------
# Public Endpoints
# -----------------------------
@app.get("/news")
def get_news(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {
        "space_weather": {
            "solar_wind_speed": "520 km/s",
            "geomagnetic_storm": "Minor G1"
        }
    }

@app.get("/vip")
def get_vip_content(api_key: str):
    if api_key not in users or users[api_key] != "vip":
        return {"error": "Invalid or missing API key"}
    return {"vip_content": ["Exclusive aurora alert", "Early CME report"]}

# -----------------------------
# Admin Dashboard (HTML)
# -----------------------------
templates = Jinja2Templates(directory="templates")

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if request.session.get("logged_in"):
        return templates.TemplateResponse("dashboard.html", {"request": request, "users": users})
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/admin/login")
async def admin_login(request: Request, password: str = Body(..., embed=True)):
    if password == os.getenv("ADMIN_PASSWORD", "admin123"):
        request.session["logged_in"] = True
        return RedirectResponse(url="/admin", status_code=303)
    raise HTTPException(status_code=403, detail="Wrong admin password")

# -----------------------------
# Admin JSON API for VIP Management
# -----------------------------
@app.post("/admin/add-vip")
async def add_vip(data: dict = Body(...)):
    key = data.get("key")
    admin_password = data.get("admin_password")
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    users[key] = "vip"
    save_users(users)
    return {"status": "VIP added", "user": key}

@app.post("/admin/delete-vip")
async def delete_vip(data: dict = Body(...)):
    key = data.get("key")
    admin_password = data.get("admin_password")
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if key in users:
        del users[key]
        save_users(users)
        return {"status": "VIP deleted", "user": key}
    raise HTTPException(status_code=404, detail="User not found")

# -----------------------------
# Root Redirect
# -----------------------------
@app.get("/", include_in_schema=False)
def root():
    return {"message": "GaiaEyes Backend API is running. Visit /docs for Swagger UI."}
