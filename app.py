import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

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
async def get_news(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
async def get_space_weather(api_key: str):
    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return {"space_weather": ["KP Index 5", "High solar wind speed"]}

@app.get("/vip")
async def get_vip_content(api_key: str):
    if api_key not in users or users[api_key] != "vip":
        raise HTTPException(status_code=403, detail="VIP access required")
    return {"vip_content": ["Exclusive satellite images", "Deep space reports"]}

# -----------------------------
# Admin Endpoints (JSON-based)
# -----------------------------

class AdminAction(BaseModel):
    key: str
    role: str = "vip"
    admin_password: str

@app.post("/add-vip")
async def add_vip(action: AdminAction):
    if action.admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    users[action.key] = action.role
    save_users(users)
    return {"message": f"VIP user '{action.key}' added successfully."}

@app.post("/delete-vip")
async def delete_vip(action: AdminAction):
    if action.admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    if action.key in users:
        del users[action.key]
        save_users(users)
        return {"message": f"VIP user '{action.key}' deleted successfully."}
    raise HTTPException(status_code=404, detail="User not found")
