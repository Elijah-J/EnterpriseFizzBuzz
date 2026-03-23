"""
Enterprise FizzBuzz Platform - FizzGate Digital Logic Circuit Simulator

Implements gate-level digital logic simulation for FizzBuzz divisibility
checking. Rather than relying on the modulo operator — a high-level
abstraction that obscures the underlying computational complexity — this
module constructs combinational logic circuits from fundamental gates
(AND, OR, NOT, XOR, NAND, NOR) to determine divisibility by 3 and 5.

The simulator operates as an event-driven engine with a priority-queue
event scheduler, propagation delay modeling, steady-state detection,
and waveform capture. A critical path analyzer provides static timing
analysis to identify the longest combinational path through the circuit,
ensuring that all outputs are valid within the configured timing budget.

This approach mirrors real hardware verification workflows used in
ASIC and FPGA design, where functional correctness of arithmetic units
must be established at the gate level before synthesis and place-and-route.
The FizzBuzz divisibility problem is no different: if the modulo-3 and
modulo-5 circuits are not formally verified at the structural level,
any higher-level correctness claim is built on unverified foundations.
"""

from __future__ import annotations

import heapq
import logging
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CircuitSimulationError,
    CircuitSteadyStateError,
    CircuitTopologyError,
    CircuitTimingViolationError,
)
from enterprise_fizzbuzz.domain.interfaces import IEventBus, IMiddleware
from enterprise_fizzbuzz.domain.models import Event, EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Gate Types
# ============================================================


class GateType(Enum):
    """Fundamental digital logic gate types.

    These six gate types form a functionally complete set from which
    any combinational logic function can be constructed. In practice,
    NAND alone is functionally complete (as is NOR), but providing all
    six improves readability of synthesized circuits and allows the
    critical path analyzer to assign realistic per-gate delays.
    """

    AND = auto()
    OR = auto()
    NOT = auto()
    XOR = auto()
    NAND = auto()
    NOR = auto()


# Per-gate propagation delays in nanoseconds, based on typical
# standard-cell library characterization for a 28nm process node.
_GATE_DELAYS_NS: dict[GateType, float] = {
    GateType.AND: 1.2,
    GateType.OR: 1.3,
    GateType.NOT: 0.8,
    GateType.XOR: 2.1,
    GateType.NAND: 1.0,
    GateType.NOR: 1.1,
}


# ============================================================
# Wire
# ============================================================


class Wire:
    """A single-bit signal wire connecting gate outputs to gate inputs.

    Each wire carries a boolean logic level and maintains a history of
    transitions for waveform capture. Wires are the fundamental
    interconnect primitive in the circuit graph.
    """

    def __init__(self, name: str, initial_value: bool = False) -> None:
        self.name = name
        self._value = initial_value
        self._history: list[tuple[float, bool]] = [(0.0, initial_value)]
        self._fanout: list[Gate] = []

    @property
    def value(self) -> bool:
        return self._value

    def drive(self, new_value: bool, timestamp: float) -> bool:
        """Set the wire value at the given timestamp.

        Returns True if the value changed (a transition occurred),
        False if the wire was already at the driven value.
        """
        if new_value != self._value:
            self._value = new_value
            self._history.append((timestamp, new_value))
            return True
        return False

    def add_fanout(self, gate: Gate) -> None:
        """Register a gate that reads from this wire."""
        self._fanout.append(gate)

    @property
    def fanout(self) -> list[Gate]:
        return list(self._fanout)

    @property
    def history(self) -> list[tuple[float, bool]]:
        return list(self._history)

    def reset(self) -> None:
        """Reset wire to initial state."""
        self._value = False
        self._history = [(0.0, False)]

    def __repr__(self) -> str:
        return f"Wire({self.name!r}, value={self._value})"


# ============================================================
# Gate
# ============================================================


