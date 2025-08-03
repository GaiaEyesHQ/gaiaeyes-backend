import os
import json
from fastapi import FastAPI, Request, Form, HTTPException, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# --- SESSION SECRET ---
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

# --- USERS STORAGE ---
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

# --- PUBLIC API ENDPOINTS ---
@app.get("/news")
def get_news(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"space_weather": {"kp_index": 6, "solar_flare": "M-class detected"}}

@app.get("/vip")
def get_vip(api_key: str):
    if api_key not in users or users[api_key] != "vip":
        return {"error": "VIP access only"}
    return {"vip_data": ["Exclusive aurora forecasts", "Early warning alerts"]}

# --- ADMIN PANEL (HTML) ---
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

# --- JSON-BASED ADMIN ENDPOINTS (FOR POSTMAN) ---
@app.post("/admin/add-user-json")
async def add_user_json(data: dict = Body(...)):
    admin_key = data.get("admin_key")
    key = data.get("key")
    role = data.get("role")

    if admin_key != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Invalid admin key")
    if not key or not role:
        raise HTTPException(status_code=422, detail="Key and role are required")

    users[key] = role
    save_users(users)
    return {"status": "success", "message": f"User {key} added with role {role}"}

@app.post("/admin/delete-user-json")
async def delete_user_json(data: dict = Body(...)):
    admin_key = data.get("admin_key")
    key = data.get("key")

    if admin_key != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Invalid admin key")
    if not key:
        raise HTTPException(status_code=422, detail="Key is required")

    if key in users:
        del users[key]
        save_users(users)
        return {"status": "success", "message": f"User {key} deleted"}
    else:
        return {"status": "not_found", "message": f"User {key} does not exist"}
