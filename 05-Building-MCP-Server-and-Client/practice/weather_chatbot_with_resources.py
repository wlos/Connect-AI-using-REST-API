"""Chat with the weather MCP server and try its resource and prompt commands."""

import asyncio
import os
import shlex
from urllib.parse import quote

import requests
from fastmcp import Client
from fastmcp.exceptions import FastMCPError
from mcp import MCPError
from mcp.types import TextContent, TextResourceContents

from mcp_chatbot import MCPChatbot

PROMPT_GUIDES = {
    "weather_briefing": "comfort",
    "travel_weather_planner": "activity",
}


async def handle_command(client: Client, query: str) -> str:
    """Translate a terminal command into an MCP resource, prompt, or tool request."""
    # Translate @aliases into resource URIs before reading them.
    if query.startswith("@"):
        target = query[1:].strip().lower()
        if not target:
            raise ValueError("Use @cities, @perth or @guidelines <activity|comfort>.")
        parts = target.split(maxsplit=1)
        if target == "cities":
            uri = "weather://reference/cities"
        elif parts[0] == "guidelines" and len(parts) == 2:
            category = quote(parts[1], safe="")
            uri = f"weather://reference/guidelines/{category}"
        elif len(parts) == 1 and target != "guidelines":
            city = quote(target, safe="")
            uri = f"weather://reference/cities/{city}"
        else:
            raise ValueError("Use @cities, @perth or @guidelines <activity|comfort>.")

        contents = await client.read_resource(uri)
        return "\n".join(block.text for block in contents if isinstance(block, TextResourceContents))

    elif query.startswith("/"):
        # Keep quoted multi-word argument values together.
        command, *parts = shlex.split(query)
        command = command.lower()
        if command == "/prompts" and not parts:
            prompts = await client.list_prompts()
            lines = []
            for prompt in prompts:
                arguments = [
                    f"{arg.name}=VALUE" if arg.required else f"[{arg.name}=VALUE]"
                    for arg in (prompt.arguments or [])
                ]
                lines.append(f"{prompt.name} " + " ".join(arguments))
            return "\n".join(lines) or "The server has no prompts."

        if command == "/prompt":
            if not parts:
                raise ValueError("Usage: /prompt <name> <arg1=value1> <arg2=value2>")
            name, *assignments = parts
            arguments = {}
            for assignment in assignments:
                key, _, value = assignment.partition("=")
                if not key or not value or key in arguments:
                    raise ValueError("Provide each prompt argument once as name=value.")
                arguments[key] = value

            result = await client.get_prompt(name, arguments=arguments)
            return "\n".join(
                message.content.text
                for message in result.messages if isinstance(message.content, TextContent)
            )

        # Keep direct tool discovery and calls available for comparison.
        if command == "/tools" and not parts:
            tools = await client.list_tools()
            lines = [f"{t.name}: {t.description}" for t in tools]
            return "\n".join(lines) or "The server has no tools."

        if command == "/call" and parts:
            tool_name, *assignments = parts
            arguments = {}
            for assignment in assignments:
                key, _, value = assignment.partition("=")
                if key in ("days", "max_results"):
                    arguments[key] = int(value)
                else:
                    arguments[key] = value
            call_res = await client.call_tool(tool_name, arguments)
            return str(call_res.data)

    raise ValueError(
        "Commands: @cities, @perth, @guidelines <category>, /prompts, "
        "/prompt <name> <arg=value>, /tools, /call <tool> <arg=value>"
    )


async def add_prompt_guide(client: Client, query: str, prompt: str) -> str:
    """Attach the reference guide requested by a rendered weather prompt."""
    name = shlex.split(query)[1]
    category = PROMPT_GUIDES.get(name)
    if category is None:
        return prompt
    guide = await handle_command(client, f"@guidelines {category}")
    return f"{prompt}\n\nReference guide:\n{guide}"


class WeatherResourceChatbot(MCPChatbot):
    """Add resource and prompt commands to the Section 5 chatbot."""

    async def chat_loop(self):
        """Route terminal commands before sending ordinary questions to the model."""
        print("\nMCP Chatbot Started!")
        print("Type your queries or 'quit' to exit.")
        print("Use @cities to list reference cities or @perth to read a city entry.")
        print("Use @guidelines <activity|comfort> to read a weather guide.")
        print("Use /prompts to list available prompts.")
        print("Use /prompt <name> <arg=value> to run a prompt.")
        print("Use /tools or /call <tool> <arg=value> to try tools directly.")

        while True:
            try:
                query = (await asyncio.to_thread(input, "\nQuery: ")).strip()
            except EOFError:
                break
            if not query:
                continue
            if query.lower() == "quit":
                break

            try:
                if query.startswith("@"):
                    print(await handle_command(self.client, query))
                elif query.startswith("/"):
                    command = query.split(maxsplit=1)[0].lower()
                    result = await handle_command(self.client, query)
                    print(result)
                    if command == "/prompt":
                        self.validate_settings()
                        await self.chat(await add_prompt_guide(self.client, query, result))
                else:
                    self.validate_settings()
                    await self.chat(query)
            except (ValueError, FastMCPError, MCPError, RuntimeError, requests.RequestException) as error:
                print(error)


async def main():
    """Open one stdio connection for commands and chat."""
    server_script = os.path.join(os.path.dirname(__file__), "weather_mcp_server_with_resources.py")
    chatbot = WeatherResourceChatbot(transport="stdio", server_script=server_script)
    async with chatbot.connect_to_server():
        await chatbot.chat_loop()


if __name__ == "__main__":
    asyncio.run(main())
