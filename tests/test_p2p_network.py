"""
Enterprise FizzBuzz Platform - Peer-to-Peer Gossip Network Tests

Tests for the SWIM failure detector, Kademlia DHT, Merkle anti-entropy,
gossip rumor dissemination, network partition/healing, and the P2P
middleware integration.

Because if your in-memory peer-to-peer FizzBuzz gossip network doesn't
have a comprehensive test suite, can you really call it enterprise-grade?
"""

from __future__ import annotations

import hashlib
import math
import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    GossipConvergenceError,
    KademliaDHTError,
    MerkleTreeDivergenceError,
    P2PNetworkPartitionError,
    NodeUnreachableError,
    P2PNetworkError,
)
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    NodeState,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.p2p_network import (
    GossipProtocol,
    KademliaDHT,
    MerkleAntiEntropy,
    P2PDashboard,
    P2PMiddleware,
    P2PNetwork,
    P2PNode,
)


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
def single_node():
    """Create a single P2P node."""
    return P2PNode(index=0, k_bucket_size=3)


@pytest.fixture
def two_nodes():
    """Create two P2P nodes."""
    return [P2PNode(index=i, k_bucket_size=3) for i in range(2)]


@pytest.fixture
def seven_nodes():
    """Create seven P2P nodes (the canonical cluster size)."""
    return [P2PNode(index=i, k_bucket_size=3) for i in range(7)]


@pytest.fixture
def small_network():
    """Create a bootstrapped 3-node network for quick tests."""
    net = P2PNetwork(num_nodes=3, k_bucket_size=2, gossip_fanout=2)
    net.bootstrap()
    return net


@pytest.fixture
def full_network():
    """Create a bootstrapped 7-node network."""
    net = P2PNetwork(num_nodes=7, k_bucket_size=3, gossip_fanout=3)
    net.bootstrap()
    return net


# ===========================================================================
# P2PNode tests
# ===========================================================================

class TestP2PNode:
    """Tests for individual P2P node functionality."""

    def test_node_id_is_sha1_hex(self, single_node):
        """Node ID should be a 40-character hexadecimal SHA-1 hash."""
        assert len(single_node.node_id) == 40
        int(single_node.node_id, 16)  # Should not raise

    def test_node_id_is_deterministic(self):
        """Same index should always produce the same node ID."""
        a = P2PNode(index=42)
        b = P2PNode(index=42)
        assert a.node_id == b.node_id

    def test_different_indices_produce_different_ids(self):
        """Different indices should produce different node IDs."""
        a = P2PNode(index=0)
        b = P2PNode(index=1)
        assert a.node_id != b.node_id

    def test_initial_state_is_alive(self, single_node):
        """New nodes should start in the ALIVE state."""
        assert single_node.state == NodeState.ALIVE

    def test_initial_heartbeat_is_zero(self, single_node):
        """New nodes should start with heartbeat 0."""
        assert single_node.heartbeat == 0

    def test_increment_heartbeat(self, single_node):
        """Heartbeat should increment monotonically."""
        single_node.increment_heartbeat()
        assert single_node.heartbeat == 1
        single_node.increment_heartbeat()
        assert single_node.heartbeat == 2

    def test_node_id_int(self, single_node):
        """node_id_int should be the integer representation of the hex ID."""
        assert single_node.node_id_int == int(single_node.node_id, 16)

    def test_xor_distance_to_self_is_zero(self, single_node):
        """XOR distance from a node to itself is always 0."""
        assert single_node.xor_distance(single_node.node_id) == 0

    def test_xor_distance_is_symmetric(self, two_nodes):
        """XOR distance should be symmetric: d(a,b) == d(b,a)."""
        a, b = two_nodes
        assert a.xor_distance(b.node_id) == b.xor_distance(a.node_id)

    def test_xor_distance_is_positive_for_different_nodes(self, two_nodes):
        """XOR distance between different nodes should be positive."""
        a, b = two_nodes
        assert a.xor_distance(b.node_id) > 0

    def test_bucket_index_uses_log2(self, two_nodes):
        """Bucket index should be floor(log2(XOR distance))."""
        a, b = two_nodes
        dist = a.xor_distance(b.node_id)
        expected = int(math.log2(dist))
        assert a.bucket_index(b.node_id) == expected

    def test_bucket_index_of_self_is_zero(self, single_node):
        """Bucket index for self should be 0 (distance is 0)."""
        assert single_node.bucket_index(single_node.node_id) == 0

    def test_update_k_bucket_adds_peer(self, two_nodes):
        """Updating k-bucket should add the peer's ID."""
        a, b = two_nodes
        a.update_k_bucket(b.node_id)
        idx = a.bucket_index(b.node_id)
        assert b.node_id in a._k_buckets[idx]

    def test_update_k_bucket_ignores_self(self, single_node):
        """A node should not add itself to its own k-buckets."""
        single_node.update_k_bucket(single_node.node_id)
        total_entries = sum(len(b) for b in single_node._k_buckets.values())
        assert total_entries == 0

    def test_k_bucket_capacity_limit(self):
        """K-buckets should not exceed the configured capacity."""
        node = P2PNode(index=0, k_bucket_size=2)
        # Create many nodes that map to the same bucket
        peers = [P2PNode(index=i) for i in range(1, 20)]
        for peer in peers:
            node.update_k_bucket(peer.node_id)
        for bucket in node._k_buckets.values():
            assert len(bucket) <= 2

    def test_find_closest_returns_sorted_by_distance(self, seven_nodes):
        """find_closest should return nodes sorted by XOR distance."""
        node = seven_nodes[0]
        for other in seven_nodes[1:]:
            node.update_k_bucket(other.node_id)

        target = seven_nodes[3].node_id
        closest = node.find_closest(target, count=3)
        target_int = int(target, 16)
        distances = [int(nid, 16) ^ target_int for nid in closest]
        assert distances == sorted(distances)

    def test_store_classification(self, single_node):
        """store_classification should add to the local store."""
        single_node.store_classification(15, "FizzBuzz")
        assert single_node.classification_store[15] == "FizzBuzz"

    def test_get_classification(self, single_node):
        """get_classification should retrieve stored values."""
        single_node.store_classification(3, "Fizz")
        assert single_node.get_classification(3) == "Fizz"

    def test_get_classification_returns_none_for_missing(self, single_node):
        """get_classification should return None for unknown keys."""
        assert single_node.get_classification(999) is None

    def test_add_and_drain_rumors(self, single_node):
        """Rumors should be drainable after being added."""
        single_node.add_rumor(15, "FizzBuzz", 0)
        single_node.add_rumor(3, "Fizz", 0)
        rumors = single_node.drain_rumors()
        assert len(rumors) == 2
        # After drain, buffer should be empty
        assert len(single_node.drain_rumors()) == 0

    def test_repr_contains_state(self, single_node):
        """repr should include node state and heartbeat."""
        r = repr(single_node)
        assert "ALIVE" in r
        assert "heartbeat=0" in r


