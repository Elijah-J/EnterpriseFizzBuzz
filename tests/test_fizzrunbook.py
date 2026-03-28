"""
Enterprise FizzBuzz Platform - FizzRunbook Runbook Automation Engine Tests

Comprehensive test suite for the FizzRunbook Runbook Automation Engine
subsystem. Validates runbook definition, step management, publication
lifecycle, execution with approval gates, rollback semantics, dashboard
rendering, middleware integration, and factory assembly.

Operational runbooks are the institutional memory of incident response.
Without automated, versioned, and auditable remediation procedures, every
outage becomes a bespoke crisis. These tests ensure that the runbook
engine enforces correct lifecycle transitions and that approval gates
cannot be bypassed, because an unapproved remediation step in production
is indistinguishable from an attack.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzrunbook import (
    FIZZRUNBOOK_VERSION,
    MIDDLEWARE_PRIORITY,
    StepType,
    ExecutionState,
    RunbookStatus,
    RunbookStep,
    RunbookDefinition,
    ExecutionRecord,
    FizzRunbookConfig,
    RunbookEngine,
    FizzRunbookDashboard,
    FizzRunbookMiddleware,
    create_fizzrunbook_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzrunbook import (
    FizzRunbookError,
    FizzRunbookNotFoundError,
    FizzRunbookExecutionError,
    FizzRunbookStateError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singleton state between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def engine():
    """Provide a fresh RunbookEngine for each test."""
    return RunbookEngine()


@pytest.fixture
def published_runbook(engine):
    """Provide an engine with a published runbook containing mixed step types."""
    rb = engine.create_runbook("Restart FizzBuzz Cluster", description="Full cluster restart procedure")
    engine.add_step(rb.runbook_id, "Notify on-call", StepType.NOTIFICATION, description="Page the SRE team")
    engine.add_step(rb.runbook_id, "Drain traffic", StepType.AUTOMATED, description="Shift load balancer weights to zero")
    engine.add_step(rb.runbook_id, "Confirm drain complete", StepType.MANUAL, description="Operator verifies no in-flight requests")
    engine.add_step(rb.runbook_id, "Rolling restart", StepType.AUTOMATED, description="Restart pods in sequence")
    rb = engine.publish(rb.runbook_id)
    return rb


# ============================================================================
# Constants
# ============================================================================


class TestConstants:
    """Verify module-level constants that anchor FizzRunbook identity."""

    def test_version_string(self):
        """The module version must be a semantic version string."""
        assert FIZZRUNBOOK_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """Middleware priority must be 211 to slot correctly in the pipeline."""
        assert MIDDLEWARE_PRIORITY == 211


# ============================================================================
# Enums
# ============================================================================


class TestEnums:
    """Validate enum members are correctly defined for step types and states."""

    def test_step_type_members(self):
        """StepType must expose MANUAL, AUTOMATED, CONDITIONAL, and NOTIFICATION."""
        assert StepType.MANUAL is not None
        assert StepType.AUTOMATED is not None
        assert StepType.CONDITIONAL is not None
        assert StepType.NOTIFICATION is not None

    def test_execution_state_members(self):
        """ExecutionState must expose all six lifecycle states."""
        expected = {"PENDING", "RUNNING", "AWAITING_APPROVAL", "COMPLETED", "FAILED", "ROLLED_BACK"}
        actual = {s.name for s in ExecutionState}
        assert expected.issubset(actual)

    def test_runbook_status_members(self):
        """RunbookStatus must expose DRAFT, PUBLISHED, and DEPRECATED."""
        assert RunbookStatus.DRAFT is not None
        assert RunbookStatus.PUBLISHED is not None
        assert RunbookStatus.DEPRECATED is not None


# ============================================================================
# Runbook Creation
# ============================================================================


class TestRunbookCreation:
    """Validate runbook creation lifecycle and initial state."""

    def test_create_runbook_returns_definition(self, engine):
        """Creating a runbook must return a RunbookDefinition instance."""
        rb = engine.create_runbook("Failover Procedure")
        assert isinstance(rb, RunbookDefinition)

    def test_create_runbook_status_is_draft(self, engine):
        """A newly created runbook must have DRAFT status."""
        rb = engine.create_runbook("Failover Procedure")
        assert rb.status == RunbookStatus.DRAFT

    def test_create_runbook_assigns_unique_ids(self, engine):
        """Each created runbook must receive a distinct runbook_id."""
        rb1 = engine.create_runbook("Runbook A")
        rb2 = engine.create_runbook("Runbook B")
        assert rb1.runbook_id != rb2.runbook_id

    def test_create_runbook_stores_name_and_description(self, engine):
        """The runbook must preserve the name and description provided at creation."""
        rb = engine.create_runbook("Cache Purge", description="Evict all stale entries from FizzCache")
        assert rb.name == "Cache Purge"
        assert rb.description == "Evict all stale entries from FizzCache"

    def test_create_runbook_empty_steps(self, engine):
        """A newly created runbook must have an empty steps list."""
        rb = engine.create_runbook("Empty Runbook")
        assert rb.steps == []


# ============================================================================
# Step Management
# ============================================================================


class TestStepManagement:
    """Validate adding and configuring runbook steps."""

    def test_add_step_returns_runbook_step(self, engine):
        """Adding a step must return a RunbookStep instance."""
        rb = engine.create_runbook("Test Runbook")
        step = engine.add_step(rb.runbook_id, "Check health", StepType.AUTOMATED)
        assert isinstance(step, RunbookStep)

    def test_add_step_preserves_attributes(self, engine):
        """The returned step must carry the correct name, type, and configuration."""
        rb = engine.create_runbook("Test Runbook")
        step = engine.add_step(
            rb.runbook_id,
            "Verify quorum",
            StepType.MANUAL,
            description="Ensure Raft quorum is maintained",
            timeout_seconds=600,
            on_failure="rollback",
        )
        assert step.name == "Verify quorum"
        assert step.step_type == StepType.MANUAL
        assert step.description == "Ensure Raft quorum is maintained"
        assert step.timeout_seconds == 600
        assert step.on_failure == "rollback"

    def test_add_step_appears_in_runbook(self, engine):
        """Added steps must be accessible via the runbook's steps list."""
        rb = engine.create_runbook("Test Runbook")
        engine.add_step(rb.runbook_id, "Step A", StepType.AUTOMATED)
        engine.add_step(rb.runbook_id, "Step B", StepType.NOTIFICATION)
        updated = engine.get_runbook(rb.runbook_id)
        assert len(updated.steps) == 2
        names = [s.name for s in updated.steps]
        assert "Step A" in names
        assert "Step B" in names

    def test_add_step_default_timeout(self, engine):
        """Steps must default to a 300-second timeout when none is specified."""
        rb = engine.create_runbook("Test Runbook")
        step = engine.add_step(rb.runbook_id, "Default timeout step", StepType.AUTOMATED)
        assert step.timeout_seconds == 300

    def test_add_step_default_on_failure(self, engine):
        """Steps must default to 'abort' failure policy when none is specified."""
        rb = engine.create_runbook("Test Runbook")
        step = engine.add_step(rb.runbook_id, "Default failure step", StepType.AUTOMATED)
        assert step.on_failure == "abort"


