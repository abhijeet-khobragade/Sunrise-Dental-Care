"""App settings, read from environment variables (or a .env file)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Sunrise Dental Care")
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
STATIC_DIR = BASE_DIR / "static"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'chatbot.db'}")

# Claude settings. Opus 5.5 gives the best answers; set CLAUDE_MODEL=claude-haiku-5-5
# in .env for a much cheaper (and faster) bot.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
# "low" keeps chat replies quick; raise to "medium"/"high" if answers feel shallow.
CLAUDE_EFFORT = os.getenv("CLAUDE_EFFORT", "low")

# Protects the /admin page. Change this before deploying anywhere public.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
