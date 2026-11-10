"""Connect to the weather HTTP server already running in Terminal 1."""

import asyncio
import json
from fastmcp import Client

SERVER_URL = "http://127.0.0.1:8000/mcp"

async def main():
    """Discover and call the weather tool over Streamable HTTP."""
    async with Client(SERVER_URL) as client:
        tools = await client.list_tools()  # Read the server's tool catalogue.
        for tool in tools:
            schema = tool.input_schema if hasattr(tool, "input_schema") else tool.inputSchema
            print(tool.name, json.dumps(schema, indent=2))
        result = await client.call_tool("get_weather", {"city": "Perth"})
        for block in result.content:
            if getattr(block, "type", None) == "text":
                print(block.text)

if __name__ == "__main__":
    asyncio.run(main())  # A terminal script owns its event loop.
