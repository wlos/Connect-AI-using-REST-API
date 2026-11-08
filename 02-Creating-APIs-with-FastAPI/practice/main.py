# Teaching companion to Session 2: Creating APIs with FastAPI.

import requests
from fastapi import FastAPI

# Replace the placeholder with your WeatherAPI key.
WEATHER_API_KEY = "YOUR_WEATHERAPI_KEY"
CURRENT_WEATHER_URL = "https://api.weatherapi.com/v1/current.json"

from pydantic import BaseModel, Field


class WeatherResponse(BaseModel):
    city: str = Field(description="Resolved location name")
    current_temp: float = Field(description="Current temperature in degrees Celsius")
    condition: str = Field(description="Current weather description")

# Start the final application; Section 5 adds routes to this same object.
app = FastAPI(title="Weather and Research API", version="1.0.0")


@app.get("/")
def root():
    """Describe the service and link to its documentation."""
    return {"message": "Weather and Research API", "docs": "/docs"}


@app.get("/weather/", response_model=WeatherResponse)
def get_weather(
    city: str,
):
    """Retrieve current weather conditions."""
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
