"""
Enterprise FizzBuzz Platform - Distributed Paxos Consensus Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class PaxosError(FizzBuzzError):
    """Base exception for all Distributed Paxos Consensus errors.

    When the simulated distributed consensus protocol for FizzBuzz
    evaluation encounters an error, it means democracy itself has
    failed — at least within the confines of a single Python process
    pretending to be a five-node cluster.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-PX00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class QuorumNotReachedError(PaxosError):
    """Raised when a Paxos round fails to achieve quorum.

    A majority of nodes could not agree on the FizzBuzz evaluation
    result. In a real distributed system, this means the cluster
    is partitioned or nodes are unresponsive. Here, it means your
    simulated network is having simulated problems. The distinction
    is purely academic, as is this entire consensus protocol.
    """

    def __init__(self, required: int, received: int, decree_number: int) -> None:
        super().__init__(
            f"Quorum not reached for decree #{decree_number}: "
            f"needed {required} votes, received {received}. "
            f"Democracy has failed for this particular modulo operation.",
            error_code="EFP-PX01",
            context={
                "required": required,
                "received": received,
                "decree_number": decree_number,
            },
        )


class BallotRejectedError(PaxosError):
    """Raised when a proposer's ballot number is rejected by an acceptor.

    The acceptor has already promised to honour a higher ballot number,
    making your ballot obsolete. This is the distributed consensus
    equivalent of arriving at a polling station after it has closed —
    your vote no longer counts, and the election has moved on without
    you. Try a higher ballot number next time.
    """

    def __init__(self, proposed: int, promised: int, node_id: str) -> None:
        super().__init__(
            f"Ballot #{proposed} rejected by node '{node_id}': "
            f"already promised to honour ballot #{promised}. "
            f"Your proposal arrived too late. The consensus train has left the station.",
            error_code="EFP-PX02",
            context={
                "proposed_ballot": proposed,
                "promised_ballot": promised,
                "node_id": node_id,
            },
        )


