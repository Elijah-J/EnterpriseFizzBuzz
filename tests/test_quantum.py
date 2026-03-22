"""
Enterprise FizzBuzz Platform - Quantum Computing Simulator Tests

Tests for the state-vector quantum simulator, quantum gates,
Shor's divisibility checker, QFT circuits, circuit visualizer,
dashboard renderer, and quantum middleware.

NOTE: All qubit counts are kept LOW (4-6) to avoid exponential
memory blowup. State vector simulation is O(4^n) per gate, so
even 10 qubits would make these tests unacceptably slow for a
FizzBuzz application.
"""

import math
import cmath
import unittest
from unittest.mock import MagicMock, patch

from enterprise_fizzbuzz.infrastructure.quantum import (
    CircuitVisualizer,
    GateApplication,
    HADAMARD_MATRIX,
    PAULI_X_MATRIX,
    PAULI_Z_MATRIX,
    PHASE_S_MATRIX,
    T_GATE_MATRIX,
    CNOT_MATRIX,
    QuantumCircuit,
    QuantumDashboard,
    QuantumFizzBuzzEngine,
    QuantumMiddleware,
    QuantumRegister,
    QuantumSimulator,
    ShorDivisibilityChecker,
    ShorResult,
    build_qft_circuit,
    build_inverse_qft_circuit,
    make_controlled_phase,
)
from enterprise_fizzbuzz.domain.exceptions import (
    QuantumCircuitError,
    QuantumDecoherenceError,
    QuantumMeasurementError,
    QuantumAdvantageMirage,
    QuantumError,
)
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext


# ============================================================
#  QuantumRegister Tests
# ============================================================

class TestQuantumRegister(unittest.TestCase):
    """Tests for QuantumRegister state vector management."""

    def test_initialization_to_zero_state(self):
        """Register should initialize to |0...0> state."""
        reg = QuantumRegister(4)
        self.assertEqual(reg.num_qubits, 4)
        self.assertEqual(reg.num_states, 16)
        self.assertEqual(reg.amplitudes[0], complex(1))
        for i in range(1, 16):
            self.assertEqual(reg.amplitudes[i], complex(0))

    def test_norm_of_initialized_register(self):
        """Initial state should have norm 1.0."""
        reg = QuantumRegister(4)
        self.assertAlmostEqual(reg.get_norm(), 1.0, places=10)

    def test_probabilities_sum_to_one(self):
        """Measurement probabilities should sum to 1.0."""
        reg = QuantumRegister(4)
        probs = reg.get_probabilities()
        self.assertAlmostEqual(sum(probs), 1.0, places=10)

    def test_measurement_of_zero_state(self):
        """Measuring |0000> should always yield 0."""
        reg = QuantumRegister(4)
        result = reg.measure()
        self.assertEqual(result, 0)

    def test_measurement_collapses_state(self):
        """After measurement, state should be a computational basis state."""
        reg = QuantumRegister(4)
        # Put into superposition manually
        reg.amplitudes = [complex(0.25)] * 16
        reg.normalize()
        result = reg.measure()
        # After measurement, only one amplitude should be nonzero
        nonzero = sum(1 for a in reg.amplitudes if abs(a) > 1e-10)
        self.assertEqual(nonzero, 1)
        self.assertAlmostEqual(abs(reg.amplitudes[result]), 1.0, places=10)

    def test_reset(self):
        """Reset should restore |0...0> state."""
        reg = QuantumRegister(4)
        reg.amplitudes[0] = complex(0)
        reg.amplitudes[5] = complex(1)
        reg.reset()
        self.assertEqual(reg.amplitudes[0], complex(1))
        self.assertEqual(reg.amplitudes[5], complex(0))

    def test_normalize(self):
        """Normalize should restore unit norm."""
        reg = QuantumRegister(4)
        reg.amplitudes = [complex(2)] * 16
        reg.normalize()
        self.assertAlmostEqual(reg.get_norm(), 1.0, places=10)

    def test_min_qubits(self):
        """Register with 1 qubit should work."""
        reg = QuantumRegister(1)
        self.assertEqual(reg.num_states, 2)

    def test_invalid_qubits_zero(self):
        """0 qubits should raise ValueError."""
        with self.assertRaises(ValueError):
            QuantumRegister(0)

    def test_invalid_qubits_too_many(self):
        """More than 16 qubits should raise ValueError."""
        with self.assertRaises(ValueError):
            QuantumRegister(17)

    def test_repr_shows_nonzero_amplitudes(self):
        """repr should show nonzero amplitudes."""
        reg = QuantumRegister(2)
        r = repr(reg)
        self.assertIn("|00>", r)

    def test_measure_subset(self):
        """Measure subset should return bits for specified qubits."""
        reg = QuantumRegister(4)
        # State is |0000>, measuring any subset should give 0
        result = reg.measure_subset([0, 1])
        self.assertEqual(result, 0)


