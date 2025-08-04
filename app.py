import os
import json
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="GaiaEyes API",
    description="Backend API for GaiaEyes with VIP and Admin functionality",
    version="2.0.0"
)

# Secret key for session handling (set your own in Render)
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

# -------------------------
# Pydantic model for JSON admin requests
# -------------------------
class VIPRequest(BaseModel):
    key: str
    admin_password: str

# -------------------------
# Public API Endpoints
# -------------------------
@app.get("/news")
def get_news(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"news": ["Solar storm detected", "Aurora visible tonight"]}

@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {"space_weather": {"solar_wind": "moderate", "geomagnetic_storm": "G2"}}

@app.get("/vip")
def get_vip(api_key: str):
    if api_key not in users or users[api_key] != "vip":
        return {"error": "Invalid or missing API key"}
    return {"vip_content": ["Exclusive space weather insights", "Early aurora alerts"]}


# -------------------------
# Admin Dashboard (HTML + Sessions)
# -------------------------
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

# -------------------------
# Admin API for VIP Management (JSON-based)
# -------------------------
@app.post("/admin/add-vip")
async def add_vip(data: VIPRequest):
    print(f"=== ADD VIP ATTEMPT ===")
    print(f"Received: key={data.key}, admin_password={data.admin_password}")

    if data.admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")

    users[data.key] = "vip"
    save_users(users)
    return {"message": f"VIP user {data.key} added successfully."}


@app.post("/admin/delete-vip")
async def delete_vip(data: VIPRequest):
    print(f"=== DELETE VIP ATTEMPT ===")
    print(f"Received: key={data.key}, admin_password={data.admin_password}")

    if data.admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")

    if data.key in users:
        del users[data.key]
        save_users(users)
        return {"message": f"VIP user {data.key} deleted successfully."}
    else:
        raise HTTPException(status_code=404, detail="User not found")
