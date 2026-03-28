"""
Enterprise FizzBuzz Platform - FizzPaxosV2: Multi-Decree Paxos with Leader Election

A multi-decree Paxos consensus protocol with integrated leader election for
the Enterprise FizzBuzz Platform.  FizzPaxosV2 extends the single-decree
Paxos implementation (FizzPaxos) with support for an unbounded sequence of
consensus instances (decrees) and a stable leader optimization that
eliminates the need for Phase 1 (Prepare/Promise) in the common case.

The original FizzPaxos subsystem implements Basic Paxos: a single-decree
protocol that decides one value per round.  In practice, the platform
needs to decide a continuous stream of FizzBuzz evaluation results across
distributed nodes.  Running a separate single-decree instance for each
evaluation incurs two round-trip delays per value.  Multi-Paxos reduces
this to one round-trip by electing a stable leader that skips Phase 1
for subsequent decrees.

Leader election uses a simple highest-ID-wins protocol among proposer
nodes.  Once a leader is established, it drives proposals through Phase 2
(Accept/Accepted) directly, cutting consensus latency in half.  If the
leader fails, any proposer can initiate a new election.

Architecture references: Lamport, "Paxos Made Simple" (2001),
van Renesse & Altinbuken, "Paxos Made Moderately Complex" (2015)
"""

