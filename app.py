import os
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# Allow CORS for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Secret key for session handling
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

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

# -------------------------
# Utility for key validation
# -------------------------
def validate_api_key(api_key: str, role_required: str = None):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    if role_required and users[api_key] != role_required:
        raise HTTPException(status_code=403, detail="Forbidden: Insufficient role")

# -------------------------
# Public endpoints
# -------------------------

@app.get("/news")
def get_news(api_key: str):
    validate_api_key(api_key)
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    validate_api_key(api_key)
    return {
        "space_weather": {
            "solar_wind_speed": "450 km/s",
            "geomagnetic_storm": "Minor G1 expected",
        }
    }

@app.get("/vip")
def get_vip_data(api_key: str):
    validate_api_key(api_key, role_required="vip")
    return {"vip_data": ["Exclusive aurora footage", "Early warning alerts"]}

# -------------------------
# Admin endpoints
# -------------------------

@app.post("/admin/add-vip")
async def add_vip_user(request: Request):
    data = await request.json()
    admin_password = data.get("admin_password")
    key = data.get("key")

    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")

    if not key:
        raise HTTPException(status_code=400, detail="Missing user key")

    users[key] = "vip"
    save_users(users)
    return {"message": f"User {key} added as VIP."}


@app.post("/admin/delete-vip")
async def delete_vip_user(request: Request):
    data = await request.json()
    admin_password = data.get("admin_password")
    key = data.get("key")

    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")

    if not key or key not in users:
        raise HTTPException(status_code=404, detail="User not found")

    del users[key]
    save_users(users)
    return {"message": f"User {key} deleted."}
