"""
Enterprise FizzBuzz Platform - FizzBPF Programmable Observability Tests

Tests for the eBPF-style programmable observability subsystem that attaches
user-defined probe programs to internal subsystem events. Validates probe
lifecycle management, event firing, handler invocation, event filtering,
statistics aggregation, dashboard rendering, middleware integration, and
the factory function.

Covers: ProbeType, ProbeState, ProbeProgram, ProbeEvent, ProbeEngine,
FizzBPFDashboard, FizzBPFMiddleware, create_fizzbpf_subsystem, and
module-level constants.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions.fizzbpf import (
    FizzBPFError,
    FizzBPFNotFoundError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.fizzbpf import (
    FIZZBPF_VERSION,
    MIDDLEWARE_PRIORITY,
    FizzBPFDashboard,
    FizzBPFMiddleware,
    ProbeEngine,
    ProbeEvent,
    ProbeProgram,
    ProbeState,
    ProbeType,
    create_fizzbpf_subsystem,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def engine():
    """A fresh ProbeEngine instance."""
    return ProbeEngine()


# ---------------------------------------------------------------------------
# Module-level constant tests
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Tests for the FizzBPF module-level exports."""

    def test_version_string(self):
        assert FIZZBPF_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 218


# ---------------------------------------------------------------------------
# ProbeType enum tests
# ---------------------------------------------------------------------------


class TestProbeType:
    """Tests for the ProbeType enumeration."""

    def test_four_probe_types(self):
        assert len(ProbeType) == 4
        members = {m.name for m in ProbeType}
        assert members == {"KPROBE", "KRETPROBE", "TRACEPOINT", "UPROBE"}


# ---------------------------------------------------------------------------
# ProbeState enum tests
# ---------------------------------------------------------------------------


class TestProbeState:
    """Tests for the ProbeState enumeration."""

    def test_three_states(self):
        assert len(ProbeState) == 3
        members = {m.name for m in ProbeState}
        assert members == {"ATTACHED", "DETACHED", "ERROR"}


# ---------------------------------------------------------------------------
# ProbeProgram dataclass tests
# ---------------------------------------------------------------------------


class TestProbeProgram:
    """Tests for the ProbeProgram dataclass."""

    def test_default_hit_count(self):
        program = ProbeProgram(
            probe_id="bpf-001",
            name="test_probe",
            probe_type=ProbeType.KPROBE,
            target="fizzbuzz.engine",
            state=ProbeState.ATTACHED,
            handler=None,
        )
        assert program.hit_count == 0

    def test_fields_assigned_correctly(self):
        handler_fn = lambda ev: None
        program = ProbeProgram(
            probe_id="bpf-002",
            name="my_probe",
            probe_type=ProbeType.TRACEPOINT,
            target="middleware.pipeline",
            state=ProbeState.DETACHED,
            handler=handler_fn,
            hit_count=42,
        )
        assert program.probe_id == "bpf-002"
        assert program.name == "my_probe"
        assert program.probe_type == ProbeType.TRACEPOINT
        assert program.target == "middleware.pipeline"
        assert program.state == ProbeState.DETACHED
        assert program.handler is handler_fn
        assert program.hit_count == 42


# ---------------------------------------------------------------------------
# ProbeEngine tests
# ---------------------------------------------------------------------------


class TestProbeEngineAttach:
    """Tests for attaching probes to the engine."""

    def test_attach_returns_probe_program_with_correct_fields(self, engine):
        probe = engine.attach("cache_monitor", ProbeType.KPROBE, "cache.lookup")
        assert isinstance(probe, ProbeProgram)
        assert probe.state == ProbeState.ATTACHED
        assert probe.name == "cache_monitor"
        assert probe.probe_type == ProbeType.KPROBE
        assert probe.target == "cache.lookup"
        assert probe.hit_count == 0

    def test_attach_generates_unique_ids(self, engine):
        p1 = engine.attach("probe_a", ProbeType.KPROBE, "target_a")
        p2 = engine.attach("probe_b", ProbeType.KPROBE, "target_b")
        assert p1.probe_id != p2.probe_id

    def test_attach_with_handler(self, engine):
        handler = lambda ev: ev
        probe = engine.attach("handled", ProbeType.KPROBE, "x", handler=handler)
        assert probe.handler is handler

    def test_attach_without_handler(self, engine):
        probe = engine.attach("no_handler", ProbeType.KPROBE, "x")
        assert probe.handler is None


