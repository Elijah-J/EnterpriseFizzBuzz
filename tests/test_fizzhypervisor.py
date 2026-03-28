"""
Enterprise FizzBuzz Platform - FizzHypervisor Test Suite

Comprehensive tests for the Type-1 bare-metal hypervisor, covering VM
lifecycle management, vCPU scheduling, EPT page table translation,
VMCS field access, VM-exit routing, FizzBuzz evaluation inside VMs,
dashboard rendering, and middleware integration.

The FizzHypervisor subsystem enables hardware-isolated FizzBuzz
evaluation by running each divisibility check inside a dedicated
virtual machine. These tests verify correct VM state transitions,
memory virtualization, exit handling, and end-to-end FizzBuzz
correctness through the hypervisor layer.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzhypervisor import (
    DEFAULT_MEMORY_MB,
    DEFAULT_TIME_SLICE_MS,
    EPT_LEVELS,
    FIZZHYPERVISOR_VERSION,
    MAX_PCPUS,
    MAX_VCPUS_PER_VM,
    MAX_VMS,
    MIDDLEWARE_PRIORITY,
    PAGE_SIZE,
    VMEXIT_CPUID,
    VMEXIT_EPT_VIOLATION,
    VMEXIT_HLT,
    VMEXIT_IO_INSTRUCTION,
    CPUIDExitHandler,
    EPTAccessType,
    EPTEntry,
    EPTPageTable,
    EPTViolationHandler,
    HLTExitHandler,
    Hypervisor,
    HypervisorDashboard,
    HypervisorMiddleware,
    IOExitHandler,
    SchedulingStats,
    VCPUScheduler,
    VCPUState,
    VMCSManager,
    VMExitHandler,
    VMExitReason,
    VMExitRouter,
    VMState,
    VirtualMachine,
    create_fizzhypervisor_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    HypervisorError,
    VMCreationError,
    VCPUSchedulingError,
    EPTViolationError,
    VMCSError,
    VMExitError,
    MemoryVirtualizationError,
    VMLifecycleError,
)


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Verify hypervisor constants match documented specifications."""

    def test_version(self):
        assert FIZZHYPERVISOR_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 250

    def test_max_vms(self):
        assert MAX_VMS == 256

    def test_page_size(self):
        assert PAGE_SIZE == 4096

    def test_ept_levels(self):
        assert EPT_LEVELS == 4


# =========================================================================
# VM State
# =========================================================================


class TestVMState:
    """Verify VM lifecycle state enumeration."""

    def test_created_state(self):
        assert VMState.CREATED.value == "created"

    def test_running_state(self):
        assert VMState.RUNNING.value == "running"

    def test_paused_state(self):
        assert VMState.PAUSED.value == "paused"

    def test_stopped_state(self):
        assert VMState.STOPPED.value == "stopped"

    def test_four_states(self):
        assert len(VMState) == 4


# =========================================================================
# EPT Page Table
# =========================================================================


class TestEPTPageTable:
    """Verify Extended Page Table GPA to HPA translation."""

    def test_map_and_translate(self):
        ept = EPTPageTable()
        ept.map_page(0x1000, 0x2000)
        hpa = ept.translate(0x1000, EPTAccessType.READ)
        assert hpa == 0x2000

    def test_translate_with_offset(self):
        ept = EPTPageTable()
        ept.map_page(0x0, 0x10000)
        hpa = ept.translate(0x100, EPTAccessType.READ)
        assert hpa == 0x10100

    def test_unmapped_returns_none(self):
        ept = EPTPageTable()
        assert ept.translate(0x5000, EPTAccessType.READ) is None

    def test_write_permission_denied(self):
        ept = EPTPageTable()
        ept.map_page(0x0, 0x10000, writable=False)
        assert ept.translate(0x0, EPTAccessType.WRITE) is None
        assert ept.translate(0x0, EPTAccessType.READ) is not None

    def test_unmap_page(self):
        ept = EPTPageTable()
        ept.map_page(0x0, 0x10000)
        assert ept.unmap_page(0x0) is True
        assert ept.translate(0x0, EPTAccessType.READ) is None

    def test_page_count(self):
        ept = EPTPageTable()
        ept.map_page(0x0, 0x10000)
        ept.map_page(0x1000, 0x20000)
        assert ept.page_count() == 2

    def test_stats_tracking(self):
        ept = EPTPageTable()
        ept.map_page(0x0, 0x10000)
        ept.translate(0x0, EPTAccessType.READ)
        ept.translate(0x5000, EPTAccessType.READ)  # miss
        assert ept.stats["lookups"] == 2
        assert ept.stats["hits"] == 1
        assert ept.stats["violations"] == 1


