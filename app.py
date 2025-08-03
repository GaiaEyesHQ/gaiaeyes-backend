import os
import json
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# Secret key for session handling
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

# --- Load Users ---
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
def get_news(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"space_weather": ["KP Index: 5", "High auroral activity"]}

@app.get("/vip")
def get_vip(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    if users[api_key] != "vip":
        return {"error": "Access denied. VIPs only."}
    return {"vip_data": ["Secret aurora spot info", "Private solar alerts"]}

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

# --- JSON-based VIP Management Endpoints ---
@app.post("/admin/add-vip")
async def add_vip(request: Request):
    data = await request.json()
    key = data.get("key")
    admin_password = data.get("admin_password")

    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Invalid admin password")

    users[key] = "vip"
    save_users(users)
    return JSONResponse({"status": "VIP added", "key": key})

@app.post("/admin/delete-vip")
async def delete_vip(request: Request):
    data = await request.json()
    key = data.get("key")
    admin_password = data.get("admin_password")

    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Invalid admin password")

    if key in users:
        del users[key]
        save_users(users)
        return JSONResponse({"status": "VIP deleted", "key": key})
    else:
        raise HTTPException(status_code=404, detail="Key not found")
