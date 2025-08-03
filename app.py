import os
import json
import logging
from fastapi import FastAPI, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# -------------------- SETUP --------------------
app = FastAPI(title="GaiaEyes Backend", description="Provides space weather and VIP access")

# Logging to Render logs
logging.basicConfig(level=logging.INFO)

# Secret key for session handling
SESSION_SECRET = os.getenv("SESSION_SECRET", "supersecret")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Users JSON file
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

# -------------------- HELPER FUNCTIONS --------------------
def validate_api_key(api_key: str, required_role: str = None):
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    if api_key not in users:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if required_role and users[api_key] != required_role:
        raise HTTPException(status_code=403, detail=f"Not authorized for {required_role} access")

# -------------------- PUBLIC ENDPOINTS --------------------
@app.get("/news")
def get_news(api_key: str = Query(None)):
    logging.info(f"/news accessed with key: {api_key}")
    validate_api_key(api_key)  # Free or VIP can access
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str = Query(None)):
    logging.info(f"/space-weather accessed with key: {api_key}")
    validate_api_key(api_key)  # Free or VIP can access
    return {"space_weather": ["Kp-index: 5", "Solar wind speed: 450 km/s"]}

@app.get("/vip")
def get_vip(api_key: str = Query(None)):
    logging.info(f"/vip accessed with key: {api_key}")
    validate_api_key(api_key, required_role="vip")
    return {"vip_content": ["Exclusive aurora forecast", "Private satellite data"]}

# -------------------- ADMIN DASHBOARD --------------------
templates = Jinja2Templates(directory="templates")

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if request.session.get("logged_in"):
        return templates.TemplateResponse("dashboard.html", {"request": request, "users": users})
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/admin/login")
async def admin_login(request: Request, password: str = Form(...)):
    expected_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if password == expected_password:
        request.session["logged_in"] = True
        logging.info("Admin logged in successfully")
        return RedirectResponse(url="/admin", status_code=303)
    logging.warning("Failed admin login attempt")
    return HTMLResponse("<h3>Wrong password. <a href='/admin'>Try again</a></h3>")

@app.post("/admin/add-vip")
async def add_vip_user(key: str = Form(...), admin_password: str = Form(...)):
    expected_password = os.getenv("ADMIN_PASSWORD", "admin123")
    logging.info(f"=== ADD VIP ATTEMPT === Received: key={key}, admin_password={admin_password}")
    logging.info(f"Expected ADMIN_PASSWORD={expected_password}")

    if admin_password != expected_password:
        raise HTTPException(status_code=403, detail="Invalid admin password")

    users[key] = "vip"
    save_users(users)
    logging.info(f"VIP user {key} added")
    return {"message": f"VIP user '{key}' added successfully"}

@app.post("/admin/delete-vip")
async def delete_vip_user(key: str = Form(...), admin_password: str = Form(...)):
    expected_password = os.getenv("ADMIN_PASSWORD", "admin123")
    logging.info(f"=== DELETE VIP ATTEMPT === Received: key={key}, admin_password={admin_password}")

    if admin_password != expected_password:
        raise HTTPException(status_code=403, detail="Invalid admin password")

    if key in users:
        del users[key]
        save_users(users)
        logging.info(f"VIP user {key} deleted")
        return {"message": f"VIP user '{key}' deleted successfully"}
    else:
        logging.warning(f"Tried to delete non-existent user {key}")
        return {"message": f"User '{key}' not found"}
