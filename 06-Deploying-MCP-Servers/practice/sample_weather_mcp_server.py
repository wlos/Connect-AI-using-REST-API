"""Serve classroom weather samples or current WeatherAPI observations through MCP."""

import argparse
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.responses import PlainTextResponse

SAMPLE_FILE = Path(__file__).resolve().parents[1] / "sample_data" / "weather_samples.json"
CURRENT_WEATHER_URL = "https://api.weatherapi.com/v1/current.json"

mcp = FastMCP("Course Weather Server")
weather_api_key = ""


def load_samples() -> dict:
    """Read the bundled weather records."""
    with open(SAMPLE_FILE, encoding="utf-8") as file:
        return json.load(file)


def sample_weather(city: str) -> dict:
    """Load the course sample for a supported city."""
    samples = load_samples()
    key = city.strip().lower()
    if key not in samples:
        raise ValueError("Choose a city from the weather catalogue.")
    return {**samples[key], "source": "Course sample (simulated)"}


def current_weather(city: str, api_key: str) -> dict:
    """Fetch current conditions and return the fields used by the chatbot."""
    if not city.strip():
        raise ValueError("Enter a city name.")

    # Send the location and key to WeatherAPI over HTTPS.
    try:
        response = requests.get(
            CURRENT_WEATHER_URL, params={"key": api_key, "q": city.strip(), "aqi": "no"}, timeout=10
        )
        response.raise_for_status()
    except requests.RequestException:
        # Request errors can contain the URL and its API key.
        raise RuntimeError("WeatherAPI request failed. Check the city, API key and service status.") from None

    try:
        data = response.json()
        current = data["current"]
        return {
            "city": data["location"]["name"],
            "temperature_c": current["temp_c"],
            "conditions": current["condition"]["text"],
            "observed_at_local": current["last_updated"],
            "source": "WeatherAPI (current conditions)",
        }
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("WeatherAPI returned an unexpected response.") from None


@mcp.resource("weather://cities", mime_type="text/markdown")
def available_cities() -> str:
    """List the cities that have simulated weather records."""
    cities = [f"- {sample['city']} (`@{key}`)" for key, sample in sorted(load_samples().items())]
    return "\n".join(["# Available weather samples", "", *cities])


@mcp.resource("weather://sample/{city}", mime_type="application/json")
def weather_sample(city: str) -> dict:
    """Read the sample for a city through a resource URI."""
    return sample_weather(city)


@mcp.prompt()
def weather_briefing(city: str, audience: str = "event participants") -> str:
    """Prepare an activity briefing with a clear audience and output format."""
    return (
        f"Write a two-sentence weather briefing for {audience} in {city}. "
        f"\n1. Use the weather data supplied by the host or call get_weather(city={city!r}) "
        "if the tool is available. Ask for weather data if neither source is available."
        "\n2. State the temperature in degrees Celsius, the conditions and the source."
        "\n3. Suggest one practical preparation for the audience."
    )


@mcp.tool()
def get_weather(city: str) -> dict:
    """Get weather conditions and temperature in Celsius, with the data source."""
    if weather_api_key:
        return current_weather(city, weather_api_key)
    return sample_weather(city)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Give the hosting platform a lightweight HTTP health check."""
    return PlainTextResponse("OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("http", "stdio"), default="http")
    parser.add_argument("--live", action="store_true", help="Read current conditions from WeatherAPI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=os.environ.get("PORT", "8000"))
    args = parser.parse_args()
    if args.live:
        load_dotenv(Path(__file__).with_name(".env"))
        weather_api_key = os.environ.get("WEATHER_API_KEY", "").strip()
        if not weather_api_key or weather_api_key.startswith("YOUR_"):
            parser.error("Set WEATHER_API_KEY in the environment or practice/.env to use --live.")
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # Each HTTP request can be served independently by this read-only demo.
        mcp.run(transport="http", host=args.host, port=args.port, stateless_http=True)
