"""Start the weather HTTP server in Terminal 1, then run python mcp_chatbot.py in Terminal 2."""

import json
from fastmcp import Client

SERVER_URL = "http://127.0.0.1:8000/mcp"

def tool_schema(tool):
    """Read the input schema exposed by the installed MCP SDK."""
    if hasattr(tool, "input_schema"):
        return tool.input_schema
    return tool.inputSchema

def result_text(result):
    """Join the text content returned by the weather MCP tool."""
    return "\n".join(block.text for block in result.content if getattr(block, "type", None) == "text")

import requests

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
CHAT_API_KEY = "YOUR_LLM_API_KEY"  # Use the same LLM API key as your earlier chatbot.
CHAT_MODEL = "YOUR_MODEL_ID"  # Select the same tool-capable model as before.
ALLOWED_TOOLS = {"get_weather"}

async def mcp_tools_to_function_declarations(client):
    """Convert discovered weather tools to the LLM's function declaration format."""
    discovered = await client.list_tools()
    return [
        {"type": "function", "function": {
            "name": tool.name,
            "description": tool.description or tool.name,
            "parameters": tool_schema(tool),
        }}
        for tool in discovered if tool.name in ALLOWED_TOOLS
    ]

async def execute_tool(client, tool_name, tool_args):
    """Call the weather server instead of looking up a local Python function."""
    if tool_name not in ALLOWED_TOOLS:
        raise ValueError("This tool is not enabled by the chatbot.")
    result = await client.call_tool(tool_name, tool_args)
    return result_text(result)

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


def send_messages(messages):
    """Print streamed text and return the assembled assistant message."""
    # stream requests incremental responses from the model API.
    payload = {"model": CHAT_MODEL, "messages": messages, "tools": tools, "stream": True}
    message = {"role": "assistant", "content": ""}
    tool_calls = {}
    with requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {CHAT_API_KEY}"},
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

import asyncio

async def chat(user_message: str, client) -> str:
    """Complete a chat turn, running requested tools through MCP."""
    pending = conversation + [{"role": "user", "content": user_message}]
    while True:
        # Keep the MCP event loop responsive while requests reads the LLM stream.
        response = await asyncio.to_thread(send_messages, pending)
        pending.append(response)  # Preserve the text, tool calls and their IDs.
        if not response.get("tool_calls"):
            break  # A text answer with no tool calls completes the turn.
        for call in response["tool_calls"]:
            tool_name = call["function"]["name"]
            tool_args = json.loads(call["function"]["arguments"])  # Read the JSON arguments.
            print(f"Calling tool {tool_name} with args {tool_args}", flush=True)
            result = await execute_tool(client, tool_name, tool_args)  # Invoke the MCP tool.
            pending.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result,  # The MCP result has been converted to text.
            })

    conversation[:] = pending  # Save the complete turn after the requests succeed.
    return response["content"]

async def mcp_chat():
    """Keep one weather MCP connection open for the conversation."""
    global tools, conversation
    if not CHAT_API_KEY or CHAT_API_KEY.startswith("YOUR_"):
        raise ValueError("Replace CHAT_API_KEY before starting the chatbot.")
    if not CHAT_MODEL or CHAT_MODEL.startswith("YOUR_"):
        raise ValueError("Replace CHAT_MODEL before starting the chatbot.")

    async with Client(SERVER_URL) as client:
        tools = await mcp_tools_to_function_declarations(client)
        if not tools:
            raise ValueError("The server did not publish the get_weather tool.")
        system_prompt = (
            "You are a weather assistant. Use Australian English. "
            "Do not invent weather data. Ask for a city when it is missing."
        )
        conversation = [{"role": "system", "content": system_prompt}]
        print("Weather chat started. Type quit to finish.")
        while True:
            user_content = (await asyncio.to_thread(input, "You: ")).strip()
            if user_content.lower() == "quit":
                print("Weather chat ended.")
                break
            if not user_content:
                continue
            await chat(user_content, client)  # Print the answer as streamed fragments arrive.

if __name__ == "__main__":
    # A terminal script owns its event loop.
    asyncio.run(mcp_chat())