class QuantumError(FizzBuzzError):
    """Base exception for all Quantum Computing Simulator errors.

    When the fabric of simulated quantum reality collapses, this exception
    hierarchy ensures that the failure is communicated with the same
    gravitas that a real quantum decoherence event deserves. The fact
    that our "qubits" are Python floats in a list does not diminish
    the seriousness of these errors in the slightest.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-QC00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class QuantumDecoherenceError(QuantumError):
    """Raised when a quantum state vector loses normalization.

    In a real quantum computer, decoherence occurs when qubits interact
    with their environment, causing the delicate superposition to collapse
    into classical noise. In our simulator, it means the sum of squared
    amplitudes drifted away from 1.0, probably due to floating-point
    arithmetic — the thermal noise of the software world.
    """

    def __init__(self, norm: float, expected: float = 1.0) -> None:
        super().__init__(
            f"Quantum decoherence detected: state vector norm is {norm:.6f}, "
            f"expected {expected:.6f}. The simulated qubits have lost contact "
            f"with simulated reality. Consider simulated error correction.",
            error_code="EFP-QC01",
            context={"norm": norm, "expected": expected},
        )


class QuantumCircuitError(QuantumError):
    """Raised when a quantum circuit is malformed or cannot be executed.

    The circuit attempted to apply a gate to a qubit that does not exist,
    or the gate matrix dimensions do not match the target qubits. This is
    the quantum computing equivalent of an IndexError, but with more
    existential implications.
    """

    def __init__(self, gate_name: str, target_qubits: Any, num_qubits: int) -> None:
        super().__init__(
            f"Cannot apply gate '{gate_name}' to qubits {target_qubits} "
            f"in a {num_qubits}-qubit register. The quantum circuit has "
            f"attempted to manipulate a qubit that exists only in the "
            f"imagination of an overly ambitious gate schedule.",
            error_code="EFP-QC02",
            context={
                "gate_name": gate_name,
                "target_qubits": str(target_qubits),
                "num_qubits": num_qubits,
            },
        )


class QuantumMeasurementError(QuantumError):
    """Raised when a quantum measurement yields an impossible outcome.

    The Born rule assigns probabilities to measurement outcomes based on
    the squared amplitudes of the state vector. When the measurement
    produces a result with zero probability, either the laws of quantum
    mechanics are wrong, or our random number generator is broken.
    Occam's razor suggests the latter.
    """

    def __init__(self, outcome: int, probability: float) -> None:
        super().__init__(
            f"Measurement yielded outcome |{outcome}> with probability "
            f"{probability:.6e}. This outcome should not have occurred, "
            f"yet here we are, staring into the void of probabilistic "
            f"impossibility. The simulation has become self-aware.",
            error_code="EFP-QC03",
            context={"outcome": outcome, "probability": probability},
        )


class QuantumAdvantageMirage(QuantumError):
    """Raised when the quantum simulator's performance advantage is requested.

    This exception exists to formally acknowledge that our quantum
    simulator provides a negative speedup over classical computation.
    The "advantage" is measured in negative scientific notation, and
    any attempt to claim otherwise constitutes academic fraud of the
    highest order.
    """

    def __init__(self, classical_ns: float, quantum_ns: float) -> None:
        ratio = quantum_ns / max(classical_ns, 1)
        super().__init__(
            f"Quantum Advantage Ratio: {-ratio:.2e}x (negative means slower). "
            f"Classical: {classical_ns:.0f}ns, Quantum: {quantum_ns:.0f}ns. "
            f"The quantum simulator is approximately {ratio:.0f}x slower than "
            f"a single modulo operation. This is expected. This is fine.",
            error_code="EFP-QC04",
            context={
                "classical_ns": classical_ns,
                "quantum_ns": quantum_ns,
                "advantage_ratio": -ratio,
            },
        )


class ByzantineFaultDetectedError(PaxosError):
    """Raised when a Byzantine fault is detected in the consensus cluster.

    One or more nodes are returning results inconsistent with their
    peers. In the Byzantine Generals Problem, this represents a
    traitorous general sending conflicting messages. In our FizzBuzz
    cluster, this represents a node that has decided 15 % 3 != 0,
    which is the modulo arithmetic equivalent of treason.
    """

    def __init__(self, node_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Byzantine fault detected on node '{node_id}': "
            f"expected '{expected}', got '{actual}'. "
            f"This node is lying about its FizzBuzz evaluation. "
            f"Leslie Lamport warned us about this.",
            error_code="EFP-PX03",
            context={
                "node_id": node_id,
                "expected": expected,
                "actual": actual,
            },
        )


class NetworkPartitionError(PaxosError):
    """Raised when a network partition prevents message delivery.

    The simulated network has been partitioned, and messages cannot
    traverse the divide. In a real distributed system, this is caused
    by switch failures, datacenter outages, or angry sysadmins pulling
    cables. Here, it is caused by a boolean flag in a Python dict.
    The emotional impact is identical.
    """

    def __init__(self, source: str, destination: str) -> None:
        super().__init__(
            f"Network partition: message from '{source}' to '{destination}' "
            f"was dropped. The simulated cable has been simulated-ly unplugged.",
            error_code="EFP-PX04",
            context={"source": source, "destination": destination},
        )


class ConsensusTimeoutError(PaxosError):
    """Raised when the Paxos protocol fails to reach consensus in time.

    The cluster spent too long deliberating the correct FizzBuzz
    result and timed out. In distributed systems, this triggers a
    new round with a higher ballot number. In FizzBuzz, it triggers
    existential questions about why we need consensus for modulo
    arithmetic in the first place.
    """

    def __init__(self, decree_number: int, elapsed_ms: float) -> None:
        super().__init__(
            f"Consensus timeout for decree #{decree_number} after "
            f"{elapsed_ms:.2f}ms. The cluster could not agree on a "
            f"FizzBuzz result within the allotted time. Consider "
            f"reducing the number of Byzantine traitors in your cluster.",
            error_code="EFP-PX05",
            context={"decree_number": decree_number, "elapsed_ms": elapsed_ms},
        )

