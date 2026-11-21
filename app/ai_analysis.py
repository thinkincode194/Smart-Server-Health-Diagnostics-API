"""LLM integration: builds the prompt, calls the provider, parses the result.

Public entry point: get_ai_analysis(metrics, status). It NEVER raises - on any
failure (missing key, timeout, HTTP error, bad output) it returns a fallback.
"""
import json
import logging
import re
from typing import Dict, Optional

import httpx

from app import config

logger = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "groq": "openai/gpt-oss-20b",
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o-mini",
}

OPENAI_STYLE_URLS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
}
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = (
    "You are a concise server health diagnostics assistant. "
    "You reply with a single JSON object and nothing else."
)


def build_prompt(metrics: Dict[str, float], status: str) -> str:
    """Structured prompt that pins down the exact output format."""
    return (
        "Analyse these system health metrics.\n\n"
        f"Overall status: {status}\n"
        f"- CPU utilization: {metrics['cpu_percent']}%\n"
        f"- Memory utilization: {metrics['memory_percent']}%\n"
        f"- Disk utilization: {metrics['disk_percent']}%\n\n"
        f"Thresholds: above {config.WARNING_THRESHOLD:.0f}% is WARNING, "
        f"above {config.CRITICAL_THRESHOLD:.0f}% is CRITICAL.\n\n"
        "Return ONLY a JSON object with exactly these keys:\n"
        '  "summary": 1-2 plain-English sentences describing the current system state,\n'
        '  "recommendation": ONE practical action to fix or optimise the bottleneck. '
        "If the status is HEALTHY, say that no action is needed.\n"
        "No markdown, no code fences, no extra keys."
    )


# ---------- provider calls (each returns the raw text of the model reply) ----------

def _call_openai_style(provider: str, model: str, prompt: str) -> str:
    response = httpx.post(
        OPENAI_STYLE_URLS[provider],
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=config.LLM_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _call_gemini(model: str, prompt: str) -> str:
    response = httpx.post(
        GEMINI_URL.format(model=model),
        headers={"x-goog-api-key": config.LLM_API_KEY},
        json={
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        },
        timeout=config.LLM_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_llm(prompt: str) -> str:
    provider = config.LLM_PROVIDER
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"Unsupported LLM_PROVIDER '{provider}'")
    model = config.LLM_MODEL or DEFAULT_MODELS[provider]
    if provider == "gemini":
        return _call_gemini(model, prompt)
    return _call_openai_style(provider, model, prompt)


# ---------- parsing & fallback ----------

def parse_llm_output(raw: str) -> Dict[str, str]:
    """Extract {"summary", "recommendation"} from the model reply.

    Tolerates stray text/code fences by grabbing the first {...} block.
    Raises ValueError if the structure is not as expected.
    """
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM output")
    data = json.loads(match.group(0))
    summary = str(data.get("summary", "")).strip()
    recommendation = str(data.get("recommendation", "")).strip()
    if not summary or not recommendation:
        raise ValueError("LLM output missing 'summary' or 'recommendation'")
    return {"summary": summary, "recommendation": recommendation}


def fallback_analysis(reason: str) -> Dict[str, Optional[str]]:
    """Clean message returned when the LLM is unavailable. Raw metrics are still sent."""
    return {
        "summary": "AI analysis is currently unavailable. Please refer to the raw metrics and status above.",
        "recommendation": "Review the metrics manually; no AI recommendation could be generated.",
        "source": "fallback",
        "error": reason,
    }


def get_ai_analysis(metrics: Dict[str, float], status: str) -> Dict[str, Optional[str]]:
    """Return AI analysis, or a fallback if anything goes wrong. Never raises."""
    if not config.LLM_API_KEY:
        return fallback_analysis("LLM_API_KEY is not configured")

    try:
        raw = _call_llm(build_prompt(metrics, status))
        result = parse_llm_output(raw)
        return {**result, "source": "llm", "error": None}
    except httpx.TimeoutException:
        logger.warning("LLM request timed out")
        return fallback_analysis("LLM request timed out")
    except httpx.HTTPStatusError as exc:
        logger.warning("LLM returned HTTP %s", exc.response.status_code)
        return fallback_analysis(f"LLM API returned HTTP {exc.response.status_code}")
    except httpx.HTTPError as exc:
        logger.warning("LLM network error: %s", exc)
        return fallback_analysis("Could not reach the LLM API")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("Could not parse LLM output: %s", exc)
        return fallback_analysis("LLM returned an unexpected response format")
    except Exception as exc:  # last-resort safety net: the API must never crash
        logger.exception("Unexpected LLM error: %s", exc)
        return fallback_analysis("Unexpected error while calling the LLM")
