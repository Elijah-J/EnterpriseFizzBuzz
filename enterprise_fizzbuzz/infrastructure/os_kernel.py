"""
Enterprise FizzBuzz Platform - Operating System Kernel Module

Implements a fully-featured operating system kernel for managing FizzBuzz
evaluation processes. Because computing n % 3 was never going to be
enterprise-grade without process scheduling, virtual memory management,
interrupt handling, and system calls.

Features:
    - Process Control Blocks with PID, state machine, CPU registers
    - Three scheduling algorithms: Round Robin, Priority Preemptive, CFS
    - Virtual Memory Manager with page table, 16-entry LRU TLB, swap
    - Interrupt Controller with 16 IRQ vectors and handler registration
    - System call interface (sys_evaluate, sys_fork, sys_exit, sys_yield)
    - Full kernel boot sequence with POST and driver initialization
    - ASCII dashboard with process table, memory map, interrupt log

The kernel faithfully implements real OS concepts applied to a problem
that requires exactly zero of them. Tanenbaum would be proud. Or horrified.
"""

from __future__ import annotations

import collections
import hashlib
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, ClassVar, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    InterruptConflictError,
    InvalidProcessStateError,
    KernelPanicError,
    PageFaultError,
    SchedulerStarvationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    ProcessPriority,
    ProcessState,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
    SchedulerAlgorithm,
)

logger = logging.getLogger(__name__)


# ── Register File ───────────────────────────────────────────────────


@dataclass
class RegisterFile:
    """Simulated CPU register file for a FizzBuzz process.

    Every FizzBuzz process deserves its own set of CPU registers,
    because storing the number 15 in a Python variable was too
    pedestrian. The register file is saved and restored on every
    context switch, adding approximately zero value but infinite
    enterprise credibility.
    """

    # General purpose registers
    r0: int = 0     # Accumulator -- holds the number being evaluated
    r1: int = 0     # Divisor register -- holds the current divisor
    r2: int = 0     # Result register -- 0=no match, 1=match
    r3: int = 0     # Label index register
    r4: int = 0     # Scratch register
    r5: int = 0     # Scratch register
    r6: int = 0     # Scratch register
    r7: int = 0     # Scratch register

    # Special registers
    pc: int = 0     # Program Counter
    sp: int = 0     # Stack Pointer
    flags: int = 0  # Status flags (bit 0=zero, bit 1=carry, bit 2=overflow)
    ir: int = 0     # Instruction Register

    def snapshot(self) -> dict[str, int]:
        """Create a serializable snapshot of the register file."""
        return {
            "r0": self.r0, "r1": self.r1, "r2": self.r2, "r3": self.r3,
            "r4": self.r4, "r5": self.r5, "r6": self.r6, "r7": self.r7,
            "pc": self.pc, "sp": self.sp, "flags": self.flags, "ir": self.ir,
        }

    def restore(self, snapshot: dict[str, int]) -> None:
        """Restore registers from a snapshot."""
        for attr, val in snapshot.items():
            setattr(self, attr, val)


# ── Process Control Block ───────────────────────────────────────────


@dataclass
class FizzProcess:
    """Process Control Block for a FizzBuzz evaluation.

    Every integer in the FizzBuzz range gets its own process, complete
    with a PID, priority level, state machine, CPU registers, virtual
    memory page allocation, and accumulated CPU time statistics. The
    fact that each process exists for approximately 0.001ms before
    terminating does nothing to diminish the importance of tracking
    all of this metadata.

    Numbers divisible by 15 receive REALTIME priority because FizzBuzz
    is the most sacred result. Numbers divisible by only 3 or 5 get
    HIGH priority. Everything else wallows in NORMAL.
    """

    pid: int
    number: int
    state: ProcessState = ProcessState.READY
    priority: ProcessPriority = ProcessPriority.NORMAL
    registers: RegisterFile = field(default_factory=RegisterFile)
    cpu_time_ns: int = 0
    wall_time_ns: int = 0
    context_switches: int = 0
    page_faults: int = 0
    parent_pid: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    terminated_at: Optional[datetime] = None
    exit_code: int = -1
    result: Optional[FizzBuzzResult] = None
    virtual_pages: list[int] = field(default_factory=list)

    # CFS-specific fields
    virtual_runtime_ns: int = 0
    weight: int = 1024  # Nice-0 weight, same as Linux CFS

    # Scheduling metadata
    wait_cycles: int = 0
    last_scheduled_ns: int = 0

    # Register snapshot for context switching
    _saved_registers: Optional[dict[str, int]] = field(default=None, repr=False)

    def save_context(self) -> None:
        """Save CPU state for context switch (like a real OS would)."""
        self._saved_registers = self.registers.snapshot()

    def restore_context(self) -> None:
        """Restore CPU state after context switch."""
        if self._saved_registers is not None:
            self.registers.restore(self._saved_registers)
            self._saved_registers = None

    @staticmethod
    def auto_priority(number: int) -> ProcessPriority:
        """Determine process priority based on the divine importance of the number.

        - Divisible by 15: REALTIME (FizzBuzz is sacred)
        - Divisible by 3 or 5: HIGH (still important)
        - Prime numbers: LOW (they contribute nothing)
        - Everything else: NORMAL
        """
        if number % 15 == 0:
            return ProcessPriority.REALTIME
        if number % 3 == 0 or number % 5 == 0:
            return ProcessPriority.HIGH
        # Check primality for LOW priority assignment
        if number > 1:
            is_prime = all(number % i != 0 for i in range(2, int(number**0.5) + 1))
            if is_prime:
                return ProcessPriority.LOW
        return ProcessPriority.NORMAL

    # ── State Machine transitions ────────────────────────────

    _VALID_TRANSITIONS: ClassVar[dict[ProcessState, set[ProcessState]]] = {
        ProcessState.READY: {ProcessState.RUNNING, ProcessState.TERMINATED},
        ProcessState.RUNNING: {ProcessState.READY, ProcessState.BLOCKED, ProcessState.ZOMBIE, ProcessState.TERMINATED},
        ProcessState.BLOCKED: {ProcessState.READY},
        ProcessState.ZOMBIE: {ProcessState.TERMINATED},
        ProcessState.TERMINATED: set(),  # Terminal state -- no escape
    }

    def transition_to(self, new_state: ProcessState) -> None:
        """Transition to a new state, validating the state machine."""
        valid = self._VALID_TRANSITIONS.get(self.state, set())
        if new_state not in valid:
            raise InvalidProcessStateError(
                self.pid, self.state.name, new_state.name
            )
        old_state = self.state
        self.state = new_state
        if new_state == ProcessState.TERMINATED:
            self.terminated_at = datetime.now(timezone.utc)
        logger.debug(
            "PID %d: %s -> %s", self.pid, old_state.name, new_state.name
        )


# ── TLB Entry ───────────────────────────────────────────────────────


