import os, json, io, datetime, requests
from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from bs4 import BeautifulSoup

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "supersecret"))

USERS_FILE = "users.json"
CACHE_FILE = "cache.json"
IMAGE_CACHE_FILE = "ionosphere_chart.gif"

def load_users():
    return json.load(open(USERS_FILE)) if os.path.exists(USERS_FILE) else {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

users = load_users()

def load_cache():
    return json.load(open(CACHE_FILE)) if os.path.exists(CACHE_FILE) else {}

def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)

cache = load_cache()

def timestamp():
    return datetime.datetime.utcnow().isoformat() + "Z"

# --- Data Fetchers ---

def fetch_schumann():
    url = "http://sosrff.tsu.ru/new/shm.jpg"
    page = "http://sosrff.tsu.ru/?page_id=7"
    amplitude = None
    try:
        html = requests.get(page, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
        tds = soup.find_all("td")
        for td in tds:
            if "Amplitude" in td.text:
                amplitude = td.find_next("td").text.strip()
                break
    except:
        amplitude = cache.get("schumann", {}).get("amplitude_dB")

    data = {
        "timestamp": timestamp(),
        "frequency_Hz": 7.83,
        "amplitude_dB": amplitude,
        "image_url": url,
        "status": "OK" if amplitude else "CACHED"
    }
    cache["schumann"] = data
    save_cache(cache)
    return data

def fetch_ionosphere():
    url = "https://www.sws.bom.gov.au/HF_Systems/1/1"
    foF2 = None
    try:
        html = requests.get(url, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
        td = soup.find("td", string="foF2")
        if td:
            foF2 = td.find_next("td").text.strip()
    except:
        foF2 = cache.get("ionosphere", {}).get("foF2_MHz")

    data = {
        "timestamp": timestamp(),
        "station": "Sydney",
        "foF2_MHz": foF2,
        "image_url": "/ionosphere-chart",
        "status": "OK" if foF2 else "CACHED"
    }
    cache["ionosphere"] = data
    save_cache(cache)
    return data

def fetch_space_weather():
    try:
        # Example: Replace with NOAA SWPC API if desired
        kp = 2
        solar_wind = 400
        data = {
            "timestamp": timestamp(),
            "kp_index": kp,
            "solar_wind_speed_kms": solar_wind,
            "status": "OK"
        }
    except:
        data = cache.get("space_weather", {
            "timestamp": timestamp(),
            "kp_index": None,
            "solar_wind_speed_kms": None,
            "status": "CACHED"
        })

    cache["space_weather"] = data
    save_cache(cache)
    return data

def fetch_ionosphere_chart():
    url = "https://www.sws.bom.gov.au/Images/HF/WorldIono/sydney.gif"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.sws.bom.gov.au/"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            with open(IMAGE_CACHE_FILE, "wb") as f:
                f.write(r.content)
            return r.content
        elif os.path.exists(IMAGE_CACHE_FILE):
            return open(IMAGE_CACHE_FILE, "rb").read()
        else:
            raise HTTPException(status_code=502, detail="No chart available")
    except:
        if os.path.exists(IMAGE_CACHE_FILE):
            return open(IMAGE_CACHE_FILE, "rb").read()
        raise HTTPException(status_code=502, detail="No chart available")

# --- API Endpoints ---

@app.get("/schumann-resonance")
def get_schumann(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return fetch_schumann()

@app.get("/ionosphere")
def get_ionosphere(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return fetch_ionosphere()

@app.get("/ionosphere-chart")
def get_ionosphere_chart(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    img = fetch_ionosphere_chart()
    return StreamingResponse(io.BytesIO(img), media_type="image/gif")

@app.get("/space-weather")
def get_space_weather(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return fetch_space_weather()

@app.get("/vip")
def get_vip(api_key: str):
    if api_key not in users:
        return {"error": "Invalid or missing API key"}
    return {
        "schumann": fetch_schumann(),
        "ionosphere": fetch_ionosphere(),
        "space_weather": fetch_space_weather()
    }

@app.post("/admin/add-vip")
def add_vip(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    users[key] = "vip"
    save_users(users)
    return {"status": "VIP user added", "key": key}

@app.post("/admin/delete-vip")
def delete_vip(key: str = Form(...), admin_password: str = Form(...)):
    if admin_password != os.getenv("ADMIN_PASSWORD", "admin123"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if key in users:
        del users[key]
        save_users(users)
        return {"status": "VIP user deleted", "key": key}
    raise HTTPException(status_code=404, detail="User not found")
