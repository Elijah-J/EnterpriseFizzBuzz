"""
Enterprise FizzBuzz Platform - FizzHypervisor Type-1 Bare-Metal Hypervisor

Implements a Type-1 (bare-metal) hypervisor for hardware-isolated FizzBuzz
evaluation. Each FizzBuzz computation executes inside a dedicated virtual
machine with its own vCPU, virtualized memory via Extended Page Tables
(EPT) or Nested Page Tables (NPT), and a fully managed Virtual Machine
Control Structure (VMCS).

Running FizzBuzz directly on bare metal introduces unacceptable security
risks: a malicious modulo operation could corrupt adjacent memory, and
a rogue division could monopolize CPU time. The FizzHypervisor eliminates
these risks by trapping every sensitive operation via VM-exits, applying
fine-grained access control through EPT permissions, and scheduling vCPUs
with time-slice fairness guarantees.

Architecture:

    Hypervisor (VMM)
        ├── VMManager              (VM lifecycle: create, start, pause, destroy)
        │     ├── VM               (guest state, vCPUs, memory map)
        │     └── VMState          (created, running, paused, stopped)
        ├── VCPUScheduler          (round-robin vCPU-to-pCPU mapping)
        │     ├── TimeSlice        (configurable quantum per vCPU)
        │     └── SchedulingStats  (utilization, preemptions, migrations)
        ├── MemoryVirtualizer      (EPT/NPT page table management)
        │     ├── EPTEntry         (GPA → HPA mapping with R/W/X bits)
        │     ├── EPTPageTable     (4-level radix tree)
        │     └── TLBFlush         (INVEPT single/global context)
        ├── VMCSManager            (VMCS field read/write/validate)
        │     ├── GuestState       (RIP, RSP, RFLAGS, CR0-CR4, segments)
        │     └── HostState        (VMM re-entry point, stack, CR3)
        ├── VMExitRouter           (dispatch table for exit reasons)
        │     ├── IOExitHandler    (port I/O interception)
        │     ├── MSRExitHandler   (model-specific register traps)
        │     ├── CRAccessHandler  (control register access)
        │     └── HLTHandler       (halt instruction trap)
        └── HypervisorDashboard    (ASCII status display)

Each FizzBuzz evaluation creates a lightweight VM, loads the number into
guest memory, executes the divisibility check via a trapped instruction
sequence, and captures the result through a VM-exit handler.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZHYPERVISOR_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 250

MAX_VMS = 256
MAX_VCPUS_PER_VM = 16
MAX_PCPUS = 64
DEFAULT_TIME_SLICE_MS = 10
DEFAULT_MEMORY_MB = 128
EPT_LEVELS = 4
PAGE_SIZE = 4096
VMCS_FIELD_COUNT = 64

# VM-exit reason codes (subset of Intel SDM Vol. 3C, Appendix C)
VMEXIT_EXTERNAL_INTERRUPT = 1
VMEXIT_TRIPLE_FAULT = 2
VMEXIT_CPUID = 10
VMEXIT_HLT = 12
VMEXIT_IO_INSTRUCTION = 30
VMEXIT_MSR_READ = 31
VMEXIT_MSR_WRITE = 32
VMEXIT_CR_ACCESS = 28
VMEXIT_EPT_VIOLATION = 48
VMEXIT_EPT_MISCONFIG = 49


# ============================================================================
# Enums
# ============================================================================

class VMState(Enum):
    """Virtual machine lifecycle states."""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class EPTAccessType(Enum):
    """EPT access permission bits."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class VMExitReason(IntEnum):
    """Enumerated VM-exit reasons for the dispatch table."""
    EXTERNAL_INTERRUPT = VMEXIT_EXTERNAL_INTERRUPT
    TRIPLE_FAULT = VMEXIT_TRIPLE_FAULT
    CPUID = VMEXIT_CPUID
    HLT = VMEXIT_HLT
    IO_INSTRUCTION = VMEXIT_IO_INSTRUCTION
    MSR_READ = VMEXIT_MSR_READ
    MSR_WRITE = VMEXIT_MSR_WRITE
    CR_ACCESS = VMEXIT_CR_ACCESS
    EPT_VIOLATION = VMEXIT_EPT_VIOLATION
    EPT_MISCONFIG = VMEXIT_EPT_MISCONFIG


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class EPTEntry:
    """A single Extended Page Table entry mapping GPA to HPA.

    Each entry contains the host physical address, permission bits
    (read/write/execute), and a present bit indicating whether the
    mapping is valid. Absent entries trigger an EPT violation VM-exit.
    """
    guest_physical: int
    host_physical: int
    readable: bool = True
    writable: bool = True
    executable: bool = False
    present: bool = True


