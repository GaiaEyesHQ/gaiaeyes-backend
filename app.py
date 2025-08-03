import os
import json
import requests
from fastapi import FastAPI, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# --- CONFIG ---
NASA_KEY = os.getenv("NASA_KEY", "aGYhKBDmeDfGFM2JkWg2lnCimJn5XgUmwM5UkB3d")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY", "0ab5dc524a2d5dc7f726017a2b98c687")
NEWS_KEY = os.getenv("NEWS_KEY", "c77748626e024b9b985f07e97826e4db")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

USERS_FILE = "users.json"

# --- APP INIT ---
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

templates = Jinja2Templates(directory="templates")

# --- USERS HANDLING ---
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

users = load_users()

# --- AUTH HELPER ---
def check_api_key(api_key: str):
    if not api_key or api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return users[api_key]

# --- PUBLIC API ENDPOINTS ---
@app.get("/news")
def get_news(api_key: str = Query(...)):
    role = check_api_key(api_key)

    # Example real call to News API (if needed)
    url = f"https://newsapi.org/v2/top-headlines?category=science&apiKey={NEWS_KEY}&pageSize=3"
    r = requests.get(url)
    data = r.json()

    return {"role": role, "news": data.get("articles", [])}

@app.get("/space-weather")
def get_space_weather(api_key: str = Query(...)):
    role = check_api_key(api_key)

    # NASA DONKI API for space weather example
    url = f"https://api.nasa.gov/DONKI/notifications?api_key={NASA_KEY}"
    r = requests.get(url)
    data = r.json()

    return {"role": role, "space_weather": data}

@app.get("/vip-users")
def list_vip_users(admin_password: str = Query(...)):
    if admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Invalid admin password")
    vip_users = {k: v for k, v in users.items() if v == "vip"}
    return vip_users

# --- JSON-BASED ADMIN ENDPOINTS (Postman Ready) ---
@app.post("/admin/add-user")
async def add_user_json(key: str = Query(...), role: str = Query(...), admin_password: str = Query(...)):
    if admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Invalid admin password")
    users[key] = role
    save_users(users)
    return {"message": f"User {key} added with role {role}"}

@app.delete("/admin/delete-user")
async def delete_user_json(key: str = Query(...), admin_password: str = Query(...)):
    if admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Invalid admin password")
    if key in users:
        del users[key]
        save_users(users)
        return {"message": f"User {key} deleted"}
    else:
        raise HTTPException(status_code=404, detail="User not found")

# --- HTML ADMIN DASHBOARD (Optional) -