# ============================================================
#  Gate Matrix Tests
# ============================================================

class TestGateMatrices(unittest.TestCase):
    """Tests for quantum gate matrix definitions."""

    def _is_unitary(self, matrix: list[list[complex]], tol: float = 1e-10) -> bool:
        """Check if a matrix is unitary (U * U^dagger = I)."""
        n = len(matrix)
        for i in range(n):
            for j in range(n):
                val = sum(matrix[i][k] * matrix[j][k].conjugate() for k in range(n))
                expected = 1.0 if i == j else 0.0
                if abs(val - expected) > tol:
                    return False
        return True

    def test_hadamard_is_unitary(self):
        """Hadamard matrix should be unitary."""
        self.assertTrue(self._is_unitary(HADAMARD_MATRIX))

    def test_pauli_x_is_unitary(self):
        """Pauli-X matrix should be unitary."""
        self.assertTrue(self._is_unitary(PAULI_X_MATRIX))

    def test_pauli_z_is_unitary(self):
        """Pauli-Z matrix should be unitary."""
        self.assertTrue(self._is_unitary(PAULI_Z_MATRIX))

    def test_phase_s_is_unitary(self):
        """Phase S matrix should be unitary."""
        self.assertTrue(self._is_unitary(PHASE_S_MATRIX))

    def test_t_gate_is_unitary(self):
        """T gate matrix should be unitary."""
        self.assertTrue(self._is_unitary(T_GATE_MATRIX))

    def test_cnot_is_unitary(self):
        """CNOT matrix should be unitary."""
        self.assertTrue(self._is_unitary(CNOT_MATRIX))

    def test_controlled_phase_is_unitary(self):
        """Controlled phase gate should be unitary for any angle."""
        for angle in [0.0, math.pi / 4, math.pi / 2, math.pi]:
            matrix = make_controlled_phase(angle)
            self.assertTrue(self._is_unitary(matrix),
                            f"CP({angle}) is not unitary")

    def test_hadamard_superposition(self):
        """H|0> should give equal superposition."""
        # H * [1, 0] = [1/sqrt(2), 1/sqrt(2)]
        result = [
            HADAMARD_MATRIX[0][0] * 1 + HADAMARD_MATRIX[0][1] * 0,
            HADAMARD_MATRIX[1][0] * 1 + HADAMARD_MATRIX[1][1] * 0,
        ]
        expected = 1 / math.sqrt(2)
        self.assertAlmostEqual(abs(result[0]), expected, places=10)
        self.assertAlmostEqual(abs(result[1]), expected, places=10)


# ============================================================
#  QuantumCircuit Tests
# ============================================================

