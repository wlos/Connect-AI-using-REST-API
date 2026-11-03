"""Expose WeatherAPI through a local MCP server for Session 5."""

import requests
from fastmcp import FastMCP

WEATHER_API_KEY = "YOUR_WEATHERAPI_KEY"  # Replace with your WeatherAPI key.
CURRENT_WEATHER_URL = "https://api.weatherapi.com/v1/current.json"
mcp = FastMCP(name="Course Weather Server")


@mcp.tool()
def get_weather(city: str) -> dict:
    """Return simplified weather for a city using WeatherAPI.

    Args:
        city: A city name, such as Perth or Sydney; include the country if needed.
    """
    city = city.strip()
    if not city:
        raise ValueError("Enter a city name.")
    api_key = WEATHER_API_KEY.strip()
    if not api_key or api_key == "YOUR_WEATHERAPI_KEY":
        raise ValueError("Replace WEATHER_API_KEY in weather_mcp_server.py before calling get_weather.")

    # key authenticates the request; q selects a location; aqi omits air-quality data.
    params = {"key": api_key, "q": city, "aqi": "no"}
    response = requests.get(
        CURRENT_WEATHER_URL, params=params, timeout=10  # Wait up to 10 seconds.
    )
    response.raise_for_status()
    data = response.json()

    # Flatten the location and current objects into one small record.
    return {
        "city": data["location"]["name"],
        "current_temp": data["current"]["temp_c"],
        "condition": data["current"]["condition"]["text"],
    }


@mcp.resource("info://server-status", mime_type="text/plain")
def server_status() -> str:
    """Describe this server without making a weather request."""
    return "Course Weather Server. Data source: WeatherAPI. A key is needed for live weather."


@mcp.prompt()
def weather_briefing(city: str) -> str:
    """Prepare a reusable request for a short weather briefing."""
    return f"Use current weather for {city} to write a short briefing. Include the city, temperature and conditions."


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the course weather MCP server.")
    parser.add_argument(
        "--transport", choices=("http", "stdio"), default="http",
        help="Choose HTTP for separate terminals or stdio for a client-managed subprocess.",
    )
    args = parser.parse_args()
    if args.transport == "stdio":
        # Reserve stdout for protocol messages when connected through pipes.
        mcp.run(transport="stdio")
    else:
        # HTTP remains the default for the two-terminal lesson.
        mcp.run(
            transport="http",  # Use Streamable HTTP.
            host="127.0.0.1",  # Accept connections from this computer.
            port=8000,  # Serve MCP requests at http://127.0.0.1:8000/mcp.
        )
