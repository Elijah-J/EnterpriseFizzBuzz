"""
Enterprise FizzBuzz Platform - FizzXDP Express Data Path Tests

Tests for the XDP kernel-bypass packet processing subsystem that attaches
programs to virtual network interfaces for per-packet classification and
action decisions.  Validates program lifecycle management, packet processing,
statistics aggregation, dashboard rendering, middleware integration, and
the factory function.

Covers: XDPAction, XDPProgram, PacketInfo, XDPEngine, FizzXDPDashboard,
FizzXDPMiddleware, create_fizzxdp_subsystem, and module-level constants.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions.fizzxdp import (
    FizzXDPError,
    XDPProgramNotFoundError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.fizzxdp import (
    FIZZXDP_VERSION,
    MIDDLEWARE_PRIORITY,
    FizzXDPDashboard,
    FizzXDPMiddleware,
    PacketInfo,
    XDPAction,
    XDPEngine,
    XDPProgram,
    create_fizzxdp_subsystem,
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
    """A fresh XDPEngine instance."""
    return XDPEngine()


# ---------------------------------------------------------------------------
# Module-level constant tests
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Tests for the FizzXDP module-level exports."""

    def test_version_string(self):
        assert FIZZXDP_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 235


# ---------------------------------------------------------------------------
# XDPAction enum tests
# ---------------------------------------------------------------------------


class TestXDPAction:
    """Tests for the XDPAction enumeration."""

    def test_five_actions(self):
        assert len(XDPAction) == 5
        members = {m.name for m in XDPAction}
        assert members == {"PASS", "DROP", "TX", "REDIRECT", "ABORTED"}

    def test_action_values(self):
        assert XDPAction.PASS.value == "pass"
        assert XDPAction.DROP.value == "drop"
        assert XDPAction.TX.value == "tx"
        assert XDPAction.REDIRECT.value == "redirect"
        assert XDPAction.ABORTED.value == "aborted"


# ---------------------------------------------------------------------------
# XDPProgram dataclass tests
# ---------------------------------------------------------------------------


class TestXDPProgram:
    """Tests for the XDPProgram dataclass."""

    def test_default_values(self):
        program = XDPProgram()
        assert program.prog_id == ""
        assert program.name == ""
        assert program.interface == ""
        assert program.action == XDPAction.PASS
        assert program.packets_processed == 0

    def test_fields_assigned_correctly(self):
        program = XDPProgram(
            prog_id="xdp-001",
            name="test_prog",
            interface="eth0",
            action=XDPAction.DROP,
            packets_processed=42,
        )
        assert program.prog_id == "xdp-001"
        assert program.name == "test_prog"
        assert program.interface == "eth0"
        assert program.action == XDPAction.DROP
        assert program.packets_processed == 42


# ---------------------------------------------------------------------------
# PacketInfo dataclass tests
# ---------------------------------------------------------------------------


class TestPacketInfo:
    """Tests for the PacketInfo dataclass."""

    def test_default_values(self):
        pkt = PacketInfo()
        assert pkt.pkt_id == ""
        assert pkt.action_taken == XDPAction.PASS

    def test_fields_assigned_correctly(self):
        pkt = PacketInfo(
            pkt_id="pkt-001",
            src="10.0.0.1",
            dst="10.0.0.2",
            protocol="TCP",
            size=1500,
            action_taken=XDPAction.REDIRECT,
        )
        assert pkt.src == "10.0.0.1"
        assert pkt.dst == "10.0.0.2"
        assert pkt.protocol == "TCP"
        assert pkt.size == 1500
        assert pkt.action_taken == XDPAction.REDIRECT


# ---------------------------------------------------------------------------
# XDPEngine tests
# ---------------------------------------------------------------------------


class TestXDPEngineAttach:
    """Tests for attaching programs to the engine."""

    def test_attach_returns_xdp_program(self, engine):
        prog = engine.attach("classifier", "fizz0")
        assert isinstance(prog, XDPProgram)
        assert prog.name == "classifier"
        assert prog.interface == "fizz0"
        assert prog.action == XDPAction.PASS
        assert prog.packets_processed == 0

    def test_attach_with_custom_action(self, engine):
        prog = engine.attach("dropper", "eth0", XDPAction.DROP)
        assert prog.action == XDPAction.DROP

    def test_attach_generates_unique_ids(self, engine):
        p1 = engine.attach("prog_a", "if0")
        p2 = engine.attach("prog_b", "if1")
        assert p1.prog_id != p2.prog_id


class TestXDPEngineDetach:
    """Tests for detaching programs from the engine."""

    def test_detach_removes_program(self, engine):
        prog = engine.attach("detach_test", "eth0")
        detached = engine.detach(prog.prog_id)
        assert detached.name == "detach_test"
        assert len(engine.list_programs()) == 0

    def test_detach_nonexistent_raises(self, engine):
        with pytest.raises(XDPProgramNotFoundError):
            engine.detach("nonexistent-id")