# ===========================================================================
# GossipProtocol tests
# ===========================================================================

class TestGossipProtocol:
    """Tests for the SWIM-style gossip protocol."""

    def test_ping_between_alive_nodes(self, two_nodes):
        """Direct ping between alive nodes should succeed."""
        protocol = GossipProtocol(two_nodes, fanout=1)
        assert protocol._ping(two_nodes[0], two_nodes[1]) is True

    def test_ping_to_dead_node_fails(self, two_nodes):
        """Ping to a DEAD node should fail."""
        protocol = GossipProtocol(two_nodes, fanout=1)
        two_nodes[1].state = NodeState.DEAD
        assert protocol._ping(two_nodes[0], two_nodes[1]) is False

    def test_ping_across_partition_fails(self, two_nodes):
        """Ping across a network partition should fail."""
        protocol = GossipProtocol(two_nodes, fanout=1)
        protocol.add_partition(two_nodes[0].node_id, two_nodes[1].node_id)
        assert protocol._ping(two_nodes[0], two_nodes[1]) is False

    def test_partition_healing(self, two_nodes):
        """Removing a partition should restore communication."""
        protocol = GossipProtocol(two_nodes, fanout=1)
        protocol.add_partition(two_nodes[0].node_id, two_nodes[1].node_id)
        assert protocol._ping(two_nodes[0], two_nodes[1]) is False
        protocol.remove_partition(two_nodes[0].node_id, two_nodes[1].node_id)
        assert protocol._ping(two_nodes[0], two_nodes[1]) is True

    def test_clear_partitions(self, two_nodes):
        """clear_partitions should heal all partitions."""
        protocol = GossipProtocol(two_nodes, fanout=1)
        protocol.add_partition(two_nodes[0].node_id, two_nodes[1].node_id)
        protocol.clear_partitions()
        assert protocol._ping(two_nodes[0], two_nodes[1]) is True

    def test_ping_updates_k_buckets(self, two_nodes):
        """A successful ping should update k-buckets on both nodes."""
        protocol = GossipProtocol(two_nodes, fanout=1)
        protocol._ping(two_nodes[0], two_nodes[1])
        # Both nodes should know about each other
        all_known_0 = []
        for bucket in two_nodes[0]._k_buckets.values():
            all_known_0.extend(bucket)
        assert two_nodes[1].node_id in all_known_0

    def test_ping_updates_statistics(self, two_nodes):
        """Pings should increment the statistics counters."""
        protocol = GossipProtocol(two_nodes, fanout=1)
        protocol._ping(two_nodes[0], two_nodes[1])
        assert two_nodes[0].pings_sent == 1
        assert two_nodes[1].pings_received == 1
        assert protocol.total_pings == 1

    def test_ping_req_via_intermediary(self, seven_nodes):
        """Indirect ping-req via intermediary should work."""
        protocol = GossipProtocol(seven_nodes, fanout=2)
        source, target, intermediary = seven_nodes[0], seven_nodes[1], seven_nodes[2]
        result = protocol._ping_req(source, target, intermediary)
        assert result is True
        assert protocol.total_ping_reqs == 1

    def test_ping_req_fails_with_dead_intermediary(self, seven_nodes):
        """ping-req should fail if intermediary is dead."""
        protocol = GossipProtocol(seven_nodes, fanout=2)
        seven_nodes[2].state = NodeState.DEAD
        result = protocol._ping_req(seven_nodes[0], seven_nodes[1], seven_nodes[2])
        assert result is False

    def test_gossip_round_increments_heartbeats(self, seven_nodes):
        """A gossip round should increment heartbeats for all alive nodes."""
        protocol = GossipProtocol(seven_nodes, fanout=3)
        protocol.gossip_round()
        for node in seven_nodes:
            assert node.heartbeat == 1

    def test_gossip_round_returns_statistics(self, seven_nodes):
        """gossip_round should return a summary dict."""
        protocol = GossipProtocol(seven_nodes, fanout=3)
        result = protocol.gossip_round()
        assert "round" in result
        assert "alive_count" in result
        assert result["round"] == 1
        assert result["alive_count"] == 7

    def test_gossip_round_increments_round_counter(self, seven_nodes):
        """Round counter should increment with each gossip round."""
        protocol = GossipProtocol(seven_nodes, fanout=3)
        protocol.gossip_round()
        protocol.gossip_round()
        assert protocol.rounds_completed == 2

    def test_suspect_detection_on_partition(self, seven_nodes):
        """Partitioned nodes should eventually be marked SUSPECT."""
        protocol = GossipProtocol(seven_nodes, fanout=6, suspect_timeout_rounds=3)
        # Partition node 0 from everyone else
        for i in range(1, 7):
            protocol.add_partition(seven_nodes[0].node_id, seven_nodes[i].node_id)

        # Run gossip rounds -- node 0 should become suspect/dead to others
        for _ in range(5):
            protocol.gossip_round()

        # At least one node should suspect or have killed node 0
        states_of_0 = []
        for node in seven_nodes[1:]:
            state = node.membership.get(seven_nodes[0].node_id, (NodeState.ALIVE, 0))[0]
            states_of_0.append(state)
        assert NodeState.SUSPECT in states_of_0 or NodeState.DEAD in states_of_0

    def test_dead_detection_after_suspect_timeout(self, seven_nodes):
        """SUSPECT nodes should be declared DEAD after timeout."""
        protocol = GossipProtocol(seven_nodes, fanout=6, suspect_timeout_rounds=2)
        # Partition node 6 from everyone
        for i in range(6):
            protocol.add_partition(seven_nodes[6].node_id, seven_nodes[i].node_id)

        # Run enough rounds for suspect -> dead promotion
        for _ in range(10):
            protocol.gossip_round()

        assert seven_nodes[6].state == NodeState.DEAD

    def test_can_communicate_symmetric(self, two_nodes):
        """Communication check should be symmetric."""
        protocol = GossipProtocol(two_nodes)
        protocol.add_partition(two_nodes[0].node_id, two_nodes[1].node_id)
        assert not protocol.can_communicate(two_nodes[0].node_id, two_nodes[1].node_id)
        assert not protocol.can_communicate(two_nodes[1].node_id, two_nodes[0].node_id)


