"""Central configuration. All secrets/settings come from environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()  # reads a local .env file if present (never commit it)

# --- LLM settings ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()  # groq | gemini | openai
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()  # optional; provider default used if empty
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "10"))

# --- Status thresholds (percent) ---
WARNING_THRESHOLD = float(os.getenv("WARNING_THRESHOLD", "70"))
CRITICAL_THRESHOLD = float(os.getenv("CRITICAL_THRESHOLD", "85"))
