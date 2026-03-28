"""Enterprise FizzBuzz Platform - FizzRunbook: Runbook Automation Engine"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzrunbook import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzrunbook")
EVENT_RUNBOOK = EventType.register("FIZZRUNBOOK_EXECUTED")
FIZZRUNBOOK_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 211


class StepType(Enum):
    MANUAL = "manual"
    AUTOMATED = "automated"
    CONDITIONAL = "conditional"
    NOTIFICATION = "notification"


class ExecutionState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RunbookStatus(Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


@dataclass
class RunbookStep:
    """A single step within a runbook definition."""
    step_id: str = ""
    name: str = ""
    step_type: StepType = StepType.AUTOMATED
    description: str = ""
    timeout_seconds: int = 300
    on_failure: str = "abort"


@dataclass
class RunbookDefinition:
    """A versioned runbook consisting of ordered steps."""
    runbook_id: str = ""
    name: str = ""
    description: str = ""
    status: RunbookStatus = RunbookStatus.DRAFT
    steps: List[RunbookStep] = field(default_factory=list)
    version: int = 1


@dataclass
class ExecutionRecord:
    """Tracks the state of a single runbook execution."""
    execution_id: str = ""
    runbook_id: str = ""
    state: ExecutionState = ExecutionState.PENDING
    current_step_index: int = 0
    step_results: List[dict] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class FizzRunbookConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class RunbookEngine:
    """Manages runbook definitions, step sequencing, execution lifecycle,
    and human-in-the-loop approval gates for operational remediation."""

    def __init__(self) -> None:
        self._runbooks: OrderedDict[str, RunbookDefinition] = OrderedDict()
        self._executions: OrderedDict[str, ExecutionRecord] = OrderedDict()

    def create_runbook(self, name: str, description: str = "") -> RunbookDefinition:
        """Create a new runbook in DRAFT status."""
        runbook_id = f"runbook-{uuid.uuid4().hex[:8]}"
        runbook = RunbookDefinition(
            runbook_id=runbook_id,
            name=name,
            description=description,
            status=RunbookStatus.DRAFT,
        )
        self._runbooks[runbook_id] = runbook
        logger.debug("Created runbook %s: %s", runbook_id, name)
        return runbook

    def add_step(self, runbook_id: str, name: str, step_type: StepType,
                 description: str = "", timeout_seconds: int = 300,
                 on_failure: str = "abort") -> RunbookStep:
        """Add a step to an existing runbook."""
        runbook = self.get_runbook(runbook_id)
        if runbook.status != RunbookStatus.DRAFT:
            raise FizzRunbookStateError(
                f"Cannot add steps to {runbook.status.value} runbook {runbook_id}"
            )
        step = RunbookStep(
            step_id=f"step-{uuid.uuid4().hex[:8]}",
            name=name,
            step_type=step_type,
            description=description,
            timeout_seconds=timeout_seconds,
            on_failure=on_failure,
        )
        runbook.steps.append(step)
        return step

    def publish(self, runbook_id: str) -> RunbookDefinition:
        """Publish a runbook, making it available for execution."""
        runbook = self.get_runbook(runbook_id)
        if runbook.status != RunbookStatus.DRAFT:
            raise FizzRunbookStateError(
                f"Only DRAFT runbooks can be published, current: {runbook.status.value}"
            )
        runbook.status = RunbookStatus.PUBLISHED
        logger.info("Published runbook %s: %s", runbook_id, runbook.name)
        return runbook

    def get_runbook(self, runbook_id: str) -> RunbookDefinition:
        """Retrieve a runbook by its ID."""
        runbook = self._runbooks.get(runbook_id)
        if runbook is None:
            raise FizzRunbookNotFoundError(runbook_id)
        return runbook

    def list_runbooks(self) -> List[RunbookDefinition]:
        """Return all runbook definitions."""
        return list(self._runbooks.values())

    def execute(self, runbook_id: str) -> ExecutionRecord:
        """Begin executing a published runbook. AUTOMATED steps run immediately;
        MANUAL steps pause execution in AWAITING_APPROVAL state."""
        runbook = self.get_runbook(runbook_id)
        if runbook.status != RunbookStatus.PUBLISHED:
            raise FizzRunbookStateError(
                f"Only PUBLISHED runbooks can be executed, current: {runbook.status.value}"
            )
        execution = ExecutionRecord(
            execution_id=f"exec-{uuid.uuid4().hex[:8]}",
            runbook_id=runbook_id,
            state=ExecutionState.RUNNING,
            current_step_index=0,
            started_at=datetime.utcnow().isoformat(),
        )
        self._executions[execution.execution_id] = execution
        self._advance_execution(execution, runbook)
        return execution

    def _advance_execution(self, execution: ExecutionRecord, runbook: RunbookDefinition) -> None:
        """Advance execution through steps until a MANUAL step or completion."""
        while execution.current_step_index < len(runbook.steps):
            step = runbook.steps[execution.current_step_index]
            if step.step_type == StepType.MANUAL:
                execution.state = ExecutionState.AWAITING_APPROVAL
                logger.debug("Execution %s awaiting approval at step %s",
                             execution.execution_id, step.name)
                return
            # AUTOMATED, CONDITIONAL, NOTIFICATION steps execute immediately
            execution.step_results.append({
                "step_id": step.step_id,
                "step_name": step.name,
                "status": "completed",
                "step_type": step.step_type.value,
            })
            execution.current_step_index += 1
        # All steps completed
        execution.state = ExecutionState.COMPLETED
        execution.completed_at = datetime.utcnow().isoformat()
        logger.info("Execution %s completed", execution.execution_id)

    def approve_step(self, execution_id: str) -> ExecutionRecord:
        """Approve the current manual step, advancing execution past the gate."""
        execution = self.get_execution(execution_id)
        if execution.state != ExecutionState.AWAITING_APPROVAL:
            raise FizzRunbookStateError(
                f"Execution {execution_id} is not awaiting approval, "
                f"current state: {execution.state.value}"
            )
        runbook = self.get_runbook(execution.runbook_id)
        step = runbook.steps[execution.current_step_index]
        execution.step_results.append({
            "step_id": step.step_id,
            "step_name": step.name,
            "status": "approved",
            "step_type": step.step_type.value,
        })
        execution.current_step_index += 1
        execution.state = ExecutionState.RUNNING
        self._advance_execution(execution, runbook)
        return execution

    def get_execution(self, execution_id: str) -> ExecutionRecord:
        """Retrieve an execution record by ID."""
        execution = self._executions.get(execution_id)
        if execution is None:
            raise FizzRunbookNotFoundError(execution_id)
        return execution

    def list_executions(self) -> List[ExecutionRecord]:
        """Return all execution records."""
        return list(self._executions.values())


class FizzRunbookDashboard:
    def __init__(self, engine: Optional[RunbookEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzRunbook Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZRUNBOOK_VERSION}"]
        if self._engine:
            runbooks = self._engine.list_runbooks()
            executions = self._engine.list_executions()
            lines.append(f"  Runbooks: {len(runbooks)}")
            lines.append(f"  Executions: {len(executions)}")
            lines.append("-" * self._width)
            for r in runbooks[:10]:
                lines.append(f"  {r.name:<30} [{r.status.value}] {len(r.steps)} steps")
            if executions:
                lines.append("-" * self._width)
                for e in executions[:5]:
                    lines.append(f"  {e.execution_id}  [{e.state.value}]  step {e.current_step_index}")
        return "\n".join(lines)


class FizzRunbookMiddleware(IMiddleware):
    def __init__(self, engine: Optional[RunbookEngine] = None,
                 dashboard: Optional[FizzRunbookDashboard] = None) -> None:
        self._engine = engine
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzrunbook"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzrunbook_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[RunbookEngine, FizzRunbookDashboard, FizzRunbookMiddleware]:
    """Factory function that creates and wires the FizzRunbook subsystem."""
    engine = RunbookEngine()
    # Create a sample runbook for cache invalidation remediation
    rb = engine.create_runbook("Cache Invalidation Recovery",
                               "Standard procedure for recovering from cache coherence failures")
    engine.add_step(rb.runbook_id, "Verify cache state", StepType.AUTOMATED,
                    "Query MESI coherence protocol for inconsistent cache lines")
    engine.add_step(rb.runbook_id, "Operator approval", StepType.MANUAL,
                    "Operator must confirm cache flush before proceeding")
    engine.add_step(rb.runbook_id, "Flush invalidated entries", StepType.AUTOMATED,
                    "Execute selective cache eviction for affected keys")
    engine.add_step(rb.runbook_id, "Notify stakeholders", StepType.NOTIFICATION,
                    "Send recovery completion notification to SRE channel")
    engine.publish(rb.runbook_id)

    dashboard = FizzRunbookDashboard(engine, dashboard_width)
    middleware = FizzRunbookMiddleware(engine, dashboard)
    logger.info("FizzRunbook initialized: %d runbooks", len(engine.list_runbooks()))
    return engine, dashboard, middleware