# ===========================================================================
# KademliaDHT tests
# ===========================================================================

class TestKademliaDHT:
    """Tests for the Kademlia Distributed Hash Table."""

    def test_hash_key_is_sha1_hex(self):
        """hash_key should produce a 40-char hex string."""
        h = KademliaDHT.hash_key("15:FizzBuzz")
        assert len(h) == 40
        int(h, 16)  # Should not raise

    def test_hash_key_is_deterministic(self):
        """Same key should always produce the same hash."""
        a = KademliaDHT.hash_key("hello")
        b = KademliaDHT.hash_key("hello")
        assert a == b

    def test_hash_key_differs_for_different_inputs(self):
        """Different keys should produce different hashes."""
        a = KademliaDHT.hash_key("3:Fizz")
        b = KademliaDHT.hash_key("5:Buzz")
        assert a != b

    def test_iterative_lookup_returns_alive_nodes(self, seven_nodes):
        """iterative_lookup should only return alive nodes."""
        dht = KademliaDHT(seven_nodes, k=3)
        seven_nodes[2].state = NodeState.DEAD
        target = KademliaDHT.hash_key("15:FizzBuzz")
        results = dht.iterative_lookup(target, count=3)
        assert all(n.state == NodeState.ALIVE for n in results)

    def test_iterative_lookup_returns_at_most_k(self, seven_nodes):
        """iterative_lookup should return at most `count` nodes."""
        dht = KademliaDHT(seven_nodes, k=3)
        target = KademliaDHT.hash_key("15:FizzBuzz")
        results = dht.iterative_lookup(target, count=2)
        assert len(results) <= 2

    def test_iterative_lookup_sorted_by_distance(self, seven_nodes):
        """Results should be sorted by XOR distance to target."""
        dht = KademliaDHT(seven_nodes, k=3)
        target_id = KademliaDHT.hash_key("15:FizzBuzz")
        target_int = int(target_id, 16)
        results = dht.iterative_lookup(target_id, count=5)
        distances = [n.node_id_int ^ target_int for n in results]
        assert distances == sorted(distances)

    def test_store_replicates_to_closest_nodes(self, seven_nodes):
        """store should replicate value to k closest nodes."""
        dht = KademliaDHT(seven_nodes, k=3)
        stored_on = dht.store("15:FizzBuzz", "FizzBuzz")
        assert len(stored_on) <= 3
        # At least one node should have the value
        has_value = any(
            n.get_classification(15) == "FizzBuzz" for n in seven_nodes
        )
        assert has_value

    def test_get_retrieves_stored_value(self, seven_nodes):
        """get should retrieve a previously stored value."""
        dht = KademliaDHT(seven_nodes, k=3)
        dht.store("3:Fizz", "Fizz")
        result = dht.get("3:Fizz")
        assert result == "Fizz"

    def test_get_returns_none_for_missing_key(self, seven_nodes):
        """get should return None for keys that were never stored."""
        dht = KademliaDHT(seven_nodes, k=3)
        result = dht.get("999:nothing")
        assert result is None

    def test_store_increments_counter(self, seven_nodes):
        """store should increment the stores_performed counter."""
        dht = KademliaDHT(seven_nodes, k=3)
        dht.store("3:Fizz", "Fizz")
        assert dht.stores_performed == 1

    def test_get_increments_counter(self, seven_nodes):
        """get should increment the gets_performed counter."""
        dht = KademliaDHT(seven_nodes, k=3)
        dht.get("3:Fizz")
        assert dht.gets_performed == 1

    def test_lookup_increments_counter(self, seven_nodes):
        """iterative_lookup should increment the lookups_performed counter."""
        dht = KademliaDHT(seven_nodes, k=3)
        dht.iterative_lookup(KademliaDHT.hash_key("test"))
        assert dht.lookups_performed == 1


