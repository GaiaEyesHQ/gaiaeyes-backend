import os
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

app = FastAPI()

# Secret key for session handling
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

USERS_FILE = "users.json"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# -------------------------------
# Utility functions for users
# -------------------------------
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

users = load_users()

# -------------------------------
# Data Models
# -------------------------------
class AdminAction(BaseModel):
    key: str
    admin_password: str

# -------------------------------
# Public API Endpoints
# -------------------------------

@app.get("/news")
def get_news(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}


@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return {"space_weather": ["Solar winds at 600 km/s", "Kp Index: 5 (G1 storm)"]}


@app.get("/vip")
def get_vip_data(api_key: str):
    if api_key not in users or users[api_key] != "vip":
        raise HTTPException(status_code=403, detail="VIP access only")
    return {"vip_data": ["Exclusive aurora forecast", "Deep space radiation alerts"]}

# -------------------------------
# Admin JSON Endpoints
# -------------------------------

@app.post("/admin/add-vip")
def add_vip_user(action: AdminAction):
    if action.admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Not authorized")
    users[action.key] = "vip"
    save_users(users)
    return {"message": f"VIP user '{action.key}' added successfully"}

@app.post("/admin/delete-vip")
def delete_vip_user(action: AdminAction):
    if action.admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Not authorized")
    if action.key in users:
        del users[action.key]
        save_users(users)
        return {"message": f"VIP user '{action.key}' deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="User not found")

# -------------------------------
# Admin Web Dashboard (Optional)
# -------------------------------
templates = Jinja2Templates(directory="templates")

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if request.session.get("logged_in"):
        return templates.TemplateResponse("dashboard.html", {"request": request, "users": users})
    return templates.TemplateResponse("login.html", {"request": request})
