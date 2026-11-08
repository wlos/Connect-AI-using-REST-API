"""Run beside weather_mcp_server.py: python mcp_client_stdio.py.

The client starts the server as a subprocess and exchanges MCP messages over
stdin/stdout. Use --list-only to discover tools without calling WeatherAPI.
"""

import asyncio
import json
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

SERVER_SCRIPT = "weather_mcp_server.py"


async def main(list_only=False):
    """Start a stdio server subprocess, discover tools and request Perth weather."""
    transport = StdioTransport(
        command=sys.executable,  # Use the client's Python environment.
        args=[SERVER_SCRIPT, "--transport", "stdio"],
        keep_alive=False,  # Close the child process when the client disconnects.
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        for tool in tools:
            schema = tool.input_schema if hasattr(tool, "input_schema") else tool.inputSchema
            print(tool.name, json.dumps(schema, indent=2))
        if list_only:
            return

        result = await client.call_tool("get_weather", {"city": "Perth"})
        for block in result.content:
            if getattr(block, "type", None) == "text":
                print(block.text)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Call the weather MCP server over stdio.")
    parser.add_argument("--list-only", action="store_true", help="List tools without a weather request.")
    args = parser.parse_args()
    asyncio.run(main(list_only=args.list_only))
