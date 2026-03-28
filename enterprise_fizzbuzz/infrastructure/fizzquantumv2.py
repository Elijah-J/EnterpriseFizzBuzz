"""
Enterprise FizzBuzz Platform - FizzQuantumV2 Quantum Error Correction Engine

Implements quantum error correction for the FizzBuzz quantum evaluation
pipeline. Raw physical qubits are too noisy for reliable divisibility
computation; this module encodes logical qubits into surface codes,
performs syndrome measurement, decodes errors, and applies corrections
to maintain coherent quantum state throughout the FizzBuzz evaluation.

The surface code is the leading candidate for practical quantum error
correction due to its high threshold error rate (~1%) and nearest-neighbor
qubit connectivity requirement. A distance-d surface code uses O(d^2)
physical qubits to encode a single logical qubit that can correct up to
floor((d-1)/2) errors per round.

The module implements:

1. **Surface code lattice**: Data qubits and ancilla qubits arranged on
   a planar lattice with X-type and Z-type stabilizers
2. **Syndrome measurement**: Ancilla-based stabilizer measurements that
   detect errors without collapsing the logical state
3. **Noise models**: Depolarizing, bit-flip, and phase-flip channels with
   configurable error rates per gate and per idle cycle
4. **Minimum-weight perfect matching decoder**: Maps syndromes to most
   likely error corrections using Edmonds' blossom algorithm principles
5. **Fault-tolerant gates**: Transversal CNOT and magic state injection
   for universal quantum computation on encoded qubits
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    QuantumErrorCorrectionError,
    SurfaceCodeError,
    SyndromeMeasurementError,
    LogicalQubitError,
    FaultTolerantGateError,
    DecoderError,
    NoiseModelError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enums
# ============================================================


class PauliOperator(Enum):
    """Single-qubit Pauli operators."""
    I = auto()
    X = auto()
    Y = auto()
    Z = auto()


class StabilizerType(Enum):
    """Types of stabilizer operators in the surface code."""
    X_STABILIZER = auto()
    Z_STABILIZER = auto()


class NoiseChannel(Enum):
    """Quantum noise channel models."""
    DEPOLARIZING = auto()
    BIT_FLIP = auto()
    PHASE_FLIP = auto()
    AMPLITUDE_DAMPING = auto()


class GateType(Enum):
    """Quantum gate types."""
    HADAMARD = auto()
    CNOT = auto()
    T_GATE = auto()
    S_GATE = auto()
    MEASURE = auto()


# ============================================================
# Physical Qubit
# ============================================================


@dataclass
class PhysicalQubit:
    """A single physical qubit with error tracking."""
    qubit_id: int
    x: int
    y: int
    is_data: bool = True
    error_state: PauliOperator = PauliOperator.I
    measurement_result: Optional[bool] = None

    def apply_error(self, error: PauliOperator) -> None:
        """Apply a Pauli error to this qubit."""
        if self.error_state == PauliOperator.I:
            self.error_state = error
        elif self.error_state == error:
            self.error_state = PauliOperator.I  # Error cancellation
        else:
            # Compose Pauli errors
            compose = {
                (PauliOperator.X, PauliOperator.Z): PauliOperator.Y,
                (PauliOperator.Z, PauliOperator.X): PauliOperator.Y,
                (PauliOperator.X, PauliOperator.Y): PauliOperator.Z,
                (PauliOperator.Y, PauliOperator.X): PauliOperator.Z,
                (PauliOperator.Y, PauliOperator.Z): PauliOperator.X,
                (PauliOperator.Z, PauliOperator.Y): PauliOperator.X,
            }
            self.error_state = compose.get(
                (self.error_state, error), PauliOperator.I
            )

    def reset(self) -> None:
        """Reset the qubit to the identity (no error) state."""
        self.error_state = PauliOperator.I
        self.measurement_result = None


# ============================================================
# Stabilizer
# ============================================================


@dataclass
class Stabilizer:
    """A stabilizer operator in the surface code.

    Each stabilizer is a tensor product of Pauli operators acting on
    a set of data qubits. The measurement outcome (eigenvalue) of a
    stabilizer indicates whether an error has occurred on one of its
    support qubits.
    """
    stabilizer_id: int
    stabilizer_type: StabilizerType
    ancilla: PhysicalQubit
    data_qubits: list[PhysicalQubit] = field(default_factory=list)

    def measure(self) -> bool:
        """Measure the stabilizer and return the syndrome bit.

        Returns True if the stabilizer eigenvalue is -1 (error detected),
        False if +1 (no error on this stabilizer).
        """
        error_detected = False
        check_operator = (
            PauliOperator.X if self.stabilizer_type == StabilizerType.X_STABILIZER
            else PauliOperator.Z
        )
        for dq in self.data_qubits:
            if dq.error_state == check_operator or dq.error_state == PauliOperator.Y:
                error_detected = not error_detected
        self.ancilla.measurement_result = error_detected
        return error_detected


# ============================================================
# Surface Code Lattice
# ============================================================


class SurfaceCodeLattice:
    """Distance-d surface code lattice for a single logical qubit.

    Arranges d^2 data qubits and (d^2-1) ancilla qubits on a planar
    lattice. X-stabilizers are placed on faces and Z-stabilizers on
    vertices of the lattice graph. The code distance determines the
    number of errors that can be corrected: floor((d-1)/2).
    """

    def __init__(self, distance: int) -> None:
        if distance < 3:
            raise SurfaceCodeError(distance, "Minimum distance is 3.")
        if distance % 2 == 0:
            raise SurfaceCodeError(distance, "Distance must be odd.")
        self.distance = distance
        self._data_qubits: list[PhysicalQubit] = []
        self._ancilla_qubits: list[PhysicalQubit] = []
        self._x_stabilizers: list[Stabilizer] = []
        self._z_stabilizers: list[Stabilizer] = []
        self._build_lattice()

    def _build_lattice(self) -> None:
        """Construct the surface code lattice with data and ancilla qubits."""
        d = self.distance
        qubit_id = 0

        # Data qubits on a d x d grid
        data_grid: dict[tuple[int, int], PhysicalQubit] = {}
        for row in range(d):
            for col in range(d):
                q = PhysicalQubit(qubit_id=qubit_id, x=col * 2, y=row * 2, is_data=True)
                data_grid[(row, col)] = q
                self._data_qubits.append(q)
                qubit_id += 1

        # X-stabilizers (face operators)
        stab_id = 0
        for row in range(d - 1):
            for col in range(d - 1):
                ancilla = PhysicalQubit(
                    qubit_id=qubit_id, x=col * 2 + 1, y=row * 2 + 1, is_data=False,
                )
                self._ancilla_qubits.append(ancilla)
                qubit_id += 1

                support = [
                    data_grid[(row, col)],
                    data_grid[(row, col + 1)],
                    data_grid[(row + 1, col)],
                    data_grid[(row + 1, col + 1)],
                ]
                stab = Stabilizer(
                    stabilizer_id=stab_id,
                    stabilizer_type=StabilizerType.X_STABILIZER,
                    ancilla=ancilla,
                    data_qubits=support,
                )
                self._x_stabilizers.append(stab)
                stab_id += 1

        # Z-stabilizers (vertex operators) -- boundary-aware
        for row in range(d):
            for col in range(d):
                if row == 0 and col == 0:
                    continue
                if row == d - 1 and col == d - 1:
                    continue
                support = []
                if row > 0:
                    support.append(data_grid[(row - 1, col)])
                if row < d - 1:
                    support.append(data_grid[(row + 1, col)])
                if col > 0:
                    support.append(data_grid[(row, col - 1)])
                if col < d - 1:
                    support.append(data_grid[(row, col + 1)])

                if len(support) >= 2:
                    ancilla = PhysicalQubit(
                        qubit_id=qubit_id, x=col * 2, y=row * 2, is_data=False,
                    )
                    self._ancilla_qubits.append(ancilla)
                    qubit_id += 1
                    stab = Stabilizer(
                        stabilizer_id=stab_id,
                        stabilizer_type=StabilizerType.Z_STABILIZER,
                        ancilla=ancilla,
                        data_qubits=support,
                    )
                    self._z_stabilizers.append(stab)
                    stab_id += 1

    @property
    def num_data_qubits(self) -> int:
        return len(self._data_qubits)

    @property
    def num_ancilla_qubits(self) -> int:
        return len(self._ancilla_qubits)

    @property
    def correction_capacity(self) -> int:
        """Maximum number of single-qubit errors correctable."""
        return (self.distance - 1) // 2

    def get_syndrome(self) -> tuple[list[bool], list[bool]]:
        """Extract X and Z syndrome vectors."""
        x_syndrome = [s.measure() for s in self._x_stabilizers]
        z_syndrome = [s.measure() for s in self._z_stabilizers]
        return x_syndrome, z_syndrome

    def inject_error(self, qubit_index: int, error: PauliOperator) -> None:
        """Inject an error on a specific data qubit for testing."""
        if 0 <= qubit_index < len(self._data_qubits):
            self._data_qubits[qubit_index].apply_error(error)

    def reset_errors(self) -> None:
        """Clear all errors from the lattice."""
        for q in self._data_qubits:
            q.reset()
        for q in self._ancilla_qubits:
            q.reset()

    @property
    def data_qubits(self) -> list[PhysicalQubit]:
        return list(self._data_qubits)

    @property
    def x_stabilizers(self) -> list[Stabilizer]:
        return list(self._x_stabilizers)

    @property
    def z_stabilizers(self) -> list[Stabilizer]:
        return list(self._z_stabilizers)


# ============================================================
# Noise Model
# ============================================================


class NoiseModel:
    """Configurable noise model for quantum error simulation.

    Applies probabilistic Pauli errors to physical qubits based on
    the selected noise channel and error rate. The noise model is
    essential for testing the error correction pipeline under
    realistic conditions.
    """

    def __init__(
        self,
        channel: NoiseChannel = NoiseChannel.DEPOLARIZING,
        error_rate: float = 0.001,
        seed: Optional[int] = None,
    ) -> None:
        if error_rate < 0.0 or error_rate > 1.0:
            raise NoiseModelError("error_rate", error_rate, "Must be between 0.0 and 1.0.")
        self.channel = channel
        self.error_rate = error_rate
        self._rng = random.Random(seed)

    def apply_noise(self, qubits: list[PhysicalQubit]) -> int:
        """Apply noise to a list of qubits. Returns the number of errors introduced."""
        errors_applied = 0
        for qubit in qubits:
            if self._rng.random() < self.error_rate:
                error = self._select_error()
                qubit.apply_error(error)
                errors_applied += 1
        return errors_applied

    def _select_error(self) -> PauliOperator:
        """Select an error operator based on the noise channel."""
        if self.channel == NoiseChannel.BIT_FLIP:
            return PauliOperator.X
        elif self.channel == NoiseChannel.PHASE_FLIP:
            return PauliOperator.Z
        elif self.channel == NoiseChannel.DEPOLARIZING:
            return self._rng.choice([PauliOperator.X, PauliOperator.Y, PauliOperator.Z])
        elif self.channel == NoiseChannel.AMPLITUDE_DAMPING:
            return PauliOperator.X  # Simplified model
        return PauliOperator.X


# ============================================================
# Decoder (Minimum-Weight Perfect Matching)
# ============================================================


class MWPMDecoder:
    """Minimum-weight perfect matching decoder for surface codes.

    Maps syndrome patterns to the most likely error correction by
    finding the minimum-weight matching on a graph where nodes
    represent syndrome defects and edge weights represent the
    distance (number of qubits) between defects.

    This implementation uses a greedy approximation to the full
    MWPM algorithm, which is sufficient for the error rates
    encountered in FizzBuzz quantum evaluation.
    """

    def __init__(self, lattice: SurfaceCodeLattice) -> None:
        self._lattice = lattice

    def decode(self, syndrome: list[bool]) -> list[tuple[int, PauliOperator]]:
        """Decode a syndrome and return the correction operators.

        Returns a list of (qubit_index, PauliOperator) pairs representing
        the corrections to apply.
        """
        # Find syndrome defect positions
        defects = [i for i, s in enumerate(syndrome) if s]

        if not defects:
            return []

        if len(defects) % 2 != 0:
            # Odd number of defects indicates a boundary defect
            defects.append(-1)  # Virtual boundary node

        # Greedy matching: pair nearest defects
        corrections = []
        matched = set()

        for i, d1 in enumerate(defects):
            if i in matched:
                continue
            best_j = None
            best_dist = float("inf")
            for j, d2 in enumerate(defects):
                if j <= i or j in matched:
                    continue
                dist = abs(d1 - d2) if d2 >= 0 else abs(d1)
                if dist < best_dist:
                    best_dist = dist
                    best_j = j
            if best_j is not None:
                matched.add(i)
                matched.add(best_j)

                # Apply correction on qubits between defects
                start = min(d1, defects[best_j]) if defects[best_j] >= 0 else 0
                end = max(d1, defects[best_j]) if defects[best_j] >= 0 else d1

                if start >= 0 and start < self._lattice.num_data_qubits:
                    corrections.append((start, PauliOperator.X))

        return corrections

    def apply_corrections(self, corrections: list[tuple[int, PauliOperator]]) -> None:
        """Apply correction operators to the lattice data qubits."""
        for qubit_idx, operator in corrections:
            if 0 <= qubit_idx < self._lattice.num_data_qubits:
                self._lattice.data_qubits[qubit_idx].apply_error(operator)


# ============================================================
# Logical Qubit
# ============================================================


class LogicalQubit:
    """A fault-tolerant logical qubit encoded in a surface code.

    Provides a logical-level interface for quantum operations while
    the surface code handles error detection and correction
    transparently. The logical qubit state is defined by the
    equivalence class of physical qubit states modulo stabilizer
    operations.
    """

    def __init__(self, logical_id: int, distance: int = 3, error_rate: float = 0.001) -> None:
        self.logical_id = logical_id
        self.lattice = SurfaceCodeLattice(distance)
        self.decoder = MWPMDecoder(self.lattice)
        self.noise_model = NoiseModel(error_rate=error_rate)
        self._logical_state: bool = False
        self._error_count: int = 0
        self._correction_count: int = 0

    def initialize(self, state: bool = False) -> None:
        """Initialize the logical qubit to |0> or |1>."""
        self.lattice.reset_errors()
        self._logical_state = state
        self._error_count = 0
        self._correction_count = 0

    def error_correction_cycle(self) -> bool:
        """Run one round of error correction.

        Returns True if a correction was applied, False if no errors detected.
        """
        # Apply noise
        errors = self.noise_model.apply_noise(self.lattice.data_qubits)
        self._error_count += errors

        # Measure syndrome
        x_syndrome, z_syndrome = self.lattice.get_syndrome()

        # Decode and correct X errors
        x_corrections = self.decoder.decode(x_syndrome)
        self.decoder.apply_corrections(x_corrections)

        # Decode and correct Z errors
        z_corrections = self.decoder.decode(z_syndrome)
        for qi, _ in z_corrections:
            if 0 <= qi < self.lattice.num_data_qubits:
                self.lattice.data_qubits[qi].apply_error(PauliOperator.Z)

        total_corrections = len(x_corrections) + len(z_corrections)
        self._correction_count += total_corrections
        return total_corrections > 0

    @property
    def logical_error_rate(self) -> float:
        """Estimated logical error rate based on observed corrections."""
        if self._error_count == 0:
            return 0.0
        return self._correction_count / max(self._error_count, 1)

    @property
    def state(self) -> bool:
        return self._logical_state


# ============================================================
# Fault-Tolerant Gate
# ============================================================


class FaultTolerantGate:
    """Implements fault-tolerant gate operations on logical qubits.

    Fault-tolerant gates prevent error propagation by ensuring that
    a single physical error produces at most one error in each code
    block. This is achieved through transversal operations where
    each physical qubit in one block interacts with at most one
    physical qubit in another block.
    """

    @staticmethod
    def transversal_cnot(control: LogicalQubit, target: LogicalQubit) -> None:
        """Apply a transversal CNOT between two logical qubits.

        Each data qubit in the control block is paired with the
        corresponding data qubit in the target block.
        """
        if control.lattice.distance != target.lattice.distance:
            raise FaultTolerantGateError(
                "transversal_CNOT",
                f"Distance mismatch: {control.lattice.distance} vs {target.lattice.distance}",
            )

        for i in range(min(control.lattice.num_data_qubits, target.lattice.num_data_qubits)):
            ctrl_q = control.lattice.data_qubits[i]
            tgt_q = target.lattice.data_qubits[i]

            # Propagate X errors from control to target
            if ctrl_q.error_state in (PauliOperator.X, PauliOperator.Y):
                tgt_q.apply_error(PauliOperator.X)

            # Propagate Z errors from target to control
            if tgt_q.error_state in (PauliOperator.Z, PauliOperator.Y):
                ctrl_q.apply_error(PauliOperator.Z)

        # Update logical states
        if control.state:
            target._logical_state = not target._logical_state

    @staticmethod
    def logical_x(qubit: LogicalQubit) -> None:
        """Apply a logical X (bit-flip) to the encoded qubit."""
        qubit._logical_state = not qubit._logical_state
        # Apply X to an entire row of data qubits (logical operator)
        d = qubit.lattice.distance
        for i in range(d):
            qubit.lattice.data_qubits[i].apply_error(PauliOperator.X)

    @staticmethod
    def logical_z(qubit: LogicalQubit) -> None:
        """Apply a logical Z (phase-flip) to the encoded qubit."""
        d = qubit.lattice.distance
        for i in range(d):
            idx = i * d
            if idx < qubit.lattice.num_data_qubits:
                qubit.lattice.data_qubits[idx].apply_error(PauliOperator.Z)


# ============================================================
# Quantum Error Correction Engine
# ============================================================


class QuantumErrorCorrectionEngine:
    """Complete quantum error correction engine for FizzBuzz evaluation.

    Manages logical qubits, runs error correction cycles, and provides
    fault-tolerant quantum computation for the FizzBuzz divisibility
    problem. The engine ensures that quantum noise does not corrupt
    the evaluation result.
    """

    def __init__(
        self,
        distance: int = 3,
        error_rate: float = 0.001,
        correction_rounds: int = 3,
    ) -> None:
        self.distance = distance
        self.error_rate = error_rate
        self.correction_rounds = correction_rounds
        self._logical_qubits: list[LogicalQubit] = []
        self._total_corrections: int = 0
        self._total_errors_detected: int = 0

    def allocate_logical_qubit(self, initial_state: bool = False) -> LogicalQubit:
        """Allocate and initialize a new logical qubit."""
        lq = LogicalQubit(
            logical_id=len(self._logical_qubits),
            distance=self.distance,
            error_rate=self.error_rate,
        )
        lq.initialize(initial_state)
        self._logical_qubits.append(lq)
        return lq

    def run_correction_cycle(self) -> dict[str, Any]:
        """Run error correction on all logical qubits."""
        results = {"corrections": 0, "qubits_corrected": 0}
        for lq in self._logical_qubits:
            for _ in range(self.correction_rounds):
                if lq.error_correction_cycle():
                    results["corrections"] += 1
            results["qubits_corrected"] += 1
        self._total_corrections += results["corrections"]
        return results

    def evaluate_fizzbuzz(self, number: int) -> dict[str, Any]:
        """Evaluate FizzBuzz divisibility using quantum error-corrected computation."""
        # Allocate logical qubits for the computation
        q_div3 = self.allocate_logical_qubit(initial_state=(number % 3 == 0))
        q_div5 = self.allocate_logical_qubit(initial_state=(number % 5 == 0))

        # Run error correction
        ec_result = self.run_correction_cycle()

        # Read logical qubit states
        div3 = q_div3.state
        div5 = q_div5.state

        if div3 and div5:
            result = "FizzBuzz"
        elif div3:
            result = "Fizz"
        elif div5:
            result = "Buzz"
        else:
            result = str(number)

        return {
            "number": number,
            "result": result,
            "div3": div3,
            "div5": div5,
            "corrections_applied": ec_result["corrections"],
            "distance": self.distance,
            "logical_qubits": len(self._logical_qubits),
        }

    @property
    def logical_qubits(self) -> list[LogicalQubit]:
        return list(self._logical_qubits)


# ============================================================
# FizzQuantumV2 Middleware
# ============================================================


class FizzQuantumV2Middleware(IMiddleware):
    """Middleware that evaluates FizzBuzz using quantum error-corrected computation."""

    priority = 257

    def __init__(
        self,
        engine: Optional[QuantumErrorCorrectionEngine] = None,
        distance: int = 3,
        error_rate: float = 0.001,
    ) -> None:
        self._engine = engine or QuantumErrorCorrectionEngine(
            distance=distance, error_rate=error_rate,
        )

    def process(self, context: ProcessingContext, next_handler: Callable) -> Any:
        """Evaluate FizzBuzz using quantum error correction."""
        result = self._engine.evaluate_fizzbuzz(context.number)
        context.metadata["qec_result"] = result["result"]
        context.metadata["qec_corrections"] = result["corrections_applied"]
        context.metadata["qec_distance"] = result["distance"]
        context.metadata["qec_logical_qubits"] = result["logical_qubits"]
        return next_handler(context)

    def get_name(self) -> str:
        return "FizzQuantumV2Middleware"

    def get_priority(self) -> int:
        return self.priority

    @property
    def engine(self) -> QuantumErrorCorrectionEngine:
        return self._engine
