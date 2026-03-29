"""
Tests for the FizzBuzz Operating System Kernel.

Validates process management, scheduling algorithms, virtual memory,
interrupt handling, system calls, and the kernel lifecycle -- all in
service of computing n % 3 and n % 5 with maximum ceremony.
"""

from __future__ import annotations

import pytest
import time

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    ProcessPriority,
    ProcessState,
    RuleDefinition,
    SchedulerAlgorithm,
)
from enterprise_fizzbuzz.domain.exceptions import (
    InterruptConflictError,
    InvalidProcessStateError,
    KernelPanicError,
    PageFaultError,
    SchedulerStarvationError,
)
from enterprise_fizzbuzz.infrastructure.os_kernel import (
    CompletelyFairScheduler,
    FizzBuzzKernel,
    FizzProcess,
    InterruptController,
    KernelDashboard,
    KernelMiddleware,
    PriorityPreemptiveScheduler,
    RegisterFile,
    RoundRobinScheduler,
    SyscallInterface,
    TLBEntry,
    VirtualMemoryManager,
)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def standard_rules() -> list[RuleDefinition]:
    """Standard FizzBuzz rules."""
    return [
        RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
        RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
    ]


@pytest.fixture
def kernel(standard_rules) -> FizzBuzzKernel:
    """A booted kernel with standard rules."""
    k = FizzBuzzKernel(
        rules=standard_rules,
        scheduler_type=SchedulerAlgorithm.ROUND_ROBIN,
        time_quantum_ms=10.0,
        boot_delay_ms=0.0,
        context_switch_overhead_us=0.0,
    )
    k.boot()
    return k


@pytest.fixture
def priority_kernel(standard_rules) -> FizzBuzzKernel:
    """A booted kernel with priority preemptive scheduling."""
    k = FizzBuzzKernel(
        rules=standard_rules,
        scheduler_type=SchedulerAlgorithm.PRIORITY_PREEMPTIVE,
        boot_delay_ms=0.0,
        context_switch_overhead_us=0.0,
    )
    k.boot()
    return k


@pytest.fixture
def cfs_kernel(standard_rules) -> FizzBuzzKernel:
    """A booted kernel with CFS scheduling."""
    k = FizzBuzzKernel(
        rules=standard_rules,
        scheduler_type=SchedulerAlgorithm.COMPLETELY_FAIR,
        boot_delay_ms=0.0,
        context_switch_overhead_us=0.0,
    )
    k.boot()
    return k


# ── RegisterFile Tests ──────────────────────────────────────────────


class TestRegisterFile:
    """Tests for the simulated CPU register file."""

    def test_default_registers_are_zero(self):
        rf = RegisterFile()
        assert rf.r0 == 0
        assert rf.pc == 0
        assert rf.sp == 0
        assert rf.flags == 0

    def test_snapshot_and_restore(self):
        rf = RegisterFile()
        rf.r0 = 42
        rf.pc = 100
        rf.sp = 0xFF00
        rf.flags = 0b101

        snap = rf.snapshot()
        assert snap["r0"] == 42
        assert snap["pc"] == 100

        # Restore into a fresh register file
        rf2 = RegisterFile()
        rf2.restore(snap)
        assert rf2.r0 == 42
        assert rf2.pc == 100
        assert rf2.sp == 0xFF00
        assert rf2.flags == 0b101

    def test_snapshot_keys(self):
        rf = RegisterFile()
        snap = rf.snapshot()
        expected_keys = {"r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
                         "pc", "sp", "flags", "ir"}
        assert set(snap.keys()) == expected_keys


# ── FizzProcess Tests ───────────────────────────────────────────────