class TestQuantumCircuit(unittest.TestCase):
    """Tests for QuantumCircuit gate scheduling."""

    def test_create_empty_circuit(self):
        """Empty circuit should have 0 gates."""
        circuit = QuantumCircuit(4)
        self.assertEqual(circuit.gate_count, 0)
        self.assertEqual(circuit.depth, 0)

    def test_add_hadamard_gate(self):
        """Adding H gate should increase gate count."""
        circuit = QuantumCircuit(4)
        circuit.h(0)
        self.assertEqual(circuit.gate_count, 1)

    def test_add_cnot_gate(self):
        """Adding CNOT gate should work with different control/target."""
        circuit = QuantumCircuit(4)
        circuit.cx(0, 1)
        self.assertEqual(circuit.gate_count, 1)

    def test_cnot_same_qubit_raises_error(self):
        """CNOT with same control and target should raise error."""
        circuit = QuantumCircuit(4)
        with self.assertRaises(QuantumCircuitError):
            circuit.cx(0, 0)

    def test_invalid_qubit_raises_error(self):
        """Gate on qubit out of range should raise error."""
        circuit = QuantumCircuit(4)
        with self.assertRaises(QuantumCircuitError):
            circuit.h(5)

    def test_negative_qubit_raises_error(self):
        """Negative qubit index should raise error."""
        circuit = QuantumCircuit(4)
        with self.assertRaises(QuantumCircuitError):
            circuit.h(-1)

    def test_fluent_api(self):
        """Circuit methods should return self for chaining."""
        circuit = QuantumCircuit(4)
        result = circuit.h(0).x(1).z(2).s(3)
        self.assertIs(result, circuit)
        self.assertEqual(circuit.gate_count, 4)

    def test_measure_all(self):
        """measure_all should add measurement for every qubit."""
        circuit = QuantumCircuit(4)
        circuit.measure_all()
        # Measurements are tracked but not counted as gates
        measurements = [g for g in circuit.gates if g.is_measurement]
        self.assertEqual(len(measurements), 4)

    def test_controlled_phase_gate(self):
        """CP gate should be added with correct angle."""
        circuit = QuantumCircuit(4)
        circuit.cp(0, 1, math.pi / 4)
        self.assertEqual(circuit.gate_count, 1)
        self.assertIn("CP(", circuit.gates[0].name)

    def test_repr(self):
        """repr should show qubit and gate counts."""
        circuit = QuantumCircuit(4)
        circuit.h(0).h(1)
        r = repr(circuit)
        self.assertIn("qubits=4", r)
        self.assertIn("gates=2", r)


# ============================================================
#  QuantumSimulator Tests
# ============================================================

