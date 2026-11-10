"""Serve the Session 5 weather chatbot and its browser interface."""

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from copy import copy

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastmcp.exceptions import FastMCPError
from mcp import MCPError
from pydantic import BaseModel, Field

from chat_store import ChatStore
from weather_chatbot_with_resources import WeatherResourceChatbot, add_prompt_guide, handle_command

# Find files beside web_chat.py even if Python is launched from another folder.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BROWSER_COOKIE = "weather_chat_browser"
DEFAULT_DB = os.path.join(os.path.dirname(SCRIPT_DIR), "weather_chat_history.sqlite3")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    chat_id: str | None = Field(default=None, max_length=64)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Keep one MCP connection open while the web app is running."""
    server_script = os.path.join(SCRIPT_DIR, "weather_mcp_server_with_resources.py")
    bot = WeatherResourceChatbot(transport="stdio", server_script=server_script)
    app.state.store = ChatStore(os.environ.get("WEATHER_CHAT_DB", DEFAULT_DB))
    app.state.turn_lock = asyncio.Lock()
    # Start the MCP subprocess at startup and close it when FastAPI shuts down.
    async with bot.connect_to_server():
        app.state.bot = bot
        yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse(os.path.join(SCRIPT_DIR, "index.html"), media_type="text/html")


def browser_id_for(request: Request, response: Response) -> str:
    """Use a persistent cookie to find this browser's chats after a restart."""
    response.headers["Cache-Control"] = "no-store"
    browser_id = request.cookies.get(BROWSER_COOKIE)
    if not browser_id:
        # SQLite stores the chats. The cookie carries only their random browser ID.
        browser_id = secrets.token_urlsafe(32)
        response.set_cookie(BROWSER_COOKIE, browser_id, max_age=365 * 86400, httponly=True, samesite="strict")
    return browser_id


@app.get("/chats")
async def list_chats(request: Request, response: Response):
    browser_id = browser_id_for(request, response)
    return {"chats": request.app.state.store.list(browser_id)}


@app.get("/chats/{chat_id}")
async def read_chat(chat_id: str, request: Request, response: Response):
    browser_id = browser_id_for(request, response)
    # Match both IDs so a chat ID alone cannot open another browser's history.
    saved = request.app.state.store.read(browser_id, chat_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"title": saved["title"], "messages": saved["messages"]}


async def reply_to(bot: WeatherResourceChatbot, message: str) -> str:
    """Run the same MCP commands and model turns as the terminal client."""
    if message.startswith(("@", "/")):
        # Direct commands only need MCP. A rendered prompt can also go to the model.
        result = await handle_command(bot.client, message)
        if message.split(maxsplit=1)[0].lower() != "/prompt":
            return result
        try:
            bot.validate_settings()
        except ValueError as error:
            return f"{result}\n\n{error}"
        prompt = await add_prompt_guide(bot.client, message, result)
        return await bot.chat(prompt)

    bot.validate_settings()
    return await bot.chat(message)


@app.post("/chat")
async def chat(body: ChatRequest, request: Request, response: Response):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Enter a question or command.")

    browser_id = browser_id_for(request, response)
    store = request.app.state.store

    # This local app processes one turn at a time so two tabs cannot overwrite a chat.
    async with request.app.state.turn_lock:
        # Share the MCP connection while restoring the selected chat's model context.
        bot = copy(request.app.state.bot)
        chat_id = body.chat_id
        if chat_id is None:
            # Use the first message as the title. Save it only after a successful reply.
            chat_id = secrets.token_urlsafe(16)
            title = " ".join(message.split())
            title = title[:56] + "…" if len(title) > 56 else title
            messages = []
        else:
            saved = store.read(browser_id, chat_id)
            if saved is None:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            title = saved["title"]
            messages = saved["messages"]
            bot.conversation = saved["conversation"]
        try:
            reply = await reply_to(bot, message)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (FastMCPError, MCPError, RuntimeError, requests.RequestException) as error:
            raise HTTPException(status_code=502, detail="The chatbot could not complete this request.") from error
        # The transcript is shown in the browser. Model context also includes tool messages.
        messages.extend([
            {"role": "user", "text": message},
            {"role": "assistant", "text": reply},
        ])

        store.save(browser_id, chat_id, title, messages, bot.conversation)

    return {"chat_id": chat_id, "title": title, "reply": reply}


if __name__ == "__main__":
    # Pass the app directly so Uvicorn does not have to locate a module by name.
    uvicorn.run(app, host="127.0.0.1", port=8000)
