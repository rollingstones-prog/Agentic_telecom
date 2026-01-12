# app/core/config.py

from __future__ import annotations
import os

# -----------------------------
# Environment
# -----------------------------
ENV = os.getenv("ENV", "development")

# -----------------------------
# Redis configuration
# -----------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_KEY_PREFIX = "call"

# Redis TTL (seconds)
# How long call state stays in memory after last event
CALL_STATE_TTL_SECONDS = int(
    os.getenv("CALL_STATE_TTL_SECONDS", 60 * 60)  # 1 hour
)

# -----------------------------
# Retry / Healing policy (Day-1 minimal)
# -----------------------------
# NOTE:
# - These are *agentic decisions only*
# - No execution, no SIP actions here

MAX_RETRIES_DEFAULT = int(os.getenv("MAX_RETRIES_DEFAULT", 2))

# Per-error overrides (can be extended later)
RETRY_POLICY = {
    "NO_ANSWER": {
        "retry": True,
        "max_retries": 2,
    },
    "SIP_TIMEOUT": {
        "retry": True,
        "max_retries": 2,
    },
    "AUDIO_LOSS": {
        "retry": True,
        "max_retries": 1,
    },
    "BUSY": {
        "retry": False,
        "max_retries": 0,
    },
    "UNKNOWN": {
        "retry": False,
        "max_retries": 0,
    },
}

# -----------------------------
# API / Service behavior
# -----------------------------
# Defensive defaults to avoid infinite loops
ALLOW_DUPLICATE_EVENTS = False
STRICT_EVENT_VALIDATION = True

from dotenv import load_dotenv
load_dotenv()

# -----------------------------
# Agentic Keys (Day-6)
# -----------------------------
CREWAI_API_KEY = os.getenv("CREWAI_API_KEY", "")
REPLIT_API_KEY = os.getenv("REPLIT_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "") # Often needed by CrewAI
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL_NAME = os.getenv("ANTHROPIC_MODEL_NAME", "claude-3-5-sonnet-20240620")

# -----------------------------
# Logging
# -----------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