# =========================================================================
# VMCS Manager
# =========================================================================


class TestVMCSManager:
    """Verify VMCS field read/write operations."""

    def test_default_guest_rflags(self):
        vmcs = VMCSManager()
        assert vmcs.read(VMCSManager.GUEST_RFLAGS) == 0x2

    def test_write_guest_rip(self):
        vmcs = VMCSManager()
        assert vmcs.write(VMCSManager.GUEST_RIP, 0x1000) is True
        assert vmcs.read(VMCSManager.GUEST_RIP) == 0x1000

    def test_read_only_field(self):
        vmcs = VMCSManager()
        assert vmcs.write(VMCSManager.VM_EXIT_REASON, 42) is False

    def test_validate_default(self):
        vmcs = VMCSManager()
        errors = vmcs.validate()
        assert len(errors) == 0

    def test_field_count(self):
        vmcs = VMCSManager()
        assert vmcs.field_count() >= 10


# =========================================================================
# Virtual Machine
# =========================================================================


class TestVirtualMachine:
    """Verify VM lifecycle and memory operations."""

    def test_initial_state(self):
        vm = VirtualMachine("test_vm", vcpu_count=2, memory_mb=4)
        assert vm.state == VMState.CREATED
        assert len(vm.vcpus) == 2
        assert vm.memory_mb == 4

    def test_start_from_created(self):
        vm = VirtualMachine("test_vm")
        assert vm.start() is True
        assert vm.state == VMState.RUNNING

    def test_pause_from_running(self):
        vm = VirtualMachine("test_vm")
        vm.start()
        assert vm.pause() is True
        assert vm.state == VMState.PAUSED

    def test_cannot_pause_from_created(self):
        vm = VirtualMachine("test_vm")
        assert vm.pause() is False

    def test_stop(self):
        vm = VirtualMachine("test_vm")
        vm.start()
        assert vm.stop() is True
        assert vm.state == VMState.STOPPED

    def test_guest_memory_write_read(self):
        vm = VirtualMachine("test_vm", memory_mb=1)
        assert vm.write_guest_memory(0x0, 42) is True
        assert vm.read_guest_memory(0x0) == 42

    def test_exit_count(self):
        vm = VirtualMachine("test_vm")
        vm.record_exit()
        vm.record_exit()
        assert vm.exit_count == 2


# =========================================================================
# vCPU Scheduler
# =========================================================================


class TestVCPUScheduler:
    """Verify round-robin vCPU scheduling."""

    def test_dispatch_assigns_pcpu(self):
        sched = VCPUScheduler(pcpu_count=4)
        vcpu = VCPUState(vcpu_id=0)
        sched.enqueue(vcpu)
        dispatched = sched.dispatch()
        assert dispatched is not None
        assert dispatched.assigned_pcpu >= 0

    def test_round_robin(self):
        sched = VCPUScheduler(pcpu_count=2)
        v0 = VCPUState(vcpu_id=0)
        v1 = VCPUState(vcpu_id=1)
        sched.enqueue(v0)
        sched.enqueue(v1)
        d0 = sched.dispatch()
        d1 = sched.dispatch()
        assert d0.assigned_pcpu != d1.assigned_pcpu

    def test_empty_queue_returns_none(self):
        sched = VCPUScheduler()
        assert sched.dispatch() is None

    def test_preempt(self):
        sched = VCPUScheduler()
        vcpu = VCPUState(vcpu_id=0)
        sched.enqueue(vcpu)
        dispatched = sched.dispatch()
        sched.preempt(dispatched)
        assert sched.queue_depth == 1
        assert dispatched.preemptions == 1


# =========================================================================
# VM-Exit Router
# =========================================================================


class TestVMExitRouter:
    """Verify VM-exit dispatch table routing."""

    def test_hlt_exit_handled(self):
        router = VMExitRouter()
        vm = VirtualMachine("test_vm")
        vm.start()
        assert router.route(vm, VMEXIT_HLT) is True
        assert vm.state == VMState.PAUSED

    def test_io_exit_handled(self):
        router = VMExitRouter()
        vm = VirtualMachine("test_vm")
        assert router.route(vm, VMEXIT_IO_INSTRUCTION) is True

    def test_unhandled_exit(self):
        router = VMExitRouter()
        vm = VirtualMachine("test_vm")
        assert router.route(vm, 999) is False

    def test_exit_log(self):
        router = VMExitRouter()
        vm = VirtualMachine("test_vm")
        router.route(vm, VMEXIT_CPUID)
        assert len(router.exit_log) == 1
        assert router.exit_log[0].reason == VMEXIT_CPUID