# ============================================================================
# Publishing
# ============================================================================


class TestPublishing:
    """Validate runbook publication lifecycle transitions."""

    def test_publish_sets_status_to_published(self, engine):
        """Publishing a draft runbook must transition it to PUBLISHED status."""
        rb = engine.create_runbook("Publish Test")
        engine.add_step(rb.runbook_id, "Step 1", StepType.AUTOMATED)
        published = engine.publish(rb.runbook_id)
        assert published.status == RunbookStatus.PUBLISHED

    def test_publish_returns_updated_definition(self, engine):
        """The returned definition must reflect the PUBLISHED status."""
        rb = engine.create_runbook("Publish Test")
        engine.add_step(rb.runbook_id, "Step 1", StepType.AUTOMATED)
        published = engine.publish(rb.runbook_id)
        assert isinstance(published, RunbookDefinition)
        fetched = engine.get_runbook(rb.runbook_id)
        assert fetched.status == RunbookStatus.PUBLISHED


# ============================================================================
# Listing
# ============================================================================


class TestListing:
    """Validate runbook and execution listing operations."""

    def test_list_runbooks_returns_all(self, engine):
        """list_runbooks must return every registered runbook."""
        engine.create_runbook("RB-1")
        engine.create_runbook("RB-2")
        engine.create_runbook("RB-3")
        result = engine.list_runbooks()
        assert len(result) == 3

    def test_list_runbooks_empty(self, engine):
        """An engine with no runbooks must return an empty list."""
        assert engine.list_runbooks() == []

    def test_list_executions_empty(self, engine):
        """An engine with no executions must return an empty list."""
        assert engine.list_executions() == []