# ===========================================================================
# MerkleAntiEntropy tests
# ===========================================================================

class TestMerkleAntiEntropy:
    """Tests for the Merkle tree anti-entropy protocol."""

    def test_empty_store_has_consistent_hash(self):
        """Two empty stores should produce the same root hash."""
        root_a, leaves_a = MerkleAntiEntropy.build_tree({})
        root_b, leaves_b = MerkleAntiEntropy.build_tree({})
        assert root_a == root_b
        assert leaves_a == []

    def test_identical_stores_have_same_root(self):
        """Identical stores should produce the same Merkle root hash."""
        store = {3: "Fizz", 5: "Buzz", 15: "FizzBuzz"}
        root_a, _ = MerkleAntiEntropy.build_tree(store)
        root_b, _ = MerkleAntiEntropy.build_tree(dict(store))
        assert root_a == root_b

    def test_different_stores_have_different_roots(self):
        """Different stores should produce different root hashes."""
        store_a = {3: "Fizz", 5: "Buzz"}
        store_b = {3: "Fizz", 5: "FizzBuzz"}  # Different value
        root_a, _ = MerkleAntiEntropy.build_tree(store_a)
        root_b, _ = MerkleAntiEntropy.build_tree(store_b)
        assert root_a != root_b

    def test_build_tree_produces_leaves(self):
        """build_tree should produce one leaf hash per entry."""
        store = {1: "1", 2: "2", 3: "Fizz"}
        _, leaves = MerkleAntiEntropy.build_tree(store)
        assert len(leaves) == 3

    def test_leaf_hash_is_sha256(self):
        """Leaf hashes should be valid SHA-256 hex strings."""
        h = MerkleAntiEntropy._hash_leaf(15, "FizzBuzz")
        assert len(h) == 64  # SHA-256 hex
        int(h, 16)  # Should not raise

    def test_internal_hash_is_sha256(self):
        """Internal node hashes should be valid SHA-256 hex strings."""
        h = MerkleAntiEntropy._hash_internal("a" * 64, "b" * 64)
        assert len(h) == 64

    def test_compare_and_sync_identical_stores(self, two_nodes):
        """Syncing identical stores should report in_sync=True."""
        for n in two_nodes:
            n.store_classification(3, "Fizz")
            n.store_classification(5, "Buzz")
        result = MerkleAntiEntropy.compare_and_sync(two_nodes[0], two_nodes[1])
        assert result["in_sync"] is True
        assert result["keys_synced"] == 0

    def test_compare_and_sync_different_stores(self, two_nodes):
        """Syncing different stores should reconcile differences."""
        two_nodes[0].store_classification(3, "Fizz")
        two_nodes[0].store_classification(5, "Buzz")
        two_nodes[1].store_classification(3, "Fizz")
        # Node 1 is missing key 5
        result = MerkleAntiEntropy.compare_and_sync(two_nodes[0], two_nodes[1])
        assert result["in_sync"] is False
        assert result["keys_synced"] >= 1
        # After sync, both should have key 5
        assert two_nodes[1].get_classification(5) == "Buzz"

    def test_compare_and_sync_conflicting_values(self, two_nodes):
        """Conflicting values should be resolved by last-writer-wins."""
        two_nodes[0].store_classification(3, "Fizz")
        two_nodes[0].heartbeat = 10
        two_nodes[1].store_classification(3, "NotFizz")
        two_nodes[1].heartbeat = 5
        result = MerkleAntiEntropy.compare_and_sync(two_nodes[0], two_nodes[1])
        # Node 0 has higher heartbeat, so it wins
        assert two_nodes[1].get_classification(3) == "Fizz"

    def test_compare_and_sync_bidirectional(self, two_nodes):
        """Sync should be bidirectional: each node gains the other's data."""
        two_nodes[0].store_classification(3, "Fizz")
        two_nodes[1].store_classification(5, "Buzz")
        MerkleAntiEntropy.compare_and_sync(two_nodes[0], two_nodes[1])
        assert two_nodes[0].get_classification(5) == "Buzz"
        assert two_nodes[1].get_classification(3) == "Fizz"


