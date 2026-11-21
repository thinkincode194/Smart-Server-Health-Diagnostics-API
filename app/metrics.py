"""System metric collection and status classification (no LLM logic here)."""
import os
from typing import Dict

import psutil

from app.config import CRITICAL_THRESHOLD, WARNING_THRESHOLD

HEALTHY = "HEALTHY"
WARNING = "WARNING"
CRITICAL = "CRITICAL"

_SEVERITY = {HEALTHY: 0, WARNING: 1, CRITICAL: 2}


def collect_metrics() -> Dict[str, float]:
    """Collect live CPU, memory and disk utilisation (all in %)."""
    # interval=1 measures CPU over one second; interval=None would return 0.0 on first call.
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    # Root of the current drive: "/" on Linux/macOS, "C:\\" on Windows.
    disk = psutil.disk_usage(os.path.abspath(os.sep)).percent
    return {
        "cpu_percent": round(cpu, 1),
        "memory_percent": round(memory, 1),
        "disk_percent": round(disk, 1),
    }


def classify_value(value: float) -> str:
    """Classify a single percentage using the configured thresholds."""
    if value > CRITICAL_THRESHOLD:
        return CRITICAL
    if value > WARNING_THRESHOLD:
        return WARNING
    return HEALTHY


def classify_status(metrics: Dict[str, float]) -> str:
    """Overall status = the worst status among all metrics."""
    statuses = [classify_value(v) for v in metrics.values()]
    return max(statuses, key=lambda s: _SEVERITY[s])