class Gate:
    """A single logic gate with typed inputs, one output, and propagation delay.

    Gates are the fundamental computation primitives. Each gate reads
    from one or more input wires, applies its boolean function, and
    drives its output wire after the configured propagation delay.
    """

    def __init__(
        self,
        name: str,
        gate_type: GateType,
        inputs: list[Wire],
        output: Wire,
        delay_ns: Optional[float] = None,
    ) -> None:
        if gate_type == GateType.NOT and len(inputs) != 1:
            raise CircuitTopologyError(
                f"NOT gate '{name}' requires exactly 1 input, got {len(inputs)}"
            )
        if gate_type != GateType.NOT and len(inputs) < 2:
            raise CircuitTopologyError(
                f"{gate_type.name} gate '{name}' requires at least 2 inputs, "
                f"got {len(inputs)}"
            )

        self.name = name
        self.gate_type = gate_type
        self.inputs = inputs
        self.output = output
        self.delay_ns = delay_ns if delay_ns is not None else _GATE_DELAYS_NS[gate_type]

        # Register this gate as a fanout of each input wire
        for wire in inputs:
            wire.add_fanout(self)

    def evaluate(self) -> bool:
        """Compute the gate's output from its current input values."""
        vals = [w.value for w in self.inputs]

        if self.gate_type == GateType.AND:
            return all(vals)
        elif self.gate_type == GateType.OR:
            return any(vals)
        elif self.gate_type == GateType.NOT:
            return not vals[0]
        elif self.gate_type == GateType.XOR:
            result = False
            for v in vals:
                result = result ^ v
            return result
        elif self.gate_type == GateType.NAND:
            return not all(vals)
        elif self.gate_type == GateType.NOR:
            return not any(vals)
        else:
            raise CircuitSimulationError(
                f"Unknown gate type: {self.gate_type}"
            )

    def __repr__(self) -> str:
        input_names = ", ".join(w.name for w in self.inputs)
        return f"Gate({self.name!r}, {self.gate_type.name}, [{input_names}] -> {self.output.name})"


# ============================================================
# Composite Circuits: Adders
# ============================================================


class HalfAdder:
    """A half adder circuit built from XOR and AND gates.

    Computes:
        sum  = A XOR B
        carry = A AND B

    The half adder is the simplest arithmetic building block. It handles
    the addition of two single-bit operands but cannot accommodate a
    carry-in from a previous stage, which limits its use to the least
    significant bit position of a multi-bit adder.
    """

    def __init__(
        self,
        prefix: str,
        input_a: Wire,
        input_b: Wire,
    ) -> None:
        self.sum_out = Wire(f"{prefix}_sum")
        self.carry_out = Wire(f"{prefix}_carry")

        self.xor_gate = Gate(
            f"{prefix}_xor", GateType.XOR,
            [input_a, input_b], self.sum_out,
        )
        self.and_gate = Gate(
            f"{prefix}_and", GateType.AND,
            [input_a, input_b], self.carry_out,
        )
        self.gates = [self.xor_gate, self.and_gate]
        self.wires = [self.sum_out, self.carry_out]


class FullAdder:
    """A full adder circuit built from two half adders and an OR gate.

    Computes:
        sum   = A XOR B XOR Cin
        carry = (A AND B) OR (Cin AND (A XOR B))

    The full adder handles carry propagation, making it suitable for
    chaining into a ripple-carry adder to perform multi-bit addition.
    """

    def __init__(
        self,
        prefix: str,
        input_a: Wire,
        input_b: Wire,
        carry_in: Wire,
    ) -> None:
        self.ha1 = HalfAdder(f"{prefix}_ha1", input_a, input_b)
        self.ha2 = HalfAdder(f"{prefix}_ha2", self.ha1.sum_out, carry_in)

        self.sum_out = self.ha2.sum_out
        self.carry_out = Wire(f"{prefix}_cout")

        self.or_gate = Gate(
            f"{prefix}_or", GateType.OR,
            [self.ha1.carry_out, self.ha2.carry_out], self.carry_out,
        )

        self.gates = self.ha1.gates + self.ha2.gates + [self.or_gate]
        self.wires = self.ha1.wires + self.ha2.wires + [self.carry_out]


class RippleCarryAdder:
    """An N-bit ripple-carry adder composed of full adders.

    Adds two N-bit binary numbers A and B with an optional carry-in,
    producing an N-bit sum and a carry-out. The carry propagates
    sequentially through each bit position, which creates the
    characteristic critical path that limits operating frequency.

    For FizzBuzz purposes, this adder is used inside the modulo
    circuit to perform repeated subtraction for divisibility checking.
    """

    def __init__(
        self,
        prefix: str,
        bits_a: list[Wire],
        bits_b: list[Wire],
        carry_in: Wire,
    ) -> None:
        if len(bits_a) != len(bits_b):
            raise CircuitTopologyError(
                f"RippleCarryAdder '{prefix}' requires equal-width operands, "
                f"got {len(bits_a)} and {len(bits_b)}"
            )
        self.width = len(bits_a)
        self.sum_bits: list[Wire] = []
        self.gates: list[Gate] = []
        self.wires: list[Wire] = []

        current_carry = carry_in
        self.full_adders: list[FullAdder] = []

        for i in range(self.width):
            fa = FullAdder(
                f"{prefix}_fa{i}",
                bits_a[i],
                bits_b[i],
                current_carry,
            )
            self.full_adders.append(fa)
            self.sum_bits.append(fa.sum_out)
            self.gates.extend(fa.gates)
            self.wires.extend(fa.wires)
            current_carry = fa.carry_out

        self.carry_out = current_carry


# ============================================================
# Modulo Circuit
# ============================================================