class TestFizzProcess:
    """Tests for the Process Control Block."""

    def test_create_process(self):
        proc = FizzProcess(pid=1, number=15)
        assert proc.pid == 1
        assert proc.number == 15
        assert proc.state == ProcessState.READY
        assert proc.exit_code == -1
        assert proc.result is None

    def test_auto_priority_fizzbuzz(self):
        assert FizzProcess.auto_priority(15) == ProcessPriority.REALTIME
        assert FizzProcess.auto_priority(30) == ProcessPriority.REALTIME
        assert FizzProcess.auto_priority(45) == ProcessPriority.REALTIME

    def test_auto_priority_fizz(self):
        assert FizzProcess.auto_priority(3) == ProcessPriority.HIGH
        assert FizzProcess.auto_priority(9) == ProcessPriority.HIGH

    def test_auto_priority_buzz(self):
        assert FizzProcess.auto_priority(5) == ProcessPriority.HIGH
        assert FizzProcess.auto_priority(10) == ProcessPriority.HIGH

    def test_auto_priority_prime(self):
        assert FizzProcess.auto_priority(7) == ProcessPriority.LOW
        assert FizzProcess.auto_priority(11) == ProcessPriority.LOW
        assert FizzProcess.auto_priority(97) == ProcessPriority.LOW

    def test_auto_priority_normal(self):
        assert FizzProcess.auto_priority(4) == ProcessPriority.NORMAL
        assert FizzProcess.auto_priority(8) == ProcessPriority.NORMAL

    def test_valid_state_transitions(self):
        proc = FizzProcess(pid=1, number=42)
        assert proc.state == ProcessState.READY

        proc.transition_to(ProcessState.RUNNING)
        assert proc.state == ProcessState.RUNNING

        proc.transition_to(ProcessState.ZOMBIE)
        assert proc.state == ProcessState.ZOMBIE

        proc.transition_to(ProcessState.TERMINATED)
        assert proc.state == ProcessState.TERMINATED
        assert proc.terminated_at is not None

    def test_invalid_state_transition(self):
        proc = FizzProcess(pid=1, number=42)
        proc.transition_to(ProcessState.RUNNING)
        proc.transition_to(ProcessState.TERMINATED)

        with pytest.raises(InvalidProcessStateError):
            proc.transition_to(ProcessState.RUNNING)

    def test_blocked_to_ready(self):
        proc = FizzProcess(pid=1, number=42)
        proc.transition_to(ProcessState.RUNNING)
        proc.transition_to(ProcessState.BLOCKED)
        assert proc.state == ProcessState.BLOCKED

        proc.transition_to(ProcessState.READY)
        assert proc.state == ProcessState.READY

    def test_save_restore_context(self):
        proc = FizzProcess(pid=1, number=42)
        proc.registers.r0 = 42
        proc.registers.pc = 10

        proc.save_context()
        assert proc._saved_registers is not None

        proc.registers.r0 = 0
        proc.registers.pc = 0

        proc.restore_context()
        assert proc.registers.r0 == 42
        assert proc.registers.pc == 10

    def test_process_priority_one(self):
        """Number 1 is neither prime (by convention) nor divisible by 3 or 5."""
        assert FizzProcess.auto_priority(1) == ProcessPriority.NORMAL


# ── VirtualMemoryManager Tests ──────────────────────────────────────


class TestVirtualMemoryManager:
    """Tests for the virtual memory subsystem."""

    def test_allocate_pages(self):
        vmm = VirtualMemoryManager(physical_pages=16, tlb_size=4)
        pages = vmm.allocate_pages(pid=1, num_pages=2)
        assert len(pages) == 2
        assert pages == [0, 1]

    def test_translate_populates_tlb(self):
        vmm = VirtualMemoryManager(physical_pages=16, tlb_size=4)
        vmm.allocate_pages(pid=1, num_pages=1)

        frame = vmm.translate(1, 0)
        assert frame >= 0
        assert vmm.tlb_misses == 1  # First access is a miss
        assert vmm.tlb_hits == 0

        # Second access should be a TLB hit
        frame2 = vmm.translate(1, 0)
        assert frame2 == frame
        assert vmm.tlb_hits == 1

    def test_tlb_lru_eviction(self):
        vmm = VirtualMemoryManager(physical_pages=64, tlb_size=4)
        # Allocate pages for 5 processes (TLB can only hold 4)
        for pid in range(1, 6):
            vmm.allocate_pages(pid=pid, num_pages=1)

        # Access all 5 pages -- the first one should be evicted
        for pid in range(1, 6):
            vmm.translate(pid, 0)

        # Access PID 1 again -- should be a TLB miss (it was evicted)
        vmm.translate(1, 0)
        assert vmm.tlb_misses == 6  # 5 initial misses + 1 re-miss

    def test_flush_tlb(self):
        vmm = VirtualMemoryManager(physical_pages=16, tlb_size=4)
        vmm.allocate_pages(pid=1, num_pages=1)
        vmm.translate(1, 0)

        vmm.flush_tlb()

        # After flush, access should be a miss again
        vmm.translate(1, 0)
        assert vmm.tlb_misses == 2  # Initial miss + post-flush miss

    def test_flush_tlb_pid(self):
        vmm = VirtualMemoryManager(physical_pages=16, tlb_size=8)
        vmm.allocate_pages(pid=1, num_pages=1)
        vmm.allocate_pages(pid=2, num_pages=1)
        vmm.translate(1, 0)
        vmm.translate(2, 0)

        vmm.flush_tlb_pid(1)

        # PID 1 should miss, PID 2 should still hit
        vmm.translate(1, 0)
        vmm.translate(2, 0)
        assert vmm.tlb_hits == 1  # Only PID 2 hits

    def test_page_fault_unmapped(self):
        vmm = VirtualMemoryManager(physical_pages=16, tlb_size=4)
        with pytest.raises(PageFaultError):
            vmm.translate(99, 0)

    def test_swap_out_and_in(self):
        # Only 2 physical pages -- third allocation forces swap
        vmm = VirtualMemoryManager(physical_pages=2, swap_pages=10, tlb_size=2)
        vmm.allocate_pages(pid=1, num_pages=1)
        vmm.allocate_pages(pid=2, num_pages=1)
        vmm.allocate_pages(pid=3, num_pages=1)  # Forces swap

        assert vmm.pages_swapped_out >= 1

        # Access the swapped page -- should trigger swap-in
        frame = vmm.translate(3, 0)
        assert frame >= 0

    def test_free_process_pages(self):
        vmm = VirtualMemoryManager(physical_pages=16, tlb_size=4)
        vmm.allocate_pages(pid=1, num_pages=3)
        free_before = len(vmm._free_frames)

        vmm.free_process_pages(1)
        free_after = len(vmm._free_frames)
        assert free_after == free_before + 3

    def test_get_memory_map(self):
        vmm = VirtualMemoryManager(physical_pages=16, tlb_size=4)
        vmm.allocate_pages(pid=1, num_pages=2)
        mem_map = vmm.get_memory_map()
        assert len(mem_map) == 2
        assert mem_map[0]["pid"] == 1

    def test_get_stats(self):
        vmm = VirtualMemoryManager()
        stats = vmm.get_stats()
        assert "tlb_hits" in stats
        assert "page_faults" in stats
        assert "free_frames" in stats

    def test_tlb_hit_rate_zero_accesses(self):
        vmm = VirtualMemoryManager()
        assert vmm.tlb_hit_rate == 0.0