from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzpaxosv2 import (
    FizzPaxosV2Error,
    PaxosV2LeaderElectionError,
    PaxosV2NoLeaderError,
    PaxosV2NodeNotFoundError,
    PaxosV2ProposalRejectedError,
    PaxosV2QuorumError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzpaxosv2")

EVENT_PAXOSV2 = EventType.register("FIZZPAXOSV2_VALUE_DECIDED")

# ============================================================
# Constants
# ============================================================

FIZZPAXOSV2_VERSION = "1.0.0"
"""Current version of the FizzPaxosV2 subsystem."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIDDLEWARE_PRIORITY = 237
"""Middleware pipeline priority for FizzPaxosV2."""


# ============================================================
# Enums
# ============================================================


class PaxosRole(Enum):
    """Roles that a node may assume in the Paxos cluster.

    A node's role determines which phases of the protocol it
    participates in.  Proposers initiate rounds, acceptors vote
    on proposals, and learners observe decided values.
    """
    PROPOSER = "proposer"
    ACCEPTOR = "acceptor"
    LEARNER = "learner"


class PaxosPhase(Enum):
    """Phases of the multi-decree Paxos protocol.

    The protocol proceeds through five message types: PREPARE and
    PROMISE form Phase 1 (leader election), ACCEPT and ACCEPTED
    form Phase 2 (value commitment), and LEARN disseminates the
    decided value to all learners.
    """
    PREPARE = "prepare"
    PROMISE = "promise"
    ACCEPT = "accept"
    ACCEPTED = "accepted"
    LEARN = "learn"


# ============================================================
# Data classes
# ============================================================


@dataclass
class Proposal:
    """A value proposed for consensus.

    Each proposal carries a unique ID, a monotonically increasing
    proposal number, and the value to be decided.
    """
    proposal_id: str = ""
    number: int = 0
    value: Any = None


@dataclass
class PaxosNode:
    """A single node in the Paxos cluster.

    Tracks the node's role, the highest proposal number it has seen,
    and the last value it accepted.
    """
    node_id: str = ""
    role: PaxosRole = PaxosRole.ACCEPTOR
    current_proposal: Optional[int] = None
    accepted_value: Optional[Any] = None


# ============================================================
# Paxos Cluster
# ============================================================


class PaxosCluster:
    """Multi-decree Paxos cluster with leader election.

    Manages a set of nodes with distinct roles and drives the
    consensus protocol through prepare, accept, and learn phases.
    A stable leader optimization reduces common-case latency.
    """

    def __init__(self) -> None:
        self._nodes: OrderedDict[str, PaxosNode] = OrderedDict()
        self._leader: Optional[PaxosNode] = None
        self._proposal_counter: int = 0
        self._decided_values: List[dict] = []

    def add_node(self, role: PaxosRole) -> PaxosNode:
        """Add a new node to the cluster.

        Args:
            role: The role this node will assume.

        Returns:
            The newly created PaxosNode with a unique ID.
        """
        node_id = f"node-{uuid.uuid4().hex[:8]}"
        node = PaxosNode(
            node_id=node_id,
            role=role,
            current_proposal=None,
            accepted_value=None,
        )
        self._nodes[node_id] = node
        logger.debug("Added %s node '%s' to cluster", role.value, node_id)
        return node

    def get_node(self, node_id: str) -> PaxosNode:
        """Retrieve a node by its unique identifier.

        Raises:
            PaxosV2NodeNotFoundError: If the node ID is not found.
        """
        node = self._nodes.get(node_id)
        if node is None:
            raise PaxosV2NodeNotFoundError(node_id)
        return node

    def list_nodes(self) -> List[PaxosNode]:
        """Return all nodes in the cluster."""
        return list(self._nodes.values())

    def get_leader(self) -> Optional[PaxosNode]:
        """Return the current leader, or None if no leader is elected."""
        return self._leader

    def elect_leader(self) -> PaxosNode:
        """Elect a leader from the proposer nodes.

        Uses a simple highest-ID-wins protocol.  The proposer with the
        lexicographically highest node_id becomes the leader.

        Returns:
            The elected leader node.

        Raises:
            PaxosV2LeaderElectionError: If there are no proposer nodes.
        """
        proposers = [n for n in self._nodes.values() if n.role == PaxosRole.PROPOSER]
        if not proposers:
            raise PaxosV2LeaderElectionError("No proposer nodes in cluster")
        # Highest ID wins
        leader = max(proposers, key=lambda n: n.node_id)
        self._leader = leader
        logger.info("Elected leader: %s", leader.node_id)
        return leader

    def propose(self, value: Any) -> dict:
        """Propose a value for consensus.

        The leader drives the proposal through the acceptor nodes.
        A majority of acceptors must accept for the value to be decided.

        Args:
            value: The value to propose for consensus.

        Returns:
            A dict with keys 'decided' (bool) and 'value' (the decided
            value, or None if consensus was not reached).

        Raises:
            PaxosV2NoLeaderError: If no leader is elected.
            PaxosV2QuorumError: If there are not enough acceptors.
        """
        if self._leader is None:
            raise PaxosV2NoLeaderError()

        acceptors = [n for n in self._nodes.values() if n.role == PaxosRole.ACCEPTOR]
        if not acceptors:
            raise PaxosV2QuorumError(required=1, available=0)

        # Phase 1: Prepare (skipped in multi-Paxos with stable leader)
        self._proposal_counter += 1
        proposal = Proposal(
            proposal_id=f"prop-{uuid.uuid4().hex[:8]}",
            number=self._proposal_counter,
            value=value,
        )

        # Phase 2: Accept
        quorum_size = len(acceptors) // 2 + 1
        accepts = 0
        for acceptor in acceptors:
            if (acceptor.current_proposal is None or
                    proposal.number >= acceptor.current_proposal):
                acceptor.current_proposal = proposal.number
                acceptor.accepted_value = value
                accepts += 1

        decided = accepts >= quorum_size
        result = {"decided": decided, "value": value if decided else None}

        if decided:
            # Phase 3: Learn
            learners = [n for n in self._nodes.values() if n.role == PaxosRole.LEARNER]
            for learner in learners:
                learner.accepted_value = value
            self._decided_values.append({
                "proposal_id": proposal.proposal_id,
                "number": proposal.number,
                "value": value,
            })
            logger.info("Value decided: %s (proposal #%d)", value, proposal.number)
        else:
            logger.warning("Consensus not reached for proposal #%d: %d/%d accepts",
                           proposal.number, accepts, quorum_size)

        return result


# ============================================================
# Dashboard
# ============================================================


class FizzPaxosV2Dashboard:
    """ASCII dashboard for monitoring the Paxos cluster."""

    def __init__(self, cluster: Optional[PaxosCluster] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._cluster = cluster
        self._width = width

    def render(self) -> str:
        """Render the Paxos cluster monitoring dashboard."""
        lines = [
            "=" * self._width,
            "FizzPaxosV2 Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZPAXOSV2_VERSION}",
        ]
        if self._cluster:
            nodes = self._cluster.list_nodes()
            leader = self._cluster.get_leader()
            lines.append(f"  Nodes: {len(nodes)}")
            lines.append(f"  Leader: {leader.node_id if leader else 'None'}")
            role_counts: Dict[str, int] = {}
            for n in nodes:
                role_counts[n.role.value] = role_counts.get(n.role.value, 0) + 1
            if role_counts:
                lines.append("-" * self._width)
                lines.append("  Role Distribution:")
                for role, count in sorted(role_counts.items()):
                    lines.append(f"    {role:<12} {count}")
            lines.append("-" * self._width)
            for n in nodes[:10]:
                leader_mark = " [LEADER]" if leader and n.node_id == leader.node_id else ""
                lines.append(
                    f"  {n.node_id:<20} role={n.role.value}{leader_mark}"
                )
        lines.append("=" * self._width)
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================


class FizzPaxosV2Middleware(IMiddleware):
    """Middleware integration for the FizzPaxosV2 subsystem."""

    def __init__(self, cluster: Optional[PaxosCluster] = None,
                 dashboard: Optional[FizzPaxosV2Dashboard] = None) -> None:
        self._cluster = cluster
        self._dashboard = dashboard

    def get_name(self) -> str:
        return "fizzpaxosv2"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzPaxosV2 not initialized"


# ============================================================
# Factory
# ============================================================


def create_fizzpaxosv2_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[PaxosCluster, FizzPaxosV2Dashboard, FizzPaxosV2Middleware]:
    """Factory function that creates and wires the FizzPaxosV2 subsystem.

    Creates a cluster with three acceptors, one proposer (elected as leader),
    and one learner -- the minimum viable Paxos deployment.

    Returns:
        A tuple of (PaxosCluster, FizzPaxosV2Dashboard, FizzPaxosV2Middleware).
    """
    cluster = PaxosCluster()
    cluster.add_node(PaxosRole.PROPOSER)
    cluster.add_node(PaxosRole.ACCEPTOR)
    cluster.add_node(PaxosRole.ACCEPTOR)
    cluster.add_node(PaxosRole.ACCEPTOR)
    cluster.add_node(PaxosRole.LEARNER)
    cluster.elect_leader()

    dashboard = FizzPaxosV2Dashboard(cluster, dashboard_width)
    middleware = FizzPaxosV2Middleware(cluster, dashboard)
    logger.info("FizzPaxosV2 initialized: %d nodes, leader=%s",
                len(cluster.list_nodes()),
                cluster.get_leader().node_id if cluster.get_leader() else "None")
    return cluster, dashboard, middleware
