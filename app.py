import os
import json
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# Secret key for session handling
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

# Load users from JSON file
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
    return {"space_weather": ["Kp-index: 6", "High solar activity"]}

@app.get("/vip")
def get_vip(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    if users[api_key] != "vip":
        return {"error": "Access denied. VIP only."}
    return {"vip_content": ["Exclusive Aurora forecast", "Private alerts"]}


# --- Admin Endpoints (JSON body for Postman testing) ---
@app.post("/admin/add-vip")
def add_vip(key: str = Body(...), admin_password: str = Body(...)):
    expected_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if admin_password != expected_password:
        raise HTTPException(status_code=403, detail="Invalid admin password")
    users[key] = "vip"
    save_users(users)
    return {"status": "VIP user added", "user": key}

@app.post("/admin/delete-vip")
def delete_vip(key: str = Body(...), admin_password: str = Body(...)):
    expected_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if admin_password != expected_password:
        raise HTTPException(status_code=403, detail="Invalid admin password")
    if key in users:
        del users[key]
        save_users(users)
        return {"status": "VIP user deleted", "user": key}
    raise HTTPException(status_code=404, detail="User not found")


# --- Admin HTML Dashboard ---
templates = Jinja2Templates(directory="templates")

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if request.session.get("logged_in"):
        return templates.TemplateResponse("dashboard.html", {"request": request, "users": users})
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/admin/login")
async def admin_login(request: Request, password: str = Body(...)):
    if password == os.getenv("ADMIN_PASSWORD", "admin123"):
        request.session["logged_in"] = True
        return RedirectResponse(url="/admin", status_code=303)
    return HTMLResponse("<h3>Wrong password. <a href='/admin'>Try again</a></h3>")