# ── RoundRobinScheduler Tests ──────────────────────────────────────


class TestRoundRobinScheduler:
    """Tests for the round-robin scheduler."""

    def test_add_and_select(self):
        sched = RoundRobinScheduler()
        proc = FizzProcess(pid=1, number=42)
        sched.add_process(proc)
        selected = sched.next_process()
        assert selected is proc

    def test_round_robin_order(self):
        sched = RoundRobinScheduler()
        p1 = FizzProcess(pid=1, number=1)
        p2 = FizzProcess(pid=2, number=2)
        p3 = FizzProcess(pid=3, number=3)
        sched.add_process(p1)
        sched.add_process(p2)
        sched.add_process(p3)

        assert sched.next_process() is p1
        assert sched.next_process() is p2
        assert sched.next_process() is p3

    def test_empty_queue_returns_none(self):
        sched = RoundRobinScheduler()
        assert sched.next_process() is None

    def test_preempt_adds_to_back(self):
        sched = RoundRobinScheduler()
        p1 = FizzProcess(pid=1, number=1)
        p2 = FizzProcess(pid=2, number=2)
        sched.add_process(p1)
        sched.add_process(p2)

        selected = sched.next_process()
        assert selected is p1

        # Preempt p1 back to queue
        sched.preempt(p1)
        assert sched.next_process() is p2
        assert sched.next_process() is p1

    def test_remove_process(self):
        sched = RoundRobinScheduler()
        p1 = FizzProcess(pid=1, number=1)
        p2 = FizzProcess(pid=2, number=2)
        sched.add_process(p1)
        sched.add_process(p2)

        sched.remove_process(1)
        assert sched.next_process() is p2

    def test_queue_depth(self):
        sched = RoundRobinScheduler()
        assert sched.queue_depth == 0
        sched.add_process(FizzProcess(pid=1, number=1))
        sched.add_process(FizzProcess(pid=2, number=2))
        assert sched.queue_depth == 2

    def test_queue_snapshot(self):
        sched = RoundRobinScheduler()
        sched.add_process(FizzProcess(pid=1, number=1))
        sched.add_process(FizzProcess(pid=2, number=2))
        assert sched.get_queue_snapshot() == [1, 2]

    def test_scheduler_name(self):
        sched = RoundRobinScheduler(time_quantum_ms=5.0)
        assert "RoundRobin" in sched.name
        assert "5.0ms" in sched.name


# ── PriorityPreemptiveScheduler Tests ──────────────────────────────


