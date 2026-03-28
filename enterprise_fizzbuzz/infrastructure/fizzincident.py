"""Enterprise FizzBuzz Platform - FizzIncident: Incident Management Lifecycle"""
from __future__ import annotations
import logging, time, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzincident import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzincident")
EVENT_INC = EventType.register("FIZZINCIDENT_CREATED")
FIZZINCIDENT_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 198

class IncidentSeverity(Enum):
    P1 = "P1"; P2 = "P2"; P3 = "P3"; P4 = "P4"
class IncidentState(Enum):
    OPEN = "open"; ACKNOWLEDGED = "acknowledged"; INVESTIGATING = "investigating"
    MITIGATED = "mitigated"; RESOLVED = "resolved"; CLOSED = "closed"

@dataclass
class FizzIncidentConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Incident:
    incident_id: str = ""; title: str = ""; description: str = ""
    severity: IncidentSeverity = IncidentSeverity.P3
    state: IncidentState = IncidentState.OPEN; assignee: str = ""
    created_at: Optional[datetime] = None; updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    timeline: List[Dict[str, Any]] = field(default_factory=list)

class IncidentManager:
    def __init__(self, config: Optional[Any] = None) -> None:
        self._incidents: OrderedDict[str, Incident] = OrderedDict()
    def create(self, title: str, description: str, severity: IncidentSeverity,
               assignee: str = "") -> Incident:
        now = datetime.now(timezone.utc)
        inc = Incident(incident_id=f"INC-{uuid.uuid4().hex[:8]}", title=title,
                       description=description, severity=severity, assignee=assignee,
                       created_at=now, state=IncidentState.OPEN)
        inc.timeline.append({"action": "created", "message": f"Incident created: {title}", "timestamp": now.isoformat(), "by": assignee})
        self._incidents[inc.incident_id] = inc; return inc
    def _transition(self, incident_id: str, new_state: IncidentState) -> Incident:
        inc = self.get(incident_id)
        now = datetime.now(timezone.utc)
        inc.state = new_state; inc.updated_at = now
        inc.timeline.append({"action": new_state.value, "message": f"State: {new_state.value}", "timestamp": now.isoformat()})
        if new_state == IncidentState.RESOLVED: inc.resolved_at = now
        return inc
    def acknowledge(self, incident_id: str) -> Incident:
        inc = self.get(incident_id)
        if inc.state != IncidentState.OPEN:
            raise FizzIncidentStateError(f"Cannot acknowledge from state {inc.state.value}")
        return self._transition(incident_id, IncidentState.ACKNOWLEDGED)
    def investigate(self, incident_id: str) -> Incident:
        return self._transition(incident_id, IncidentState.INVESTIGATING)
    def mitigate(self, incident_id: str) -> Incident:
        return self._transition(incident_id, IncidentState.MITIGATED)
    def resolve(self, incident_id: str) -> Incident:
        return self._transition(incident_id, IncidentState.RESOLVED)
    def close(self, incident_id: str) -> Incident:
        return self._transition(incident_id, IncidentState.CLOSED)
    def get(self, incident_id: str) -> Incident:
        inc = self._incidents.get(incident_id)
        if inc is None: raise FizzIncidentNotFoundError(incident_id)
        return inc
    def list_incidents(self, state: Optional[IncidentState] = None) -> List[Incident]:
        if state is None: return list(self._incidents.values())
        return [i for i in self._incidents.values() if i.state == state]
    def add_timeline_entry(self, incident_id: str, message: str) -> Incident:
        inc = self.get(incident_id)
        inc.timeline.append({"action": "note", "message": message,
                             "timestamp": datetime.now(timezone.utc).isoformat()})
        inc.updated_at = datetime.now(timezone.utc); return inc
    def get_mttr(self) -> float:
        resolved = [i for i in self._incidents.values() if i.resolved_at and i.created_at]
        if not resolved: return 0.0
        total = sum((i.resolved_at - i.created_at).total_seconds() for i in resolved)
        return total / len(resolved)

class FizzIncidentDashboard:
    def __init__(self, manager: Optional[IncidentManager] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._manager = manager; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzIncident Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZINCIDENT_VERSION}"]
        if self._manager:
            incs = self._manager.list_incidents()
            lines.append(f"  Incidents: {len(incs)}")
            lines.append(f"  MTTR: {self._manager.get_mttr():.0f}s")
            for i in incs[-5:]:
                lines.append(f"  {i.incident_id} [{i.severity.value}] {i.state.value} {i.title}")
        return "\n".join(lines)

class FizzIncidentMiddleware(IMiddleware):
    def __init__(self, manager: Optional[IncidentManager] = None, dashboard: Optional[FizzIncidentDashboard] = None) -> None:
        self._manager = manager; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzincident"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"

def create_fizzincident_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[IncidentManager, FizzIncidentDashboard, FizzIncidentMiddleware]:
    manager = IncidentManager()
    inc = manager.create("FizzBuzz Evaluation Latency Spike", "P99 latency exceeded SLA threshold",
                          IncidentSeverity.P2, "bob.mcfizzington")
    manager.acknowledge(inc.incident_id)
    dashboard = FizzIncidentDashboard(manager, dashboard_width)
    middleware = FizzIncidentMiddleware(manager, dashboard)
    logger.info("FizzIncident initialized: %d incidents", len(manager.list_incidents()))
    return manager, dashboard, middleware
