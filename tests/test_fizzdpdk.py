"""
Enterprise FizzBuzz Platform - FizzDPDK Data Plane Development Kit Test Suite

Comprehensive tests for the DPDK packet processing engine, covering mbuf
pool allocation, ring buffer operations, RSS hash computation, flow
classification, Ethernet port management, EAL initialization, middleware
pipeline integration, dashboard rendering, and exception handling.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzdpdk import (
    FIZZDPDK_VERSION,
    MIDDLEWARE_PRIORITY,
    DEFAULT_RING_SIZE,
    DPDKDashboard,
    DPDKEal,
    DPDKMiddleware,
    EthPort,
    FlowAction,
    FlowClassifier,
    Mbuf,
    MbufPool,
    PortState,
    RSSEngine,
    RingBuffer,
    RingMode,
    create_fizzdpdk_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    DPDKFlowError,
    DPDKMbufPoolError,
    DPDKPortError,
    DPDKRingError,
    DPDKRxError,
    DPDKTxError,
)


# =========================================================================
# Helpers
# =========================================================================

@dataclass
class ProcessingContext:
    number: int
    session_id: str = "test-session"
    results: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    def test_version(self):
        assert FIZZDPDK_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 248


# =========================================================================
# Mbuf Pool
# =========================================================================

class TestMbufPool:
    def test_create_pool(self):
        pool = MbufPool("test", num_mbufs=16, mbuf_size=256)
        assert pool.available == 16
        assert pool.allocated == 0

    def test_alloc(self):
        pool = MbufPool("test", num_mbufs=4)
        mbuf = pool.alloc()
        assert isinstance(mbuf, Mbuf)
        assert pool.allocated == 1
        assert pool.available == 3

    def test_free(self):
        pool = MbufPool("test", num_mbufs=4)
        mbuf = pool.alloc()
        pool.free(mbuf)
        assert pool.allocated == 0
        assert pool.available == 4

    def test_pool_exhaustion(self):
        pool = MbufPool("test", num_mbufs=2)
        pool.alloc()
        pool.alloc()
        with pytest.raises(DPDKMbufPoolError):
            pool.alloc()

    def test_utilization(self):
        pool = MbufPool("test", num_mbufs=4)
        pool.alloc()
        assert pool.utilization == 0.25


# =========================================================================
# Ring Buffer
# =========================================================================

class TestRingBuffer:
    def test_create_ring(self):
        ring = RingBuffer("test", size=16)
        assert ring.size == 16
        assert ring.is_empty

    def test_non_power_of_2_raises(self):
        with pytest.raises(DPDKRingError):
            RingBuffer("test", size=7)

    def test_enqueue_dequeue(self):
        ring = RingBuffer("test", size=4)
        assert ring.enqueue("a") is True
        assert ring.count == 1
        item = ring.dequeue()
        assert item == "a"
        assert ring.is_empty

    def test_full(self):
        ring = RingBuffer("test", size=2)
        ring.enqueue("a")
        ring.enqueue("b")
        assert ring.is_full
        assert ring.enqueue("c") is False

    def test_dequeue_empty(self):
        ring = RingBuffer("test", size=4)
        assert ring.dequeue() is None

    def test_burst_enqueue(self):
        ring = RingBuffer("test", size=4)
        count = ring.enqueue_burst(["a", "b", "c"])
        assert count == 3
        assert ring.count == 3

    def test_burst_dequeue(self):
        ring = RingBuffer("test", size=8)
        ring.enqueue_burst(["a", "b", "c"])
        items = ring.dequeue_burst(2)
        assert items == ["a", "b"]

    def test_wrap_around(self):
        ring = RingBuffer("test", size=4)
        ring.enqueue("a")
        ring.enqueue("b")
        ring.dequeue()
        ring.dequeue()
        ring.enqueue("c")
        ring.enqueue("d")
        ring.enqueue("e")
        assert ring.dequeue() == "c"
        assert ring.dequeue() == "d"
        assert ring.dequeue() == "e"


# =========================================================================
# RSS Engine
# =========================================================================

class TestRSSEngine:
    def test_compute_hash(self):
        rss = RSSEngine(num_queues=4)
        h = rss.compute_hash(0x0A000001, 0x0A000002, 80, 443, 6)
        assert isinstance(h, int)

    def test_get_queue(self):
        rss = RSSEngine(num_queues=4)
        h = rss.compute_hash(0x0A000001, 0x0A000002, 80, 443, 6)
        q = rss.get_queue(h)
        assert 0 <= q < 4

    def test_deterministic(self):
        rss = RSSEngine(num_queues=4)
        h1 = rss.compute_hash(1, 2, 3, 4, 6)
        h2 = rss.compute_hash(1, 2, 3, 4, 6)
        assert h1 == h2


# =========================================================================
# Flow Classifier
# =========================================================================

class TestFlowClassifier:
    def test_add_rule(self):
        fc = FlowClassifier()
        rid = fc.add_rule(src_ip=0x0A000001, action=FlowAction.QUEUE, target_queue=2)
        assert fc.rule_count == 1

    def test_classify_match(self):
        fc = FlowClassifier()
        fc.add_rule(src_ip=0x0A000001, action=FlowAction.QUEUE, target_queue=2)
        rule = fc.classify(0x0A000001, 0, 0, 0, 0)
        assert rule is not None
        assert rule.target_queue == 2
        assert rule.hit_count == 1

    def test_classify_no_match(self):
        fc = FlowClassifier()
        fc.add_rule(src_ip=0x0A000001)
        rule = fc.classify(0x0B000001, 0, 0, 0, 0)
        assert rule is None

    def test_delete_rule(self):
        fc = FlowClassifier()
        rid = fc.add_rule(src_ip=1)
        fc.delete_rule(rid)
        assert fc.rule_count == 0

    def test_delete_missing_rule(self):
        fc = FlowClassifier()
        with pytest.raises(DPDKFlowError):
            fc.delete_rule(99)


# =========================================================================
# Ethernet Port
# =========================================================================

class TestEthPort:
    def test_create_port(self):
        port = EthPort(0, num_rx_queues=2, num_tx_queues=2)
        assert port.state == PortState.STOPPED

    def test_start_stop(self):
        port = EthPort(0)
        port.start()
        assert port.state == PortState.STARTED
        port.stop()
        assert port.state == PortState.STOPPED

    def test_rx_not_started(self):
        port = EthPort(0)
        with pytest.raises(DPDKRxError):
            port.rx_burst(0, 32)

    def test_tx_not_started(self):
        port = EthPort(0)
        with pytest.raises(DPDKTxError):
            port.tx_burst(0, [])

    def test_inject_and_rx(self):
        port = EthPort(0, num_rx_queues=1)
        port.start()
        mbuf = Mbuf(buf_id=0, data=bytearray(64), data_len=64, pkt_len=64)
        port.inject_rx(0, mbuf)
        pkts = port.rx_burst(0, 32)
        assert len(pkts) == 1
        assert port.stats.rx_packets == 1


# =========================================================================
# DPDK EAL
# =========================================================================

class TestDPDKEal:
    def test_create(self):
        eal = DPDKEal(num_mbufs=64)
        assert eal.mbuf_pool.num_mbufs == 64

    def test_create_port(self):
        eal = DPDKEal()
        port = eal.create_port(0)
        assert eal.port_count == 1

    def test_create_duplicate_port(self):
        eal = DPDKEal()
        eal.create_port(0)
        with pytest.raises(DPDKPortError):
            eal.create_port(0)

    def test_get_stats(self):
        eal = DPDKEal()
        stats = eal.get_stats()
        assert stats["version"] == FIZZDPDK_VERSION


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    def test_render(self):
        eal = DPDKEal()
        output = DPDKDashboard.render(eal)
        assert "FizzDPDK" in output
        assert "Mbufs" in output


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    def test_process_fizz(self):
        eal, mw = create_fizzdpdk_subsystem()
        ctx = ProcessingContext(number=9)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["dpdk_classification"] == "Fizz"

    def test_process_buzz(self):
        eal, mw = create_fizzdpdk_subsystem()
        ctx = ProcessingContext(number=25)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["dpdk_classification"] == "Buzz"

    def test_process_fizzbuzz(self):
        eal, mw = create_fizzdpdk_subsystem()
        ctx = ProcessingContext(number=45)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["dpdk_classification"] == "FizzBuzz"

    def test_rss_hash_in_metadata(self):
        eal, mw = create_fizzdpdk_subsystem()
        ctx = ProcessingContext(number=7)
        result = mw.process(ctx, lambda c: c)
        assert "dpdk_rss_hash" in result.metadata

    def test_get_name(self):
        _, mw = create_fizzdpdk_subsystem()
        assert mw.get_name() == "fizzdpdk"

    def test_get_priority(self):
        _, mw = create_fizzdpdk_subsystem()
        assert mw.get_priority() == 248


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    def test_create_subsystem(self):
        eal, mw = create_fizzdpdk_subsystem(num_mbufs=128)
        assert eal.mbuf_pool.num_mbufs == 128
        assert mw.eal is eal
