"""
Enterprise FizzBuzz Platform - Quantum Computing Simulator Module

Implements a full state-vector quantum computer simulation with a
simplified Shor's algorithm for FizzBuzz divisibility checking. Because
the modulo operator was insufficiently dramatic, and every enterprise
platform deserves to simulate quantum mechanics using O(2^n) memory
to check if a number is divisible by 3.

The Quantum Advantage Ratio is always negative. This is by design.
The simulator faithfully reproduces the key property of quantum
computing: it is slower than classical for trivial problems, but
with much more impressive ASCII diagrams.

Components:
    QuantumRegister     - State vector of 2^n complex amplitudes
    QuantumGate         - Unitary gate operations (H, X, CNOT, QFT)
    QuantumCircuit      - Ordered sequence of gate applications
    QuantumSimulator    - State vector simulation engine
    ShorDivisibilityChecker - Simplified Shor's period-finding
    QuantumFizzBuzzEngine   - FizzBuzz evaluation via quantum simulation
    CircuitVisualizer   - ASCII circuit diagram renderer
    QuantumDashboard    - Performance statistics with negative speedup
    QuantumMiddleware    - IMiddleware implementation (priority -7)
"""

from __future__ import annotations

import cmath
import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    QuantumCircuitError,
    QuantumDecoherenceError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
#  Quantum Register: The State Vector
# ============================================================

class QuantumRegister:
    """A quantum register of n qubits represented as a state vector.

    The state of n qubits is a complex vector in a 2^n dimensional
    Hilbert space. We store this as a list of complex numbers, initialized
    to |0...0> (all probability amplitude on the first basis state).

    For 4 qubits, that's 16 complex numbers. For 20 qubits, it would be
    1,048,576 complex numbers. For 50 qubits, it would exceed the memory
    of every computer on Earth combined. We use 4.
    """

    def __init__(self, num_qubits: int) -> None:
        if num_qubits < 1:
            raise ValueError(
                f"A quantum register requires at least 1 qubit. "
                f"Got {num_qubits}. Even Schroedinger had a cat."
            )
        if num_qubits > 16:
            raise ValueError(
                f"Refusing to allocate {2**num_qubits} complex amplitudes. "
                f"Max 16 qubits (65536 amplitudes). This is a FizzBuzz "
                f"platform, not a national laboratory."
            )
        self.num_qubits = num_qubits
        self.num_states = 2 ** num_qubits
        # Initialize to |0...0>
        self.amplitudes: list[complex] = [complex(0)] * self.num_states
        self.amplitudes[0] = complex(1)

    def reset(self) -> None:
        """Reset the register to |0...0>."""
        self.amplitudes = [complex(0)] * self.num_states
        self.amplitudes[0] = complex(1)

    def get_probabilities(self) -> list[float]:
        """Return the measurement probability for each basis state."""
        return [abs(a) ** 2 for a in self.amplitudes]

    def get_norm(self) -> float:
        """Return the L2 norm of the state vector (should be 1.0)."""
        return math.sqrt(sum(abs(a) ** 2 for a in self.amplitudes))

    def normalize(self) -> None:
        """Renormalize the state vector to unit length."""
        norm = self.get_norm()
        if norm > 0:
            self.amplitudes = [a / norm for a in self.amplitudes]

    def measure(self) -> int:
        """Perform a projective measurement in the computational basis.

        Collapses the state vector according to the Born rule:
        the probability of observing state |k> is |amplitude_k|^2.

        Returns the index of the measured basis state.
        """
        probs = self.get_probabilities()
        r = random.random()
        cumulative = 0.0
        for i, p in enumerate(probs):
            cumulative += p
            if r <= cumulative:
                # Collapse: set measured state to |1>, all others to |0>
                self.amplitudes = [complex(0)] * self.num_states
                self.amplitudes[i] = complex(1)
                return i
        # Fallback (floating point rounding)
        return self.num_states - 1

    def measure_subset(self, qubit_indices: list[int]) -> int:
        """Measure only specific qubits, returning their combined value.

        Partial measurement collapses only the specified qubits while
        leaving the rest in a (potentially entangled) superposition.
        For simplicity, we measure the full state and extract the
        relevant bits — which is physically equivalent but computationally
        less interesting.
        """
        full_measurement = self.measure()
        result = 0
        for bit_pos, qubit_idx in enumerate(reversed(qubit_indices)):
            bit_value = (full_measurement >> (self.num_qubits - 1 - qubit_idx)) & 1
            result |= bit_value << bit_pos
        return result

    def __repr__(self) -> str:
        nonzero = [
            (i, a) for i, a in enumerate(self.amplitudes) if abs(a) > 1e-10
        ]
        terms = []
        for i, a in nonzero[:8]:
            basis = format(i, f"0{self.num_qubits}b")
            terms.append(f"({a.real:+.3f}{a.imag:+.3f}j)|{basis}>")
        suffix = f" ... +{len(nonzero) - 8} more" if len(nonzero) > 8 else ""
        return " + ".join(terms) + suffix


# ============================================================
#  Quantum Gates: Unitary Transformations
# ============================================================

# Gate matrices as 2D lists of complex numbers.
# Each gate is a unitary matrix that preserves the norm of the state vector.

# Hadamard gate: creates superposition from |0> -> (|0> + |1>) / sqrt(2)
_SQRT2_INV = 1.0 / math.sqrt(2)
HADAMARD_MATRIX: list[list[complex]] = [
    [complex(_SQRT2_INV), complex(_SQRT2_INV)],
    [complex(_SQRT2_INV), complex(-_SQRT2_INV)],
]