@dataclass
class VMCSField:
    """A single field in the Virtual Machine Control Structure.

    The VMCS holds all guest and host state required to perform
    VM-entry and VM-exit transitions. Fields are identified by a
    numeric encoding and store 64-bit values.
    """
    encoding: int
    name: str
    value: int = 0
    read_only: bool = False


@dataclass
class VCPUState:
    """Architectural state of a virtual CPU.

    Captures the complete register state that must be saved on VM-exit
    and restored on VM-entry. The FizzBuzz number under evaluation is
    stored in RAX, and the classification result appears in RBX.
    """
    vcpu_id: int
    rip: int = 0
    rsp: int = 0
    rax: int = 0
    rbx: int = 0
    rcx: int = 0
    rdx: int = 0
    rflags: int = 0x2  # Reserved bit always set
    cr0: int = 0x80000011  # PE + ET + PG
    cr3: int = 0
    cr4: int = 0x2000  # VMXE
    assigned_pcpu: int = -1
    time_slice_ms: int = DEFAULT_TIME_SLICE_MS
    total_cycles: int = 0
    preemptions: int = 0


@dataclass
class SchedulingStats:
    """Aggregated vCPU scheduling statistics across the hypervisor."""
    total_dispatches: int = 0
    total_preemptions: int = 0
    total_migrations: int = 0
    pcpu_utilization: dict[int, float] = field(default_factory=dict)


@dataclass
class VMExitRecord:
    """Record of a single VM-exit event for diagnostics."""
    vm_name: str
    reason: int
    timestamp: float = 0.0
    handled: bool = False
    handler_name: str = ""


# ============================================================================
# EPT Page Table
# ============================================================================

class EPTPageTable:
    """4-level Extended Page Table for GPA → HPA translation.

    The EPT mirrors the hardware page table walker: a guest physical
    address is split into four 9-bit indices plus a 12-bit page offset.
    Each level of the table resolves one index until the final HPA is
    produced. If any level is absent, an EPT violation is raised.
    """

    def __init__(self) -> None:
        self._entries: dict[int, EPTEntry] = {}
        self._stats = {"lookups": 0, "hits": 0, "violations": 0}

    def map_page(self, gpa: int, hpa: int, **kwargs: Any) -> EPTEntry:
        """Install a GPA → HPA mapping in the page table."""
        page_gpa = gpa & ~(PAGE_SIZE - 1)
        entry = EPTEntry(
            guest_physical=page_gpa,
            host_physical=hpa,
            readable=kwargs.get("readable", True),
            writable=kwargs.get("writable", True),
            executable=kwargs.get("executable", False),
        )
        self._entries[page_gpa] = entry
        return entry

    def unmap_page(self, gpa: int) -> bool:
        """Remove a GPA mapping. Returns True if the mapping existed."""
        page_gpa = gpa & ~(PAGE_SIZE - 1)
        return self._entries.pop(page_gpa, None) is not None

    def translate(self, gpa: int, access: EPTAccessType) -> Optional[int]:
        """Translate a GPA to an HPA, checking permissions.

        Returns the HPA on success, or None if the translation fails
        (triggering an EPT violation).
        """
        self._stats["lookups"] += 1
        page_gpa = gpa & ~(PAGE_SIZE - 1)
        offset = gpa & (PAGE_SIZE - 1)

        entry = self._entries.get(page_gpa)
        if entry is None or not entry.present:
            self._stats["violations"] += 1
            return None

        if access == EPTAccessType.READ and not entry.readable:
            self._stats["violations"] += 1
            return None
        if access == EPTAccessType.WRITE and not entry.writable:
            self._stats["violations"] += 1
            return None
        if access == EPTAccessType.EXECUTE and not entry.executable:
            self._stats["violations"] += 1
            return None

        self._stats["hits"] += 1
        return entry.host_physical + offset

    def page_count(self) -> int:
        """Return the number of mapped pages."""
        return len(self._entries)

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)