class TestPriorityPreemptiveScheduler:
    """Tests for the priority-based preemptive scheduler."""

    def test_highest_priority_first(self):
        sched = PriorityPreemptiveScheduler()
        p_low = FizzProcess(pid=1, number=7, priority=ProcessPriority.LOW)
        p_rt = FizzProcess(pid=2, number=15, priority=ProcessPriority.REALTIME)
        p_norm = FizzProcess(pid=3, number=4, priority=ProcessPriority.NORMAL)

        sched.add_process(p_low)
        sched.add_process(p_norm)
        sched.add_process(p_rt)

        assert sched.next_process() is p_rt

    def test_same_priority_fifo(self):
        sched = PriorityPreemptiveScheduler()
        p1 = FizzProcess(pid=1, number=3, priority=ProcessPriority.HIGH)
        p2 = FizzProcess(pid=2, number=5, priority=ProcessPriority.HIGH)

        sched.add_process(p1)
        sched.add_process(p2)

        assert sched.next_process() is p1
        assert sched.next_process() is p2

    def test_should_preempt(self):
        sched = PriorityPreemptiveScheduler()
        running = FizzProcess(pid=1, number=4, priority=ProcessPriority.NORMAL)
        candidate = FizzProcess(pid=2, number=15, priority=ProcessPriority.REALTIME)
        assert sched.should_preempt(running, candidate) is True

    def test_should_not_preempt_lower(self):
        sched = PriorityPreemptiveScheduler()
        running = FizzProcess(pid=1, number=15, priority=ProcessPriority.REALTIME)
        candidate = FizzProcess(pid=2, number=4, priority=ProcessPriority.NORMAL)
        assert sched.should_preempt(running, candidate) is False

    def test_empty_returns_none(self):
        sched = PriorityPreemptiveScheduler()
        assert sched.next_process() is None

    def test_queue_depth(self):
        sched = PriorityPreemptiveScheduler()
        sched.add_process(FizzProcess(pid=1, number=1, priority=ProcessPriority.LOW))
        sched.add_process(FizzProcess(pid=2, number=2, priority=ProcessPriority.HIGH))
        assert sched.queue_depth == 2

    def test_get_queue_snapshot(self):
        sched = PriorityPreemptiveScheduler()
        sched.add_process(FizzProcess(pid=1, number=3, priority=ProcessPriority.HIGH))
        sched.add_process(FizzProcess(pid=2, number=7, priority=ProcessPriority.LOW))
        snap = sched.get_queue_snapshot()
        assert 1 in snap["HIGH"]
        assert 2 in snap["LOW"]

    def test_remove_from_all_queues(self):
        sched = PriorityPreemptiveScheduler()
        sched.add_process(FizzProcess(pid=1, number=3, priority=ProcessPriority.HIGH))
        sched.remove_process(1)
        assert sched.queue_depth == 0


# ── CompletelyFairScheduler Tests ──────────────────────────────────


class TestCompletelyFairScheduler:
    """Tests for the CFS scheduler."""

    def test_selects_lowest_vruntime(self):
        sched = CompletelyFairScheduler()
        p1 = FizzProcess(pid=1, number=1, virtual_runtime_ns=1000)
        p2 = FizzProcess(pid=2, number=2, virtual_runtime_ns=500)
        p3 = FizzProcess(pid=3, number=3, virtual_runtime_ns=2000)

        sched.add_process(p1)
        sched.add_process(p2)
        sched.add_process(p3)

        selected = sched.next_process()
        assert selected is p2

    def test_vruntime_update_weighted(self):
        sched = CompletelyFairScheduler(default_weight=1024)
        proc = FizzProcess(pid=1, number=15, priority=ProcessPriority.REALTIME)
        sched.add_process(proc)

        initial_vruntime = proc.virtual_runtime_ns
        sched.update_vruntime(proc, 1_000_000)  # 1ms of actual time

        # REALTIME weight is 4096, default is 1024
        # delta_vruntime = 1_000_000 * (1024 / 4096) = 250_000
        expected_delta = int(1_000_000 * (1024 / 4096))
        assert proc.virtual_runtime_ns == initial_vruntime + expected_delta

    def test_low_priority_advances_faster(self):
        sched = CompletelyFairScheduler(default_weight=1024)
        proc_high = FizzProcess(pid=1, number=3, priority=ProcessPriority.HIGH)
        proc_low = FizzProcess(pid=2, number=7, priority=ProcessPriority.LOW)

        sched.add_process(proc_high)
        sched.add_process(proc_low)

        sched.update_vruntime(proc_high, 1_000_000)
        sched.update_vruntime(proc_low, 1_000_000)

        # Low priority should have higher vruntime (ran "more" in virtual time)
        assert proc_low.virtual_runtime_ns > proc_high.virtual_runtime_ns

    def test_empty_returns_none(self):
        sched = CompletelyFairScheduler()
        assert sched.next_process() is None

    def test_only_selects_ready(self):
        sched = CompletelyFairScheduler()
        proc = FizzProcess(pid=1, number=1)
        proc.transition_to(ProcessState.RUNNING)
        proc.transition_to(ProcessState.TERMINATED)
        sched.add_process(proc)

        assert sched.next_process() is None

    def test_vruntime_snapshot(self):
        sched = CompletelyFairScheduler()
        proc = FizzProcess(pid=1, number=42)
        sched.add_process(proc)
        snap = sched.get_vruntime_snapshot()
        assert len(snap) == 1
        assert snap[0]["pid"] == 1

    def test_remove_process(self):
        sched = CompletelyFairScheduler()
        sched.add_process(FizzProcess(pid=1, number=1))
        sched.remove_process(1)
        assert sched.queue_depth == 0


# ── InterruptController Tests ──────────────────────────────────────


