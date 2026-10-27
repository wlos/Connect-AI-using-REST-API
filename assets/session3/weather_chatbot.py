"""Session 3-4 weather chatbot. Install requests, fill in the keys, then run this file."""

import json

import requests

CHAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
CHAT_API_KEY = "YOUR_GEMINI_API_KEY"  # Replace with your actual Gemini API key.
CHAT_MODEL = "gemini-3.8-flash"

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
        "name": "get_weather",
        "description": "Get current weather for a city in degrees Celsius. Not a forecast.",
        "input_schema": {
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
    }
]

mapping_tool_function = {
    "get_weather": get_weather,
}

def execute_tool(tool_name, tool_args):
    """Run the mapped Python function and print its inputs and result."""
    print(f"\n[Tool call] {tool_name}", flush=True)
    print(
        "[Tool arguments]",
        json.dumps(tool_args, ensure_ascii=False),
        flush=True,
    )

    # Unpack the arguments and call the selected local function.
    result = mapping_tool_function[tool_name](**tool_args)

    print(
        "[Tool result]",
        json.dumps(result, ensure_ascii=False, indent=2),
        flush=True,
    )
    return result

def send_messages(messages, tools=None, tool_choice="auto"):
    """Send a conversation with optional tools to the selected API."""
    payload = {"model": CHAT_MODEL, "messages": messages}
    if tools is not None:
        api_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],  # Use the API's field name.
                },
            }
            for tool in tools
        ]
        payload.update(tools=api_tools, tool_choice=tool_choice)
    response = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {CHAT_API_KEY}"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]

def chat(user_message: str) -> str:
    """Complete a chat turn, running any requested weather tools."""
    pending = conversation + [{"role": "user", "content": user_message}]
    response = send_messages(pending, tools=tools)
    pending.append(response)  # Preserve the full reply, including tool calls and their IDs.

    if response.get("tool_calls"):
        for call in response["tool_calls"]:
            tool_name = call["function"]["name"]
            tool_args = json.loads(call["function"]["arguments"])  # Read the JSON arguments.
            result = execute_tool(tool_name, tool_args)  # Run the mapped Python function.
            pending.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(result),
            })
        response = send_messages(pending, tools=tools, tool_choice="none")
        pending.append(response)

    conversation[:] = pending  # Save the complete turn after the requests succeed.
    return response["content"]

system_prompt = (
    "You are a friendly weather assistant. Use Australian English. "
    "Use get_weather for current observations and do not invent weather data. "
    "Ask for a city when it is missing. This tool does not provide forecasts."
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
        print("Assistant:", chat(user_content))


if __name__ == "__main__":
    main()
