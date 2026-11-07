"""Run the weather chatbot with --transport http or --transport stdio."""

import argparse
import asyncio
import json
import sys

import requests
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

SERVER_URL = "http://127.0.0.1:8000/mcp"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
CHAT_API_KEY = "YOUR_LLM_API_KEY"  # Enter your LLM provider's API key.
CHAT_MODEL = "YOUR_MODEL_ID"  # Select a model that supports tool calls.

def tool_schema(tool):
    """Read the input schema exposed by the installed MCP SDK."""
    if hasattr(tool, "input_schema"):
        return tool.input_schema
    return tool.inputSchema

def result_text(result):
    """Join the text content returned by the weather MCP tool."""
    return "\n".join(block.text for block in result.content if getattr(block, "type", None) == "text")

def read_stream_deltas(response):
    """Read text and tool fragments from the API's SSE data lines."""
    # A small chunk_size avoids buffering short replies before displaying them.
    for line in response.iter_lines(chunk_size=1, decode_unicode=True):
        if not line.startswith("data:"):
            continue  # Skip blank lines and keep-alive comments.
        data = line[5:].strip()
        if data == "[DONE]":
            return
        chunk = json.loads(data)
        if chunk.get("error"):
            raise RuntimeError(chunk["error"])
        for choice in chunk.get("choices", []):
            if choice.get("finish_reason") not in (None, "stop", "tool_calls"):
                raise RuntimeError(f"Incomplete model response: {choice['finish_reason']}")
            yield choice.get("delta", {})
    raise RuntimeError("The model response stream ended before [DONE].")


class MCPChatbot:
    """Own the MCP connection, LLM settings and conversation history."""

    def __init__(self, transport="http", *, server_url=SERVER_URL,
                 server_script="weather_mcp_server.py", api_url=CHAT_URL,
                 api_key=CHAT_API_KEY, model=CHAT_MODEL,
                 system_prompt=None):
        self.transport = transport
        self.api_url, self.api_key, self.model = api_url, api_key, model
        server = server_url if transport == "http" else StdioTransport(
            command=sys.executable,  # Use this Python environment for the subprocess.
            args=[server_script, "--transport", "stdio"],
            keep_alive=False,  # Close the subprocess when the client disconnects.
        )
        self.client = Client(server)
        self.available_tools = []
        self.messages = [{"role": "system", "content": system_prompt or (
            "You are a weather assistant. Use Australian English. "
            "Do not invent weather data. Ask for a city when it is missing."
        )}]

    def validate_settings(self):
        """Check the transport, API endpoint, API key and model before connecting."""
        if self.transport not in ("http", "stdio"):
            raise ValueError("Choose http or stdio for the MCP transport.")
        for name, value in (
            ("CHAT_URL", self.api_url),
            ("CHAT_API_KEY", self.api_key),
            ("CHAT_MODEL", self.model),
        ):
            if not isinstance(value, str) or not value.strip() or value.strip().startswith("YOUR_"):
                raise ValueError(f"Replace {name} before starting the chatbot.")
        if not self.api_url.startswith(("https://", "http://")):
            raise ValueError("CHAT_URL must be an HTTP or HTTPS API endpoint.")

    async def mcp_tools_to_llm(self):
        """Convert discovered MCP tools to the LLM's function declaration format."""
        tools = await self.client.list_tools()
        return [
            {"type": "function", "function": {
                "name": tool.name,
                "description": tool.description or tool.name,
                "parameters": tool_schema(tool),
            }}
            for tool in tools
        ]

    async def execute_tool(self, tool_name, tool_args):
        """Check the discovered tool name, invoke MCP and return text to the LLM."""
        tool_names = {tool["function"]["name"] for tool in self.available_tools}
        if tool_name not in tool_names:
            raise ValueError(f"Tool was not discovered on this server: {tool_name}")
        result = await self.client.call_tool(tool_name, tool_args)
        return result_text(result)

    async def connect_and_run(self):
        """Discover tools once and keep the MCP connection open for the chat."""
        self.validate_settings()
        async with self.client:
            self.available_tools = await self.mcp_tools_to_llm()
            tool_names = {tool["function"]["name"] for tool in self.available_tools}
            if not tool_names:
                raise ValueError("The server did not publish any tools.")
            print("Connected to server with tools:", sorted(tool_names))
            await self.chat_loop()

    def send_messages(self, messages):
        """Print streamed text and return the assembled assistant message."""
        # stream requests incremental responses from the model API.
        payload = {"model": self.model, "messages": messages, "tools": self.available_tools, "stream": True}
        message = {"role": "assistant", "content": ""}
        tool_calls = {}
        with requests.post(
            self.api_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            stream=True,  # Read the HTTP response incrementally.
            timeout=(10, 60),  # Connection timeout and wait between received data.
        ) as response:
            response.raise_for_status()
            response.encoding = "utf-8"
            for delta in read_stream_deltas(response):
                text = delta.get("content")
                if text:
                    if not message["content"]:
                        print("Assistant: ", end="", flush=True)
                    print(text, end="", flush=True)
                    message["content"] += text

                # Group fragments by index; parallel tool calls may be interleaved.
                for fragment in delta.get("tool_calls") or []:
                    index = fragment.get("index", 0)
                    if index not in tool_calls:
                        tool_calls[index] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    call = tool_calls[index]
                    for key, value in fragment.items():
                        if key not in ("index", "function"):
                            # Preserve provider metadata, including thought signatures.
                            call[key] = value
                    function = fragment.get("function") or {}
                    for key in ("name", "arguments"):
                        call["function"][key] += function.get(key) or ""
        if message["content"]:
            print(flush=True)
        if tool_calls:
            message["tool_calls"] = [tool_calls[index] for index in sorted(tool_calls)]
        return message

    async def chat(self, user_message: str) -> str:
        """Complete a chat turn, running requested tools through MCP."""
        pending = self.messages + [{"role": "user", "content": user_message}]
        while True:
            # Keep the MCP event loop responsive while requests reads the LLM stream.
            response = await asyncio.to_thread(self.send_messages, pending)
            pending.append(response)  # Preserve the text, tool calls and their IDs.
            if not response.get("tool_calls"):
                break  # A text answer with no tool calls completes the turn.
            for call in response["tool_calls"]:
                tool_name = call["function"]["name"]
                tool_args = json.loads(call["function"]["arguments"])  # Read the JSON arguments.
                print(f"Calling tool {tool_name} with args {tool_args}", flush=True)
                result = await self.execute_tool(tool_name, tool_args)  # Invoke the MCP tool.
                pending.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,  # Return the MCP text to the LLM.
                })

        self.messages = pending  # Save the complete turn after the requests succeed.
        return response["content"]

    async def chat_loop(self):
        """Read terminal input and complete turns until the user types quit."""
        print("\nMCP Chatbot Started!\n")
        print("Type your queries or 'quit' to exit.")
        while True:
            user_message = (await asyncio.to_thread(input, "You: ")).strip()
            if user_message.lower() == "quit":
                print("Chat ended.")
                return
            if user_message:
                await self.chat(user_message)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the weather MCP chatbot.")
    parser.add_argument("--transport", choices=("http", "stdio"), default="http")
    args = parser.parse_args()
    asyncio.run(MCPChatbot(transport=args.transport).connect_and_run())