class TestInterruptController:
    """Tests for the interrupt controller."""

    def test_register_handler(self):
        ic = InterruptController(num_vectors=16)
        ic.register_handler(0, "timer", lambda **kw: None)
        assert 0 in ic.get_handler_map()

    def test_duplicate_irq_raises(self):
        ic = InterruptController(num_vectors=16)
        ic.register_handler(0, "timer", lambda **kw: None)
        with pytest.raises(InterruptConflictError):
            ic.register_handler(0, "other_timer", lambda **kw: None)

    def test_fire_calls_handler(self):
        called = {"count": 0}
        def handler(**kw):
            called["count"] += 1

        ic = InterruptController(num_vectors=16)
        ic.register_handler(4, "fizz", handler)
        ic.fire(4, number=3)
        assert called["count"] == 1

    def test_masked_interrupt_suppressed(self):
        called = {"count": 0}
        def handler(**kw):
            called["count"] += 1

        ic = InterruptController(num_vectors=16)
        ic.register_handler(4, "fizz", handler)
        ic.mask(4)
        ic.fire(4, number=3)
        assert called["count"] == 0

    def test_unmask_allows_interrupt(self):
        called = {"count": 0}
        def handler(**kw):
            called["count"] += 1

        ic = InterruptController(num_vectors=16)
        ic.register_handler(4, "fizz", handler)
        ic.mask(4)
        ic.unmask(4)
        ic.fire(4, number=3)
        assert called["count"] == 1

    def test_mask_all_unmask_all(self):
        called = {"count": 0}
        def handler(**kw):
            called["count"] += 1

        ic = InterruptController(num_vectors=16)
        ic.register_handler(4, "fizz", handler)
        ic.mask_all()
        ic.fire(4, number=3)
        assert called["count"] == 0

        ic.unmask_all()
        ic.fire(4, number=3)
        assert called["count"] == 1

    def test_fire_unregistered_irq(self):
        ic = InterruptController(num_vectors=16)
        # Should not raise
        ic.fire(5, number=10)
        assert ic.total_interrupts == 1

    def test_out_of_range_irq(self):
        ic = InterruptController(num_vectors=16)
        with pytest.raises(KernelPanicError):
            ic.register_handler(99, "bad", lambda **kw: None)

    def test_interrupt_log(self):
        ic = InterruptController(num_vectors=16)
        ic.register_handler(0, "timer", lambda **kw: None)
        ic.fire(0)
        ic.fire(0)
        log = ic.get_log()
        assert len(log) == 2
        assert log[0]["irq"] == 0

    def test_handler_exception_is_caught(self):
        def bad_handler(**kw):
            raise RuntimeError("handler exploded")

        ic = InterruptController(num_vectors=16)
        ic.register_handler(0, "bad", bad_handler)
        # Should not propagate
        ic.fire(0)
        assert ic.total_interrupts == 1


# ── FizzBuzzKernel Tests ──────────────────────────────────────────


