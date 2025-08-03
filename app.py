import os
import requests
from flask import Flask, jsonify

app = Flask(__name__)

# Load API keys from environment or use defaults
NASA_API_KEY = os.getenv("NASA_API_KEY", "aGYhKBDmeDfGFM2JkWg2lnCimJn5XgUmwM5UkB3d")
OWM_API_KEY = os.getenv("OWM_API_KEY", "0ab5dc524a2d5dc7f726017a2b98c687")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "c77748626e024b9b985f07e97826e4db")

@app.route("/")
def home():
    return jsonify({"message": "Gaia Eyes Backend is running!"})


# ------------------------
# SPACE WEATHER ENDPOINT
# ------------------------
@app.route("/space-weather")
def get_space_weather():
    try:
        # Example: NASA DONKI API for space weather alerts
        nasa_url = f"https://api.nasa.gov/DONKI/notifications?type=all&api_key={NASA_API_KEY}"
        nasa_response = requests.get(nasa_url)
        nasa_data = nasa_response.json()

        # Example: OpenWeatherMap current weather for a sample location (e.g., Boulder, CO)
        weather_url = f"https://api.openweathermap.org/data/2.5/weather?q=Boulder&appid={OWM_API_KEY}&units=metric"
        weather_response = requests.get(weather_url)
        weather_data = weather_response.json()

        return jsonify({
            "nasa_alerts": nasa_data,
            "sample_weather": weather_data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------------
# NEWS ENDPOINT
# ------------------------
@app.route("/news")
def get_news():
    print("DEBUG: /news endpoint hit!")  # Logs in Render console

    try:
        url = (
            f"https://newsapi.org/v2/everything?"
            f"q=(space%20weather%20OR%20solar%20flare%20OR%20geomagnetic%20storm%20OR%20extreme%20weather)&"
            f"language=en&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
        )
        response = requests.get(url)
        data = response.json()

        # Fallback if API fails or no articles
        if "articles" not in data:
            data = {
                "status": "error",
                "message": "NewsAPI returned no articles",
                "debug": data
            }

        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------------
# HEALTH CHECK (Optional)
# ------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ------------------------
# RENDER ENTRYPOINT
# ------------------------
if __name__ == "__main__":
    # Flask dev server for local testing
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