@dataclass
class TLBEntry:
    """Translation Lookaside Buffer entry.

    Caches virtual-to-physical page mappings so the kernel doesn't have
    to walk the page table on every memory access. In a real CPU, TLB
    misses cost dozens of cycles. Here, they cost a dictionary lookup,
    which is basically the same thing in enterprise terms.
    """

    virtual_page: int
    physical_page: int
    pid: int
    valid: bool = True
    dirty: bool = False
    accessed_at_ns: int = 0


# ── Virtual Memory Manager ─────────────────────────────────────────


class VirtualMemoryManager:
    """Virtual memory subsystem for the FizzBuzz kernel.

    Manages a page table, a 16-entry LRU TLB, physical frame allocation,
    and a swap area. Because FizzBuzz numbers need their own virtual
    address spaces, page fault handlers, and demand paging -- just like
    real processes that actually need memory.

    The TLB uses collections.OrderedDict for O(1) LRU eviction, which
    is exactly how hardware TLBs work (they don't, but let's not ruin
    the fantasy).
    """

    def __init__(
        self,
        tlb_size: int = 16,
        physical_pages: int = 128,
        swap_pages: int = 256,
        page_size: int = 64,
    ) -> None:
        self._tlb_size = tlb_size
        self._physical_pages = physical_pages
        self._swap_pages = swap_pages
        self._page_size = page_size

        # TLB: OrderedDict for LRU (most recently used at end)
        self._tlb: OrderedDict[tuple[int, int], TLBEntry] = OrderedDict()

        # Page table: (pid, virtual_page) -> physical_page
        self._page_table: dict[tuple[int, int], int] = {}

        # Physical frame allocation
        self._free_frames: list[int] = list(range(physical_pages))
        self._allocated_frames: dict[int, tuple[int, int]] = {}  # frame -> (pid, vpage)

        # Swap space
        self._swap: dict[tuple[int, int], int] = {}  # (pid, vpage) -> swap_slot
        self._free_swap_slots: list[int] = list(range(swap_pages))

        # Statistics
        self.tlb_hits: int = 0
        self.tlb_misses: int = 0
        self.page_faults: int = 0
        self.pages_swapped_in: int = 0
        self.pages_swapped_out: int = 0

    @property
    def tlb_hit_rate(self) -> float:
        """TLB hit rate as a fraction."""
        total = self.tlb_hits + self.tlb_misses
        return self.tlb_hits / total if total > 0 else 0.0

    def allocate_pages(self, pid: int, num_pages: int) -> list[int]:
        """Allocate virtual pages for a process. Returns virtual page numbers."""
        virtual_pages = []
        for i in range(num_pages):
            vpage = i
            if self._free_frames:
                frame = self._free_frames.pop(0)
                self._page_table[(pid, vpage)] = frame
                self._allocated_frames[frame] = (pid, vpage)
            else:
                # No free frames -- need to swap out a page
                self._swap_out_page()
                frame = self._free_frames.pop(0)
                self._page_table[(pid, vpage)] = frame
                self._allocated_frames[frame] = (pid, vpage)
            virtual_pages.append(vpage)
        return virtual_pages

    def translate(self, pid: int, virtual_page: int) -> int:
        """Translate a virtual page to a physical frame, consulting TLB first."""
        key = (pid, virtual_page)

        # Check TLB (fast path)
        if key in self._tlb:
            self.tlb_hits += 1
            entry = self._tlb[key]
            # Move to end for LRU
            self._tlb.move_to_end(key)
            entry.accessed_at_ns = time.perf_counter_ns()
            return entry.physical_page

        # TLB miss -- walk the page table
        self.tlb_misses += 1

        if key in self._page_table:
            frame = self._page_table[key]
            self._update_tlb(pid, virtual_page, frame)
            return frame

        # Page fault: page is in swap or doesn't exist
        self.page_faults += 1
        if key in self._swap:
            return self._handle_page_fault(pid, virtual_page)

        raise PageFaultError(
            virtual_page * self._page_size,
            f"Page {virtual_page} not mapped for PID {pid}"
        )

    def _update_tlb(self, pid: int, virtual_page: int, physical_page: int) -> None:
        """Update the TLB with a new mapping, evicting LRU if full."""
        key = (pid, virtual_page)
        if key in self._tlb:
            self._tlb.move_to_end(key)
            return

        # Evict LRU entry if TLB is full
        if len(self._tlb) >= self._tlb_size:
            self._tlb.popitem(last=False)

        self._tlb[key] = TLBEntry(
            virtual_page=virtual_page,
            physical_page=physical_page,
            pid=pid,
            accessed_at_ns=time.perf_counter_ns(),
        )

    def _swap_out_page(self) -> None:
        """Swap out the least recently used page to make room."""
        if not self._allocated_frames:
            raise KernelPanicError("Out of physical memory and no pages to swap")

        # Find the frame with the oldest TLB access (crude LRU approximation)
        oldest_frame = min(self._allocated_frames.keys())
        pid, vpage = self._allocated_frames[oldest_frame]

        # Move to swap
        if not self._free_swap_slots:
            raise KernelPanicError("Swap space exhausted -- the FizzBuzz kernel is out of memory everywhere")
        swap_slot = self._free_swap_slots.pop(0)
        self._swap[(pid, vpage)] = swap_slot

        # Free the physical frame
        del self._page_table[(pid, vpage)]
        del self._allocated_frames[oldest_frame]
        self._free_frames.append(oldest_frame)

        # Invalidate TLB entry
        tlb_key = (pid, vpage)
        if tlb_key in self._tlb:
            del self._tlb[tlb_key]

        self.pages_swapped_out += 1
        logger.debug("Swapped out page (PID=%d, vpage=%d) to swap slot %d", pid, vpage, swap_slot)

    def _handle_page_fault(self, pid: int, virtual_page: int) -> int:
        """Handle a page fault by swapping in the requested page."""
        key = (pid, virtual_page)
        if key not in self._swap:
            raise PageFaultError(
                virtual_page * self._page_size,
                f"Page {virtual_page} not in swap for PID {pid}"
            )

        # Need a free frame
        if not self._free_frames:
            self._swap_out_page()

        frame = self._free_frames.pop(0)

        # Restore from swap
        swap_slot = self._swap.pop(key)
        self._free_swap_slots.append(swap_slot)
        self._page_table[key] = frame
        self._allocated_frames[frame] = key

        self._update_tlb(pid, virtual_page, frame)
        self.pages_swapped_in += 1

        logger.debug("Swapped in page (PID=%d, vpage=%d) from swap to frame %d", pid, virtual_page, frame)
        return frame

    def flush_tlb(self) -> None:
        """Flush the entire TLB. Called on context switch, naturally."""
        self._tlb.clear()

    def flush_tlb_pid(self, pid: int) -> None:
        """Flush TLB entries for a specific process."""
        keys_to_remove = [k for k in self._tlb if k[0] == pid]
        for key in keys_to_remove:
            del self._tlb[key]

    def free_process_pages(self, pid: int) -> None:
        """Free all pages belonging to a terminated process."""
        # Free physical pages
        keys_to_free = [(p, v) for (p, v) in self._page_table if p == pid]
        for key in keys_to_free:
            frame = self._page_table.pop(key)
            if frame in self._allocated_frames:
                del self._allocated_frames[frame]
            self._free_frames.append(frame)

        # Free swap pages
        swap_to_free = [(p, v) for (p, v) in self._swap if p == pid]
        for key in swap_to_free:
            slot = self._swap.pop(key)
            self._free_swap_slots.append(slot)

        # Flush TLB for this PID
        self.flush_tlb_pid(pid)

    def get_memory_map(self) -> list[dict[str, Any]]:
        """Return the current memory map for dashboard display."""
        entries = []
        for (pid, vpage), frame in sorted(self._page_table.items()):
            entries.append({
                "pid": pid,
                "virtual_page": vpage,
                "physical_frame": frame,
                "in_tlb": (pid, vpage) in self._tlb,
            })
        return entries

    def get_stats(self) -> dict[str, Any]:
        """Return memory statistics."""
        return {
            "tlb_hits": self.tlb_hits,
            "tlb_misses": self.tlb_misses,
            "tlb_hit_rate": f"{self.tlb_hit_rate:.1%}",
            "page_faults": self.page_faults,
            "free_frames": len(self._free_frames),
            "allocated_frames": len(self._allocated_frames),
            "swap_used": len(self._swap),
            "pages_swapped_in": self.pages_swapped_in,
            "pages_swapped_out": self.pages_swapped_out,
        }