class TestQuantumSimulator(unittest.TestCase):
    """Tests for the state vector quantum simulator."""

    def test_hadamard_creates_superposition(self):
        """H on |0> should create equal superposition."""
        reg = QuantumRegister(1)
        circuit = QuantumCircuit(1)
        circuit.h(0)
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        probs = reg.get_probabilities()
        self.assertAlmostEqual(probs[0], 0.5, places=5)
        self.assertAlmostEqual(probs[1], 0.5, places=5)

    def test_pauli_x_flips_state(self):
        """X|0> should give |1>."""
        reg = QuantumRegister(1)
        circuit = QuantumCircuit(1)
        circuit.x(0)
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        self.assertAlmostEqual(abs(reg.amplitudes[0]), 0.0, places=10)
        self.assertAlmostEqual(abs(reg.amplitudes[1]), 1.0, places=10)

    def test_double_hadamard_identity(self):
        """H * H should give identity (return to |0>)."""
        reg = QuantumRegister(1)
        circuit = QuantumCircuit(1)
        circuit.h(0).h(0)
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        self.assertAlmostEqual(abs(reg.amplitudes[0]), 1.0, places=5)
        self.assertAlmostEqual(abs(reg.amplitudes[1]), 0.0, places=5)

    def test_cnot_with_control_zero(self):
        """CNOT with control=|0> should not flip target."""
        reg = QuantumRegister(2)
        circuit = QuantumCircuit(2)
        circuit.cx(0, 1)
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        # State should still be |00>
        self.assertAlmostEqual(abs(reg.amplitudes[0]), 1.0, places=10)

    def test_cnot_with_control_one(self):
        """CNOT with control=|1> should flip target."""
        reg = QuantumRegister(2)
        circuit = QuantumCircuit(2)
        circuit.x(0)  # Set control to |1>
        circuit.cx(0, 1)  # Should flip target
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        # State should be |11>
        self.assertAlmostEqual(abs(reg.amplitudes[3]), 1.0, places=10)

    def test_bell_state(self):
        """H on q0, CNOT(q0, q1) should create Bell state."""
        reg = QuantumRegister(2)
        circuit = QuantumCircuit(2)
        circuit.h(0).cx(0, 1)
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        probs = reg.get_probabilities()
        # Bell state: (|00> + |11>) / sqrt(2)
        self.assertAlmostEqual(probs[0], 0.5, places=5)  # |00>
        self.assertAlmostEqual(probs[1], 0.0, places=5)  # |01>
        self.assertAlmostEqual(probs[2], 0.0, places=5)  # |10>
        self.assertAlmostEqual(probs[3], 0.5, places=5)  # |11>

    def test_preserves_norm(self):
        """Gates should preserve the state vector norm."""
        reg = QuantumRegister(4)
        circuit = QuantumCircuit(4)
        circuit.h(0).h(1).cx(0, 2).h(3)
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        self.assertAlmostEqual(reg.get_norm(), 1.0, places=5)

    def test_gate_count_tracking(self):
        """Simulator should track number of gates applied."""
        reg = QuantumRegister(4)
        circuit = QuantumCircuit(4)
        circuit.h(0).h(1).h(2)
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        self.assertEqual(sim.gates_applied, 3)

    def test_measurement_tracking(self):
        """Simulator should track number of measurements."""
        reg = QuantumRegister(2)
        circuit = QuantumCircuit(2)
        circuit.h(0).measure_all()
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        self.assertEqual(sim.measurements_performed, 2)

    def test_execution_log(self):
        """Simulator should maintain an execution log."""
        reg = QuantumRegister(2)
        circuit = QuantumCircuit(2)
        circuit.h(0).measure(0)
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        log = sim.execution_log
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["type"], "gate")
        self.assertEqual(log[1]["type"], "measurement")

    def test_reset_stats(self):
        """reset_stats should clear all counters."""
        sim = QuantumSimulator()
        sim.gates_applied = 42
        sim.measurements_performed = 7
        sim.reset_stats()
        self.assertEqual(sim.gates_applied, 0)
        self.assertEqual(sim.measurements_performed, 0)


# ============================================================
#  QFT Circuit Tests
# ============================================================

class TestQFTCircuit(unittest.TestCase):
    """Tests for Quantum Fourier Transform circuit construction."""

    def test_qft_circuit_has_gates(self):
        """QFT circuit should contain gates."""
        circuit = build_qft_circuit(4)
        self.assertGreater(circuit.gate_count, 0)

    def test_qft_circuit_qubit_count(self):
        """QFT circuit should have correct qubit count."""
        circuit = build_qft_circuit(4)
        self.assertEqual(circuit.num_qubits, 4)

    def test_inverse_qft_circuit_has_gates(self):
        """Inverse QFT circuit should contain gates."""
        circuit = build_inverse_qft_circuit(4)
        self.assertGreater(circuit.gate_count, 0)

    def test_qft_preserves_norm(self):
        """QFT should preserve the state vector norm."""
        reg = QuantumRegister(4)
        circuit = build_qft_circuit(4)
        sim = QuantumSimulator()
        sim.execute(circuit, reg)
        self.assertAlmostEqual(reg.get_norm(), 1.0, places=4)

    def test_qft_then_inverse_qft_identity(self):
        """QFT followed by inverse QFT should approximate identity."""
        reg = QuantumRegister(4)
        # Save original state
        original = list(reg.amplitudes)

        # Apply QFT then inverse QFT
        qft = build_qft_circuit(4)
        inv_qft = build_inverse_qft_circuit(4)
        sim = QuantumSimulator()
        sim.execute(qft, reg)
        sim.execute(inv_qft, reg)

        # State should be close to original
        for i in range(16):
            self.assertAlmostEqual(
                abs(reg.amplitudes[i]), abs(original[i]),
                places=3,
                msg=f"Amplitude mismatch at index {i}",
            )

    def test_qft_with_target_qubits(self):
        """QFT should work with specific target qubits."""
        circuit = build_qft_circuit(4, target_qubits=[0, 1])
        self.assertGreater(circuit.gate_count, 0)


