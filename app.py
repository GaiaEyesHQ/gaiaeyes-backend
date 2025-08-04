import os
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

app = FastAPI()

# Secret key for session handling (use your Render environment variable)
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

# ------------------------------
#   Public Endpoints
# ------------------------------

@app.get("/news")
def get_news(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}


@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"space_weather": ["Solar wind speed 450 km/s", "Kp-index 5"]}


@app.get("/vip")
def get_vip(api_key: str):
    if api_key not in users or users[api_key] != "vip":
        return {"error": "Invalid or missing API key"}
    return {"vip_data": ["Secret aurora map", "Pro space weather forecast"]}


# ------------------------------
#   Admin Endpoints (JSON Body)
# ------------------------------

class AdminAction(BaseModel):
    key: str
    admin_password: str


@app.post("/admin/add-vip")
def add_vip(action: AdminAction):
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if action.admin_password != admin_password:
        raise HTTPException(status_code=403, detail="Not authorized")

    users[action.key] = "vip"
    save_users(users)
    return {"status": "VIP user added", "user": action.key}


@app.post("/admin/delete-vip")
def delete_vip(action: AdminAction):
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if action.admin_password != admin_password:
        raise HTTPException(status_code=403, detail="Not authorized")

    if action.key in users:
        del users[action.key]
        save_users(users)
        return {"status": "VIP user deleted", "user": action.key}
    else:
        raise HTTPException(status_code=404, detail="User not found")


# ------------------------------
#   Admin Dashboard (Optional)
# ------------------------------

templates = Jinja2Templates(directory="templates")


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if request.session.get("logged_in"):
        return templates.TemplateResponse("dashboard.html", {"request": request, "users": users})
    return templates.TemplateResponse("login.html", {"request": request})