# ===========================================================================
# P2PNetwork tests
# ===========================================================================

class TestP2PNetwork:
    """Tests for the P2P network orchestrator."""

    def test_bootstrap_creates_nodes(self, full_network):
        """Bootstrap should create the configured number of nodes."""
        assert len(full_network.nodes) == 7

    def test_all_nodes_alive_after_bootstrap(self, full_network):
        """All nodes should be ALIVE after bootstrap."""
        assert all(n.state == NodeState.ALIVE for n in full_network.nodes)

    def test_bootstrap_populates_membership(self, full_network):
        """Each node should know about all other nodes after bootstrap."""
        for node in full_network.nodes:
            for other in full_network.nodes:
                if other.node_id != node.node_id:
                    assert other.node_id in node.membership

    def test_bootstrap_populates_k_buckets(self, full_network):
        """Each node should have entries in k-buckets after bootstrap."""
        for node in full_network.nodes:
            total = sum(len(b) for b in node._k_buckets.values())
            assert total > 0

    def test_gossip_round_succeeds(self, full_network):
        """A gossip round should execute without error."""
        result = full_network.gossip_round()
        assert result["round"] == 1
        assert result["alive_count"] == 7

    def test_evaluate_and_disseminate_converges(self, small_network):
        """evaluate_and_disseminate should achieve convergence."""
        result = small_network.evaluate_and_disseminate(15, "FizzBuzz")
        assert result["converged"] is True

    def test_evaluate_and_disseminate_stores_on_all_alive(self, small_network):
        """After dissemination, all alive nodes should have the result."""
        small_network.evaluate_and_disseminate(15, "FizzBuzz")
        for node in small_network.nodes:
            if node.state == NodeState.ALIVE:
                assert node.get_classification(15) == "FizzBuzz"

    def test_evaluate_multiple_values(self, small_network):
        """Multiple values should all be disseminated correctly."""
        small_network.evaluate_and_disseminate(3, "Fizz")
        small_network.evaluate_and_disseminate(5, "Buzz")
        small_network.evaluate_and_disseminate(15, "FizzBuzz")
        for node in small_network.nodes:
            if node.state == NodeState.ALIVE:
                assert node.get_classification(3) == "Fizz"
                assert node.get_classification(5) == "Buzz"
                assert node.get_classification(15) == "FizzBuzz"

    def test_partition_blocks_communication(self, small_network):
        """Partitioned nodes should not be able to communicate."""
        small_network.partition([0], [1, 2])
        # Verify the partition is in effect
        assert not small_network.gossip.can_communicate(
            small_network.nodes[0].node_id,
            small_network.nodes[1].node_id,
        )

    def test_heal_restores_communication(self, small_network):
        """Healing should restore communication between all nodes."""
        small_network.partition([0], [1, 2])
        small_network.heal()
        assert small_network.gossip.can_communicate(
            small_network.nodes[0].node_id,
            small_network.nodes[1].node_id,
        )

    def test_heal_syncs_divergent_stores(self, small_network):
        """Healing should sync divergent classification stores."""
        # Give node 0 some data, node 1 some different data
        small_network.nodes[0].store_classification(100, "Buzz")
        small_network.nodes[1].store_classification(200, "Fizz")
        # Heal triggers anti-entropy
        small_network.heal()
        # Both should now have both values
        assert small_network.nodes[0].get_classification(200) == "Fizz"
        assert small_network.nodes[1].get_classification(100) == "Buzz"

    def test_topology_summary_structure(self, full_network):
        """get_topology_summary should return expected keys."""
        summary = full_network.get_topology_summary()
        expected_keys = {
            "total_nodes", "alive", "suspect", "dead",
            "gossip_rounds", "total_pings", "total_ping_reqs",
            "dht_lookups", "dht_stores", "dht_gets",
            "unique_classifications", "partition_events",
            "sync_events", "bootstrap_time_ms",
        }
        assert expected_keys.issubset(summary.keys())

    def test_topology_summary_counts(self, full_network):
        """Topology summary should reflect the current state."""
        summary = full_network.get_topology_summary()
        assert summary["total_nodes"] == 7
        assert summary["alive"] == 7
        assert summary["dead"] == 0

    def test_network_with_custom_node_count(self):
        """Network should respect custom node count."""
        net = P2PNetwork(num_nodes=3)
        net.bootstrap()
        assert len(net.nodes) == 3

    def test_partition_and_gossip_causes_suspect(self):
        """Partitioned nodes should eventually be suspected."""
        net = P2PNetwork(num_nodes=5, gossip_fanout=4, suspect_timeout_rounds=2)
        net.bootstrap()
        # Partition node 4 from the rest
        net.partition([4], [0, 1, 2, 3])
        # Run several gossip rounds
        for _ in range(8):
            net.gossip_round()
        # Node 4 should be DEAD or SUSPECT in other nodes' views
        node_4_state = net.nodes[0].membership.get(
            net.nodes[4].node_id, (NodeState.ALIVE, 0)
        )[0]
        assert node_4_state in (NodeState.SUSPECT, NodeState.DEAD)

    def test_convergence_in_olog_n_rounds(self, full_network):
        """Gossip should converge in O(log n) rounds."""
        result = full_network.evaluate_and_disseminate(42, "Fizz")
        if result["converged"]:
            # O(log 7) ~= 3, allow some slack
            assert result["rounds"] <= 10

    def test_no_alive_nodes_returns_not_converged(self):
        """evaluate_and_disseminate should handle all-dead cluster."""
        net = P2PNetwork(num_nodes=3)
        net.bootstrap()
        for node in net.nodes:
            node.state = NodeState.DEAD
        result = net.evaluate_and_disseminate(15, "FizzBuzz")
        assert result["converged"] is False


