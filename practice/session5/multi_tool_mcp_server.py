"""Provide the multiple-tools practice functions through a stdio MCP server."""

import requests
from fastmcp import FastMCP

WEATHER_API_KEY = "YOUR_WEATHERAPI_KEY"  # Replace with your WeatherAPI key.
CURRENT_WEATHER_URL = "https://api.weatherapi.com/v1/current.json"
mcp = FastMCP(name="Weather and Research Server")


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


from datetime import date

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


import arxiv

# page_size limits each batch; delay_seconds spaces requests to arXiv.
arxiv_client = arxiv.Client(page_size=10, delay_seconds=3)


@mcp.tool()
def search_papers(query: str, max_results: int = 5) -> list[dict]:
    """Search arXiv for papers and return titles, summaries and source URLs.

    Args:
        query: Research topic or search terms.
        max_results: Maximum number of papers, from one to ten.
    """
    if not query.strip() or not 1 <= max_results <= 10:
        raise ValueError("Provide a topic and choose one to ten papers.")
    # all searches across fields; max_results limits the records returned.
    search = arxiv.Search(query=f"all:{query.strip()}", max_results=max_results)
    return [
        {"title": paper.title, "summary": paper.summary, "source_url": paper.entry_id}
        for paper in arxiv_client.results(search)
    ]


if __name__ == "__main__":
    # The chatbot launches this process and uses stdin/stdout for MCP messages.
    mcp.run(transport="stdio")
