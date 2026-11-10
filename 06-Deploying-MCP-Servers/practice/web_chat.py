"""Serve the multi-server chatbot through FastAPI."""

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from copy import copy
from dataclasses import dataclass, field

import requests
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastmcp.exceptions import FastMCPError
from mcp import MCPError
from pydantic import BaseModel, Field

from multi_server_chatbot import MultiServerChatbot, PRACTICE_DIR

SESSION_COOKIE = "mcp_practice_session"
DEMO_USER = "learner"
basic_auth = HTTPBasic(auto_error=False)


@dataclass
class Conversation:
    title: str
    messages: list[dict[str, str]]
    conversation: list[dict]


@dataclass
class BrowserSession:
    chats: dict[str, Conversation] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    chat_id: str | None = Field(default=None, max_length=64)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Share open MCP connections across the browser sessions."""
    app.state.password = os.environ.get("CHAT_ACCESS_PASSWORD", "")
    if os.environ.get("RENDER") and not app.state.password:
        raise ValueError("Set CHAT_ACCESS_PASSWORD before deploying the web chat.")
    bot = MultiServerChatbot(
        weather_url=os.environ.get("MCP_SERVER_URL", "").strip(),
        include_learn=os.environ.get("ENABLE_MICROSOFT_LEARN") == "1",
    )
    bot.validate_settings()
    async with bot.connect_to_servers():
        app.state.bot = bot
        app.state.sessions = {}
        yield


app = FastAPI(lifespan=lifespan)


def require_access(request: Request, credentials: HTTPBasicCredentials | None = Depends(basic_auth)):
    """Protect the deployed classroom demo and its LLM key with a shared password."""
    password = request.app.state.password
    if not password:
        return  # Allow local testing without a browser password.
    if (
        credentials is None
        or credentials.username != DEMO_USER
        or not secrets.compare_digest(credentials.password.encode(), password.encode())
    ):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", dependencies=[Depends(require_access)])
async def index():
    return FileResponse(PRACTICE_DIR / "index.html", media_type="text/html")


def browser_session(request: Request, response: Response) -> tuple[str, BrowserSession]:
    """Keep each browser's chats separate and private."""
    response.headers["Cache-Control"] = "no-store"
    sessions = request.app.state.sessions
    session_id = request.cookies.get(SESSION_COOKIE)
    session = sessions.get(session_id)
    if session is None:
        session_id = secrets.token_urlsafe(32)
        session = BrowserSession()
        response.set_cookie(
            SESSION_COOKIE, session_id, httponly=True, samesite="strict",
            secure=request.url.scheme == "https" or bool(os.environ.get("RENDER")),
        )
    return session_id, session


@app.get("/chats", dependencies=[Depends(require_access)])
async def list_chats(request: Request, response: Response):
    session_id, session = browser_session(request, response)
    request.app.state.sessions[session_id] = session
    return {"chats": [
        {"id": chat_id, "title": chat.title}
        for chat_id, chat in reversed(session.chats.items())
    ]}


@app.get("/chats/{chat_id}", dependencies=[Depends(require_access)])
async def read_chat(chat_id: str, request: Request, response: Response):
    session = request.app.state.sessions.get(request.cookies.get(SESSION_COOKIE))
    saved = session.chats.get(chat_id) if session else None
    if saved is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    response.headers["Cache-Control"] = "no-store"
    return {"title": saved.title, "messages": saved.messages}


@app.post("/chat", dependencies=[Depends(require_access)])
async def chat(body: ChatRequest, request: Request, response: Response):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Enter a question.")

    session_id, session = browser_session(request, response)
    # Serialise turns from the same browser while sharing the MCP clients.
    async with session.lock:
        bot = copy(request.app.state.bot)
        chat_id = body.chat_id
        if "chat_id" not in body.model_fields_set:
            # A request containing only a message continues the most recent chat.
            chat_id = next(reversed(session.chats), None)
        if chat_id is None:
            chat_id = secrets.token_urlsafe(16)
            title = " ".join(message.split())
            title = title[:56] + "…" if len(title) > 56 else title
            messages = []
        else:
            saved = session.chats.get(chat_id)
            if saved is None:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            title = saved.title
            messages = saved.messages
            bot.conversation = saved.conversation
        try:
            reply = await bot.chat(message)
        except (FastMCPError, MCPError, requests.RequestException, RuntimeError, ValueError) as error:
            raise HTTPException(status_code=502, detail="The chatbot could not complete this turn.") from error

        # Save the transcript and model context after a complete turn.
        session.chats.pop(chat_id, None)
        session.chats[chat_id] = Conversation(title, [
            *messages,
            {"role": "user", "text": message},
            {"role": "assistant", "text": reply},
        ], bot.conversation)
    request.app.state.sessions[session_id] = session
    return {"chat_id": chat_id, "title": title, "reply": reply}
