import os
import requests
from datetime import datetime
from fastapi import FastAPI

app = FastAPI()

NASA_API_KEY = os.getenv("NASA_API_KEY", "aGYhKBDmeDfGFM2JkWg2lnCimJn5XgUmwM5UkB3d")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "0ab5dc524a2d5dc7f726017a2b98c687")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "c77748626e024b9b985f07e97826e4db")

@app.get("/")
def root():
    return {"status": "Gaia Eyes API running", "updated_at": datetime.utcnow().isoformat()}
