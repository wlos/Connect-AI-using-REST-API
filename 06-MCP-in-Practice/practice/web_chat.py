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
class BrowserSession:
    conversation: list[dict]
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Share two open MCP connections across the browser sessions."""
    app.state.password = os.environ.get("CHAT_ACCESS_PASSWORD", "")
    if os.environ.get("RENDER") and not app.state.password:
        raise ValueError("Set CHAT_ACCESS_PASSWORD before deploying the web chat.")
    bot = MultiServerChatbot()
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
    return FileResponse(os.path.join(PRACTICE_DIR, "index.html"), media_type="text/html")


@app.post("/chat", dependencies=[Depends(require_access)])
async def chat(body: ChatRequest, request: Request, response: Response):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Enter a question.")

    sessions = request.app.state.sessions
    session_id = request.cookies.get(SESSION_COOKIE)
    shared_bot = request.app.state.bot
    session = sessions.get(session_id)
    if session is None:
        session_id = secrets.token_urlsafe(32)
        session = BrowserSession(conversation=shared_bot.conversation.copy())

    # Serialise turns from the same browser while sharing the MCP clients.
    async with session.lock:
        bot = copy(shared_bot)
        bot.conversation = session.conversation
        try:
            reply = await bot.chat(message)
        except (FastMCPError, MCPError, requests.RequestException, RuntimeError, ValueError) as error:
            raise HTTPException(status_code=502, detail="The chatbot could not complete this turn.") from error
        session.conversation = bot.conversation
    sessions[session_id] = session
    response.set_cookie(
        SESSION_COOKIE, session_id, httponly=True, samesite="strict",
        secure=request.url.scheme == "https" or bool(os.environ.get("RENDER")),
    )
    response.headers["Cache-Control"] = "no-store"
    return {"reply": reply}
