"""Serve WeatherAPI tools, reference resources and prompts through MCP."""

import argparse
import json
import os

from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.responses import PlainTextResponse

load_dotenv(Path(__file__).with_name(".env"))
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY") or "YOUR_WEATHERAPI_KEY"
CURRENT_WEATHER_URL = "https://api.weatherapi.com/v1/current.json"
mcp = FastMCP(name="Weather Server")


@mcp.tool()
def get_weather(city: str) -> dict:
    """Get current observed weather in degrees Celsius, not a forecast or history.

    Args:
        city: City name, such as Perth, Australia.
    """
    # key authenticates the request; q selects a location; aqi omits air-quality data.
    params = {"key": WEATHER_API_KEY, "q": city.strip(), "aqi": "no"}
    response = requests.get(CURRENT_WEATHER_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    return {
        "city": data["location"]["name"],
        "current_temp": data["current"]["temp_c"],
        "condition": data["current"]["condition"]["text"],
    }


FORECAST_WEATHER_URL = "https://api.weatherapi.com/v1/forecast.json"


def shape_daily_weather(data: dict) -> dict:
    """Keep the daily fields shared by forecast and history responses."""
    return {
        "city": data["location"]["name"],
        "days": [
            {"date": day["date"], "max": day["day"]["maxtemp_c"], "min": day["day"]["mintemp_c"]}
            for day in data["forecast"]["forecastday"]
        ],
    }


@mcp.tool()
def get_forecast(city: str, days: int = 1) -> dict:
    """Get a daily forecast for today and following days in Celsius, not history.

    Args:
        city: City name, such as Sydney, Australia.
        days: Number of forecast days, from one to three.
    """
    if not 1 <= days <= 3:
        raise ValueError("Choose one to three forecast days.")
    # days sets the forecast horizon; q selects a location.
    params = {"key": WEATHER_API_KEY, "q": city.strip(), "days": days}
    response = requests.get(FORECAST_WEATHER_URL, params=params, timeout=10)
    response.raise_for_status()
    return shape_daily_weather(response.json())

HISTORY_WEATHER_URL = "https://api.weatherapi.com/v1/history.json"


@mcp.tool()
def get_history(city: str, dt: str) -> dict:
    """Get recorded weather for a past date, subject to the WeatherAPI plan.

    Args:
        city: City name, such as Perth, Australia.
        dt: A past calendar date in YYYY-MM-DD format, not a forecast date.
    """
    history_date = date.fromisoformat(dt)  # Parse the YYYY-MM-DD input.
    params = {"key": WEATHER_API_KEY, "q": city.strip(), "dt": history_date.isoformat()}
    response = requests.get(HISTORY_WEATHER_URL, params=params, timeout=10)
    response.raise_for_status()
    return shape_daily_weather(response.json())


SAMPLE_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_data")
GUIDELINE_FILES = {
    "activity": "activity.md",
    "comfort": "comfort.md",
}


def load_reference_cities() -> dict:
    """Load the city records shared by both city resources."""
    with open(f"{SAMPLE_DATA_DIR}/reference_cities.json", encoding="utf-8") as source:
        return json.load(source)


@mcp.resource("weather://reference/cities", mime_type="text/markdown")
def reference_cities() -> str:
    """Return a catalogue of Australian reference cities."""
    header = """# Australian Reference Cities

| City | State | Climate | Coordinates |
|---|---|---|---|
"""
    cities = load_reference_cities()
    rows = [
        f"| {city['name']} | {city['state']} | {city['climate']} | {city['coordinates']} |"
        for city in cities.values()
    ]
    return header + "\n".join(rows)


@mcp.resource("weather://reference/cities/{city}", mime_type="text/markdown")
def reference_city(city: str) -> str:
    """Return the reference entry for one city."""
    cities = load_reference_cities()
    key = city.strip().lower()
    if key not in cities:
        raise ValueError("Choose a city from weather://reference/cities.")
    record = cities[key]
    return (
        f"# {record['name']}, {record['state']}\n\n"
        f"- Climate: {record['climate']}\n"
        f"- Coordinates: {record['coordinates']}"
    )


@mcp.resource("weather://reference/guidelines/{category}", mime_type="text/markdown")
def reference_guidelines(category: str) -> str:
    """Return a Markdown guide for the requested category."""
    key = category.strip().lower()
    if key not in GUIDELINE_FILES:
        raise ValueError("Choose activity or comfort.")
    # Map the category to a known file in the data directory.
    filename = GUIDELINE_FILES[key]
    with open(f"{SAMPLE_DATA_DIR}/{filename}", encoding="utf-8") as source:
        return source.read()


# ---------------------------------------------------------------------------
# 3. Prompts
# ---------------------------------------------------------------------------


@mcp.prompt()
def weather_briefing(city: str, audience: str = "general travellers") -> str:
    """Prepare an audience-tailored weather briefing using current observations and guidelines."""
    return (
        f"You are a weather specialist preparing a concise briefing for {audience} in {city}.\n"
        f"1. Call get_weather(city={city!r}) to inspect current observed temperatures and conditions.\n"
        "2. Consult weather://reference/guidelines/comfort for appropriate temperature thresholds.\n"
        "3. Deliver a concise 2-3 sentence briefing with practical attire and activity recommendations."
    )


@mcp.prompt()
def travel_weather_planner(destination: str, forecast_days: int = 3, activity_type: str = "sightseeing") -> str:
    """Prepare a multi-day itinerary plan based on forecast predictions and activity guidelines."""
    return (
        f"Plan an outdoor activity schedule for {activity_type} in {destination} over {forecast_days} days.\n"
        f"1. Call get_forecast(city={destination!r}, days={forecast_days}) to inspect daily forecasts.\n"
        "2. Consult weather://reference/guidelines/activity to evaluate outdoor weather suitability.\n"
        "3. Provide a structured day-by-day plan with optimal morning/afternoon timing."
    )


@mcp.prompt()
def weather_anomaly_check(city: str, past_date: str) -> str:
    """Evaluate whether current conditions deviate unusually from a historical date."""
    return (
        f"Conduct a weather comparison for {city} between today and {past_date}.\n"
        f"1. Call get_history(city={city!r}, dt={past_date!r}) to obtain historical baseline temperatures.\n"
        f"2. Call get_weather(city={city!r}) to obtain current temperatures today.\n"
        "3. Compare the two records, noting temperature differences and notable shifts in conditions."
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Give the hosting platform a lightweight HTTP health check."""
    return PlainTextResponse("OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("http", "stdio"), default="http")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=os.environ.get("PORT", "8000"))
    args = parser.parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="http", host=args.host, port=args.port, stateless_http=True)
