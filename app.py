import json
import os
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse

app = FastAPI()

# JSON file for storing user keys
USER_FILE = "users.json"

# Load users from JSON
def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r") as f:
            return {user["key"]: user for user in json.load(f)}
    return {}

# Save users to JSON
def save_users(users):
    with open(USER_FILE, "w") as f:
        json.dump(list(users.values()), f, indent=2)

# Initialize users
USER_DB = load_users()

# Middleware to check API key
async def verify_api_key(request: Request):
    api_key = request.headers.get("x-api-key")
    if not api_key or api_key not in USER_DB:
        return JSONResponse(status_code=403, content={"error": "Invalid or missing API key"})
    request.state.user_role = USER_DB[api_key]["role"]

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Skip auth for root
    if request.url.path != "/":
        response = await verify_api_key(request)
        if isinstance(response, JSONResponse):
            return response
    return await call_next(request)

@app.get("/")
async def root():
    return {"message": "GaiaEyes Backend is running!"}

@app.get("/news")
async def get_news():
    return {"data": "Here will be your space news"}

@app.get("/space-weather")
async def get_space_weather():
    return {"data": "Here will be your space weather"}

# Admin endpoint to add a user
@app.post("/admin/add-user")
async def add_user(user: dict):
    key = user.get("key")
    role = user.get("role", "free")
    if not key:
        raise HTTPException(status_code=400, detail="Key is required")
    USER_DB[key] = {"key": key, "role": role}
    save_users(USER_DB)
    return {"message": "User added", "key": key, "role": role}
