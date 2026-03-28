"""Tests for the FizzMPSC lock-free MPSC channel subsystem.

Validates multi-producer single-consumer message passing semantics,
bounded and unbounded channel modes, close propagation, and the
middleware integration required by the enterprise pipeline.
"""
from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.fizzmpsc import (
    FIZZMPSC_VERSION,
    MIDDLEWARE_PRIORITY,
    ChannelStats,
    Channel,
    ChannelRegistry,
    FizzMPSCDashboard,
    FizzMPSCMiddleware,
    create_fizzmpsc_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzmpsc import (
    FizzMPSCError,
    FizzMPSCNotFoundError,
    FizzMPSCClosedError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registry() -> ChannelRegistry:
    return ChannelRegistry()


@pytest.fixture()
def unbounded(registry: ChannelRegistry) -> Channel:
    """An unbounded channel (capacity=0)."""
    return registry.create_channel("events")


@pytest.fixture()
def bounded(registry: ChannelRegistry) -> Channel:
    """A bounded channel with capacity 3."""
    return registry.create_channel("bounded", capacity=3)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestModuleConstants:
    def test_version_string(self) -> None:
        assert FIZZMPSC_VERSION == "1.0.0"

    def test_middleware_priority(self) -> None:
        assert MIDDLEWARE_PRIORITY == 231


# ---------------------------------------------------------------------------
# Send / Recv FIFO semantics
# ---------------------------------------------------------------------------

class TestSendRecv:
    def test_send_returns_true_on_success(self, unbounded: Channel) -> None:
        assert unbounded.send("Fizz") is True

    def test_recv_returns_none_on_empty(self, unbounded: Channel) -> None:
        assert unbounded.recv() is None

    def test_fifo_ordering(self, unbounded: Channel) -> None:
        unbounded.send("Fizz")
        unbounded.send("Buzz")
        unbounded.send("FizzBuzz")
        assert unbounded.recv() == "Fizz"
        assert unbounded.recv() == "Buzz"
        assert unbounded.recv() == "FizzBuzz"

    def test_pending_tracks_queue_depth(self, unbounded: Channel) -> None:
        assert unbounded.pending == 0
        unbounded.send("a")
        unbounded.send("b")
        assert unbounded.pending == 2
        unbounded.recv()
        assert unbounded.pending == 1


# ---------------------------------------------------------------------------
# Capacity limits
# ---------------------------------------------------------------------------

class TestBoundedChannel:
    def test_bounded_channel_accepts_up_to_capacity(self, bounded: Channel) -> None:
        assert bounded.send(1) is True
        assert bounded.send(2) is True
        assert bounded.send(3) is True

    def test_bounded_channel_rejects_when_full(self, bounded: Channel) -> None:
        bounded.send(1)
        bounded.send(2)
        bounded.send(3)
        assert bounded.send(4) is False

    def test_bounded_channel_accepts_after_drain(self, bounded: Channel) -> None:
        bounded.send(1)
        bounded.send(2)
        bounded.send(3)
        bounded.recv()
        assert bounded.send(4) is True

    def test_unbounded_channel_never_rejects(self, unbounded: Channel) -> None:
        for i in range(500):
            assert unbounded.send(i) is True


# ---------------------------------------------------------------------------
# Close semantics
# ---------------------------------------------------------------------------

class TestCloseSemantics:
    def test_close_sets_is_closed(self, unbounded: Channel) -> None:
        assert unbounded.is_closed is False
        unbounded.close()
        assert unbounded.is_closed is True

    def test_send_on_closed_channel_raises(self, unbounded: Channel) -> None:
        unbounded.close()
        with pytest.raises(FizzMPSCClosedError):
            unbounded.send("too late")

    def test_recv_on_closed_empty_returns_none(self, unbounded: Channel) -> None:
        unbounded.close()
        assert unbounded.recv() is None

    def test_recv_drains_remaining_after_close(self, unbounded: Channel) -> None:
        unbounded.send("last")
        unbounded.close()
        assert unbounded.recv() == "last"
        assert unbounded.recv() is None


# ---------------------------------------------------------------------------
# Stats tracking
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_initial_values(self, unbounded: Channel) -> None:
        s = unbounded.stats()
        assert isinstance(s, ChannelStats)
        assert s.sent == 0
        assert s.received == 0
        assert s.pending == 0
        assert s.capacity == 0

    def test_stats_after_activity(self, unbounded: Channel) -> None:
        unbounded.send("a")
        unbounded.send("b")
        unbounded.recv()
        s = unbounded.stats()
        assert s.sent == 2
        assert s.received == 1
        assert s.pending == 1

    def test_bounded_stats_reports_capacity(self, bounded: Channel) -> None:
        s = bounded.stats()
        assert s.capacity == 3


# ---------------------------------------------------------------------------
# ChannelRegistry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_create_channel(self, registry: ChannelRegistry) -> None:
        ch = registry.create_channel("metrics")
        assert isinstance(ch, Channel)
        assert ch.name == "metrics"

    def test_get_channel(self, registry: ChannelRegistry, unbounded: Channel) -> None:
        fetched = registry.get_channel(unbounded.channel_id)
        assert fetched is unbounded

    def test_get_channel_not_found_raises(self, registry: ChannelRegistry) -> None:
        with pytest.raises(FizzMPSCNotFoundError):
            registry.get_channel("ch-nonexistent")

    def test_list_channels(self, registry: ChannelRegistry) -> None:
        registry.create_channel("a")
        registry.create_channel("b")
        # The fixture already created "events", so total = events + a + b = 3
        # But unbounded fixture may or may not be called; use a fresh registry.
        fresh = ChannelRegistry()
        fresh.create_channel("x")
        fresh.create_channel("y")
        assert len(fresh.list_channels()) == 2

    def test_close_all(self, registry: ChannelRegistry) -> None:
        ch1 = registry.create_channel("r1")
        ch2 = registry.create_channel("r2")
        registry.close_all()
        assert ch1.is_closed is True
        assert ch2.is_closed is True


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_render_contains_version(self) -> None:
        dashboard = FizzMPSCDashboard()
        output = dashboard.render()
        assert FIZZMPSC_VERSION in output

    def test_render_with_registry_shows_channel_count(self, registry: ChannelRegistry) -> None:
        registry.create_channel("results")
        dashboard = FizzMPSCDashboard(registry)
        output = dashboard.render()
        assert "Channels:" in output


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class TestMiddleware:
    def test_get_name(self) -> None:
        mw = FizzMPSCMiddleware()
        assert mw.get_name() == "fizzmpsc"

    def test_get_priority(self) -> None:
        mw = FizzMPSCMiddleware()
        assert mw.get_priority() == 231

    def test_process_delegates_to_next_handler(self) -> None:
        mw = FizzMPSCMiddleware()
        ctx = ProcessingContext(number=7, session_id="mpsc-test")
        result = mw.process(ctx, lambda c: c)
        assert result is ctx


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

class TestFactory:
    def test_create_fizzmpsc_subsystem_returns_triple(self) -> None:
        registry, dashboard, middleware = create_fizzmpsc_subsystem()
        assert isinstance(registry, ChannelRegistry)
        assert isinstance(dashboard, FizzMPSCDashboard)
        assert isinstance(middleware, FizzMPSCMiddleware)

    def test_factory_pre_provisions_channels(self) -> None:
        registry, _, _ = create_fizzmpsc_subsystem()
        channels = registry.list_channels()
        assert len(channels) == 2
        names = {ch.name for ch in channels}
        assert "fizzbuzz_results" in names
        assert "metrics_events" in names
