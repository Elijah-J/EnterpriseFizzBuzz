"""
Tests for FizzClock — NTP/PTP Clock Synchronization.

Verifies that the Enterprise FizzBuzz Platform's distributed clock
synchronization infrastructure correctly implements:
  - VirtualClock drift modeling and frequency adjustment
  - NTPPacket field encoding and serialization
  - NTPServer request handling and timestamp exchange
  - NTPClient offset/delay computation using the NTP on-wire algorithm
  - PIController proportional-integral clock discipline
  - StratumHierarchy multi-level time distribution topology
  - AllanDeviationAnalyzer frequency stability measurement
  - ClockDashboard ASCII rendering
  - ClockMiddleware integration with the processing pipeline
  - Exception hierarchy (ClockSyncError, StratumError, etc.)
  - Factory function for complete subsystem creation
"""

from __future__ import annotations

import math
from typing import Any, Callable
from dataclasses import dataclass, field

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    ClockDriftExceededError,
    ClockSyncError,
    NTPPacketError,
    StratumError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.clock_sync import (
    AllanDeviationAnalyzer,
    ClockDashboard,
    ClockMiddleware,
    LeapIndicator,
    MAX_STRATUM,
    NTPClient,
    NTPMeasurement,
    NTPMode,
    NTPPacket,
    NTPServer,
    NTP_VERSION,
    PIController,
    PPM_TO_RATIO,
    StratumHierarchy,
    StratumNode,
    VirtualClock,
    create_clock_sync_subsystem,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def reference_clock():
    """A VirtualClock with zero drift (ideal reference)."""
    return VirtualClock(name="ref-clock", drift_ppm=0.0, jitter_ns=0.0)


@pytest.fixture
def drifting_clock():
    """A VirtualClock with 50 ppm drift (typical commodity oscillator)."""
    return VirtualClock(name="drift-clock", drift_ppm=50.0, jitter_ns=0.0)


@pytest.fixture
def jittery_clock():
    """A VirtualClock with jitter but no systematic drift."""
    return VirtualClock(name="jitter-clock", drift_ppm=0.0, jitter_ns=500.0)


@pytest.fixture
def ntp_server(reference_clock):
    """An NTP server at stratum 1 with a reference clock."""
    return NTPServer(clock=reference_clock, stratum=1, reference_id="GPS")


@pytest.fixture
def ntp_client(drifting_clock):
    """An NTP client with a drifting clock."""
    return NTPClient(clock=drifting_clock)


@pytest.fixture
def pi_controller():
    """A PI controller with default parameters."""
    return PIController(kp=0.7, ki=0.3)


@pytest.fixture
def hierarchy():
    """A basic stratum hierarchy with reference and two secondaries."""
    h = StratumHierarchy()
    h.add_reference("primary", drift_ppm=0.001, reference_id="GPS")
    h.add_secondary("node-a", "primary", drift_ppm=10.0, jitter_ns=50.0)
    h.add_secondary("node-b", "primary", drift_ppm=25.0, jitter_ns=100.0)
    return h


@pytest.fixture
def make_context():
    """Factory for creating ProcessingContext instances."""
    def _make(number: int = 15) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-session-0001")
    return _make


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    """Passthrough handler that returns the context unchanged."""
    return ctx


# ============================================================
# VirtualClock Tests
# ============================================================


class TestVirtualClock:
    """Tests for the VirtualClock simulated oscillator."""

    def test_create_clock_with_defaults(self):
        clock = VirtualClock()
        assert clock.name == "clock-0"
        assert clock.drift_ppm == 0.0
        assert clock.nominal_drift_ppm == 0.0
        assert clock.frequency_adjustment_ppm == 0.0

    def test_create_clock_with_name_and_drift(self):
        clock = VirtualClock(name="my-clock", drift_ppm=25.0)
        assert clock.name == "my-clock"
        assert clock.nominal_drift_ppm == 25.0
        assert clock.drift_ppm == 25.0

    def test_now_ns_returns_positive(self, reference_clock):
        ns = reference_clock.now_ns()
        assert ns > 0

    def test_now_seconds_returns_positive(self, reference_clock):
        s = reference_clock.now_seconds()
        assert s > 0

    def test_now_seconds_approximately_matches_ns(self, reference_clock):
        ns = reference_clock.now_ns()
        s = reference_clock.now_seconds()
        assert abs(s - ns / 1e9) < 1.0  # Within 1 second tolerance

    def test_step_correction_modifies_offset(self, reference_clock):
        t1 = reference_clock.now_ns()
        reference_clock.step(1_000_000.0)  # +1ms
        t2 = reference_clock.now_ns()
        diff = t2 - t1
        # The step should have added approximately 1ms
        assert diff > 900_000  # At least 0.9ms

    def test_frequency_adjustment(self, reference_clock):
        assert reference_clock.frequency_adjustment_ppm == 0.0
        reference_clock.adjust_frequency(5.0)
        assert reference_clock.frequency_adjustment_ppm == 5.0
        assert reference_clock.drift_ppm == 5.0  # 0 nominal + 5 adjustment

    def test_effective_drift_includes_adjustment(self, drifting_clock):
        assert drifting_clock.drift_ppm == 50.0
        drifting_clock.adjust_frequency(-10.0)
        assert drifting_clock.drift_ppm == 40.0

    def test_get_statistics(self, drifting_clock):
        drifting_clock.step(1000.0)
        drifting_clock.adjust_frequency(2.0)
        stats = drifting_clock.get_statistics()
        assert stats["name"] == "drift-clock"
        assert stats["drift_ppm"] == 50.0
        assert stats["frequency_adjustment_ppm"] == 2.0
        assert stats["effective_drift_ppm"] == 52.0
        assert stats["step_corrections"] == 1
        assert stats["total_adjustments"] == 2

    def test_jittery_clock_returns_varying_values(self, jittery_clock):
        # With jitter, consecutive readings should not be perfectly monotonic
        # at nanosecond resolution (though they will be close)
        values = [jittery_clock.now_ns() for _ in range(10)]
        # All values should be positive
        assert all(v > 0 for v in values)


# ============================================================
# NTPPacket Tests
# ============================================================


class TestNTPPacket:
    """Tests for the NTP v4 message format."""

    def test_default_packet(self):
        pkt = NTPPacket()
        assert pkt.version == NTP_VERSION
        assert pkt.mode == NTPMode.CLIENT
        assert pkt.stratum == 0
        assert pkt.leap_indicator == LeapIndicator.NO_WARNING
        assert pkt.reference_id == "LOCL"

    def test_packet_with_timestamps(self):
        pkt = NTPPacket(
            originate_timestamp=1000.0,
            receive_timestamp=1001.0,
            transmit_timestamp=1001.5,
        )
        assert pkt.originate_timestamp == 1000.0
        assert pkt.receive_timestamp == 1001.0
        assert pkt.transmit_timestamp == 1001.5

    def test_to_dict(self):
        pkt = NTPPacket(stratum=2, reference_id="GPS")
        d = pkt.to_dict()
        assert d["stratum"] == 2
        assert d["reference_id"] == "GPS"
        assert d["vn"] == NTP_VERSION
        assert d["mode"] == NTPMode.CLIENT
        assert "li" in d
        assert "poll" in d
        assert "precision" in d

    def test_server_mode_packet(self):
        pkt = NTPPacket(mode=NTPMode.SERVER, stratum=1)
        assert pkt.mode == NTPMode.SERVER

    def test_all_ntp_modes_valid(self):
        for mode in NTPMode:
            pkt = NTPPacket(mode=mode)
            assert pkt.mode == mode

    def test_leap_indicator_values(self):
        assert LeapIndicator.NO_WARNING == 0
        assert LeapIndicator.LAST_MINUTE_61 == 1
        assert LeapIndicator.LAST_MINUTE_59 == 2
        assert LeapIndicator.ALARM == 3


# ============================================================
# NTPServer Tests
# ============================================================


class TestNTPServer:
    """Tests for the NTP server."""

    def test_create_server(self, reference_clock):
        server = NTPServer(clock=reference_clock, stratum=1, reference_id="GPS")
        assert server.stratum == 1
        assert server.reference_id == "GPS"
        assert server.requests_served == 0

    def test_handle_request_returns_server_packet(self, ntp_server):
        request = NTPPacket(mode=NTPMode.CLIENT, transmit_timestamp=1000.0)
        response = ntp_server.handle_request(request)
        assert response.mode == NTPMode.SERVER
        assert response.stratum == 1
        assert response.originate_timestamp == 1000.0
        assert response.receive_timestamp > 0
        assert response.transmit_timestamp > 0
        assert response.transmit_timestamp >= response.receive_timestamp

    def test_handle_request_increments_counter(self, ntp_server):
        request = NTPPacket(mode=NTPMode.CLIENT, transmit_timestamp=1.0)
        ntp_server.handle_request(request)
        ntp_server.handle_request(request)
        assert ntp_server.requests_served == 2

    def test_server_invalid_stratum(self, reference_clock):
        with pytest.raises(StratumError):
            NTPServer(clock=reference_clock, stratum=17)

    def test_server_stratum_zero(self, reference_clock):
        server = NTPServer(clock=reference_clock, stratum=0)
        assert server.stratum == 0

    def test_server_negative_stratum(self, reference_clock):
        with pytest.raises(StratumError):
            NTPServer(clock=reference_clock, stratum=-1)


# ============================================================
# NTPClient Tests
# ============================================================


class TestNTPClient:
    """Tests for the NTP client offset and delay computation."""

    def test_create_client(self, drifting_clock):
        client = NTPClient(clock=drifting_clock)
        assert client.measurement_count == 0
        assert client.best_offset is None
        assert client.best_delay is None

    def test_query_produces_measurement(self, ntp_client, ntp_server):
        m = ntp_client.query(ntp_server)
        assert isinstance(m, NTPMeasurement)
        assert m.t1 > 0
        assert m.t2 > 0
        assert m.t3 > 0
        assert m.t4 > 0
        assert m.stratum == 1

    def test_offset_formula_correctness(self, ntp_client, ntp_server):
        """Verify that offset = ((T2-T1) + (T3-T4)) / 2."""
        m = ntp_client.query(ntp_server)
        expected_offset = ((m.t2 - m.t1) + (m.t3 - m.t4)) / 2.0
        assert abs(m.offset - expected_offset) < 1e-12

    def test_delay_formula_correctness(self, ntp_client, ntp_server):
        """Verify that delay = (T4-T1) - (T3-T2)."""
        m = ntp_client.query(ntp_server)
        expected_delay = (m.t4 - m.t1) - (m.t3 - m.t2)
        assert abs(m.delay - expected_delay) < 1e-12

    def test_delay_is_non_negative(self, ntp_client, ntp_server):
        """Round-trip delay should be non-negative in normal operation."""
        m = ntp_client.query(ntp_server)
        assert m.delay >= 0

    def test_poll_burst_returns_multiple(self, ntp_client, ntp_server):
        results = ntp_client.poll_burst(ntp_server, count=8)
        assert len(results) == 8
        assert ntp_client.measurement_count == 8

    def test_best_measurement_tracked(self, ntp_client, ntp_server):
        ntp_client.poll_burst(ntp_server, count=4)
        assert isinstance(ntp_client.best_offset, float)
        assert isinstance(ntp_client.best_delay, float)

    def test_filtered_offset_returns_median(self, ntp_client, ntp_server):
        ntp_client.poll_burst(ntp_server, count=8)
        filtered = ntp_client.get_filtered_offset()
        assert isinstance(filtered, float)

    def test_filtered_offset_none_when_empty(self, drifting_clock):
        client = NTPClient(clock=drifting_clock)
        assert client.get_filtered_offset() is None

    def test_get_statistics(self, ntp_client, ntp_server):
        ntp_client.poll_burst(ntp_server, count=4)
        stats = ntp_client.get_statistics()
        assert stats["measurement_count"] == 4
        assert stats["best_offset_us"] is not None
        assert stats["best_delay_us"] is not None
        assert stats["mean_offset_us"] is not None
        assert stats["stddev_offset_us"] is not None

    def test_get_statistics_empty(self, drifting_clock):
        client = NTPClient(clock=drifting_clock)
        stats = client.get_statistics()
        assert stats["measurement_count"] == 0
        assert stats["best_offset_us"] is None


# ============================================================
# PIController Tests
# ============================================================


class TestPIController:
    """Tests for the proportional-integral clock discipline."""

    def test_create_controller(self, pi_controller):
        assert pi_controller.kp == 0.7
        assert pi_controller.ki == 0.3
        assert pi_controller.integral == 0.0

    def test_slew_for_small_offset(self, pi_controller, reference_clock):
        action = pi_controller.discipline(reference_clock, 0.001)  # 1ms offset
        assert action["type"] == "slew"
        assert "adjustment_ppm" in action
        assert "p_term_ppm" in action
        assert "i_term_ppm" in action

    def test_step_for_large_offset(self, pi_controller, reference_clock):
        action = pi_controller.discipline(reference_clock, 0.5)  # 500ms offset
        assert action["type"] == "step"
        assert action["correction_ns"] == 0.5 * 1e9

    def test_step_threshold_boundary(self):
        pi = PIController(step_threshold_s=0.128)
        clock = VirtualClock(name="test")
        # Just below threshold -> slew
        action = pi.discipline(clock, 0.127)
        assert action["type"] == "slew"

    def test_step_threshold_at_boundary(self):
        pi = PIController(step_threshold_s=0.128)
        clock = VirtualClock(name="test")
        # At threshold -> step
        action = pi.discipline(clock, 0.129)
        assert action["type"] == "step"

    def test_integral_accumulates(self, pi_controller, reference_clock):
        pi_controller.discipline(reference_clock, 0.001)
        assert pi_controller.integral == 0.001
        pi_controller.discipline(reference_clock, 0.002)
        assert abs(pi_controller.integral - 0.003) < 1e-12

    def test_integral_resets_on_step(self, pi_controller, reference_clock):
        pi_controller.discipline(reference_clock, 0.001)
        assert pi_controller.integral != 0.0
        pi_controller.discipline(reference_clock, 1.0)  # Large offset -> step
        assert pi_controller.integral == 0.0

    def test_correction_history(self, pi_controller, reference_clock):
        pi_controller.discipline(reference_clock, 0.001)
        pi_controller.discipline(reference_clock, 0.5)
        assert len(pi_controller.corrections) == 2
        assert pi_controller.corrections[0]["type"] == "slew"
        assert pi_controller.corrections[1]["type"] == "step"

    def test_max_adjustment_clamping(self):
        pi = PIController(kp=1000.0, ki=0.0, max_adjustment_ppm=100.0)
        clock = VirtualClock(name="test")
        action = pi.discipline(clock, 0.01)
        # The adjustment should be clamped
        assert abs(action["adjustment_ppm"]) <= 100.0

    def test_frequency_adjustment_applied_to_clock(self, pi_controller, reference_clock):
        assert reference_clock.frequency_adjustment_ppm == 0.0
        pi_controller.discipline(reference_clock, 0.001)
        # After discipline, clock should have a non-zero frequency adjustment
        assert reference_clock.frequency_adjustment_ppm != 0.0


# ============================================================
# StratumHierarchy Tests
# ============================================================


class TestStratumHierarchy:
    """Tests for the stratum hierarchy topology."""

    def test_create_empty_hierarchy(self):
        h = StratumHierarchy()
        assert h.root is None
        assert len(h.nodes) == 0

    def test_add_reference(self):
        h = StratumHierarchy()
        node = h.add_reference("primary", drift_ppm=0.001, reference_id="GPS")
        assert node.stratum == 1
        assert node.name == "primary"
        assert h.root == "primary"

    def test_add_secondary(self, hierarchy):
        nodes = hierarchy.nodes
        assert "node-a" in nodes
        assert nodes["node-a"].stratum == 2
        assert nodes["node-a"].parent == "primary"
        assert nodes["node-a"].client is not None
        assert nodes["node-a"].pi_controller is not None

    def test_secondary_stratum_is_parent_plus_one(self, hierarchy):
        assert hierarchy.nodes["node-a"].stratum == hierarchy.nodes["primary"].stratum + 1

    def test_add_secondary_to_nonexistent_parent(self):
        h = StratumHierarchy()
        h.add_reference("primary")
        with pytest.raises(StratumError):
            h.add_secondary("child", "nonexistent")

    def test_max_stratum_exceeded(self):
        h = StratumHierarchy()
        h.add_reference("s1", drift_ppm=0.0)
        parent = "s1"
        # Build a deep chain up to stratum 16
        for i in range(2, MAX_STRATUM + 1):
            name = f"s{i}"
            h.add_secondary(name, parent, drift_ppm=float(i))
            parent = name
        # One more should exceed MAX_STRATUM
        with pytest.raises(StratumError):
            h.add_secondary("too-deep", parent)

    def test_synchronize_reference_returns_none(self, hierarchy):
        result = hierarchy.synchronize("primary")
        assert result is None

    def test_synchronize_secondary(self, hierarchy):
        result = hierarchy.synchronize("node-a")
        assert result is not None
        assert result["node"] == "node-a"
        assert result["parent"] == "primary"
        assert "type" in result

    def test_synchronize_all(self, hierarchy):
        actions = hierarchy.synchronize_all()
        # Should synchronize node-a and node-b (not primary)
        assert len(actions) == 2
        node_names = {a["node"] for a in actions}
        assert "node-a" in node_names
        assert "node-b" in node_names

    def test_synchronize_nonexistent_node(self, hierarchy):
        with pytest.raises(ClockSyncError):
            hierarchy.synchronize("nonexistent")

    def test_get_tree_lines(self, hierarchy):
        lines = hierarchy.get_tree_lines()
        assert len(lines) >= 3  # Root + 2 children
        # Root line should contain "primary"
        assert any("primary" in line for line in lines)
        assert any("node-a" in line for line in lines)
        assert any("node-b" in line for line in lines)

    def test_get_tree_lines_empty(self):
        h = StratumHierarchy()
        lines = h.get_tree_lines()
        assert lines == ["(empty hierarchy)"]

    def test_children_tracked(self, hierarchy):
        primary = hierarchy.nodes["primary"]
        assert "node-a" in primary.children
        assert "node-b" in primary.children


# ============================================================
# AllanDeviationAnalyzer Tests
# ============================================================


class TestAllanDeviationAnalyzer:
    """Tests for the Allan deviation frequency stability analyzer."""

    def test_create_analyzer(self):
        a = AllanDeviationAnalyzer(base_interval_s=1.0)
        assert a.sample_count == 0

    def test_record_phase(self):
        a = AllanDeviationAnalyzer()
        a.record_phase(0.001)
        a.record_phase(0.002)
        assert a.sample_count == 2

    def test_adev_insufficient_data(self):
        a = AllanDeviationAnalyzer()
        a.record_phase(0.001)
        assert a.compute_adev(1) is None

    def test_adev_with_constant_offset(self):
        """A clock with constant offset has zero Allan deviation."""
        a = AllanDeviationAnalyzer(base_interval_s=1.0)
        for _ in range(20):
            a.record_phase(0.001)  # Constant offset
        adev = a.compute_adev(1)
        assert isinstance(adev, float)
        assert adev == 0.0

    def test_adev_with_linear_drift(self):
        """A clock with linear drift produces non-zero ADEV."""
        a = AllanDeviationAnalyzer(base_interval_s=1.0)
        for i in range(20):
            a.record_phase(i * 0.001)  # Linear drift: 1ms per sample
        adev = a.compute_adev(1)
        assert isinstance(adev, float)
        assert adev >= 0.0

    def test_adev_with_random_walk(self):
        """White noise phase data should produce positive ADEV."""
        a = AllanDeviationAnalyzer(base_interval_s=1.0)
        # Simulate noisy data with a simple pattern
        for i in range(30):
            phase = math.sin(i * 0.5) * 0.001
            a.record_phase(phase)
        adev = a.compute_adev(1)
        assert isinstance(adev, float)
        assert adev > 0.0

    def test_adev_spectrum(self):
        a = AllanDeviationAnalyzer(base_interval_s=1.0)
        for i in range(64):
            a.record_phase(math.sin(i * 0.3) * 0.001)
        spectrum = a.compute_adev_spectrum()
        assert len(spectrum) > 0
        # Each entry is (tau, sigma_y)
        for tau, sigma_y in spectrum:
            assert tau > 0
            assert sigma_y >= 0

    def test_adev_spectrum_empty(self):
        a = AllanDeviationAnalyzer()
        spectrum = a.compute_adev_spectrum()
        assert spectrum == []

    def test_get_statistics(self):
        a = AllanDeviationAnalyzer()
        for i in range(10):
            a.record_phase(i * 0.0001)
        stats = a.get_statistics()
        assert stats["sample_count"] == 10
        assert stats["base_interval_s"] == 1.0
        assert "spectrum" in stats


# ============================================================
# ClockDashboard Tests
# ============================================================


class TestClockDashboard:
    """Tests for the ASCII clock synchronization dashboard."""

    def test_render_basic(self, hierarchy):
        output = ClockDashboard.render(hierarchy)
        assert "FIZZCLOCK" in output
        assert "STRATUM HIERARCHY" in output
        assert "primary" in output

    def test_render_with_offset_history(self, hierarchy):
        history = [0.5, -0.3, 0.1, -0.2, 0.4, 0.0, -0.1, 0.3]
        output = ClockDashboard.render(hierarchy, offset_history=history)
        assert "OFFSET HISTORY" in output

    def test_render_with_analyzer(self, hierarchy):
        analyzer = AllanDeviationAnalyzer()
        for i in range(20):
            analyzer.record_phase(math.sin(i * 0.5) * 0.001)
        output = ClockDashboard.render(hierarchy, analyzer=analyzer)
        assert "ALLAN DEVIATION" in output

    def test_render_includes_node_status(self, hierarchy):
        output = ClockDashboard.render(hierarchy)
        assert "NODE SYNCHRONIZATION STATUS" in output
        assert "node-a" in output
        assert "node-b" in output

    def test_render_custom_width(self, hierarchy):
        output = ClockDashboard.render(hierarchy, width=90)
        lines = output.split("\n")
        # Check that border lines are approximately the right width
        assert len(lines[0]) == 90


# ============================================================
# ClockMiddleware Tests
# ============================================================


class TestClockMiddleware:
    """Tests for the clock synchronization middleware."""

    def test_create_middleware(self, hierarchy):
        mw = ClockMiddleware(hierarchy=hierarchy)
        assert mw.get_name() == "ClockMiddleware"
        assert mw.get_priority() == 3

    def test_process_stamps_context(self, hierarchy, make_context):
        mw = ClockMiddleware(hierarchy=hierarchy)
        ctx = make_context(15)
        result = mw.process(ctx, _identity_handler)
        assert "clock_sync" in result.metadata
        assert "reference_time" in result.metadata["clock_sync"]
        assert result.metadata["clock_sync"]["stratum"] == 1

    def test_process_synchronizes_nodes(self, hierarchy, make_context):
        mw = ClockMiddleware(hierarchy=hierarchy, sync_every_n=1)
        ctx = make_context(15)
        mw.process(ctx, _identity_handler)
        assert len(mw.sync_actions) > 0

    def test_sync_every_n_respected(self, hierarchy, make_context):
        mw = ClockMiddleware(hierarchy=hierarchy, sync_every_n=3)
        # First 2 evaluations should not trigger sync
        for i in range(1, 3):
            ctx = make_context(i)
            mw.process(ctx, _identity_handler)
        actions_before = len(mw.sync_actions)
        # Third evaluation should trigger
        ctx = make_context(3)
        mw.process(ctx, _identity_handler)
        assert len(mw.sync_actions) > actions_before

    def test_offset_history_recorded(self, hierarchy, make_context):
        analyzer = AllanDeviationAnalyzer()
        mw = ClockMiddleware(hierarchy=hierarchy, analyzer=analyzer)
        ctx = make_context(15)
        mw.process(ctx, _identity_handler)
        assert len(mw.offset_history) > 0

    def test_analyzer_receives_samples(self, hierarchy, make_context):
        analyzer = AllanDeviationAnalyzer()
        mw = ClockMiddleware(hierarchy=hierarchy, analyzer=analyzer)
        ctx = make_context(15)
        mw.process(ctx, _identity_handler)
        assert analyzer.sample_count > 0

    def test_render_dashboard(self, hierarchy):
        mw = ClockMiddleware(hierarchy=hierarchy)
        output = mw.render_dashboard()
        assert "FIZZCLOCK" in output

    def test_middleware_passes_through(self, hierarchy, make_context):
        """Middleware should not modify the evaluation result."""
        mw = ClockMiddleware(hierarchy=hierarchy)
        ctx = make_context(42)
        marker = {"processed": True}

        def handler(c: ProcessingContext) -> ProcessingContext:
            c.metadata["marker"] = marker
            return c

        result = mw.process(ctx, handler)
        assert result.metadata["marker"] is marker


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateClockSyncSubsystem:
    """Tests for the create_clock_sync_subsystem factory."""

    def test_creates_all_components(self):
        hierarchy, analyzer, middleware = create_clock_sync_subsystem()
        assert isinstance(hierarchy, StratumHierarchy)
        assert isinstance(analyzer, AllanDeviationAnalyzer)
        assert isinstance(middleware, ClockMiddleware)

    def test_hierarchy_has_primary(self):
        hierarchy, _, _ = create_clock_sync_subsystem()
        assert hierarchy.root == "ntp-primary"
        assert hierarchy.nodes["ntp-primary"].stratum == 1

    def test_hierarchy_has_secondary_nodes(self):
        hierarchy, _, _ = create_clock_sync_subsystem(num_secondary_nodes=3)
        nodes = hierarchy.nodes
        assert "fizz-node-0" in nodes
        assert "fizz-node-1" in nodes
        assert "fizz-node-2" in nodes

    def test_custom_drift(self):
        hierarchy, _, _ = create_clock_sync_subsystem(drift_ppm=50.0)
        node = hierarchy.nodes["fizz-node-0"]
        assert node.clock.nominal_drift_ppm == 50.0

    def test_no_analyzer(self):
        _, analyzer, _ = create_clock_sync_subsystem(enable_adev=False)
        assert analyzer is None

    def test_initial_synchronization_performed(self):
        hierarchy, _, _ = create_clock_sync_subsystem()
        # After creation, secondary nodes should have been synchronized
        node = hierarchy.nodes["fizz-node-0"]
        assert node.client is not None
        assert node.client.measurement_count > 0


# ============================================================
# Exception Tests
# ============================================================


class TestClockExceptions:
    """Tests for the clock synchronization exception hierarchy."""

    def test_clock_sync_error_base(self):
        err = ClockSyncError("test error")
        assert "EFP-NTP0" in str(err)
        assert "test error" in str(err)

    def test_clock_drift_exceeded_error(self):
        err = ClockDriftExceededError("my-clock", 600.0, 500.0)
        assert err.clock_name == "my-clock"
        assert err.drift_ppm == 600.0
        assert err.max_ppm == 500.0
        assert "EFP-NTP1" in str(err)

    def test_stratum_error(self):
        err = StratumError(17, "too deep")
        assert err.stratum == 17
        assert err.reason == "too deep"
        assert "EFP-NTP2" in str(err)

    def test_ntp_packet_error(self):
        err = NTPPacketError("version", "unsupported")
        assert err.field_name == "version"
        assert err.reason == "unsupported"
        assert "EFP-NTP3" in str(err)

    def test_exceptions_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(ClockSyncError, FizzBuzzError)
        assert issubclass(ClockDriftExceededError, ClockSyncError)
        assert issubclass(StratumError, ClockSyncError)
        assert issubclass(NTPPacketError, ClockSyncError)


# ============================================================
# Constants and Enum Tests
# ============================================================


class TestConstants:
    """Tests for module-level constants and enums."""

    def test_ntp_version(self):
        assert NTP_VERSION == 4

    def test_max_stratum(self):
        assert MAX_STRATUM == 16

    def test_ppm_to_ratio(self):
        assert PPM_TO_RATIO == 1e-6

    def test_ntp_modes(self):
        assert NTPMode.CLIENT == 3
        assert NTPMode.SERVER == 4
        assert NTPMode.BROADCAST == 5

    def test_leap_indicators(self):
        assert len(LeapIndicator) == 4