class TestFizzBuzzKernel:
    """Tests for the kernel lifecycle and process management."""

    def test_boot(self, kernel):
        assert kernel._booted is True
        boot_log = kernel.get_boot_log()
        assert any("BOOT" in line for line in boot_log)

    def test_double_boot_panics(self, kernel):
        with pytest.raises(KernelPanicError):
            kernel.boot()

    def test_spawn_process(self, kernel):
        proc = kernel.spawn_process(15)
        assert proc.pid >= 1
        assert proc.number == 15
        assert proc.priority == ProcessPriority.REALTIME
        assert proc.state == ProcessState.READY

    def test_spawn_sets_registers(self, kernel):
        proc = kernel.spawn_process(42)
        assert proc.registers.r0 == 42
        assert proc.registers.sp == 0xFFFF

    def test_evaluate_fizz(self, kernel):
        result = kernel.evaluate_number(3)
        assert result.output == "Fizz"

    def test_evaluate_buzz(self, kernel):
        result = kernel.evaluate_number(5)
        assert result.output == "Buzz"

    def test_evaluate_fizzbuzz(self, kernel):
        result = kernel.evaluate_number(15)
        assert result.output == "FizzBuzz"

    def test_evaluate_plain_number(self, kernel):
        result = kernel.evaluate_number(7)
        assert result.output == "7"

    def test_run_produces_correct_results(self, kernel):
        results = kernel.run(1, 20)
        assert len(results) == 20

        expected = []
        for i in range(1, 21):
            if i % 15 == 0:
                expected.append("FizzBuzz")
            elif i % 3 == 0:
                expected.append("Fizz")
            elif i % 5 == 0:
                expected.append("Buzz")
            else:
                expected.append(str(i))

        actual = [r.output for r in results]
        assert actual == expected

    def test_run_1_to_100(self, kernel):
        """The definitive test: kernel produces same results as simple FizzBuzz."""
        results = kernel.run(1, 100)
        assert len(results) == 100

        for i, result in enumerate(results, start=1):
            if i % 15 == 0:
                assert result.output == "FizzBuzz", f"Failed for {i}"
            elif i % 3 == 0:
                assert result.output == "Fizz", f"Failed for {i}"
            elif i % 5 == 0:
                assert result.output == "Buzz", f"Failed for {i}"
            else:
                assert result.output == str(i), f"Failed for {i}"

    def test_run_without_boot_panics(self, standard_rules):
        k = FizzBuzzKernel(
            rules=standard_rules,
            boot_delay_ms=0.0,
            context_switch_overhead_us=0.0,
        )
        with pytest.raises(KernelPanicError):
            k.run(1, 5)

    def test_get_process(self, kernel):
        proc = kernel.spawn_process(42)
        found = kernel.get_process(proc.pid)
        assert found is proc

    def test_get_nonexistent_process(self, kernel):
        assert kernel.get_process(9999) is None

    def test_process_count(self, kernel):
        assert kernel.process_count == 0
        kernel.spawn_process(1)
        kernel.spawn_process(2)
        assert kernel.process_count == 2

    def test_shutdown(self, kernel):
        kernel.run(1, 5)
        kernel.shutdown()
        assert kernel._shutdown is True

    def test_double_shutdown_is_safe(self, kernel):
        kernel.shutdown()
        kernel.shutdown()  # Should not raise

    def test_uptime(self, kernel):
        time.sleep(0.001)
        assert kernel.uptime_ms > 0

    def test_get_stats(self, kernel):
        kernel.run(1, 5)
        stats = kernel.get_stats()
        assert "uptime_ms" in stats
        assert "scheduler" in stats
        assert "memory" in stats
        assert stats["total_processes"] >= 5

    def test_get_process_table(self, kernel):
        kernel.run(1, 3)
        table = kernel.get_process_table()
        assert len(table) >= 3
        assert all("pid" in row for row in table)

    def test_priority_scheduler_kernel(self, priority_kernel):
        results = priority_kernel.run(1, 15)
        assert len(results) == 15
        assert results[14].output == "FizzBuzz"

    def test_cfs_scheduler_kernel(self, cfs_kernel):
        results = cfs_kernel.run(1, 15)
        assert len(results) == 15
        assert results[14].output == "FizzBuzz"

    def test_scheduler_name_rr(self, kernel):
        assert "RoundRobin" in kernel.scheduler_name

    def test_scheduler_name_priority(self, priority_kernel):
        assert "Priority" in priority_kernel.scheduler_name

    def test_scheduler_name_cfs(self, cfs_kernel):
        assert "CFS" in cfs_kernel.scheduler_name

    def test_events_emitted(self, standard_rules):
        events = []
        def collector(event):
            events.append(event)

        k = FizzBuzzKernel(
            rules=standard_rules,
            boot_delay_ms=0.0,
            context_switch_overhead_us=0.0,
            event_callback=collector,
        )
        k.boot()
        k.run(1, 3)

        event_types = {e.event_type for e in events}
        assert EventType.KERNEL_BOOT_STARTED in event_types
        assert EventType.KERNEL_BOOT_COMPLETED in event_types
        assert EventType.KERNEL_PROCESS_SPAWNED in event_types

    def test_interrupts_fired_during_run(self, kernel):
        kernel.run(1, 15)
        assert kernel._interrupts.total_interrupts > 0

    def test_syscalls_invoked_during_run(self, kernel):
        kernel.run(1, 5)
        assert kernel._syscall.total_syscalls > 0


# ── SyscallInterface Tests ─────────────────────────────────────────


class TestSyscallInterface:
    """Tests for the system call interface."""

    def test_sys_evaluate(self, kernel):
        proc = kernel.spawn_process(15)
        result = kernel._syscall.sys_evaluate(proc.pid, 15)
        assert result is not None
        assert result.output == "FizzBuzz"

    def test_sys_evaluate_nonexistent_pid(self, kernel):
        result = kernel._syscall.sys_evaluate(9999, 15)
        assert result is None

    def test_sys_fork(self, kernel):
        parent = kernel.spawn_process(15)
        child_pid = kernel._syscall.sys_fork(parent.pid)
        assert child_pid > parent.pid

        child = kernel.get_process(child_pid)
        assert child is not None
        assert child.number == parent.number
        assert child.parent_pid == parent.pid

    def test_sys_fork_nonexistent(self, kernel):
        assert kernel._syscall.sys_fork(9999) == -1

    def test_sys_exit(self, kernel):
        proc = kernel.spawn_process(42)
        proc.transition_to(ProcessState.RUNNING)
        kernel._syscall.sys_exit(proc.pid, exit_code=0)
        assert proc.state == ProcessState.ZOMBIE
        assert proc.exit_code == 0

    def test_sys_yield(self, kernel):
        proc = kernel.spawn_process(42)
        proc.transition_to(ProcessState.RUNNING)
        kernel._syscall.sys_yield(proc.pid)
        assert proc.state == ProcessState.READY

    def test_syscall_log(self, kernel):
        proc = kernel.spawn_process(42)
        kernel._syscall.sys_evaluate(proc.pid, 42)
        log = kernel._syscall.get_log()
        assert len(log) >= 1
        assert log[-1]["syscall"] == "sys_evaluate"

    def test_total_syscalls_count(self, kernel):
        proc = kernel.spawn_process(1)
        kernel._syscall.sys_evaluate(proc.pid, 1)
        kernel._syscall.sys_evaluate(proc.pid, 2)
        assert kernel._syscall.total_syscalls == 2


