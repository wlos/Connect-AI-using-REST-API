"""Session 3-4 weather chatbot. Install requests, fill in the keys, then run this file."""

import json

import requests

CHAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
CHAT_API_KEY = "YOUR_GEMINI_API_KEY"
CHAT_MODEL = "gemini-3.6-flash"

# To use OpenRouter, replace the three settings above with these values.
# CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
# CHAT_API_KEY = "YOUR_OPENROUTER_API_KEY"
# CHAT_MODEL = "minimax/minimax-m3.1-flash:free"

WEATHER_API_KEY = "YOUR_WEATHERAPI_KEY"
CURRENT_WEATHER_URL = "https://api.weatherapi.com/v1/current.json"

def get_weather(city: str):
    """Return simplified weather for a city."""
    # key authenticates the request; q selects a location; aqi omits air-quality data.
    params = {"key": WEATHER_API_KEY, "q": city.strip(), "aqi": "no"}
    response = requests.get(
        CURRENT_WEATHER_URL,
        params=params,
        timeout=10,  # Maximum wait for the weather response, in seconds.
    )
    response.raise_for_status()
    data = response.json()

    # Flatten the location and current objects into one small record.
    return {
        "city": data["location"]["name"],
        "current_temp": data["current"]["temp_c"],
        "condition": data["current"]["condition"]["text"],
    }

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city in degrees Celsius. Not a forecast.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, such as Perth, Australia.",
                    }
                },
                "required": ["city"],
                "additionalProperties": False,
            },
        },
    }
]

mapping_tool_function = {
    "get_weather": get_weather,
}

def execute_tool(tool_name, tool_args):
    """Run a local tool and format its result as text for the model."""
    # Unpack the arguments and call the selected local function.
    result = mapping_tool_function[tool_name](**tool_args)
    if result is None:
        result = "The operation completed but didn't return any results."
    elif isinstance(result, list):
        result = ", ".join(str(item) for item in result)
    elif isinstance(result, dict):
        # Convert dictionaries to formatted JSON strings.
        result = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        result = str(result)
    return result

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

def chat(user_message: str) -> str:
    """Complete a chat turn, running any requested weather tools."""
    pending = conversation + [{"role": "user", "content": user_message}]
    while True:
        response = send_messages(pending)
        pending.append(response)  # Preserve the text, tool calls and their IDs.
        if not response.get("tool_calls"):
            break  # A text answer with no tool calls completes the turn.
        for call in response["tool_calls"]:
            tool_name = call["function"]["name"]
            tool_args = json.loads(call["function"]["arguments"])  # Read the JSON arguments.
            print(f"Calling tool {tool_name} with args {tool_args}", flush=True)
            result = execute_tool(tool_name, tool_args)  # Run the mapped Python function.
            pending.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result,  # execute_tool has already converted the result to text.
            })

    conversation[:] = pending  # Save the complete turn after the requests succeed.
    return response["content"]

system_prompt = (
    "You are a weather assistant. Use Australian English. "
    "Do not invent weather data. Ask for a city when it is missing."
)
conversation = [{"role": "system", "content": system_prompt}]

def main():
    """Read weather questions until the user enters quit."""
    if not CHAT_API_KEY or CHAT_API_KEY.startswith("YOUR_"):
        raise ValueError("Replace CHAT_API_KEY with your key before running.")
    if not WEATHER_API_KEY or WEATHER_API_KEY.startswith("YOUR_"):
        raise ValueError("Replace WEATHER_API_KEY with your key before running.")
    print("Weather chat started. Type quit to finish.")
    while True:
        user_content = input("You: ").strip()
        if user_content.lower() == "quit":
            print("Weather chat ended.")
            break
        if not user_content:
            continue
        chat(user_content)  # send_messages prints each text fragment as it arrives.


if __name__ == "__main__":
    main()