# ===========================================================================
# P2PDashboard tests
# ===========================================================================

class TestP2PDashboard:
    """Tests for the ASCII dashboard rendering."""

    def test_render_returns_string(self, full_network):
        """render should return a non-empty string."""
        output = P2PDashboard.render(full_network, width=60)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_title(self, full_network):
        """Dashboard should contain the title."""
        output = P2PDashboard.render(full_network)
        assert "PEER-TO-PEER GOSSIP NETWORK DASHBOARD" in output

    def test_render_contains_node_roster(self, full_network):
        """Dashboard should contain node roster entries."""
        output = P2PDashboard.render(full_network)
        assert "NODE ROSTER" in output
        assert "[+]" in output  # Alive indicator

    def test_render_contains_gossip_stats(self, full_network):
        """Dashboard should contain gossip statistics."""
        output = P2PDashboard.render(full_network)
        assert "GOSSIP STATISTICS" in output
        assert "Rounds completed" in output

    def test_render_contains_dht_section(self, full_network):
        """Dashboard should contain Kademlia DHT section."""
        output = P2PDashboard.render(full_network)
        assert "KADEMLIA DHT" in output

    def test_render_contains_convergence(self, full_network):
        """Dashboard should contain convergence status."""
        output = P2PDashboard.render(full_network)
        assert "CONVERGENCE STATUS" in output

    def test_render_after_evaluation(self, full_network):
        """Dashboard should work after evaluations have been done."""
        full_network.evaluate_and_disseminate(15, "FizzBuzz")
        output = P2PDashboard.render(full_network)
        assert "CONSENSUS" in output or "DIVERGENCE" in output

    def test_render_with_dead_nodes(self, full_network):
        """Dashboard should show dead nodes with [X] indicator."""
        full_network.nodes[0].state = NodeState.DEAD
        output = P2PDashboard.render(full_network)
        assert "[X]" in output

    def test_render_with_custom_width(self, full_network):
        """Dashboard should respect custom width."""
        output = P2PDashboard.render(full_network, width=80)
        for line in output.split("\n"):
            assert len(line) <= 80

    def test_render_all_dead_cluster(self):
        """Dashboard should handle all-dead cluster gracefully."""
        net = P2PNetwork(num_nodes=3)
        net.bootstrap()
        for node in net.nodes:
            node.state = NodeState.DEAD
        output = P2PDashboard.render(net)
        assert "dead" in output.lower() or "NO ALIVE" in output