# ── KernelDashboard Tests ─────────────────────────────────────────


class TestKernelDashboard:
    """Tests for the kernel dashboard rendering."""

    def test_render_produces_output(self, kernel):
        kernel.run(1, 10)
        output = KernelDashboard.render(kernel, width=60)
        assert "FIZZBUZZ OPERATING SYSTEM KERNEL" in output
        assert "KERNEL STATISTICS" in output

    def test_render_with_process_table(self, kernel):
        kernel.run(1, 5)
        output = KernelDashboard.render(kernel, show_process_table=True)
        assert "PROCESS TABLE" in output

    def test_render_with_memory(self, kernel):
        kernel.run(1, 5)
        output = KernelDashboard.render(kernel, show_memory_map=True)
        assert "VIRTUAL MEMORY" in output

    def test_render_with_interrupt_log(self, kernel):
        kernel.run(1, 5)
        output = KernelDashboard.render(kernel, show_interrupt_log=True)
        assert "INTERRUPT LOG" in output

    def test_render_irq_vector_map(self, kernel):
        output = KernelDashboard.render(kernel)
        assert "IRQ VECTOR MAP" in output

    def test_render_boot_log(self, kernel):
        output = KernelDashboard.render(kernel)
        assert "BOOT LOG" in output

    def test_render_empty_kernel(self, kernel):
        # Dashboard should render even without running anything
        output = KernelDashboard.render(kernel)
        assert len(output) > 100

    def test_render_tagline(self, kernel):
        output = KernelDashboard.render(kernel)
        assert "Linus" in output


# ── KernelMiddleware Tests ─────────────────────────────────────────


class TestKernelMiddleware:
    """Tests for the kernel middleware."""

    def test_middleware_name(self, kernel):
        mw = KernelMiddleware(kernel=kernel)
        assert mw.get_name() == "KernelMiddleware"

    def test_middleware_priority(self, kernel):
        mw = KernelMiddleware(kernel=kernel)
        assert mw.get_priority() == -10

    def test_middleware_evaluates_number(self, kernel):
        mw = KernelMiddleware(kernel=kernel)

        ctx = ProcessingContext(number=15, session_id="test-session")

        def next_handler(c):
            return c

        result_ctx = mw.process(ctx, next_handler)
        assert len(result_ctx.results) == 1
        assert result_ctx.results[0].output == "FizzBuzz"
        assert "kernel_pid" in result_ctx.metadata

    def test_middleware_injects_metadata(self, kernel):
        mw = KernelMiddleware(kernel=kernel)
        ctx = ProcessingContext(number=3, session_id="test-session")
        result_ctx = mw.process(ctx, lambda c: c)

        assert "kernel_priority" in result_ctx.metadata
        assert result_ctx.metadata["kernel_priority"] == "HIGH"

    def test_middleware_short_circuits(self, kernel):
        """Kernel middleware should short-circuit and not call next_handler."""
        mw = KernelMiddleware(kernel=kernel)
        called = {"count": 0}

        def next_handler(c):
            called["count"] += 1
            return c

        ctx = ProcessingContext(number=5, session_id="test-session")
        mw.process(ctx, next_handler)

        # next_handler should NOT be called because kernel evaluated successfully
        assert called["count"] == 0


# ── Exception Tests ────────────────────────────────────────────────


class TestKernelExceptions:
    """Tests for kernel-specific exceptions."""

    def test_kernel_panic_error(self):
        exc = KernelPanicError("test reason")
        assert "KERNEL PANIC" in str(exc)
        assert exc.error_code == "EFP-KN01"
        assert exc.reason == "test reason"

    def test_invalid_process_state_error(self):
        exc = InvalidProcessStateError(42, "TERMINATED", "RUNNING")
        assert "PID=42" in str(exc)
        assert exc.error_code == "EFP-KN02"
        assert exc.pid == 42

    def test_page_fault_error(self):
        exc = PageFaultError(0x1000, "not mapped")
        assert "0x00001000" in str(exc)
        assert exc.error_code == "EFP-KN03"
        assert exc.virtual_address == 0x1000

    def test_scheduler_starvation_error(self):
        exc = SchedulerStarvationError(7, 1000)
        assert "PID=7" in str(exc)
        assert exc.error_code == "EFP-KN04"
        assert exc.wait_cycles == 1000

    def test_interrupt_conflict_error(self):
        exc = InterruptConflictError(4, "fizz_handler", "other_handler")
        assert "IRQ conflict" in str(exc)
        assert exc.error_code == "EFP-KN05"
        assert exc.irq == 4