# Pauli-X gate (NOT gate): |0> -> |1>, |1> -> |0>
PAULI_X_MATRIX: list[list[complex]] = [
    [complex(0), complex(1)],
    [complex(1), complex(0)],
]

# Pauli-Z gate: |0> -> |0>, |1> -> -|1> (phase flip)
PAULI_Z_MATRIX: list[list[complex]] = [
    [complex(1), complex(0)],
    [complex(0), complex(-1)],
]

# Phase gate (S gate): |0> -> |0>, |1> -> i|1>
PHASE_S_MATRIX: list[list[complex]] = [
    [complex(1), complex(0)],
    [complex(0), complex(0, 1)],
]

# T gate (pi/8 gate): |0> -> |0>, |1> -> e^(i*pi/4)|1>
_T_PHASE = cmath.exp(complex(0, math.pi / 4))
T_GATE_MATRIX: list[list[complex]] = [
    [complex(1), complex(0)],
    [complex(0), _T_PHASE],
]

# CNOT gate (4x4): controlled-NOT, flips target if control is |1>
CNOT_MATRIX: list[list[complex]] = [
    [complex(1), complex(0), complex(0), complex(0)],
    [complex(0), complex(1), complex(0), complex(0)],
    [complex(0), complex(0), complex(0), complex(1)],
    [complex(0), complex(0), complex(1), complex(0)],
]


def make_controlled_phase(angle: float) -> list[list[complex]]:
    """Create a 4x4 controlled-phase gate matrix for the given angle.

    The controlled-phase gate applies a phase e^(i*angle) to the |11> state
    and leaves all other basis states unchanged. This is essential for the
    Quantum Fourier Transform, where controlled rotations create the
    phase relationships needed for period-finding.
    """
    phase = cmath.exp(complex(0, angle))
    return [
        [complex(1), complex(0), complex(0), complex(0)],
        [complex(0), complex(1), complex(0), complex(0)],
        [complex(0), complex(0), complex(1), complex(0)],
        [complex(0), complex(0), complex(0), phase],
    ]


@dataclass
class GateApplication:
    """A single gate application in a quantum circuit.

    Records which gate to apply to which qubit(s), forming the
    building blocks of a quantum circuit. Each gate application
    is a unitary transformation on the full state vector.
    """

    name: str
    matrix: list[list[complex]]
    target_qubits: list[int]
    is_measurement: bool = False

    @property
    def num_target_qubits(self) -> int:
        return len(self.target_qubits)


# ============================================================
#  Quantum Circuit: Ordered Gate Sequence
# ============================================================

class QuantumCircuit:
    """An ordered sequence of quantum gate operations.

    A quantum circuit defines the algorithm to be executed on the
    quantum register. Gates are applied in order, transforming the
    state vector through a series of unitary operations.

    The circuit also records measurement operations, which collapse
    the quantum state according to the Born rule.
    """

    def __init__(self, num_qubits: int) -> None:
        self.num_qubits = num_qubits
        self.gates: list[GateApplication] = []
        self._measurement_qubits: list[int] = []

    def h(self, qubit: int) -> QuantumCircuit:
        """Apply Hadamard gate to the specified qubit."""
        self._validate_qubit(qubit)
        self.gates.append(GateApplication(
            name="H", matrix=HADAMARD_MATRIX, target_qubits=[qubit],
        ))
        return self

    def x(self, qubit: int) -> QuantumCircuit:
        """Apply Pauli-X (NOT) gate to the specified qubit."""
        self._validate_qubit(qubit)
        self.gates.append(GateApplication(
            name="X", matrix=PAULI_X_MATRIX, target_qubits=[qubit],
        ))
        return self

    def z(self, qubit: int) -> QuantumCircuit:
        """Apply Pauli-Z (phase flip) gate to the specified qubit."""
        self._validate_qubit(qubit)
        self.gates.append(GateApplication(
            name="Z", matrix=PAULI_Z_MATRIX, target_qubits=[qubit],
        ))
        return self

    def s(self, qubit: int) -> QuantumCircuit:
        """Apply S (Phase) gate to the specified qubit."""
        self._validate_qubit(qubit)
        self.gates.append(GateApplication(
            name="S", matrix=PHASE_S_MATRIX, target_qubits=[qubit],
        ))
        return self

    def t(self, qubit: int) -> QuantumCircuit:
        """Apply T (pi/8) gate to the specified qubit."""
        self._validate_qubit(qubit)
        self.gates.append(GateApplication(
            name="T", matrix=T_GATE_MATRIX, target_qubits=[qubit],
        ))
        return self

    def cx(self, control: int, target: int) -> QuantumCircuit:
        """Apply CNOT gate with specified control and target qubits."""
        self._validate_qubit(control)
        self._validate_qubit(target)
        if control == target:
            raise QuantumCircuitError("CNOT", [control, target], self.num_qubits)
        self.gates.append(GateApplication(
            name="CX", matrix=CNOT_MATRIX, target_qubits=[control, target],
        ))
        return self

    def cp(self, control: int, target: int, angle: float) -> QuantumCircuit:
        """Apply controlled-phase gate with specified angle."""
        self._validate_qubit(control)
        self._validate_qubit(target)
        if control == target:
            raise QuantumCircuitError("CP", [control, target], self.num_qubits)
        matrix = make_controlled_phase(angle)
        self.gates.append(GateApplication(
            name=f"CP({angle:.3f})",
            matrix=matrix,
            target_qubits=[control, target],
        ))
        return self

    def measure(self, qubit: int) -> QuantumCircuit:
        """Add a measurement operation for the specified qubit."""
        self._validate_qubit(qubit)
        self._measurement_qubits.append(qubit)
        self.gates.append(GateApplication(
            name="M", matrix=[], target_qubits=[qubit], is_measurement=True,
        ))
        return self

    def measure_all(self) -> QuantumCircuit:
        """Add measurement operations for all qubits."""
        for q in range(self.num_qubits):
            self.measure(q)
        return self

    def _validate_qubit(self, qubit: int) -> None:
        """Validate that a qubit index is within range."""
        if not (0 <= qubit < self.num_qubits):
            raise QuantumCircuitError(
                "qubit_validation", [qubit], self.num_qubits
            )

    @property
    def depth(self) -> int:
        """Return the number of gate layers (excluding measurements)."""
        return sum(1 for g in self.gates if not g.is_measurement)

    @property
    def gate_count(self) -> int:
        """Return the total number of gates (excluding measurements)."""
        return sum(1 for g in self.gates if not g.is_measurement)

    def __repr__(self) -> str:
        return (
            f"QuantumCircuit(qubits={self.num_qubits}, "
            f"gates={self.gate_count}, depth={self.depth})"
        )


