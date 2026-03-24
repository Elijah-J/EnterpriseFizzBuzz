"""
Enterprise FizzBuzz Platform - Peer-to-Peer Gossip Network exceptions (EFP-P2P0 through EFP-P2P5)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class P2PNetworkError(FizzBuzzError):
    """Base exception for all Peer-to-Peer Gossip Network errors.

    When your distributed FizzBuzz cluster — which exists entirely in a
    single Python process and communicates via method calls — encounters
    a networking error, you know that the concept of "distributed" has
    been stretched to its absolute breaking point. These exceptions cover
    everything from node failures to Merkle tree divergence to Kademlia
    routing mishaps, all without a single TCP socket in sight.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-P2P0"),
            context=kwargs.pop("context", {}),
        )


class NodeUnreachableError(P2PNetworkError):
    """Raised when a gossip ping or ping-req fails to reach a target node.

    The SWIM failure detector has attempted direct ping and indirect
    ping-req through intermediaries, but the target node remains
    stubbornly silent. In a real distributed system, this could mean
    a network partition, a crashed process, or a misconfigured firewall.
    Here, it means we called a method on an object and it didn't
    respond as expected, which is arguably worse.
    """

    def __init__(self, node_id: str, attempts: int) -> None:
        super().__init__(
            f"Node '{node_id[:16]}...' unreachable after {attempts} attempts. "
            f"The SWIM failure detector has exhausted all contact strategies. "
            f"The node may have left the cluster or transcended the mortal plane.",
            error_code="EFP-P2P1",
            context={"node_id": node_id, "attempts": attempts},
        )
        self.node_id = node_id


class GossipConvergenceError(P2PNetworkError):
    """Raised when the gossip protocol fails to converge within the expected rounds.

    In theory, gossip protocols achieve convergence in O(log n) rounds.
    In practice, in-memory gossip with zero network latency should converge
    almost instantly. If this exception fires, something has gone deeply
    wrong with the rumor dissemination algorithm — or someone has configured
    a cluster with zero nodes, which is the distributed systems equivalent
    of dividing by zero.
    """

    def __init__(self, rounds: int, expected_rounds: int, divergent_count: int) -> None:
        super().__init__(
            f"Gossip failed to converge after {rounds} rounds "
            f"(expected ~{expected_rounds}). {divergent_count} node(s) still "
            f"have divergent state. Epidemic information dissemination has "
            f"stalled, which should be impossible in a single-process cluster.",
            error_code="EFP-P2P2",
            context={
                "rounds": rounds,
                "expected_rounds": expected_rounds,
                "divergent_count": divergent_count,
            },
        )


class KademliaDHTError(P2PNetworkError):
    """Raised when a Kademlia DHT operation fails.

    The Distributed Hash Table could not complete the requested operation.
    Perhaps the k-buckets are empty (unlikely in an in-memory simulation),
    or the XOR distance metric has suffered an existential crisis and
    forgotten how to compute exclusive-or. Either way, the key you wanted
    is somewhere in the hash space, and none of the nodes know where.
    """

    def __init__(self, operation: str, key: str, reason: str) -> None:
        super().__init__(
            f"Kademlia DHT {operation} failed for key '{key[:16]}...': {reason}. "
            f"The XOR distance metric has been consulted but provided no comfort.",
            error_code="EFP-P2P3",
            context={"operation": operation, "key": key, "reason": reason},
        )
        self.operation = operation
        self.key = key


class MerkleTreeDivergenceError(P2PNetworkError):
    """Raised when Merkle tree anti-entropy detects irreconcilable divergence.

    The Merkle trees of two nodes disagree on the state of the FizzBuzz
    classification store, and the anti-entropy reconciliation has failed
    to resolve the conflict. In a real distributed database, this would
    trigger a quorum read or a vector clock comparison. Here, it means
    two in-memory dicts have different values for the same key, which is
    a crisis of cosmic proportions.
    """

    def __init__(self, node_a: str, node_b: str, divergent_keys: int) -> None:
        super().__init__(
            f"Merkle divergence between nodes '{node_a[:16]}...' and "
            f"'{node_b[:16]}...': {divergent_keys} key(s) irreconcilable. "
            f"The SHA-256 hash tree has spoken, and the trees disagree.",
            error_code="EFP-P2P4",
            context={
                "node_a": node_a,
                "node_b": node_b,
                "divergent_keys": divergent_keys,
            },
        )


class P2PNetworkPartitionError(P2PNetworkError):
    """Raised when a simulated network partition isolates P2P gossip nodes.

    A network partition has torn your FizzBuzz cluster asunder, creating
    two (or more) isolated sub-clusters that can no longer gossip with
    each other. In CAP theorem terms, you must now choose between
    consistency and availability for your modulo arithmetic results.
    Choose wisely — the integrity of n % 3 hangs in the balance.

    Not to be confused with the Paxos NetworkPartitionError, which
    covers consensus-level partitions. This one covers gossip-level
    partitions, because enterprise FizzBuzz has enough network partition
    errors to warrant separate exception hierarchies for each protocol.
    """

    def __init__(self, partition_a: list[str], partition_b: list[str]) -> None:
        super().__init__(
            f"P2P gossip partition detected: {len(partition_a)} node(s) in "
            f"partition A, {len(partition_b)} node(s) in partition B. "
            f"The CAP theorem has entered the chat. Choose wisely.",
            error_code="EFP-P2P5",
            context={
                "partition_a_size": len(partition_a),
                "partition_b_size": len(partition_b),
            },
        )
        self.partition_a = partition_a
        self.partition_b = partition_b