class ModuloCircuit:
    """Combinational circuit that computes N mod D == 0 using minterm logic.

    For a given divisor D and bit-width W, the circuit enumerates all
    integers in [0, 2^W) that are divisible by D, converts each to a
    binary pattern, and constructs a sum-of-products (SOP) expression.
    Each product term (minterm) is an AND gate over the input bits
    (complemented or uncomplemented), and the minterms are OR-ed
    together to produce the final divisibility output.

    This is the canonical two-level AND-OR synthesis approach used in
    PLA (Programmable Logic Array) structures. While not area-optimal
    for large bit-widths, it is functionally transparent and produces
    a flat circuit topology that is straightforward to verify.
    """

    def __init__(
        self,
        prefix: str,
        input_bits: list[Wire],
        divisor: int,
    ) -> None:
        if divisor < 2:
            raise CircuitTopologyError(
                f"ModuloCircuit '{prefix}' requires divisor >= 2, got {divisor}"
            )

        self.prefix = prefix
        self.divisor = divisor
        self.width = len(input_bits)
        self.input_bits = input_bits
        self.gates: list[Gate] = []
        self.wires: list[Wire] = []
        self.minterm_count = 0

        # Create NOT gates for each input bit (complemented literals)
        self._not_wires: list[Wire] = []
        for i, wire in enumerate(input_bits):
            not_wire = Wire(f"{prefix}_not{i}")
            not_gate = Gate(
                f"{prefix}_inv{i}", GateType.NOT,
                [wire], not_wire,
            )
            self._not_wires.append(not_wire)
            self.gates.append(not_gate)
            self.wires.append(not_wire)

        # Enumerate minterms: values in [0, 2^W) divisible by divisor
        max_val = 1 << self.width
        minterms: list[int] = [
            v for v in range(0, max_val, divisor)
        ]
        self.minterm_count = len(minterms)

        if not minterms:
            # No values are divisible — output is always False
            self.output = Wire(f"{prefix}_out")
            self.wires.append(self.output)
            return

        # Build minterm AND gates
        minterm_wires: list[Wire] = []
        for idx, value in enumerate(minterms):
            literals: list[Wire] = []
            for bit_pos in range(self.width):
                if (value >> bit_pos) & 1:
                    literals.append(input_bits[bit_pos])
                else:
                    literals.append(self._not_wires[bit_pos])

            if len(literals) == 1:
                # Single-literal minterm — no AND gate needed
                minterm_wires.append(literals[0])
            else:
                mt_wire = Wire(f"{prefix}_mt{idx}")
                mt_gate = Gate(
                    f"{prefix}_and_mt{idx}", GateType.AND,
                    literals, mt_wire,
                )
                minterm_wires.append(mt_wire)
                self.gates.append(mt_gate)
                self.wires.append(mt_wire)

        # OR all minterms together
        if len(minterm_wires) == 1:
            self.output = minterm_wires[0]
        else:
            self.output = Wire(f"{prefix}_out")
            self.wires.append(self.output)
            # Build a balanced OR tree to minimize depth
            self._build_or_tree(prefix, minterm_wires, self.output)

    def _build_or_tree(
        self,
        prefix: str,
        inputs: list[Wire],
        output: Wire,
    ) -> None:
        """Build a balanced OR tree reducing all inputs to one output."""
        if len(inputs) <= 4:
            # Small enough for a single wide OR gate
            gate = Gate(
                f"{prefix}_or_final", GateType.OR,
                inputs, output,
            )
            self.gates.append(gate)
            return

        # Split into groups of ~4, OR each group, then recurse
        group_size = 4
        group_outputs: list[Wire] = []
        for g_idx in range(0, len(inputs), group_size):
            group = inputs[g_idx:g_idx + group_size]
            if len(group) == 1:
                group_outputs.append(group[0])
            else:
                g_wire = Wire(f"{prefix}_or_g{g_idx}")
                g_gate = Gate(
                    f"{prefix}_or_grp{g_idx}", GateType.OR,
                    group, g_wire,
                )
                group_outputs.append(g_wire)
                self.gates.append(g_gate)
                self.wires.append(g_wire)

        if len(group_outputs) == 1:
            # Need to connect the single group output to the final output
            buf_gate = Gate(
                f"{prefix}_or_buf", GateType.OR,
                [group_outputs[0], group_outputs[0]], output,
            )
            self.gates.append(buf_gate)
        elif len(group_outputs) <= 4:
            final_gate = Gate(
                f"{prefix}_or_final", GateType.OR,
                group_outputs, output,
            )
            self.gates.append(final_gate)
        else:
            self._build_or_tree(f"{prefix}_l2", group_outputs, output)


# ============================================================
# FizzBuzz Classifier
# ============================================================


