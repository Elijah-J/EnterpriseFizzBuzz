"""
Enterprise FizzBuzz Platform - FizzRDMA Remote DMA Engine Test Suite

Comprehensive tests for the RDMA engine, covering protection domains,
memory region registration, queue pair state machine transitions,
completion queue operations, RDMA verbs (send, recv, read, write),
FizzBuzz evaluation via zero-copy transfer, dashboard rendering,
and middleware integration.

The FizzRDMA subsystem enables zero-copy FizzBuzz result transfer
between nodes, bypassing the kernel networking stack entirely. These
tests verify correct IB Verbs semantics, QP state transitions, and
end-to-end data transfer correctness.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzrdma import (
    FIZZRDMA_VERSION,
    MAX_CQ_ENTRIES,
    MAX_MEMORY_REGIONS,
    MAX_QUEUE_PAIRS,
    MIDDLEWARE_PRIORITY,
    CompletionEntry,
    CompletionQueue,
    CompletionStatus,
    MemoryRegion,
    ProtectionDomain,
    QPState,
    QueuePair,
    RDMAContext,
    RDMADashboard,
    RDMAMiddleware,
    RDMAOpcode,
    WorkRequest,
    create_fizzrdma_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    RDMAError,
    RDMAMemoryRegionError,
    RDMAProtectionDomainError,
    RDMAQueuePairError,
    RDMACompletionError,
    RDMASendError,
    RDMAReadError,
    RDMAWriteError,
)


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Verify RDMA constants match documented specifications."""

    def test_version(self):
        assert FIZZRDMA_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 252

    def test_max_cq_entries(self):
        assert MAX_CQ_ENTRIES == 4096


# =========================================================================
# Protection Domain
# =========================================================================


class TestProtectionDomain:
    """Verify protection domain memory region management."""

    def test_register_memory(self):
        pd = ProtectionDomain()
        mr = pd.register_memory(0x1000, 256)
        assert mr.mr_id >= 1
        assert mr.pd_handle == pd.handle

    def test_deregister_memory(self):
        pd = ProtectionDomain()
        mr = pd.register_memory(0x1000, 256)
        assert pd.deregister_memory(mr.mr_id) is True
        assert pd.mr_count == 0

    def test_find_mr_by_rkey(self):
        pd = ProtectionDomain()
        mr = pd.register_memory(0x1000, 256)
        found = pd.find_mr_by_rkey(mr.rkey)
        assert found is not None
        assert found.mr_id == mr.mr_id

    def test_mr_count(self):
        pd = ProtectionDomain()
        pd.register_memory(0x1000, 256)
        pd.register_memory(0x2000, 512)
        assert pd.mr_count == 2


# =========================================================================
# Memory Region
# =========================================================================


class TestMemoryRegion:
    """Verify memory region read/write operations."""

    def test_write_and_read(self):
        mr = MemoryRegion(mr_id=1, address=0, length=256,
                          lkey=100, rkey=101, pd_handle=1,
                          data=bytearray(256))
        mr.write(0, b"FizzBuzz")
        assert mr.read(0, 8) == b"FizzBuzz"

    def test_write_returns_bytes_written(self):
        mr = MemoryRegion(mr_id=1, address=0, length=4,
                          lkey=100, rkey=101, pd_handle=1,
                          data=bytearray(4))
        written = mr.write(0, b"Hello World")
        assert written == 4  # Truncated to region size


# =========================================================================
# Completion Queue
# =========================================================================


class TestCompletionQueue:
    """Verify completion queue post and poll operations."""

    def test_post_and_poll(self):
        cq = CompletionQueue()
        entry = CompletionEntry(wr_id=1, status=CompletionStatus.SUCCESS,
                                opcode=RDMAOpcode.SEND)
        assert cq.post_completion(entry) is True
        results = cq.poll(1)
        assert len(results) == 1
        assert results[0].wr_id == 1

    def test_poll_empty(self):
        cq = CompletionQueue()
        assert cq.poll(1) == []

    def test_total_completions(self):
        cq = CompletionQueue()
        for i in range(5):
            cq.post_completion(CompletionEntry(wr_id=i,
                               status=CompletionStatus.SUCCESS,
                               opcode=RDMAOpcode.SEND))
        assert cq.total_completions == 5


# =========================================================================
# Queue Pair
# =========================================================================