class TestProbeEngineDetach:
    """Tests for detaching probes from the engine."""

    def test_detach_sets_state_to_detached(self, engine):
        probe = engine.attach("det_test", ProbeType.KPROBE, "target")
        detached = engine.detach(probe.probe_id)
        assert detached.state == ProbeState.DETACHED

    def test_detach_nonexistent_raises(self, engine):
        with pytest.raises((FizzBPFNotFoundError, FizzBPFError)):
            engine.detach("nonexistent-probe-id")


class TestProbeEngineGetProbe:
    """Tests for retrieving a specific probe by ID."""

    def test_get_attached_probe(self, engine):
        probe = engine.attach("getter", ProbeType.UPROBE, "x")
        retrieved = engine.get_probe(probe.probe_id)
        assert retrieved.probe_id == probe.probe_id
        assert retrieved.name == "getter"

    def test_get_nonexistent_raises(self, engine):
        with pytest.raises((FizzBPFNotFoundError, FizzBPFError)):
            engine.get_probe("does-not-exist")


class TestProbeEngineListProbes:
    """Tests for listing all registered probes."""

    def test_list_empty_engine(self, engine):
        assert engine.list_probes() == []

    def test_list_after_attaching(self, engine):
        engine.attach("a", ProbeType.KPROBE, "t1")
        engine.attach("b", ProbeType.KRETPROBE, "t2")
        probes = engine.list_probes()
        assert len(probes) == 2
        names = {p.name for p in probes}
        assert names == {"a", "b"}


class TestProbeEngineFire:
    """Tests for firing probe events."""

    def test_fire_returns_probe_event(self, engine):
        probe = engine.attach("fire_test", ProbeType.TRACEPOINT, "target")
        event = engine.fire(probe.probe_id)
        assert isinstance(event, ProbeEvent)

    def test_fire_increments_hit_count(self, engine):
        probe = engine.attach("hit_counter", ProbeType.KPROBE, "target")
        engine.fire(probe.probe_id)
        engine.fire(probe.probe_id)
        engine.fire(probe.probe_id)
        updated = engine.get_probe(probe.probe_id)
        assert updated.hit_count == 3

    def test_fire_calls_handler(self, engine):
        received = []
        handler = lambda ev: received.append(ev)
        probe = engine.attach("handler_test", ProbeType.KPROBE, "t", handler=handler)
        engine.fire(probe.probe_id, data={"key": "value"})
        assert len(received) == 1
        assert isinstance(received[0], ProbeEvent)

    def test_fire_with_data(self, engine):
        probe = engine.attach("data_test", ProbeType.KPROBE, "t")
        event = engine.fire(probe.probe_id, data={"metric": 42})
        assert event.data["metric"] == 42

    def test_fire_event_fields(self, engine):
        probe = engine.attach("field_check", ProbeType.KPROBE, "t")
        event = engine.fire(probe.probe_id)
        assert event.probe_id == probe.probe_id
        assert isinstance(event.timestamp, str) and len(event.timestamp) > 0
        assert isinstance(event.event_id, str) and len(event.event_id) > 0

    def test_fire_nonexistent_raises(self, engine):
        with pytest.raises((FizzBPFNotFoundError, FizzBPFError)):
            engine.fire("ghost-probe")


