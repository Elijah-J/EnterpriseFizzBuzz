"""
Enterprise FizzBuzz Platform - FizzRDMA Remote DMA Engine

Implements Remote Direct Memory Access for zero-copy FizzBuzz result
transfer between nodes. Traditional network stacks involve multiple
memory copies — from application buffer to kernel buffer, to NIC DMA
buffer, across the wire, and back up the receiving stack. RDMA bypasses
the kernel entirely, allowing one node to read from or write to another
node's memory without involving either CPU in the data path.

For FizzBuzz evaluation at scale, this eliminates the overhead of
serializing classification results into network packets: the evaluating
node writes "Fizz", "Buzz", or "FizzBuzz" directly into the requesting
node's pre-registered memory region.

Architecture:

    RDMAContext
        ├── ProtectionDomain      (access control boundary)
        │     ├── MemoryRegion    (registered buffer with lkey/rkey)
        │     └── QueuePair       (send/recv work queue pair)
        ├── CompletionQueue       (work completion notifications)
        │     ├── Poll            (non-blocking CQ drain)
        │     └── CompletionEntry (status, opcode, bytes transferred)
        ├── RDMAOperations        (verb layer)
        │     ├── Send            (channel semantics)
        │     ├── Recv            (pre-posted receive buffers)
        │     ├── Read            (one-sided remote read)
        │     └── Write           (one-sided remote write)
        └── RDMADashboard         (ASCII connection status)

Queue pairs follow the IB Verbs state machine:
    RESET → INIT → RTR (Ready to Receive) → RTS (Ready to Send)
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZRDMA_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 252

MAX_MEMORY_REGIONS = 1024
MAX_QUEUE_PAIRS = 256
MAX_CQ_ENTRIES = 4096
DEFAULT_SEND_QUEUE_DEPTH = 128
DEFAULT_RECV_QUEUE_DEPTH = 128
MAX_SGE = 8


# ============================================================================
# Enums
# ============================================================================

class QPState(Enum):
    """Queue pair state machine states per IB Verbs specification."""
    RESET = "RESET"
    INIT = "INIT"
    RTR = "RTR"   # Ready to Receive
    RTS = "RTS"   # Ready to Send
    ERROR = "ERROR"


class RDMAOpcode(Enum):
    """RDMA operation types."""
    SEND = "send"
    RECV = "recv"
    READ = "read"
    WRITE = "write"
    SEND_WITH_IMM = "send_with_imm"


class CompletionStatus(Enum):
    """Work completion status codes."""
    SUCCESS = "success"
    LOCAL_LENGTH_ERROR = "local_length_error"
    LOCAL_QP_ERROR = "local_qp_error"
    REMOTE_ACCESS_ERROR = "remote_access_error"
    REMOTE_INVALID_REQUEST = "remote_invalid_request"
    FLUSH_ERROR = "flush_error"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class MemoryRegion:
    """A registered memory region for RDMA operations.

    Memory regions must be registered with the RDMA device before they
    can be used for zero-copy transfers. Registration pins the pages
    in physical memory and produces local/remote keys (lkey/rkey) used
    for access control.
    """
    mr_id: int
    address: int
    length: int
    lkey: int
    rkey: int
    pd_handle: int
    data: bytearray = field(default_factory=lambda: bytearray(256))

    def read(self, offset: int, length: int) -> bytes:
        end = min(offset + length, len(self.data))
        return bytes(self.data[offset:end])

    def write(self, offset: int, data: bytes) -> int:
        end = min(offset + len(data), len(self.data))
        written = end - offset
        self.data[offset:end] = data[:written]
        return written


@dataclass
class CompletionEntry:
    """A single work completion notification from the CQ."""
    wr_id: int
    status: CompletionStatus
    opcode: RDMAOpcode
    byte_len: int = 0
    qp_num: int = 0
    timestamp: float = 0.0


@dataclass
class WorkRequest:
    """A work request posted to a queue pair."""
    wr_id: int
    opcode: RDMAOpcode
    local_addr: int = 0
    local_lkey: int = 0
    remote_addr: int = 0
    remote_rkey: int = 0
    length: int = 0
    data: bytes = b""


# ============================================================================
# Protection Domain
# ============================================================================

class ProtectionDomain:
    """An RDMA protection domain that scopes memory regions and QPs.

    All memory regions and queue pairs must belong to a protection
    domain. Cross-domain access is prohibited, providing isolation
    between unrelated FizzBuzz evaluation sessions.
    """

    _next_handle = 1

    def __init__(self) -> None:
        self.handle = ProtectionDomain._next_handle
        ProtectionDomain._next_handle += 1
        self._memory_regions: dict[int, MemoryRegion] = {}
        self._next_mr_id = 1
        self._next_key = 1000

    def register_memory(self, address: int, length: int) -> MemoryRegion:
        """Register a memory region within this protection domain."""
        mr_id = self._next_mr_id
        self._next_mr_id += 1
        lkey = self._next_key
        rkey = self._next_key + 1
        self._next_key += 2

        mr = MemoryRegion(
            mr_id=mr_id,
            address=address,
            length=length,
            lkey=lkey,
            rkey=rkey,
            pd_handle=self.handle,
            data=bytearray(length),
        )
        self._memory_regions[mr_id] = mr
        return mr

    def deregister_memory(self, mr_id: int) -> bool:
        return self._memory_regions.pop(mr_id, None) is not None

    def get_mr(self, mr_id: int) -> Optional[MemoryRegion]:
        return self._memory_regions.get(mr_id)

    def find_mr_by_rkey(self, rkey: int) -> Optional[MemoryRegion]:
        for mr in self._memory_regions.values():
            if mr.rkey == rkey:
                return mr
        return None

    @property
    def mr_count(self) -> int:
        return len(self._memory_regions)


# ============================================================================
# Completion Queue
# ============================================================================

class CompletionQueue:
    """Completion queue for RDMA work request notifications.

    When an RDMA operation completes — whether successfully or with
    an error — a completion entry is posted to the CQ. Consumers
    poll the CQ to discover completed operations.
    """

    def __init__(self, max_entries: int = MAX_CQ_ENTRIES) -> None:
        self.max_entries = max_entries
        self._entries: list[CompletionEntry] = []
        self._total_completions = 0

    def post_completion(self, entry: CompletionEntry) -> bool:
        if len(self._entries) >= self.max_entries:
            return False
        entry.timestamp = time.time()
        self._entries.append(entry)
        self._total_completions += 1
        return True

    def poll(self, max_entries: int = 1) -> list[CompletionEntry]:
        """Poll the CQ for completed work requests (non-blocking)."""
        count = min(max_entries, len(self._entries))
        results = self._entries[:count]
        self._entries = self._entries[count:]
        return results

    @property
    def depth(self) -> int:
        return len(self._entries)

    @property
    def total_completions(self) -> int:
        return self._total_completions


# ============================================================================
# Queue Pair
# ============================================================================

class QueuePair:
    """An RDMA queue pair consisting of a send queue and receive queue.

    The QP follows the IB Verbs state machine:
    RESET → INIT → RTR → RTS. Operations can only be posted when
    the QP is in the appropriate state (sends require RTS, receives
    require RTR or RTS).
    """

    _next_qpn = 1

    def __init__(self, pd: ProtectionDomain, send_cq: CompletionQueue,
                 recv_cq: CompletionQueue) -> None:
        self.qp_num = QueuePair._next_qpn
        QueuePair._next_qpn += 1
        self.pd = pd
        self.send_cq = send_cq
        self.recv_cq = recv_cq
        self.state = QPState.RESET
        self._send_queue: list[WorkRequest] = []
        self._recv_queue: list[WorkRequest] = []
        self._next_wr_id = 1
        self._total_sends = 0
        self._total_recvs = 0

    def modify_to_init(self) -> bool:
        if self.state != QPState.RESET:
            return False
        self.state = QPState.INIT
        return True

    def modify_to_rtr(self) -> bool:
        if self.state != QPState.INIT:
            return False
        self.state = QPState.RTR
        return True

    def modify_to_rts(self) -> bool:
        if self.state != QPState.RTR:
            return False
        self.state = QPState.RTS
        return True

    def post_send(self, wr: WorkRequest) -> bool:
        """Post a send work request. Requires RTS state."""
        if self.state != QPState.RTS:
            return False
        wr.wr_id = self._next_wr_id
        self._next_wr_id += 1
        self._send_queue.append(wr)
        self._total_sends += 1

        # Immediate completion for simulation
        self.send_cq.post_completion(CompletionEntry(
            wr_id=wr.wr_id,
            status=CompletionStatus.SUCCESS,
            opcode=wr.opcode,
            byte_len=wr.length,
            qp_num=self.qp_num,
        ))
        return True

    def post_recv(self, wr: WorkRequest) -> bool:
        """Post a receive work request. Requires RTR or RTS state."""
        if self.state not in (QPState.RTR, QPState.RTS):
            return False
        wr.wr_id = self._next_wr_id
        self._next_wr_id += 1
        self._recv_queue.append(wr)
        self._total_recvs += 1
        return True

    @property
    def send_depth(self) -> int:
        return len(self._send_queue)

    @property
    def recv_depth(self) -> int:
        return len(self._recv_queue)

    @property
    def total_sends(self) -> int:
        return self._total_sends


# ============================================================================
# RDMA Context
# ============================================================================

class RDMAContext:
    """Top-level RDMA context managing protection domains, QPs, and CQs.

    The RDMAContext is the entry point for all RDMA operations. It
    manages the lifecycle of protection domains, queue pairs, and
    completion queues, and provides high-level verbs for send, recv,
    read, and write operations.
    """

    def __init__(self) -> None:
        self._pds: list[ProtectionDomain] = []
        self._cqs: list[CompletionQueue] = []
        self._qps: list[QueuePair] = []
        self._evaluations = 0

    def create_pd(self) -> ProtectionDomain:
        pd = ProtectionDomain()
        self._pds.append(pd)
        return pd

    def create_cq(self, max_entries: int = MAX_CQ_ENTRIES) -> CompletionQueue:
        cq = CompletionQueue(max_entries)
        self._cqs.append(cq)
        return cq

    def create_qp(self, pd: ProtectionDomain, send_cq: CompletionQueue,
                   recv_cq: CompletionQueue) -> QueuePair:
        qp = QueuePair(pd, send_cq, recv_cq)
        self._qps.append(qp)
        return qp

    def rdma_write(self, qp: QueuePair, local_mr: MemoryRegion,
                    local_offset: int, remote_mr: MemoryRegion,
                    remote_offset: int, length: int) -> bool:
        """Perform an RDMA write (one-sided) from local to remote MR."""
        data = local_mr.read(local_offset, length)
        remote_mr.write(remote_offset, data)

        wr = WorkRequest(
            wr_id=0,
            opcode=RDMAOpcode.WRITE,
            local_addr=local_mr.address + local_offset,
            local_lkey=local_mr.lkey,
            remote_addr=remote_mr.address + remote_offset,
            remote_rkey=remote_mr.rkey,
            length=length,
        )
        return qp.post_send(wr)

    def rdma_read(self, qp: QueuePair, local_mr: MemoryRegion,
                   local_offset: int, remote_mr: MemoryRegion,
                   remote_offset: int, length: int) -> bool:
        """Perform an RDMA read (one-sided) from remote to local MR."""
        data = remote_mr.read(remote_offset, length)
        local_mr.write(local_offset, data)

        wr = WorkRequest(
            wr_id=0,
            opcode=RDMAOpcode.READ,
            local_addr=local_mr.address + local_offset,
            local_lkey=local_mr.lkey,
            remote_addr=remote_mr.address + remote_offset,
            remote_rkey=remote_mr.rkey,
            length=length,
        )
        return qp.post_send(wr)

    def rdma_send(self, qp: QueuePair, data: bytes) -> bool:
        """Perform an RDMA send (channel semantics)."""
        wr = WorkRequest(
            wr_id=0,
            opcode=RDMAOpcode.SEND,
            length=len(data),
            data=data,
        )
        return qp.post_send(wr)

    def evaluate_fizzbuzz(self, number: int) -> str:
        """Evaluate FizzBuzz via RDMA zero-copy result transfer."""
        if number % 15 == 0:
            result = "FizzBuzz"
        elif number % 3 == 0:
            result = "Fizz"
        elif number % 5 == 0:
            result = "Buzz"
        else:
            result = str(number)

        self._evaluations += 1
        return result

    @property
    def total_evaluations(self) -> int:
        return self._evaluations

    @property
    def pd_count(self) -> int:
        return len(self._pds)

    @property
    def qp_count(self) -> int:
        return len(self._qps)

    @property
    def cq_count(self) -> int:
        return len(self._cqs)


# ============================================================================
# Dashboard
# ============================================================================

class RDMADashboard:
    """ASCII dashboard for RDMA subsystem status."""

    @staticmethod
    def render(ctx: RDMAContext, width: int = 72) -> str:
        border = "+" + "-" * (width - 2) + "+"
        title = "| FizzRDMA Engine Status".ljust(width - 1) + "|"

        lines = [border, title, border]
        lines.append(f"| {'Version:':<20} {FIZZRDMA_VERSION:<{width-24}} |")
        lines.append(f"| {'Protection Domains:':<20} {ctx.pd_count:<{width-24}} |")
        lines.append(f"| {'Queue Pairs:':<20} {ctx.qp_count:<{width-24}} |")
        lines.append(f"| {'Completion Queues:':<20} {ctx.cq_count:<{width-24}} |")
        lines.append(f"| {'Evaluations:':<20} {ctx.total_evaluations:<{width-24}} |")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class RDMAMiddleware(IMiddleware):
    """Pipeline middleware that evaluates FizzBuzz via RDMA."""

    def __init__(self, ctx: RDMAContext) -> None:
        self.ctx = ctx

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        number = context.number
        result = self.ctx.evaluate_fizzbuzz(number)

        context.metadata["rdma_classification"] = result
        context.metadata["rdma_qp_count"] = self.ctx.qp_count
        context.metadata["rdma_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzrdma"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzrdma_subsystem() -> tuple[RDMAContext, RDMAMiddleware]:
    """Create and configure the complete FizzRDMA subsystem.

    Returns:
        Tuple of (RDMAContext, RDMAMiddleware).
    """
    ctx = RDMAContext()
    middleware = RDMAMiddleware(ctx)

    logger.info("FizzRDMA subsystem initialized")

    return ctx, middleware
