import os
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

# --- FastAPI App ---
app = FastAPI()

# Secret key for session handling
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

# --------------------
# Public Endpoints
# --------------------
@app.get("/news")
def get_news(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"space_weather": {"geomagnetic_index": 5, "solar_flare": "M1-class"}}

@app.get("/vip")
def get_vip_content(api_key: str):
    if users.get(api_key) != "vip":
        return {"error": "VIP access required"}
    return {"vip_content": ["Secret aurora forecast map", "Exclusive data feed"]}

# --------------------
# Admin Models
# --------------------
class AdminRequest(BaseModel):
    key: str
    admin_password: str

# --------------------
# Admin Endpoints
# --------------------
@app.post("/admin/add-vip")
async def add_vip(data: AdminRequest):
    # DEBUG LOGGING
    print("=== ADD VIP ATTEMPT ===")
    print(f"Received: key={data.key}, admin_password={data.admin_password}")
    print(f"Expected ADMIN_PASSWORD={os.getenv('ADMIN_PASSWORD')}")

    # Admin check
    if data.admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Forbidden")

    users[data.key] = "vip"
    save_users(users)
    return {"message": f"User {data.key} added as VIP."}

@app.post("/admin/delete-vip")
async def delete_vip(data: AdminRequest):
    # DEBUG LOGGING
    print("=== DELETE VIP ATTEMPT ===")
    print(f"Received: key={data.key}, admin_password={data.admin_password}")
    print(f"Expected ADMIN_PASSWORD={os.getenv('ADMIN_PASSWORD')}")

    # Admin check
    if data.admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Forbidden")

    if data.key in users:
        del users[data.key]
        save_users(users)
        return {"message": f"User {data.key} deleted."}
    else:
        raise HTTPException(status_code=404, detail="User not found")
