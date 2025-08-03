import os
import json
from fastapi import FastAPI, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# Secret key for session handling
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

# --- Public Endpoints ---
@app.get("/news")
def get_news(api_key: str = Query(...)):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str = Query(...)):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {
        "space_weather": {
            "solar_wind_speed": "420 km/s",
            "geomagnetic_storm": "Kp index 5 (G1)",
            "aurora_forecast": "Moderate chance at high latitudes"
        }
    }

@app.get("/vip")
def get_vip_content(api_key: str = Query(...)):
    if api_key not in users or users[api_key] != "vip":
        return {"error": "VIP access only"}
    return {"vip_content": ["Exclusive solar imagery", "Deep space anomaly reports"]}

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

@app.post("/admin/add-user")
async def add_user(request: Request, key: str = Form(...), role: str = Form(...)):
    if not request.session.get("logged_in"):
        raise HTTPException(status_code=403, detail="Not authorized")
    users[key] = role
    save_users(users)
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete-user")
async def delete_user(request: Request, key: str = Form(...)):
    if not request.session.get("logged_in"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if key in users:
        del users[key]
        save_users(users)
    return RedirectResponse(url="/admin", status_code=303)