# ============================================================
#  ShorDivisibilityChecker Tests
# ============================================================

class TestShorDivisibilityChecker(unittest.TestCase):
    """Tests for the simplified Shor's algorithm divisibility checker."""

    def setUp(self):
        """Create a checker with small qubit count for speed."""
        self.checker = ShorDivisibilityChecker(
            num_qubits=4,
            max_attempts=5,
            fallback_to_classical=True,
        )

    def test_divisible_by_3(self):
        """9 should be divisible by 3."""
        result = self.checker.check_divisibility(9, 3)
        self.assertTrue(result.is_divisible)

    def test_not_divisible_by_3(self):
        """7 should not be divisible by 3."""
        result = self.checker.check_divisibility(7, 3)
        self.assertFalse(result.is_divisible)

    def test_divisible_by_5(self):
        """15 should be divisible by 5."""
        result = self.checker.check_divisibility(15, 5)
        self.assertTrue(result.is_divisible)

    def test_not_divisible_by_5(self):
        """13 should not be divisible by 5."""
        result = self.checker.check_divisibility(13, 5)
        self.assertFalse(result.is_divisible)

    def test_zero_divisible_by_anything(self):
        """0 should be divisible by any number."""
        result = self.checker.check_divisibility(0, 3)
        self.assertTrue(result.is_divisible)

    def test_divisor_one(self):
        """Everything is divisible by 1."""
        result = self.checker.check_divisibility(42, 1)
        self.assertTrue(result.is_divisible)

    def test_result_has_timing(self):
        """Result should include timing information."""
        result = self.checker.check_divisibility(15, 3)
        self.assertGreater(result.quantum_time_ns, 0)

    def test_quantum_advantage_is_negative(self):
        """The quantum advantage ratio should always be negative."""
        result = self.checker.check_divisibility(15, 3)
        # Quantum is always slower than classical modulo
        self.assertLessEqual(result.quantum_advantage_ratio, 0)

    def test_stats_tracking(self):
        """Checker should track total checks and fallbacks."""
        self.checker.check_divisibility(9, 3)
        self.checker.check_divisibility(10, 5)
        self.assertEqual(self.checker.total_checks, 2)

    def test_results_log(self):
        """Checker should maintain a results log."""
        self.checker.check_divisibility(9, 3)
        self.assertEqual(len(self.checker.results_log), 1)

    def test_success_rate(self):
        """Success rate should be between 0 and 1."""
        self.checker.check_divisibility(9, 3)
        rate = self.checker.success_rate
        self.assertGreaterEqual(rate, 0.0)
        self.assertLessEqual(rate, 1.0)

    def test_reset_stats(self):
        """reset_stats should clear all counters."""
        self.checker.check_divisibility(9, 3)
        self.checker.reset_stats()
        self.assertEqual(self.checker.total_checks, 0)
        self.assertEqual(len(self.checker.results_log), 0)

    def test_no_fallback_mode(self):
        """Without fallback, results may not have correct answers."""
        checker = ShorDivisibilityChecker(
            num_qubits=4,
            max_attempts=1,
            fallback_to_classical=False,
        )
        # Should not crash even without fallback
        result = checker.check_divisibility(7, 3)
        self.assertIsInstance(result, ShorResult)


# ============================================================
#  QuantumFizzBuzzEngine Tests
# ============================================================