# ============================================================
#  Quantum Simulator: State Vector Engine
# ============================================================

class QuantumSimulator:
    """State vector quantum computer simulator.

    Applies gate operations to a quantum register by computing the
    tensor (Kronecker) product of gate matrices with identity matrices
    to form the full 2^n x 2^n transformation matrix, then multiplying
    it with the state vector.

    This is O(4^n) per gate application, which is why real quantum
    simulation is hard, and why our 4-qubit simulator is the perfect
    amount of overkill for checking n % 3 == 0.
    """

    def __init__(
        self,
        decoherence_threshold: float = 0.001,
    ) -> None:
        self.decoherence_threshold = decoherence_threshold
        self.gates_applied = 0
        self.measurements_performed = 0
        self._execution_log: list[dict[str, Any]] = []

    def execute(
        self, circuit: QuantumCircuit, register: QuantumRegister
    ) -> int:
        """Execute a quantum circuit on the given register.

        Applies each gate in sequence, checking for decoherence after
        each operation. Returns the final measurement result.

        Raises QuantumDecoherenceError if the state vector norm drifts
        beyond the decoherence threshold.
        """
        measurement_result = 0

        for gate in circuit.gates:
            if gate.is_measurement:
                measurement_result = register.measure()
                self.measurements_performed += 1
                self._execution_log.append({
                    "type": "measurement",
                    "result": measurement_result,
                    "qubits": gate.target_qubits,
                })
                continue

            # Apply the gate to the state vector
            if gate.num_target_qubits == 1:
                self._apply_single_qubit_gate(
                    register, gate.matrix, gate.target_qubits[0]
                )
            elif gate.num_target_qubits == 2:
                self._apply_two_qubit_gate(
                    register, gate.matrix,
                    gate.target_qubits[0], gate.target_qubits[1]
                )
            else:
                raise QuantumCircuitError(
                    gate.name, gate.target_qubits, register.num_qubits
                )

            self.gates_applied += 1
            self._execution_log.append({
                "type": "gate",
                "name": gate.name,
                "qubits": gate.target_qubits,
            })

            # Check for decoherence
            norm = register.get_norm()
            if abs(norm - 1.0) > self.decoherence_threshold:
                logger.warning(
                    "Decoherence detected: norm=%.6f (threshold=%.6f). "
                    "Renormalizing state vector.",
                    norm, self.decoherence_threshold,
                )
                register.normalize()

        return measurement_result

    def _apply_single_qubit_gate(
        self,
        register: QuantumRegister,
        gate_matrix: list[list[complex]],
        target: int,
    ) -> None:
        """Apply a 2x2 gate matrix to a single qubit via Kronecker product.

        For an n-qubit system, we compute the full 2^n x 2^n matrix by
        taking the tensor product: I_before (x) Gate (x) I_after,
        then multiply with the state vector.

        For efficiency with small qubit counts, we directly compute the
        matrix-vector product using the structure of the Kronecker product.
        """
        n = register.num_qubits
        num_states = register.num_states
        new_amplitudes = [complex(0)] * num_states

        # Target qubit position from MSB (qubit 0 is most significant)
        target_bit = n - 1 - target

        for state_idx in range(num_states):
            bit_val = (state_idx >> target_bit) & 1

            # Compute the paired state (with target bit flipped)
            paired_idx = state_idx ^ (1 << target_bit)

            if bit_val == 0:
                # |0> component: gate[0][0] * |0> + gate[0][1] * |1>
                new_amplitudes[state_idx] += (
                    gate_matrix[0][0] * register.amplitudes[state_idx]
                    + gate_matrix[0][1] * register.amplitudes[paired_idx]
                )
            else:
                # |1> component: gate[1][0] * |0> + gate[1][1] * |1>
                new_amplitudes[state_idx] += (
                    gate_matrix[1][0] * register.amplitudes[paired_idx]
                    + gate_matrix[1][1] * register.amplitudes[state_idx]
                )

        register.amplitudes = new_amplitudes

    def _apply_two_qubit_gate(
        self,
        register: QuantumRegister,
        gate_matrix: list[list[complex]],
        control: int,
        target: int,
    ) -> None:
        """Apply a 4x4 gate matrix to two qubits.

        The gate matrix acts on the two-qubit subspace indexed by the
        control and target qubits. We iterate over all basis states and
        compute the transformation based on the control-target bit values.
        """
        n = register.num_qubits
        num_states = register.num_states
        new_amplitudes = list(register.amplitudes)

        control_bit = n - 1 - control
        target_bit = n - 1 - target

        # Process states in groups of 4 (based on control-target bit pairs)
        visited = set()

        for state_idx in range(num_states):
            # Extract control and target bit values
            c_val = (state_idx >> control_bit) & 1
            t_val = (state_idx >> target_bit) & 1

            # Find the base state (control=0, target=0)
            base = state_idx
            base &= ~(1 << control_bit)
            base &= ~(1 << target_bit)

            if base in visited:
                continue
            visited.add(base)

            # Four states in this group
            s00 = base
            s01 = base | (1 << target_bit)
            s10 = base | (1 << control_bit)
            s11 = base | (1 << control_bit) | (1 << target_bit)

            a00 = register.amplitudes[s00]
            a01 = register.amplitudes[s01]
            a10 = register.amplitudes[s10]
            a11 = register.amplitudes[s11]

            old = [a00, a01, a10, a11]

            for row in range(4):
                result = complex(0)
                for col in range(4):
                    result += gate_matrix[row][col] * old[col]
                idx = [s00, s01, s10, s11][row]
                new_amplitudes[idx] = result

        register.amplitudes = new_amplitudes

    @property
    def execution_log(self) -> list[dict[str, Any]]:
        """Return the execution log of gate applications and measurements."""
        return list(self._execution_log)

    def reset_stats(self) -> None:
        """Reset execution statistics."""
        self.gates_applied = 0
        self.measurements_performed = 0
        self._execution_log = []


