import httpx

from app import ai_analysis, config
from app.metrics import CRITICAL, HEALTHY, WARNING, classify_status


def m(cpu, mem, disk):
    return {"cpu_percent": cpu, "memory_percent": mem, "disk_percent": disk}


def test_classification():
    assert classify_status(m(10, 20, 30)) == HEALTHY
    assert classify_status(m(76.5, 68.2, 54)) == WARNING
    assert classify_status(m(10, 90, 30)) == CRITICAL
    assert classify_status(m(70, 70, 70)) == HEALTHY  # boundary: must be strictly greater


def test_parse_handles_code_fences():
    raw = '```json\n{"summary": "All good.", "recommendation": "No action needed."}\n```'
    assert ai_analysis.parse_llm_output(raw)["summary"] == "All good."


def test_missing_api_key_gives_fallback(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    result = ai_analysis.get_ai_analysis(m(1, 1, 1), HEALTHY)
    assert result["source"] == "fallback"


def test_timeout_gives_fallback(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "x")

    def boom(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(ai_analysis, "_call_llm", boom)
    result = ai_analysis.get_ai_analysis(m(1, 1, 1), HEALTHY)
    assert result["source"] == "fallback" and "timed out" in result["error"]


def test_bad_output_gives_fallback(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "x")
    monkeypatch.setattr(ai_analysis, "_call_llm", lambda p: "not json at all")
    assert ai_analysis.get_ai_analysis(m(1, 1, 1), HEALTHY)["source"] == "fallback"


def test_success_path(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "x")
    monkeypatch.setattr(
        ai_analysis, "_call_llm",
        lambda p: '{"summary": "CPU high.", "recommendation": "Check processes."}',
    )
    result = ai_analysis.get_ai_analysis(m(80, 10, 10), WARNING)
    assert result["source"] == "llm" and result["recommendation"] == "Check processes."