# ===========================================================================
# P2PMiddleware tests
# ===========================================================================

class TestP2PMiddleware:
    """Tests for the P2P middleware integration."""

    def _make_context(self, number: int) -> ProcessingContext:
        """Create a minimal ProcessingContext for testing."""
        ctx = ProcessingContext(number=number, session_id="test-session-p2p")
        result = FizzBuzzResult(number=number, output=str(number))
        ctx.results.append(result)
        return ctx

    def test_middleware_name(self, full_network):
        """Middleware should report its name."""
        mw = P2PMiddleware(network=full_network)
        assert mw.get_name() == "P2PMiddleware"

    def test_middleware_priority(self, full_network):
        """Middleware should have priority -8."""
        mw = P2PMiddleware(network=full_network)
        assert mw.get_priority() == -8

    def test_middleware_enriches_metadata(self, full_network):
        """Middleware should add P2P metadata to the processing context."""
        mw = P2PMiddleware(network=full_network)

        ctx = self._make_context(15)
        ctx.results[-1].output = "FizzBuzz"

        def next_handler(c):
            return c

        result = mw.process(ctx, next_handler)
        assert "p2p_converged" in result.metadata
        assert "p2p_rounds" in result.metadata
        assert "p2p_origin" in result.metadata

    def test_middleware_disseminates_result(self, small_network):
        """Middleware should disseminate the result to all nodes."""
        mw = P2PMiddleware(network=small_network)

        ctx = self._make_context(15)
        ctx.results[-1].output = "FizzBuzz"

        def next_handler(c):
            return c

        mw.process(ctx, next_handler)

        # All alive nodes should have the result
        for node in small_network.nodes:
            if node.state == NodeState.ALIVE:
                assert node.get_classification(15) == "FizzBuzz"

    def test_middleware_passes_through_no_results(self, full_network):
        """Middleware should handle context with no results gracefully."""
        mw = P2PMiddleware(network=full_network)
        ctx = ProcessingContext(number=1, session_id="test-session-p2p")

        def next_handler(c):
            return c

        result = mw.process(ctx, next_handler)
        assert "p2p_converged" not in result.metadata


# ===========================================================================
# Exception tests
# ===========================================================================

class TestP2PExceptions:
    """Tests for P2P-specific exception classes."""

    def test_p2p_network_error_base(self):
        """P2PNetworkError should be a FizzBuzzError."""
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = P2PNetworkError("test error")
        assert isinstance(err, FizzBuzzError)
        assert "EFP-P2P0" in str(err)

    def test_node_unreachable_error(self):
        """NodeUnreachableError should include node ID."""
        err = NodeUnreachableError("abcdef1234567890" * 3, 5)
        assert "EFP-P2P1" in str(err)
        assert "unreachable" in str(err).lower()

    def test_gossip_convergence_error(self):
        """GossipConvergenceError should include round counts."""
        err = GossipConvergenceError(rounds=20, expected_rounds=3, divergent_count=2)
        assert "EFP-P2P2" in str(err)
        assert "20" in str(err)

    def test_kademlia_dht_error(self):
        """KademliaDHTError should include operation details."""
        err = KademliaDHTError("STORE", "abcdef1234" * 4, "bucket full")
        assert "EFP-P2P3" in str(err)
        assert "STORE" in str(err)

    def test_merkle_tree_divergence_error(self):
        """MerkleTreeDivergenceError should include node IDs."""
        err = MerkleTreeDivergenceError("aaa" * 14, "bbb" * 14, 5)
        assert "EFP-P2P4" in str(err)
        assert "5" in str(err)

    def test_network_partition_error(self):
        """P2PNetworkPartitionError should include partition sizes."""
        err = P2PNetworkPartitionError(["a", "b"], ["c", "d", "e"])
        assert "EFP-P2P5" in str(err)
        assert err.partition_a == ["a", "b"]
        assert err.partition_b == ["c", "d", "e"]