# ============================================================================
# VMCS Manager
# ============================================================================

class VMCSManager:
    """Manages the Virtual Machine Control Structure for a single VM.

    The VMCS is the hardware data structure that Intel VT-x uses to
    store guest and host state during VM transitions. This manager
    provides typed read/write access and validation of critical fields.
    """

    GUEST_RIP = 0x681E
    GUEST_RSP = 0x681C
    GUEST_RFLAGS = 0x6820
    GUEST_CR0 = 0x6800
    GUEST_CR3 = 0x6802
    GUEST_CR4 = 0x6804
    HOST_RIP = 0x6C16
    HOST_RSP = 0x6C14
    HOST_CR3 = 0x6C02
    VM_EXIT_REASON = 0x4402

    def __init__(self) -> None:
        self._fields: dict[int, VMCSField] = {}
        self._init_fields()

    def _init_fields(self) -> None:
        """Initialize standard VMCS fields with default values."""
        defaults = [
            (self.GUEST_RIP, "GUEST_RIP", 0, False),
            (self.GUEST_RSP, "GUEST_RSP", 0, False),
            (self.GUEST_RFLAGS, "GUEST_RFLAGS", 0x2, False),
            (self.GUEST_CR0, "GUEST_CR0", 0x80000011, False),
            (self.GUEST_CR3, "GUEST_CR3", 0, False),
            (self.GUEST_CR4, "GUEST_CR4", 0x2000, False),
            (self.HOST_RIP, "HOST_RIP", 0, False),
            (self.HOST_RSP, "HOST_RSP", 0, False),
            (self.HOST_CR3, "HOST_CR3", 0, False),
            (self.VM_EXIT_REASON, "VM_EXIT_REASON", 0, True),
        ]
        for encoding, name, value, ro in defaults:
            self._fields[encoding] = VMCSField(encoding, name, value, ro)

    def read(self, encoding: int) -> int:
        """Read a VMCS field by encoding."""
        f = self._fields.get(encoding)
        if f is None:
            return 0
        return f.value

    def write(self, encoding: int, value: int) -> bool:
        """Write a VMCS field. Returns False if the field is read-only."""
        f = self._fields.get(encoding)
        if f is None:
            self._fields[encoding] = VMCSField(encoding, f"FIELD_{encoding:#x}", value)
            return True
        if f.read_only:
            return False
        f.value = value
        return True

    def field_count(self) -> int:
        return len(self._fields)

    def validate(self) -> list[str]:
        """Validate VMCS consistency. Returns list of error messages."""
        errors = []
        cr0 = self.read(self.GUEST_CR0)
        if not (cr0 & 1):
            errors.append("GUEST_CR0.PE (Protected Mode Enable) not set")
        cr4 = self.read(self.GUEST_CR4)
        if not (cr4 & 0x2000):
            errors.append("GUEST_CR4.VMXE not set")
        return errors


# ============================================================================
# VM-Exit Router
# ============================================================================

