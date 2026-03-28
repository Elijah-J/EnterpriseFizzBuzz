"""Enterprise FizzBuzz Platform - FizzPaxosV2 Multi-Decree Paxos Errors"""
from __future__ import annotations
from ._base import FizzBuzzError


class FizzPaxosV2Error(FizzBuzzError):
    """Base exception for all FizzPaxosV2 multi-decree Paxos errors.

    FizzPaxosV2 implements a multi-decree Paxos protocol with leader
    election for the Enterprise FizzBuzz Platform.  When consensus
    fails at this layer, the cluster cannot agree on FizzBuzz
    evaluation results, which is the distributed systems equivalent
    of a constitutional crisis over modulo arithmetic.
    """

    def __init__(self, message: str, *, error_code: str = "EFP-PV200",
                 context: dict | None = None) -> None:
        super().__init__(message, error_code=error_code, context=context)


class PaxosV2NodeNotFoundError(FizzPaxosV2Error):
    """Raised when a node lookup fails.

    The requested node ID does not correspond to any node in the
    cluster.  The node may have been removed, or it may never have
    existed in the first place.
    """

    def __init__(self, node_id: str) -> None:
        super().__init__(
            f"Paxos node not found: {node_id}",
            error_code="EFP-PV201",
            context={"node_id": node_id},
        )
        self.node_id = node_id


class PaxosV2QuorumError(FizzPaxosV2Error):
    """Raised when the cluster cannot achieve quorum.

    A majority of nodes must participate in each round for the Paxos
    protocol to make progress.  Without quorum, the cluster is
    effectively partitioned and no value can be decided.
    """

    def __init__(self, required: int, available: int) -> None:
        super().__init__(
            f"Quorum not achievable: need {required}, have {available} nodes",
            error_code="EFP-PV202",
            context={"required": required, "available": available},
        )


class PaxosV2LeaderElectionError(FizzPaxosV2Error):
    """Raised when leader election fails.

    The cluster could not elect a leader, either because there are
    no proposer nodes, or because the election protocol encountered
    an internal error.  A leaderless cluster cannot process proposals.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Leader election failed: {reason}",
            error_code="EFP-PV203",
            context={"reason": reason},
        )


class PaxosV2ProposalRejectedError(FizzPaxosV2Error):
    """Raised when a proposal is rejected by the cluster.

    The acceptors did not accept the proposed value, either because
    a higher-numbered proposal was already in progress, or because
    the proposer is not the current leader.
    """

    def __init__(self, proposal_number: int, reason: str) -> None:
        super().__init__(
            f"Proposal #{proposal_number} rejected: {reason}",
            error_code="EFP-PV204",
            context={"proposal_number": proposal_number, "reason": reason},
        )


class PaxosV2NoLeaderError(FizzPaxosV2Error):
    """Raised when an operation requires a leader but none is elected."""

    def __init__(self) -> None:
        super().__init__(
            "No leader elected. Call elect_leader() before proposing values.",
            error_code="EFP-PV205",
        )
