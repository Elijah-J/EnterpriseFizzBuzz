"""Enterprise FizzBuzz Platform - FizzComplianceV2: Compliance Automation"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzcompliancv2 import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzcompliancV2")
EVENT_COMP = EventType.register("FIZZCOMPLIANCV2_ASSESSED")
FIZZCOMPLIANCV2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 192

class Framework(Enum):
    SOC2 = "SOC2"; ISO27001 = "ISO27001"; PCI_DSS = "PCI_DSS"; NIST_800_53 = "NIST_800_53"
class ControlStatus(Enum):
    COMPLIANT = "compliant"; NON_COMPLIANT = "non_compliant"; PARTIAL = "partial"; NOT_ASSESSED = "not_assessed"

@dataclass
class FizzComplianceV2Config:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
@dataclass
class Control:
    control_id: str = ""; framework: Framework = Framework.SOC2; title: str = ""
    description: str = ""; status: ControlStatus = ControlStatus.NOT_ASSESSED
    evidence: List[str] = field(default_factory=list); last_assessed: Optional[datetime] = None

class ComplianceEngine:
    def __init__(self) -> None:
        self._controls: OrderedDict[str, Control] = OrderedDict()
    def add_control(self, control: Control) -> Control:
        self._controls[control.control_id] = control; return control
    def assess(self, control_id: str) -> Control:
        ctrl = self._controls.get(control_id)
        if ctrl is None: raise FizzComplianceV2ControlError(f"Not found: {control_id}")
        ctrl.last_assessed = datetime.now(timezone.utc)
        if ctrl.evidence: ctrl.status = ControlStatus.COMPLIANT
        elif ctrl.status == ControlStatus.NOT_ASSESSED: ctrl.status = ControlStatus.PARTIAL
        return ctrl
    def list_controls(self, framework: Optional[Framework] = None) -> List[Control]:
        if framework is None: return list(self._controls.values())
        return [c for c in self._controls.values() if c.framework == framework]
    def get_compliance_score(self, framework: Framework) -> float:
        controls = self.list_controls(framework)
        if not controls: return 0.0
        compliant = sum(1 for c in controls if c.status == ControlStatus.COMPLIANT)
        partial = sum(1 for c in controls if c.status == ControlStatus.PARTIAL)
        return (compliant + partial * 0.5) / len(controls)
    def collect_evidence(self, control_id: str, evidence: str) -> Control:
        ctrl = self._controls.get(control_id)
        if ctrl is None: raise FizzComplianceV2ControlError(f"Not found: {control_id}")
        ctrl.evidence.append(evidence); return ctrl
    def generate_report(self, framework: Framework) -> Dict[str, Any]:
        controls = self.list_controls(framework)
        return {"framework": framework.value, "controls": len(controls),
                "score": self.get_compliance_score(framework),
                "compliant": sum(1 for c in controls if c.status == ControlStatus.COMPLIANT),
                "non_compliant": sum(1 for c in controls if c.status == ControlStatus.NON_COMPLIANT)}

class FizzComplianceV2Dashboard:
    def __init__(self, engine: Optional[ComplianceEngine] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzComplianceV2 Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZCOMPLIANCV2_VERSION}"]
        if self._engine:
            for fw in Framework:
                controls = self._engine.list_controls(fw)
                if controls:
                    score = self._engine.get_compliance_score(fw)
                    lines.append(f"  {fw.value}: {len(controls)} controls, score={score:.0%}")
        return "\n".join(lines)

class FizzComplianceV2Middleware(IMiddleware):
    def __init__(self, engine: Optional[ComplianceEngine] = None, dashboard: Optional[FizzComplianceV2Dashboard] = None) -> None:
        self._engine = engine; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzcompliancv2"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"

def create_fizzcompliancv2_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[ComplianceEngine, FizzComplianceV2Dashboard, FizzComplianceV2Middleware]:
    engine = ComplianceEngine()
    engine.add_control(Control(control_id="SOC2-CC1.1", framework=Framework.SOC2,
                                title="Logical Access", status=ControlStatus.COMPLIANT, evidence=["rbac-config.json"]))
    engine.add_control(Control(control_id="SOC2-CC6.1", framework=Framework.SOC2,
                                title="Change Management", status=ControlStatus.PARTIAL))
    dashboard = FizzComplianceV2Dashboard(engine, dashboard_width)
    middleware = FizzComplianceV2Middleware(engine, dashboard)
    logger.info("FizzComplianceV2 initialized")
    return engine, dashboard, middleware