# ============================================================================
# Execution Lifecycle
# ============================================================================


class TestExecution:
    """Validate runbook execution, step progression, and approval gates."""

    def test_execute_returns_execution_record(self, engine, published_runbook):
        """Executing a published runbook must return an ExecutionRecord."""
        record = engine.execute(published_runbook.runbook_id)
        assert isinstance(record, ExecutionRecord)
        assert record.runbook_id == published_runbook.runbook_id

    def test_execute_draft_raises_state_error(self, engine):
        """Executing a DRAFT runbook must raise FizzRunbookStateError."""
        rb = engine.create_runbook("Draft Runbook")
        engine.add_step(rb.runbook_id, "Step 1", StepType.AUTOMATED)
        with pytest.raises(FizzRunbookStateError):
            engine.execute(rb.runbook_id)

    def test_execute_pauses_at_manual_step(self, engine, published_runbook):
        """Execution must pause at MANUAL steps with AWAITING_APPROVAL state."""
        record = engine.execute(published_runbook.runbook_id)
        # Steps: NOTIFICATION (auto), AUTOMATED (auto), MANUAL (pause), AUTOMATED
        # Execution should pause at the MANUAL step (index 2)
        assert record.state == ExecutionState.AWAITING_APPROVAL
        assert record.current_step_index == 2

    def test_approve_step_advances_execution(self, engine, published_runbook):
        """Approving a manual step must advance execution past it."""
        record = engine.execute(published_runbook.runbook_id)
        assert record.state == ExecutionState.AWAITING_APPROVAL
        approved = engine.approve_step(record.execution_id)
        # After approval, the final AUTOMATED step runs and execution completes
        assert approved.state == ExecutionState.COMPLETED

    def test_execution_completes_with_all_automated_steps(self, engine):
        """A runbook with only automated steps must complete without pausing."""
        rb = engine.create_runbook("All Auto")
        engine.add_step(rb.runbook_id, "Auto 1", StepType.AUTOMATED)
        engine.add_step(rb.runbook_id, "Auto 2", StepType.AUTOMATED)
        published = engine.publish(rb.runbook_id)
        record = engine.execute(published.runbook_id)
        assert record.state == ExecutionState.COMPLETED

    def test_get_execution_retrieves_record(self, engine, published_runbook):
        """An execution record must be retrievable by its execution_id."""
        record = engine.execute(published_runbook.runbook_id)
        retrieved = engine.get_execution(record.execution_id)
        assert retrieved.execution_id == record.execution_id
        assert retrieved.runbook_id == published_runbook.runbook_id

    def test_list_executions_after_run(self, engine, published_runbook):
        """list_executions must include records for all executed runbooks."""
        engine.execute(published_runbook.runbook_id)
        engine.execute(published_runbook.runbook_id)
        executions = engine.list_executions()
        assert len(executions) == 2

    def test_execution_has_step_results(self, engine):
        """Completed executions must contain step_results for each executed step."""
        rb = engine.create_runbook("Step Results Test")
        engine.add_step(rb.runbook_id, "Auto Step", StepType.AUTOMATED)
        published = engine.publish(rb.runbook_id)
        record = engine.execute(published.runbook_id)
        assert isinstance(record.step_results, list)
        assert len(record.step_results) >= 1