class FizzBuzzClassifier:
    """Top-level circuit combining mod-3 and mod-5 divisibility checkers.

    The classifier accepts a 7-bit binary input (sufficient for values
    0-127, covering the standard FizzBuzz range 1-100) and produces
    three boolean outputs:

        - div_by_3: True if the input is divisible by 3
        - div_by_5: True if the input is divisible by 5
        - div_by_15: True if divisible by both (AND of the above)

    These outputs map directly to the FizzBuzz classification:
        - div_by_15  -> "FizzBuzz"
        - div_by_3   -> "Fizz"
        - div_by_5   -> "Buzz"
        - none       -> str(n)
    """

    BIT_WIDTH = 7  # Supports values 0-127

    def __init__(self) -> None:
        # Create input wires (LSB first)
        self.input_bits: list[Wire] = [
            Wire(f"in_{i}") for i in range(self.BIT_WIDTH)
        ]

        # Build modulo subcircuits
        self.mod3 = ModuloCircuit("mod3", self.input_bits, 3)
        self.mod5 = ModuloCircuit("mod5", self.input_bits, 5)

        # FizzBuzz output = div_by_3 AND div_by_5
        self.fizzbuzz_wire = Wire("fizzbuzz_out")
        self.fizzbuzz_gate = Gate(
            "fizzbuzz_and", GateType.AND,
            [self.mod3.output, self.mod5.output],
            self.fizzbuzz_wire,
        )

        # Collect all gates, wires for analysis
        self.all_gates: list[Gate] = (
            self.mod3.gates + self.mod5.gates + [self.fizzbuzz_gate]
        )
        self.all_wires: list[Wire] = (
            self.input_bits
            + self.mod3.wires
            + self.mod5.wires
            + [self.fizzbuzz_wire]
        )

        self._gate_count_by_type: dict[GateType, int] = defaultdict(int)
        for g in self.all_gates:
            self._gate_count_by_type[g.gate_type] += 1

    def load_input(self, number: int) -> None:
        """Load an integer onto the input wires in binary (LSB first)."""
        if number < 0 or number >= (1 << self.BIT_WIDTH):
            raise CircuitSimulationError(
                f"Input {number} out of range for {self.BIT_WIDTH}-bit circuit "
                f"[0, {(1 << self.BIT_WIDTH) - 1}]"
            )
        for i in range(self.BIT_WIDTH):
            self.input_bits[i]._value = bool((number >> i) & 1)

    def classify(self, number: int) -> dict[str, Any]:
        """Classify a number through the gate-level circuit.

        Returns a dict with the classification result and circuit metadata.
        """
        self.load_input(number)

        # Evaluate all gates in topological order
        evaluated: set[str] = set()
        self._propagate_all(evaluated)

        div3 = self.mod3.output.value
        div5 = self.mod5.output.value
        div15 = self.fizzbuzz_wire.value

        if div3 and div5:
            label = "FizzBuzz"
        elif div3:
            label = "Fizz"
        elif div5:
            label = "Buzz"
        else:
            label = str(number)

        return {
            "number": number,
            "label": label,
            "div_by_3": div3,
            "div_by_5": div5,
            "div_by_15": div15,
            "gate_evaluations": len(evaluated),
            "binary": format(number, f"0{self.BIT_WIDTH}b"),
        }

    def _propagate_all(self, evaluated: set[str]) -> None:
        """Evaluate all gates via topological traversal."""
        for gate in self._topological_sort():
            result = gate.evaluate()
            gate.output._value = result
            evaluated.add(gate.name)

    def _topological_sort(self) -> list[Gate]:
        """Return gates in topological order (inputs before outputs)."""
        # Map wire name -> gate that drives it
        wire_driver: dict[str, Gate] = {}
        for g in self.all_gates:
            wire_driver[g.output.name] = g

        # Build adjacency: gate -> set of gates it depends on
        in_degree: dict[str, int] = {g.name: 0 for g in self.all_gates}
        dependents: dict[str, list[str]] = {g.name: [] for g in self.all_gates}
        gate_map: dict[str, Gate] = {g.name: g for g in self.all_gates}

        for g in self.all_gates:
            for inp in g.inputs:
                driver = wire_driver.get(inp.name)
                if driver is not None:
                    in_degree[g.name] += 1
                    dependents[driver.name].append(g.name)

        # Kahn's algorithm
        queue = [g.name for g in self.all_gates if in_degree[g.name] == 0]
        result: list[Gate] = []
        while queue:
            name = queue.pop(0)
            result.append(gate_map[name])
            for dep in dependents[name]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        if len(result) != len(self.all_gates):
            raise CircuitTopologyError(
                "Combinational loop detected in FizzBuzz classifier circuit. "
                "This indicates a synthesis error in the minterm logic."
            )
        return result

    @property
    def gate_count(self) -> int:
        return len(self.all_gates)

    @property
    def wire_count(self) -> int:
        return len(self.all_wires)

    @property
    def gate_count_by_type(self) -> dict[GateType, int]:
        return dict(self._gate_count_by_type)

    def reset(self) -> None:
        """Reset all wires to their initial state."""
        for w in self.all_wires:
            w.reset()


