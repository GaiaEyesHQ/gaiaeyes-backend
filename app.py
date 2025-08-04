import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from fastapi import Request

# --- Initialize App ---
app = FastAPI(title="GaiaEyes API", description="API for GaiaEyes project")

# Session middleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

# --- Users storage ---
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
    return {"space_weather": {"solar_wind_speed": "500 km/s", "geomagnetic_index": "Kp=6"}}

@app.get("/vip")
def get_vip(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    if users[api_key] != "vip":
        return {"error": "Not a VIP user"}
    return {"vip_content": ["Exclusive space images", "VIP early alerts"]}

# --- Admin Dashboard ---
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if request.session.get("logged_in"):
        return templates.TemplateResponse("dashboard.html", {"request": request, "users": users})
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/admin/login")
async def admin_login(request: Request):
    form = await request.form()
    password = form.get("password")
    if password == os.getenv("ADMIN_PASSWORD", "admin123"):
        request.session["logged_in"] = True
        return RedirectResponse(url="/admin", status_code=303)
    return HTMLResponse("<h3>Wrong password. <a href='/admin'>Try again</a></h3>")

# --- API Models for Add/Delete VIP ---
class AdminAction(BaseModel):
    key: str
    admin_password: str

@app.post("/admin/add-vip")
def add_vip(data: AdminAction):
    admin_password_env = os.getenv("ADMIN_PASSWORD", "admin123")
    print(f"=== ADD VIP ATTEMPT ===\nReceived: key={data.key}, admin_password={data.admin_password}\nExpected ADMIN_PASSWORD={admin_password_env}")

    if data.admin_password != admin_password_env:
        raise HTTPException(status_code=403, detail="Not authorized")
    users[data.key] = "vip"
    save_users(users)
    return {"message": f"VIP user '{data.key}' added successfully."}

@app.post("/admin/delete-vip")
def delete_vip(data: AdminAction):
    admin_password_env = os.getenv("ADMIN_PASSWORD", "admin123")
    print(f"=== DELETE VIP ATTEMPT ===\nReceived: key={data.key}, admin_password={data.admin_password}\nExpected ADMIN_PASSWORD={admin_password_env}")

    if data.admin_password != admin_password_env:
        raise HTTPException(status_code=403, detail="Not authorized")
    if data.key in users:
        del users[data.key]
        save_users(users)
        return {"message": f"VIP user '{data.key}' deleted successfully."}
    raise HTTPException(status_code=404, detail=f"VIP user '{data.key}' not found.")
