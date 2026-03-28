"""
Enterprise FizzBuzz Platform - FizzDPDK Data Plane Development Kit

Implements high-performance packet processing with poll-mode drivers,
mbuf pools, ring buffers, flow classification, and Receive Side Scaling
(RSS) hash computation for network-accelerated FizzBuzz delivery.

The Data Plane Development Kit bypasses the kernel networking stack
to achieve line-rate packet processing for FizzBuzz classification
results, enabling millions of packets per second per core:

    DPDKEal
        ├── MbufPool              (pre-allocated packet buffer pool)
        │     ├── Alloc           (zero-copy buffer acquisition)
        │     ├── Free            (buffer return to pool)
        │     └── Stats           (pool utilization tracking)
        ├── RingBuffer            (lockless SPSC/MPMC queue)
        │     ├── Enqueue         (producer-side insertion)
        │     └── Dequeue         (consumer-side extraction)
        ├── EthPort               (Ethernet port abstraction)
        │     ├── RxQueue         (receive queue with RSS)
        │     ├── TxQueue         (transmit queue with offloads)
        │     └── PortStats       (packet/byte counters)
        ├── FlowClassifier        (5-tuple flow rule matching)
        │     ├── AddRule         (install classification rule)
        │     └── Classify        (match packet to rule)
        └── RSSEngine             (Toeplitz hash for queue distribution)

Each FizzBuzz classification result is encapsulated in an Ethernet
frame and transmitted via the DPDK fast path, bypassing all kernel
overhead for maximum throughput.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZDPDK_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 248

DEFAULT_NUM_MBUFS = 8192
DEFAULT_MBUF_SIZE = 2048
DEFAULT_RING_SIZE = 1024
MAX_PORTS = 32
MAX_QUEUES_PER_PORT = 16
MAX_FLOW_RULES = 4096
RSS_KEY_SIZE = 40


# ============================================================================
# Enums
# ============================================================================

class PortState(Enum):
    """Ethernet port operational states."""
    STOPPED = "stopped"
    STARTED = "started"
    CLOSED = "closed"


class RingMode(Enum):
    """Ring buffer producer/consumer modes."""
    SPSC = "single-producer/single-consumer"
    MPMC = "multi-producer/multi-consumer"


class FlowAction(Enum):
    """Flow rule actions."""
    QUEUE = "queue"
    DROP = "drop"
    MARK = "mark"
    RSS = "rss"


class ProtocolType(Enum):
    """Network protocol types for flow classification."""
    ETH = "ethernet"
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    TCP = "tcp"
    UDP = "udp"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class Mbuf:
    """Message buffer (packet buffer)."""
    buf_id: int
    data: bytearray
    data_len: int = 0
    pkt_len: int = 0
    port: int = 0
    queue: int = 0
    rss_hash: int = 0
    timestamp: float = 0.0

    @property
    def is_empty(self) -> bool:
        return self.data_len == 0


@dataclass
class FlowRule:
    """Flow classification rule."""
    rule_id: int
    src_ip: int = 0
    dst_ip: int = 0
    src_port: int = 0
    dst_port: int = 0
    protocol: int = 0
    action: FlowAction = FlowAction.QUEUE
    target_queue: int = 0
    hit_count: int = 0


@dataclass
class PortStats:
    """Ethernet port statistics."""
    rx_packets: int = 0
    tx_packets: int = 0
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_errors: int = 0
    tx_errors: int = 0
    rx_dropped: int = 0


# ============================================================================
# Mbuf Pool
# ============================================================================

class MbufPool:
    """Pre-allocated pool of message buffers.

    Mbuf pools provide O(1) allocation and deallocation of packet
    buffers by pre-allocating all buffers at initialization time.
    This eliminates malloc/free overhead in the packet processing
    fast path.
    """

    def __init__(
        self,
        name: str,
        num_mbufs: int = DEFAULT_NUM_MBUFS,
        mbuf_size: int = DEFAULT_MBUF_SIZE,
    ) -> None:
        self.name = name
        self.num_mbufs = num_mbufs
        self.mbuf_size = mbuf_size
        self._free_list: list[Mbuf] = [
            Mbuf(buf_id=i, data=bytearray(mbuf_size))
            for i in range(num_mbufs)
        ]
        self._allocated = 0

    def alloc(self) -> Mbuf:
        """Allocate an mbuf from the pool."""
        from enterprise_fizzbuzz.domain.exceptions.fizzdpdk import DPDKMbufPoolError

        if not self._free_list:
            raise DPDKMbufPoolError(self.name, "pool exhausted")

        mbuf = self._free_list.pop()
        mbuf.data_len = 0
        mbuf.pkt_len = 0
        mbuf.timestamp = time.monotonic()
        self._allocated += 1
        return mbuf

    def free(self, mbuf: Mbuf) -> None:
        """Return an mbuf to the pool."""
        mbuf.data[:] = b"\x00" * self.mbuf_size
        mbuf.data_len = 0
        mbuf.pkt_len = 0
        self._free_list.append(mbuf)
        self._allocated -= 1

    @property
    def available(self) -> int:
        return len(self._free_list)

    @property
    def allocated(self) -> int:
        return self._allocated

    @property
    def utilization(self) -> float:
        if self.num_mbufs == 0:
            return 0.0
        return self._allocated / self.num_mbufs


# ============================================================================
# Ring Buffer
# ============================================================================

class RingBuffer:
    """Lockless ring buffer for inter-core communication.

    The ring buffer is the fundamental data structure for passing
    packets between processing stages without locks. It uses a
    power-of-2 size and modular arithmetic for wrap-around.
    """

    def __init__(
        self,
        name: str,
        size: int = DEFAULT_RING_SIZE,
        mode: RingMode = RingMode.SPSC,
    ) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzdpdk import DPDKRingError

        # Enforce power-of-2 size
        if size <= 0 or (size & (size - 1)) != 0:
            raise DPDKRingError(name, f"size must be a power of 2 (got {size})")

        self.name = name
        self.size = size
        self.mode = mode
        self._buffer: list[Any] = [None] * size
        self._head = 0
        self._tail = 0
        self._count = 0

    def enqueue(self, item: Any) -> bool:
        """Enqueue an item. Returns True on success, False if full."""
        if self._count >= self.size:
            return False

        self._buffer[self._tail] = item
        self._tail = (self._tail + 1) & (self.size - 1)
        self._count += 1
        return True

    def dequeue(self) -> Optional[Any]:
        """Dequeue an item. Returns None if empty."""
        if self._count == 0:
            return None

        item = self._buffer[self._head]
        self._buffer[self._head] = None
        self._head = (self._head + 1) & (self.size - 1)
        self._count -= 1
        return item

    def enqueue_burst(self, items: list[Any]) -> int:
        """Enqueue multiple items. Returns number enqueued."""
        enqueued = 0
        for item in items:
            if not self.enqueue(item):
                break
            enqueued += 1
        return enqueued

    def dequeue_burst(self, count: int) -> list[Any]:
        """Dequeue up to count items."""
        results = []
        for _ in range(count):
            item = self.dequeue()
            if item is None:
                break
            results.append(item)
        return results

    @property
    def count(self) -> int:
        return self._count

    @property
    def is_full(self) -> bool:
        return self._count >= self.size

    @property
    def is_empty(self) -> bool:
        return self._count == 0

    @property
    def free_count(self) -> int:
        return self.size - self._count


# ============================================================================
# RSS Engine
# ============================================================================

class RSSEngine:
    """Receive Side Scaling hash engine.

    Computes Toeplitz hash values for 5-tuple flow distribution
    across multiple receive queues, ensuring packets from the same
    flow are directed to the same core.
    """

    def __init__(self, key: Optional[bytes] = None, num_queues: int = 4) -> None:
        self._key = key or bytes(range(RSS_KEY_SIZE))
        self._num_queues = num_queues

    def compute_hash(self, src_ip: int, dst_ip: int, src_port: int, dst_port: int, protocol: int) -> int:
        """Compute RSS hash for a 5-tuple."""
        # Simplified Toeplitz-like hash using SHA-256
        input_data = struct.pack(
            ">IIHHB", src_ip, dst_ip, src_port, dst_port, protocol,
        )
        h = hashlib.sha256(self._key + input_data).digest()
        return struct.unpack(">I", h[:4])[0]

    def get_queue(self, rss_hash: int) -> int:
        """Map an RSS hash to a queue index."""
        return rss_hash % self._num_queues

    @property
    def num_queues(self) -> int:
        return self._num_queues


# ============================================================================
# Flow Classifier
# ============================================================================

class FlowClassifier:
    """5-tuple flow classification engine.

    Matches packets against installed flow rules to determine
    the appropriate forwarding action. Rules are matched in
    priority order (lowest rule_id first).
    """

    def __init__(self) -> None:
        self._rules: dict[int, FlowRule] = {}
        self._next_id = 0

    def add_rule(
        self,
        src_ip: int = 0,
        dst_ip: int = 0,
        src_port: int = 0,
        dst_port: int = 0,
        protocol: int = 0,
        action: FlowAction = FlowAction.QUEUE,
        target_queue: int = 0,
    ) -> int:
        """Install a flow classification rule."""
        from enterprise_fizzbuzz.domain.exceptions.fizzdpdk import DPDKFlowError

        if len(self._rules) >= MAX_FLOW_RULES:
            raise DPDKFlowError(self._next_id, "maximum flow rules reached")

        rule = FlowRule(
            rule_id=self._next_id,
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=src_port,
            dst_port=dst_port,
            protocol=protocol,
            action=action,
            target_queue=target_queue,
        )
        self._rules[self._next_id] = rule
        self._next_id += 1
        return rule.rule_id

    def classify(self, src_ip: int, dst_ip: int, src_port: int, dst_port: int, protocol: int) -> Optional[FlowRule]:
        """Classify a packet against installed rules."""
        for rule in sorted(self._rules.values(), key=lambda r: r.rule_id):
            match = True
            if rule.src_ip != 0 and rule.src_ip != src_ip:
                match = False
            if rule.dst_ip != 0 and rule.dst_ip != dst_ip:
                match = False
            if rule.src_port != 0 and rule.src_port != src_port:
                match = False
            if rule.dst_port != 0 and rule.dst_port != dst_port:
                match = False
            if rule.protocol != 0 and rule.protocol != protocol:
                match = False

            if match:
                rule.hit_count += 1
                return rule

        return None

    def delete_rule(self, rule_id: int) -> None:
        """Delete a flow rule."""
        from enterprise_fizzbuzz.domain.exceptions.fizzdpdk import DPDKFlowError
        if rule_id not in self._rules:
            raise DPDKFlowError(rule_id, "rule not found")
        del self._rules[rule_id]

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def get_rule(self, rule_id: int) -> FlowRule:
        from enterprise_fizzbuzz.domain.exceptions.fizzdpdk import DPDKFlowError
        if rule_id not in self._rules:
            raise DPDKFlowError(rule_id, "rule not found")
        return self._rules[rule_id]


# ============================================================================
# Ethernet Port
# ============================================================================

class EthPort:
    """DPDK Ethernet port abstraction.

    Each port represents a physical or virtual network interface
    managed by a DPDK poll-mode driver. Ports support multiple
    receive and transmit queues for parallel processing.
    """

    def __init__(self, port_id: int, num_rx_queues: int = 4, num_tx_queues: int = 4) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzdpdk import DPDKPortError

        if num_rx_queues > MAX_QUEUES_PER_PORT or num_tx_queues > MAX_QUEUES_PER_PORT:
            raise DPDKPortError(port_id, "too many queues")

        self.port_id = port_id
        self.num_rx_queues = num_rx_queues
        self.num_tx_queues = num_tx_queues
        self._state = PortState.STOPPED
        self._stats = PortStats()
        self._rx_rings: list[RingBuffer] = [
            RingBuffer(f"port{port_id}_rx{i}", DEFAULT_RING_SIZE)
            for i in range(num_rx_queues)
        ]
        self._tx_rings: list[RingBuffer] = [
            RingBuffer(f"port{port_id}_tx{i}", DEFAULT_RING_SIZE)
            for i in range(num_tx_queues)
        ]

    def start(self) -> None:
        """Start the port."""
        self._state = PortState.STARTED

    def stop(self) -> None:
        """Stop the port."""
        self._state = PortState.STOPPED

    def rx_burst(self, queue_id: int, max_pkts: int) -> list[Mbuf]:
        """Receive a burst of packets from a queue."""
        from enterprise_fizzbuzz.domain.exceptions.fizzdpdk import DPDKRxError

        if self._state != PortState.STARTED:
            raise DPDKRxError(self.port_id, queue_id, "port not started")
        if queue_id >= self.num_rx_queues:
            raise DPDKRxError(self.port_id, queue_id, "invalid queue ID")

        pkts = self._rx_rings[queue_id].dequeue_burst(max_pkts)
        self._stats.rx_packets += len(pkts)
        for pkt in pkts:
            self._stats.rx_bytes += pkt.pkt_len
        return pkts

    def tx_burst(self, queue_id: int, pkts: list[Mbuf]) -> int:
        """Transmit a burst of packets on a queue."""
        from enterprise_fizzbuzz.domain.exceptions.fizzdpdk import DPDKTxError

        if self._state != PortState.STARTED:
            raise DPDKTxError(self.port_id, queue_id, "port not started")
        if queue_id >= self.num_tx_queues:
            raise DPDKTxError(self.port_id, queue_id, "invalid queue ID")

        sent = self._tx_rings[queue_id].enqueue_burst(pkts)
        self._stats.tx_packets += sent
        for i in range(sent):
            self._stats.tx_bytes += pkts[i].pkt_len
        return sent

    def inject_rx(self, queue_id: int, mbuf: Mbuf) -> bool:
        """Inject a packet into an RX queue (for testing/simulation)."""
        if queue_id >= self.num_rx_queues:
            return False
        return self._rx_rings[queue_id].enqueue(mbuf)

    @property
    def state(self) -> PortState:
        return self._state

    @property
    def stats(self) -> PortStats:
        return self._stats


# ============================================================================
# DPDK EAL (Environment Abstraction Layer)
# ============================================================================

class DPDKEal:
    """DPDK Environment Abstraction Layer.

    The EAL initializes the DPDK runtime, manages hugepage memory,
    creates mbuf pools, and provides port discovery and configuration.
    """

    def __init__(self, num_mbufs: int = DEFAULT_NUM_MBUFS) -> None:
        self.mbuf_pool = MbufPool("default_pool", num_mbufs)
        self.rss_engine = RSSEngine()
        self.flow_classifier = FlowClassifier()
        self._ports: dict[int, EthPort] = {}

    def create_port(
        self,
        port_id: int,
        num_rx_queues: int = 4,
        num_tx_queues: int = 4,
    ) -> EthPort:
        """Create and configure an Ethernet port."""
        from enterprise_fizzbuzz.domain.exceptions.fizzdpdk import DPDKPortError

        if port_id in self._ports:
            raise DPDKPortError(port_id, "port already exists")
        if len(self._ports) >= MAX_PORTS:
            raise DPDKPortError(port_id, "maximum ports reached")

        port = EthPort(port_id, num_rx_queues, num_tx_queues)
        self._ports[port_id] = port
        return port

    def get_port(self, port_id: int) -> EthPort:
        from enterprise_fizzbuzz.domain.exceptions.fizzdpdk import DPDKPortError
        if port_id not in self._ports:
            raise DPDKPortError(port_id, "port not found")
        return self._ports[port_id]

    @property
    def port_count(self) -> int:
        return len(self._ports)

    def get_stats(self) -> dict:
        return {
            "version": FIZZDPDK_VERSION,
            "ports": self.port_count,
            "mbufs_total": self.mbuf_pool.num_mbufs,
            "mbufs_available": self.mbuf_pool.available,
            "mbufs_allocated": self.mbuf_pool.allocated,
            "pool_utilization": f"{self.mbuf_pool.utilization:.1%}",
            "flow_rules": self.flow_classifier.rule_count,
            "rss_queues": self.rss_engine.num_queues,
        }


# ============================================================================
# Dashboard
# ============================================================================

class DPDKDashboard:
    """ASCII dashboard for DPDK EAL visualization."""

    @staticmethod
    def render(eal: DPDKEal, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzDPDK Data Plane Development Kit Dashboard".center(width))
        lines.append(border)

        stats = eal.get_stats()
        lines.append(f"  Version: {stats['version']}")
        lines.append(f"  Ports: {stats['ports']}")
        lines.append(f"  Mbufs total: {stats['mbufs_total']}")
        lines.append(f"  Mbufs available: {stats['mbufs_available']}")
        lines.append(f"  Mbufs allocated: {stats['mbufs_allocated']}")
        lines.append(f"  Pool utilization: {stats['pool_utilization']}")
        lines.append(f"  Flow rules: {stats['flow_rules']}")
        lines.append(f"  RSS queues: {stats['rss_queues']}")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class DPDKMiddleware(IMiddleware):
    """Middleware that encapsulates FizzBuzz results as DPDK packets.

    Each classification result is packaged as an mbuf and queued for
    transmission via the DPDK fast path, bypassing kernel networking
    overhead.
    """

    def __init__(self, eal: DPDKEal) -> None:
        self.eal = eal
        self.evaluations = 0

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        number = context.number
        self.evaluations += 1

        if number % 15 == 0:
            label = "FizzBuzz"
        elif number % 3 == 0:
            label = "Fizz"
        elif number % 5 == 0:
            label = "Buzz"
        else:
            label = str(number)

        rss_hash = self.eal.rss_engine.compute_hash(
            src_ip=number, dst_ip=0, src_port=0, dst_port=0, protocol=6,
        )

        context.metadata["dpdk_classification"] = label
        context.metadata["dpdk_rss_hash"] = rss_hash
        context.metadata["dpdk_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzdpdk"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzdpdk_subsystem(
    num_mbufs: int = DEFAULT_NUM_MBUFS,
) -> tuple[DPDKEal, DPDKMiddleware]:
    """Create and configure the complete FizzDPDK subsystem.

    Args:
        num_mbufs: Number of mbufs in the default pool.

    Returns:
        Tuple of (DPDKEal, DPDKMiddleware).
    """
    eal = DPDKEal(num_mbufs=num_mbufs)
    middleware = DPDKMiddleware(eal)

    logger.info(
        "FizzDPDK subsystem initialized: %d mbufs",
        num_mbufs,
    )

    return eal, middleware