# =========================================================================
# Hypervisor
# =========================================================================


class TestHypervisor:
    """Verify top-level hypervisor operations."""

    def test_create_vm(self):
        hyp = Hypervisor(pcpu_count=2)
        vm = hyp.create_vm("vm0")
        assert vm is not None
        assert hyp.vm_count == 1

    def test_destroy_vm(self):
        hyp = Hypervisor()
        hyp.create_vm("vm0")
        assert hyp.destroy_vm("vm0") is True
        assert hyp.vm_count == 0

    def test_evaluate_fizzbuzz_fizz(self):
        hyp = Hypervisor()
        assert hyp.evaluate_fizzbuzz(3) == "Fizz"

    def test_evaluate_fizzbuzz_buzz(self):
        hyp = Hypervisor()
        assert hyp.evaluate_fizzbuzz(5) == "Buzz"

    def test_evaluate_fizzbuzz_fizzbuzz(self):
        hyp = Hypervisor()
        assert hyp.evaluate_fizzbuzz(15) == "FizzBuzz"

    def test_evaluate_fizzbuzz_number(self):
        hyp = Hypervisor()
        assert hyp.evaluate_fizzbuzz(7) == "7"

    def test_evaluation_count(self):
        hyp = Hypervisor()
        hyp.evaluate_fizzbuzz(1)
        hyp.evaluate_fizzbuzz(2)
        assert hyp.total_evaluations == 2


# =========================================================================
# Dashboard
# =========================================================================


class TestHypervisorDashboard:
    """Verify ASCII dashboard rendering."""

    def test_render_produces_output(self):
        hyp = Hypervisor()
        output = HypervisorDashboard.render(hyp)
        assert "FizzHypervisor" in output
        assert FIZZHYPERVISOR_VERSION in output

    def test_render_with_vm(self):
        hyp = Hypervisor()
        hyp.create_vm("test_vm")
        output = HypervisorDashboard.render(hyp)
        assert "test_vm" in output


# =========================================================================
# Middleware
# =========================================================================


class TestHypervisorMiddleware:
    """Verify pipeline middleware integration."""

    def test_middleware_sets_metadata(self):
        hyp = Hypervisor()
        mw = HypervisorMiddleware(hyp)

        @dataclass
        class Ctx:
            number: int
            session_id: str = "test"
            metadata: dict = None
            def __post_init__(self):
                if self.metadata is None:
                    self.metadata = {}

        ctx = Ctx(number=15)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["hypervisor_classification"] == "FizzBuzz"
        assert result.metadata["hypervisor_enabled"] is True

    def test_middleware_name(self):
        hyp = Hypervisor()
        mw = HypervisorMiddleware(hyp)
        assert mw.get_name() == "fizzhypervisor"

    def test_middleware_priority(self):
        hyp = Hypervisor()
        mw = HypervisorMiddleware(hyp)
        assert mw.get_priority() == 250


# =========================================================================
# Factory
# =========================================================================


class TestFactory:
    """Verify subsystem factory function."""

    def test_create_subsystem(self):
        hyp, mw = create_fizzhypervisor_subsystem(pcpu_count=2)
        assert isinstance(hyp, Hypervisor)
        assert isinstance(mw, HypervisorMiddleware)
        assert hyp.pcpu_count == 2


# =========================================================================
# Exceptions
# =========================================================================


class TestExceptions:
    """Verify hypervisor exception hierarchy."""

    def test_hypervisor_error_base(self):
        err = HypervisorError("test")
        assert "test" in str(err)

    def test_vm_creation_error(self):
        err = VMCreationError("vm0", "out of memory")
        assert err.vm_name == "vm0"
        assert err.reason == "out of memory"

    def test_ept_violation_error(self):
        err = EPTViolationError(0x1000, "write")
        assert err.guest_physical == 0x1000
        assert err.access_type == "write"

    def test_vm_lifecycle_error(self):
        err = VMLifecycleError("vm0", "stopped", "running")
        assert err.vm_name == "vm0"
        assert err.current_state == "stopped"
        assert err.target_state == "running"