class DigitalTwinError(FizzBuzzError):
    """Base exception for all Digital Twin simulation errors.

    When your simulation of a simulation of modulo arithmetic encounters
    an error, you have achieved a level of meta-failure that transcends
    conventional debugging. These exceptions cover everything from model
    construction failures to Monte Carlo convergence issues to drift
    detection meltdowns, all in service of predicting the outcome of
    n % 3 before actually computing n % 3.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DT00"),
            context=kwargs.pop("context", {}),
        )


class TwinModelConstructionError(DigitalTwinError):
    """Raised when the digital twin model fails to construct its component DAG.

    The twin attempted to mirror the platform's subsystem topology but
    encountered a configuration state so degenerate that even a simulation
    refused to model it. If the real platform is running fine but the twin
    can't model it, the twin is arguably the smarter one.
    """

    def __init__(self, component: str, reason: str) -> None:
        super().__init__(
            f"Failed to construct twin component '{component}': {reason}. "
            f"The digital twin has declined to model this subsystem.",
            error_code="EFP-DT01",
            context={"component": component, "reason": reason},
        )
        self.component = component


class TwinSimulationDivergenceError(DigitalTwinError):
    """Raised when a twin simulation diverges beyond acceptable thresholds.

    The digital twin predicted one outcome and reality delivered another,
    and the divergence exceeds the configured tolerance. In a real digital
    twin deployment, this would trigger a model recalibration. Here, it
    means our prediction of modulo arithmetic was wrong, which raises
    profound questions about determinism.
    """

    def __init__(self, predicted: float, actual: float, divergence_fdu: float) -> None:
        super().__init__(
            f"Twin simulation diverged: predicted={predicted:.4f}, "
            f"actual={actual:.4f}, divergence={divergence_fdu:.4f} FDU. "
            f"The simulation and reality have agreed to disagree.",
            error_code="EFP-DT02",
            context={
                "predicted": predicted,
                "actual": actual,
                "divergence_fdu": divergence_fdu,
            },
        )
        self.divergence_fdu = divergence_fdu


class MonteCarloConvergenceError(DigitalTwinError):
    """Raised when the Monte Carlo engine fails to converge within N runs.

    After thousands of random simulations of modulo arithmetic, the
    statistical distribution refused to stabilize. Either the variance
    is too high, the sample size too small, or the random number generator
    has developed opinions about divisibility. In any case, the confidence
    intervals remain stubbornly wide.
    """

    def __init__(self, n_simulations: int, variance: float) -> None:
        super().__init__(
            f"Monte Carlo failed to converge after {n_simulations} simulations "
            f"(variance={variance:.6f}). The random number generator appears to "
            f"be philosophically opposed to convergence.",
            error_code="EFP-DT03",
            context={"n_simulations": n_simulations, "variance": variance},
        )
        self.n_simulations = n_simulations


class WhatIfScenarioParseError(DigitalTwinError):
    """Raised when a what-if scenario string fails to parse.

    The what-if scenario parser expected 'param=value' pairs but received
    something that defies syntactic comprehension. The scenario description
    is neither valid configuration nor valid English, leaving the simulator
    in a state of existential ambiguity.
    """

    def __init__(self, scenario: str, reason: str) -> None:
        super().__init__(
            f"Failed to parse what-if scenario '{scenario}': {reason}. "
            f"Expected format: 'param=value;param2=value2'. "
            f"The simulator cannot hypothesize about unparseable futures.",
            error_code="EFP-DT04",
            context={"scenario": scenario, "reason": reason},
        )
        self.scenario = scenario


class TwinDriftThresholdExceededError(DigitalTwinError):
    """Raised when cumulative twin drift exceeds the configured FDU threshold.

    The digital twin has drifted so far from reality that it is no longer
    a useful model of the platform. At this point, the twin is essentially
    a work of fiction — a speculative narrative about what FizzBuzz might
    have been, had the universe taken a different path through the modulo
    landscape.
    """

    def __init__(self, cumulative_fdu: float, threshold_fdu: float) -> None:
        super().__init__(
            f"Cumulative twin drift ({cumulative_fdu:.4f} FDU) exceeds threshold "
            f"({threshold_fdu:.4f} FDU). The digital twin is now officially "
            f"fan fiction. Consider rebuilding the model.",
            error_code="EFP-DT05",
            context={
                "cumulative_fdu": cumulative_fdu,
                "threshold_fdu": threshold_fdu,
            },
        )
        self.cumulative_fdu = cumulative_fdu

