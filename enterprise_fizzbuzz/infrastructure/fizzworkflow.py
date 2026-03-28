"""
Enterprise FizzBuzz Platform - FizzWorkflow: Workflow Orchestration Engine

BPMN-style workflows with saga patterns and compensation for transactional
multi-step operations.

Architecture reference: Temporal, Camunda, AWS Step Functions, Saga pattern.
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzworkflow import (
    FizzWorkflowError, FizzWorkflowNotFoundError, FizzWorkflowStepError,
    FizzWorkflowCompensationError, FizzWorkflowTimeoutError,
    FizzWorkflowInstanceError, FizzWorkflowConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzworkflow")

EVENT_WF_STARTED = EventType.register("FIZZWORKFLOW_STARTED")
EVENT_WF_COMPLETED = EventType.register("FIZZWORKFLOW_COMPLETED")
EVENT_WF_COMPENSATED = EventType.register("FIZZWORKFLOW_COMPENSATED")

FIZZWORKFLOW_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 154


class WorkflowState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"

class StepState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    COMPENSATED = "compensated"


@dataclass
class FizzWorkflowConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class WorkflowStep:
    step_id: str = ""
    name: str = ""
    handler: Any = None  # Callable[[dict], dict] or str
    state: StepState = StepState.PENDING
    compensation: Any = None  # Callable[[dict], None] or str or None
    output: Any = None
    error: str = ""
    duration_ms: float = 0.0

@dataclass
class WorkflowDefinition:
    name: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    timeout: float = 30.0

@dataclass
class WorkflowInstance:
    instance_id: str = ""
    definition_name: str = ""
    state: WorkflowState = WorkflowState.PENDING
    steps: List[WorkflowStep] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    context: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# Workflow Engine
# ============================================================

class WorkflowEngine:
    """Executes workflow definitions step by step."""

    def __init__(self) -> None:
        self._definitions: Dict[str, WorkflowDefinition] = {}
        self._instances: OrderedDict[str, WorkflowInstance] = OrderedDict()

    def register(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        self._definitions[definition.name] = definition
        return definition

    def start(self, definition_name: str, context: Optional[Dict[str, Any]] = None) -> WorkflowInstance:
        defn = self._definitions.get(definition_name)
        if defn is None:
            raise FizzWorkflowNotFoundError(definition_name)

        instance = WorkflowInstance(
            instance_id=f"wf-{uuid.uuid4().hex[:8]}",
            definition_name=definition_name,
            state=WorkflowState.RUNNING,
            steps=[copy.deepcopy(step) for step in defn.steps],
            started_at=datetime.now(timezone.utc),
            context=dict(context or {}),
        )
        self._instances[instance.instance_id] = instance

        # Execute steps
        for step in instance.steps:
            step.state = StepState.RUNNING
            start = time.time()
            try:
                if callable(step.handler):
                    result = step.handler(instance.context)
                    if isinstance(result, dict):
                        instance.context.update(result)
                    step.output = result
                step.state = StepState.COMPLETED
            except Exception as e:
                step.state = StepState.FAILED
                step.error = str(e)
                instance.state = WorkflowState.FAILED
                step.duration_ms = (time.time() - start) * 1000
                # Skip remaining steps
                for remaining in instance.steps[instance.steps.index(step) + 1:]:
                    remaining.state = StepState.SKIPPED
                break
            step.duration_ms = (time.time() - start) * 1000

        if instance.state != WorkflowState.FAILED:
            instance.state = WorkflowState.COMPLETED

        instance.completed_at = datetime.now(timezone.utc)
        return instance

    def get_instance(self, instance_id: str) -> WorkflowInstance:
        inst = self._instances.get(instance_id)
        if inst is None:
            raise FizzWorkflowInstanceError(f"Instance not found: {instance_id}")
        return inst

    def list_instances(self) -> List[WorkflowInstance]:
        return list(self._instances.values())

    def compensate(self, instance_id: str) -> WorkflowInstance:
        instance = self.get_instance(instance_id)
        if instance.state != WorkflowState.FAILED:
            raise FizzWorkflowCompensationError("Can only compensate failed workflows")

        instance.state = WorkflowState.COMPENSATING
        # Run compensations in reverse for completed steps
        completed = [s for s in instance.steps if s.state == StepState.COMPLETED]
        for step in reversed(completed):
            if step.compensation and callable(step.compensation):
                try:
                    step.compensation(instance.context)
                    step.state = StepState.COMPENSATED
                except Exception:
                    pass

        instance.state = WorkflowState.COMPENSATED
        return instance

    @property
    def definition_count(self) -> int:
        return len(self._definitions)

    @property
    def instance_count(self) -> int:
        return len(self._instances)


# ============================================================
# Saga Orchestrator
# ============================================================

class SagaOrchestrator:
    """Executes sagas with forward execution and reverse compensation."""

    def execute_saga(self, steps: List[WorkflowStep],
                     context: Optional[Dict[str, Any]] = None) -> WorkflowInstance:
        ctx = dict(context or {})
        instance = WorkflowInstance(
            instance_id=f"saga-{uuid.uuid4().hex[:8]}",
            definition_name="saga",
            state=WorkflowState.RUNNING,
            steps=[copy.deepcopy(s) for s in steps],
            started_at=datetime.now(timezone.utc),
            context=ctx,
        )

        completed_steps = []

        for step in instance.steps:
            step.state = StepState.RUNNING
            try:
                if callable(step.handler):
                    result = step.handler(ctx)
                    if isinstance(result, dict):
                        ctx.update(result)
                    step.output = result
                step.state = StepState.COMPLETED
                completed_steps.append(step)
            except Exception as e:
                step.state = StepState.FAILED
                step.error = str(e)
                instance.state = WorkflowState.COMPENSATING

                # Run compensations in reverse order
                for comp_step in reversed(completed_steps):
                    if comp_step.compensation and callable(comp_step.compensation):
                        try:
                            comp_step.compensation(ctx)
                            comp_step.state = StepState.COMPENSATED
                        except Exception:
                            pass

                instance.state = WorkflowState.COMPENSATED
                instance.completed_at = datetime.now(timezone.utc)
                instance.context = ctx
                return instance

        instance.state = WorkflowState.COMPLETED
        instance.completed_at = datetime.now(timezone.utc)
        instance.context = ctx
        return instance


# ============================================================
# Dashboard & Middleware
# ============================================================

class FizzWorkflowDashboard:
    def __init__(self, engine: Optional[WorkflowEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzWorkflow Orchestration Engine".center(self._width),
            "=" * self._width,
            f"  Version:     {FIZZWORKFLOW_VERSION}",
        ]
        if self._engine:
            lines.append(f"  Definitions: {self._engine.definition_count}")
            lines.append(f"  Instances:   {self._engine.instance_count}")
            for inst in self._engine.list_instances()[-5:]:
                steps_done = sum(1 for s in inst.steps if s.state == StepState.COMPLETED)
                lines.append(f"  {inst.instance_id} {inst.definition_name:<20} {inst.state.value:<12} {steps_done}/{len(inst.steps)} steps")
        return "\n".join(lines)


class FizzWorkflowMiddleware(IMiddleware):
    def __init__(self, engine: Optional[WorkflowEngine] = None,
                 dashboard: Optional[FizzWorkflowDashboard] = None) -> None:
        self._engine = engine
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzworkflow"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzWorkflow not initialized"


def create_fizzworkflow_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[WorkflowEngine, FizzWorkflowDashboard, FizzWorkflowMiddleware]:
    engine = WorkflowEngine()

    # Default workflow: FizzBuzz evaluation pipeline
    engine.register(WorkflowDefinition(
        name="fizzbuzz-evaluation",
        steps=[
            WorkflowStep(step_id="s1", name="validate_input", handler=lambda ctx: ctx),
            WorkflowStep(step_id="s2", name="evaluate_rules", handler=lambda ctx: {"result": "FizzBuzz"}),
            WorkflowStep(step_id="s3", name="format_output", handler=lambda ctx: ctx),
        ],
    ))

    dashboard = FizzWorkflowDashboard(engine, dashboard_width)
    middleware = FizzWorkflowMiddleware(engine, dashboard)

    logger.info("FizzWorkflow initialized: %d definitions", engine.definition_count)
    return engine, dashboard, middleware