# ── Schedulers ──────────────────────────────────────────────────────


class RoundRobinScheduler:
    """Round-robin process scheduler with configurable time quantum.

    The most democratic of scheduling algorithms: every FizzBuzz process
    gets an equal time slice, regardless of whether it's evaluating the
    sacred number 15 or the utterly unremarkable number 47. Fairness
    over efficiency, because in the FizzBuzz kernel, all modulo operations
    are created equal (even though some are more FizzBuzz than others).
    """

    def __init__(self, time_quantum_ms: float = 10.0) -> None:
        self._time_quantum_ms = time_quantum_ms
        self._queue: collections.deque[FizzProcess] = collections.deque()
        self.context_switches: int = 0
        self.total_scheduled: int = 0

    @property
    def name(self) -> str:
        return f"RoundRobin(quantum={self._time_quantum_ms}ms)"

    def add_process(self, process: FizzProcess) -> None:
        """Add a process to the end of the run queue."""
        self._queue.append(process)

    def next_process(self) -> Optional[FizzProcess]:
        """Select the next process using round-robin order."""
        while self._queue:
            process = self._queue.popleft()
            if process.state == ProcessState.READY:
                self.total_scheduled += 1
                return process
            # Skip non-READY processes
        return None

    def preempt(self, process: FizzProcess) -> None:
        """Return a preempted process to the back of the queue."""
        if process.state == ProcessState.READY:
            self._queue.append(process)
            self.context_switches += 1

    def remove_process(self, pid: int) -> None:
        """Remove a process from the run queue."""
        self._queue = collections.deque(
            p for p in self._queue if p.pid != pid
        )

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    def get_queue_snapshot(self) -> list[int]:
        """Return PIDs in queue order for dashboard."""
        return [p.pid for p in self._queue]


class PriorityPreemptiveScheduler:
    """Priority-based preemptive scheduler with 4 priority queues.

    Higher-priority processes preempt lower-priority ones, because in
    the FizzBuzz kernel, a FizzBuzz evaluation (divisible by 15) is
    simply more important than a Fizz evaluation (divisible by only 3).
    This mirrors the real world, where some computations are more equal
    than others, and the scheduler is the benevolent dictator that
    decides who runs next.
    """

    def __init__(self) -> None:
        self._queues: dict[ProcessPriority, collections.deque[FizzProcess]] = {
            ProcessPriority.REALTIME: collections.deque(),
            ProcessPriority.HIGH: collections.deque(),
            ProcessPriority.NORMAL: collections.deque(),
            ProcessPriority.LOW: collections.deque(),
        }
        self.context_switches: int = 0
        self.total_scheduled: int = 0

    @property
    def name(self) -> str:
        return "PriorityPreemptive(4-queue)"

    def add_process(self, process: FizzProcess) -> None:
        """Add a process to the appropriate priority queue."""
        self._queues[process.priority].append(process)

    def next_process(self) -> Optional[FizzProcess]:
        """Select the highest-priority ready process."""
        for priority in ProcessPriority:
            queue = self._queues[priority]
            while queue:
                process = queue.popleft()
                if process.state == ProcessState.READY:
                    self.total_scheduled += 1
                    return process
        return None

    def should_preempt(self, running: FizzProcess, candidate: FizzProcess) -> bool:
        """Check if the candidate should preempt the running process."""
        return candidate.priority.value < running.priority.value

    def preempt(self, process: FizzProcess) -> None:
        """Return a preempted process to its priority queue."""
        if process.state == ProcessState.READY:
            self._queues[process.priority].append(process)
            self.context_switches += 1

    def remove_process(self, pid: int) -> None:
        """Remove a process from all queues."""
        for queue in self._queues.values():
            # Rebuild queue without the target PID
            remaining = collections.deque(p for p in queue if p.pid != pid)
            queue.clear()
            queue.extend(remaining)

    @property
    def queue_depth(self) -> int:
        return sum(len(q) for q in self._queues.values())

    def get_queue_snapshot(self) -> dict[str, list[int]]:
        """Return PIDs per priority level for dashboard."""
        return {
            p.name: [proc.pid for proc in q]
            for p, q in self._queues.items()
        }


class CompletelyFairScheduler:
    """Completely Fair Scheduler (CFS) inspired by the Linux kernel.

    Tracks virtual runtime for each process, weighted by priority.
    Higher-priority processes accumulate virtual runtime more slowly,
    so they get more actual CPU time. This is exactly how Linux
    schedules processes, except Linux has billions of users and we
    have one person running FizzBuzz on their laptop.

    The vruntime tree is implemented as a sorted list because we don't
    have a red-black tree in stdlib, and implementing one for a FizzBuzz
    kernel would be... actually, it would be perfectly on-brand.
    """

    def __init__(
        self,
        default_weight: int = 1024,
        min_granularity_ms: float = 1.0,
    ) -> None:
        self._default_weight = default_weight
        self._min_granularity_ms = min_granularity_ms
        self._processes: dict[int, FizzProcess] = {}
        self.context_switches: int = 0
        self.total_scheduled: int = 0

    @property
    def name(self) -> str:
        return f"CFS(weight={self._default_weight})"

    # CFS weight table (mirroring Linux nice levels, simplified)
    _PRIORITY_WEIGHTS: dict[ProcessPriority, int] = {
        ProcessPriority.REALTIME: 4096,   # 4x the CPU time
        ProcessPriority.HIGH: 2048,       # 2x the CPU time
        ProcessPriority.NORMAL: 1024,     # Baseline
        ProcessPriority.LOW: 256,         # 1/4 the CPU time
    }

    def add_process(self, process: FizzProcess) -> None:
        """Add a process to the CFS tree."""
        process.weight = self._PRIORITY_WEIGHTS.get(process.priority, self._default_weight)
        self._processes[process.pid] = process

    def next_process(self) -> Optional[FizzProcess]:
        """Select the process with the smallest virtual runtime."""
        ready = [
            p for p in self._processes.values()
            if p.state == ProcessState.READY
        ]
        if not ready:
            return None

        # Pick the process with minimum vruntime (CFS core algorithm)
        selected = min(ready, key=lambda p: p.virtual_runtime_ns)
        self.total_scheduled += 1
        return selected

    def update_vruntime(self, process: FizzProcess, actual_ns: int) -> None:
        """Update virtual runtime after execution.

        vruntime += actual_time * (default_weight / process_weight)

        Higher-weight processes advance their vruntime more slowly,
        so they get selected more often. This is the core CFS insight:
        fairness through weighted virtual time.
        """
        weight = max(1, process.weight)
        delta_vruntime = int(actual_ns * (self._default_weight / weight))
        process.virtual_runtime_ns += delta_vruntime

    def preempt(self, process: FizzProcess) -> None:
        """Process was preempted -- vruntime already updated."""
        self.context_switches += 1

    def remove_process(self, pid: int) -> None:
        """Remove a process from the CFS tree."""
        self._processes.pop(pid, None)

    @property
    def queue_depth(self) -> int:
        return sum(1 for p in self._processes.values() if p.state == ProcessState.READY)

    def get_vruntime_snapshot(self) -> list[dict[str, Any]]:
        """Return vruntime data for dashboard."""
        return sorted(
            [
                {
                    "pid": p.pid,
                    "vruntime_ns": p.virtual_runtime_ns,
                    "weight": p.weight,
                    "state": p.state.name,
                }
                for p in self._processes.values()
            ],
            key=lambda x: x["vruntime_ns"],
        )


