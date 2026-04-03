"""Prometheus-compatible metrics collector for TutorClaw."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Thread-safe metrics collector with Prometheus text and JSON output."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._gauges: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._histograms: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        self._histogram_bounds = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._descriptions: Dict[str, str] = {
            "tutor_workflow_duration_seconds": "Workflow execution duration",
            "tutor_workflow_errors_total": "Total workflow errors",
            "tutor_model_calls_total": "Total model API calls",
            "tutor_active_workflows": "Number of active workflows",
            "tutor_uptime_seconds": "Tutor uptime in seconds",
        }
        self._types: Dict[str, str] = {
            "tutor_workflow_duration_seconds": "histogram",
            "tutor_workflow_errors_total": "counter",
            "tutor_model_calls_total": "counter",
            "tutor_active_workflows": "gauge",
            "tutor_uptime_seconds": "gauge",
        }
        self._label_store: Dict[str, Dict[str, Dict[str, str]]] = defaultdict(dict)
        self._start_time = time.time()

        # Initialize built-in gauges
        self.gauge("tutor_uptime_seconds", 0)

    def counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        key = self._label_key(labels)
        with self._lock:
            self._counters[name][key] = self._counters[name].get(key, 0) + value
            self._label_store[name][key] = labels or {}
            self._types.setdefault(name, "counter")

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric."""
        key = self._label_key(labels)
        with self._lock:
            self._gauges[name][key] = value
            self._label_store[name][key] = labels or {}
            self._types.setdefault(name, "gauge")

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram observation."""
        key = self._label_key(labels)
        entry = (key, value, labels or {})
        with self._lock:
            self._histograms[name].append(entry)
            self._types.setdefault(name, "histogram")

    @staticmethod
    def _label_key(labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return ""
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))

    @staticmethod
    def _label_str(labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return ""
        pairs = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return "{" + pairs + "}"

    def format_prometheus(self) -> str:
        """Output metrics in Prometheus text exposition format."""
        lines: List[str] = []

        with self._lock:
            self.gauge("tutor_uptime_seconds", time.time() - self._start_time)
            all_names = list(dict.fromkeys(
                list(self._counters.keys()) +
                list(self._gauges.keys()) +
                list(self._histograms.keys())
            ))

            for name in all_names:
                mtype = self._types.get(name, "gauge")
                desc = self._descriptions.get(name, "")
                if desc:
                    lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} {mtype}")

                if mtype == "counter" and name in self._counters:
                    for key, val in self._counters[name].items():
                        lbl = "{" + key + "}" if key else ""
                        lines.append(f"{name}{lbl} {val}")
                elif mtype == "gauge" and name in self._gauges:
                    for key, val in self._gauges[name].items():
                        lbl = "{" + key + "}" if key else ""
                        lines.append(f"{name}{lbl} {val}")
                elif mtype == "histogram" and name in self._histograms:
                    for entry in self._histograms[name]:
                        key, val, labels = entry
                        lbl = "{" + key + "}" if key else ""
                        lines.append(f"{name}{lbl} {val}")
                lines.append("")

        return "\n".join(lines)

    def format_json(self) -> Dict[str, Any]:
        """Output metrics as a JSON-serializable dict."""
        with self._lock:
            self.gauge("tutor_uptime_seconds", time.time() - self._start_time)
            result: Dict[str, Any] = {
                "counters": {},
                "gauges": {},
                "histograms": {},
            }
            for name, vals in self._counters.items():
                result["counters"][name] = dict(vals)
            for name, vals in self._gauges.items():
                result["gauges"][name] = dict(vals)
            for name, entries in self._histograms.items():
                result["histograms"][name] = [
                    {"value": v} for _, v, _ in entries
                ]
            return result


# Module-level singleton
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get or create the global MetricsCollector singleton."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
