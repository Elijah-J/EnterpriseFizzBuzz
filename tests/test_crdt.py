"""
Enterprise FizzBuzz Platform - FizzCRDT Test Suite

Comprehensive tests for the Conflict-Free Replicated Data Types subsystem.
Verifies that every CRDT satisfies the join-semilattice axioms (commutative,
associative, idempotent merge) and that the replication engine achieves
Strong Eventual Consistency across all replicas.
"""

from __future__ import annotations

import time

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.crdt import (
    CRDTDashboard,
    CRDTMergeEngine,
    CRDTMiddleware,
    CRDTType,
    GCounter,
    LWWMap,
    LWWRegister,
    MVRegister,
    MergeResult,
    ORSet,
    PNCounter,
    RGA,
    RGANode,
    ReplicaState,
    VectorClock,
)
from enterprise_fizzbuzz.domain.exceptions import (
    CRDTCausalityViolationError,
    CRDTError,
    CRDTMergeConflictError,
    CRDTReplicaDivergenceError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# =====================================================================
# VectorClock Tests
# =====================================================================


class TestVectorClock:
    """Tests for the VectorClock implementation."""

    def test_create_empty(self):
        vc = VectorClock(node_id="a")
        assert vc.clocks == {}
        assert vc.node_id == "a"

    def test_increment(self):
        vc = VectorClock(node_id="a")
        vc.increment()
        assert vc.get("a") == 1
        vc.increment()
        assert vc.get("a") == 2

    def test_increment_other_node(self):
        vc = VectorClock(node_id="a")
        vc.increment("b")
        assert vc.get("a") == 0
        assert vc.get("b") == 1

    def test_merge_element_wise_max(self):
        vc1 = VectorClock(node_id="a", clocks={"a": 3, "b": 1})
        vc2 = VectorClock(node_id="b", clocks={"a": 1, "b": 5, "c": 2})
        merged = vc1.merge(vc2)
        assert merged.get("a") == 3
        assert merged.get("b") == 5
        assert merged.get("c") == 2

    def test_merge_commutative(self):
        vc1 = VectorClock(node_id="a", clocks={"a": 3, "b": 1})
        vc2 = VectorClock(node_id="b", clocks={"a": 1, "b": 5})
        m1 = vc1.merge(vc2)
        m2 = vc2.merge(vc1)
        assert m1 == m2

    def test_merge_idempotent(self):
        vc = VectorClock(node_id="a", clocks={"a": 3, "b": 1})
        merged = vc.merge(vc)
        assert merged == vc

    def test_happened_before_true(self):
        vc1 = VectorClock(node_id="a", clocks={"a": 1, "b": 1})
        vc2 = VectorClock(node_id="b", clocks={"a": 2, "b": 1})
        assert vc1.happened_before(vc2) is True

    def test_happened_before_false_when_equal(self):
        vc1 = VectorClock(node_id="a", clocks={"a": 1, "b": 1})
        vc2 = VectorClock(node_id="b", clocks={"a": 1, "b": 1})
        assert vc1.happened_before(vc2) is False

    def test_happened_before_false_when_concurrent(self):
        vc1 = VectorClock(node_id="a", clocks={"a": 2, "b": 1})
        vc2 = VectorClock(node_id="b", clocks={"a": 1, "b": 2})
        assert vc1.happened_before(vc2) is False
        assert vc2.happened_before(vc1) is False

    def test_is_concurrent(self):
        vc1 = VectorClock(node_id="a", clocks={"a": 2, "b": 1})
        vc2 = VectorClock(node_id="b", clocks={"a": 1, "b": 2})
        assert vc1.is_concurrent(vc2) is True

    def test_is_not_concurrent_when_ordered(self):
        vc1 = VectorClock(node_id="a", clocks={"a": 1, "b": 1})
        vc2 = VectorClock(node_id="b", clocks={"a": 2, "b": 2})
        assert vc1.is_concurrent(vc2) is False

    def test_dominates(self):
        vc1 = VectorClock(node_id="a", clocks={"a": 3, "b": 2})
        vc2 = VectorClock(node_id="b", clocks={"a": 1, "b": 2})
        assert vc1.dominates(vc2) is True
        assert vc2.dominates(vc1) is False

    def test_equality(self):
        vc1 = VectorClock(node_id="a", clocks={"a": 1, "b": 2})
        vc2 = VectorClock(node_id="b", clocks={"a": 1, "b": 2})
        assert vc1 == vc2

    def test_copy(self):
        vc = VectorClock(node_id="a", clocks={"a": 1, "b": 2})
        vc_copy = vc.copy()
        assert vc == vc_copy
        vc_copy.increment("a")
        assert vc != vc_copy

    def test_repr(self):
        vc = VectorClock(node_id="a", clocks={"a": 1})
        assert "a:1" in repr(vc)


# =====================================================================
# GCounter Tests
# =====================================================================


class TestGCounter:
    """Tests for the GCounter (grow-only counter) CRDT."""

    def test_create_empty(self):
        gc = GCounter(node_id="a")
        assert gc.value() == 0

    def test_increment(self):
        gc = GCounter(node_id="a")
        gc.increment()
        assert gc.value() == 1
        gc.increment(5)
        assert gc.value() == 6

    def test_increment_multiple_nodes(self):
        gc = GCounter(node_id="a")
        gc.increment(3, node_id="a")
        gc.increment(5, node_id="b")
        assert gc.value() == 8

    def test_increment_negative_raises(self):
        gc = GCounter(node_id="a")
        with pytest.raises(CRDTError):
            gc.increment(-1)

    def test_merge_element_wise_max(self):
        gc1 = GCounter(node_id="a", counters={"a": 3, "b": 1})
        gc2 = GCounter(node_id="b", counters={"a": 1, "b": 5})
        merged = gc1.merge(gc2)
        assert merged.value() == 8  # a=3, b=5

    def test_merge_commutative(self):
        gc1 = GCounter(node_id="a", counters={"a": 3, "b": 1})
        gc2 = GCounter(node_id="b", counters={"a": 1, "b": 5})
        assert gc1.merge(gc2) == gc2.merge(gc1)

    def test_merge_associative(self):
        gc1 = GCounter(node_id="a", counters={"a": 3})
        gc2 = GCounter(node_id="b", counters={"b": 5})
        gc3 = GCounter(node_id="c", counters={"c": 7})
        assert gc1.merge(gc2).merge(gc3) == gc1.merge(gc2.merge(gc3))

    def test_merge_idempotent(self):
        gc = GCounter(node_id="a", counters={"a": 3, "b": 1})
        assert gc.merge(gc) == gc

    def test_equality(self):
        gc1 = GCounter(node_id="a", counters={"a": 3, "b": 1})
        gc2 = GCounter(node_id="b", counters={"a": 3, "b": 1})
        assert gc1 == gc2

    def test_repr(self):
        gc = GCounter(node_id="a")
        gc.increment(5)
        assert "5" in repr(gc)


# =====================================================================
# PNCounter Tests
# =====================================================================


class TestPNCounter:
    """Tests for the PNCounter (positive-negative counter) CRDT."""

    def test_create_zero(self):
        pn = PNCounter(node_id="a")
        assert pn.value() == 0

    def test_increment(self):
        pn = PNCounter(node_id="a")
        pn.increment(5)
        assert pn.value() == 5

    def test_decrement(self):
        pn = PNCounter(node_id="a")
        pn.increment(10)
        pn.decrement(3)
        assert pn.value() == 7

    def test_negative_value(self):
        pn = PNCounter(node_id="a")
        pn.decrement(5)
        assert pn.value() == -5

    def test_merge(self):
        pn1 = PNCounter(node_id="a")
        pn1.increment(5, node_id="a")
        pn1.decrement(2, node_id="a")

        pn2 = PNCounter(node_id="b")
        pn2.increment(3, node_id="b")
        pn2.decrement(1, node_id="b")

        merged = pn1.merge(pn2)
        # P: a=5, b=3 -> 8, N: a=2, b=1 -> 3, value = 5
        assert merged.value() == 5

    def test_merge_commutative(self):
        pn1 = PNCounter(node_id="a")
        pn1.increment(5, node_id="a")
        pn2 = PNCounter(node_id="b")
        pn2.increment(3, node_id="b")
        assert pn1.merge(pn2).value() == pn2.merge(pn1).value()

    def test_merge_idempotent(self):
        pn = PNCounter(node_id="a")
        pn.increment(5)
        assert pn.merge(pn) == pn

    def test_repr(self):
        pn = PNCounter(node_id="a")
        pn.increment(10)
        pn.decrement(3)
        assert "7" in repr(pn)


# =====================================================================
# LWWRegister Tests
# =====================================================================


class TestLWWRegister:
    """Tests for the LWWRegister (last-writer-wins register) CRDT."""

    def test_create_empty(self):
        reg = LWWRegister(node_id="a")
        assert reg.value is None
        assert reg.timestamp == 0.0

    def test_set_value(self):
        reg = LWWRegister(node_id="a")
        reg.set("Fizz", timestamp=1.0)
        assert reg.value == "Fizz"
        assert reg.timestamp == 1.0

    def test_set_ignores_older(self):
        reg = LWWRegister(node_id="a")
        reg.set("Fizz", timestamp=2.0)
        reg.set("Buzz", timestamp=1.0)
        assert reg.value == "Fizz"

    def test_merge_keeps_latest(self):
        reg1 = LWWRegister(node_id="a", value="Fizz", timestamp=1.0)
        reg2 = LWWRegister(node_id="b", value="Buzz", timestamp=2.0)
        merged = reg1.merge(reg2)
        assert merged.value == "Buzz"

    def test_merge_commutative(self):
        reg1 = LWWRegister(node_id="a", value="Fizz", timestamp=1.0)
        reg2 = LWWRegister(node_id="b", value="Buzz", timestamp=2.0)
        assert reg1.merge(reg2).value == reg2.merge(reg1).value

    def test_merge_idempotent(self):
        reg = LWWRegister(node_id="a", value="Fizz", timestamp=1.0)
        assert reg.merge(reg) == reg

    def test_merge_tiebreak_by_node_id(self):
        reg1 = LWWRegister(node_id="a", value="Fizz", timestamp=1.0)
        reg2 = LWWRegister(node_id="b", value="Buzz", timestamp=1.0)
        # node_id "b" > "a", so reg2's value wins
        merged = reg1.merge(reg2)
        assert merged.value == "Buzz"

    def test_equality(self):
        reg1 = LWWRegister(node_id="a", value="Fizz", timestamp=1.0)
        reg2 = LWWRegister(node_id="b", value="Fizz", timestamp=1.0)
        assert reg1 == reg2

    def test_repr(self):
        reg = LWWRegister(node_id="a", value="Fizz", timestamp=1.0)
        assert "Fizz" in repr(reg)


# =====================================================================
# MVRegister Tests
# =====================================================================


class TestMVRegister:
    """Tests for the MVRegister (multi-value register) CRDT."""

    def test_create_empty(self):
        mv = MVRegister(node_id="a")
        assert mv.values == []

    def test_set_value(self):
        mv = MVRegister(node_id="a")
        vc = VectorClock(node_id="a", clocks={"a": 1})
        mv.set("Fizz", vc)
        assert "Fizz" in mv.values

    def test_set_replaces_dominated(self):
        mv = MVRegister(node_id="a")
        vc1 = VectorClock(node_id="a", clocks={"a": 1})
        mv.set("Fizz", vc1)
        vc2 = VectorClock(node_id="a", clocks={"a": 2})
        mv.set("Buzz", vc2)
        assert mv.values == ["Buzz"]

    def test_merge_keeps_concurrent(self):
        mv1 = MVRegister(node_id="a")
        vc1 = VectorClock(node_id="a", clocks={"a": 1})
        mv1.set("Fizz", vc1)

        mv2 = MVRegister(node_id="b")
        vc2 = VectorClock(node_id="b", clocks={"b": 1})
        mv2.set("Buzz", vc2)

        merged = mv1.merge(mv2)
        assert len(merged.values) == 2
        assert "Fizz" in merged.values
        assert "Buzz" in merged.values

    def test_merge_discards_dominated(self):
        mv1 = MVRegister(node_id="a")
        vc1 = VectorClock(node_id="a", clocks={"a": 1})
        mv1.set("Fizz", vc1)

        mv2 = MVRegister(node_id="b")
        vc2 = VectorClock(node_id="a", clocks={"a": 2})
        mv2.set("Buzz", vc2)

        merged = mv1.merge(mv2)
        assert merged.values == ["Buzz"]

    def test_merge_commutative(self):
        mv1 = MVRegister(node_id="a")
        vc1 = VectorClock(node_id="a", clocks={"a": 1})
        mv1.set("Fizz", vc1)

        mv2 = MVRegister(node_id="b")
        vc2 = VectorClock(node_id="b", clocks={"b": 1})
        mv2.set("Buzz", vc2)

        m1 = mv1.merge(mv2)
        m2 = mv2.merge(mv1)
        assert set(m1.values) == set(m2.values)

    def test_merge_idempotent(self):
        mv = MVRegister(node_id="a")
        vc = VectorClock(node_id="a", clocks={"a": 1})
        mv.set("Fizz", vc)
        merged = mv.merge(mv)
        assert merged.values == mv.values

    def test_repr(self):
        mv = MVRegister(node_id="a")
        assert "MVRegister" in repr(mv)


# =====================================================================
# ORSet Tests
# =====================================================================


class TestORSet:
    """Tests for the ORSet (observed-remove set) CRDT."""

    def test_create_empty(self):
        s = ORSet(node_id="a")
        assert len(s) == 0
        assert s.elements() == set()

    def test_add(self):
        s = ORSet(node_id="a")
        s.add("Fizz")
        assert s.contains("Fizz") is True
        assert len(s) == 1

    def test_remove(self):
        s = ORSet(node_id="a")
        s.add("Fizz")
        s.remove("Fizz")
        assert s.contains("Fizz") is False

    def test_add_wins_concurrent(self):
        """Concurrent add and remove of same element: add wins."""
        s1 = ORSet(node_id="a")
        s1.add("Fizz")

        # s2 observes Fizz and removes it
        s2 = ORSet(node_id="b")
        s2._elements = {"Fizz": set()}  # Simulates remove

        # s1 adds Fizz concurrently (new tag)
        # Merge should keep the element (add-wins)
        merged = s1.merge(s2)
        assert merged.contains("Fizz") is True

    def test_merge_union_of_tags(self):
        s1 = ORSet(node_id="a")
        s1.add("Fizz")

        s2 = ORSet(node_id="b")
        s2.add("Buzz")

        merged = s1.merge(s2)
        assert merged.contains("Fizz") is True
        assert merged.contains("Buzz") is True

    def test_merge_commutative(self):
        s1 = ORSet(node_id="a")
        s1.add("Fizz")
        s2 = ORSet(node_id="b")
        s2.add("Buzz")
        assert s1.merge(s2).elements() == s2.merge(s1).elements()

    def test_merge_idempotent(self):
        s = ORSet(node_id="a")
        s.add("Fizz")
        s.add("Buzz")
        merged = s.merge(s)
        assert merged.elements() == s.elements()

    def test_merge_associative(self):
        s1 = ORSet(node_id="a")
        s1.add("Fizz")
        s2 = ORSet(node_id="b")
        s2.add("Buzz")
        s3 = ORSet(node_id="c")
        s3.add("FizzBuzz")
        assert s1.merge(s2).merge(s3).elements() == s1.merge(s2.merge(s3)).elements()

    def test_remove_nonexistent_is_noop(self):
        s = ORSet(node_id="a")
        s.remove("Nonexistent")
        assert len(s) == 0

    def test_add_duplicate(self):
        s = ORSet(node_id="a")
        s.add("Fizz")
        s.add("Fizz")
        assert s.contains("Fizz") is True

    def test_repr(self):
        s = ORSet(node_id="a")
        s.add("Fizz")
        assert "ORSet" in repr(s)


# =====================================================================
# LWWMap Tests
# =====================================================================


class TestLWWMap:
    """Tests for the LWWMap (last-writer-wins map) CRDT."""

    def test_create_empty(self):
        m = LWWMap(node_id="a")
        assert m.keys() == set()

    def test_set_and_get(self):
        m = LWWMap(node_id="a")
        m.set("divisor", 3, timestamp=1.0)
        assert m.get("divisor") == 3

    def test_set_overwrites_with_newer(self):
        m = LWWMap(node_id="a")
        m.set("divisor", 3, timestamp=1.0)
        m.set("divisor", 5, timestamp=2.0)
        assert m.get("divisor") == 5

    def test_remove(self):
        m = LWWMap(node_id="a")
        m.set("divisor", 3, timestamp=1.0)
        m.remove("divisor", timestamp=2.0)
        assert m.get("divisor") is None

    def test_set_after_remove(self):
        m = LWWMap(node_id="a")
        m.set("divisor", 3, timestamp=1.0)
        m.remove("divisor", timestamp=2.0)
        m.set("divisor", 5, timestamp=3.0)
        assert m.get("divisor") == 5

    def test_merge(self):
        m1 = LWWMap(node_id="a")
        m1.set("fizz", 3, timestamp=1.0)

        m2 = LWWMap(node_id="b")
        m2.set("buzz", 5, timestamp=1.0)

        merged = m1.merge(m2)
        assert merged.get("fizz") == 3
        assert merged.get("buzz") == 5

    def test_merge_commutative(self):
        m1 = LWWMap(node_id="a")
        m1.set("key", "val1", timestamp=1.0)
        m2 = LWWMap(node_id="b")
        m2.set("key", "val2", timestamp=2.0)
        assert m1.merge(m2).get("key") == m2.merge(m1).get("key")

    def test_merge_idempotent(self):
        m = LWWMap(node_id="a")
        m.set("key", "val", timestamp=1.0)
        assert m.merge(m) == m

    def test_merge_with_tombstone(self):
        m1 = LWWMap(node_id="a")
        m1.set("key", "val", timestamp=1.0)

        m2 = LWWMap(node_id="b")
        m2.set("key", "val", timestamp=1.0)
        m2.remove("key", timestamp=2.0)

        merged = m1.merge(m2)
        assert merged.get("key") is None

    def test_items(self):
        m = LWWMap(node_id="a")
        m.set("a", 1, timestamp=1.0)
        m.set("b", 2, timestamp=1.0)
        items = dict(m.items())
        assert items == {"a": 1, "b": 2}

    def test_repr(self):
        m = LWWMap(node_id="a")
        m.set("key", "val", timestamp=1.0)
        assert "LWWMap" in repr(m)


# =====================================================================
# RGA Tests
# =====================================================================


class TestRGA:
    """Tests for the RGA (replicated growable array) CRDT."""

    def test_create_empty(self):
        rga = RGA(node_id="a")
        assert rga.values() == []
        assert len(rga) == 0

    def test_append(self):
        rga = RGA(node_id="a")
        rga.append("Fizz")
        rga.append("Buzz")
        assert rga.values() == ["Fizz", "Buzz"]

    def test_insert_at_beginning(self):
        rga = RGA(node_id="a")
        rga.append("Buzz")
        rga.insert(0, "Fizz")
        assert rga.values() == ["Fizz", "Buzz"]

    def test_insert_in_middle(self):
        rga = RGA(node_id="a")
        rga.append("Fizz")
        rga.append("FizzBuzz")
        rga.insert(1, "Buzz")
        assert rga.values() == ["Fizz", "Buzz", "FizzBuzz"]

    def test_delete(self):
        rga = RGA(node_id="a")
        rga.append("Fizz")
        rga.append("Buzz")
        rga.delete(0)
        assert rga.values() == ["Buzz"]

    def test_merge_combines_elements(self):
        rga1 = RGA(node_id="a")
        rga1.append("Fizz")

        rga2 = RGA(node_id="b")
        rga2.append("Buzz")

        merged = rga1.merge(rga2)
        assert len(merged) == 2
        assert "Fizz" in merged.values()
        assert "Buzz" in merged.values()

    def test_merge_commutative(self):
        rga1 = RGA(node_id="a")
        rga1.append("Fizz")

        rga2 = RGA(node_id="b")
        rga2.append("Buzz")

        assert rga1.merge(rga2).values() == rga2.merge(rga1).values()

    def test_merge_idempotent(self):
        rga = RGA(node_id="a")
        rga.append("Fizz")
        rga.append("Buzz")
        assert rga.merge(rga).values() == rga.values()

    def test_merge_preserves_tombstones(self):
        rga1 = RGA(node_id="a")
        uid = rga1.append("Fizz")
        rga1.append("Buzz")

        # Create a copy and delete in it
        rga2 = RGA(node_id="b")
        for node in rga1.all_nodes():
            rga2._nodes.append(RGANode(
                value=node.value,
                timestamp=node.timestamp,
                node_id=node.node_id,
                unique_id=node.unique_id,
                tombstone=node.tombstone,
            ))
        rga2._lamport_clock = rga1._lamport_clock
        rga2._rebuild_index()
        rga2.delete(0)  # Delete "Fizz" in rga2

        merged = rga1.merge(rga2)
        # Tombstone should be preserved
        assert "Fizz" not in merged.values()
        assert "Buzz" in merged.values()

    def test_concurrent_inserts_ordered_by_timestamp_and_node(self):
        """Concurrent inserts at same position are ordered by (timestamp, node_id)."""
        rga1 = RGA(node_id="a")
        rga1._lamport_clock = 10.0
        rga1.append("from_a")

        rga2 = RGA(node_id="b")
        rga2._lamport_clock = 10.0
        rga2.append("from_b")

        merged = rga1.merge(rga2)
        vals = merged.values()
        # Both have timestamp 11.0, tiebreak by node_id ("a" < "b")
        assert vals[0] == "from_a"
        assert vals[1] == "from_b"

    def test_repr(self):
        rga = RGA(node_id="a")
        rga.append("Fizz")
        assert "Fizz" in repr(rga)


# =====================================================================
# CRDTMergeEngine Tests
# =====================================================================


class TestCRDTMergeEngine:
    """Tests for the CRDT merge engine."""

    def test_register_replica(self):
        engine = CRDTMergeEngine()
        state = engine.register_replica("node-0")
        assert state.replica_id == "node-0"
        assert "node-0" in engine.replicas

    def test_register_duplicate_returns_existing(self):
        engine = CRDTMergeEngine()
        s1 = engine.register_replica("node-0")
        s2 = engine.register_replica("node-0")
        assert s1 is s2

    def test_set_and_get_crdt(self):
        engine = CRDTMergeEngine()
        engine.register_replica("node-0")
        gc = GCounter(node_id="node-0")
        gc.increment(5)
        engine.set_crdt("node-0", "counter", gc)
        retrieved = engine.get_crdt("node-0", "counter")
        assert retrieved.value() == 5

    def test_set_crdt_unregistered_raises(self):
        engine = CRDTMergeEngine()
        gc = GCounter(node_id="x")
        with pytest.raises(CRDTReplicaDivergenceError):
            engine.set_crdt("x", "counter", gc)

    def test_merge_replicas(self):
        engine = CRDTMergeEngine()
        engine.register_replica("a")
        engine.register_replica("b")

        gc_a = GCounter(node_id="a")
        gc_a.increment(5, node_id="a")
        engine.set_crdt("a", "counter", gc_a)

        gc_b = GCounter(node_id="b")
        gc_b.increment(3, node_id="b")
        engine.set_crdt("b", "counter", gc_b)

        result = engine.merge_replicas("a", "b")
        assert result.crdts_merged > 0

        merged = engine.get_crdt("b", "counter")
        assert merged.value() == 8

    def test_merge_nonexistent_source_raises(self):
        engine = CRDTMergeEngine()
        engine.register_replica("b")
        with pytest.raises(CRDTReplicaDivergenceError):
            engine.merge_replicas("nonexistent", "b")

    def test_full_sync(self):
        engine = CRDTMergeEngine()
        engine.register_replica("a")
        engine.register_replica("b")
        engine.register_replica("c")

        gc_a = GCounter(node_id="a")
        gc_a.increment(5, node_id="a")
        engine.set_crdt("a", "counter", gc_a)

        gc_b = GCounter(node_id="b")
        gc_b.increment(3, node_id="b")
        engine.set_crdt("b", "counter", gc_b)

        results = engine.full_sync()
        assert len(results) == 6  # 3 * 2 = 6 pairs

        # All replicas should now have the same counter value
        for rid in ["a", "b", "c"]:
            c = engine.get_crdt(rid, "counter")
            assert c is not None
            assert c.value() == 8

    def test_convergence_report(self):
        engine = CRDTMergeEngine()
        engine.register_replica("a")
        engine.register_replica("b")

        gc = GCounter(node_id="a")
        gc.increment(5)
        engine.set_crdt("a", "counter", gc)
        engine.set_crdt("b", "counter", GCounter(node_id="b"))

        report = engine.convergence_report()
        assert report["total_replicas"] == 2
        assert report["all_converged"] is False

        engine.full_sync()
        report = engine.convergence_report()
        assert report["all_converged"] is True

    def test_merge_history(self):
        engine = CRDTMergeEngine()
        engine.register_replica("a")
        engine.register_replica("b")
        engine.merge_replicas("a", "b")
        assert len(engine.merge_history) == 1
        assert engine.total_merges == 1


# =====================================================================
# CRDTDashboard Tests
# =====================================================================


class TestCRDTDashboard:
    """Tests for the CRDT ASCII dashboard."""

    def test_render_empty(self):
        engine = CRDTMergeEngine()
        output = CRDTDashboard.render(engine, width=60)
        assert "FizzCRDT" in output
        assert "Convergence Summary" in output

    def test_render_with_replicas(self):
        engine = CRDTMergeEngine()
        engine.register_replica("node-0")
        engine.register_replica("node-1")
        gc = GCounter(node_id="node-0")
        gc.increment(5)
        engine.set_crdt("node-0", "eval_counter", gc)

        output = CRDTDashboard.render(engine, width=60)
        assert "node-0" in output
        assert "node-1" in output
        assert "GCounter" in output

    def test_render_after_merge(self):
        engine = CRDTMergeEngine()
        engine.register_replica("a")
        engine.register_replica("b")
        gc = GCounter(node_id="a")
        gc.increment(3)
        engine.set_crdt("a", "counter", gc)
        engine.merge_replicas("a", "b")

        output = CRDTDashboard.render(engine, width=60)
        assert "Recent Merges" in output
        assert "a -> b" in output

    def test_render_custom_width(self):
        engine = CRDTMergeEngine()
        output = CRDTDashboard.render(engine, width=80)
        for line in output.strip().split("\n"):
            if line.startswith("+"):
                assert len(line) == 80


# =====================================================================
# CRDTMiddleware Tests
# =====================================================================


class TestCRDTMiddleware:
    """Tests for the CRDT middleware."""

    def _make_context(self, number: int = 15) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-session")

    def _make_handler(self, output: str = "FizzBuzz"):
        def handler(ctx: ProcessingContext) -> ProcessingContext:
            ctx.results.append(
                FizzBuzzResult(
                    number=ctx.number,
                    output=output,
                )
            )
            return ctx
        return handler

    def test_priority(self):
        engine = CRDTMergeEngine()
        middleware = CRDTMiddleware(engine=engine, replica_count=3)
        assert middleware.get_priority() == 870

    def test_name(self):
        engine = CRDTMergeEngine()
        middleware = CRDTMiddleware(engine=engine, replica_count=3)
        assert middleware.get_name() == "CRDTMiddleware"

    def test_process_replicates_classification(self):
        engine = CRDTMergeEngine()
        middleware = CRDTMiddleware(engine=engine, replica_count=3)
        ctx = self._make_context(15)
        handler = self._make_handler("FizzBuzz")
        result = middleware.process(ctx, handler)
        assert result.metadata["crdt_replicas"] == 3
        assert middleware.evaluation_count == 1

    def test_process_increments_counters(self):
        engine = CRDTMergeEngine()
        middleware = CRDTMiddleware(engine=engine, replica_count=2)
        ctx = self._make_context(3)
        handler = self._make_handler("Fizz")
        middleware.process(ctx, handler)

        # Check that the counter was replicated (output="Fizz")
        for rid in ["fizz-node-0", "fizz-node-1"]:
            counter = engine.get_crdt(rid, "count_Fizz")
            assert counter is not None
            assert counter.value() > 0

    def test_multiple_evaluations(self):
        engine = CRDTMergeEngine()
        middleware = CRDTMiddleware(engine=engine, replica_count=2)
        handler = self._make_handler("Fizz")

        for i in range(5):
            ctx = self._make_context(i)
            middleware.process(ctx, handler)

        assert middleware.evaluation_count == 5


# =====================================================================
# Exception Tests
# =====================================================================


class TestCRDTExceptions:
    """Tests for the CRDT exception hierarchy."""

    def test_crdt_error(self):
        err = CRDTError("something went wrong")
        assert "EFP-CRDT00" in str(err)

    def test_merge_conflict_error(self):
        err = CRDTMergeConflictError(crdt_type="GCounter", detail="negative value")
        assert "EFP-CRDT01" in str(err)
        assert err.crdt_type == "GCounter"

    def test_causality_violation_error(self):
        err = CRDTCausalityViolationError(clock_a="VC(a:1)", clock_b="VC(b:2)")
        assert "EFP-CRDT02" in str(err)

    def test_replica_divergence_error(self):
        err = CRDTReplicaDivergenceError(
            replica_a="node-0", replica_b="node-1", crdt_name="counter"
        )
        assert "EFP-CRDT03" in str(err)

    def test_crdt_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = CRDTError("test")
        assert isinstance(err, FizzBuzzError)

    def test_merge_conflict_is_crdt_error(self):
        err = CRDTMergeConflictError("GCounter", "bad")
        assert isinstance(err, CRDTError)


# =====================================================================
# Semilattice Axiom Property Tests
# =====================================================================


class TestSemilatticeAxioms:
    """Verify that all CRDTs satisfy join-semilattice axioms."""

    def test_gcounter_commutativity(self):
        a = GCounter(node_id="a", counters={"a": 3, "b": 1})
        b = GCounter(node_id="b", counters={"a": 1, "b": 5, "c": 2})
        assert a.merge(b) == b.merge(a)

    def test_gcounter_associativity(self):
        a = GCounter(node_id="a", counters={"a": 3})
        b = GCounter(node_id="b", counters={"b": 5})
        c = GCounter(node_id="c", counters={"c": 7})
        assert a.merge(b).merge(c) == a.merge(b.merge(c))

    def test_gcounter_idempotency(self):
        a = GCounter(node_id="a", counters={"a": 3, "b": 1})
        assert a.merge(a) == a

    def test_pncounter_commutativity(self):
        a = PNCounter(node_id="a")
        a.increment(5, node_id="a")
        a.decrement(2, node_id="a")
        b = PNCounter(node_id="b")
        b.increment(3, node_id="b")
        assert a.merge(b).value() == b.merge(a).value()

    def test_lww_register_commutativity(self):
        a = LWWRegister(node_id="a", value="Fizz", timestamp=1.0)
        b = LWWRegister(node_id="b", value="Buzz", timestamp=2.0)
        assert a.merge(b).value == b.merge(a).value

    def test_lww_register_idempotency(self):
        a = LWWRegister(node_id="a", value="Fizz", timestamp=1.0)
        assert a.merge(a) == a

    def test_orset_commutativity(self):
        a = ORSet(node_id="a")
        a.add("Fizz")
        b = ORSet(node_id="b")
        b.add("Buzz")
        assert a.merge(b).elements() == b.merge(a).elements()

    def test_orset_associativity(self):
        a = ORSet(node_id="a")
        a.add("Fizz")
        b = ORSet(node_id="b")
        b.add("Buzz")
        c = ORSet(node_id="c")
        c.add("FizzBuzz")
        assert a.merge(b).merge(c).elements() == a.merge(b.merge(c)).elements()

    def test_orset_idempotency(self):
        a = ORSet(node_id="a")
        a.add("Fizz")
        a.add("Buzz")
        assert a.merge(a).elements() == a.elements()

    def test_vector_clock_commutativity(self):
        a = VectorClock(node_id="a", clocks={"a": 3, "b": 1})
        b = VectorClock(node_id="b", clocks={"a": 1, "b": 5})
        assert a.merge(b) == b.merge(a)

    def test_vector_clock_associativity(self):
        a = VectorClock(node_id="a", clocks={"a": 3})
        b = VectorClock(node_id="b", clocks={"b": 5})
        c = VectorClock(node_id="c", clocks={"c": 7})
        assert a.merge(b).merge(c) == a.merge(b.merge(c))

    def test_vector_clock_idempotency(self):
        a = VectorClock(node_id="a", clocks={"a": 3, "b": 1})
        assert a.merge(a) == a
