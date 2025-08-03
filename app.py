from flask import Flask, jsonify, request
import requests
import os
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Load API keys from environment variables
NASA_API_KEY = os.environ.get("NASA_API_KEY", "")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "supersecret")  # For influencer/free users

# Root route
@app.route("/")
def home():
    return jsonify({"message": "GaiaEyes Backend is Live!"})

# Space weather route
@app.route("/space-weather", methods=["GET"])
def space_weather():
    try:
        # Example: NASA DONKI API (Space Weather)
        url = f"https://api.nasa.gov/DONKI/WSAEnlilSimulations?api_key={NASA_API_KEY}"
        response = requests.get(url)
        data = response.json()
        return jsonify({"timestamp": datetime.utcnow().isoformat(), "data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Earth weather route
@app.route("/earth-weather", methods=["GET"])
def earth_weather():
    city = request.args.get("city", "New York")
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        response = requests.get(url)
        data = response.json()
        return jsonify({"timestamp": datetime.utcnow().isoformat(), "city": city, "data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# News route
@app.route("/news", methods=["GET"])
def news():
    try:
        url = f"https://newsapi.org/v2/everything?q=space+weather&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
        response = requests.get(url)
        data = response.json()
        return jsonify({"timestamp": datetime.utcnow().isoformat(), "articles": data.get("articles", [])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Protected route for influencer/free users
@app.route("/grant-access", methods=["POST"])
def grant_access():
    data = request.get_json()
    admin_key = data.get("admin_key")
    user_email = data.get("user_email")

    if admin_key != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    # Simulated granting access
    return jsonify({"message": f"Free access granted to {user_email}"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
