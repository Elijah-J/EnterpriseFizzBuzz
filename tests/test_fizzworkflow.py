"""
Tests for the FizzWorkflow Workflow Orchestration Engine.

Validates workflow registration, execution, instance management, saga
orchestration with forward execution and reverse compensation, dashboard
rendering, and middleware integration. The saga compensation protocol is
the critical correctness property: when step N fails, compensations for
steps N-1 through 0 must execute in strict reverse order.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, AsyncMock, call

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzworkflow import (
    FIZZWORKFLOW_VERSION,
    MIDDLEWARE_PRIORITY,
    WorkflowState,
    StepState,
    FizzWorkflowConfig,
    WorkflowStep,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowEngine,
    SagaOrchestrator,
    FizzWorkflowDashboard,
    FizzWorkflowMiddleware,
    create_fizzworkflow_subsystem,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def engine():
    return WorkflowEngine()


@pytest.fixture
def saga():
    return SagaOrchestrator()


def _make_step(name, handler=None, compensation=None):
    """Helper to build a WorkflowStep with sensible defaults."""
    return WorkflowStep(
        step_id=str(uuid.uuid4()),
        name=name,
        handler=handler or (lambda ctx: ctx),
        compensation=compensation,
    )


def _make_definition(name="test-workflow", steps=None, timeout=30.0):
    return WorkflowDefinition(
        name=name,
        steps=steps or [],
        timeout=timeout,
    )


# ============================================================================
# Constants
# ============================================================================


class TestConstants:
    """Module-level constants must match the published contract."""

    def test_version(self):
        assert FIZZWORKFLOW_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 154


# ============================================================================
# WorkflowEngine
# ============================================================================


class TestWorkflowEngine:
    """Core engine: register definitions, start instances, query state."""

    def test_register_definition(self, engine):
        """Registering a workflow definition stores it for later retrieval."""
        defn = _make_definition("order-process", steps=[
            _make_step("validate"),
            _make_step("charge"),
        ])
        result = engine.register(defn)
        assert result is defn or result.name == "order-process"

    def test_start_workflow_completes(self, engine):
        """Starting a workflow with all-passing steps reaches COMPLETED."""
        call_log = []

        def step_handler(ctx):
            call_log.append("executed")
            return "ok"

        defn = _make_definition("simple", steps=[
            _make_step("a", handler=step_handler),
            _make_step("b", handler=step_handler),
        ])
        engine.register(defn)
        instance = engine.start("simple", context={"input": 42})

        assert instance.state == WorkflowState.COMPLETED
        assert len(call_log) == 2
        assert all(s.state == StepState.COMPLETED for s in instance.steps)

    def test_get_instance(self, engine):
        """A started workflow can be retrieved by instance_id."""
        defn = _make_definition("lookup", steps=[_make_step("x")])
        engine.register(defn)
        instance = engine.start("lookup", context={})

        retrieved = engine.get_instance(instance.instance_id)
        assert retrieved.instance_id == instance.instance_id
        assert retrieved.definition_name == "lookup"

    def test_list_instances(self, engine):
        """list_instances returns all previously started workflows."""
        defn = _make_definition("multi", steps=[_make_step("s")])
        engine.register(defn)

        engine.start("multi", context={"run": 1})
        engine.start("multi", context={"run": 2})
        engine.start("multi", context={"run": 3})

        instances = engine.list_instances()
        assert len(instances) >= 3

    def test_failed_step_stops_workflow(self, engine):
        """When a step raises, the workflow enters FAILED and no further steps run."""
        call_log = []

        def good_step(ctx):
            call_log.append("good")

        def bad_step(ctx):
            call_log.append("bad")
            raise RuntimeError("step exploded")

        def unreachable_step(ctx):
            call_log.append("unreachable")

        defn = _make_definition("fail-test", steps=[
            _make_step("ok", handler=good_step),
            _make_step("boom", handler=bad_step),
            _make_step("never", handler=unreachable_step),
        ])
        engine.register(defn)
        instance = engine.start("fail-test", context={})

        assert instance.state == WorkflowState.FAILED
        assert "unreachable" not in call_log
        assert call_log == ["good", "bad"]

        # The failed step should record the error
        failed_steps = [s for s in instance.steps if s.state == StepState.FAILED]
        assert len(failed_steps) == 1
        assert "exploded" in failed_steps[0].error

    def test_workflow_context_passed_to_steps(self, engine):
        """The context dict provided at start() is accessible to every step handler."""
        received_contexts = []

        def capture_ctx(ctx):
            received_contexts.append(dict(ctx) if isinstance(ctx, dict) else ctx)

        defn = _make_definition("ctx-test", steps=[
            _make_step("s1", handler=capture_ctx),
            _make_step("s2", handler=capture_ctx),
        ])
        engine.register(defn)
        engine.start("ctx-test", context={"user": "elias", "amount": 100})

        assert len(received_contexts) == 2
        for ctx in received_contexts:
            if isinstance(ctx, dict):
                assert ctx.get("user") == "elias"


# ============================================================================
# SagaOrchestrator
# ============================================================================


class TestSagaOrchestrator:
    """Saga pattern: forward execution with reverse compensation on failure."""

    def test_saga_completes_all_steps(self, saga):
        """A saga with no failures completes every step in order."""
        log = []

        steps = [
            _make_step("reserve", handler=lambda ctx: log.append("reserve")),
            _make_step("charge", handler=lambda ctx: log.append("charge")),
            _make_step("ship", handler=lambda ctx: log.append("ship")),
        ]
        instance = saga.execute_saga(steps, context={})

        assert instance.state == WorkflowState.COMPLETED
        assert log == ["reserve", "charge", "ship"]

    def test_saga_compensates_on_failure_in_reverse_order(self, saga):
        """
        When step N fails, compensations for steps N-1..0 must run in
        strict reverse order. This is the critical saga correctness invariant.
        """
        compensation_order = []

        def comp_a(ctx):
            compensation_order.append("comp_a")

        def comp_b(ctx):
            compensation_order.append("comp_b")

        def comp_c(ctx):
            compensation_order.append("comp_c")

        def failing_handler(ctx):
            raise RuntimeError("payment declined")

        steps = [
            _make_step("step_a", handler=lambda ctx: "ok", compensation=comp_a),
            _make_step("step_b", handler=lambda ctx: "ok", compensation=comp_b),
            _make_step("step_c", handler=lambda ctx: "ok", compensation=comp_c),
            _make_step("step_fail", handler=failing_handler),
        ]
        instance = saga.execute_saga(steps, context={})

        # Workflow must be in a failed/compensated terminal state
        assert instance.state in (
            WorkflowState.FAILED,
            WorkflowState.COMPENSATED,
            WorkflowState.COMPENSATING,
        )

        # Compensations must have run in reverse: c, b, a
        assert compensation_order == ["comp_c", "comp_b", "comp_a"], (
            f"Expected reverse compensation order [comp_c, comp_b, comp_a], "
            f"got {compensation_order}"
        )

    def test_partial_compensation(self, saga):
        """
        If step 2 of 4 fails, only steps 0 and 1 have compensations to run.
        Steps 2 and 3 were never completed, so they should not compensate.
        """
        compensation_order = []

        def comp_0(ctx):
            compensation_order.append("comp_0")

        def comp_1(ctx):
            compensation_order.append("comp_1")

        def fail_at_2(ctx):
            raise RuntimeError("fail at step 2")

        steps = [
            _make_step("s0", handler=lambda ctx: "ok", compensation=comp_0),
            _make_step("s1", handler=lambda ctx: "ok", compensation=comp_1),
            _make_step("s2", handler=fail_at_2, compensation=lambda ctx: compensation_order.append("comp_2_should_not_run")),
            _make_step("s3", handler=lambda ctx: "ok", compensation=lambda ctx: compensation_order.append("comp_3_should_not_run")),
        ]
        instance = saga.execute_saga(steps, context={})

        # Only steps that successfully completed should be compensated
        assert "comp_1" in compensation_order
        assert "comp_0" in compensation_order
        assert "comp_3_should_not_run" not in compensation_order
        # comp_2 (the failed step) should also not be compensated
        assert "comp_2_should_not_run" not in compensation_order
        # Reverse order of successful steps
        assert compensation_order == ["comp_1", "comp_0"]

    def test_saga_context_flows_through_steps(self, saga):
        """Steps in a saga receive and can read the shared context."""
        observations = []

        def observe(ctx):
            if isinstance(ctx, dict):
                observations.append(ctx.get("tenant"))

        steps = [
            _make_step("obs1", handler=observe),
            _make_step("obs2", handler=observe),
        ]
        saga.execute_saga(steps, context={"tenant": "acme"})

        assert observations == ["acme", "acme"]

    def test_empty_saga(self, saga):
        """A saga with zero steps completes immediately."""
        instance = saga.execute_saga([], context={})
        assert instance.state == WorkflowState.COMPLETED
        assert len(instance.steps) == 0


# ============================================================================
# FizzWorkflowDashboard
# ============================================================================


class TestFizzWorkflowDashboard:
    """ASCII dashboard for operational visibility into workflow state."""

    def test_render_returns_string(self):
        dashboard = FizzWorkflowDashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_workflow_info(self):
        """The dashboard should include recognizable workflow-related content."""
        dashboard = FizzWorkflowDashboard()
        rendered = dashboard.render().lower()
        # Should mention workflow-related terms
        assert any(
            term in rendered
            for term in ["workflow", "instance", "step", "saga", "fizzworkflow"]
        ), f"Dashboard output lacks workflow-related terms: {rendered[:200]}"


# ============================================================================
# FizzWorkflowMiddleware
# ============================================================================


class TestFizzWorkflowMiddleware:
    """Middleware integration for the FizzBuzz processing pipeline."""

    def test_get_name(self):
        mw = FizzWorkflowMiddleware()
        assert mw.get_name() == "fizzworkflow"

    def test_get_priority(self):
        mw = FizzWorkflowMiddleware()
        assert mw.get_priority() == 154

    def test_process_calls_next(self):
        """Middleware must forward to the next handler in the pipeline."""
        mw = FizzWorkflowMiddleware()
        mock_next = MagicMock()
        ctx = MagicMock()

        mw.process(ctx, mock_next)
        mock_next.assert_called_once()


# ============================================================================
# create_fizzworkflow_subsystem
# ============================================================================


class TestCreateSubsystem:
    """Factory function wiring for the composition root."""

    def test_returns_tuple_of_three(self):
        result = create_fizzworkflow_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_engine_functional(self):
        """The engine from the factory can register and start workflows."""
        engine, _dashboard, _mw = create_fizzworkflow_subsystem()
        defn = _make_definition("factory-test", steps=[
            _make_step("ping", handler=lambda ctx: "pong"),
        ])
        engine.register(defn)
        instance = engine.start("factory-test", context={})
        assert instance.state == WorkflowState.COMPLETED

    def test_correct_types(self):
        """Each element of the tuple is the expected type."""
        engine, dashboard, middleware = create_fizzworkflow_subsystem()
        assert isinstance(engine, WorkflowEngine)
        assert isinstance(dashboard, FizzWorkflowDashboard)
        assert isinstance(middleware, FizzWorkflowMiddleware)
