"""FastAPI application: routing only. Logic lives in metrics.py and ai_analysis.py."""
import logging
from datetime import datetime, timezone

from fastapi import FastAPI

from app.ai_analysis import get_ai_analysis
from app.metrics import classify_status, collect_metrics

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Smart Server Health Diagnostics API",
    description="Live system metrics with an LLM-generated diagnostic summary.",
    version="1.0.0",
)


@app.get("/api/healthreport")
def health_report() -> dict:
    # Plain `def` (not async): FastAPI runs it in a threadpool, so the blocking
    # psutil/httpx calls don't freeze the event loop.
    metrics = collect_metrics()
    status = classify_status(metrics)
    ai_analysis = get_ai_analysis(metrics, status)
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "metrics": metrics,
        "ai_analysis": ai_analysis,
    }
