"""Explore weather resources and prompts from the terminal."""

import asyncio
import os
import shlex
import sys
from urllib.parse import quote

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import FastMCPError
from mcp import MCPError
from mcp.types import TextContent, TextResourceContents


async def handle_command(client: Client, query: str) -> str:
    """Translate a terminal command into a resource or prompt request."""
    if query.startswith("@"):
        city = query[1:].strip().lower()
        if not city:
            raise ValueError("Use @cities or enter a city such as @perth.")
        # The city is one URI segment. Encode any spaces or reserved characters.
        uri = "weather://cities" if city == "cities" else f"weather://sample/{quote(city, safe='')}"
        contents = await client.read_resource(uri)
        return "\n".join(block.text for block in contents if isinstance(block, TextResourceContents))

    command, *parts = shlex.split(query)
    if command == "/prompts" and not parts:
        prompts = await client.list_prompts()
        lines = []
        for prompt in prompts:
            arguments = [
                f"{arg.name}=VALUE" if arg.required else f"[{arg.name}=VALUE]"
                for arg in (prompt.arguments or [])
            ]
            lines.append(" ".join([prompt.name, *arguments]))
        return "\n".join(lines) or "The server has no prompts."

    if command == "/prompt" and parts:
        name, *assignments = parts
        arguments = {}
        for assignment in assignments:
            key, _, value = assignment.partition("=")
            if not key or not value or key in arguments:
                raise ValueError("Provide each prompt argument once as name=value.")
            arguments[key] = value

        # get_prompt returns rendered messages. Print the text parts with their roles.
        result = await client.get_prompt(name, arguments=arguments)
        return "\n".join(
            f"{message.role}: {message.content.text}"
            for message in result.messages if isinstance(message.content, TextContent)
        )

    raise ValueError("Use @cities, @<city>, /prompts or /prompt <name> <arg=value>.")


async def main():
    """Open one stdio client for the whole command loop."""
    server_script = os.path.join(os.path.dirname(__file__), "sample_weather_mcp_server.py")
    transport = StdioTransport(
        command=sys.executable, args=[server_script, "--transport", "stdio"], keep_alive=False,
    )
    print("Try @cities, @perth, /prompts or /prompt weather_briefing city=Perth. Type quit to exit.")
    async with Client(transport) as client:
        while True:
            try:
                query = (await asyncio.to_thread(input, "MCP> ")).strip()
            except EOFError:
                break
            if query.lower() == "quit":
                break
            if query:
                try:
                    print(await handle_command(client, query))
                except (ValueError, FastMCPError, MCPError) as error:
                    print(f"Could not complete the command. {error}")


if __name__ == "__main__":
    asyncio.run(main())
