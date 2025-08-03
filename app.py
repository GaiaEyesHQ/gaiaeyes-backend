import os
import json
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="GaiaEyes Backend API",
    description="API for space weather, news, and VIP access management",
    version="1.0.0",
)

# Session middleware
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

# Pydantic model for admin requests
class AdminAction(BaseModel):
    key: str
    admin_password: str

# --- Public Endpoints ---
@app.get("/news", tags=["Public Endpoints"])
def get_news(api_key: str):
    """Returns the latest space-related news for authorized users."""
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}


@app.get("/space-weather", tags=["Public Endpoints"])
def get_space_weather(api_key: str):
    """Returns space weather updates for authorized users."""
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"space_weather": ["Solar wind speed: 450 km/s", "Kp Index: 5 (G1 storm)"]}


@app.get("/vip", tags=["Public Endpoints"])
def get_vip_content(api_key: str):
    """Returns VIP content if the user's role is 'vip'."""
    role = users.get(api_key)
    if not role:
        return {"error": "Invalid or missing API key"}
    if role != "vip":
        return {"error": "Not authorized for VIP content"}
    return {"vip_content": ["Exclusive Aurora Forecast", "Premium Space Data"]}


# --- Admin Endpoints ---
@app.post("/admin/add-vip", tags=["VIP Admin"])
def add_vip_user(data: AdminAction):
    """
    Adds a new VIP user.
    - Requires `admin_password`
    - Provide a `key` for the new VIP user
    """
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    print(f"=== ADD VIP ATTEMPT ===\nReceived: key={data.key}, admin_password={data.admin_password}\nExpected ADMIN_PASSWORD={admin_password}")

    if data.admin_password != admin_password:
        raise HTTPException(status_code=403, detail="Not authorized")

    users[data.key] = "vip"
    save_users(users)
    return {"status": "success", "message": f"User {data.key} added as VIP"}


@app.post("/admin/delete-vip", tags=["VIP Admin"])
def delete_vip_user(data: AdminAction):
    """
    Deletes a VIP user.
    - Requires `admin_password`
    - Provide the VIP `key` to delete
    """
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    print(f"=== DELETE VIP ATTEMPT ===\nReceived: key={data.key}, admin_password={data.admin_password}\nExpected ADMIN_PASSWORD={admin_password}")

    if data.admin_password != admin_password:
        raise HTTPException(status_code=403, detail="Not authorized")

    if data.key in users:
        del users[data.key]
        save_users(users)
        return {"status": "success", "message": f"User {data.key} deleted"}
    else:
        raise HTTPException(status_code=404, detail="User not found")
