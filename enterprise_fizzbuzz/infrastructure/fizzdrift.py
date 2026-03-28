"""Enterprise FizzBuzz Platform - FizzDrift: Infrastructure Drift Detection"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzdrift import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzdrift")
EVENT_DRIFT = EventType.register("FIZZDRIFT_DETECTED")
FIZZDRIFT_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 206

class DriftSeverity(Enum):
    NONE = "none"; LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"
class DriftAction(Enum):
    NO_ACTION = "no_action"; ALERT = "alert"; AUTO_REMEDIATE = "auto_remediate"

@dataclass
class FizzDriftConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
@dataclass
class DriftItem:
    drift_id: str = ""; resource: str = ""; expected_value: Any = None
    actual_value: Any = None; severity: DriftSeverity = DriftSeverity.NONE
    detected_at: Optional[datetime] = None

class DriftDetector:
    def __init__(self, config: Optional[Any] = None) -> None:
        self._expected: Dict[str, Any] = {}
        self._drifts: OrderedDict[str, DriftItem] = OrderedDict()
    def register_expected(self, resource: str, expected_value: Any) -> None:
        self._expected[resource] = expected_value
    def record_actual(self, resource: str, actual_value: Any) -> Optional[DriftItem]:
        expected = self._expected.get(resource)
        if expected is None or expected == actual_value:
            return None
        severity = self._classify_severity(expected, actual_value)
        drift = DriftItem(drift_id=f"drift-{uuid.uuid4().hex[:8]}", resource=resource,
                          expected_value=expected, actual_value=actual_value,
                          severity=severity, detected_at=datetime.now(timezone.utc))
        self._drifts[drift.drift_id] = drift; return drift
    def detect_all(self) -> List[DriftItem]:
        return list(self._drifts.values())
    def get_drift_count(self) -> int:
        return len(self._drifts)
    def clear_drift(self, drift_id: str) -> bool:
        return self._drifts.pop(drift_id, None) is not None
    def _classify_severity(self, expected: Any, actual: Any) -> DriftSeverity:
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            pct = abs(expected - actual) / max(abs(expected), 1) * 100
            if pct > 50: return DriftSeverity.CRITICAL
            elif pct > 25: return DriftSeverity.HIGH
            elif pct > 10: return DriftSeverity.MEDIUM
            return DriftSeverity.LOW
        return DriftSeverity.MEDIUM

class RemediationEngine:
    def __init__(self) -> None:
        self._rules: Dict[str, DriftAction] = {}
    def add_rule(self, resource: str, action: DriftAction) -> None:
        self._rules[resource] = action
    def remediate(self, drift_item: DriftItem) -> Dict[str, Any]:
        action = self._rules.get(drift_item.resource, DriftAction.ALERT)
        return {"drift_id": drift_item.drift_id, "resource": drift_item.resource,
                "action": action.value, "applied": action != DriftAction.NO_ACTION}
    def list_rules(self) -> Dict[str, str]:
        return {k: v.value for k, v in self._rules.items()}

class FizzDriftDashboard:
    def __init__(self, detector: Optional[DriftDetector] = None,
                 remediator: Optional[RemediationEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._detector = detector; self._remediator = remediator; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzDrift Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZDRIFT_VERSION}"]
        if self._detector:
            drifts = self._detector.detect_all()
            lines.append(f"  Drifts: {len(drifts)}")
            for d in drifts[:5]:
                lines.append(f"  {d.resource}: {d.expected_value} -> {d.actual_value} [{d.severity.value}]")
        return "\n".join(lines)

class FizzDriftMiddleware(IMiddleware):
    def __init__(self, detector: Optional[DriftDetector] = None, dashboard: Optional[FizzDriftDashboard] = None) -> None:
        self._detector = detector; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzdrift"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"

def create_fizzdrift_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[DriftDetector, FizzDriftDashboard, FizzDriftMiddleware]:
    detector = DriftDetector()
    remediator = RemediationEngine()
    detector.register_expected("fizzbuzz.modules", 185)
    detector.register_expected("fizzbuzz.test_count", 25000)
    remediator.add_rule("fizzbuzz.modules", DriftAction.ALERT)
    remediator.add_rule("fizzbuzz.test_count", DriftAction.AUTO_REMEDIATE)
    dashboard = FizzDriftDashboard(detector, remediator, dashboard_width)
    middleware = FizzDriftMiddleware(detector, dashboard)
    logger.info("FizzDrift initialized: %d expected values", len(detector._expected))
    return detector, dashboard, middleware
