"""
Tests for the FizzGate Digital Logic Circuit Simulator.

Verifies that the Enterprise FizzBuzz Platform's gate-level circuit
simulation infrastructure correctly implements:
  - Wire primitives (drive, history, fanout registration)
  - Gate types (AND, OR, NOT, XOR, NAND, NOR) with correct truth tables
  - HalfAdder, FullAdder, RippleCarryAdder composite circuits
  - ModuloCircuit minterm-based divisibility logic
  - FizzBuzzClassifier correctness for all values 1-100
  - EventDrivenSimulator with propagation delay and steady-state detection
  - WaveformCapture and ASCII rendering
  - CriticalPathAnalyzer static timing analysis
  - CircuitDashboard rendering
  - CircuitMiddleware integration with the processing pipeline
  - Exception hierarchy (topology, simulation, steady-state, timing)
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    CircuitSimulationError,
    CircuitSteadyStateError,
    CircuitTopologyError,
    CircuitTimingViolationError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.circuit_simulator import (
    CircuitDashboard,
    CircuitMiddleware,
    CriticalPathAnalyzer,
    EventDrivenSimulator,
    FizzBuzzClassifier,
    FullAdder,
    Gate,
    GateType,
    HalfAdder,
    ModuloCircuit,
    RippleCarryAdder,
    SimulationEvent,
    WaveformCapture,
    Wire,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def make_wire():
    """Factory for creating named wires."""
    def _make(name: str, value: bool = False) -> Wire:
        return Wire(name, initial_value=value)
    return _make


@pytest.fixture
def classifier():
    """Create a fresh FizzBuzzClassifier."""
    return FizzBuzzClassifier()


@pytest.fixture
def simulator(classifier):
    """Create an EventDrivenSimulator with default settings."""
    return EventDrivenSimulator(classifier)


# ============================================================
# Wire Tests
# ============================================================


class TestWire:
    """Tests for the Wire signal primitive."""

    def test_initial_value_default(self):
        w = Wire("test")
        assert w.value is False

    def test_initial_value_true(self):
        w = Wire("test", initial_value=True)
        assert w.value is True

    def test_drive_changes_value(self):
        w = Wire("test")
        changed = w.drive(True, 1.0)
        assert changed is True
        assert w.value is True

    def test_drive_same_value_no_change(self):
        w = Wire("test")
        changed = w.drive(False, 1.0)
        assert changed is False

    def test_history_records_transitions(self):
        w = Wire("test")
        w.drive(True, 1.0)
        w.drive(False, 2.0)
        w.drive(True, 3.0)
        assert len(w.history) == 4  # initial + 3 transitions
        assert w.history[0] == (0.0, False)
        assert w.history[1] == (1.0, True)
        assert w.history[2] == (2.0, False)
        assert w.history[3] == (3.0, True)

    def test_fanout_registration(self):
        w = Wire("test")
        out = Wire("out")
        g = Gate("g", GateType.NOT, [w], out)
        assert len(w.fanout) == 1
        assert w.fanout[0] is g

    def test_reset(self):
        w = Wire("test", initial_value=True)
        w.drive(False, 1.0)
        w.reset()
        assert w.value is False
        assert len(w.history) == 1

    def test_repr(self):
        w = Wire("sig_a", initial_value=True)
        assert "sig_a" in repr(w)
        assert "True" in repr(w)

    def test_name_preserved(self):
        w = Wire("important_signal")
        assert w.name == "important_signal"


# ============================================================
# Gate Tests
# ============================================================


class TestGate:
    """Tests for individual logic gate evaluation."""

    def test_and_gate_truth_table(self):
        for a, b, expected in [(False, False, False), (False, True, False),
                               (True, False, False), (True, True, True)]:
            wa = Wire("a", initial_value=a)
            wb = Wire("b", initial_value=b)
            out = Wire("out")
            g = Gate("and", GateType.AND, [wa, wb], out)
            assert g.evaluate() == expected, f"AND({a}, {b}) should be {expected}"

    def test_or_gate_truth_table(self):
        for a, b, expected in [(False, False, False), (False, True, True),
                               (True, False, True), (True, True, True)]:
            wa = Wire("a", initial_value=a)
            wb = Wire("b", initial_value=b)
            out = Wire("out")
            g = Gate("or", GateType.OR, [wa, wb], out)
            assert g.evaluate() == expected, f"OR({a}, {b}) should be {expected}"

    def test_not_gate_truth_table(self):
        for a, expected in [(False, True), (True, False)]:
            wa = Wire("a", initial_value=a)
            out = Wire("out")
            g = Gate("not", GateType.NOT, [wa], out)
            assert g.evaluate() == expected, f"NOT({a}) should be {expected}"

    def test_xor_gate_truth_table(self):
        for a, b, expected in [(False, False, False), (False, True, True),
                               (True, False, True), (True, True, False)]:
            wa = Wire("a", initial_value=a)
            wb = Wire("b", initial_value=b)
            out = Wire("out")
            g = Gate("xor", GateType.XOR, [wa, wb], out)
            assert g.evaluate() == expected, f"XOR({a}, {b}) should be {expected}"

    def test_nand_gate_truth_table(self):
        for a, b, expected in [(False, False, True), (False, True, True),
                               (True, False, True), (True, True, False)]:
            wa = Wire("a", initial_value=a)
            wb = Wire("b", initial_value=b)
            out = Wire("out")
            g = Gate("nand", GateType.NAND, [wa, wb], out)
            assert g.evaluate() == expected, f"NAND({a}, {b}) should be {expected}"

    def test_nor_gate_truth_table(self):
        for a, b, expected in [(False, False, True), (False, True, False),
                               (True, False, False), (True, True, False)]:
            wa = Wire("a", initial_value=a)
            wb = Wire("b", initial_value=b)
            out = Wire("out")
            g = Gate("nor", GateType.NOR, [wa, wb], out)
            assert g.evaluate() == expected, f"NOR({a}, {b}) should be {expected}"

    def test_not_gate_rejects_two_inputs(self):
        wa = Wire("a")
        wb = Wire("b")
        out = Wire("out")
        with pytest.raises(CircuitTopologyError):
            Gate("not", GateType.NOT, [wa, wb], out)

    def test_and_gate_rejects_single_input(self):
        wa = Wire("a")
        out = Wire("out")
        with pytest.raises(CircuitTopologyError):
            Gate("and", GateType.AND, [wa], out)

    def test_three_input_and(self):
        wa = Wire("a", initial_value=True)
        wb = Wire("b", initial_value=True)
        wc = Wire("c", initial_value=True)
        out = Wire("out")
        g = Gate("and3", GateType.AND, [wa, wb, wc], out)
        assert g.evaluate() is True

    def test_three_input_and_one_false(self):
        wa = Wire("a", initial_value=True)
        wb = Wire("b", initial_value=False)
        wc = Wire("c", initial_value=True)
        out = Wire("out")
        g = Gate("and3", GateType.AND, [wa, wb, wc], out)
        assert g.evaluate() is False

    def test_gate_default_delay(self):
        wa = Wire("a")
        wb = Wire("b")
        out = Wire("out")
        g = Gate("and", GateType.AND, [wa, wb], out)
        assert g.delay_ns == 1.2  # Default AND delay

    def test_gate_custom_delay(self):
        wa = Wire("a")
        wb = Wire("b")
        out = Wire("out")
        g = Gate("and", GateType.AND, [wa, wb], out, delay_ns=5.0)
        assert g.delay_ns == 5.0

    def test_gate_repr(self):
        wa = Wire("a")
        wb = Wire("b")
        out = Wire("out")
        g = Gate("mygate", GateType.AND, [wa, wb], out)
        r = repr(g)
        assert "mygate" in r
        assert "AND" in r

    def test_xor_three_inputs(self):
        """XOR with three inputs: parity function."""
        wa = Wire("a", initial_value=True)
        wb = Wire("b", initial_value=True)
        wc = Wire("c", initial_value=True)
        out = Wire("out")
        g = Gate("xor3", GateType.XOR, [wa, wb, wc], out)
        # 1 ^ 1 ^ 1 = 1
        assert g.evaluate() is True


# ============================================================
# GateType Tests
# ============================================================


class TestGateType:
    """Tests for the GateType enumeration."""

    def test_all_types_exist(self):
        assert GateType.AND is not None
        assert GateType.OR is not None
        assert GateType.NOT is not None
        assert GateType.XOR is not None
        assert GateType.NAND is not None
        assert GateType.NOR is not None

    def test_six_types(self):
        assert len(GateType) == 6


# ============================================================
# HalfAdder Tests
# ============================================================


class TestHalfAdder:
    """Tests for the HalfAdder composite circuit."""

    def test_half_adder_0_plus_0(self):
        a = Wire("a", initial_value=False)
        b = Wire("b", initial_value=False)
        ha = HalfAdder("ha", a, b)
        ha.xor_gate.output._value = ha.xor_gate.evaluate()
        ha.and_gate.output._value = ha.and_gate.evaluate()
        assert ha.sum_out.value is False
        assert ha.carry_out.value is False

    def test_half_adder_0_plus_1(self):
        a = Wire("a", initial_value=False)
        b = Wire("b", initial_value=True)
        ha = HalfAdder("ha", a, b)
        ha.xor_gate.output._value = ha.xor_gate.evaluate()
        ha.and_gate.output._value = ha.and_gate.evaluate()
        assert ha.sum_out.value is True
        assert ha.carry_out.value is False

    def test_half_adder_1_plus_1(self):
        a = Wire("a", initial_value=True)
        b = Wire("b", initial_value=True)
        ha = HalfAdder("ha", a, b)
        ha.xor_gate.output._value = ha.xor_gate.evaluate()
        ha.and_gate.output._value = ha.and_gate.evaluate()
        assert ha.sum_out.value is False
        assert ha.carry_out.value is True

    def test_half_adder_gate_count(self):
        a = Wire("a")
        b = Wire("b")
        ha = HalfAdder("ha", a, b)
        assert len(ha.gates) == 2


# ============================================================
# FullAdder Tests
# ============================================================


class TestFullAdder:
    """Tests for the FullAdder composite circuit."""

    def _eval_full_adder(self, a_val, b_val, cin_val):
        a = Wire("a", initial_value=a_val)
        b = Wire("b", initial_value=b_val)
        cin = Wire("cin", initial_value=cin_val)
        fa = FullAdder("fa", a, b, cin)
        # Evaluate in order
        for g in fa.gates:
            g.output._value = g.evaluate()
        return fa.sum_out.value, fa.carry_out.value

    def test_full_adder_0_0_0(self):
        s, c = self._eval_full_adder(False, False, False)
        assert s is False and c is False

    def test_full_adder_1_0_0(self):
        s, c = self._eval_full_adder(True, False, False)
        assert s is True and c is False

    def test_full_adder_1_1_0(self):
        s, c = self._eval_full_adder(True, True, False)
        assert s is False and c is True

    def test_full_adder_1_1_1(self):
        s, c = self._eval_full_adder(True, True, True)
        assert s is True and c is True

    def test_full_adder_0_1_1(self):
        s, c = self._eval_full_adder(False, True, True)
        assert s is False and c is True

    def test_full_adder_gate_count(self):
        a = Wire("a")
        b = Wire("b")
        cin = Wire("cin")
        fa = FullAdder("fa", a, b, cin)
        assert len(fa.gates) == 5  # 2 half adders (2 gates each) + 1 OR


# ============================================================
# RippleCarryAdder Tests
# ============================================================


class TestRippleCarryAdder:
    """Tests for the RippleCarryAdder multi-bit addition circuit."""

    def _eval_rca(self, a_val: int, b_val: int, bits: int = 4) -> int:
        a_wires = [Wire(f"a{i}", initial_value=bool((a_val >> i) & 1)) for i in range(bits)]
        b_wires = [Wire(f"b{i}", initial_value=bool((b_val >> i) & 1)) for i in range(bits)]
        cin = Wire("cin", initial_value=False)
        rca = RippleCarryAdder("rca", a_wires, b_wires, cin)

        # Evaluate all gates in order
        for fa in rca.full_adders:
            for g in fa.gates:
                g.output._value = g.evaluate()

        result = 0
        for i, s in enumerate(rca.sum_bits):
            if s.value:
                result |= (1 << i)
        return result

    def test_rca_3_plus_5(self):
        assert self._eval_rca(3, 5) == 8

    def test_rca_0_plus_0(self):
        assert self._eval_rca(0, 0) == 0

    def test_rca_7_plus_1(self):
        assert self._eval_rca(7, 1) == 8

    def test_rca_mismatched_widths(self):
        a = [Wire("a0"), Wire("a1")]
        b = [Wire("b0")]
        cin = Wire("cin")
        with pytest.raises(CircuitTopologyError):
            RippleCarryAdder("rca", a, b, cin)


# ============================================================
# ModuloCircuit Tests
# ============================================================


class TestModuloCircuit:
    """Tests for the ModuloCircuit minterm-based divisibility checker."""

    def _eval_mod(self, number: int, divisor: int, bits: int = 7) -> bool:
        input_bits = [
            Wire(f"in_{i}", initial_value=bool((number >> i) & 1))
            for i in range(bits)
        ]
        mc = ModuloCircuit("mod", input_bits, divisor)
        # Evaluate all gates in topological order (simple sequential)
        for g in mc.gates:
            g.output._value = g.evaluate()
        return mc.output.value

    def test_mod3_divisible(self):
        for n in [0, 3, 6, 9, 12, 15, 21, 30, 45, 99]:
            assert self._eval_mod(n, 3) is True, f"{n} should be divisible by 3"

    def test_mod3_not_divisible(self):
        for n in [1, 2, 4, 5, 7, 8, 10, 11, 13, 14, 97]:
            assert self._eval_mod(n, 3) is False, f"{n} should not be divisible by 3"

    def test_mod5_divisible(self):
        for n in [0, 5, 10, 15, 20, 25, 50, 100]:
            assert self._eval_mod(n, 5) is True, f"{n} should be divisible by 5"

    def test_mod5_not_divisible(self):
        for n in [1, 2, 3, 4, 6, 7, 8, 9, 11, 99]:
            assert self._eval_mod(n, 5) is False, f"{n} should not be divisible by 5"

    def test_mod7(self):
        for n in range(0, 128):
            expected = (n % 7 == 0)
            assert self._eval_mod(n, 7) == expected, f"{n} % 7 == 0 should be {expected}"

    def test_invalid_divisor(self):
        input_bits = [Wire(f"in_{i}") for i in range(4)]
        with pytest.raises(CircuitTopologyError):
            ModuloCircuit("mod", input_bits, 1)

    def test_minterm_count_mod3(self):
        input_bits = [Wire(f"in_{i}") for i in range(7)]
        mc = ModuloCircuit("mod", input_bits, 3)
        # 128 / 3 = 42.67, so 43 minterms (0, 3, 6, ..., 126)
        expected = len(range(0, 128, 3))
        assert mc.minterm_count == expected


# ============================================================
# FizzBuzzClassifier Tests
# ============================================================


class TestFizzBuzzClassifier:
    """Tests for the top-level FizzBuzz classification circuit."""

    def test_correctness_1_to_100(self, classifier):
        """The critical test: verify gate-level results match n%3/n%5 for 1-100."""
        for n in range(1, 101):
            result = classifier.classify(n)
            expected_div3 = (n % 3 == 0)
            expected_div5 = (n % 5 == 0)
            expected_div15 = (n % 15 == 0)

            if expected_div15:
                expected_label = "FizzBuzz"
            elif expected_div3:
                expected_label = "Fizz"
            elif expected_div5:
                expected_label = "Buzz"
            else:
                expected_label = str(n)

            assert result["div_by_3"] == expected_div3, f"n={n}: div_by_3 mismatch"
            assert result["div_by_5"] == expected_div5, f"n={n}: div_by_5 mismatch"
            assert result["div_by_15"] == expected_div15, f"n={n}: div_by_15 mismatch"
            assert result["label"] == expected_label, f"n={n}: label mismatch"

    def test_classify_1(self, classifier):
        result = classifier.classify(1)
        assert result["label"] == "1"
        assert result["div_by_3"] is False
        assert result["div_by_5"] is False

    def test_classify_3(self, classifier):
        result = classifier.classify(3)
        assert result["label"] == "Fizz"
        assert result["div_by_3"] is True
        assert result["div_by_5"] is False

    def test_classify_5(self, classifier):
        result = classifier.classify(5)
        assert result["label"] == "Buzz"
        assert result["div_by_5"] is True
        assert result["div_by_3"] is False

    def test_classify_15(self, classifier):
        result = classifier.classify(15)
        assert result["label"] == "FizzBuzz"
        assert result["div_by_15"] is True

    def test_classify_30(self, classifier):
        result = classifier.classify(30)
        assert result["label"] == "FizzBuzz"

    def test_classify_returns_binary(self, classifier):
        result = classifier.classify(42)
        assert result["binary"] == "0101010"

    def test_classify_returns_gate_evaluations(self, classifier):
        result = classifier.classify(1)
        assert result["gate_evaluations"] > 0

    def test_input_out_of_range(self, classifier):
        with pytest.raises(CircuitSimulationError):
            classifier.classify(128)

    def test_input_negative(self, classifier):
        with pytest.raises(CircuitSimulationError):
            classifier.classify(-1)

    def test_gate_count_positive(self, classifier):
        assert classifier.gate_count > 0

    def test_wire_count_positive(self, classifier):
        assert classifier.wire_count > 0

    def test_gate_count_by_type(self, classifier):
        counts = classifier.gate_count_by_type
        assert GateType.AND in counts
        assert GateType.NOT in counts

    def test_reset(self, classifier):
        classifier.classify(15)
        classifier.reset()
        # After reset, input bits should be 0
        for w in classifier.input_bits:
            assert w.value is False

    def test_bit_width(self):
        assert FizzBuzzClassifier.BIT_WIDTH == 7


# ============================================================
# EventDrivenSimulator Tests
# ============================================================


class TestEventDrivenSimulator:
    """Tests for the event-driven circuit simulator."""

    def test_simulate_basic(self, simulator):
        result = simulator.simulate(15)
        assert result["label"] == "FizzBuzz"
        assert result["number"] == 15

    def test_simulate_correctness_1_to_100(self, classifier):
        """Event-driven simulation must match modulo arithmetic for 1-100."""
        sim = EventDrivenSimulator(classifier)
        for n in range(1, 101):
            classifier.reset()
            result = sim.simulate(n)
            if n % 15 == 0:
                assert result["label"] == "FizzBuzz", f"n={n}"
            elif n % 3 == 0:
                assert result["label"] == "Fizz", f"n={n}"
            elif n % 5 == 0:
                assert result["label"] == "Buzz", f"n={n}"
            else:
                assert result["label"] == str(n), f"n={n}"

    def test_simulate_events_processed(self, simulator):
        result = simulator.simulate(7)
        assert result["events_processed"] >= 0

    def test_simulate_steady_state_ns(self, simulator):
        result = simulator.simulate(7)
        assert result["steady_state_ns"] >= 0.0

    def test_simulate_with_waveform(self, classifier):
        sim = EventDrivenSimulator(classifier)
        result = sim.simulate(15, capture_waveform=True)
        assert "waveform" in result
        assert result["waveform"] is not None

    def test_simulate_glitch_count(self, simulator):
        result = simulator.simulate(42)
        assert result["glitch_count"] >= 0

    def test_max_events_limit(self, classifier):
        """Verify that the simulator respects the max events limit."""
        sim = EventDrivenSimulator(classifier, max_events=10000)
        # This should complete without hitting the limit for valid circuits
        result = sim.simulate(99)
        assert result["events_processed"] < 10000


# ============================================================
# SimulationEvent Tests
# ============================================================


class TestSimulationEvent:
    """Tests for the SimulationEvent data class."""

    def test_ordering(self):
        e1 = SimulationEvent(1.0, 0, "w1", True)
        e2 = SimulationEvent(2.0, 1, "w2", False)
        assert e1 < e2

    def test_same_time_sequence_ordering(self):
        e1 = SimulationEvent(1.0, 0, "w1", True)
        e2 = SimulationEvent(1.0, 1, "w2", False)
        assert e1 < e2


# ============================================================
# WaveformCapture Tests
# ============================================================


class TestWaveformCapture:
    """Tests for waveform capture and ASCII rendering."""

    def test_record_and_render(self, classifier):
        wf = WaveformCapture(classifier)
        wf.record("in_0", 0.0, True)
        wf.record("in_0", 5.0, False)
        output = wf.render_ascii(width=40)
        assert "Signal" in output
        assert "in_0" in output

    def test_empty_waveform(self, classifier):
        wf = WaveformCapture(classifier)
        output = wf.render_ascii()
        assert "no signal transitions" in output


# ============================================================
# CriticalPathAnalyzer Tests
# ============================================================


class TestCriticalPathAnalyzer:
    """Tests for static timing analysis."""

    def test_analyze_returns_critical_delay(self, classifier):
        analyzer = CriticalPathAnalyzer(classifier)
        result = analyzer.analyze()
        assert result["critical_delay_ns"] > 0

    def test_analyze_returns_gate_count(self, classifier):
        analyzer = CriticalPathAnalyzer(classifier)
        result = analyzer.analyze()
        assert result["total_gates"] == classifier.gate_count

    def test_analyze_returns_max_frequency(self, classifier):
        analyzer = CriticalPathAnalyzer(classifier)
        result = analyzer.analyze()
        assert result["max_frequency_ghz"] > 0

    def test_analyze_critical_path_length(self, classifier):
        analyzer = CriticalPathAnalyzer(classifier)
        result = analyzer.analyze()
        assert result["critical_path_length"] > 0

    def test_analyze_arrival_times(self, classifier):
        analyzer = CriticalPathAnalyzer(classifier)
        result = analyzer.analyze()
        assert "mod3_out" in result["arrival_times"]
        assert "mod5_out" in result["arrival_times"]
        assert "fizzbuzz_out" in result["arrival_times"]

    def test_fizzbuzz_arrival_exceeds_components(self, classifier):
        """FizzBuzz output arrival must exceed both mod3 and mod5."""
        analyzer = CriticalPathAnalyzer(classifier)
        result = analyzer.analyze()
        fb_arrival = result["arrival_times"]["fizzbuzz_out"]
        m3_arrival = result["arrival_times"]["mod3_out"]
        m5_arrival = result["arrival_times"]["mod5_out"]
        # fizzbuzz = AND(mod3, mod5), so it must arrive after both
        assert fb_arrival >= m3_arrival
        assert fb_arrival >= m5_arrival


# ============================================================
# CircuitDashboard Tests
# ============================================================


class TestCircuitDashboard:
    """Tests for the ASCII dashboard renderer."""

    def test_render_no_results(self, classifier):
        output = CircuitDashboard.render(classifier, [])
        assert "FIZZGATE" in output
        assert "CIRCUIT TOPOLOGY" in output

    def test_render_with_results(self, classifier):
        results = [classifier.classify(n) for n in range(1, 11)]
        output = CircuitDashboard.render(classifier, results)
        assert "RECENT SIMULATION RESULTS" in output

    def test_render_contains_gate_counts(self, classifier):
        output = CircuitDashboard.render(classifier, [])
        assert "Total gates" in output

    def test_render_contains_critical_path(self, classifier):
        output = CircuitDashboard.render(classifier, [])
        assert "CRITICAL PATH" in output

    def test_render_custom_width(self, classifier):
        output = CircuitDashboard.render(classifier, [], width=80)
        for line in output.split("\n"):
            assert len(line) <= 80


# ============================================================
# CircuitMiddleware Tests
# ============================================================


class TestCircuitMiddleware:
    """Tests for the FizzGate middleware integration."""

    def _make_context(self, number: int) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-session")

    def _make_next_handler(self) -> Callable[[ProcessingContext], ProcessingContext]:
        def handler(ctx: ProcessingContext) -> ProcessingContext:
            return ctx
        return handler

    def test_middleware_name(self):
        mw = CircuitMiddleware()
        assert mw.get_name() == "FizzGateCircuitSimulator"

    def test_middleware_priority(self):
        mw = CircuitMiddleware()
        assert mw.get_priority() == -6

    def test_middleware_process_attaches_metadata(self):
        mw = CircuitMiddleware()
        ctx = self._make_context(15)
        result = mw.process(ctx, self._make_next_handler())
        assert "fizzgate" in result.metadata
        assert result.metadata["fizzgate"]["label"] == "FizzBuzz"

    def test_middleware_process_fizz(self):
        mw = CircuitMiddleware()
        ctx = self._make_context(9)
        result = mw.process(ctx, self._make_next_handler())
        assert result.metadata["fizzgate"]["label"] == "Fizz"

    def test_middleware_process_buzz(self):
        mw = CircuitMiddleware()
        ctx = self._make_context(10)
        result = mw.process(ctx, self._make_next_handler())
        assert result.metadata["fizzgate"]["label"] == "Buzz"

    def test_middleware_process_number(self):
        mw = CircuitMiddleware()
        ctx = self._make_context(7)
        result = mw.process(ctx, self._make_next_handler())
        assert result.metadata["fizzgate"]["label"] == "7"

    def test_middleware_skips_out_of_range(self):
        mw = CircuitMiddleware()
        ctx = self._make_context(200)
        result = mw.process(ctx, self._make_next_handler())
        assert "fizzgate" not in result.metadata

    def test_middleware_results_accumulate(self):
        mw = CircuitMiddleware()
        for n in [3, 5, 15]:
            ctx = self._make_context(n)
            mw.process(ctx, self._make_next_handler())
        assert len(mw.results) == 3

    def test_middleware_classifier_accessible(self):
        mw = CircuitMiddleware()
        assert mw.classifier is not None
        assert isinstance(mw.classifier, FizzBuzzClassifier)


# ============================================================
# Exception Tests
# ============================================================


class TestCircuitExceptions:
    """Tests for the FizzGate exception hierarchy."""

    def test_circuit_simulation_error(self):
        exc = CircuitSimulationError("test error")
        assert "test error" in str(exc)
        assert exc.error_code == "EFP-CKT0"

    def test_circuit_topology_error(self):
        exc = CircuitTopologyError("bad topology")
        assert "bad topology" in str(exc)
        assert exc.error_code == "EFP-CKT1"

    def test_circuit_steady_state_error(self):
        exc = CircuitSteadyStateError("did not converge")
        assert "did not converge" in str(exc)
        assert exc.error_code == "EFP-CKT2"

    def test_circuit_timing_violation_error(self):
        exc = CircuitTimingViolationError(600.0, 500.0, 42)
        assert "600.0" in str(exc)
        assert "500.0" in str(exc)
        assert exc.error_code == "EFP-CKT3"
        assert exc.number == 42

    def test_inheritance(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(CircuitSimulationError, FizzBuzzError)
        assert issubclass(CircuitTopologyError, CircuitSimulationError)
        assert issubclass(CircuitSteadyStateError, CircuitSimulationError)
        assert issubclass(CircuitTimingViolationError, CircuitSimulationError)
