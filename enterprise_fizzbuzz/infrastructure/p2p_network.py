"""
Enterprise FizzBuzz Platform - Peer-to-Peer Gossip Network Module

Implements a fully simulated in-memory peer-to-peer network with:
- SWIM-style failure detection (ping, ping-req, suspect timers)
- Kademlia DHT with XOR distance metric and k-buckets
- Infection-style rumor dissemination (gossip protocol)
- Merkle tree anti-entropy for classification store synchronization
- Network partition simulation and healing
- ASCII dashboard for topology visualization

All communication is simulated via direct method calls between Python
objects. No sockets, no TCP, no UDP, no carrier pigeons. The network
latency is exactly 0.000ms, which makes this the most performant
distributed system in human history. Unfortunately, it is also the
least distributed distributed system in human history, because every
"node" is a dict in the same process.

The nodes gossip about FizzBuzz classification results, because the
only thing more reliable than computing n % 3 locally is computing it
on 7 nodes and then spending O(log n) gossip rounds ensuring they all
agree. Byzantine generals would be proud. Or confused.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    GossipConvergenceError,
    KademliaDHTError,
    MerkleTreeDivergenceError,
    NodeUnreachableError,
    P2PNetworkPartitionError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    NodeState,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# P2PNode: individual node in the gossip network
# ---------------------------------------------------------------------------

class P2PNode:
    """A single node in the Enterprise FizzBuzz P2P Network.

    Each node is identified by a 160-bit SHA-1 hash derived from its
    ordinal index, because in enterprise distributed systems, even the
    act of assigning an identifier must involve a cryptographic hash
    function. The node maintains:

    - A heartbeat counter (monotonically increasing, like Bob's stress)
    - A local classification store (number -> FizzBuzz result)
    - A membership list (node_id -> NodeState)
    - Kademlia k-buckets for XOR-distance routing

    The node is blissfully unaware that it exists in the same Python
    process as every other node. As far as it's concerned, it is a
    sovereign participant in a vast distributed network of modulo
    arithmetic evaluators.
    """

    def __init__(
        self,
        index: int,
        k_bucket_size: int = 3,
    ) -> None:
        # 160-bit SHA-1 node ID, stored as 40-char hex string
        self.node_id: str = hashlib.sha1(
            f"enterprise-fizzbuzz-node-{index}".encode()
        ).hexdigest()
        self.index = index
        self.heartbeat: int = 0
        self.state: NodeState = NodeState.ALIVE

        # Classification store: number -> output string
        self.classification_store: dict[int, str] = {}

        # Membership list: node_id -> (state, heartbeat)
        self.membership: dict[str, tuple[NodeState, int]] = {}

        # Kademlia k-buckets: bucket_index -> list of node_ids
        self._k = k_bucket_size
        self._k_buckets: dict[int, list[str]] = {}

        # Suspect timers: node_id -> rounds_remaining
        self._suspect_timers: dict[str, int] = {}

        # Gossip rumor buffer: list of (key, value, generation)
        self._rumor_buffer: list[tuple[int, str, int]] = []

        # Statistics
        self.pings_sent: int = 0
        self.pings_received: int = 0
        self.rumors_propagated: int = 0

    @property
    def node_id_int(self) -> int:
        """Return the node ID as an integer for XOR distance computation."""
        return int(self.node_id, 16)

    def xor_distance(self, other_id: str) -> int:
        """Compute the Kademlia XOR distance to another node."""
        return self.node_id_int ^ int(other_id, 16)

    def bucket_index(self, other_id: str) -> int:
        """Compute the k-bucket index for a given node ID.

        The bucket index is floor(log2(distance)), which partitions the
        160-bit ID space into buckets of exponentially increasing size.
        Bucket 0 contains the node's closest neighbor; bucket 159
        contains the most distant node in the hash space.
        """
        dist = self.xor_distance(other_id)
        if dist == 0:
            return 0
        return int(math.log2(dist))

    def update_k_bucket(self, other_id: str) -> None:
        """Insert or refresh a node ID in the appropriate k-bucket."""
        if other_id == self.node_id:
            return
        idx = self.bucket_index(other_id)
        bucket = self._k_buckets.setdefault(idx, [])

        if other_id in bucket:
            # Move to end (most recently seen)
            bucket.remove(other_id)
            bucket.append(other_id)
        elif len(bucket) < self._k:
            bucket.append(other_id)
        else:
            # Bucket full -- in real Kademlia we'd ping the head.
            # Here we just evict the oldest entry because enterprise
            # efficiency demands immediate capacity management.
            bucket.pop(0)
            bucket.append(other_id)

    def find_closest(self, target_id: str, count: int = 3) -> list[str]:
        """Find the `count` closest node IDs to target using k-buckets."""
        all_known: list[str] = []
        for bucket in self._k_buckets.values():
            all_known.extend(bucket)

        # Sort by XOR distance to target
        target_int = int(target_id, 16)
        all_known.sort(key=lambda nid: int(nid, 16) ^ target_int)
        return all_known[:count]

    def increment_heartbeat(self) -> None:
        """Tick the heartbeat counter. One more round survived."""
        self.heartbeat += 1

    def store_classification(self, number: int, output: str) -> None:
        """Store a FizzBuzz classification result in the local store."""
        self.classification_store[number] = output

    def get_classification(self, number: int) -> Optional[str]:
        """Retrieve a classification from the local store."""
        return self.classification_store.get(number)

    def add_rumor(self, number: int, output: str, generation: int = 0) -> None:
        """Add a rumor to the dissemination buffer."""
        self._rumor_buffer.append((number, output, generation))

    def drain_rumors(self) -> list[tuple[int, str, int]]:
        """Drain and return all pending rumors."""
        rumors = list(self._rumor_buffer)
        self._rumor_buffer.clear()
        return rumors

    def __repr__(self) -> str:
        return (
            f"P2PNode(id={self.node_id[:12]}..., "
            f"state={self.state.name}, "
            f"heartbeat={self.heartbeat}, "
            f"store_size={len(self.classification_store)})"
        )


# ---------------------------------------------------------------------------
# GossipProtocol: SWIM-style failure detection + rumor dissemination
# ---------------------------------------------------------------------------

class GossipProtocol:
    """SWIM-style gossip protocol for the Enterprise FizzBuzz P2P Network.

    Implements the Scalable Weakly-consistent Infection-style Process
    Group Membership Protocol (SWIM), adapted for the critical task of
    ensuring that all 7 nodes in our in-memory FizzBuzz cluster agree
    on whether 15 is FizzBuzz.

    The protocol operates in rounds:
    1. Each node selects a random peer and sends a PING.
    2. If the peer responds with ACK, it is ALIVE. Hooray.
    3. If no ACK, the node selects k intermediaries for indirect PING-REQ.
    4. If still no response, the target enters SUSPECT state.
    5. After a configurable timeout, SUSPECT nodes are declared DEAD.
    6. Concurrently, rumors (FizzBuzz classifications) are piggybacked
       on gossip messages via infection-style dissemination.

    In a real network, steps 1-5 would involve UDP packets and timeouts.
    Here, they involve method calls and boolean flags. The academic
    rigor is preserved; the networking stack is not.
    """

    def __init__(
        self,
        nodes: list[P2PNode],
        fanout: int = 3,
        suspect_timeout_rounds: int = 3,
    ) -> None:
        self._nodes = nodes
        self._node_map: dict[str, P2PNode] = {n.node_id: n for n in nodes}
        self._fanout = fanout
        self._suspect_timeout = suspect_timeout_rounds

        # Track which node pairs are partitioned
        self._partitioned_pairs: set[tuple[str, str]] = set()

        # Stats
        self.rounds_completed: int = 0
        self.total_pings: int = 0
        self.total_ping_reqs: int = 0
        self.total_suspect_events: int = 0
        self.total_dead_events: int = 0

    def can_communicate(self, a_id: str, b_id: str) -> bool:
        """Check if two nodes can communicate (not partitioned)."""
        pair = (min(a_id, b_id), max(a_id, b_id))
        return pair not in self._partitioned_pairs

    def add_partition(self, a_id: str, b_id: str) -> None:
        """Simulate a network partition between two nodes."""
        pair = (min(a_id, b_id), max(a_id, b_id))
        self._partitioned_pairs.add(pair)

    def remove_partition(self, a_id: str, b_id: str) -> None:
        """Heal a network partition between two nodes."""
        pair = (min(a_id, b_id), max(a_id, b_id))
        self._partitioned_pairs.discard(pair)

    def clear_partitions(self) -> None:
        """Heal all network partitions."""
        self._partitioned_pairs.clear()

    def _ping(self, source: P2PNode, target: P2PNode) -> bool:
        """Direct ping from source to target. Returns True if ACK received."""
        if target.state == NodeState.DEAD:
            return False
        if not self.can_communicate(source.node_id, target.node_id):
            return False
        source.pings_sent += 1
        target.pings_received += 1
        self.total_pings += 1
        # Update k-buckets on both sides
        source.update_k_bucket(target.node_id)
        target.update_k_bucket(source.node_id)
        return True

    def _ping_req(
        self, source: P2PNode, target: P2PNode, intermediary: P2PNode
    ) -> bool:
        """Indirect ping via an intermediary node.

        Source asks intermediary to ping target on its behalf. This is
        the SWIM protocol's defense against false positives caused by
        asymmetric network failures (which, in our case, are simulated
        asymmetric method call failures -- equally devastating).
        """
        if intermediary.state == NodeState.DEAD:
            return False
        if not self.can_communicate(source.node_id, intermediary.node_id):
            return False
        self.total_ping_reqs += 1
        return self._ping(intermediary, target)

    def gossip_round(self) -> dict[str, Any]:
        """Execute one complete gossip round across all alive nodes.

        Each alive node:
        1. Increments its heartbeat
        2. Selects random peers and pings them
        3. Runs the SWIM failure detector (ping -> ping-req -> suspect -> dead)
        4. Disseminates rumors (piggybacked classification data)

        Returns a summary dict with round statistics.
        """
        alive_nodes = [n for n in self._nodes if n.state != NodeState.DEAD]

        state_changes: list[tuple[str, NodeState, NodeState]] = []
        rumors_spread = 0

        for node in alive_nodes:
            node.increment_heartbeat()

            # Update own membership entry
            node.membership[node.node_id] = (NodeState.ALIVE, node.heartbeat)

            # Select random peers for gossip
            other_alive = [
                n for n in alive_nodes if n.node_id != node.node_id
            ]
            if not other_alive:
                continue

            targets = random.sample(
                other_alive, min(self._fanout, len(other_alive))
            )

            for target in targets:
                ack = self._ping(node, target)

                if ack:
                    # Target is alive -- update membership
                    old_state = node.membership.get(
                        target.node_id, (NodeState.ALIVE, 0)
                    )[0]
                    node.membership[target.node_id] = (
                        NodeState.ALIVE,
                        target.heartbeat,
                    )
                    # Clear suspect timer if any
                    node._suspect_timers.pop(target.node_id, None)

                    if old_state == NodeState.SUSPECT:
                        state_changes.append(
                            (target.node_id, NodeState.SUSPECT, NodeState.ALIVE)
                        )

                    # Disseminate rumors (piggyback on ACK)
                    rumors = node.drain_rumors()
                    for num, output, gen in rumors:
                        if gen < 3:  # Limit rumor propagation
                            target.store_classification(num, output)
                            target.add_rumor(num, output, gen + 1)
                            rumors_spread += 1
                            node.rumors_propagated += 1

                    # Anti-entropy piggyback: share classification store
                    # entries that the target is missing. In real gossip
                    # protocols, state is piggybacked on every message.
                    for num, output in node.classification_store.items():
                        if target.get_classification(num) is None:
                            target.store_classification(num, output)
                            target.add_rumor(num, output, 1)
                            rumors_spread += 1
                else:
                    # No ACK -- try indirect ping-req
                    intermediaries = [
                        n
                        for n in other_alive
                        if n.node_id != target.node_id
                        and n.node_id != node.node_id
                    ]
                    indirect_success = False
                    for intermediary in intermediaries[:2]:
                        if self._ping_req(node, target, intermediary):
                            indirect_success = True
                            break

                    if indirect_success:
                        node.membership[target.node_id] = (
                            NodeState.ALIVE,
                            target.heartbeat,
                        )
                    else:
                        # Mark as SUSPECT
                        current = node.membership.get(
                            target.node_id, (NodeState.ALIVE, 0)
                        )
                        if current[0] == NodeState.ALIVE:
                            node.membership[target.node_id] = (
                                NodeState.SUSPECT,
                                current[1],
                            )
                            node._suspect_timers[target.node_id] = (
                                self._suspect_timeout
                            )
                            self.total_suspect_events += 1
                            state_changes.append(
                                (target.node_id, NodeState.ALIVE, NodeState.SUSPECT)
                            )

            # Decrement suspect timers and promote to DEAD
            expired = []
            for nid, remaining in node._suspect_timers.items():
                if remaining <= 1:
                    expired.append(nid)
                else:
                    node._suspect_timers[nid] = remaining - 1

            for nid in expired:
                del node._suspect_timers[nid]
                node.membership[nid] = (NodeState.DEAD, 0)
                # Actually mark the node as DEAD
                if nid in self._node_map:
                    old_state = self._node_map[nid].state
                    self._node_map[nid].state = NodeState.DEAD
                    self.total_dead_events += 1
                    state_changes.append(
                        (nid, old_state, NodeState.DEAD)
                    )

        self.rounds_completed += 1

        return {
            "round": self.rounds_completed,
            "alive_count": sum(
                1 for n in self._nodes if n.state == NodeState.ALIVE
            ),
            "suspect_count": sum(
                1 for n in self._nodes if n.state == NodeState.SUSPECT
            ),
            "dead_count": sum(
                1 for n in self._nodes if n.state == NodeState.DEAD
            ),
            "state_changes": state_changes,
            "rumors_spread": rumors_spread,
        }


# ---------------------------------------------------------------------------
# KademliaDHT: XOR distance-based distributed hash table
# ---------------------------------------------------------------------------

class KademliaDHT:
    """Kademlia Distributed Hash Table for the Enterprise FizzBuzz P2P Network.

    Implements the four fundamental Kademlia operations:
    - XOR distance metric for ID-space routing
    - k-bucket management for peer discovery
    - Iterative lookup for finding the closest nodes to a key
    - Store/Get for distributed key-value storage

    The keys are SHA-1 hashes of FizzBuzz number-output pairs, because
    storing "15 -> FizzBuzz" in a flat dict would be far too pedestrian.
    Instead, we hash the key into a 160-bit ID space, route to the k
    closest nodes via iterative XOR-distance narrowing, and replicate
    the value across multiple peers for redundancy that nobody asked for.

    All routing happens via method calls. The routing table is a Python
    dict. The latency is zero. The overhead is significant.
    """

    def __init__(self, nodes: list[P2PNode], k: int = 3) -> None:
        self._nodes = nodes
        self._node_map: dict[str, P2PNode] = {n.node_id: n for n in nodes}
        self._k = k
        self.lookups_performed: int = 0
        self.stores_performed: int = 0
        self.gets_performed: int = 0

    @staticmethod
    def hash_key(key: str) -> str:
        """Hash a key into the 160-bit Kademlia ID space."""
        return hashlib.sha1(key.encode()).hexdigest()

    def iterative_lookup(self, target_id: str, count: int = 3) -> list[P2PNode]:
        """Find the `count` closest alive nodes to a target ID.

        This is the iterative Kademlia FIND_NODE operation. In a real
        implementation, this involves multiple rounds of network queries,
        progressively narrowing in on the target. Here, we simply sort
        all nodes by XOR distance because we have omniscient access to
        the entire cluster. The result is the same; the networking is
        conspicuously absent.
        """
        self.lookups_performed += 1
        target_int = int(target_id, 16)
        alive = [n for n in self._nodes if n.state == NodeState.ALIVE]
        alive.sort(key=lambda n: n.node_id_int ^ target_int)
        return alive[:count]

    def store(self, key: str, value: str) -> list[str]:
        """Store a key-value pair on the k closest nodes.

        Returns the list of node IDs that accepted the store.
        """
        self.stores_performed += 1
        target_id = self.hash_key(key)
        closest = self.iterative_lookup(target_id, self._k)

        stored_on: list[str] = []
        for node in closest:
            # Store in the node's classification store using the
            # original integer key (parsed from the composite key)
            try:
                number = int(key.split(":")[0])
                node.store_classification(number, value)
                stored_on.append(node.node_id)
            except (ValueError, IndexError):
                # Non-numeric keys are stored as metadata
                pass

        return stored_on

    def get(self, key: str) -> Optional[str]:
        """Retrieve a value from the DHT by looking up the closest nodes.

        Returns the first value found, or None if no node has it.
        """
        self.gets_performed += 1
        target_id = self.hash_key(key)
        closest = self.iterative_lookup(target_id, self._k)

        try:
            number = int(key.split(":")[0])
        except (ValueError, IndexError):
            return None

        for node in closest:
            result = node.get_classification(number)
            if result is not None:
                return result

        return None


# ---------------------------------------------------------------------------
# MerkleAntiEntropy: Merkle tree for classification store synchronization
# ---------------------------------------------------------------------------

class MerkleAntiEntropy:
    """Merkle tree anti-entropy protocol for classification store sync.

    Builds a binary Merkle tree over the sorted (key, value) pairs in a
    node's classification store. Two nodes can compare root hashes in
    O(1), and if they differ, recursively descend to identify divergent
    leaves in O(log n) comparisons.

    In a real distributed database, this is how Cassandra, Dynamo, and
    Riak detect and repair data inconsistencies across replicas. Here,
    it detects that two in-memory dicts in the same process have somehow
    managed to disagree about the result of n % 3. The fact that this
    can happen (via simulated network partitions) is a testament to the
    thoroughness of our simulation and the futility of our existence.
    """

    @staticmethod
    def _hash_leaf(key: int, value: str) -> str:
        """Hash a single (key, value) leaf using SHA-256."""
        return hashlib.sha256(f"{key}:{value}".encode()).hexdigest()

    @staticmethod
    def _hash_internal(left: str, right: str) -> str:
        """Hash two child hashes to form an internal node."""
        return hashlib.sha256(f"{left}{right}".encode()).hexdigest()

    @classmethod
    def build_tree(cls, store: dict[int, str]) -> tuple[str, list[str]]:
        """Build a Merkle tree over the classification store.

        Returns (root_hash, leaf_hashes). If the store is empty,
        returns a sentinel hash that represents the existential void.
        """
        if not store:
            empty_hash = hashlib.sha256(b"empty-fizzbuzz-store").hexdigest()
            return empty_hash, []

        # Sort by key for deterministic ordering
        sorted_items = sorted(store.items())
        leaves = [cls._hash_leaf(k, v) for k, v in sorted_items]

        # Build tree bottom-up
        current_level = list(leaves)
        while len(current_level) > 1:
            next_level: list[str] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                next_level.append(cls._hash_internal(left, right))
            current_level = next_level

        root_hash = current_level[0]
        return root_hash, leaves

    @classmethod
    def compare_and_sync(
        cls,
        node_a: P2PNode,
        node_b: P2PNode,
    ) -> dict[str, Any]:
        """Compare Merkle trees of two nodes and sync divergent entries.

        Returns a summary of the synchronization operation, including
        which keys were synced and in which direction. The sync strategy
        is "last writer wins" based on heartbeat count, because in
        enterprise distributed systems, the node that has been alive
        longest is probably right. Probably.
        """
        root_a, _ = cls.build_tree(node_a.classification_store)
        root_b, _ = cls.build_tree(node_b.classification_store)

        result: dict[str, Any] = {
            "root_a": root_a[:16],
            "root_b": root_b[:16],
            "in_sync": root_a == root_b,
            "keys_synced": 0,
            "direction": "none",
        }

        if root_a == root_b:
            return result

        # Trees diverge -- find and sync divergent keys
        all_keys = set(node_a.classification_store.keys()) | set(
            node_b.classification_store.keys()
        )
        synced = 0

        for key in all_keys:
            val_a = node_a.classification_store.get(key)
            val_b = node_b.classification_store.get(key)

            if val_a == val_b:
                continue

            # Last-writer-wins based on heartbeat
            if val_a is not None and val_b is not None:
                if node_a.heartbeat >= node_b.heartbeat:
                    node_b.classification_store[key] = val_a
                else:
                    node_a.classification_store[key] = val_b
                synced += 1
            elif val_a is not None:
                node_b.classification_store[key] = val_a
                synced += 1
            else:
                node_a.classification_store[key] = val_b  # type: ignore[assignment]
                synced += 1

        result["keys_synced"] = synced
        result["direction"] = "bidirectional"
        return result


# ---------------------------------------------------------------------------
# P2PNetwork: orchestrator
# ---------------------------------------------------------------------------

class P2PNetwork:
    """Orchestrator for the Enterprise FizzBuzz Peer-to-Peer Gossip Network.

    Manages the lifecycle of all P2P subsystems:
    - Bootstrap: create nodes, populate k-buckets, establish initial topology
    - Gossip rounds: run SWIM failure detection and rumor dissemination
    - Evaluate and disseminate: compute FizzBuzz on one node, spread to all
    - Network partition and healing: simulate split-brain and recovery
    - Anti-entropy: Merkle tree sync to repair divergent stores

    This class is the composition root of the P2P subsystem, wiring
    together P2PNodes, GossipProtocol, KademliaDHT, and MerkleAntiEntropy
    into a cohesive distributed system that operates entirely within a
    single thread of a single process on a single machine. Peak distribution.
    """

    def __init__(
        self,
        num_nodes: int = 7,
        k_bucket_size: int = 3,
        gossip_fanout: int = 3,
        suspect_timeout_rounds: int = 3,
        max_gossip_rounds: int = 20,
        event_bus: Any = None,
    ) -> None:
        self._num_nodes = num_nodes
        self._k = k_bucket_size
        self._max_rounds = max_gossip_rounds
        self._event_bus = event_bus

        # Create nodes
        self.nodes: list[P2PNode] = [
            P2PNode(index=i, k_bucket_size=k_bucket_size)
            for i in range(num_nodes)
        ]

        # Initialize subsystems
        self.gossip = GossipProtocol(
            nodes=self.nodes,
            fanout=gossip_fanout,
            suspect_timeout_rounds=suspect_timeout_rounds,
        )
        self.dht = KademliaDHT(nodes=self.nodes, k=k_bucket_size)
        self.merkle = MerkleAntiEntropy()

        # Statistics
        self._bootstrap_time_ns: int = 0
        self._gossip_history: list[dict[str, Any]] = []
        self._partition_events: list[dict[str, Any]] = []
        self._sync_events: list[dict[str, Any]] = []

    def bootstrap(self) -> None:
        """Bootstrap the P2P network: populate k-buckets and membership lists.

        Every node learns about every other node, because in a 7-node
        cluster there's no point in gradual peer discovery. It's a room
        with 7 people -- everyone can see everyone else. But we still
        go through the ceremony of updating k-buckets and membership
        lists, because protocol compliance is non-negotiable.
        """
        start = time.perf_counter_ns()

        for node in self.nodes:
            for other in self.nodes:
                if other.node_id != node.node_id:
                    node.update_k_bucket(other.node_id)
                    node.membership[other.node_id] = (
                        NodeState.ALIVE,
                        other.heartbeat,
                    )

        self._bootstrap_time_ns = time.perf_counter_ns() - start
        self._emit_event(EventType.P2P_NODE_JOINED, {
            "num_nodes": self._num_nodes,
            "bootstrap_time_ns": self._bootstrap_time_ns,
        })

        logger.info(
            "P2P network bootstrapped: %d nodes in %.3fms",
            self._num_nodes,
            self._bootstrap_time_ns / 1_000_000,
        )

    def gossip_round(self) -> dict[str, Any]:
        """Execute one gossip round and record the result."""
        result = self.gossip.gossip_round()
        self._gossip_history.append(result)

        if result["state_changes"]:
            self._emit_event(EventType.P2P_NODE_STATE_CHANGED, {
                "round": result["round"],
                "changes": [
                    {"node": nid[:12], "from": old.name, "to": new.name}
                    for nid, old, new in result["state_changes"]
                ],
            })

        self._emit_event(EventType.P2P_GOSSIP_ROUND_COMPLETED, {
            "round": result["round"],
            "alive": result["alive_count"],
            "suspect": result["suspect_count"],
            "dead": result["dead_count"],
            "rumors_spread": result["rumors_spread"],
        })

        return result

    def evaluate_and_disseminate(
        self,
        number: int,
        output: str,
    ) -> dict[str, Any]:
        """Evaluate a FizzBuzz result on a random node and gossip it to all.

        The result is:
        1. Stored on a randomly selected alive node
        2. Stored in the DHT (replicated to k closest nodes)
        3. Added to the rumor buffer for epidemic dissemination
        4. Spread via gossip rounds until convergence

        Returns a summary of the dissemination process.
        """
        alive_nodes = [n for n in self.nodes if n.state == NodeState.ALIVE]
        if not alive_nodes:
            return {"converged": False, "rounds": 0, "reason": "no_alive_nodes"}

        # Pick a random origin node
        origin = random.choice(alive_nodes)
        origin.store_classification(number, output)
        origin.add_rumor(number, output, 0)

        # Store in DHT
        dht_key = f"{number}:{output}"
        stored_on = self.dht.store(dht_key, output)

        self._emit_event(EventType.P2P_DHT_STORE, {
            "number": number,
            "output": output,
            "origin": origin.node_id[:12],
            "replicated_to": len(stored_on),
        })

        # Run gossip rounds until convergence or max rounds
        expected_rounds = max(1, int(math.log2(max(1, len(alive_nodes)))) + 1)
        rounds = 0

        for _ in range(self._max_rounds):
            self.gossip_round()
            rounds += 1

            # Check convergence: all alive nodes have this classification
            alive_now = [n for n in self.nodes if n.state == NodeState.ALIVE]
            converged = all(
                n.get_classification(number) == output for n in alive_now
            )
            if converged:
                return {
                    "converged": True,
                    "rounds": rounds,
                    "expected_rounds": expected_rounds,
                    "origin": origin.node_id[:12],
                    "alive_count": len(alive_now),
                }

        return {
            "converged": False,
            "rounds": rounds,
            "expected_rounds": expected_rounds,
            "origin": origin.node_id[:12],
            "alive_count": len(
                [n for n in self.nodes if n.state == NodeState.ALIVE]
            ),
        }

    def partition(self, group_a_indices: list[int], group_b_indices: list[int]) -> None:
        """Simulate a network partition between two groups of nodes.

        Nodes in group_a cannot communicate with nodes in group_b, and
        vice versa. Within each group, communication is unaffected.
        This is the distributed systems equivalent of putting tape down
        the middle of the room and declaring two separate kingdoms.
        """
        for a_idx in group_a_indices:
            for b_idx in group_b_indices:
                if a_idx < len(self.nodes) and b_idx < len(self.nodes):
                    self.gossip.add_partition(
                        self.nodes[a_idx].node_id,
                        self.nodes[b_idx].node_id,
                    )

        self._partition_events.append({
            "type": "partition",
            "group_a": group_a_indices,
            "group_b": group_b_indices,
        })

        logger.info(
            "Network partition: group_a=%s, group_b=%s",
            group_a_indices,
            group_b_indices,
        )

    def heal(self) -> None:
        """Heal all network partitions and run anti-entropy sync.

        After healing, Merkle tree anti-entropy is run between all pairs
        of nodes to reconcile divergent classification stores. This is
        the distributed systems equivalent of a couples therapy session
        where everyone shares their truth and reconciles their differences.
        """
        self.gossip.clear_partitions()

        # Run anti-entropy between all pairs
        sync_results: list[dict[str, Any]] = []
        alive = [n for n in self.nodes if n.state != NodeState.DEAD]

        for i in range(len(alive)):
            for j in range(i + 1, len(alive)):
                result = self.merkle.compare_and_sync(alive[i], alive[j])
                if not result["in_sync"]:
                    sync_results.append({
                        "node_a": alive[i].node_id[:12],
                        "node_b": alive[j].node_id[:12],
                        "keys_synced": result["keys_synced"],
                    })

        self._partition_events.append({"type": "heal"})
        self._sync_events.extend(sync_results)

        if sync_results:
            self._emit_event(EventType.P2P_MERKLE_SYNC, {
                "pairs_synced": len(sync_results),
                "total_keys_synced": sum(
                    r["keys_synced"] for r in sync_results
                ),
            })

        logger.info(
            "Network healed: %d pair(s) synced via Merkle anti-entropy",
            len(sync_results),
        )

    def get_topology_summary(self) -> dict[str, Any]:
        """Return a summary of the current network topology."""
        alive = sum(1 for n in self.nodes if n.state == NodeState.ALIVE)
        suspect = sum(1 for n in self.nodes if n.state == NodeState.SUSPECT)
        dead = sum(1 for n in self.nodes if n.state == NodeState.DEAD)

        # Compute total classifications across all nodes
        all_classifications: set[int] = set()
        for node in self.nodes:
            all_classifications.update(node.classification_store.keys())

        return {
            "total_nodes": len(self.nodes),
            "alive": alive,
            "suspect": suspect,
            "dead": dead,
            "gossip_rounds": self.gossip.rounds_completed,
            "total_pings": self.gossip.total_pings,
            "total_ping_reqs": self.gossip.total_ping_reqs,
            "dht_lookups": self.dht.lookups_performed,
            "dht_stores": self.dht.stores_performed,
            "dht_gets": self.dht.gets_performed,
            "unique_classifications": len(all_classifications),
            "partition_events": len(self._partition_events),
            "sync_events": len(self._sync_events),
            "bootstrap_time_ms": self._bootstrap_time_ns / 1_000_000,
        }

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus, if available."""
        if self._event_bus is not None:
            try:
                from enterprise_fizzbuzz.domain.models import Event
                event = Event(
                    event_type=event_type,
                    payload=payload,
                    source="P2PNetwork",
                )
                self._event_bus.publish(event)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# P2PDashboard: ASCII dashboard
# ---------------------------------------------------------------------------

class P2PDashboard:
    """ASCII dashboard for the Enterprise FizzBuzz Peer-to-Peer Gossip Network.

    Renders a comprehensive overview of the P2P cluster including:
    - Network topology with node states and heartbeats
    - Gossip statistics (rounds, pings, rumors)
    - DHT summary (lookups, stores, gets)
    - Merkle anti-entropy status

    Because what's the point of simulating a distributed system if you
    can't look at an ASCII visualization of it?
    """

    @staticmethod
    def render(network: P2PNetwork, width: int = 60) -> str:
        """Render the complete P2P dashboard."""
        lines: list[str] = []
        hr = "+" + "-" * (width - 2) + "+"
        title_bar = f"|{'PEER-TO-PEER GOSSIP NETWORK DASHBOARD':^{width - 2}}|"

        lines.append(hr)
        lines.append(title_bar)
        lines.append(
            f"|{'Because distributed FizzBuzz is the future':^{width - 2}}|"
        )
        lines.append(hr)

        # Topology section
        topo = network.get_topology_summary()
        lines.append(f"|{'--- CLUSTER TOPOLOGY ---':^{width - 2}}|")
        lines.append(
            f"|  Total Nodes: {topo['total_nodes']:<{width - 18}}|"
        )

        state_str = (
            f"ALIVE={topo['alive']}  "
            f"SUSPECT={topo['suspect']}  "
            f"DEAD={topo['dead']}"
        )
        lines.append(f"|  States: {state_str:<{width - 13}}|")

        lines.append(f"|{'':<{width - 2}}|")

        # Node details
        lines.append(f"|{'--- NODE ROSTER ---':^{width - 2}}|")
        for node in network.nodes:
            state_icon = {
                NodeState.ALIVE: "[+]",
                NodeState.SUSPECT: "[?]",
                NodeState.DEAD: "[X]",
            }[node.state]
            node_line = (
                f"  {state_icon} {node.node_id[:12]}... "
                f"hb={node.heartbeat:>4} "
                f"store={len(node.classification_store):>3}"
            )
            lines.append(f"|{node_line:<{width - 2}}|")

        lines.append(f"|{'':<{width - 2}}|")

        # Gossip stats
        lines.append(f"|{'--- GOSSIP STATISTICS ---':^{width - 2}}|")
        lines.append(
            f"|  Rounds completed: {topo['gossip_rounds']:<{width - 23}}|"
        )
        lines.append(
            f"|  Total pings: {topo['total_pings']:<{width - 18}}|"
        )
        lines.append(
            f"|  Total ping-reqs: {topo['total_ping_reqs']:<{width - 22}}|"
        )

        total_rumors = sum(n.rumors_propagated for n in network.nodes)
        lines.append(
            f"|  Rumors propagated: {total_rumors:<{width - 24}}|"
        )

        lines.append(f"|{'':<{width - 2}}|")

        # DHT stats
        lines.append(f"|{'--- KADEMLIA DHT ---':^{width - 2}}|")
        lines.append(
            f"|  Lookups: {topo['dht_lookups']:<{width - 14}}|"
        )
        lines.append(
            f"|  Stores: {topo['dht_stores']:<{width - 13}}|"
        )
        lines.append(
            f"|  Gets: {topo['dht_gets']:<{width - 11}}|"
        )
        lines.append(
            f"|  Unique classifications: {topo['unique_classifications']:<{width - 29}}|"
        )

        lines.append(f"|{'':<{width - 2}}|")

        # Convergence assessment
        lines.append(f"|{'--- CONVERGENCE STATUS ---':^{width - 2}}|")
        alive_nodes = [n for n in network.nodes if n.state == NodeState.ALIVE]
        if alive_nodes:
            # Check if all alive nodes agree on all classifications
            reference = alive_nodes[0].classification_store
            all_agree = all(
                n.classification_store == reference for n in alive_nodes[1:]
            )
            if all_agree:
                conv_line = "  ALL ALIVE NODES IN CONSENSUS"
                lines.append(f"|{conv_line:<{width - 2}}|")
                conv_line2 = f"  Agreement on {len(reference)} classification(s)"
                lines.append(f"|{conv_line2:<{width - 2}}|")
            else:
                conv_line = "  DIVERGENCE DETECTED"
                lines.append(f"|{conv_line:<{width - 2}}|")
                # Count divergent keys
                all_keys: set[int] = set()
                for n in alive_nodes:
                    all_keys.update(n.classification_store.keys())
                divergent = 0
                for k in all_keys:
                    vals = {
                        n.get_classification(k)
                        for n in alive_nodes
                        if n.get_classification(k) is not None
                    }
                    if len(vals) > 1:
                        divergent += 1
                conv_line2 = f"  {divergent} key(s) with conflicting values"
                lines.append(f"|{conv_line2:<{width - 2}}|")
        else:
            lines.append(f"|{'  NO ALIVE NODES (the cluster is dead)':<{width - 2}}|")

        lines.append(f"|{'':<{width - 2}}|")
        bootstrap_line = (
            f"  Bootstrap time: {topo['bootstrap_time_ms']:.3f}ms"
        )
        lines.append(f"|{bootstrap_line:<{width - 2}}|")
        lines.append(hr)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# P2PMiddleware: IMiddleware integration
# ---------------------------------------------------------------------------

class P2PMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through the P2P network.

    Intercepts each evaluation, disseminates the result across the gossip
    network, and enriches the processing context with P2P metadata. The
    middleware runs at priority -8, which means it executes before most
    other middleware but after the critical path components.

    Every FizzBuzz evaluation now involves:
    1. The normal rule engine evaluation (the useful part)
    2. Storing the result on a random P2P node
    3. Replicating to k DHT nodes via Kademlia
    4. Gossiping the result to all peers via epidemic dissemination
    5. Building and comparing Merkle trees for anti-entropy

    Steps 2-5 add approximately zero value and significant ceremony.
    This is enterprise-grade peer-to-peer computing at its finest.
    """

    def __init__(
        self,
        network: P2PNetwork,
        event_bus: Any = None,
    ) -> None:
        self._network = network
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a number through the P2P network."""
        # Let the actual evaluation happen first
        result = next_handler(context)

        # Extract the classification result
        if result.results:
            latest = result.results[-1]
            number = latest.number
            output = latest.output

            # Disseminate through the P2P network
            dissemination = self._network.evaluate_and_disseminate(
                number, output
            )

            # Enrich metadata
            result.metadata["p2p_converged"] = dissemination.get(
                "converged", False
            )
            result.metadata["p2p_rounds"] = dissemination.get("rounds", 0)
            result.metadata["p2p_origin"] = dissemination.get("origin", "?")
            result.metadata["p2p_alive_count"] = dissemination.get(
                "alive_count", 0
            )

        return result

    def get_name(self) -> str:
        return "P2PMiddleware"

    def get_priority(self) -> int:
        return -8
