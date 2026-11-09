"""Serve reproducible sample weather through MCP."""

import argparse
import json
import os

from fastmcp import FastMCP
from starlette.responses import PlainTextResponse

SAMPLE_FILE = os.path.join(os.path.dirname(__file__), "..", "sample_data", "weather_samples.json")

mcp = FastMCP("Course Weather Server")


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
        f"\n1. Use the sample supplied by the host or call get_weather(city={city!r}) "
        "if the tool is available. Ask for the sample if neither source is available."
        "\n2. State the temperature in degrees Celsius and the conditions. Label both as simulated."
        "\n3. Suggest one practical preparation for the audience."
    )


@mcp.tool()
def get_weather(city: str) -> dict:
    """Get simulated weather for Perth or Sydney, including temperature and conditions."""
    return sample_weather(city)


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
        # Each HTTP request can be served independently by this read-only demo.
        mcp.run(transport="http", host=args.host, port=args.port, stateless_http=True)