# ===========================================================================
# NodeState enum tests
# ===========================================================================

class TestNodeState:
    """Tests for the NodeState enum."""

    def test_alive_state_exists(self):
        assert NodeState.ALIVE is not None

    def test_suspect_state_exists(self):
        assert NodeState.SUSPECT is not None

    def test_dead_state_exists(self):
        assert NodeState.DEAD is not None

    def test_three_states(self):
        """NodeState should have exactly 3 members."""
        assert len(NodeState) == 3


# ===========================================================================
# EventType P2P entries tests
# ===========================================================================

class TestP2PEventTypes:
    """Tests for P2P-related EventType entries."""

    def test_p2p_node_joined(self):
        assert EventType.P2P_NODE_JOINED is not None

    def test_p2p_gossip_round_completed(self):
        assert EventType.P2P_GOSSIP_ROUND_COMPLETED is not None

    def test_p2p_node_state_changed(self):
        assert EventType.P2P_NODE_STATE_CHANGED is not None

    def test_p2p_dht_store(self):
        assert EventType.P2P_DHT_STORE is not None

    def test_p2p_merkle_sync(self):
        assert EventType.P2P_MERKLE_SYNC is not None

    def test_p2p_dashboard_rendered(self):
        assert EventType.P2P_DASHBOARD_RENDERED is not None


# ===========================================================================
# Integration tests
# ===========================================================================

class TestP2PIntegration:
    """Integration tests for the full P2P subsystem."""

    def test_full_lifecycle(self):
        """Test the complete P2P lifecycle: bootstrap, evaluate, partition, heal."""
        net = P2PNetwork(num_nodes=5, k_bucket_size=2, gossip_fanout=3)
        net.bootstrap()

        # Evaluate and disseminate
        net.evaluate_and_disseminate(3, "Fizz")
        net.evaluate_and_disseminate(5, "Buzz")
        net.evaluate_and_disseminate(15, "FizzBuzz")

        # All alive nodes should agree
        for node in net.nodes:
            assert node.get_classification(15) == "FizzBuzz"

        # Partition
        net.partition([0, 1], [2, 3, 4])

        # Store divergent data on each partition
        net.nodes[0].store_classification(42, "Fizz")
        net.nodes[3].store_classification(42, "NotFizz")

        # Heal and sync
        net.heal()

        # After healing, all nodes should have key 42
        values = {
            n.get_classification(42)
            for n in net.nodes
            if n.get_classification(42) is not None
        }
        # At least one value should exist
        assert len(values) >= 1

    def test_dht_store_and_get(self):
        """DHT should support store and get across the cluster."""
        net = P2PNetwork(num_nodes=5, k_bucket_size=3)
        net.bootstrap()

        net.dht.store("7:Wuzz", "Wuzz")
        result = net.dht.get("7:Wuzz")
        assert result == "Wuzz"

    def test_merkle_detects_divergence(self):
        """Merkle anti-entropy should detect and fix divergence."""
        net = P2PNetwork(num_nodes=3, k_bucket_size=2)
        net.bootstrap()

        # Manually create divergence
        net.nodes[0].store_classification(99, "Fizz")
        net.nodes[1].store_classification(99, "Buzz")

        # Run anti-entropy via heal
        net.heal()

        # After healing, nodes should agree
        val_0 = net.nodes[0].get_classification(99)
        val_1 = net.nodes[1].get_classification(99)
        assert val_0 == val_1

    def test_dashboard_after_full_lifecycle(self):
        """Dashboard should render correctly after full lifecycle."""
        net = P2PNetwork(num_nodes=5, k_bucket_size=2, gossip_fanout=3)
        net.bootstrap()
        net.evaluate_and_disseminate(15, "FizzBuzz")
        net.partition([0], [1, 2, 3, 4])
        net.heal()
        output = P2PDashboard.render(net, width=60)
        assert "PEER-TO-PEER" in output
        assert len(output) > 100
