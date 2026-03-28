"""
Enterprise FizzBuzz Platform - Quantum Error Correction Exceptions (EFP-QE00 through EFP-QE09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class QuantumErrorCorrectionError(FizzBuzzError):
    """Base exception for all FizzQuantumV2 error correction subsystem errors.

    Quantum error correction protects the logical qubits used for FizzBuzz
    divisibility computation from decoherence and gate errors. When the
    error correction pipeline itself fails, the logical qubit state
    becomes unrecoverable and the quantum FizzBuzz evaluation must be
    discarded and restarted from scratch.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-QE00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SurfaceCodeError(QuantumErrorCorrectionError):
    """Raised when the surface code lattice is malformed or inconsistent.

    The surface code arranges data qubits and ancilla qubits on a planar
    lattice. If the lattice dimensions are invalid or the stabilizer
    assignments are inconsistent, syndrome extraction will produce
    unreliable results.
    """

    def __init__(self, distance: int, reason: str) -> None:
        super().__init__(
            f"Surface code with distance {distance} is invalid: {reason}",
            error_code="EFP-QE01",
            context={"distance": distance, "reason": reason},
        )


class SyndromeMeasurementError(QuantumErrorCorrectionError):
    """Raised when syndrome extraction produces an inconsistent result.

    Syndrome bits indicate which stabilizers have been violated by errors.
    An inconsistent syndrome (one that does not correspond to any valid
    error pattern) suggests a measurement error in the ancilla qubits
    themselves.
    """

    def __init__(self, syndrome: str, num_rounds: int) -> None:
        super().__init__(
            f"Inconsistent syndrome '{syndrome}' after {num_rounds} measurement rounds.",
            error_code="EFP-QE02",
            context={"syndrome": syndrome, "num_rounds": num_rounds},
        )


class LogicalQubitError(QuantumErrorCorrectionError):
    """Raised when a logical qubit loses coherence beyond the correction threshold.

    Each logical qubit is encoded across multiple physical qubits. If the
    physical error rate exceeds the code's correction capacity, the logical
    error rate increases exponentially and the qubit state is lost.
    """

    def __init__(self, logical_qubit_id: int, error_rate: float) -> None:
        super().__init__(
            f"Logical qubit {logical_qubit_id} has exceeded the correction threshold "
            f"with physical error rate {error_rate:.6f}.",
            error_code="EFP-QE03",
            context={"logical_qubit_id": logical_qubit_id, "error_rate": error_rate},
        )


class FaultTolerantGateError(QuantumErrorCorrectionError):
    """Raised when a fault-tolerant gate operation fails.

    Fault-tolerant gates are constructed from transversal operations or
    magic state distillation to prevent error propagation within the code
    block. A failure here means the gate introduced correlated errors
    across the logical qubit.
    """

    def __init__(self, gate_name: str, reason: str) -> None:
        super().__init__(
            f"Fault-tolerant gate '{gate_name}' failed: {reason}",
            error_code="EFP-QE04",
            context={"gate_name": gate_name, "reason": reason},
        )


class DecoderError(QuantumErrorCorrectionError):
    """Raised when the decoder cannot determine a valid correction.

    The decoder maps syndromes to correction operators. If the decoder
    algorithm (minimum weight perfect matching or union-find) cannot
    converge on a solution, the error cannot be corrected.
    """

    def __init__(self, decoder_type: str, reason: str) -> None:
        super().__init__(
            f"Decoder '{decoder_type}' failed to produce a correction: {reason}",
            error_code="EFP-QE05",
            context={"decoder_type": decoder_type, "reason": reason},
        )


class NoiseModelError(QuantumErrorCorrectionError):
    """Raised when the noise model parameters are invalid or inconsistent.

    The noise model describes the probability distribution of errors on
    physical qubits and gates. Invalid parameters (negative probabilities,
    probabilities exceeding 1.0, or inconsistent channel specifications)
    render the simulation meaningless.
    """

    def __init__(self, parameter: str, value: float, reason: str) -> None:
        super().__init__(
            f"Invalid noise model parameter '{parameter}' = {value}: {reason}",
            error_code="EFP-QE06",
            context={"parameter": parameter, "value": value},
        )
