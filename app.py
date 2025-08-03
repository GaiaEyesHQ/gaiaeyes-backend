from flask import Flask, jsonify, request
import requests
import os

app = Flask(__name__)

# -------------------
# API KEYS (use env vars in production)
# -------------------
NASA_API_KEY = os.getenv("NASA_API_KEY", "aGYhKBDmeDfGFM2JkWg2lnCimJn5XgUmwM5UkB3d")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY", "0ab5dc524a2d5dc7f726017a2b98c687")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "c77748626e024b9b985f07e97826e4db")

# -------------------
# ROUTES
# -------------------

@app.route("/")
def home():
    return jsonify({"message": "Gaia Eyes Backend is Running!"})

@app.route("/space-weather")
def space_weather():
    # NASA DONKI endpoint example for space weather alerts
    url = f"https://api.nasa.gov/DONKI/notifications?type=all&api_key={NASA_API_KEY}"
    response = requests.get(url)
    data = response.json() if response.status_code == 200 else {"error": "NASA API failed"}
    return jsonify(data)

@app.route("/earth-weather")
def earth_weather():
    city = request.args.get("city", "New York")
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_KEY}&units=metric"
    response = requests.get(url)
    data = response.json() if response.status_code == 200 else {"error": "OpenWeatherMap API failed"}
    return jsonify(data)

@app.route("/news")
def news():
    url = f"https://newsapi.org/v2/top-headlines?category=science&language=en&apiKey={NEWS_API_KEY}"
    response = requests.get(url)
    data = response.json() if response.status_code == 200 else {"error": "News API failed"}
    return jsonify(data)


# -------------------
# RUN LOCALLY (Render will use Uvicorn)
# -------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