# ============================================================
#  Quantum Fourier Transform (QFT)
# ============================================================

def build_qft_circuit(num_qubits: int, target_qubits: Optional[list[int]] = None) -> QuantumCircuit:
    """Build a Quantum Fourier Transform circuit.

    The QFT maps computational basis states to frequency-domain states,
    enabling period-finding. It is the quantum analogue of the discrete
    Fourier transform, and the key ingredient in Shor's algorithm.

    For n qubits, QFT applies:
    1. Hadamard gate to qubit k
    2. Controlled-R_m gates from qubit k to qubits k+1, k+2, ...
    3. Repeat for all qubits
    4. SWAP qubits to reverse output order

    The resulting circuit has O(n^2) gates, which is exponentially
    faster than the classical FFT for the same-sized input.
    Unfortunately, the input must first be prepared in a quantum
    state, which is the hard part.
    """
    qubits = target_qubits or list(range(num_qubits))
    n = len(qubits)
    circuit = QuantumCircuit(num_qubits)

    for i in range(n):
        # Hadamard on qubit i
        circuit.h(qubits[i])

        # Controlled phase rotations
        for j in range(i + 1, n):
            angle = math.pi / (2 ** (j - i))
            circuit.cp(qubits[j], qubits[i], angle)

    # Swap qubits to reverse order (bit reversal)
    for i in range(n // 2):
        j = n - 1 - i
        # SWAP via 3 CNOTs
        circuit.cx(qubits[i], qubits[j])
        circuit.cx(qubits[j], qubits[i])
        circuit.cx(qubits[i], qubits[j])

    return circuit


def build_inverse_qft_circuit(
    num_qubits: int, target_qubits: Optional[list[int]] = None
) -> QuantumCircuit:
    """Build the inverse Quantum Fourier Transform circuit.

    The inverse QFT is the adjoint (conjugate transpose) of the QFT.
    It maps frequency-domain states back to computational basis states,
    allowing us to read out the period found by the quantum phase
    estimation subroutine.
    """
    qubits = target_qubits or list(range(num_qubits))
    n = len(qubits)
    circuit = QuantumCircuit(num_qubits)

    # Swap qubits to reverse order first
    for i in range(n // 2):
        j = n - 1 - i
        circuit.cx(qubits[i], qubits[j])
        circuit.cx(qubits[j], qubits[i])
        circuit.cx(qubits[i], qubits[j])

    # Apply gates in reverse order with negated phases
    for i in range(n - 1, -1, -1):
        for j in range(n - 1, i, -1):
            angle = -math.pi / (2 ** (j - i))
            circuit.cp(qubits[j], qubits[i], angle)
        circuit.h(qubits[i])

    return circuit


# ============================================================
#  Shor's Divisibility Checker (Simplified)
# ============================================================

@dataclass
class ShorResult:
    """Result of a Shor's algorithm divisibility check.

    Contains the quantum measurement outcome, the found period,
    and whether divisibility was confirmed. Also tracks whether
    a classical fallback was needed, because it almost always is.
    """

    number: int
    divisor: int
    is_divisible: bool
    period_found: Optional[int] = None
    measurement_outcome: Optional[int] = None
    attempts: int = 0
    used_classical_fallback: bool = False
    quantum_time_ns: float = 0.0
    classical_time_ns: float = 0.0

    @property
    def quantum_advantage_ratio(self) -> float:
        """The quantum advantage ratio. Always negative."""
        if self.classical_time_ns > 0:
            return -(self.quantum_time_ns / max(self.classical_time_ns, 1))
        return -float("inf")


class ShorDivisibilityChecker:
    """Simplified Shor's algorithm for divisibility checking.

    Shor's algorithm finds the period of f(x) = a^x mod N, which can
    be used to factor N and determine divisibility. Our simplification:

    1. Prepare a superposition of computational basis states via QFT
    2. Encode the modular arithmetic structure in the phase
    3. Apply inverse QFT to read out the period
    4. Check if the period divides evenly (indicating divisibility)

    For small divisors (3, 5), the period of a^x mod d is small,
    so even our tiny 4-qubit register can sometimes find it.
    When it can't (which is often), we fall back to classical modulo,
    because enterprise reliability trumps quantum supremacy.
    """

    def __init__(
        self,
        num_qubits: int = 4,
        max_attempts: int = 10,
        decoherence_threshold: float = 0.001,
        max_period_attempts: int = 5,
        fallback_to_classical: bool = True,
    ) -> None:
        self.num_qubits = num_qubits
        self.max_attempts = max_attempts
        self.decoherence_threshold = decoherence_threshold
        self.max_period_attempts = max_period_attempts
        self.fallback_to_classical = fallback_to_classical
        self.simulator = QuantumSimulator(
            decoherence_threshold=decoherence_threshold,
        )
        self.total_checks = 0
        self.classical_fallbacks = 0
        self.quantum_successes = 0
        self._results_log: list[ShorResult] = []

    def check_divisibility(self, number: int, divisor: int) -> ShorResult:
        """Check if number is divisible by divisor using quantum period-finding.

        The algorithm:
        1. Choose a random base 'a' coprime to divisor
        2. Build a quantum circuit that finds the period of a^x mod divisor
        3. Measure the quantum register
        4. Use the measurement to determine the period
        5. Check if the period indicates divisibility

        If the quantum approach fails after max_attempts, fall back to
        classical modulo. This happens more often than we'd like to admit.
        """
        self.total_checks += 1
        quantum_start = time.perf_counter_ns()
        result = ShorResult(number=number, divisor=divisor, is_divisible=False)

        # Handle trivial cases classically (even quantum supremacists
        # concede that checking n == 0 doesn't need a quantum computer)
        if number == 0:
            result.is_divisible = True
            result.used_classical_fallback = True
            result.quantum_time_ns = float(time.perf_counter_ns() - quantum_start)
            self.classical_fallbacks += 1
            self._results_log.append(result)
            return result

        if divisor <= 1:
            result.is_divisible = True
            result.used_classical_fallback = True
            result.quantum_time_ns = float(time.perf_counter_ns() - quantum_start)
            self.classical_fallbacks += 1
            self._results_log.append(result)
            return result

        # Try quantum period-finding
        for attempt in range(self.max_attempts):
            result.attempts = attempt + 1

            # Choose a base coprime to divisor
            a = self._choose_base(divisor)

            # Compute the actual period classically (to construct the oracle)
            period = self._classical_period(a, divisor)

            if period is not None and period > 0:
                # Build and run quantum period-finding circuit
                measurement = self._run_period_finding_circuit(
                    a, divisor, period
                )
                result.measurement_outcome = measurement

                # Extract period from measurement
                found_period = self._extract_period(measurement, divisor)
                if found_period is not None and found_period > 0:
                    result.period_found = found_period

                    # Check divisibility using the period
                    # If number mod divisor == 0, the period of a^x mod divisor
                    # should divide evenly into the register size
                    is_div = (number % divisor == 0)
                    result.is_divisible = is_div
                    result.quantum_time_ns = float(
                        time.perf_counter_ns() - quantum_start
                    )
                    self.quantum_successes += 1
                    self._results_log.append(result)

                    # Measure classical time for comparison
                    classical_start = time.perf_counter_ns()
                    _ = number % divisor
                    result.classical_time_ns = float(
                        time.perf_counter_ns() - classical_start
                    )

                    return result

        # Quantum approach failed — fall back to classical
        if self.fallback_to_classical:
            classical_start = time.perf_counter_ns()
            result.is_divisible = (number % divisor == 0)
            result.classical_time_ns = float(
                time.perf_counter_ns() - classical_start
            )
            result.used_classical_fallback = True
            result.quantum_time_ns = float(
                time.perf_counter_ns() - quantum_start
            )
            self.classical_fallbacks += 1
            self._results_log.append(result)
            return result

        # No fallback — return uncertain result
        result.quantum_time_ns = float(time.perf_counter_ns() - quantum_start)
        self._results_log.append(result)
        return result

    def _choose_base(self, divisor: int) -> int:
        """Choose a random base coprime to the divisor."""
        for _ in range(100):
            a = random.randint(2, max(divisor - 1, 2))
            if math.gcd(a, divisor) == 1:
                return a
        return 2

    def _classical_period(self, a: int, n: int) -> Optional[int]:
        """Find the period of a^x mod n classically.

        The period r is the smallest positive integer such that
        a^r mod n == 1. We compute this iteratively because our
        quantum simulator needs to know the answer before it can
        pretend to find it. This is not cheating — it's "oracle
        construction."
        """
        if n <= 1:
            return 1
        x = a % n
        for r in range(1, n + 1):
            if x == 1:
                return r
            x = (x * a) % n
        return None

    def _run_period_finding_circuit(
        self, a: int, divisor: int, period: int
    ) -> int:
        """Build and execute the quantum period-finding circuit.

        This constructs a simplified version of the quantum phase
        estimation circuit used in Shor's algorithm:
        1. Initialize qubits in superposition (Hadamard layer)
        2. Apply modular exponentiation oracle (encoded in phases)
        3. Apply inverse QFT to extract the period
        4. Measure the register
        """
        register = QuantumRegister(self.num_qubits)
        circuit = QuantumCircuit(self.num_qubits)

        # Step 1: Create uniform superposition
        for q in range(self.num_qubits):
            circuit.h(q)

        # Step 2: Apply phase encoding based on the period
        # For each basis state |x>, apply phase e^(2*pi*i*x/period)
        # This encodes the period information in the quantum state
        num_states = 2 ** self.num_qubits
        for q in range(self.num_qubits):
            # Apply Z rotations to encode the period
            angle = 2.0 * math.pi * (2 ** q) / max(period, 1)
            # Approximate the phase gate using available gates
            if abs(angle) > 0.01:
                # Use a phase gate: Rz(angle) = [[1, 0], [0, e^(i*angle)]]
                rz_matrix: list[list[complex]] = [
                    [complex(1), complex(0)],
                    [complex(0), cmath.exp(complex(0, angle))],
                ]
                circuit.gates.append(GateApplication(
                    name=f"Rz({angle:.3f})",
                    matrix=rz_matrix,
                    target_qubits=[q],
                ))

        # Step 3: Apply inverse QFT
        inv_qft = build_inverse_qft_circuit(self.num_qubits)
        circuit.gates.extend(inv_qft.gates)

        # Step 4: Measure all qubits
        circuit.measure_all()

        # Execute the circuit
        measurement = self.simulator.execute(circuit, register)
        return measurement

    def _extract_period(self, measurement: int, divisor: int) -> Optional[int]:
        """Extract the period from a quantum measurement result.

        The measurement result should be close to k * (2^n / period)
        for some integer k. We use continued fraction expansion to
        find the best rational approximation and extract the period.

        In practice, with 4 qubits and a divisor of 3, the period is
        often found on the first try. With divisor 5, it might take
        a few attempts. With divisor 97, well, that's why we have
        classical fallback.
        """
        if measurement == 0:
            return None

        n_states = 2 ** self.num_qubits
        # The measurement should be approximately k * n_states / period
        # Use continued fractions to find the period
        fraction = measurement / n_states

        # Continued fraction expansion
        period = self._continued_fraction_period(fraction, divisor)
        return period

    def _continued_fraction_period(
        self, fraction: float, max_period: int
    ) -> Optional[int]:
        """Extract period using continued fraction expansion.

        This is the classical post-processing step of Shor's algorithm.
        Given a fraction close to k/r (where r is the period), we use
        the continued fraction algorithm to find the best rational
        approximation with denominator <= max_period.
        """
        if fraction < 1e-10:
            return None

        # Simple continued fraction convergents
        h_prev, h_curr = 0, 1
        k_prev, k_curr = 1, 0
        x = fraction

        for _ in range(20):
            a = int(x)
            h_prev, h_curr = h_curr, a * h_curr + h_prev
            k_prev, k_curr = k_curr, a * k_curr + k_prev

            if k_curr > 0 and k_curr <= max_period:
                # Check if this denominator is a valid period
                if k_curr > 0:
                    return k_curr

            remainder = x - a
            if abs(remainder) < 1e-10:
                break
            x = 1.0 / remainder

        return None

    @property
    def success_rate(self) -> float:
        """Return the quantum success rate (usually embarrassingly low)."""
        if self.total_checks == 0:
            return 0.0
        return self.quantum_successes / self.total_checks

    @property
    def results_log(self) -> list[ShorResult]:
        """Return the full results log."""
        return list(self._results_log)

    def reset_stats(self) -> None:
        """Reset all statistics."""
        self.total_checks = 0
        self.classical_fallbacks = 0
        self.quantum_successes = 0
        self._results_log = []
        self.simulator.reset_stats()


# ============================================================
#  Quantum FizzBuzz Engine
# ============================================================

@dataclass
class QuantumEvaluationResult:
    """Result of a quantum FizzBuzz evaluation for a single number."""

    number: int
    output: str
    matched_rules: list[str]
    shor_results: list[ShorResult]
    total_quantum_time_ns: float = 0.0
    total_classical_time_ns: float = 0.0
    all_classical_fallback: bool = False

    @property
    def quantum_advantage_ratio(self) -> float:
        """Overall quantum advantage ratio. Always negative."""
        if self.total_classical_time_ns > 0:
            return -(self.total_quantum_time_ns /
                     max(self.total_classical_time_ns, 1))
        return -float("inf")


class QuantumFizzBuzzEngine:
    """FizzBuzz evaluation engine powered by quantum divisibility checking.

    Wraps the ShorDivisibilityChecker to evaluate each FizzBuzz rule
    using quantum period-finding instead of classical modulo. The results
    are identical to the standard rule engine (assuming the quantum
    simulator doesn't fail, which it sometimes does, which is why we
    have classical fallback).

    This engine exists to prove that any computation, no matter how
    trivial, can be made more complex by invoking quantum mechanics.
    """

    def __init__(
        self,
        rules: list[dict[str, Any]],
        num_qubits: int = 4,
        max_attempts: int = 10,
        decoherence_threshold: float = 0.001,
        max_period_attempts: int = 5,
        fallback_to_classical: bool = True,
    ) -> None:
        self.rules = sorted(rules, key=lambda r: r.get("priority", 0))
        self.checker = ShorDivisibilityChecker(
            num_qubits=num_qubits,
            max_attempts=max_attempts,
            decoherence_threshold=decoherence_threshold,
            max_period_attempts=max_period_attempts,
            fallback_to_classical=fallback_to_classical,
        )
        self._evaluation_log: list[QuantumEvaluationResult] = []

    def evaluate(self, number: int) -> QuantumEvaluationResult:
        """Evaluate a number using quantum divisibility checking.

        For each rule, use Shor's algorithm to determine if the number
        is divisible by the rule's divisor. Concatenate matched labels
        to produce the FizzBuzz output.
        """
        matched_rules: list[str] = []
        shor_results: list[ShorResult] = []
        total_q_time = 0.0
        total_c_time = 0.0

        for rule in self.rules:
            divisor = rule["divisor"]
            label = rule["label"]

            result = self.checker.check_divisibility(number, divisor)
            shor_results.append(result)
            total_q_time += result.quantum_time_ns
            total_c_time += result.classical_time_ns

            if result.is_divisible:
                matched_rules.append(label)

        output = "".join(matched_rules) if matched_rules else str(number)

        eval_result = QuantumEvaluationResult(
            number=number,
            output=output,
            matched_rules=matched_rules,
            shor_results=shor_results,
            total_quantum_time_ns=total_q_time,
            total_classical_time_ns=total_c_time,
            all_classical_fallback=all(r.used_classical_fallback for r in shor_results),
        )

        self._evaluation_log.append(eval_result)
        return eval_result

    @property
    def evaluation_log(self) -> list[QuantumEvaluationResult]:
        """Return the full evaluation log."""
        return list(self._evaluation_log)

    @property
    def total_evaluations(self) -> int:
        return len(self._evaluation_log)

    @property
    def average_quantum_advantage(self) -> float:
        """Average quantum advantage ratio across all evaluations."""
        if not self._evaluation_log:
            return 0.0
        ratios = [e.quantum_advantage_ratio for e in self._evaluation_log
                  if not math.isinf(e.quantum_advantage_ratio)]
        return sum(ratios) / len(ratios) if ratios else 0.0

    def reset(self) -> None:
        """Reset the engine and all statistics."""
        self._evaluation_log = []
        self.checker.reset_stats()


# ============================================================
#  Circuit Visualizer: ASCII Art for Quantum Circuits
# ============================================================

class CircuitVisualizer:
    """Renders quantum circuits as ASCII art diagrams.

    Produces diagrams in the standard quantum circuit notation:

        q0: --[H]--[*]--------[M]
        q1: -------[X]--[H]--[M]
        q2: --[H]---------[Z]--[M]

    Because even simulated quantum gates deserve visualization.
    """

    @staticmethod
    def render(circuit: QuantumCircuit, width: int = 60) -> str:
        """Render a quantum circuit as an ASCII diagram."""
        lines: list[list[str]] = [[] for _ in range(circuit.num_qubits)]
        labels = [f"q{i}" for i in range(circuit.num_qubits)]
        max_label = max(len(l) for l in labels)

        for gate in circuit.gates:
            if gate.is_measurement:
                for q in gate.target_qubits:
                    lines[q].append("[M]")
                # Add wire segments to other qubits
                for q in range(circuit.num_qubits):
                    if q not in gate.target_qubits:
                        lines[q].append("---")
            elif gate.num_target_qubits == 1:
                q = gate.target_qubits[0]
                gate_label = gate.name if len(gate.name) <= 3 else gate.name[:2]
                lines[q].append(f"[{gate_label}]")
                for other_q in range(circuit.num_qubits):
                    if other_q != q:
                        pad = len(gate_label) + 2
                        lines[other_q].append("-" * pad)
            elif gate.num_target_qubits == 2:
                ctrl, tgt = gate.target_qubits
                lines[ctrl].append("[*]")
                lines[tgt].append("[X]")
                for other_q in range(circuit.num_qubits):
                    if other_q not in gate.target_qubits:
                        lines[other_q].append("---")

                # Draw vertical connections
                lo = min(ctrl, tgt)
                hi = max(ctrl, tgt)
                for mid in range(lo + 1, hi):
                    if mid != ctrl and mid != tgt:
                        # Replace last segment with vertical connector
                        if lines[mid]:
                            lines[mid][-1] = "-|-"

        # Build output
        output_lines = []
        for q in range(circuit.num_qubits):
            label = labels[q].rjust(max_label)
            wire = "--".join(lines[q]) if lines[q] else "---"
            line = f"  {label}: --{wire}--"
            if len(line) > width:
                line = line[:width - 3] + "..."
            output_lines.append(line)

        return "\n".join(output_lines)


# ============================================================
#  Quantum Dashboard: Statistics & Metrics
# ============================================================

class QuantumDashboard:
    """ASCII dashboard for Quantum Computing Simulator statistics.

    Displays gate counts, measurement statistics, quantum advantage
    ratios (always negative), and ASCII circuit diagrams. The
    "Quantum Advantage" metric is deliberately presented in negative
    scientific notation to emphasize the absurdity.
    """

    @staticmethod
    def render(
        engine: QuantumFizzBuzzEngine,
        circuit: Optional[QuantumCircuit] = None,
        width: int = 60,
        show_circuit: bool = True,
    ) -> str:
        """Render the quantum computing statistics dashboard."""
        border = "+" + "=" * (width - 2) + "+"
        thin = "+" + "-" * (width - 2) + "+"

        lines = [
            border,
            _center("QUANTUM COMPUTING SIMULATOR DASHBOARD", width),
            _center("Shor's Algorithm for Enterprise FizzBuzz", width),
            border,
            "",
            thin,
            _center("QUANTUM STATISTICS", width),
            thin,
        ]

        checker = engine.checker
        sim = checker.simulator

        lines.append(_kv("Total Evaluations", str(engine.total_evaluations), width))
        lines.append(_kv("Divisibility Checks", str(checker.total_checks), width))
        lines.append(_kv("Quantum Successes", str(checker.quantum_successes), width))
        lines.append(_kv("Classical Fallbacks", str(checker.classical_fallbacks), width))
        lines.append(_kv(
            "Quantum Success Rate",
            f"{checker.success_rate * 100:.1f}%",
            width,
        ))
        lines.append(_kv("Gates Applied", str(sim.gates_applied), width))
        lines.append(_kv("Measurements Performed", str(sim.measurements_performed), width))
        lines.append(_kv("Register Size", f"{checker.num_qubits} qubits", width))
        lines.append(_kv(
            "Hilbert Space Dimension",
            str(2 ** checker.num_qubits),
            width,
        ))

        # Quantum Advantage (the punchline)
        lines.append("")
        lines.append(thin)
        lines.append(_center("QUANTUM ADVANTAGE ANALYSIS", width))
        lines.append(thin)

        avg_advantage = engine.average_quantum_advantage
        lines.append(_kv(
            "Avg. Quantum Advantage",
            f"{avg_advantage:.2e}x",
            width,
        ))
        lines.append(_kv(
            "Interpretation",
            "SLOWER (as expected)",
            width,
        ))
        lines.append(_kv(
            "Recommendation",
            "Use classical modulo",
            width,
        ))

        # Compute total times
        total_q = sum(e.total_quantum_time_ns for e in engine.evaluation_log)
        total_c = sum(e.total_classical_time_ns for e in engine.evaluation_log)
        lines.append(_kv(
            "Total Quantum Time",
            f"{total_q / 1_000_000:.2f}ms",
            width,
        ))
        lines.append(_kv(
            "Total Classical Time",
            f"{total_c / 1_000:.2f}us" if total_c < 1_000_000 else f"{total_c / 1_000_000:.4f}ms",
            width,
        ))

        if total_c > 0:
            slowdown = total_q / total_c
            lines.append(_kv(
                "Slowdown Factor",
                f"{slowdown:.0f}x (quantum is slower)",
                width,
            ))

        # Circuit diagram
        if show_circuit and circuit is not None:
            lines.append("")
            lines.append(thin)
            lines.append(_center("SAMPLE CIRCUIT DIAGRAM", width))
            lines.append(thin)
            lines.append(CircuitVisualizer.render(circuit, width=width - 4))

        # Disclaimer
        lines.append("")
        lines.append(thin)
        lines.append(_center("DISCLAIMER", width))
        lines.append(thin)
        lines.append(_center("No actual quantum hardware was harmed", width))
        lines.append(_center("in the simulation of this FizzBuzz evaluation.", width))
        lines.append(_center("All qubits are simulated using Python floats.", width))
        lines.append(_center("The Quantum Advantage is negative. This is fine.", width))
        lines.append(border)

        return "\n".join(lines)


def _center(text: str, width: int) -> str:
    """Center text within border characters."""
    inner = width - 4
    return f"| {text:^{inner}} |"


def _kv(key: str, value: str, width: int) -> str:
    """Format a key-value pair within border characters."""
    inner = width - 4
    key_width = inner // 2
    val_width = inner - key_width - 2
    return f"| {key:<{key_width}}: {value:<{val_width}} |"


# ============================================================
#  Quantum Middleware: Pipeline Integration
# ============================================================

class QuantumMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluation through the quantum simulator.

    When enabled, this middleware intercepts the evaluation pipeline and
    uses the QuantumFizzBuzzEngine to perform divisibility checking via
    Shor's algorithm instead of classical modulo arithmetic.

    Priority -7 ensures this runs very early in the pipeline, before
    most other middleware has a chance to interfere with the quantum
    state. Not that anything in the pipeline can actually affect our
    simulated qubits, but the priority reflects the importance we
    assign to quantum supremacy theatre.
    """

    def __init__(
        self,
        engine: QuantumFizzBuzzEngine,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._engine = engine
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a number through the quantum FizzBuzz engine."""
        # Emit quantum circuit initialization event
        if self._event_bus is not None:
            from enterprise_fizzbuzz.domain.models import Event
            self._event_bus.publish(Event(
                event_type=EventType.QUANTUM_CIRCUIT_INITIALIZED,
                payload={"number": context.number, "qubits": self._engine.checker.num_qubits},
                source="QuantumMiddleware",
            ))

        # Run the quantum evaluation
        qe_result = self._engine.evaluate(context.number)

        # Store quantum metadata in the context
        context.metadata["quantum_output"] = qe_result.output
        context.metadata["quantum_matched_rules"] = qe_result.matched_rules
        context.metadata["quantum_advantage_ratio"] = qe_result.quantum_advantage_ratio
        context.metadata["quantum_classical_fallback"] = qe_result.all_classical_fallback
        context.metadata["quantum_time_ns"] = qe_result.total_quantum_time_ns

        # Emit measurement event
        if self._event_bus is not None:
            from enterprise_fizzbuzz.domain.models import Event
            self._event_bus.publish(Event(
                event_type=EventType.QUANTUM_MEASUREMENT_PERFORMED,
                payload={
                    "number": context.number,
                    "output": qe_result.output,
                    "advantage_ratio": qe_result.quantum_advantage_ratio,
                    "fallback": qe_result.all_classical_fallback,
                },
                source="QuantumMiddleware",
            ))

        # Continue the pipeline (the standard engine will also evaluate,
        # but the quantum result is recorded in metadata for comparison)
        result = next_handler(context)

        return result

    def get_name(self) -> str:
        return "QuantumMiddleware"

    def get_priority(self) -> int:
        return -7

    @property
    def engine(self) -> QuantumFizzBuzzEngine:
        """Return the quantum FizzBuzz engine."""
        return self._engine
