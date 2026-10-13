"""FastAPI web server: serves the chat UI and the JSON API behind it.

Run with:  uvicorn app.main:app --reload
"""

import logging
import os
import secrets

import anthropic
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import config
from app.chatbot import Chatbot
from app.database import Appointment, Handoff, make_session_factory
from app.knowledge import KnowledgeBase

logger = logging.getLogger("chatbot")

app = FastAPI(title=f"{config.BUSINESS_NAME} Support Bot")
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

session_factory = make_session_factory()
knowledge_base = KnowledgeBase.from_folder(config.KNOWLEDGE_DIR)
_bot: Chatbot | None = None


def get_bot() -> Chatbot:
    """Create the chatbot on first use, so the server still starts without an API key."""
    global _bot
    if _bot is None:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise HTTPException(503, "Chatbot is not configured: set ANTHROPIC_API_KEY in .env")
        _bot = Chatbot(
            anthropic.Anthropic(), knowledge_base, session_factory,
            business=config.BUSINESS_NAME, model=config.CLAUDE_MODEL, effort=config.CLAUDE_EFFORT,
        )
    return _bot


# ---------- Chat API ----------

class ChatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    actions: list[str]


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    bot = get_bot()
    try:
        result = bot.reply(req.session_id, req.message.strip())
    except anthropic.AuthenticationError:
        raise HTTPException(503, "The API key is invalid. Check ANTHROPIC_API_KEY in .env")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Lots of people are chatting right now. Please try again in a minute.")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "Couldn't reach the AI service. Check your internet connection.")
    except anthropic.APIStatusError as e:
        logger.exception("Claude API error (request id %s)", e.request_id)
        raise HTTPException(502, "The assistant had a problem. Please try again.")
    return ChatResponse(reply=result.text, actions=result.actions)


@app.post("/api/chat/reset")
def reset_chat(req: ChatRequest):
    if _bot is not None:
        _bot.reset(req.session_id)
    return {"ok": True}


# ---------- Admin API (for clinic staff) ----------

def require_admin(token: str | None) -> None:
    if not config.ADMIN_TOKEN or not token or not secrets.compare_digest(token, config.ADMIN_TOKEN):
        raise HTTPException(401, "Invalid admin token")


@app.get("/api/admin/appointments")
def list_appointments(x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    with session_factory() as db:
        rows = db.scalars(select(Appointment).order_by(Appointment.date, Appointment.time))
        return [
            {"id": a.id, "patient_name": a.patient_name, "phone": a.phone,
             "service": a.service, "date": a.date, "time": a.time}
            for a in rows
        ]


@app.get("/api/admin/handoffs")
def list_handoffs(x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    with session_factory() as db:
        rows = db.scalars(select(Handoff).order_by(Handoff.created_at.desc()))
        return [
            {"id": h.id, "contact": h.contact, "reason": h.reason, "summary": h.summary,
             "status": h.status, "created_at": h.created_at.isoformat(timespec="minutes")}
            for h in rows
        ]


# ---------- Pages ----------

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(config.STATIC_DIR / "admin.html")
