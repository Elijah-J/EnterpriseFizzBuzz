"""
Enterprise FizzBuzz Platform - FizzPaxosV2 Multi-Decree Paxos Tests

Tests for the multi-decree Paxos consensus protocol with leader election
that enables the distributed FizzBuzz cluster to agree on evaluation
results with reduced latency through a stable leader optimization.

Covers: PaxosRole, PaxosPhase, Proposal, PaxosNode, PaxosCluster,
FizzPaxosV2Dashboard, FizzPaxosV2Middleware, create_fizzpaxosv2_subsystem,
and module-level constants.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions.fizzpaxosv2 import (
    FizzPaxosV2Error,
    PaxosV2LeaderElectionError,
    PaxosV2NoLeaderError,
    PaxosV2NodeNotFoundError,
    PaxosV2ProposalRejectedError,
    PaxosV2QuorumError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.fizzpaxosv2 import (
    FIZZPAXOSV2_VERSION,
    MIDDLEWARE_PRIORITY,
    FizzPaxosV2Dashboard,
    FizzPaxosV2Middleware,
    PaxosCluster,
    PaxosNode,
    PaxosPhase,
    PaxosRole,
    Proposal,
    create_fizzpaxosv2_subsystem,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def cluster():
    """A fresh PaxosCluster instance."""
    return PaxosCluster()


@pytest.fixture
def ready_cluster():
    """A cluster with a proposer, three acceptors, a learner, and an elected leader."""
    c = PaxosCluster()
    c.add_node(PaxosRole.PROPOSER)
    c.add_node(PaxosRole.ACCEPTOR)
    c.add_node(PaxosRole.ACCEPTOR)
    c.add_node(PaxosRole.ACCEPTOR)
    c.add_node(PaxosRole.LEARNER)
    c.elect_leader()
    return c


# ---------------------------------------------------------------------------
# Module-level constant tests
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Tests for the FizzPaxosV2 module-level exports."""

    def test_version_string(self):
        assert FIZZPAXOSV2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 237


# ---------------------------------------------------------------------------
# PaxosRole enum tests
# ---------------------------------------------------------------------------


class TestPaxosRole:
    """Tests for the PaxosRole enumeration."""

    def test_three_roles(self):
        assert len(PaxosRole) == 3
        members = {m.name for m in PaxosRole}
        assert members == {"PROPOSER", "ACCEPTOR", "LEARNER"}

    def test_role_values(self):
        assert PaxosRole.PROPOSER.value == "proposer"
        assert PaxosRole.ACCEPTOR.value == "acceptor"
        assert PaxosRole.LEARNER.value == "learner"


# ---------------------------------------------------------------------------
# PaxosPhase enum tests
# ---------------------------------------------------------------------------


class TestPaxosPhase:
    """Tests for the PaxosPhase enumeration."""

    def test_five_phases(self):
        assert len(PaxosPhase) == 5
        members = {m.name for m in PaxosPhase}
        assert members == {"PREPARE", "PROMISE", "ACCEPT", "ACCEPTED", "LEARN"}


# ---------------------------------------------------------------------------
# Proposal dataclass tests
# ---------------------------------------------------------------------------


class TestProposal:
    """Tests for the Proposal dataclass."""

    def test_default_values(self):
        p = Proposal()
        assert p.proposal_id == ""
        assert p.number == 0
        assert p.value is None

    def test_fields_assigned_correctly(self):
        p = Proposal(proposal_id="prop-001", number=42, value="FizzBuzz")
        assert p.proposal_id == "prop-001"
        assert p.number == 42
        assert p.value == "FizzBuzz"


# ---------------------------------------------------------------------------
# PaxosNode dataclass tests
# ---------------------------------------------------------------------------


class TestPaxosNode:
    """Tests for the PaxosNode dataclass."""

    def test_default_values(self):
        n = PaxosNode()
        assert n.node_id == ""
        assert n.role == PaxosRole.ACCEPTOR
        assert n.current_proposal is None
        assert n.accepted_value is None

    def test_fields_assigned_correctly(self):
        n = PaxosNode(
            node_id="node-001",
            role=PaxosRole.PROPOSER,
            current_proposal=5,
            accepted_value="Fizz",
        )
        assert n.node_id == "node-001"
        assert n.role == PaxosRole.PROPOSER
        assert n.current_proposal == 5
        assert n.accepted_value == "Fizz"