# ── ProcessState Enum Tests ────────────────────────────────────────


class TestProcessStateEnum:
    """Tests for the ProcessState enum."""

    def test_all_states_exist(self):
        assert ProcessState.READY.name == "READY"
        assert ProcessState.RUNNING.name == "RUNNING"
        assert ProcessState.BLOCKED.name == "BLOCKED"
        assert ProcessState.ZOMBIE.name == "ZOMBIE"
        assert ProcessState.TERMINATED.name == "TERMINATED"

    def test_states_are_distinct(self):
        states = [ProcessState.READY, ProcessState.RUNNING, ProcessState.BLOCKED,
                  ProcessState.ZOMBIE, ProcessState.TERMINATED]
        assert len(set(states)) == 5


# ── ProcessPriority Enum Tests ─────────────────────────────────────


class TestProcessPriorityEnum:
    """Tests for the ProcessPriority enum."""

    def test_realtime_is_highest(self):
        assert ProcessPriority.REALTIME.value < ProcessPriority.HIGH.value
        assert ProcessPriority.HIGH.value < ProcessPriority.NORMAL.value
        assert ProcessPriority.NORMAL.value < ProcessPriority.LOW.value


# ── SchedulerAlgorithm Enum Tests ──────────────────────────────────


class TestSchedulerAlgorithmEnum:
    """Tests for the SchedulerAlgorithm enum."""

    def test_values(self):
        assert SchedulerAlgorithm.ROUND_ROBIN.value == "rr"
        assert SchedulerAlgorithm.PRIORITY_PREEMPTIVE.value == "priority"
        assert SchedulerAlgorithm.COMPLETELY_FAIR.value == "cfs"


# ── Integration Tests ──────────────────────────────────────────────


class TestKernelIntegration:
    """Integration tests verifying end-to-end kernel correctness."""

    def test_all_three_schedulers_produce_same_results(self, standard_rules):
        """All scheduler algorithms must produce identical FizzBuzz results."""
        results_by_scheduler = {}

        for sched_type in SchedulerAlgorithm:
            k = FizzBuzzKernel(
                rules=standard_rules,
                scheduler_type=sched_type,
                boot_delay_ms=0.0,
                context_switch_overhead_us=0.0,
            )
            k.boot()
            results = k.run(1, 30)
            results_by_scheduler[sched_type] = [r.output for r in results]
            k.shutdown()

        # All schedulers should produce identical output
        rr_results = results_by_scheduler[SchedulerAlgorithm.ROUND_ROBIN]
        for sched_type, results in results_by_scheduler.items():
            assert results == rr_results, f"{sched_type} diverged from RR"

    def test_kernel_matches_standard_rule_engine(self, standard_rules):
        """Kernel results must match StandardRuleEngine for 1-100."""
        from enterprise_fizzbuzz.infrastructure.rules_engine import (
            ConcreteRule,
            StandardRuleEngine,
        )

        # Standard engine results
        rules = [ConcreteRule(rd) for rd in standard_rules]
        engine = StandardRuleEngine()
        standard_results = [engine.evaluate(n, rules).output for n in range(1, 101)]

        # Kernel results
        k = FizzBuzzKernel(
            rules=standard_rules,
            boot_delay_ms=0.0,
            context_switch_overhead_us=0.0,
        )
        k.boot()
        kernel_results_raw = k.run(1, 100)
        kernel_results = [r.output for r in kernel_results_raw]
        k.shutdown()

        assert kernel_results == standard_results

    def test_large_range(self, standard_rules):
        """Kernel can handle larger ranges without crashing."""
        k = FizzBuzzKernel(
            rules=standard_rules,
            max_processes=1000,
            physical_pages=512,
            swap_pages=1024,
            boot_delay_ms=0.0,
            context_switch_overhead_us=0.0,
        )
        k.boot()
        results = k.run(1, 200)
        assert len(results) == 200
        # Spot check
        assert results[14].output == "FizzBuzz"  # 15
        assert results[98].output == "Fizz"      # 99
        assert results[99].output == "Buzz"      # 100
        k.shutdown()

    def test_context_switches_tracked(self, standard_rules):
        """Context switches should be tracked by the kernel."""
        k = FizzBuzzKernel(
            rules=standard_rules,
            boot_delay_ms=0.0,
            context_switch_overhead_us=0.0,
        )
        k.boot()
        k.run(1, 10)
        assert k._total_context_switches >= 1
        k.shutdown()
