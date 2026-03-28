"""
Enterprise FizzBuzz Platform - FizzQuantumV2 Quantum Error Correction Test Suite

Validates the quantum error correction pipeline from surface code lattice
construction through syndrome measurement, decoding, and fault-tolerant
gate operations. Without these tests, undetected physical qubit errors
could silently corrupt the quantum FizzBuzz evaluation result, turning
a correct "FizzBuzz" into an incorrect "Buzz" with no audit trail.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzquantumv2 import (
    FaultTolerantGate,
    FizzQuantumV2Middleware,
    LogicalQubit,
    MWPMDecoder,
    NoiseChannel,
    NoiseModel,
    PauliOperator,
    PhysicalQubit,
    QuantumErrorCorrectionEngine,
    Stabilizer,
    StabilizerType,
    SurfaceCodeLattice,
)
from enterprise_fizzbuzz.domain.exceptions import (
    QuantumErrorCorrectionError,
    SurfaceCodeError,
    NoiseModelError,
    FaultTolerantGateError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


def _make_context(number: int) -> ProcessingContext:
    return ProcessingContext(number=number, session_id=str(uuid.uuid4()))


# ============================================================
# Surface Code Lattice Tests
# ============================================================


class TestSurfaceCodeLattice:
    def test_distance_3_lattice_construction(self):
        lattice = SurfaceCodeLattice(3)
        assert lattice.num_data_qubits == 9  # 3x3
        assert lattice.distance == 3

    def test_distance_5_lattice(self):
        lattice = SurfaceCodeLattice(5)
        assert lattice.num_data_qubits == 25

    def test_even_distance_raises(self):
        with pytest.raises(SurfaceCodeError):
            SurfaceCodeLattice(4)

    def test_distance_below_3_raises(self):
        with pytest.raises(SurfaceCodeError):
            SurfaceCodeLattice(1)

    def test_correction_capacity(self):
        lattice = SurfaceCodeLattice(5)
        assert lattice.correction_capacity == 2

    def test_syndrome_no_errors(self):
        lattice = SurfaceCodeLattice(3)
        x_syn, z_syn = lattice.get_syndrome()
        assert not any(x_syn)
        assert not any(z_syn)

    def test_inject_error_changes_syndrome(self):
        lattice = SurfaceCodeLattice(3)
        lattice.inject_error(4, PauliOperator.X)  # Center qubit
        x_syn, z_syn = lattice.get_syndrome()
        # At least one syndrome bit should be triggered
        assert any(x_syn) or any(z_syn)

    def test_reset_clears_errors(self):
        lattice = SurfaceCodeLattice(3)
        lattice.inject_error(0, PauliOperator.X)
        lattice.reset_errors()
        for q in lattice.data_qubits:
            assert q.error_state == PauliOperator.I


# ============================================================
# Physical Qubit Tests
# ============================================================


class TestPhysicalQubit:
    def test_apply_and_cancel_error(self):
        q = PhysicalQubit(qubit_id=0, x=0, y=0)
        q.apply_error(PauliOperator.X)
        assert q.error_state == PauliOperator.X
        q.apply_error(PauliOperator.X)
        assert q.error_state == PauliOperator.I

    def test_compose_x_z_gives_y(self):
        q = PhysicalQubit(qubit_id=1, x=0, y=0)
        q.apply_error(PauliOperator.X)
        q.apply_error(PauliOperator.Z)
        assert q.error_state == PauliOperator.Y

    def test_reset(self):
        q = PhysicalQubit(qubit_id=2, x=0, y=0)
        q.apply_error(PauliOperator.Z)
        q.reset()
        assert q.error_state == PauliOperator.I


# ============================================================
# Noise Model Tests
# ============================================================


class TestNoiseModel:
    def test_invalid_error_rate_raises(self):
        with pytest.raises(NoiseModelError):
            NoiseModel(error_rate=-0.1)

    def test_invalid_error_rate_above_one(self):
        with pytest.raises(NoiseModelError):
            NoiseModel(error_rate=1.5)

    def test_zero_error_rate_no_errors(self):
        nm = NoiseModel(error_rate=0.0, seed=42)
        qubits = [PhysicalQubit(i, 0, 0) for i in range(10)]
        errors = nm.apply_noise(qubits)
        assert errors == 0

    def test_full_error_rate_all_errors(self):
        nm = NoiseModel(error_rate=1.0, seed=42)
        qubits = [PhysicalQubit(i, 0, 0) for i in range(5)]
        errors = nm.apply_noise(qubits)
        assert errors == 5

    def test_bit_flip_channel(self):
        nm = NoiseModel(channel=NoiseChannel.BIT_FLIP, error_rate=1.0, seed=0)
        q = PhysicalQubit(0, 0, 0)
        nm.apply_noise([q])
        assert q.error_state == PauliOperator.X


# ============================================================
# Decoder Tests
# ============================================================


class TestMWPMDecoder:
    def test_decode_empty_syndrome(self):
        lattice = SurfaceCodeLattice(3)
        decoder = MWPMDecoder(lattice)
        corrections = decoder.decode([False, False, False, False])
        assert corrections == []

    def test_decode_single_defect_pair(self):
        lattice = SurfaceCodeLattice(3)
        decoder = MWPMDecoder(lattice)
        corrections = decoder.decode([True, True, False, False])
        assert len(corrections) >= 1


# ============================================================
# Logical Qubit Tests
# ============================================================


class TestLogicalQubit:
    def test_initialize_state(self):
        lq = LogicalQubit(0, distance=3, error_rate=0.0)
        lq.initialize(True)
        assert lq.state is True

    def test_error_correction_cycle_no_noise(self):
        lq = LogicalQubit(0, distance=3, error_rate=0.0)
        lq.initialize(False)
        corrected = lq.error_correction_cycle()
        assert corrected is False  # No errors to correct


# ============================================================
# Fault-Tolerant Gate Tests
# ============================================================


class TestFaultTolerantGate:
    def test_transversal_cnot_flips_target(self):
        ctrl = LogicalQubit(0, distance=3, error_rate=0.0)
        tgt = LogicalQubit(1, distance=3, error_rate=0.0)
        ctrl.initialize(True)
        tgt.initialize(False)
        FaultTolerantGate.transversal_cnot(ctrl, tgt)
        assert tgt.state is True

    def test_transversal_cnot_no_flip_when_control_false(self):
        ctrl = LogicalQubit(0, distance=3, error_rate=0.0)
        tgt = LogicalQubit(1, distance=3, error_rate=0.0)
        ctrl.initialize(False)
        tgt.initialize(False)
        FaultTolerantGate.transversal_cnot(ctrl, tgt)
        assert tgt.state is False

    def test_distance_mismatch_raises(self):
        ctrl = LogicalQubit(0, distance=3, error_rate=0.0)
        tgt = LogicalQubit(1, distance=5, error_rate=0.0)
        ctrl.initialize(False)
        tgt.initialize(False)
        with pytest.raises(FaultTolerantGateError):
            FaultTolerantGate.transversal_cnot(ctrl, tgt)


# ============================================================
# Engine Tests
# ============================================================


class TestQuantumErrorCorrectionEngine:
    def test_evaluate_fizzbuzz_15(self):
        engine = QuantumErrorCorrectionEngine(distance=3, error_rate=0.0)
        result = engine.evaluate_fizzbuzz(15)
        assert result["result"] == "FizzBuzz"

    def test_evaluate_fizz_9(self):
        engine = QuantumErrorCorrectionEngine(distance=3, error_rate=0.0)
        result = engine.evaluate_fizzbuzz(9)
        assert result["result"] == "Fizz"

    def test_evaluate_buzz_10(self):
        engine = QuantumErrorCorrectionEngine(distance=3, error_rate=0.0)
        result = engine.evaluate_fizzbuzz(10)
        assert result["result"] == "Buzz"

    def test_evaluate_plain_7(self):
        engine = QuantumErrorCorrectionEngine(distance=3, error_rate=0.0)
        result = engine.evaluate_fizzbuzz(7)
        assert result["result"] == "7"


# ============================================================
# Middleware Tests
# ============================================================


class TestFizzQuantumV2Middleware:
    def test_middleware_annotates_context(self):
        mw = FizzQuantumV2Middleware(distance=3, error_rate=0.0)
        ctx = _make_context(15)
        called = []
        mw.process(ctx, lambda c: called.append(True))
        assert called
        assert ctx.metadata["qec_result"] == "FizzBuzz"
        assert ctx.metadata["qec_distance"] == 3
