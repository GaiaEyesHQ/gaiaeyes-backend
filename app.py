import os
import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests (frontend/mobile)

# Load environment variables
NASA_API_KEY = os.environ.get("NASA_API_KEY")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

# ✅ Root endpoint
@app.route("/")
def home():
    return jsonify({"message": "GaiaEyes Backend is running!"})

# ✅ Space Weather Endpoint (example: NASA DONKI API)
@app.route("/space-weather")
def space_weather():
    url = f"https://api.nasa.gov/DONKI/notifications?type=all&api_key={NASA_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Earth Weather Endpoint (example: OpenWeather current global weather)
@app.route("/earth-weather/<city>")
def earth_weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ News Endpoint (example: Space & Science News)
@app.route("/news")
def news():
    url = f"https://newsapi.org/v2/everything?q=space OR astronomy OR solar&language=en&apiKey={NEWS_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ For Render deployment
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