class TestXDPEngineProcessPacket:
    """Tests for processing packets through XDP programs."""

    def test_process_returns_packet_info(self, engine):
        prog = engine.attach("proc_test", "fizz0")
        pkt = engine.process_packet(prog.prog_id, "10.0.0.1", "10.0.0.2", "TCP", 1500)
        assert isinstance(pkt, PacketInfo)
        assert pkt.src == "10.0.0.1"
        assert pkt.dst == "10.0.0.2"
        assert pkt.protocol == "TCP"
        assert pkt.size == 1500
        assert pkt.action_taken == XDPAction.PASS

    def test_process_increments_packet_count(self, engine):
        prog = engine.attach("counter_test", "fizz0")
        engine.process_packet(prog.prog_id, "a", "b", "UDP", 64)
        engine.process_packet(prog.prog_id, "a", "b", "UDP", 64)
        engine.process_packet(prog.prog_id, "a", "b", "UDP", 64)
        updated = engine.get_program(prog.prog_id)
        assert updated.packets_processed == 3

    def test_process_uses_program_action(self, engine):
        prog = engine.attach("drop_prog", "eth0", XDPAction.DROP)
        pkt = engine.process_packet(prog.prog_id, "x", "y", "FIZZ", 100)
        assert pkt.action_taken == XDPAction.DROP

    def test_process_nonexistent_raises(self, engine):
        with pytest.raises(XDPProgramNotFoundError):
            engine.process_packet("ghost-prog", "a", "b", "TCP", 64)


class TestXDPEngineGetProgram:
    """Tests for retrieving a specific program by ID."""

    def test_get_existing_program(self, engine):
        prog = engine.attach("getter_test", "if0")
        retrieved = engine.get_program(prog.prog_id)
        assert retrieved.prog_id == prog.prog_id
        assert retrieved.name == "getter_test"

    def test_get_nonexistent_raises(self, engine):
        with pytest.raises(XDPProgramNotFoundError):
            engine.get_program("does-not-exist")


class TestXDPEngineListPrograms:
    """Tests for listing all attached programs."""

    def test_list_empty_engine(self, engine):
        assert engine.list_programs() == []

    def test_list_after_attaching(self, engine):
        engine.attach("a", "if0")
        engine.attach("b", "if1")
        programs = engine.list_programs()
        assert len(programs) == 2
        names = {p.name for p in programs}
        assert names == {"a", "b"}


class TestXDPEngineStats:
    """Tests for the engine statistics aggregation."""

    def test_stats_empty(self, engine):
        stats = engine.get_stats()
        assert stats["total_programs"] == 0
        assert stats["total_packets_processed"] == 0
        assert stats["action_counts"] == {}

    def test_stats_after_processing(self, engine):
        p = engine.attach("stat_test", "if0", XDPAction.PASS)
        engine.process_packet(p.prog_id, "a", "b", "TCP", 100)
        engine.process_packet(p.prog_id, "a", "b", "TCP", 200)
        stats = engine.get_stats()
        assert stats["total_programs"] == 1
        assert stats["total_packets_processed"] == 2
        assert stats["action_counts"]["pass"] == 2


# ---------------------------------------------------------------------------
# FizzXDPDashboard tests
# ---------------------------------------------------------------------------


class TestFizzXDPDashboard:
    """Tests for the FizzXDP monitoring dashboard."""

    def test_render_returns_nonempty_string(self, engine):
        dashboard = FizzXDPDashboard(engine)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_version(self, engine):
        dashboard = FizzXDPDashboard(engine)
        output = dashboard.render()
        assert FIZZXDP_VERSION in output

    def test_render_with_programs(self, engine):
        engine.attach("visible_prog", "fizz0")
        dashboard = FizzXDPDashboard(engine)
        output = dashboard.render()
        assert "visible_prog" in output


# ---------------------------------------------------------------------------
# FizzXDPMiddleware tests
# ---------------------------------------------------------------------------


class TestFizzXDPMiddleware:
    """Tests for the FizzXDP middleware integration."""

    def test_middleware_name_and_priority(self, engine):
        mw = FizzXDPMiddleware(engine)
        assert mw.get_name() == "fizzxdp"
        assert mw.get_priority() == 235

    def test_middleware_passes_through(self, engine):
        mw = FizzXDPMiddleware(engine)
        ctx = ProcessingContext(number=15, session_id="test-xdp-session")

        def next_handler(ctx: ProcessingContext) -> ProcessingContext:
            ctx.results.append(FizzBuzzResult(number=15, output="FizzBuzz"))
            return ctx

        result = mw.process(ctx, next_handler)
        assert len(result.results) == 1
        assert result.results[0].output == "FizzBuzz"


# ---------------------------------------------------------------------------
# Factory function tests
# ---------------------------------------------------------------------------


class TestCreateFizzXDPSubsystem:
    """Tests for the create_fizzxdp_subsystem factory."""

    def test_returns_engine_dashboard_middleware_tuple(self):
        result = create_fizzxdp_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        eng, dash, mw = result
        assert isinstance(eng, XDPEngine)
        assert isinstance(dash, FizzXDPDashboard)
        assert isinstance(mw, FizzXDPMiddleware)

    def test_factory_attaches_default_programs(self):
        eng, _, _ = create_fizzxdp_subsystem()
        programs = eng.list_programs()
        assert len(programs) == 3
        names = {p.name for p in programs}
        assert "fizz_classifier" in names
        assert "buzz_filter" in names
        assert "fizzbuzz_redirect" in names


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Tests for the FizzXDP exception classes."""

    def test_program_not_found_is_subclass(self):
        assert issubclass(XDPProgramNotFoundError, FizzXDPError)

    def test_fizzxdp_error_message(self):
        err = FizzXDPError("test error")
        assert "test error" in str(err)

    def test_program_not_found_error_message(self):
        err = XDPProgramNotFoundError("xdp-999")
        assert "xdp-999" in str(err)
