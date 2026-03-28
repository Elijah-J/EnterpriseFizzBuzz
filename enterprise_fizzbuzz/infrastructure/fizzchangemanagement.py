"""Enterprise FizzBuzz Platform - FizzChangeManagement: Formal Change Management"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzchangemanagement import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzchangemanagement")
EVENT_CHM = EventType.register("FIZZCHANGEMANAGEMENT_CREATED")
FIZZCHANGEMANAGEMENT_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 200

class ChangeType(Enum):
    STANDARD = "standard"; NORMAL = "normal"; EMERGENCY = "emergency"
class ChangeState(Enum):
    DRAFT = "draft"; SUBMITTED = "submitted"; APPROVED = "approved"
    REJECTED = "rejected"; IMPLEMENTING = "implementing"; COMPLETED = "completed"
    FAILED = "failed"; ROLLED_BACK = "rolled_back"
class RiskLevel(Enum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"

@dataclass
class FizzChangeManagementConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class ChangeRequest:
    cr_id: str = ""; title: str = ""; description: str = ""
    change_type: ChangeType = ChangeType.NORMAL
    state: ChangeState = ChangeState.DRAFT
    risk_level: RiskLevel = RiskLevel.LOW; requester: str = ""
    approvers: List[str] = field(default_factory=list)
    implementation_plan: str = ""; rollback_plan: str = ""
    created_at: Optional[datetime] = None; approved_at: Optional[datetime] = None

class ChangeManager:
    def __init__(self, config: Optional[Any] = None) -> None:
        self._changes: OrderedDict[str, ChangeRequest] = OrderedDict()
    def create(self, title: str, description: str, change_type: ChangeType,
               risk_level: RiskLevel, requester: str) -> ChangeRequest:
        cr = ChangeRequest(cr_id=f"CR-{uuid.uuid4().hex[:8]}", title=title,
                           description=description, change_type=change_type,
                           risk_level=risk_level, requester=requester,
                           state=ChangeState.DRAFT, created_at=datetime.now(timezone.utc))
        self._changes[cr.cr_id] = cr; return cr
    def submit(self, cr_id: str) -> ChangeRequest:
        cr = self.get(cr_id)
        if cr.state != ChangeState.DRAFT:
            raise FizzChangeManagementStateError(f"Cannot submit from {cr.state.value}")
        cr.state = ChangeState.SUBMITTED; return cr
    def approve(self, cr_id: str, approver: str = "") -> ChangeRequest:
        cr = self.get(cr_id)
        if cr.state != ChangeState.SUBMITTED:
            raise FizzChangeManagementStateError(f"Cannot approve from {cr.state.value}")
        cr.state = ChangeState.APPROVED; cr.approved_at = datetime.now(timezone.utc)
        if approver: cr.approvers.append(approver)
        return cr
    def reject(self, cr_id: str, reason: str = "") -> ChangeRequest:
        cr = self.get(cr_id)
        cr.state = ChangeState.REJECTED; return cr
    def implement(self, cr_id: str) -> ChangeRequest:
        cr = self.get(cr_id)
        if cr.state not in (ChangeState.APPROVED, ChangeState.SUBMITTED) and cr.change_type != ChangeType.EMERGENCY:
            raise FizzChangeManagementStateError(f"Cannot implement from {cr.state.value}")
        cr.state = ChangeState.IMPLEMENTING; return cr
    def complete(self, cr_id: str) -> ChangeRequest:
        cr = self.get(cr_id); cr.state = ChangeState.COMPLETED; return cr
    def rollback(self, cr_id: str) -> ChangeRequest:
        cr = self.get(cr_id); cr.state = ChangeState.ROLLED_BACK; return cr
    def get(self, cr_id: str) -> ChangeRequest:
        cr = self._changes.get(cr_id)
        if cr is None: raise FizzChangeManagementNotFoundError(cr_id)
        return cr
    def list_changes(self, state: Optional[ChangeState] = None) -> List[ChangeRequest]:
        if state is None: return list(self._changes.values())
        return [c for c in self._changes.values() if c.state == state]

class FizzChangeManagementDashboard:
    def __init__(self, manager: Optional[ChangeManager] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._manager = manager; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzChangeManagement Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZCHANGEMANAGEMENT_VERSION}"]
        if self._manager:
            changes = self._manager.list_changes()
            lines.append(f"  Changes: {len(changes)}")
            for cr in changes[-5:]:
                lines.append(f"  {cr.cr_id} [{cr.change_type.value}] {cr.state.value} {cr.risk_level.value} {cr.title}")
        return "\n".join(lines)

class FizzChangeManagementMiddleware(IMiddleware):
    def __init__(self, manager: Optional[ChangeManager] = None, dashboard: Optional[FizzChangeManagementDashboard] = None) -> None:
        self._manager = manager; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzchangemanagement"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"

def create_fizzchangemanagement_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[ChangeManager, FizzChangeManagementDashboard, FizzChangeManagementMiddleware]:
    manager = ChangeManager()
    cr = manager.create("Deploy FizzBuzz v2.0", "Major version upgrade with new evaluation algorithm",
                         ChangeType.NORMAL, RiskLevel.MEDIUM, "bob.mcfizzington")
    manager.submit(cr.cr_id)
    dashboard = FizzChangeManagementDashboard(manager, dashboard_width)
    middleware = FizzChangeManagementMiddleware(manager, dashboard)
    logger.info("FizzChangeManagement initialized: %d changes", len(manager.list_changes()))
    return manager, dashboard, middleware