# ============================================================================
# Exception Hierarchy
# ============================================================================


class TestExceptions:
    """Validate the FizzRunbook exception hierarchy."""

    def test_base_exception_inheritable(self):
        """FizzRunbookError must be usable as a base exception class."""
        assert issubclass(FizzRunbookNotFoundError, FizzRunbookError)
        assert issubclass(FizzRunbookExecutionError, FizzRunbookError)
        assert issubclass(FizzRunbookStateError, FizzRunbookError)


# ============================================================================
# Dashboard
# ============================================================================


class TestDashboard:
    """Validate the FizzRunbook dashboard rendering output."""

    def test_render_returns_string(self, engine):
        """The dashboard must render to a non-empty string."""
        engine.create_runbook("Dashboard Runbook")
        dashboard = FizzRunbookDashboard(engine)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_includes_runbook_name(self, engine):
        """The rendered dashboard must include runbook names from the engine."""
        engine.create_runbook("Certificate Rotation Procedure")
        dashboard = FizzRunbookDashboard(engine)
        output = dashboard.render()
        assert "Certificate Rotation Procedure" in output


# ============================================================================
# Middleware
# ============================================================================


class TestMiddleware:
    """Validate the FizzRunbook middleware pipeline integration."""

    def test_middleware_name(self):
        """The middleware must identify itself as 'fizzrunbook'."""
        engine = RunbookEngine()
        mw = FizzRunbookMiddleware(engine)
        assert mw.get_name() == "fizzrunbook"

    def test_middleware_priority(self):
        """The middleware priority must match the module constant."""
        engine = RunbookEngine()
        mw = FizzRunbookMiddleware(engine)
        assert mw.get_priority() == 211

    def test_middleware_process_passes_through(self):
        """The middleware must invoke next_handler and return a context."""
        engine = RunbookEngine()
        mw = FizzRunbookMiddleware(engine)
        ctx = ProcessingContext(number=42, session_id="test-session")
        called = False

        def next_handler(c):
            nonlocal called
            called = True
            return c

        result = mw.process(ctx, next_handler)
        assert called, "Middleware must invoke the next handler in the pipeline"
        assert isinstance(result, ProcessingContext)
        assert result.number == 42


# ============================================================================
# Factory
# ============================================================================


class TestCreateSubsystem:
    """Validate the create_fizzrunbook_subsystem factory function."""

    def test_factory_returns_three_components(self):
        """The factory must return a (engine, dashboard, middleware) triple."""
        result = create_fizzrunbook_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_factory_component_types(self):
        """Each component must be the correct type."""
        engine, dashboard, middleware = create_fizzrunbook_subsystem()
        assert isinstance(engine, RunbookEngine)
        assert isinstance(dashboard, FizzRunbookDashboard)
        assert isinstance(middleware, FizzRunbookMiddleware)

    def test_factory_components_are_wired(self):
        """The dashboard and middleware must be wired to the same engine instance."""
        engine, dashboard, middleware = create_fizzrunbook_subsystem()
        # Verify the engine is functional through the factory-produced components
        rb = engine.create_runbook("Factory Wiring Test")
        engine.add_step(rb.runbook_id, "Step 1", StepType.AUTOMATED)
        engine.publish(rb.runbook_id)
        # Dashboard should reflect the runbook
        output = dashboard.render()
        assert "Factory Wiring Test" in output
