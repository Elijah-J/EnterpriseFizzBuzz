"""
Enterprise FizzBuzz Platform - FizzFPGA Synthesis Engine Test Suite

Comprehensive verification of the FPGA synthesis pipeline, from LUT
configuration through bitstream generation. These tests ensure that
the hardware-accelerated FizzBuzz evaluation path produces correct
divisibility results across the full synthesis flow.

Without these tests, a misconfigured LUT truth table could silently
classify 15 as "Fizz" instead of "FizzBuzz", and no amount of
timing analysis would catch a functional correctness error.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzfpga import (
    BitstreamGenerator,
    CLB,
    ClockDomainID,
    ClockDomainManager,
    FlipFlop,
    FlipFlopType,
    FizzFPGAMiddleware,
    FPGASynthesisEngine,
    LookupTable,
    LUTSize,
    PartialReconfigurationEngine,
    RoutingFabric,
    RoutingResourceType,
    RoutingSegment,
    SynthesisPhase,
    TimingConstraint,
)
from enterprise_fizzbuzz.domain.exceptions import (
    FPGASynthesisError,
    LUTConfigurationError,
    FlipFlopTimingError,
    RoutingCongestionError,
    BitstreamGenerationError,
    ClockDomainCrossingError,
    PartialReconfigurationError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


def _make_context(number: int) -> ProcessingContext:
    return ProcessingContext(number=number, session_id=str(uuid.uuid4()))


# ============================================================
# LUT Tests
# ============================================================


class TestLookupTable:
    def test_lut4_configure_and_evaluate(self):
        lut = LookupTable("lut_0", num_inputs=4)
        # AND gate: output 1 only when all inputs are 1 (pattern 0b1111 = 15)
        lut.configure(1 << 15)
        assert lut.evaluate((True, True, True, True)) is True
        assert lut.evaluate((True, True, True, False)) is False

    def test_lut6_configure(self):
        lut = LookupTable("lut_1", num_inputs=6)
        lut.configure(0)
        assert lut.evaluate((False,) * 6) is False

    def test_lut_invalid_input_width(self):
        with pytest.raises(LUTConfigurationError):
            LookupTable("bad", num_inputs=5)

    def test_lut_evaluate_unconfigured_raises(self):
        lut = LookupTable("lut_unc", num_inputs=4)
        with pytest.raises(FPGASynthesisError):
            lut.evaluate((False, False, False, False))

    def test_lut_utilization(self):
        lut = LookupTable("lut_u", num_inputs=4)
        lut.configure(0xFFFF)  # All outputs True
        assert lut.utilization == 1.0

    def test_lut_utilization_half(self):
        lut = LookupTable("lut_h", num_inputs=4)
        lut.configure(0xFF00)
        assert 0.4 < lut.utilization < 0.6  # 8/16 = 0.5

    def test_lut_wrong_input_count_raises(self):
        lut = LookupTable("lut_w", num_inputs=4)
        lut.configure(0)
        with pytest.raises(LUTConfigurationError):
            lut.evaluate((True, True))


# ============================================================
# Flip-Flop Tests
# ============================================================


class TestFlipFlop:
    def test_d_flipflop_latch(self):
        ff = FlipFlop("ff_0")
        ff.set_input(True)
        result = ff.clock_edge()
        assert result is True
        assert ff.q is True

    def test_flipflop_holds_state(self):
        ff = FlipFlop("ff_1")
        ff.set_input(True)
        ff.clock_edge()
        assert ff.q is True
        # Without new set_input, next clock edge latches same next_state
        ff.clock_edge()
        assert ff.q is True

    def test_timing_check_passes(self):
        ff = FlipFlop("ff_t", timing=TimingConstraint(setup_ns=0.5))
        slack = ff.check_timing(data_arrival_ns=2.0, clock_period_ns=10.0)
        assert slack > 0

    def test_timing_violation_raises(self):
        ff = FlipFlop("ff_v", timing=TimingConstraint(setup_ns=2.0))
        with pytest.raises(FlipFlopTimingError):
            ff.check_timing(data_arrival_ns=9.5, clock_period_ns=10.0)


# ============================================================
# Routing Fabric Tests
# ============================================================


class TestRoutingFabric:
    def test_route_connection(self):
        fabric = RoutingFabric(4, 4)
        seg = fabric.route("clb_0_0", "clb_1_0")
        assert seg.occupied is True
        assert seg.source == "clb_0_0"

    def test_utilization_increases(self):
        fabric = RoutingFabric(4, 4)
        before = fabric.get_utilization(RoutingResourceType.SINGLE)
        fabric.route("a", "b")
        after = fabric.get_utilization(RoutingResourceType.SINGLE)
        assert after > before

    def test_total_utilization(self):
        fabric = RoutingFabric(4, 4)
        assert fabric.total_utilization >= 0.0


# ============================================================
# Clock Domain Tests
# ============================================================


class TestClockDomainManager:
    def test_add_and_get_domain(self):
        mgr = ClockDomainManager()
        domain = mgr.add_domain(ClockDomainID.SYSTEM, 100.0)
        assert domain.period_ns == pytest.approx(10.0)
        assert mgr.get_domain(ClockDomainID.SYSTEM) is domain

    def test_unsynchronized_crossing_detected(self):
        mgr = ClockDomainManager()
        mgr.add_domain(ClockDomainID.SYSTEM, 100.0)
        mgr.add_domain(ClockDomainID.FIZZ, 50.0)
        mgr.register_crossing(ClockDomainID.SYSTEM, ClockDomainID.FIZZ, "data_bus")
        violations = mgr.verify_all_crossings()
        assert len(violations) == 1

    def test_synchronized_crossing_passes(self):
        mgr = ClockDomainManager()
        mgr.add_domain(ClockDomainID.SYSTEM, 100.0)
        mgr.add_domain(ClockDomainID.BUZZ, 75.0)
        mgr.register_crossing(ClockDomainID.SYSTEM, ClockDomainID.BUZZ, "ctrl")
        mgr.synchronize_crossing(ClockDomainID.SYSTEM, ClockDomainID.BUZZ, "ctrl")
        violations = mgr.verify_all_crossings()
        assert len(violations) == 0


# ============================================================
# Synthesis Engine Tests
# ============================================================


class TestFPGASynthesisEngine:
    def test_synthesize_mod3_circuit(self):
        engine = FPGASynthesisEngine(grid_width=4, grid_height=4)
        clbs = engine.synthesize_mod_circuit(3)
        assert len(clbs) >= 1

    def test_full_synthesis_produces_bitstream(self):
        engine = FPGASynthesisEngine(grid_width=4, grid_height=4)
        bitstream = engine.full_synthesis(3)
        assert len(bitstream) > 0
        assert bitstream[:4] == b"FIZZ"

    def test_evaluate_divisible_by_3(self):
        engine = FPGASynthesisEngine(grid_width=4, grid_height=4)
        assert engine.evaluate_number(9, 3) is True

    def test_evaluate_not_divisible_by_3(self):
        engine = FPGASynthesisEngine(grid_width=4, grid_height=4)
        assert engine.evaluate_number(7, 3) is False

    def test_evaluate_divisible_by_5(self):
        engine = FPGASynthesisEngine(grid_width=4, grid_height=4)
        assert engine.evaluate_number(10, 5) is True

    def test_synthesis_log_populated(self):
        engine = FPGASynthesisEngine(grid_width=4, grid_height=4)
        engine.full_synthesis(3)
        assert len(engine.synthesis_log) > 0


# ============================================================
# Partial Reconfiguration Tests
# ============================================================


class TestPartialReconfiguration:
    def test_define_and_reconfigure_region(self):
        pr = PartialReconfigurationEngine()
        clb = CLB(clb_id="clb_0_0", x=0, y=0)
        clb.luts[0].configure(0)
        pr.define_region("region_a", [clb])
        pr.reconfigure("region_a", {clb.luts[0].lut_id: 0xFFFF})
        assert clb.luts[0]._init_mask == 0xFFFF

    def test_locked_region_raises(self):
        pr = PartialReconfigurationEngine()
        clb = CLB(clb_id="clb_1_1", x=1, y=1)
        pr.define_region("locked", [clb])
        pr.lock_region("locked")
        with pytest.raises(PartialReconfigurationError):
            pr.reconfigure("locked", {})

    def test_undefined_region_raises(self):
        pr = PartialReconfigurationEngine()
        with pytest.raises(PartialReconfigurationError):
            pr.reconfigure("nonexistent", {})


# ============================================================
# Middleware Tests
# ============================================================


class TestFizzFPGAMiddleware:
    def test_middleware_annotates_context(self):
        mw = FizzFPGAMiddleware(grid_width=4, grid_height=4)
        ctx = _make_context(15)
        called = []
        mw.process(ctx, lambda c: called.append(True))
        assert called
        assert ctx.metadata["fpga_result"] == "FizzBuzz"
        assert ctx.metadata["fpga_div3"] is True
        assert ctx.metadata["fpga_div5"] is True

    def test_middleware_plain_number(self):
        mw = FizzFPGAMiddleware(grid_width=4, grid_height=4)
        ctx = _make_context(7)
        mw.process(ctx, lambda c: None)
        assert ctx.metadata["fpga_result"] == "7"