# ── Interrupt Controller ───────────────────────────────────────────


class InterruptController:
    """Interrupt controller with 16 IRQ vectors.

    Manages hardware and software interrupts for the FizzBuzz kernel.
    In a real system, interrupts handle I/O completion, timer ticks,
    and hardware events. In the FizzBuzz kernel, they handle the
    earth-shattering events of "a number was divisible by 3" and
    "the timer quantum expired."

    Supports interrupt masking, because sometimes you need to disable
    interrupts while performing critical modulo operations. The kernel
    will not be interrupted during division.
    """

    # Well-known IRQ assignments (because every kernel needs an IRQ map)
    IRQ_TIMER = 0
    IRQ_SCHEDULER = 1
    IRQ_PAGE_FAULT = 2
    IRQ_SYSCALL = 3
    IRQ_FIZZ = 4
    IRQ_BUZZ = 5
    IRQ_FIZZBUZZ = 6
    IRQ_PROCESS_EXIT = 7
    IRQ_CONTEXT_SWITCH = 8
    IRQ_TLB_FLUSH = 9
    IRQ_KEYBOARD = 10   # There is no keyboard, but we reserve the IRQ anyway
    IRQ_NETWORK = 11    # There is no network either
    IRQ_DISK = 12       # There is definitely no disk
    IRQ_SPARE_13 = 13
    IRQ_SPARE_14 = 14
    IRQ_PANIC = 15

    def __init__(self, num_vectors: int = 16) -> None:
        self._num_vectors = num_vectors
        self._handlers: dict[int, tuple[str, Callable[..., None]]] = {}
        self._mask: int = 0  # Bitmask: 1 = masked (disabled)
        self._log: list[dict[str, Any]] = []
        self.total_interrupts: int = 0

    def register_handler(
        self,
        irq: int,
        name: str,
        handler: Callable[..., None],
    ) -> None:
        """Register an interrupt handler on an IRQ vector."""
        if irq < 0 or irq >= self._num_vectors:
            raise KernelPanicError(f"IRQ {irq} out of range [0, {self._num_vectors})")
        if irq in self._handlers:
            existing_name, _ = self._handlers[irq]
            raise InterruptConflictError(irq, existing_name, name)
        self._handlers[irq] = (name, handler)
        logger.debug("IRQ %d: registered handler '%s'", irq, name)

    def fire(self, irq: int, **kwargs: Any) -> None:
        """Fire an interrupt on the specified IRQ vector."""
        if irq < 0 or irq >= self._num_vectors:
            return

        # Check mask
        if self._mask & (1 << irq):
            logger.debug("IRQ %d masked -- interrupt suppressed", irq)
            return

        self.total_interrupts += 1
        entry = {
            "irq": irq,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "handler": self._handlers.get(irq, ("unhandled", None))[0],
            "kwargs": {k: str(v)[:50] for k, v in kwargs.items()},
        }
        self._log.append(entry)

        if irq in self._handlers:
            _, handler = self._handlers[irq]
            try:
                handler(**kwargs)
            except Exception as exc:
                logger.warning("IRQ %d handler raised: %s", irq, exc)
        else:
            logger.debug("IRQ %d fired but no handler registered", irq)

    def mask(self, irq: int) -> None:
        """Mask (disable) an IRQ vector."""
        self._mask |= (1 << irq)

    def unmask(self, irq: int) -> None:
        """Unmask (enable) an IRQ vector."""
        self._mask &= ~(1 << irq)

    def mask_all(self) -> None:
        """Disable all interrupts (cli)."""
        self._mask = (1 << self._num_vectors) - 1

    def unmask_all(self) -> None:
        """Enable all interrupts (sti)."""
        self._mask = 0

    def get_log(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the last N interrupt log entries."""
        return self._log[-limit:]

    def get_handler_map(self) -> dict[int, str]:
        """Return IRQ -> handler name mapping for dashboard."""
        return {irq: name for irq, (name, _) in self._handlers.items()}


# ── System Call Interface ──────────────────────────────────────────


class SyscallInterface:
    """System call interface for the FizzBuzz kernel.

    Provides the blessed boundary between user-space FizzBuzz programs
    and the kernel's sacred internals. Just like a real OS, user-space
    code cannot directly access hardware (the modulo operator) without
    going through a system call. The overhead is staggering. The
    enterprise value is immeasurable.
    """

    SYSCALL_EVALUATE = 0x01
    SYSCALL_FORK = 0x02
    SYSCALL_EXIT = 0x03
    SYSCALL_YIELD = 0x04
    SYSCALL_GETPID = 0x05
    SYSCALL_MMAP = 0x06

    def __init__(self, kernel: FizzBuzzKernel) -> None:
        self._kernel = kernel
        self.total_syscalls: int = 0
        self._syscall_log: list[dict[str, Any]] = []

    def sys_evaluate(self, pid: int, number: int) -> Optional[FizzBuzzResult]:
        """Evaluate a number through the FizzBuzz pipeline via syscall.

        This is the most important system call in the kernel. It wraps
        the act of computing n % 3 and n % 5 in enough ceremony to
        make POSIX blush.
        """
        self.total_syscalls += 1
        self._log_syscall("sys_evaluate", pid=pid, number=number)

        process = self._kernel.get_process(pid)
        if process is None:
            return None

        # Load number into r0 (the accumulator)
        process.registers.r0 = number

        # Evaluate using the kernel's rule engine
        result = self._kernel.evaluate_number(number)

        # Store result
        process.result = result
        process.registers.r2 = 1 if result.matched_rules else 0
        return result

    def sys_fork(self, parent_pid: int) -> int:
        """Fork a FizzBuzz process. Returns the child PID.

        Creates a child process that inherits the parent's number
        and priority. In a real OS, fork() copies the entire address
        space. Here, it copies an integer and some metadata, which
        is still more copying than FizzBuzz actually requires.
        """
        self.total_syscalls += 1
        self._log_syscall("sys_fork", parent_pid=parent_pid)

        parent = self._kernel.get_process(parent_pid)
        if parent is None:
            return -1

        child = self._kernel.spawn_process(
            parent.number,
            parent_pid=parent_pid,
        )
        return child.pid

    def sys_exit(self, pid: int, exit_code: int = 0) -> None:
        """Terminate a FizzBuzz process.

        The process transitions to ZOMBIE state (because it has terminated
        but its parent hasn't called wait()), then to TERMINATED once the
        kernel cleans up. Circle of life.
        """
        self.total_syscalls += 1
        self._log_syscall("sys_exit", pid=pid, exit_code=exit_code)

        process = self._kernel.get_process(pid)
        if process is None:
            return

        process.exit_code = exit_code
        process.transition_to(ProcessState.ZOMBIE)

    def sys_yield(self, pid: int) -> None:
        """Voluntarily yield the CPU to another FizzBuzz process.

        A process that yields is politely saying "I've done enough modulo
        for now, let someone else have a turn." This is the cooperative
        scheduling escape hatch in an otherwise preemptive kernel.
        """
        self.total_syscalls += 1
        self._log_syscall("sys_yield", pid=pid)

        process = self._kernel.get_process(pid)
        if process is None:
            return

        if process.state == ProcessState.RUNNING:
            process.transition_to(ProcessState.READY)

    def _log_syscall(self, name: str, **kwargs: Any) -> None:
        """Log a system call for audit purposes."""
        self._syscall_log.append({
            "syscall": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **{k: str(v) for k, v in kwargs.items()},
        })

    def get_log(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the last N syscall log entries."""
        return self._syscall_log[-limit:]


# ── FizzBuzz Kernel ────────────────────────────────────────────────


class FizzBuzzKernel:
    """The FizzBuzz Operating System Kernel.

    Orchestrates process creation, scheduling, memory management,
    interrupt handling, and FizzBuzz evaluation. This is the beating
    heart of the most over-engineered modulo arithmetic platform ever
    conceived. Every number in the evaluation range becomes a process
    with its own PID, PCB, virtual address space, and scheduling
    priority. The kernel boots, spawns processes, runs the scheduler,
    handles interrupts, and shuts down -- all to compute the same
    results as `for i in range(1, 101): print("Fizz"*(i%3==0) + "Buzz"*(i%5==0) or i)`.

    Boot sequence:
        1. POST (Power-On Self Test) -- verify kernel integrity
        2. Memory initialization -- set up VMM
        3. Interrupt controller setup -- register IRQ handlers
        4. Scheduler initialization -- prepare run queues
        5. Syscall interface -- register system call table
        6. Driver probing -- detect "hardware" (there is none)
    """

    def __init__(
        self,
        rules: list[RuleDefinition],
        scheduler_type: SchedulerAlgorithm = SchedulerAlgorithm.ROUND_ROBIN,
        time_quantum_ms: float = 10.0,
        max_processes: int = 256,
        page_size: int = 64,
        tlb_size: int = 16,
        physical_pages: int = 128,
        swap_pages: int = 256,
        irq_vectors: int = 16,
        boot_delay_ms: float = 5.0,
        context_switch_overhead_us: float = 50.0,
        cfs_default_weight: int = 1024,
        cfs_min_granularity_ms: float = 1.0,
        event_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        self._rules = rules
        self._scheduler_type = scheduler_type
        self._time_quantum_ms = time_quantum_ms
        self._max_processes = max_processes
        self._boot_delay_ms = boot_delay_ms
        self._context_switch_overhead_us = context_switch_overhead_us
        self._event_callback = event_callback

        # Subsystems (initialized during boot)
        self._vmm = VirtualMemoryManager(
            tlb_size=tlb_size,
            physical_pages=physical_pages,
            swap_pages=swap_pages,
            page_size=page_size,
        )
        self._interrupts = InterruptController(num_vectors=irq_vectors)
        self._syscall = SyscallInterface(self)

        # Scheduler
        if scheduler_type == SchedulerAlgorithm.ROUND_ROBIN:
            self._scheduler: Any = RoundRobinScheduler(time_quantum_ms=time_quantum_ms)
        elif scheduler_type == SchedulerAlgorithm.PRIORITY_PREEMPTIVE:
            self._scheduler = PriorityPreemptiveScheduler()
        elif scheduler_type == SchedulerAlgorithm.COMPLETELY_FAIR:
            self._scheduler = CompletelyFairScheduler(
                default_weight=cfs_default_weight,
                min_granularity_ms=cfs_min_granularity_ms,
            )
        else:
            self._scheduler = RoundRobinScheduler(time_quantum_ms=time_quantum_ms)

        # Process table
        self._processes: dict[int, FizzProcess] = {}
        self._next_pid: int = 1
        self._current_process: Optional[FizzProcess] = None

        # Kernel state
        self._booted: bool = False
        self._shutdown: bool = False
        self._boot_time_ns: int = 0
        self._total_context_switches: int = 0
        self._uptime_start_ns: int = 0

        # Evaluation results
        self._results: list[FizzBuzzResult] = []

        # Boot log
        self._boot_log: list[str] = []

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        """Emit a kernel event."""
        if self._event_callback:
            event = Event(
                event_type=event_type,
                payload=payload,
                source="FizzBuzzKernel",
            )
            self._event_callback(event)

    # ── Boot Sequence ────────────────────────────────────────

    def boot(self) -> None:
        """Execute the kernel boot sequence.

        A carefully choreographed sequence of initialization steps
        that transforms a Python object into a fully-operational
        FizzBuzz operating system. Each step is logged with the
        gravitas befitting a mainframe IPL.
        """
        if self._booted:
            raise KernelPanicError("Kernel already booted -- double boot detected")

        self._uptime_start_ns = time.perf_counter_ns()
        self._emit(EventType.KERNEL_BOOT_STARTED)

        self._boot_log.append("[BOOT] FizzBuzz Kernel v1.0.0 starting...")
        self._boot_log.append("[POST] Power-On Self Test...")
        self._boot_log.append("[POST]   Verifying modulo operator integrity... OK")
        self._boot_log.append("[POST]   Testing 15 % 3 == 0... PASS")
        self._boot_log.append("[POST]   Testing 15 % 5 == 0... PASS")
        self._boot_log.append("[POST]   Arithmetic Logic Unit: OPERATIONAL")

        # Memory initialization
        self._boot_log.append(f"[MEM]  Initializing Virtual Memory Manager...")
        self._boot_log.append(f"[MEM]    TLB: {self._vmm._tlb_size} entries (LRU)")
        self._boot_log.append(f"[MEM]    Physical pages: {self._vmm._physical_pages}")
        self._boot_log.append(f"[MEM]    Swap pages: {self._vmm._swap_pages}")
        self._boot_log.append(f"[MEM]    Page size: {self._vmm._page_size} bytes")

        # Interrupt controller
        self._boot_log.append(f"[IRQ]  Initializing Interrupt Controller ({self._interrupts._num_vectors} vectors)...")
        self._register_default_irq_handlers()
        self._boot_log.append("[IRQ]    Timer (IRQ 0): registered")
        self._boot_log.append("[IRQ]    Scheduler (IRQ 1): registered")
        self._boot_log.append("[IRQ]    Page Fault (IRQ 2): registered")
        self._boot_log.append("[IRQ]    Syscall (IRQ 3): registered")
        self._boot_log.append("[IRQ]    Fizz (IRQ 4): registered")
        self._boot_log.append("[IRQ]    Buzz (IRQ 5): registered")
        self._boot_log.append("[IRQ]    FizzBuzz (IRQ 6): registered")
        self._boot_log.append("[IRQ]    Process Exit (IRQ 7): registered")

        # Scheduler
        self._boot_log.append(f"[SCHED] Scheduler: {self._scheduler.name}")
        self._boot_log.append(f"[SCHED] Context switch overhead: {self._context_switch_overhead_us}us")

        # Driver probing (there are no drivers, but we probe anyway)
        self._boot_log.append("[DRV]  Probing hardware devices...")
        self._boot_log.append("[DRV]    /dev/fizz: Modulo-3 Coprocessor ... FOUND")
        self._boot_log.append("[DRV]    /dev/buzz: Modulo-5 Coprocessor ... FOUND")
        self._boot_log.append("[DRV]    /dev/null: Bit Bucket ............. FOUND")
        self._boot_log.append("[DRV]    /dev/random: Entropy Source ....... NOT FOUND (deterministic is better)")
        self._boot_log.append("[DRV]    /dev/feelings: Emotional I/O ..... NOT FOUND")

        # Syscall table
        self._boot_log.append("[SYS]  System call table initialized (6 syscalls)")

        # Simulated boot delay for dramatic effect
        if self._boot_delay_ms > 0:
            time.sleep(self._boot_delay_ms / 1000.0)

        self._boot_time_ns = time.perf_counter_ns() - self._uptime_start_ns
        self._booted = True

        self._boot_log.append(f"[BOOT] Kernel boot completed in {self._boot_time_ns / 1_000_000:.2f}ms")
        self._boot_log.append(f"[BOOT] {len(self._rules)} FizzBuzz rules loaded")
        self._boot_log.append("[BOOT] System ready. May your modulo operations be swift and accurate.")

        self._emit(EventType.KERNEL_BOOT_COMPLETED, boot_time_ms=self._boot_time_ns / 1_000_000)

    def _register_default_irq_handlers(self) -> None:
        """Register the built-in IRQ handlers."""
        self._interrupts.register_handler(
            InterruptController.IRQ_TIMER,
            "timer_tick",
            lambda **kw: logger.debug("Timer tick"),
        )
        self._interrupts.register_handler(
            InterruptController.IRQ_SCHEDULER,
            "scheduler_preempt",
            lambda **kw: logger.debug("Scheduler preemption"),
        )
        self._interrupts.register_handler(
            InterruptController.IRQ_PAGE_FAULT,
            "page_fault_handler",
            lambda **kw: logger.debug("Page fault: %s", kw),
        )
        self._interrupts.register_handler(
            InterruptController.IRQ_SYSCALL,
            "syscall_handler",
            lambda **kw: logger.debug("System call: %s", kw),
        )
        self._interrupts.register_handler(
            InterruptController.IRQ_FIZZ,
            "fizz_handler",
            lambda **kw: logger.debug("FIZZ interrupt!"),
        )
        self._interrupts.register_handler(
            InterruptController.IRQ_BUZZ,
            "buzz_handler",
            lambda **kw: logger.debug("BUZZ interrupt!"),
        )
        self._interrupts.register_handler(
            InterruptController.IRQ_FIZZBUZZ,
            "fizzbuzz_handler",
            lambda **kw: logger.debug("FIZZBUZZ interrupt! The sacred event!"),
        )
        self._interrupts.register_handler(
            InterruptController.IRQ_PROCESS_EXIT,
            "process_exit_handler",
            lambda **kw: logger.debug("Process exit: %s", kw),
        )

    # ── Process Management ───────────────────────────────────

    def spawn_process(
        self,
        number: int,
        parent_pid: Optional[int] = None,
    ) -> FizzProcess:
        """Spawn a new FizzBuzz process for evaluating a number."""
        if len(self._processes) >= self._max_processes:
            raise KernelPanicError(
                f"Process table full ({self._max_processes} processes). "
                f"The FizzBuzz kernel has reached its maximum process capacity."
            )

        pid = self._next_pid
        self._next_pid += 1

        priority = FizzProcess.auto_priority(number)
        process = FizzProcess(
            pid=pid,
            number=number,
            priority=priority,
            parent_pid=parent_pid,
        )

        # Initialize registers
        process.registers.r0 = number
        process.registers.pc = 0
        process.registers.sp = 0xFFFF

        # Allocate virtual memory (1 page per process for code, 1 for stack)
        try:
            process.virtual_pages = self._vmm.allocate_pages(pid, 2)
        except KernelPanicError:
            # Out of memory -- still create the process, just without pages
            process.virtual_pages = []

        self._processes[pid] = process
        self._scheduler.add_process(process)

        self._emit(
            EventType.KERNEL_PROCESS_SPAWNED,
            pid=pid,
            number=number,
            priority=priority.name,
        )

        return process

    def get_process(self, pid: int) -> Optional[FizzProcess]:
        """Get a process by PID."""
        return self._processes.get(pid)

    # ── Evaluation ───────────────────────────────────────────

    def evaluate_number(self, number: int) -> FizzBuzzResult:
        """Evaluate a single number using the loaded rules.

        This is the inner sanctum of the kernel -- where the actual
        modulo arithmetic happens. All the process management, virtual
        memory, and interrupt handling ultimately serves this one
        function: computing n % 3 and n % 5.
        """
        start_ns = time.perf_counter_ns()
        sorted_rules = sorted(self._rules, key=lambda r: r.priority)
        matches: list[RuleMatch] = []

        for rule_def in sorted_rules:
            if number % rule_def.divisor == 0:
                matches.append(RuleMatch(rule=rule_def, number=number))

        output = "".join(m.rule.label for m in matches) or str(number)
        elapsed_ns = time.perf_counter_ns() - start_ns

        result = FizzBuzzResult(
            number=number,
            output=output,
            matched_rules=matches,
            processing_time_ns=elapsed_ns,
        )

        # Fire appropriate interrupt
        if output == "FizzBuzz":
            self._interrupts.fire(InterruptController.IRQ_FIZZBUZZ, number=number)
        elif output == "Fizz":
            self._interrupts.fire(InterruptController.IRQ_FIZZ, number=number)
        elif output == "Buzz":
            self._interrupts.fire(InterruptController.IRQ_BUZZ, number=number)

        return result

    # ── Context Switching ────────────────────────────────────

    def _context_switch(self, old: Optional[FizzProcess], new: FizzProcess) -> None:
        """Perform a context switch between two processes.

        Saves the old process's registers, flushes the TLB (because
        address spaces are per-process), and restores the new process's
        registers. In a real OS, this would take microseconds of
        precious CPU time. Here, it takes nanoseconds of equally
        precious Python time.
        """
        if old is not None:
            old.save_context()
            old.context_switches += 1

        # Flush TLB on context switch (like a real MMU)
        self._vmm.flush_tlb()

        # Restore new process's context
        new.restore_context()
        new.last_scheduled_ns = time.perf_counter_ns()

        self._current_process = new
        self._total_context_switches += 1

        # Simulate context switch overhead
        if self._context_switch_overhead_us > 0:
            # Spin for the overhead duration (nanosecond precision)
            spin_end = time.perf_counter_ns() + int(self._context_switch_overhead_us * 1000)
            while time.perf_counter_ns() < spin_end:
                pass

        self._emit(
            EventType.KERNEL_CONTEXT_SWITCH,
            old_pid=old.pid if old else None,
            new_pid=new.pid,
        )

        # Fire context switch interrupt
        self._interrupts.fire(
            InterruptController.IRQ_SCHEDULER,
            old_pid=old.pid if old else None,
            new_pid=new.pid,
        )

    # ── Main Run Loop ────────────────────────────────────────

    def run(self, start: int, end: int) -> list[FizzBuzzResult]:
        """Run the FizzBuzz kernel: spawn processes, schedule, evaluate.

        This is the kernel's main loop. For each number in the range,
        a process is spawned. The scheduler then selects processes for
        execution, the kernel performs context switches, and evaluations
        happen through the syscall interface. The results are collected
        and returned in order, because despite all the scheduling chaos,
        the output must be deterministic. FizzBuzz is not a concurrent
        system (even though we pretend it is).
        """
        if not self._booted:
            raise KernelPanicError("Kernel not booted -- call boot() first")

        # Spawn a process for each number
        pid_to_number: dict[int, int] = {}
        for number in range(start, end + 1):
            proc = self.spawn_process(number)
            pid_to_number[proc.pid] = number

        # Run the scheduler until all processes are complete
        results_by_number: dict[int, FizzBuzzResult] = {}
        max_iterations = len(pid_to_number) * 3  # Safety valve

        iteration = 0
        while iteration < max_iterations:
            iteration += 1

            # Fire timer interrupt
            self._interrupts.fire(InterruptController.IRQ_TIMER)

            # Get next process from scheduler
            process = self._scheduler.next_process()
            if process is None:
                break  # All done

            # Context switch
            old_process = self._current_process
            if old_process is not None and old_process != process:
                if old_process.state == ProcessState.RUNNING:
                    old_process.transition_to(ProcessState.READY)
                    self._scheduler.preempt(old_process)
            self._context_switch(old_process, process)

            # Run the process
            process.transition_to(ProcessState.RUNNING)

            # Perform TLB translation (for the drama)
            if process.virtual_pages:
                try:
                    self._vmm.translate(process.pid, process.virtual_pages[0])
                except PageFaultError:
                    process.page_faults += 1
                    self._interrupts.fire(
                        InterruptController.IRQ_PAGE_FAULT,
                        pid=process.pid,
                        vpage=process.virtual_pages[0] if process.virtual_pages else -1,
                    )
                    self._emit(EventType.KERNEL_PAGE_FAULT, pid=process.pid)

            # Fire syscall interrupt
            self._interrupts.fire(
                InterruptController.IRQ_SYSCALL,
                pid=process.pid,
                syscall="sys_evaluate",
            )
            self._emit(EventType.KERNEL_SYSCALL_INVOKED, pid=process.pid, syscall="sys_evaluate")

            # Evaluate through syscall interface
            exec_start_ns = time.perf_counter_ns()
            result = self._syscall.sys_evaluate(process.pid, process.number)
            exec_elapsed_ns = time.perf_counter_ns() - exec_start_ns

            # Update CPU time
            process.cpu_time_ns += exec_elapsed_ns

            # Update CFS vruntime if using CFS
            if isinstance(self._scheduler, CompletelyFairScheduler):
                self._scheduler.update_vruntime(process, exec_elapsed_ns)

            # Store result
            if result is not None:
                results_by_number[process.number] = result

            # Terminate the process
            process.transition_to(ProcessState.ZOMBIE)
            self._interrupts.fire(
                InterruptController.IRQ_PROCESS_EXIT,
                pid=process.pid,
                exit_code=0,
            )
            self._emit(
                EventType.KERNEL_PROCESS_TERMINATED,
                pid=process.pid,
                number=process.number,
            )

            # Clean up zombie -> terminated
            process.exit_code = 0
            process.transition_to(ProcessState.TERMINATED)

            # Free memory
            self._vmm.free_process_pages(process.pid)
            self._scheduler.remove_process(process.pid)

        # Collect results in order
        self._results = [
            results_by_number[n]
            for n in range(start, end + 1)
            if n in results_by_number
        ]

        return self._results

    # ── Shutdown ─────────────────────────────────────────────

    def shutdown(self) -> None:
        """Gracefully shut down the FizzBuzz kernel.

        All remaining processes are terminated, memory is freed,
        and the kernel logs its final statistics. The system is
        now safe to power off (close the Python interpreter).
        """
        if self._shutdown:
            return

        self._shutdown = True
        self._emit(EventType.KERNEL_SHUTDOWN)

        # Terminate any remaining processes
        for process in list(self._processes.values()):
            if process.state not in (ProcessState.TERMINATED, ProcessState.ZOMBIE):
                try:
                    process.transition_to(ProcessState.TERMINATED)
                except InvalidProcessStateError:
                    pass
                self._vmm.free_process_pages(process.pid)

        logger.debug("Kernel shutdown complete. %d processes handled.", len(self._processes))

    # ── Statistics and Dashboard ─────────────────────────────

    @property
    def uptime_ms(self) -> float:
        """Kernel uptime in milliseconds."""
        if self._uptime_start_ns == 0:
            return 0.0
        return (time.perf_counter_ns() - self._uptime_start_ns) / 1_000_000

    @property
    def process_count(self) -> int:
        return len(self._processes)

    @property
    def scheduler_name(self) -> str:
        return self._scheduler.name

    def get_process_table(self) -> list[dict[str, Any]]:
        """Return process table for dashboard display."""
        table = []
        for proc in sorted(self._processes.values(), key=lambda p: p.pid):
            table.append({
                "pid": proc.pid,
                "number": proc.number,
                "state": proc.state.name,
                "priority": proc.priority.name,
                "cpu_ns": proc.cpu_time_ns,
                "ctx_sw": proc.context_switches,
                "pf": proc.page_faults,
                "vruntime": proc.virtual_runtime_ns,
                "result": proc.result.output if proc.result else "-",
            })
        return table

    def get_boot_log(self) -> list[str]:
        """Return the kernel boot log."""
        return list(self._boot_log)

    def get_stats(self) -> dict[str, Any]:
        """Return comprehensive kernel statistics."""
        return {
            "uptime_ms": self.uptime_ms,
            "scheduler": self.scheduler_name,
            "total_processes": len(self._processes),
            "context_switches": self._total_context_switches,
            "total_interrupts": self._interrupts.total_interrupts,
            "total_syscalls": self._syscall.total_syscalls,
            "memory": self._vmm.get_stats(),
            "boot_time_ms": self._boot_time_ns / 1_000_000,
        }


# ── Kernel Dashboard ──────────────────────────────────────────────


class KernelDashboard:
    """ASCII dashboard for the FizzBuzz Operating System Kernel.

    Renders a multi-pane dashboard showing the process table, memory
    map, interrupt log, scheduler state, and kernel statistics. Because
    the only thing better than a FizzBuzz OS kernel is a terminal
    dashboard that visualizes every pointless detail of its operation.
    """

    @staticmethod
    def render(
        kernel: FizzBuzzKernel,
        width: int = 60,
        show_process_table: bool = True,
        show_memory_map: bool = True,
        show_interrupt_log: bool = True,
    ) -> str:
        """Render the complete kernel dashboard."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        thin = "+" + "-" * (width - 2) + "+"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "|  " + text.ljust(width - 4) + "|"

        # Header
        lines.append(border)
        lines.append(center("FIZZBUZZ OPERATING SYSTEM KERNEL"))
        lines.append(center("Process Management & Memory Dashboard"))
        lines.append(border)

        # Kernel stats
        stats = kernel.get_stats()
        lines.append(center("KERNEL STATISTICS"))
        lines.append(thin)
        lines.append(left(f"Scheduler: {stats['scheduler']}"))
        lines.append(left(f"Uptime: {stats['uptime_ms']:.2f}ms"))
        lines.append(left(f"Boot time: {stats['boot_time_ms']:.2f}ms"))
        lines.append(left(f"Total processes: {stats['total_processes']}"))
        lines.append(left(f"Context switches: {stats['context_switches']}"))
        lines.append(left(f"Interrupts fired: {stats['total_interrupts']}"))
        lines.append(left(f"System calls: {stats['total_syscalls']}"))

        # Memory stats
        mem = stats["memory"]
        lines.append(thin)
        lines.append(center("VIRTUAL MEMORY"))
        lines.append(thin)
        lines.append(left(f"TLB hit rate: {mem['tlb_hit_rate']}"))
        lines.append(left(f"TLB hits/misses: {mem['tlb_hits']}/{mem['tlb_misses']}"))
        lines.append(left(f"Page faults: {mem['page_faults']}"))
        lines.append(left(f"Free frames: {mem['free_frames']}"))
        lines.append(left(f"Swap used: {mem['swap_used']}"))
        lines.append(left(f"Swapped in/out: {mem['pages_swapped_in']}/{mem['pages_swapped_out']}"))

        # Process table
        if show_process_table:
            lines.append(thin)
            lines.append(center("PROCESS TABLE (top 20)"))
            lines.append(thin)
            header = f"{'PID':>5} {'NUM':>5} {'STATE':>10} {'PRI':>8} {'CPU(us)':>8} {'RESULT':>10}"
            lines.append(left(header))
            lines.append(left("-" * min(len(header), width - 6)))

            proc_table = kernel.get_process_table()[:20]
            for row in proc_table:
                cpu_us = row["cpu_ns"] / 1000
                line = f"{row['pid']:>5} {row['number']:>5} {row['state']:>10} {row['priority']:>8} {cpu_us:>8.1f} {row['result']:>10}"
                lines.append(left(line))

            if not proc_table:
                lines.append(left("  (no processes)"))

        # Interrupt log
        if show_interrupt_log:
            lines.append(thin)
            lines.append(center("INTERRUPT LOG (last 10)"))
            lines.append(thin)
            irq_log = kernel._interrupts.get_log(limit=10)
            for entry in irq_log:
                irq_line = f"IRQ {entry['irq']:>2} [{entry['handler']:<20}]"
                lines.append(left(irq_line))
            if not irq_log:
                lines.append(left("  (no interrupts fired)"))

        # IRQ Handler map
        lines.append(thin)
        lines.append(center("IRQ VECTOR MAP"))
        lines.append(thin)
        handler_map = kernel._interrupts.get_handler_map()
        for irq in sorted(handler_map.keys()):
            lines.append(left(f"  IRQ {irq:>2}: {handler_map[irq]}"))

        # Boot log (last 5 lines)
        lines.append(thin)
        lines.append(center("BOOT LOG (last 5)"))
        lines.append(thin)
        for log_line in kernel.get_boot_log()[-5:]:
            truncated = log_line[:width - 6]
            lines.append(left(truncated))

        lines.append(border)
        lines.append(center("Linus would be proud. Or horrified."))
        lines.append(border)

        return "\n".join("  " + ln for ln in lines)


# ── Kernel Middleware ─────────────────────────────────────────────


class KernelMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through the OS kernel.

    Intercepts each number in the processing pipeline and evaluates it
    as a kernel process -- complete with process spawning, scheduling,
    context switching, virtual memory page allocation, interrupt firing,
    and system calls. The result is identical to what StandardRuleEngine
    would produce, but with approximately 1000x more ceremony.

    Priority -10 ensures this runs very early in the middleware pipeline,
    because the kernel must have first dibs on every number.
    """

    def __init__(
        self,
        kernel: FizzBuzzKernel,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._kernel = kernel
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Route the evaluation through the kernel's process management."""
        number = context.number

        # Spawn a process for this number
        proc = self._kernel.spawn_process(number)

        # Transition to RUNNING (processes start as READY)
        proc.transition_to(ProcessState.RUNNING)

        # Execute through syscall interface
        exec_start = time.perf_counter_ns()
        result = self._kernel._syscall.sys_evaluate(proc.pid, number)
        exec_elapsed = time.perf_counter_ns() - exec_start

        # Update process stats
        proc.cpu_time_ns += exec_elapsed

        # Terminate the process: RUNNING -> ZOMBIE -> TERMINATED
        proc.transition_to(ProcessState.ZOMBIE)
        proc.exit_code = 0
        proc.transition_to(ProcessState.TERMINATED)
        self._kernel._vmm.free_process_pages(proc.pid)

        # Inject kernel metadata into context
        context.metadata["kernel_pid"] = proc.pid
        context.metadata["kernel_priority"] = proc.priority.name
        context.metadata["kernel_cpu_time_ns"] = proc.cpu_time_ns
        context.metadata["kernel_page_faults"] = proc.page_faults
        context.metadata["kernel_context_switches"] = proc.context_switches

        # If the kernel produced a result, attach it to the context
        if result is not None:
            context.results.append(result)
            # Short-circuit: kernel already evaluated, skip downstream engine
            return context

        # Fallback to downstream pipeline
        return next_handler(context)

    def get_name(self) -> str:
        return "KernelMiddleware"

    def get_priority(self) -> int:
        return -10