# ============================================================
# Event-Driven Simulator
# ============================================================


@dataclass(order=True)
class SimulationEvent:
    """A scheduled event in the event-driven simulation.

    Events are ordered by timestamp (earliest first), with tie-breaking
    on sequence number to maintain insertion order for simultaneous events.
    """

    timestamp: float
    sequence: int = field(compare=True)
    wire_name: str = field(compare=False)
    new_value: bool = field(compare=False)
    source_gate: str = field(compare=False, default="")


class EventDrivenSimulator:
    """Discrete-event simulator with propagation delay and steady-state detection.

    Models signal propagation through the circuit with realistic gate
    delays. Events are processed from a priority queue (min-heap) ordered
    by timestamp. The simulator detects steady state when no further
    events remain in the queue, indicating that all signals have settled.

    The maximum event count is configurable to prevent runaway simulation
    in the presence of combinational loops (which should not exist in a
    correctly synthesized circuit, but defense in depth is prudent).
    """

    def __init__(
        self,
        classifier: FizzBuzzClassifier,
        max_events: int = 10000,
        glitch_threshold_ns: float = 5.0,
    ) -> None:
        self._classifier = classifier
        self._max_events = max_events
        self._glitch_threshold_ns = glitch_threshold_ns
        self._event_queue: list[SimulationEvent] = []
        self._sequence = 0
        self._events_processed = 0
        self._glitch_count = 0
        self._steady_state_time = 0.0
        self._waveform: Optional[WaveformCapture] = None

    def simulate(self, number: int, capture_waveform: bool = False) -> dict[str, Any]:
        """Run a full event-driven simulation for the given input.

        Loads the input onto the circuit, schedules initial gate
        evaluations, and processes events until steady state.
        """
        self._event_queue.clear()
        self._sequence = 0
        self._events_processed = 0
        self._glitch_count = 0
        self._waveform = WaveformCapture(self._classifier) if capture_waveform else None

        # Load input bits
        self._classifier.load_input(number)

        # Build wire->driver map
        wire_driver: dict[str, Gate] = {}
        for g in self._classifier.all_gates:
            wire_driver[g.output.name] = g

        # Schedule initial events: evaluate all gates in topological order
        # and schedule events for any outputs that differ from current wire state
        for gate in self._classifier._topological_sort():
            new_val = gate.evaluate()
            if new_val != gate.output.value:
                self._schedule(gate.delay_ns, gate.output.name, new_val, gate.name)

        # Process events
        while self._event_queue:
            if self._events_processed >= self._max_events:
                raise CircuitSteadyStateError(
                    f"Simulation exceeded {self._max_events} events for input {number}. "
                    f"The circuit may contain an oscillation or the event limit is too low."
                )

            event = heapq.heappop(self._event_queue)
            self._events_processed += 1

            # Find the wire
            target_wire = None
            for w in self._classifier.all_wires:
                if w.name == event.wire_name:
                    target_wire = w
                    break

            if target_wire is None:
                continue

            changed = target_wire.drive(event.new_value, event.timestamp)

            if self._waveform is not None:
                self._waveform.record(event.wire_name, event.timestamp, event.new_value)

            if changed:
                # Check for glitch
                if len(target_wire.history) >= 3:
                    last_three = target_wire.history[-3:]
                    dt = last_three[2][0] - last_three[1][0]
                    if dt < self._glitch_threshold_ns:
                        self._glitch_count += 1

                # Schedule downstream gate evaluations
                for fanout_gate in target_wire.fanout:
                    new_val = fanout_gate.evaluate()
                    if new_val != fanout_gate.output.value:
                        self._schedule(
                            event.timestamp + fanout_gate.delay_ns,
                            fanout_gate.output.name,
                            new_val,
                            fanout_gate.name,
                        )

            self._steady_state_time = event.timestamp

        # Read final outputs
        div3 = self._classifier.mod3.output.value
        div5 = self._classifier.mod5.output.value
        div15 = self._classifier.fizzbuzz_wire.value

        if div3 and div5:
            label = "FizzBuzz"
        elif div3:
            label = "Fizz"
        elif div5:
            label = "Buzz"
        else:
            label = str(number)

        result = {
            "number": number,
            "label": label,
            "div_by_3": div3,
            "div_by_5": div5,
            "div_by_15": div15,
            "events_processed": self._events_processed,
            "steady_state_ns": self._steady_state_time,
            "glitch_count": self._glitch_count,
            "binary": format(number, f"0{self._classifier.BIT_WIDTH}b"),
        }

        if self._waveform is not None:
            result["waveform"] = self._waveform

        return result

    def _schedule(
        self,
        timestamp: float,
        wire_name: str,
        new_value: bool,
        source_gate: str,
    ) -> None:
        """Add an event to the priority queue."""
        event = SimulationEvent(
            timestamp=timestamp,
            sequence=self._sequence,
            wire_name=wire_name,
            new_value=new_value,
            source_gate=source_gate,
        )
        heapq.heappush(self._event_queue, event)
        self._sequence += 1


