"""
Enterprise FizzBuzz Platform - FizzTelemetry: Real User Monitoring & Error Tracking

Event tracking, error reporting, performance metrics, and session management
for frontend telemetry from FizzWindow and platform consumers.

Architecture reference: Sentry, Datadog RUM, Google Analytics, Prometheus client.
"""

from __future__ import annotations

import copy
import logging
import math
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizztelemetry import (
    FizzTelemetryError, FizzTelemetryEventError, FizzTelemetryErrorReportError,
    FizzTelemetrySessionError, FizzTelemetryPerformanceError,
    FizzTelemetryExportError, FizzTelemetryConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizztelemetry")

EVENT_TELEMETRY_RECORDED = EventType.register("FIZZTELEMETRY_RECORDED")
EVENT_TELEMETRY_ERROR = EventType.register("FIZZTELEMETRY_ERROR")

FIZZTELEMETRY_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 146


class EventCategory(Enum):
    PAGE_VIEW = "page_view"
    CLICK = "click"
    ERROR = "error"
    PERFORMANCE = "performance"
    CUSTOM = "custom"

class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FATAL = "fatal"


@dataclass
class FizzTelemetryConfig:
    sample_rate: float = 1.0
    max_events: int = 10000
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class TelemetryEvent:
    event_id: str = ""
    category: EventCategory = EventCategory.CUSTOM
    name: str = ""
    timestamp: Optional[datetime] = None
    user_id: str = ""
    session_id: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

@dataclass
class ErrorReport:
    error_id: str = ""
    message: str = ""
    stack_trace: str = ""
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    url: str = ""
    user_id: str = ""
    browser: str = ""
    os: str = ""
    count: int = 1
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


# ============================================================
# Telemetry Collector
# ============================================================

class TelemetryCollector:
    """Collects telemetry events and error reports."""

    def __init__(self, config: Optional[FizzTelemetryConfig] = None) -> None:
        self._config = config or FizzTelemetryConfig()
        self._events: List[TelemetryEvent] = []
        self._errors: List[ErrorReport] = []
        self._error_fingerprints: Dict[str, ErrorReport] = {}

    def record(self, event: TelemetryEvent) -> TelemetryEvent:
        if not event.event_id:
            event.event_id = f"evt-{uuid.uuid4().hex[:8]}"
        if not event.timestamp:
            event.timestamp = datetime.now(timezone.utc)
        self._events.append(event)
        # Trim if over limit
        if len(self._events) > self._config.max_events:
            self._events = self._events[-self._config.max_events:]
        return event

    def record_error(self, message: str, stack_trace: str = "",
                     severity: ErrorSeverity = ErrorSeverity.MEDIUM,
                     url: str = "", user_id: str = "") -> ErrorReport:
        # Deduplicate by message fingerprint
        fingerprint = message.strip()
        now = datetime.now(timezone.utc)

        if fingerprint in self._error_fingerprints:
            report = self._error_fingerprints[fingerprint]
            report.count += 1
            report.last_seen = now
            return report

        report = ErrorReport(
            error_id=f"err-{uuid.uuid4().hex[:8]}",
            message=message, stack_trace=stack_trace,
            severity=severity, url=url, user_id=user_id,
            browser="FizzBrowser/1.0", os="FizzOS/1.0",
            count=1, first_seen=now, last_seen=now,
        )
        self._errors.append(report)
        self._error_fingerprints[fingerprint] = report
        return report

    def get_events(self, limit: int = 100) -> List[TelemetryEvent]:
        return self._events[-limit:]

    def get_errors(self, limit: int = 100) -> List[ErrorReport]:
        return self._errors[-limit:]

    def get_event_count(self) -> int:
        return len(self._events)

    def get_error_count(self) -> int:
        return len(self._errors)


# ============================================================
# Performance Tracker
# ============================================================

class PerformanceTracker:
    """Tracks performance timings and computes percentiles."""

    def __init__(self) -> None:
        self._timings: Dict[str, List[float]] = defaultdict(list)

    def record_timing(self, name: str, duration_ms: float, url: str = "") -> None:
        self._timings[name].append(duration_ms)

    def get_percentiles(self, name: str) -> Dict[str, float]:
        values = sorted(self._timings.get(name, []))
        if not values:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        return {
            "p50": self._percentile(values, 50),
            "p95": self._percentile(values, 95),
            "p99": self._percentile(values, 99),
        }

    def get_web_vitals(self) -> Dict[str, float]:
        """Return Core Web Vitals metrics (simulated)."""
        return {
            "LCP": self._percentile(sorted(self._timings.get("lcp", [100.0])), 75),
            "FID": self._percentile(sorted(self._timings.get("fid", [10.0])), 75),
            "CLS": 0.05,
            "TTFB": self._percentile(sorted(self._timings.get("ttfb", [50.0])), 75),
        }

    def _percentile(self, sorted_values: List[float], pct: int) -> float:
        if not sorted_values:
            return 0.0
        idx = max(0, min(len(sorted_values) - 1, int(math.ceil(pct / 100.0 * len(sorted_values)) - 1)))
        return sorted_values[idx]


# ============================================================
# Session Tracker
# ============================================================

class SessionTracker:
    """Tracks user sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def start_session(self, user_id: str) -> str:
        session_id = f"ses-{uuid.uuid4().hex[:8]}"
        self._sessions[session_id] = {
            "user_id": user_id,
            "started_at": datetime.now(timezone.utc),
            "active": True,
            "events": 0,
        }
        return session_id

    def end_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id]["active"] = False

    def get_active_sessions(self) -> int:
        return sum(1 for s in self._sessions.values() if s.get("active", False))

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self._sessions.get(session_id, {})


# ============================================================
# Dashboard & Middleware
# ============================================================

class FizzTelemetryDashboard:
    def __init__(self, collector: Optional[TelemetryCollector] = None,
                 perf: Optional[PerformanceTracker] = None,
                 sessions: Optional[SessionTracker] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._collector = collector
        self._perf = perf
        self._sessions = sessions
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzTelemetry Real User Monitoring".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZTELEMETRY_VERSION}",
        ]
        if self._collector:
            lines.append(f"  Events:   {self._collector.get_event_count()}")
            lines.append(f"  Errors:   {self._collector.get_error_count()}")
        if self._sessions:
            lines.append(f"  Sessions: {self._sessions.get_active_sessions()}")
        if self._perf:
            vitals = self._perf.get_web_vitals()
            lines.append(f"  LCP: {vitals['LCP']:.0f}ms  FID: {vitals['FID']:.0f}ms  CLS: {vitals['CLS']:.2f}")
        return "\n".join(lines)


class FizzTelemetryMiddleware(IMiddleware):
    def __init__(self, collector: Optional[TelemetryCollector] = None,
                 dashboard: Optional[FizzTelemetryDashboard] = None) -> None:
        self._collector = collector
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizztelemetry"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzTelemetry not initialized"


# ============================================================
# Factory
# ============================================================

def create_fizztelemetry_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[TelemetryCollector, FizzTelemetryDashboard, FizzTelemetryMiddleware]:
    config = FizzTelemetryConfig(dashboard_width=dashboard_width)
    collector = TelemetryCollector(config)
    perf = PerformanceTracker()
    sessions = SessionTracker()

    # Seed some default telemetry
    collector.record(TelemetryEvent(category=EventCategory.PAGE_VIEW, name="fizzbuzz_home",
                                     user_id="bob", session_id="ses-init"))
    collector.record(TelemetryEvent(category=EventCategory.CLICK, name="evaluate_button",
                                     user_id="bob", session_id="ses-init"))
    perf.record_timing("page_load", 120.0, "/")
    perf.record_timing("api_response", 45.0, "/api/fizzbuzz/15")
    perf.record_timing("lcp", 150.0)
    perf.record_timing("fid", 12.0)
    perf.record_timing("ttfb", 55.0)
    sessions.start_session("bob")

    dashboard = FizzTelemetryDashboard(collector, perf, sessions, dashboard_width)
    middleware = FizzTelemetryMiddleware(collector, dashboard)

    logger.info("FizzTelemetry initialized: %d events, %d errors", collector.get_event_count(), collector.get_error_count())
    return collector, dashboard, middleware
