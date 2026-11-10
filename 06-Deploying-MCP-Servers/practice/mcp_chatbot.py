"""Chat loop adapted from Session 5 for Session 6's local practice files."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import requests


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
    """Own the model connection settings and manage a conversation."""

    def __init__(self, *, client, api_url, api_key, model, system_prompt):
        self.client = client
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.available_tools = []
        self.conversation = [{"role": "system", "content": system_prompt}]

    def validate_settings(self):
        """Validate the model settings before opening MCP connections."""
        for name, value in (("CHAT_API_KEY", self.api_key), ("CHAT_MODEL", self.model)):
            if not value or not value.strip() or value.strip().startswith("YOUR_"):
                raise ValueError(f"Replace {name} before starting the chatbot.")
        if not self.api_url.startswith(("https://", "http://")):
            raise ValueError("The model API URL must use HTTP or HTTPS.")

    async def list_tools_for_llm(self, client=None):
        """List MCP tools and convert them to the LLM's function format."""
        client = self.client if client is None else client
        tools = await client.list_tools()
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

    @asynccontextmanager
    async def connect_to_server(self, client=None, *, server_label=None):
        """Open one MCP client and discover its tools."""
        connection = self.client if client is None else client
        async with connection:
            if client is None:
                tools = self.available_tools = await self.list_tools_for_llm()
            else:
                tools = await self.list_tools_for_llm(client)
            tool_names = {tool["function"]["name"] for tool in tools}
            if not tool_names:
                raise ValueError("The server did not publish any tools.")
            server_info = connection.server_info
            server_name = server_info.name if server_info else "MCP server"
            label = f"{server_name} ({server_label})" if server_label else server_name
            print(f"Connected to {label} with tools: {sorted(tool_names)}", flush=True)
            yield tools  # Keep the client open until the caller leaves this context.

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
        pending = self.conversation + [{"role": "user", "content": user_message}]
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

        self.conversation = pending  # Save the complete turn after the requests succeed.
        return response["content"]

    async def chat_loop(self):
        """Read terminal input and let learners export the latest reply."""
        print("\nMCP Chatbot Started!\n")
        print("Type your question, '/save <path>' to save the latest reply, or 'quit' to exit.")
        latest_reply = ""
        while True:
            user_message = (await asyncio.to_thread(input, "You: ")).strip()
            if not user_message:
                continue
            if user_message.lower() == "quit":
                print("Chat ended.")
                return
            command, *arguments = user_message.split(maxsplit=1)
            if command == "/save":
                if not arguments:
                    print("Usage: /save <path>")
                elif not latest_reply.strip():
                    print("Generate a reply before saving.")
                else:
                    try:
                        path = Path(arguments[0]).expanduser()
                        with path.open("x", encoding="utf-8") as file:
                            file.write(latest_reply.rstrip("\n") + "\n")
                    except (OSError, RuntimeError) as error:
                        print(f"Could not save the reply. {error}")
                    else:
                        print(f"Reply saved to {path}")
                continue
            latest_reply = await self.chat(user_message)
