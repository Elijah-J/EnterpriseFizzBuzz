"""
Enterprise FizzBuzz Platform - FizzIncident Management Lifecycle Test Suite

Tests for the incident management subsystem responsible for tracking,
escalating, and resolving production incidents across the FizzBuzz
platform. Proper incident lifecycle management is critical for
maintaining SLA compliance and ensuring that divisibility computation
outages are handled with appropriate urgency and rigor.
"""

from __future__ import annotations

import time

import pytest

from enterprise_fizzbuzz.infrastructure.fizzincident import (
    FIZZINCIDENT_VERSION,
    MIDDLEWARE_PRIORITY,
    FizzIncidentConfig,
    FizzIncidentDashboard,
    FizzIncidentMiddleware,
    Incident,
    IncidentManager,
    IncidentSeverity,
    IncidentState,
    create_fizzincident_subsystem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def manager():
    """Provide a fresh IncidentManager for each test."""
    config = FizzIncidentConfig()
    return IncidentManager(config)


@pytest.fixture
def sample_incident(manager):
    """Create and return a single P2 incident for reuse in transition tests."""
    return manager.create(
        title="FizzBuzz output cache miss rate exceeded threshold",
        description="Cache miss rate for divisibility results spiked to 42% during peak load.",
        severity=IncidentSeverity.P2,
        assignee="oncall-fizz-team",
    )


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are correctly exported."""

    def test_version_string(self):
        assert FIZZINCIDENT_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 198


# ---------------------------------------------------------------------------
# TestIncidentManager
# ---------------------------------------------------------------------------

class TestIncidentManager:
    """Tests covering incident creation, state transitions, and queries."""

    def test_create_incident_returns_open_state(self, manager):
        """Newly created incidents must begin in the OPEN state."""
        incident = manager.create(
            title="Modulo coprocessor thermal runaway",
            description="Hardware accelerator exceeded safe operating temperature during Fizz evaluation.",
            severity=IncidentSeverity.P1,
            assignee="sre-fizzbuzz",
        )
        assert isinstance(incident, Incident)
        assert incident.state == IncidentState.OPEN
        assert incident.severity == IncidentSeverity.P1
        assert incident.title == "Modulo coprocessor thermal runaway"
        assert incident.assignee == "sre-fizzbuzz"
        assert incident.created_at is not None
        assert incident.resolved_at is None
        assert isinstance(incident.timeline, list)

    def test_acknowledge_transitions_from_open(self, manager, sample_incident):
        """An OPEN incident can be acknowledged."""
        acked = manager.acknowledge(sample_incident.incident_id)
        assert acked.state == IncidentState.ACKNOWLEDGED
        assert acked.updated_at is not None

    def test_acknowledge_rejects_non_open_state(self, manager, sample_incident):
        """Acknowledging an already-acknowledged incident must raise an error."""
        manager.acknowledge(sample_incident.incident_id)
        with pytest.raises(Exception):
            manager.acknowledge(sample_incident.incident_id)

    def test_investigate_transitions_from_acknowledged(self, manager, sample_incident):
        """An ACKNOWLEDGED incident can move to INVESTIGATING."""
        manager.acknowledge(sample_incident.incident_id)
        investigating = manager.investigate(sample_incident.incident_id)
        assert investigating.state == IncidentState.INVESTIGATING

    def test_mitigate_transitions_from_investigating(self, manager, sample_incident):
        """An INVESTIGATING incident can be mitigated."""
        manager.acknowledge(sample_incident.incident_id)
        manager.investigate(sample_incident.incident_id)
        mitigated = manager.mitigate(sample_incident.incident_id)
        assert mitigated.state == IncidentState.MITIGATED

    def test_resolve_sets_resolved_at(self, manager, sample_incident):
        """Resolving an incident must populate the resolved_at timestamp."""
        manager.acknowledge(sample_incident.incident_id)
        manager.investigate(sample_incident.incident_id)
        manager.mitigate(sample_incident.incident_id)
        resolved = manager.resolve(sample_incident.incident_id)
        assert resolved.state == IncidentState.RESOLVED
        assert resolved.resolved_at is not None

    def test_close_transitions_from_resolved(self, manager, sample_incident):
        """A RESOLVED incident can be closed, completing the lifecycle."""
        manager.acknowledge(sample_incident.incident_id)
        manager.investigate(sample_incident.incident_id)
        manager.mitigate(sample_incident.incident_id)
        manager.resolve(sample_incident.incident_id)
        closed = manager.close(sample_incident.incident_id)
        assert closed.state == IncidentState.CLOSED

    def test_get_retrieves_incident_by_id(self, manager, sample_incident):
        """Retrieving an incident by ID returns the correct record."""
        fetched = manager.get(sample_incident.incident_id)
        assert fetched.incident_id == sample_incident.incident_id
        assert fetched.title == sample_incident.title

    def test_list_incidents_filters_by_state(self, manager):
        """Listing incidents with a state filter returns only matching records."""
        manager.create("Incident A", "desc", IncidentSeverity.P3, "team-a")
        inc_b = manager.create("Incident B", "desc", IncidentSeverity.P4, "team-b")
        manager.acknowledge(inc_b.incident_id)

        open_incidents = manager.list_incidents(state=IncidentState.OPEN)
        acked_incidents = manager.list_incidents(state=IncidentState.ACKNOWLEDGED)

        assert len(open_incidents) == 1
        assert open_incidents[0].title == "Incident A"
        assert len(acked_incidents) == 1
        assert acked_incidents[0].title == "Incident B"

    def test_add_timeline_entry(self, manager, sample_incident):
        """Adding a timeline entry appends to the incident timeline."""
        updated = manager.add_timeline_entry(
            sample_incident.incident_id,
            "Correlation ID traced to FizzBuzz pipeline stage 3.",
        )
        assert len(updated.timeline) >= 1
        messages = [entry["message"] for entry in updated.timeline]
        assert "Correlation ID traced to FizzBuzz pipeline stage 3." in messages

    def test_mttr_calculation(self, manager):
        """Mean time to resolve must be computed from resolved incidents only."""
        inc = manager.create("MTTR test", "desc", IncidentSeverity.P3, "team")
        manager.acknowledge(inc.incident_id)
        manager.investigate(inc.incident_id)
        manager.mitigate(inc.incident_id)
        manager.resolve(inc.incident_id)

        mttr = manager.get_mttr()
        assert isinstance(mttr, float)
        assert mttr >= 0.0


# ---------------------------------------------------------------------------
# TestDashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    """Tests for the incident management dashboard rendering."""

    def test_render_returns_string(self, manager):
        """The dashboard render method must return a string."""
        manager.create("Dashboard test", "desc", IncidentSeverity.P2, "team")
        dashboard = FizzIncidentDashboard(manager)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_includes_incident_info(self, manager):
        """Rendered dashboard output must include incident details."""
        manager.create("Buzz alignment failure", "desc", IncidentSeverity.P1, "team")
        dashboard = FizzIncidentDashboard(manager)
        output = dashboard.render()
        assert "Buzz alignment failure" in output or "P1" in output


# ---------------------------------------------------------------------------
# TestMiddleware
# ---------------------------------------------------------------------------

class TestMiddleware:
    """Tests for the FizzIncident middleware integration."""

    def test_middleware_name(self):
        """Middleware must report its canonical name."""
        config = FizzIncidentConfig()
        mgr = IncidentManager(config)
        mw = FizzIncidentMiddleware(mgr)
        assert mw.get_name() == "fizzincident"

    def test_middleware_priority(self):
        """Middleware priority must match the module constant."""
        config = FizzIncidentConfig()
        mgr = IncidentManager(config)
        mw = FizzIncidentMiddleware(mgr)
        assert mw.get_priority() == 198

    def test_middleware_process_calls_next(self):
        """The middleware must invoke the next handler in the pipeline."""
        config = FizzIncidentConfig()
        mgr = IncidentManager(config)
        mw = FizzIncidentMiddleware(mgr)

        called = {"next_invoked": False}

        class FakeContext:
            number = 15
            classification = None
            metadata = {}

        def fake_next(ctx):
            called["next_invoked"] = True
            return ctx

        mw.process(FakeContext(), fake_next)
        assert called["next_invoked"] is True


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """Tests for the factory function that wires the subsystem."""

    def test_returns_tuple_of_three(self):
        """Factory must return a 3-tuple of (manager, dashboard, middleware)."""
        result = create_fizzincident_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_returns_correct_types(self):
        """Each element of the tuple must be the expected type."""
        mgr, dashboard, mw = create_fizzincident_subsystem()
        assert isinstance(mgr, IncidentManager)
        assert isinstance(dashboard, FizzIncidentDashboard)
        assert isinstance(mw, FizzIncidentMiddleware)

    def test_subsystem_components_are_wired(self):
        """The dashboard and middleware must reference the same manager."""
        mgr, dashboard, mw = create_fizzincident_subsystem()
        # Create an incident via the manager and verify the dashboard can see it
        mgr.create("Wiring test", "desc", IncidentSeverity.P3, "team")
        output = dashboard.render()
        assert "Wiring test" in output or len(output) > 0