# ---------------------------------------------------------------------------
# PaxosCluster tests
# ---------------------------------------------------------------------------


class TestPaxosClusterAddNode:
    """Tests for adding nodes to the cluster."""

    def test_add_returns_paxos_node(self, cluster):
        node = cluster.add_node(PaxosRole.ACCEPTOR)
        assert isinstance(node, PaxosNode)
        assert node.role == PaxosRole.ACCEPTOR
        assert node.current_proposal is None
        assert node.accepted_value is None

    def test_add_generates_unique_ids(self, cluster):
        n1 = cluster.add_node(PaxosRole.ACCEPTOR)
        n2 = cluster.add_node(PaxosRole.ACCEPTOR)
        assert n1.node_id != n2.node_id

    def test_add_multiple_roles(self, cluster):
        cluster.add_node(PaxosRole.PROPOSER)
        cluster.add_node(PaxosRole.ACCEPTOR)
        cluster.add_node(PaxosRole.LEARNER)
        nodes = cluster.list_nodes()
        roles = {n.role for n in nodes}
        assert roles == {PaxosRole.PROPOSER, PaxosRole.ACCEPTOR, PaxosRole.LEARNER}


class TestPaxosClusterGetNode:
    """Tests for retrieving nodes by ID."""

    def test_get_existing_node(self, cluster):
        node = cluster.add_node(PaxosRole.PROPOSER)
        retrieved = cluster.get_node(node.node_id)
        assert retrieved.node_id == node.node_id

    def test_get_nonexistent_raises(self, cluster):
        with pytest.raises(PaxosV2NodeNotFoundError):
            cluster.get_node("does-not-exist")


class TestPaxosClusterListNodes:
    """Tests for listing all nodes."""

    def test_list_empty_cluster(self, cluster):
        assert cluster.list_nodes() == []

    def test_list_after_adding(self, cluster):
        cluster.add_node(PaxosRole.ACCEPTOR)
        cluster.add_node(PaxosRole.ACCEPTOR)
        nodes = cluster.list_nodes()
        assert len(nodes) == 2


class TestPaxosClusterLeaderElection:
    """Tests for the leader election protocol."""

    def test_elect_leader_returns_proposer(self, cluster):
        cluster.add_node(PaxosRole.PROPOSER)
        cluster.add_node(PaxosRole.ACCEPTOR)
        leader = cluster.elect_leader()
        assert leader.role == PaxosRole.PROPOSER

    def test_elect_leader_no_proposers_raises(self, cluster):
        cluster.add_node(PaxosRole.ACCEPTOR)
        with pytest.raises(PaxosV2LeaderElectionError):
            cluster.elect_leader()

    def test_get_leader_before_election(self, cluster):
        assert cluster.get_leader() is None

    def test_get_leader_after_election(self, cluster):
        cluster.add_node(PaxosRole.PROPOSER)
        cluster.elect_leader()
        leader = cluster.get_leader()
        assert leader is not None
        assert leader.role == PaxosRole.PROPOSER


class TestPaxosClusterPropose:
    """Tests for proposing values for consensus."""

    def test_propose_decides_value(self, ready_cluster):
        result = ready_cluster.propose("FizzBuzz")
        assert result["decided"] is True
        assert result["value"] == "FizzBuzz"

    def test_propose_without_leader_raises(self, cluster):
        cluster.add_node(PaxosRole.ACCEPTOR)
        with pytest.raises(PaxosV2NoLeaderError):
            cluster.propose("value")

    def test_propose_without_acceptors_raises(self, cluster):
        cluster.add_node(PaxosRole.PROPOSER)
        cluster.elect_leader()
        with pytest.raises(PaxosV2QuorumError):
            cluster.propose("value")

    def test_propose_multiple_values(self, ready_cluster):
        r1 = ready_cluster.propose("Fizz")
        r2 = ready_cluster.propose("Buzz")
        r3 = ready_cluster.propose("FizzBuzz")
        assert r1["decided"] is True
        assert r2["decided"] is True
        assert r3["decided"] is True
        assert r1["value"] == "Fizz"
        assert r2["value"] == "Buzz"
        assert r3["value"] == "FizzBuzz"

    def test_learners_receive_decided_value(self, ready_cluster):
        ready_cluster.propose("FizzBuzz")
        learners = [n for n in ready_cluster.list_nodes() if n.role == PaxosRole.LEARNER]
        assert len(learners) > 0
        for learner in learners:
            assert learner.accepted_value == "FizzBuzz"