# ============================================================
# Waveform Capture
# ============================================================


class WaveformCapture:
    """Captures signal transitions for ASCII timing diagram rendering.

    Records all wire value changes during simulation and renders them
    as an ASCII waveform diagram suitable for terminal display. The
    waveform format follows standard VCD (Value Change Dump) conventions,
    adapted for text-mode rendering.
    """

    def __init__(self, classifier: FizzBuzzClassifier) -> None:
        self._transitions: dict[str, list[tuple[float, bool]]] = defaultdict(list)
        self._classifier = classifier
        # Track key signals for display
        self._display_signals = (
            [f"in_{i}" for i in range(classifier.BIT_WIDTH)]
            + ["mod3_out", "mod5_out", "fizzbuzz_out"]
        )

    def record(self, wire_name: str, timestamp: float, value: bool) -> None:
        """Record a signal transition."""
        self._transitions[wire_name].append((timestamp, value))

    def render_ascii(self, width: int = 60) -> str:
        """Render an ASCII timing diagram.

        Each signal is shown as a row with high/low levels represented
        by box-drawing characters. Time advances left to right.
        """
        if not self._transitions:
            return "  (no signal transitions recorded)"

        # Determine time range
        all_times = []
        for transitions in self._transitions.values():
            for t, _ in transitions:
                all_times.append(t)
        if not all_times:
            return "  (no signal transitions recorded)"

        max_time = max(all_times) if all_times else 1.0
        if max_time == 0:
            max_time = 1.0

        signal_width = width - 20  # Reserve space for signal names
        if signal_width < 10:
            signal_width = 10

        lines = []
        lines.append(f"  {'Signal':<16} {'Waveform'}")
        lines.append(f"  {'=' * 16} {'=' * signal_width}")

        # Time axis
        time_labels = f"  {'Time (ns)':<16} "
        step = max_time / 4
        for i in range(5):
            t = step * i
            lbl = f"{t:.1f}"
            time_labels += lbl
            padding = max(0, (signal_width // 4) - len(lbl))
            time_labels += " " * padding
        lines.append(time_labels[:width])

        # Render each display signal
        for sig_name in self._display_signals:
            transitions = self._transitions.get(sig_name, [])
            wave = self._render_signal(sig_name, transitions, signal_width, max_time)
            lines.append(f"  {sig_name:<16} {wave}")

        return "\n".join(lines)

    def _render_signal(
        self,
        name: str,
        transitions: list[tuple[float, bool]],
        width: int,
        max_time: float,
    ) -> str:
        """Render a single signal's waveform as ASCII characters."""
        # Sort transitions by time
        transitions = sorted(transitions, key=lambda x: x[0])

        # Sample value at each column position
        chars = []
        for col in range(width):
            t_at_col = (col / max(width - 1, 1)) * max_time
            val = False
            for t, v in transitions:
                if t <= t_at_col:
                    val = v
                else:
                    break
            chars.append("\u2580" if val else "\u2500")

        return "".join(chars)


# ============================================================
# Critical Path Analyzer
# ============================================================


class CriticalPathAnalyzer:
    """Static timing analysis engine for combinational circuits.

    Computes the critical path — the longest delay path from any
    primary input to any primary output — using a topological
    traversal with arrival time propagation. This is the standard
    STA (Static Timing Analysis) approach used in EDA tools.

    The critical path delay determines the maximum operating frequency
    of the circuit: f_max = 1 / T_critical. For the FizzBuzz classifier,
    this represents the minimum time required for a divisibility check
    to produce valid outputs after input bits are asserted.
    """

    def __init__(self, classifier: FizzBuzzClassifier) -> None:
        self._classifier = classifier

    def analyze(self) -> dict[str, Any]:
        """Perform static timing analysis and return results."""
        # Build wire -> driver gate map
        wire_driver: dict[str, Gate] = {}
        for g in self._classifier.all_gates:
            wire_driver[g.output.name] = g

        # Compute arrival times at each gate output
        arrival: dict[str, float] = {}
        path_from: dict[str, Optional[str]] = {}
        input_names = {w.name for w in self._classifier.input_bits}

        for gate in self._classifier._topological_sort():
            max_input_arrival = 0.0
            max_input_wire = None
            for inp in gate.inputs:
                if inp.name in input_names:
                    arr = 0.0
                elif inp.name in arrival:
                    arr = arrival[inp.name]
                else:
                    arr = 0.0
                if arr >= max_input_arrival:
                    max_input_arrival = arr
                    max_input_wire = inp.name

            arrival[gate.output.name] = max_input_arrival + gate.delay_ns
            path_from[gate.output.name] = max_input_wire

        # Find the output with maximum arrival time
        outputs = {
            "mod3_out": self._classifier.mod3.output.name,
            "mod5_out": self._classifier.mod5.output.name,
            "fizzbuzz_out": self._classifier.fizzbuzz_wire.name,
        }

        critical_delay = 0.0
        critical_output = ""
        for label, wire_name in outputs.items():
            d = arrival.get(wire_name, 0.0)
            if d >= critical_delay:
                critical_delay = d
                critical_output = label

        # Trace back the critical path
        critical_path_gates: list[str] = []
        current = outputs.get(critical_output, "")
        visited: set[str] = set()
        while current and current not in input_names and current not in visited:
            visited.add(current)
            driver = wire_driver.get(current)
            if driver:
                critical_path_gates.append(driver.name)
                # Find the input with the highest arrival time
                best_input = None
                best_arr = -1.0
                for inp in driver.inputs:
                    arr = arrival.get(inp.name, 0.0)
                    if arr > best_arr:
                        best_arr = arr
                        best_input = inp.name
                current = best_input
            else:
                break

        critical_path_gates.reverse()

        # Gate level statistics
        total_delay_by_type: dict[str, float] = defaultdict(float)
        for g in self._classifier.all_gates:
            total_delay_by_type[g.gate_type.name] += g.delay_ns

        return {
            "critical_delay_ns": round(critical_delay, 2),
            "critical_output": critical_output,
            "critical_path_length": len(critical_path_gates),
            "critical_path_gates": critical_path_gates,
            "max_frequency_ghz": round(1.0 / critical_delay, 4) if critical_delay > 0 else float("inf"),
            "total_gates": self._classifier.gate_count,
            "total_wires": self._classifier.wire_count,
            "delay_by_gate_type": dict(total_delay_by_type),
            "arrival_times": {
                label: round(arrival.get(wire_name, 0.0), 2)
                for label, wire_name in outputs.items()
            },
        }


# ============================================================
# Circuit Dashboard
# ============================================================


class CircuitDashboard:
    """ASCII dashboard renderer for FizzGate circuit analysis.

    Displays circuit topology summary, gate counts by type, critical
    path analysis, and recent simulation results in a formatted
    terminal dashboard.
    """

    @staticmethod
    def render(
        classifier: FizzBuzzClassifier,
        simulation_results: list[dict[str, Any]],
        width: int = 60,
    ) -> str:
        """Render the complete FizzGate dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        spacer = "|" + " " * (width - 2) + "|"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "|  " + text.ljust(width - 4) + "|"

        lines.append(border)
        lines.append(center("FIZZGATE DIGITAL LOGIC CIRCUIT DASHBOARD"))
        lines.append(center("Gate-Level Divisibility Verification"))
        lines.append(border)

        # Circuit topology
        lines.append(spacer)
        lines.append(left("CIRCUIT TOPOLOGY"))
        lines.append(left("-" * (width - 6)))
        lines.append(left(f"Input width:      {classifier.BIT_WIDTH} bits"))
        lines.append(left(f"Input range:      0 - {(1 << classifier.BIT_WIDTH) - 1}"))
        lines.append(left(f"Total gates:      {classifier.gate_count}"))
        lines.append(left(f"Total wires:      {classifier.wire_count}"))
        lines.append(left(f"Mod-3 minterms:   {classifier.mod3.minterm_count}"))
        lines.append(left(f"Mod-5 minterms:   {classifier.mod5.minterm_count}"))
        lines.append(spacer)

        # Gate count by type
        lines.append(left("GATE COUNT BY TYPE"))
        lines.append(left("-" * (width - 6)))
        for gate_type in GateType:
            count = classifier.gate_count_by_type.get(gate_type, 0)
            if count > 0:
                bar_len = min(count, width - 30)
                bar = "\u2588" * bar_len
                lines.append(left(f"  {gate_type.name:<6} {count:>4}  {bar}"))
        lines.append(spacer)

        # Critical path analysis
        analyzer = CriticalPathAnalyzer(classifier)
        timing = analyzer.analyze()
        lines.append(left("CRITICAL PATH ANALYSIS"))
        lines.append(left("-" * (width - 6)))
        lines.append(left(f"Critical delay:   {timing['critical_delay_ns']} ns"))
        lines.append(left(f"Critical output:  {timing['critical_output']}"))
        lines.append(left(f"Path depth:       {timing['critical_path_length']} gates"))
        lines.append(left(f"Max frequency:    {timing['max_frequency_ghz']} GHz"))
        lines.append(spacer)

        # Arrival times
        lines.append(left("OUTPUT ARRIVAL TIMES"))
        lines.append(left("-" * (width - 6)))
        for label, arr_time in timing["arrival_times"].items():
            lines.append(left(f"  {label:<18} {arr_time:>8.2f} ns"))
        lines.append(spacer)

        # Recent simulation results
        if simulation_results:
            lines.append(left("RECENT SIMULATION RESULTS"))
            lines.append(left("-" * (width - 6)))
            display_results = simulation_results[-10:]
            lines.append(left(f"  {'N':>4}  {'Binary':>9}  {'Label':<10} {'Events':>6} {'Settle':>8}"))
            lines.append(left(f"  {'---':>4}  {'---------':>9}  {'-----':<10} {'------':>6} {'------':>8}"))
            for r in display_results:
                settle = r.get("steady_state_ns", 0.0)
                events = r.get("events_processed", r.get("gate_evaluations", 0))
                lines.append(left(
                    f"  {r['number']:>4}  {r['binary']:>9}  "
                    f"{r['label']:<10} {events:>6} {settle:>7.1f}ns"
                ))
            lines.append(spacer)

        lines.append(border)
        return "\n".join(lines)


# ============================================================
# Circuit Middleware
# ============================================================


class CircuitMiddleware(IMiddleware):
    """Middleware that performs gate-level divisibility verification.

    For each number passing through the pipeline, this middleware
    constructs or reuses a FizzBuzzClassifier circuit and runs
    an event-driven simulation to compute the FizzBuzz classification
    at the gate level. The result is stored in the processing context
    metadata for comparison with the standard evaluation.

    Priority: -6 (runs early in the pipeline to establish ground truth
    before higher-level evaluation strategies modify the result).
    """

    def __init__(
        self,
        event_bus: Optional[IEventBus] = None,
        enable_waveform: bool = False,
        enable_dashboard: bool = False,
        max_events: int = 10000,
        timing_budget_ns: float = 500.0,
        glitch_threshold_ns: float = 5.0,
    ) -> None:
        self._event_bus = event_bus
        self._enable_waveform = enable_waveform
        self._enable_dashboard = enable_dashboard
        self._max_events = max_events
        self._timing_budget_ns = timing_budget_ns
        self._glitch_threshold_ns = glitch_threshold_ns
        self._classifier = FizzBuzzClassifier()
        self._simulator = EventDrivenSimulator(
            self._classifier,
            max_events=self._max_events,
            glitch_threshold_ns=self._glitch_threshold_ns,
        )
        self._results: list[dict[str, Any]] = []
        self._priority = -6

    @property
    def classifier(self) -> FizzBuzzClassifier:
        return self._classifier

    @property
    def results(self) -> list[dict[str, Any]]:
        return list(self._results)

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Run gate-level simulation and attach results to context metadata."""
        number = context.number

        # Range check: 7-bit circuit supports 0-127
        if number < 0 or number >= (1 << FizzBuzzClassifier.BIT_WIDTH):
            logger.warning(
                "FizzGate: number %d outside 7-bit range, skipping circuit simulation",
                number,
            )
            return next_handler(context)

        start_time = time.monotonic_ns()

        try:
            # Reset circuit state for clean simulation
            self._classifier.reset()

            # Run event-driven simulation
            result = self._simulator.simulate(
                number,
                capture_waveform=self._enable_waveform,
            )

            elapsed_ns = time.monotonic_ns() - start_time
            result["wall_time_ns"] = elapsed_ns

            # Check timing budget
            if result.get("steady_state_ns", 0.0) > self._timing_budget_ns:
                logger.warning(
                    "FizzGate: circuit settle time %.1f ns exceeds budget %.1f ns for input %d",
                    result["steady_state_ns"],
                    self._timing_budget_ns,
                    number,
                )

            self._results.append(result)

            # Attach to context metadata
            context.metadata["fizzgate"] = {
                "label": result["label"],
                "div_by_3": result["div_by_3"],
                "div_by_5": result["div_by_5"],
                "div_by_15": result["div_by_15"],
                "events_processed": result["events_processed"],
                "steady_state_ns": result["steady_state_ns"],
                "glitch_count": result["glitch_count"],
            }

            # Publish event if event bus available
            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.NUMBER_PROCESSED,
                    payload={
                        "subsystem": "fizzgate",
                        "number": number,
                        "label": result["label"],
                        "events_processed": result["events_processed"],
                    },
                    source="FizzGateCircuitSimulator",
                ))

        except (CircuitSimulationError, CircuitSteadyStateError) as exc:
            logger.error("FizzGate simulation failed for %d: %s", number, exc)
            context.metadata["fizzgate"] = {"error": str(exc)}

        return next_handler(context)

    def get_name(self) -> str:
        """Return the middleware's identifier."""
        return "FizzGateCircuitSimulator"

    def get_priority(self) -> int:
        """Return the middleware's priority."""
        return self._priority