class TestQueuePair:
    """Verify QP state machine transitions and work posting."""

    def test_initial_state_reset(self):
        pd = ProtectionDomain()
        cq = CompletionQueue()
        qp = QueuePair(pd, cq, cq)
        assert qp.state == QPState.RESET

    def test_state_transitions(self):
        pd = ProtectionDomain()
        cq = CompletionQueue()
        qp = QueuePair(pd, cq, cq)
        assert qp.modify_to_init() is True
        assert qp.state == QPState.INIT
        assert qp.modify_to_rtr() is True
        assert qp.state == QPState.RTR
        assert qp.modify_to_rts() is True
        assert qp.state == QPState.RTS

    def test_invalid_transition(self):
        pd = ProtectionDomain()
        cq = CompletionQueue()
        qp = QueuePair(pd, cq, cq)
        assert qp.modify_to_rtr() is False  # Must go through INIT

    def test_post_send_requires_rts(self):
        pd = ProtectionDomain()
        cq = CompletionQueue()
        qp = QueuePair(pd, cq, cq)
        wr = WorkRequest(wr_id=0, opcode=RDMAOpcode.SEND, length=10)
        assert qp.post_send(wr) is False

    def test_post_send_in_rts(self):
        pd = ProtectionDomain()
        cq = CompletionQueue()
        qp = QueuePair(pd, cq, cq)
        qp.modify_to_init()
        qp.modify_to_rtr()
        qp.modify_to_rts()
        wr = WorkRequest(wr_id=0, opcode=RDMAOpcode.SEND, length=10)
        assert qp.post_send(wr) is True
        assert qp.total_sends == 1

    def test_post_recv_in_rtr(self):
        pd = ProtectionDomain()
        cq = CompletionQueue()
        qp = QueuePair(pd, cq, cq)
        qp.modify_to_init()
        qp.modify_to_rtr()
        wr = WorkRequest(wr_id=0, opcode=RDMAOpcode.RECV, length=10)
        assert qp.post_recv(wr) is True


# =========================================================================
# RDMA Context
# =========================================================================


class TestRDMAContext:
    """Verify top-level RDMA context operations."""

    def test_create_pd(self):
        ctx = RDMAContext()
        pd = ctx.create_pd()
        assert ctx.pd_count == 1

    def test_create_qp(self):
        ctx = RDMAContext()
        pd = ctx.create_pd()
        cq = ctx.create_cq()
        qp = ctx.create_qp(pd, cq, cq)
        assert ctx.qp_count == 1

    def test_rdma_write(self):
        ctx = RDMAContext()
        pd = ctx.create_pd()
        cq = ctx.create_cq()
        qp = ctx.create_qp(pd, cq, cq)
        qp.modify_to_init()
        qp.modify_to_rtr()
        qp.modify_to_rts()

        local_mr = pd.register_memory(0x0, 64)
        remote_mr = pd.register_memory(0x1000, 64)
        local_mr.write(0, b"Fizz")

        assert ctx.rdma_write(qp, local_mr, 0, remote_mr, 0, 4) is True
        assert remote_mr.read(0, 4) == b"Fizz"

    def test_rdma_read(self):
        ctx = RDMAContext()
        pd = ctx.create_pd()
        cq = ctx.create_cq()
        qp = ctx.create_qp(pd, cq, cq)
        qp.modify_to_init()
        qp.modify_to_rtr()
        qp.modify_to_rts()

        local_mr = pd.register_memory(0x0, 64)
        remote_mr = pd.register_memory(0x1000, 64)
        remote_mr.write(0, b"Buzz")

        assert ctx.rdma_read(qp, local_mr, 0, remote_mr, 0, 4) is True
        assert local_mr.read(0, 4) == b"Buzz"

    def test_evaluate_fizzbuzz(self):
        ctx = RDMAContext()
        assert ctx.evaluate_fizzbuzz(15) == "FizzBuzz"
        assert ctx.evaluate_fizzbuzz(7) == "7"
        assert ctx.total_evaluations == 2


# =========================================================================
# Dashboard
# =========================================================================


class TestRDMADashboard:
    """Verify ASCII dashboard rendering."""

    def test_render_produces_output(self):
        ctx = RDMAContext()
        output = RDMADashboard.render(ctx)
        assert "FizzRDMA" in output
        assert FIZZRDMA_VERSION in output


# =========================================================================
# Middleware
# =========================================================================


class TestRDMAMiddleware:
    """Verify pipeline middleware integration."""

    def test_middleware_sets_metadata(self):
        ctx = RDMAContext()
        mw = RDMAMiddleware(ctx)

        @dataclass
        class Ctx:
            number: int
            session_id: str = "test"
            metadata: dict = None
            def __post_init__(self):
                if self.metadata is None:
                    self.metadata = {}

        c = Ctx(number=3)
        result = mw.process(c, lambda c: c)
        assert result.metadata["rdma_classification"] == "Fizz"
        assert result.metadata["rdma_enabled"] is True

    def test_middleware_name(self):
        ctx = RDMAContext()
        mw = RDMAMiddleware(ctx)
        assert mw.get_name() == "fizzrdma"

    def test_middleware_priority(self):
        ctx = RDMAContext()
        mw = RDMAMiddleware(ctx)
        assert mw.get_priority() == 252


# =========================================================================
# Factory
# =========================================================================


class TestFactory:
    """Verify subsystem factory function."""

    def test_create_subsystem(self):
        ctx, mw = create_fizzrdma_subsystem()
        assert isinstance(ctx, RDMAContext)
        assert isinstance(mw, RDMAMiddleware)


# =========================================================================
# Exceptions
# =========================================================================


class TestExceptions:
    """Verify RDMA exception hierarchy."""

    def test_rdma_error_base(self):
        err = RDMAError("test")
        assert "test" in str(err)

    def test_rdma_qp_error(self):
        err = RDMAQueuePairError(42, "invalid transition")
        assert err.qp_num == 42

    def test_rdma_write_error(self):
        err = RDMAWriteError(0x1000, 100, "access denied")
        assert err.remote_addr == 0x1000
        assert err.rkey == 100