# ---------------------------------------------------------------------------
# FizzPaxosV2Dashboard tests
# ---------------------------------------------------------------------------


class TestFizzPaxosV2Dashboard:
    """Tests for the FizzPaxosV2 monitoring dashboard."""

    def test_render_returns_nonempty_string(self, ready_cluster):
        dashboard = FizzPaxosV2Dashboard(ready_cluster)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_version(self, ready_cluster):
        dashboard = FizzPaxosV2Dashboard(ready_cluster)
        output = dashboard.render()
        assert FIZZPAXOSV2_VERSION in output

    def test_render_shows_leader(self, ready_cluster):
        leader = ready_cluster.get_leader()
        dashboard = FizzPaxosV2Dashboard(ready_cluster)
        output = dashboard.render()
        assert leader.node_id in output


# ---------------------------------------------------------------------------
# FizzPaxosV2Middleware tests
# ---------------------------------------------------------------------------


class TestFizzPaxosV2Middleware:
    """Tests for the FizzPaxosV2 middleware integration."""

    def test_middleware_name_and_priority(self, ready_cluster):
        mw = FizzPaxosV2Middleware(ready_cluster)
        assert mw.get_name() == "fizzpaxosv2"
        assert mw.get_priority() == 237

    def test_middleware_passes_through(self, ready_cluster):
        mw = FizzPaxosV2Middleware(ready_cluster)
        ctx = ProcessingContext(number=5, session_id="test-paxos-session")

        def next_handler(ctx: ProcessingContext) -> ProcessingContext:
            ctx.results.append(FizzBuzzResult(number=5, output="Buzz"))
            return ctx

        result = mw.process(ctx, next_handler)
        assert len(result.results) == 1
        assert result.results[0].output == "Buzz"


# ---------------------------------------------------------------------------
# Factory function tests
# ---------------------------------------------------------------------------


class TestCreateFizzPaxosV2Subsystem:
    """Tests for the create_fizzpaxosv2_subsystem factory."""

    def test_returns_cluster_dashboard_middleware_tuple(self):
        result = create_fizzpaxosv2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        cl, dash, mw = result
        assert isinstance(cl, PaxosCluster)
        assert isinstance(dash, FizzPaxosV2Dashboard)
        assert isinstance(mw, FizzPaxosV2Middleware)

    def test_factory_creates_five_nodes(self):
        cl, _, _ = create_fizzpaxosv2_subsystem()
        nodes = cl.list_nodes()
        assert len(nodes) == 5

    def test_factory_elects_leader(self):
        cl, _, _ = create_fizzpaxosv2_subsystem()
        leader = cl.get_leader()
        assert leader is not None
        assert leader.role == PaxosRole.PROPOSER


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Tests for the FizzPaxosV2 exception classes."""

    def test_node_not_found_is_subclass(self):
        assert issubclass(PaxosV2NodeNotFoundError, FizzPaxosV2Error)

    def test_quorum_error_is_subclass(self):
        assert issubclass(PaxosV2QuorumError, FizzPaxosV2Error)

    def test_leader_election_error_is_subclass(self):
        assert issubclass(PaxosV2LeaderElectionError, FizzPaxosV2Error)

    def test_proposal_rejected_is_subclass(self):
        assert issubclass(PaxosV2ProposalRejectedError, FizzPaxosV2Error)

    def test_no_leader_error_is_subclass(self):
        assert issubclass(PaxosV2NoLeaderError, FizzPaxosV2Error)

    def test_fizzpaxosv2_error_message(self):
        err = FizzPaxosV2Error("consensus failed")
        assert "consensus failed" in str(err)