class TestQuantumFizzBuzzEngine(unittest.TestCase):
    """Tests for the Quantum FizzBuzz evaluation engine."""

    def setUp(self):
        """Create an engine with standard FizzBuzz rules."""
        self.rules = [
            {"name": "FizzRule", "divisor": 3, "label": "Fizz", "priority": 1},
            {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
        ]
        self.engine = QuantumFizzBuzzEngine(
            rules=self.rules,
            num_qubits=4,
            max_attempts=5,
            fallback_to_classical=True,
        )

    def test_fizz(self):
        """3 should produce 'Fizz'."""
        result = self.engine.evaluate(3)
        self.assertEqual(result.output, "Fizz")

    def test_buzz(self):
        """5 should produce 'Buzz'."""
        result = self.engine.evaluate(5)
        self.assertEqual(result.output, "Buzz")

    def test_fizzbuzz(self):
        """15 should produce 'FizzBuzz'."""
        result = self.engine.evaluate(15)
        self.assertEqual(result.output, "FizzBuzz")

    def test_plain_number(self):
        """7 should produce '7'."""
        result = self.engine.evaluate(7)
        self.assertEqual(result.output, "7")

    def test_one(self):
        """1 should produce '1'."""
        result = self.engine.evaluate(1)
        self.assertEqual(result.output, "1")

    def test_evaluation_log(self):
        """Engine should maintain evaluation log."""
        self.engine.evaluate(15)
        self.assertEqual(len(self.engine.evaluation_log), 1)
        self.assertEqual(self.engine.total_evaluations, 1)

    def test_quantum_advantage_is_always_negative(self):
        """Average quantum advantage should be negative or zero."""
        for n in [3, 5, 15, 7]:
            self.engine.evaluate(n)
        self.assertLessEqual(self.engine.average_quantum_advantage, 0)

    def test_full_range_correctness(self):
        """Quantum engine should produce correct FizzBuzz for range 1-30."""
        for n in range(1, 31):
            result = self.engine.evaluate(n)
            expected = ""
            if n % 3 == 0:
                expected += "Fizz"
            if n % 5 == 0:
                expected += "Buzz"
            if not expected:
                expected = str(n)
            self.assertEqual(
                result.output, expected,
                f"Number {n}: expected '{expected}', got '{result.output}'",
            )

    def test_reset(self):
        """Reset should clear evaluation log."""
        self.engine.evaluate(15)
        self.engine.reset()
        self.assertEqual(self.engine.total_evaluations, 0)
        self.assertEqual(len(self.engine.evaluation_log), 0)


# ============================================================
#  CircuitVisualizer Tests
# ============================================================

class TestCircuitVisualizer(unittest.TestCase):
    """Tests for ASCII circuit diagram rendering."""

    def test_render_empty_circuit(self):
        """Empty circuit should render without crashing."""
        circuit = QuantumCircuit(2)
        output = CircuitVisualizer.render(circuit)
        self.assertIn("q0", output)
        self.assertIn("q1", output)

    def test_render_hadamard(self):
        """Circuit with H gate should show [H]."""
        circuit = QuantumCircuit(2)
        circuit.h(0)
        output = CircuitVisualizer.render(circuit)
        self.assertIn("[H]", output)

    def test_render_measurement(self):
        """Circuit with measurement should show [M]."""
        circuit = QuantumCircuit(2)
        circuit.measure(0)
        output = CircuitVisualizer.render(circuit)
        self.assertIn("[M]", output)

    def test_render_cnot(self):
        """Circuit with CNOT should show [*] and [X]."""
        circuit = QuantumCircuit(2)
        circuit.cx(0, 1)
        output = CircuitVisualizer.render(circuit)
        self.assertIn("[*]", output)
        self.assertIn("[X]", output)

    def test_render_complex_circuit(self):
        """Complex circuit should render without crashing."""
        circuit = QuantumCircuit(4)
        circuit.h(0).h(1).cx(0, 2).z(3).measure_all()
        output = CircuitVisualizer.render(circuit, width=80)
        self.assertIn("q0", output)
        self.assertIn("q3", output)


# ============================================================
#  QuantumDashboard Tests
# ============================================================

class TestQuantumDashboard(unittest.TestCase):
    """Tests for the Quantum Computing Simulator dashboard."""

    def setUp(self):
        """Create an engine and run some evaluations."""
        rules = [
            {"name": "FizzRule", "divisor": 3, "label": "Fizz", "priority": 1},
            {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
        ]
        self.engine = QuantumFizzBuzzEngine(
            rules=rules, num_qubits=4, fallback_to_classical=True,
        )
        for n in range(1, 6):
            self.engine.evaluate(n)

    def test_render_without_circuit(self):
        """Dashboard should render without a circuit."""
        output = QuantumDashboard.render(self.engine, width=60)
        self.assertIn("QUANTUM COMPUTING SIMULATOR DASHBOARD", output)
        self.assertIn("Quantum Advantage", output)
        self.assertIn("DISCLAIMER", output)

    def test_render_with_circuit(self):
        """Dashboard should render with a circuit diagram."""
        circuit = build_qft_circuit(4)
        circuit.measure_all()
        output = QuantumDashboard.render(
            self.engine, circuit=circuit, width=60, show_circuit=True,
        )
        self.assertIn("SAMPLE CIRCUIT DIAGRAM", output)

    def test_shows_negative_advantage(self):
        """Dashboard should show negative quantum advantage."""
        output = QuantumDashboard.render(self.engine, width=60)
        # Should contain negative scientific notation or "SLOWER"
        self.assertTrue(
            "SLOWER" in output or "-" in output,
            "Dashboard should indicate quantum is slower"
        )

    def test_shows_statistics(self):
        """Dashboard should show evaluation statistics."""
        output = QuantumDashboard.render(self.engine, width=60)
        self.assertIn("Total Evaluations", output)
        self.assertIn("Gates Applied", output)
        self.assertIn("Hilbert Space Dimension", output)


# ============================================================
#  QuantumMiddleware Tests
# ============================================================

class TestQuantumMiddleware(unittest.TestCase):
    """Tests for the QuantumMiddleware pipeline integration."""

    def setUp(self):
        """Create middleware with a quantum engine."""
        rules = [
            {"name": "FizzRule", "divisor": 3, "label": "Fizz", "priority": 1},
            {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
        ]
        self.engine = QuantumFizzBuzzEngine(
            rules=rules, num_qubits=4, fallback_to_classical=True,
        )
        self.middleware = QuantumMiddleware(engine=self.engine)

    def test_get_name(self):
        """Middleware should return 'QuantumMiddleware'."""
        self.assertEqual(self.middleware.get_name(), "QuantumMiddleware")

    def test_get_priority(self):
        """Middleware should have priority -7."""
        self.assertEqual(self.middleware.get_priority(), -7)

    def test_process_adds_quantum_metadata(self):
        """Middleware should add quantum metadata to context."""
        context = ProcessingContext(number=15, session_id="test-session")
        next_handler = MagicMock(return_value=context)

        result = self.middleware.process(context, next_handler)

        self.assertIn("quantum_output", result.metadata)
        self.assertEqual(result.metadata["quantum_output"], "FizzBuzz")
        self.assertIn("quantum_advantage_ratio", result.metadata)
        self.assertIn("quantum_time_ns", result.metadata)

    def test_process_calls_next_handler(self):
        """Middleware should call the next handler in the pipeline."""
        context = ProcessingContext(number=7, session_id="test-session")
        next_handler = MagicMock(return_value=context)

        self.middleware.process(context, next_handler)

        next_handler.assert_called_once_with(context)

    def test_process_with_event_bus(self):
        """Middleware should emit events when event bus is provided."""
        event_bus = MagicMock()
        middleware = QuantumMiddleware(engine=self.engine, event_bus=event_bus)

        context = ProcessingContext(number=15, session_id="test-session")
        next_handler = MagicMock(return_value=context)

        middleware.process(context, next_handler)

        # Should have emitted at least 2 events
        self.assertGreaterEqual(event_bus.publish.call_count, 2)

    def test_engine_property(self):
        """Middleware should expose the engine property."""
        self.assertIs(self.middleware.engine, self.engine)


# ============================================================
#  Exception Tests
# ============================================================

class TestQuantumExceptions(unittest.TestCase):
    """Tests for quantum-specific exceptions."""

    def test_quantum_error_base(self):
        """QuantumError should be a FizzBuzzError."""
        err = QuantumError("test")
        self.assertIn("EFP-QC00", str(err))

    def test_decoherence_error(self):
        """QuantumDecoherenceError should include norm info."""
        err = QuantumDecoherenceError(norm=0.95)
        self.assertIn("0.95", str(err))
        self.assertIn("EFP-QC01", str(err))

    def test_circuit_error(self):
        """QuantumCircuitError should include gate and qubit info."""
        err = QuantumCircuitError("H", [5], 4)
        self.assertIn("EFP-QC02", str(err))
        self.assertIn("H", str(err))

    def test_measurement_error(self):
        """QuantumMeasurementError should include outcome info."""
        err = QuantumMeasurementError(outcome=7, probability=0.0)
        self.assertIn("EFP-QC03", str(err))

    def test_advantage_mirage(self):
        """QuantumAdvantageMirage should report negative advantage."""
        err = QuantumAdvantageMirage(classical_ns=10, quantum_ns=1000000)
        self.assertIn("EFP-QC04", str(err))
        self.assertIn("negative", str(err).lower())


# ============================================================
#  ShorResult Tests
# ============================================================

class TestShorResult(unittest.TestCase):
    """Tests for ShorResult dataclass."""

    def test_quantum_advantage_ratio_negative(self):
        """Advantage ratio should be negative when quantum is slower."""
        result = ShorResult(
            number=15, divisor=3, is_divisible=True,
            quantum_time_ns=1000.0, classical_time_ns=1.0,
        )
        self.assertLess(result.quantum_advantage_ratio, 0)

    def test_quantum_advantage_ratio_zero_classical(self):
        """Should handle zero classical time gracefully."""
        result = ShorResult(
            number=15, divisor=3, is_divisible=True,
            quantum_time_ns=1000.0, classical_time_ns=0.0,
        )
        self.assertEqual(result.quantum_advantage_ratio, -float("inf"))


# ============================================================
#  QuantumEvaluationResult Tests
# ============================================================

class TestQuantumEvaluationResult(unittest.TestCase):
    """Tests for QuantumEvaluationResult dataclass."""

    def test_advantage_ratio(self):
        """Should compute advantage ratio from totals."""
        from enterprise_fizzbuzz.infrastructure.quantum import QuantumEvaluationResult
        result = QuantumEvaluationResult(
            number=15, output="FizzBuzz", matched_rules=["Fizz", "Buzz"],
            shor_results=[], total_quantum_time_ns=1000.0,
            total_classical_time_ns=1.0,
        )
        self.assertLess(result.quantum_advantage_ratio, 0)


# ============================================================
#  Integration / Edge Case Tests
# ============================================================

class TestQuantumIntegration(unittest.TestCase):
    """Integration and edge case tests."""

    def test_large_number_divisibility(self):
        """Should handle large numbers via classical fallback."""
        checker = ShorDivisibilityChecker(
            num_qubits=4, max_attempts=2, fallback_to_classical=True,
        )
        result = checker.check_divisibility(999, 3)
        self.assertTrue(result.is_divisible)

    def test_prime_number_not_divisible(self):
        """Prime numbers should not be divisible by 3 or 5."""
        engine = QuantumFizzBuzzEngine(
            rules=[
                {"name": "FizzRule", "divisor": 3, "label": "Fizz", "priority": 1},
                {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
            ],
            num_qubits=4,
            fallback_to_classical=True,
        )
        for prime in [7, 11, 13, 17, 19, 23, 29]:
            result = engine.evaluate(prime)
            self.assertEqual(result.output, str(prime),
                             f"Prime {prime} should output itself")

    def test_multiple_evaluations_consistent(self):
        """Multiple evaluations of same number should give same result."""
        engine = QuantumFizzBuzzEngine(
            rules=[
                {"name": "FizzRule", "divisor": 3, "label": "Fizz", "priority": 1},
                {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
            ],
            num_qubits=4,
            fallback_to_classical=True,
        )
        results = [engine.evaluate(15).output for _ in range(10)]
        self.assertTrue(all(r == "FizzBuzz" for r in results))

    def test_qft_circuit_different_sizes(self):
        """QFT circuits should work for different qubit counts."""
        for n in [2, 3, 4, 5, 6]:
            circuit = build_qft_circuit(n)
            self.assertEqual(circuit.num_qubits, n)
            self.assertGreater(circuit.gate_count, 0)


if __name__ == "__main__":
    unittest.main()
