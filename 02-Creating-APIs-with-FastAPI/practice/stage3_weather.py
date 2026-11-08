# Teaching companion to Session 2: Creating APIs with FastAPI.

import requests
from fastapi import FastAPI

# Replace the placeholder with your WeatherAPI key.
WEATHER_API_KEY = "YOUR_WEATHERAPI_KEY"
CURRENT_WEATHER_URL = "https://api.weatherapi.com/v1/current.json"

# Replace the fixed-data prototype with a live weather application.
app = FastAPI(title="Live Weather API")


@app.get("/")
def root():
    """Describe the local service."""
    return {"message": "Weather API", "docs": "/docs"}


@app.get("/weather/")
def get_weather(city: str):
    """Return simplified weather for a city."""
    # key authenticates the request; q selects a location; aqi omits air-quality data.
    params = {"key": WEATHER_API_KEY, "q": city.strip(), "aqi": "no"}
    response = requests.get(
        CURRENT_WEATHER_URL,
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    # Flatten the location and current objects into one small record.
    return {
        "city": data["location"]["name"],
        "current_temp": data["current"]["temp_c"],
        "condition": data["current"]["condition"]["text"],
    }