class TestProbeEngineGetEvents:
    """Tests for retrieving recorded probe events."""

    def test_get_events_empty(self, engine):
        assert engine.get_events() == []

    def test_get_all_events(self, engine):
        p1 = engine.attach("e1", ProbeType.KPROBE, "t1")
        p2 = engine.attach("e2", ProbeType.KPROBE, "t2")
        engine.fire(p1.probe_id)
        engine.fire(p2.probe_id)
        events = engine.get_events()
        assert len(events) == 2

    def test_get_events_filtered_by_probe_id(self, engine):
        p1 = engine.attach("f1", ProbeType.KPROBE, "t1")
        p2 = engine.attach("f2", ProbeType.KPROBE, "t2")
        engine.fire(p1.probe_id)
        engine.fire(p1.probe_id)
        engine.fire(p2.probe_id)
        filtered = engine.get_events(probe_id=p1.probe_id)
        assert len(filtered) == 2
        assert all(e.probe_id == p1.probe_id for e in filtered)


class TestProbeEngineStats:
    """Tests for the engine statistics aggregation."""

    def test_stats_empty(self, engine):
        stats = engine.get_stats()
        assert stats["total_probes"] == 0
        assert stats["total_events"] == 0
        assert stats["active_probes"] == 0

    def test_stats_after_attach_and_fire(self, engine):
        p = engine.attach("s1", ProbeType.KPROBE, "t")
        engine.fire(p.probe_id)
        engine.fire(p.probe_id)
        stats = engine.get_stats()
        assert stats["total_probes"] == 1
        assert stats["total_events"] == 2
        assert stats["active_probes"] == 1

    def test_stats_active_decreases_after_detach(self, engine):
        p = engine.attach("s2", ProbeType.KPROBE, "t")
        engine.detach(p.probe_id)
        stats = engine.get_stats()
        assert stats["total_probes"] == 1
        assert stats["active_probes"] == 0


# ---------------------------------------------------------------------------
# FizzBPFDashboard tests
# ---------------------------------------------------------------------------


class TestFizzBPFDashboard:
    """Tests for the FizzBPF monitoring dashboard."""

    def test_render_returns_nonempty_string(self, engine):
        dashboard = FizzBPFDashboard(engine)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0


# ---------------------------------------------------------------------------
# FizzBPFMiddleware tests
# ---------------------------------------------------------------------------


class TestFizzBPFMiddleware:
    """Tests for the FizzBPF middleware integration."""

    def test_middleware_name_and_priority(self, engine):
        mw = FizzBPFMiddleware(engine)
        assert mw.get_name() == "fizzbpf"
        assert mw.get_priority() == 218

    def test_middleware_passes_through(self, engine):
        mw = FizzBPFMiddleware(engine)
        ctx = ProcessingContext(number=15, session_id="test-bpf-session")

        def next_handler(ctx: ProcessingContext) -> ProcessingContext:
            ctx.results.append(FizzBuzzResult(number=15, output="FizzBuzz"))
            return ctx

        result = mw.process(ctx, next_handler)
        assert len(result.results) == 1
        assert result.results[0].output == "FizzBuzz"


# ---------------------------------------------------------------------------
# Factory function tests
# ---------------------------------------------------------------------------


class TestCreateFizzBPFSubsystem:
    """Tests for the create_fizzbpf_subsystem factory."""

    def test_returns_engine_dashboard_middleware_tuple(self):
        result = create_fizzbpf_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        eng, dash, mw = result
        assert isinstance(eng, ProbeEngine)
        assert isinstance(dash, FizzBPFDashboard)
        assert isinstance(mw, FizzBPFMiddleware)


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Tests for the FizzBPF exception classes."""

    def test_not_found_is_subclass_of_fizzbpf_error(self):
        assert issubclass(FizzBPFNotFoundError, FizzBPFError)

    def test_fizzbpf_error_message(self):
        err = FizzBPFError("probe overload")
        assert "probe overload" in str(err)

    def test_not_found_error_message(self):
        err = FizzBPFNotFoundError("bpf-999")
        assert "bpf-999" in str(err)