class VMExitHandler:
    """Base class for VM-exit reason handlers."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.invocations = 0

    def handle(self, vm: "VirtualMachine", exit_reason: int) -> bool:
        """Handle a VM-exit. Returns True if handled."""
        self.invocations += 1
        return True


class IOExitHandler(VMExitHandler):
    """Handles port I/O instruction exits."""

    def __init__(self) -> None:
        super().__init__("io_instruction")

    def handle(self, vm: "VirtualMachine", exit_reason: int) -> bool:
        super().handle(vm, exit_reason)
        return exit_reason == VMEXIT_IO_INSTRUCTION


class HLTExitHandler(VMExitHandler):
    """Handles HLT instruction exits, transitioning the VM to paused."""

    def __init__(self) -> None:
        super().__init__("hlt")

    def handle(self, vm: "VirtualMachine", exit_reason: int) -> bool:
        super().handle(vm, exit_reason)
        if exit_reason == VMEXIT_HLT:
            vm.state = VMState.PAUSED
            return True
        return False


class CPUIDExitHandler(VMExitHandler):
    """Handles CPUID instruction exits with synthetic leaf data."""

    def __init__(self) -> None:
        super().__init__("cpuid")

    def handle(self, vm: "VirtualMachine", exit_reason: int) -> bool:
        super().handle(vm, exit_reason)
        return exit_reason == VMEXIT_CPUID


class EPTViolationHandler(VMExitHandler):
    """Handles EPT violation exits by logging the faulting address."""

    def __init__(self) -> None:
        super().__init__("ept_violation")

    def handle(self, vm: "VirtualMachine", exit_reason: int) -> bool:
        super().handle(vm, exit_reason)
        return exit_reason == VMEXIT_EPT_VIOLATION


class VMExitRouter:
    """Routes VM-exit events to the appropriate handler.

    The router maintains a dispatch table mapping exit reason codes
    to handler objects. When a VM-exit occurs, the router iterates
    through registered handlers until one claims the exit.
    """

    def __init__(self) -> None:
        self._handlers: dict[int, VMExitHandler] = {}
        self._exit_log: list[VMExitRecord] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        self._handlers[VMEXIT_IO_INSTRUCTION] = IOExitHandler()
        self._handlers[VMEXIT_HLT] = HLTExitHandler()
        self._handlers[VMEXIT_CPUID] = CPUIDExitHandler()
        self._handlers[VMEXIT_EPT_VIOLATION] = EPTViolationHandler()

    def register_handler(self, reason: int, handler: VMExitHandler) -> None:
        self._handlers[reason] = handler

    def route(self, vm: "VirtualMachine", exit_reason: int) -> bool:
        """Route a VM-exit to the appropriate handler.

        Returns True if the exit was handled, False otherwise.
        """
        record = VMExitRecord(
            vm_name=vm.name,
            reason=exit_reason,
            timestamp=time.time(),
        )

        handler = self._handlers.get(exit_reason)
        if handler is not None:
            result = handler.handle(vm, exit_reason)
            record.handled = result
            record.handler_name = handler.name
            self._exit_log.append(record)
            return result

        self._exit_log.append(record)
        return False

    @property
    def exit_log(self) -> list[VMExitRecord]:
        return list(self._exit_log)

    @property
    def handler_count(self) -> int:
        return len(self._handlers)


# ============================================================================
# Virtual Machine
# ============================================================================

class VirtualMachine:
    """A single virtual machine managed by the hypervisor.

    Each VM encapsulates a set of vCPUs, an EPT page table for memory
    virtualization, a VMCS for hardware state management, and the guest
    memory contents. The VM lifecycle follows a strict state machine:
    CREATED → RUNNING → PAUSED/STOPPED.
    """

    def __init__(self, name: str, vcpu_count: int = 1, memory_mb: int = DEFAULT_MEMORY_MB) -> None:
        self.name = name
        self.state = VMState.CREATED
        self.vcpus: list[VCPUState] = [
            VCPUState(vcpu_id=i) for i in range(vcpu_count)
        ]
        self.memory_mb = memory_mb
        self.ept = EPTPageTable()
        self.vmcs = VMCSManager()
        self.guest_memory: dict[int, int] = {}
        self.created_at = time.time()
        self._exit_count = 0

        # Map initial memory pages (1 page per MB for simulation)
        for i in range(memory_mb):
            gpa = i * PAGE_SIZE
            hpa = hash((name, i)) & 0xFFFFFFFF
            self.ept.map_page(gpa, hpa)

    def start(self) -> bool:
        """Transition the VM to RUNNING state."""
        if self.state not in (VMState.CREATED, VMState.PAUSED):
            return False
        self.state = VMState.RUNNING
        return True

    def pause(self) -> bool:
        """Transition the VM to PAUSED state."""
        if self.state != VMState.RUNNING:
            return False
        self.state = VMState.PAUSED
        return True

    def stop(self) -> bool:
        """Transition the VM to STOPPED state."""
        if self.state == VMState.STOPPED:
            return False
        self.state = VMState.STOPPED
        return True

    def write_guest_memory(self, gpa: int, value: int) -> bool:
        """Write a value to guest physical memory."""
        hpa = self.ept.translate(gpa, EPTAccessType.WRITE)
        if hpa is None:
            return False
        self.guest_memory[gpa] = value
        return True

    def read_guest_memory(self, gpa: int) -> Optional[int]:
        """Read a value from guest physical memory."""
        hpa = self.ept.translate(gpa, EPTAccessType.READ)
        if hpa is None:
            return None
        return self.guest_memory.get(gpa, 0)

    def record_exit(self) -> None:
        self._exit_count += 1

    @property
    def exit_count(self) -> int:
        return self._exit_count


# ============================================================================
# vCPU Scheduler
# ============================================================================

class VCPUScheduler:
    """Round-robin vCPU scheduler with configurable time slices.

    Maps virtual CPUs to physical CPUs using a simple round-robin
    policy. Each vCPU receives a fixed time quantum; when the quantum
    expires, the vCPU is preempted and the next runnable vCPU is
    dispatched. This ensures fair CPU allocation among competing
    FizzBuzz VMs.
    """

    def __init__(self, pcpu_count: int = 4) -> None:
        self.pcpu_count = pcpu_count
        self._run_queue: list[VCPUState] = []
        self._stats = SchedulingStats()
        self._next_pcpu = 0

    def enqueue(self, vcpu: VCPUState) -> None:
        """Add a vCPU to the scheduling run queue."""
        self._run_queue.append(vcpu)

    def dispatch(self) -> Optional[VCPUState]:
        """Select the next vCPU to run and assign it to a pCPU.

        Returns the dispatched vCPU, or None if the queue is empty.
        """
        if not self._run_queue:
            return None

        vcpu = self._run_queue.pop(0)
        vcpu.assigned_pcpu = self._next_pcpu
        self._next_pcpu = (self._next_pcpu + 1) % self.pcpu_count
        self._stats.total_dispatches += 1
        vcpu.total_cycles += vcpu.time_slice_ms
        return vcpu

    def preempt(self, vcpu: VCPUState) -> None:
        """Preempt a running vCPU and return it to the run queue."""
        vcpu.preemptions += 1
        self._stats.total_preemptions += 1
        self._run_queue.append(vcpu)

    @property
    def queue_depth(self) -> int:
        return len(self._run_queue)

    @property
    def stats(self) -> SchedulingStats:
        return self._stats


# ============================================================================
# Hypervisor
# ============================================================================

class Hypervisor:
    """Type-1 bare-metal hypervisor for FizzBuzz evaluation.

    The Hypervisor is the top-level component that manages VM
    lifecycles, coordinates vCPU scheduling across physical cores,
    routes VM-exits, and provides a unified interface for creating
    and destroying FizzBuzz VMs.
    """

    def __init__(self, pcpu_count: int = 4) -> None:
        self.pcpu_count = pcpu_count
        self._vms: dict[str, VirtualMachine] = {}
        self.scheduler = VCPUScheduler(pcpu_count)
        self.exit_router = VMExitRouter()
        self._total_evaluations = 0

    def create_vm(self, name: str, vcpu_count: int = 1, memory_mb: int = DEFAULT_MEMORY_MB) -> VirtualMachine:
        """Create a new virtual machine."""
        if name in self._vms:
            raise ValueError(f"VM '{name}' already exists")
        if len(self._vms) >= MAX_VMS:
            raise ValueError(f"Maximum VM count ({MAX_VMS}) reached")

        vm = VirtualMachine(name, vcpu_count, memory_mb)
        self._vms[name] = vm

        logger.debug("Created VM '%s' with %d vCPUs and %d MB memory",
                      name, vcpu_count, memory_mb)
        return vm

    def destroy_vm(self, name: str) -> bool:
        """Destroy a virtual machine and free its resources."""
        vm = self._vms.pop(name, None)
        if vm is None:
            return False
        vm.stop()
        return True

    def get_vm(self, name: str) -> Optional[VirtualMachine]:
        return self._vms.get(name)

    def evaluate_fizzbuzz(self, number: int) -> str:
        """Evaluate FizzBuzz for a number inside a transient VM.

        Creates a temporary VM, writes the number to guest memory,
        performs the divisibility check, captures the result, and
        destroys the VM. This ensures complete hardware isolation
        for every FizzBuzz evaluation.
        """
        vm_name = f"fizz_vm_{number}_{self._total_evaluations}"
        vm = self.create_vm(vm_name, vcpu_count=1, memory_mb=1)
        vm.start()

        # Write number to guest memory at GPA 0x0
        vm.write_guest_memory(0x0, number)

        # Schedule the vCPU
        self.scheduler.enqueue(vm.vcpus[0])
        vcpu = self.scheduler.dispatch()

        # Perform FizzBuzz evaluation (simulated instruction sequence)
        if number % 15 == 0:
            result = "FizzBuzz"
        elif number % 3 == 0:
            result = "Fizz"
        elif number % 5 == 0:
            result = "Buzz"
        else:
            result = str(number)

        # Simulate a VM-exit for the result delivery
        vm.record_exit()
        self.exit_router.route(vm, VMEXIT_HLT)

        # Write result encoding to guest memory
        result_code = {"Fizz": 1, "Buzz": 2, "FizzBuzz": 3}.get(result, 0)
        vm.write_guest_memory(0x1000, result_code)

        self._total_evaluations += 1
        self.destroy_vm(vm_name)

        return result

    @property
    def vm_count(self) -> int:
        return len(self._vms)

    @property
    def total_evaluations(self) -> int:
        return self._total_evaluations

    def vm_names(self) -> list[str]:
        return list(self._vms.keys())


# ============================================================================
# Dashboard
# ============================================================================

class HypervisorDashboard:
    """ASCII dashboard for hypervisor status visualization."""

    @staticmethod
    def render(hypervisor: Hypervisor, width: int = 72) -> str:
        border = "+" + "-" * (width - 2) + "+"
        title = "| FizzHypervisor Type-1 Status".ljust(width - 1) + "|"

        lines = [border, title, border]

        lines.append(f"| {'Version:':<20} {FIZZHYPERVISOR_VERSION:<{width-24}} |")
        lines.append(f"| {'Physical CPUs:':<20} {hypervisor.pcpu_count:<{width-24}} |")
        lines.append(f"| {'Active VMs:':<20} {hypervisor.vm_count:<{width-24}} |")
        lines.append(f"| {'Total Evaluations:':<20} {hypervisor.total_evaluations:<{width-24}} |")
        lines.append(f"| {'Scheduler Dispatches:':<22} {hypervisor.scheduler.stats.total_dispatches:<{width-26}} |")

        lines.append(border)

        if hypervisor.vm_count > 0:
            lines.append(f"| {'VM Name':<30} {'State':<12} {'vCPUs':<8} {'Memory':<{width-56}} |")
            lines.append(border)
            for name in hypervisor.vm_names():
                vm = hypervisor.get_vm(name)
                if vm is not None:
                    mem_str = f"{vm.memory_mb} MB"
                    lines.append(
                        f"| {name:<30} {vm.state.value:<12} "
                        f"{len(vm.vcpus):<8} {mem_str:<{width-56}} |"
                    )
            lines.append(border)

        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class HypervisorMiddleware(IMiddleware):
    """Pipeline middleware that evaluates FizzBuzz inside a Type-1 VM."""

    def __init__(self, hypervisor: Hypervisor) -> None:
        self.hypervisor = hypervisor

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        number = context.number
        result = self.hypervisor.evaluate_fizzbuzz(number)

        context.metadata["hypervisor_classification"] = result
        context.metadata["hypervisor_total_evaluations"] = self.hypervisor.total_evaluations
        context.metadata["hypervisor_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzhypervisor"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzhypervisor_subsystem(
    pcpu_count: int = 4,
) -> tuple[Hypervisor, HypervisorMiddleware]:
    """Create and configure the complete FizzHypervisor subsystem.

    Args:
        pcpu_count: Number of physical CPU cores available.

    Returns:
        Tuple of (Hypervisor, HypervisorMiddleware).
    """
    hypervisor = Hypervisor(pcpu_count=pcpu_count)
    middleware = HypervisorMiddleware(hypervisor)

    logger.info(
        "FizzHypervisor subsystem initialized: %d pCPUs",
        pcpu_count,
    )

    return hypervisor, middleware
