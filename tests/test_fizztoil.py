"""
Enterprise FizzBuzz Platform - FizzToil SRE Toil Measurement Tests

Comprehensive test suite for the FizzToil SRE Toil Measurement and
Automation subsystem. Validates toil tracking, budget computation,
automation state transitions, dashboard rendering, middleware
integration, and factory assembly.

SRE toil is the operational tax every platform pays for existing.
Measuring it is the first step toward eliminating it. These tests
ensure the measurement apparatus itself is trustworthy, because an
SRE who cannot trust their toil metrics is an SRE flying blind.
"""

from __future__ import annotations

import uuid

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizztoil import (
    FIZZTOIL_VERSION,
    MIDDLEWARE_PRIORITY,
    ToilCategory,
    AutomationState,
    FizzToilConfig,
    ToilTask,
    ToilTracker,
    FizzToilDashboard,
    FizzToilMiddleware,
    create_fizztoil_subsystem,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singleton state between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def tracker():
    """Provide a fresh ToilTracker for each test."""
    return ToilTracker()


@pytest.fixture
def populated_tracker(tracker):
    """Provide a tracker pre-loaded with representative toil tasks."""
    tracker.add_task(
        name="Restart FizzBuzz pods",
        category=ToilCategory.MANUAL,
        time_spent_minutes=15.0,
        frequency_per_week=7.0,
        assignee="oncall-alpha",
    )
    tracker.add_task(
        name="Rotate FizzBuzz TLS certs",
        category=ToilCategory.REPETITIVE,
        time_spent_minutes=30.0,
        frequency_per_week=1.0,
        assignee="oncall-beta",
    )
    tracker.add_task(
        name="Scale evaluation shards",
        category=ToilCategory.AUTOMATABLE,
        time_spent_minutes=10.0,
        frequency_per_week=14.0,
        assignee="oncall-alpha",
    )
    tracker.add_task(
        name="Patch FizzBuzz CVEs",
        category=ToilCategory.TACTICAL,
        time_spent_minutes=60.0,
        frequency_per_week=0.5,
        assignee="oncall-gamma",
    )
    return tracker


# ================================================================
# Constants Tests
# ================================================================


class TestConstants:
    """Validates module-level constants that govern FizzToil identity."""

    def test_version_string(self):
        """The module version must be a semantic version string."""
        assert FIZZTOIL_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """Middleware priority must be 204 to slot correctly in the pipeline."""
        assert MIDDLEWARE_PRIORITY == 204


# ================================================================
# ToilTracker Tests
# ================================================================


class TestToilTracker:
    """Validates the core toil tracking engine."""

    def test_add_task_returns_toil_task(self, tracker):
        """Adding a task must return a ToilTask with the provided attributes."""
        task = tracker.add_task(
            name="Flush evaluation cache",
            category=ToilCategory.MANUAL,
            time_spent_minutes=5.0,
            frequency_per_week=21.0,
            assignee="oncall-alpha",
        )
        assert isinstance(task, ToilTask)
        assert task.name == "Flush evaluation cache"
        assert task.category == ToilCategory.MANUAL
        assert task.time_spent_minutes == 5.0
        assert task.frequency_per_week == 21.0
        assert task.assignee == "oncall-alpha"
        assert task.automation_state == AutomationState.MANUAL

    def test_add_task_generates_unique_ids(self, tracker):
        """Each added task must receive a distinct task_id."""
        t1 = tracker.add_task("Task A", ToilCategory.MANUAL, 5.0, 1.0, "alice")
        t2 = tracker.add_task("Task B", ToilCategory.MANUAL, 5.0, 1.0, "alice")
        assert t1.task_id != t2.task_id

    def test_get_task_by_id(self, tracker):
        """A task must be retrievable by its assigned task_id."""
        task = tracker.add_task("Reboot nodes", ToilCategory.REPETITIVE, 20.0, 3.0, "bob")
        retrieved = tracker.get_task(task.task_id)
        assert retrieved.task_id == task.task_id
        assert retrieved.name == "Reboot nodes"

    def test_list_tasks_returns_all(self, populated_tracker):
        """list_tasks must return every registered task."""
        tasks = populated_tracker.list_tasks()
        assert len(tasks) == 4
        names = {t.name for t in tasks}
        assert "Restart FizzBuzz pods" in names
        assert "Scale evaluation shards" in names

    def test_toil_budget_calculation(self, populated_tracker):
        """The toil budget must accurately sum weekly hours across all tasks."""
        budget = populated_tracker.get_toil_budget()
        # Task 1: 15min * 7/week = 105 min = 1.75 hr
        # Task 2: 30min * 1/week = 30 min = 0.5 hr
        # Task 3: 10min * 14/week = 140 min = 2.333... hr
        # Task 4: 60min * 0.5/week = 30 min = 0.5 hr
        # Total = 305 min = 5.0833... hr
        assert "total_hours" in budget
        expected_total = (15 * 7 + 30 * 1 + 10 * 14 + 60 * 0.5) / 60.0
        assert abs(budget["total_hours"] - expected_total) < 0.01

    def test_toil_budget_includes_automatable_hours(self, populated_tracker):
        """The budget must separately report hours spent on automatable toil."""
        budget = populated_tracker.get_toil_budget()
        assert "automatable_hours" in budget
        # Only the AUTOMATABLE task: 10min * 14/week = 140 min = 2.333 hr
        expected_automatable = (10 * 14) / 60.0
        assert abs(budget["automatable_hours"] - expected_automatable) < 0.01

    def test_toil_budget_includes_manual_hours(self, populated_tracker):
        """The budget must separately report hours spent on manual toil."""
        budget = populated_tracker.get_toil_budget()
        assert "manual_hours" in budget
        # MANUAL category task: 15min * 7/week = 105 min = 1.75 hr
        expected_manual = (15 * 7) / 60.0
        assert abs(budget["manual_hours"] - expected_manual) < 0.01

    def test_automate_changes_state(self, tracker):
        """Automating a task must transition it to FULLY_AUTOMATED."""
        task = tracker.add_task("Deploy canary", ToilCategory.AUTOMATABLE, 8.0, 5.0, "sre-team")
        assert task.automation_state == AutomationState.MANUAL
        automated = tracker.automate(task.task_id)
        assert automated.automation_state == AutomationState.FULLY_AUTOMATED
        # Confirm persistence through get_task
        retrieved = tracker.get_task(task.task_id)
        assert retrieved.automation_state == AutomationState.FULLY_AUTOMATED

    def test_automation_rate_with_mixed_states(self, tracker):
        """Automation rate must reflect the fraction of fully automated tasks."""
        tracker.add_task("Manual A", ToilCategory.MANUAL, 5.0, 1.0, "alice")
        t2 = tracker.add_task("Auto B", ToilCategory.AUTOMATABLE, 5.0, 1.0, "bob")
        tracker.add_task("Manual C", ToilCategory.TACTICAL, 5.0, 1.0, "carol")
        t4 = tracker.add_task("Auto D", ToilCategory.AUTOMATABLE, 5.0, 1.0, "dave")

        tracker.automate(t2.task_id)
        tracker.automate(t4.task_id)

        rate = tracker.get_automation_rate()
        # 2 out of 4 automated
        assert abs(rate - 0.5) < 0.01

    def test_empty_tracker_automation_rate(self, tracker):
        """An empty tracker must report an automation rate of zero."""
        rate = tracker.get_automation_rate()
        assert rate == 0.0

    def test_empty_tracker_budget(self, tracker):
        """An empty tracker must report zero hours across all budget categories."""
        budget = tracker.get_toil_budget()
        assert budget["total_hours"] == 0.0
        assert budget["automatable_hours"] == 0.0
        assert budget["manual_hours"] == 0.0


# ================================================================
# Dashboard Tests
# ================================================================


class TestDashboard:
    """Validates the FizzToil dashboard rendering output."""

    def test_render_returns_string(self):
        """The dashboard must render to a non-empty string."""
        tracker = ToilTracker()
        tracker.add_task("Toil A", ToilCategory.MANUAL, 10.0, 5.0, "oncall")
        dashboard = FizzToilDashboard(tracker)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_includes_task_information(self):
        """The rendered dashboard must include task names from the tracker."""
        tracker = ToilTracker()
        tracker.add_task("Rotate secrets", ToilCategory.REPETITIVE, 20.0, 2.0, "vault-sre")
        dashboard = FizzToilDashboard(tracker)
        output = dashboard.render()
        assert "Rotate secrets" in output


# ================================================================
# Middleware Tests
# ================================================================


class TestMiddleware:
    """Validates the FizzToil middleware pipeline integration."""

    def test_middleware_name(self):
        """The middleware must identify itself as 'fizztoil'."""
        tracker = ToilTracker()
        mw = FizzToilMiddleware(tracker)
        assert mw.get_name() == "fizztoil"

    def test_middleware_priority(self):
        """The middleware priority must match the module constant."""
        tracker = ToilTracker()
        mw = FizzToilMiddleware(tracker)
        assert mw.get_priority() == 204

    def test_middleware_process_passes_through(self):
        """The middleware must invoke next_handler and return a context."""
        tracker = ToilTracker()
        mw = FizzToilMiddleware(tracker)
        ctx = ProcessingContext(number=15, session_id="test-session")
        called = False

        def next_handler(c):
            nonlocal called
            called = True
            return c

        result = mw.process(ctx, next_handler)
        assert called, "Middleware must invoke the next handler in the pipeline"
        assert isinstance(result, ProcessingContext)
        assert result.number == 15


# ================================================================
# Factory Tests
# ================================================================


class TestCreateSubsystem:
    """Validates the create_fizztoil_subsystem factory function."""

    def test_factory_returns_three_components(self):
        """The factory must return a (tracker, dashboard, middleware) triple."""
        result = create_fizztoil_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_factory_component_types(self):
        """Each component must be the correct type."""
        tracker, dashboard, middleware = create_fizztoil_subsystem()
        assert isinstance(tracker, ToilTracker)
        assert isinstance(dashboard, FizzToilDashboard)
        assert isinstance(middleware, FizzToilMiddleware)

    def test_factory_components_are_wired(self):
        """The dashboard and middleware must be wired to the same tracker."""
        tracker, dashboard, middleware = create_fizztoil_subsystem()
        # Add a task through the tracker and verify it appears in the dashboard
        tracker.add_task("Verify wiring", ToilCategory.MANUAL, 1.0, 1.0, "test")
        output = dashboard.render()
        assert "Verify wiring" in output
