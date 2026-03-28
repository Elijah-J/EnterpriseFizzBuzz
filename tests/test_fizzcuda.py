"""
Enterprise FizzBuzz Platform - FizzCUDA GPU Compute Framework Test Suite

Comprehensive tests for the CUDA-style GPU compute framework, covering
device management, memory allocation and transfer, kernel compilation
and launch, stream operations, thread block validation, FizzBuzz
classification correctness, middleware integration, dashboard rendering,
and exception handling.

The FizzCUDA subsystem provides massively parallel FizzBuzz classification
by dispatching workloads across virtual GPU streaming multiprocessors.
These tests verify that the virtual GPU produces results identical to
the CPU-based rule engine while faithfully modeling the CUDA execution
hierarchy of grids, thread blocks, and individual threads.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzcuda import (
    CLASSIFY_BUZZ,
    CLASSIFY_FIZZ,
    CLASSIFY_FIZZBUZZ,
    CLASSIFY_NONE,
    DEFAULT_BLOCK_SIZE,
    DEFAULT_GLOBAL_MEMORY_BYTES,
    DEFAULT_SHARED_MEMORY_PER_BLOCK,
    DEFAULT_SM_COUNT,
    FIZZCUDA_VERSION,
    MAX_THREADS_PER_BLOCK,
    MIDDLEWARE_PRIORITY,
    WARP_SIZE,
    CUDADashboard,
    CUDADevice,
    CUDAKernel,
    CUDAMiddleware,
    CUDARuntime,
    CUDAStream,
    DeviceCapability,
    Dim3,
    GPUMemory,
    KernelState,
    KernelStats,
    MemoryDirection,
    SharedMemory,
    StreamState,
    ThreadContext,
    classification_code_to_string,
    create_fizzcuda_subsystem,
    fizzbuzz_classify_kernel,
)
from enterprise_fizzbuzz.domain.exceptions import (
    CUDADeviceNotFoundError,
    CUDAError,
    CUDAInvalidBlockDimError,
    CUDAKernelLaunchError,
    CUDAMemoryError,
    CUDASharedMemoryExceededError,
    CUDAStreamError,
    CUDASynchronizationError,
)


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    """Verify FizzCUDA constants match documented specifications."""

    def test_version(self):
        assert FIZZCUDA_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 238

    def test_warp_size_is_32(self):
        assert WARP_SIZE == 32

    def test_max_threads_per_block(self):
        assert MAX_THREADS_PER_BLOCK == 1024

    def test_default_shared_memory_is_48kib(self):
        assert DEFAULT_SHARED_MEMORY_PER_BLOCK == 49152

    def test_default_sm_count(self):
        assert DEFAULT_SM_COUNT == 4


# =========================================================================
# Dim3
# =========================================================================

class TestDim3:
    """Verify the three-dimensional index type."""

    def test_default_values(self):
        d = Dim3()
        assert d.x == 1 and d.y == 1 and d.z == 1

    def test_total_1d(self):
        d = Dim3(x=256)
        assert d.total == 256

    def test_total_3d(self):
        d = Dim3(x=8, y=4, z=2)
        assert d.total == 64

    def test_as_tuple(self):
        d = Dim3(x=3, y=5, z=7)
        assert d.as_tuple() == (3, 5, 7)


# =========================================================================
# ThreadContext
# =========================================================================

class TestThreadContext:
    """Verify global thread ID computation."""

    def test_global_id_first_thread(self):
        ctx = ThreadContext(
            thread_idx=Dim3(0, 0, 0),
            block_idx=Dim3(0, 0, 0),
            block_dim=Dim3(256, 1, 1),
            grid_dim=Dim3(4, 1, 1),
        )
        assert ctx.global_thread_id == 0

    def test_global_id_second_block(self):
        ctx = ThreadContext(
            thread_idx=Dim3(0, 0, 0),
            block_idx=Dim3(1, 0, 0),
            block_dim=Dim3(256, 1, 1),
            grid_dim=Dim3(4, 1, 1),
        )
        assert ctx.global_thread_id == 256

    def test_global_id_within_block(self):
        ctx = ThreadContext(
            thread_idx=Dim3(42, 0, 0),
            block_idx=Dim3(0, 0, 0),
            block_dim=Dim3(256, 1, 1),
            grid_dim=Dim3(1, 1, 1),
        )
        assert ctx.global_thread_id == 42


# =========================================================================
# GPU Memory
# =========================================================================

class TestGPUMemory:
    """Verify device memory allocation and data transfer."""

    def test_allocate_returns_nonzero_address(self):
        mem = GPUMemory(capacity_bytes=1024 * 1024)
        addr = mem.allocate(256)
        assert addr > 0

    def test_allocate_tracks_bytes(self):
        mem = GPUMemory(capacity_bytes=1024 * 1024)
        mem.allocate(256)
        assert mem.bytes_allocated > 0

    def test_allocate_exceeds_capacity_raises(self):
        mem = GPUMemory(capacity_bytes=512)
        with pytest.raises(CUDAMemoryError):
            mem.allocate(1024)

    def test_allocate_zero_raises(self):
        mem = GPUMemory(capacity_bytes=1024)
        with pytest.raises(CUDAMemoryError):
            mem.allocate(0)

    def test_write_and_read(self):
        mem = GPUMemory(capacity_bytes=1024 * 1024)
        addr = mem.allocate(40)
        mem.write(addr, [10, 20, 30])
        result = mem.read(addr, 3)
        assert result == [10, 20, 30]

    def test_free_reclaims_memory(self):
        mem = GPUMemory(capacity_bytes=1024 * 1024)
        addr = mem.allocate(256)
        allocated_before = mem.bytes_allocated
        mem.free(addr)
        assert mem.bytes_allocated < allocated_before

    def test_utilization(self):
        mem = GPUMemory(capacity_bytes=1024)
        mem.allocate(256)
        assert 0.0 < mem.utilization <= 1.0

    def test_get_stats(self):
        mem = GPUMemory(capacity_bytes=4096)
        mem.allocate(128)
        stats = mem.get_stats()
        assert stats["capacity_bytes"] == 4096
        assert stats["active_allocations"] == 1


# =========================================================================
# Shared Memory
# =========================================================================

class TestSharedMemory:
    """Verify per-block shared memory operations."""

    def test_store_and_load(self):
        smem = SharedMemory(size_bytes=1024)
        smem.store(0, 42)
        assert smem.load(0) == 42

    def test_load_uninitialized_returns_zero(self):
        smem = SharedMemory(size_bytes=1024)
        assert smem.load(100) == 0

    def test_store_out_of_bounds_raises(self):
        smem = SharedMemory(size_bytes=64)
        with pytest.raises(CUDASharedMemoryExceededError):
            smem.store(64, 1)

    def test_clear_resets_data(self):
        smem = SharedMemory(size_bytes=1024)
        smem.store(0, 99)
        smem.clear()
        assert smem.load(0) == 0


# =========================================================================
# CUDA Stream
# =========================================================================

class TestCUDAStream:
    """Verify stream operations and state management."""

    def test_initial_state_is_idle(self):
        stream = CUDAStream(stream_id=1)
        assert stream.state == StreamState.IDLE

    def test_record_operation_sets_executing(self):
        stream = CUDAStream(stream_id=1)
        stream.record_operation("test_op")
        assert stream.state == StreamState.EXECUTING

    def test_synchronize_sets_synchronized(self):
        stream = CUDAStream(stream_id=1)
        stream.record_operation("test_op")
        stream.synchronize()
        assert stream.state == StreamState.SYNCHRONIZED

    def test_error_stream_raises_on_sync(self):
        stream = CUDAStream(stream_id=1)
        stream.set_error("test failure")
        with pytest.raises(CUDAStreamError):
            stream.synchronize()

    def test_operation_count(self):
        stream = CUDAStream(stream_id=1)
        stream.record_operation("op1")
        stream.record_operation("op2")
        assert stream.operation_count == 2


# =========================================================================
# CUDA Kernel
# =========================================================================

class TestCUDAKernel:
    """Verify kernel compilation and execution."""

    def _make_noop_kernel(self):
        def noop(ctx, mem, shared, params):
            pass
        return CUDAKernel(name="noop", func=noop)

    def test_initial_state_is_compiled(self):
        kernel = self._make_noop_kernel()
        assert kernel.state == KernelState.COMPILED

    def test_execute_returns_stats(self):
        kernel = self._make_noop_kernel()
        mem = GPUMemory(capacity_bytes=1024 * 1024)
        stats = kernel.execute(Dim3(1), Dim3(32), mem)
        assert isinstance(stats, KernelStats)
        assert stats.active_threads == 32

    def test_execute_sets_complete(self):
        kernel = self._make_noop_kernel()
        mem = GPUMemory(capacity_bytes=1024 * 1024)
        kernel.execute(Dim3(1), Dim3(32), mem)
        assert kernel.state == KernelState.COMPLETE

    def test_block_size_exceeds_max_raises(self):
        kernel = self._make_noop_kernel()
        mem = GPUMemory(capacity_bytes=1024 * 1024)
        with pytest.raises(CUDAKernelLaunchError):
            kernel.execute(Dim3(1), Dim3(2048), mem)

    def test_launch_count_increments(self):
        kernel = self._make_noop_kernel()
        mem = GPUMemory(capacity_bytes=1024 * 1024)
        kernel.execute(Dim3(1), Dim3(32), mem)
        kernel.execute(Dim3(1), Dim3(32), mem)
        assert kernel.launch_count == 2


# =========================================================================
# CUDA Device
# =========================================================================

class TestCUDADevice:
    """Verify virtual GPU device properties."""

    def test_default_properties(self):
        dev = CUDADevice()
        assert dev.device_id == 0
        assert dev.max_threads_per_block == 1024
        assert dev.warp_size == 32

    def test_compute_capability(self):
        dev = CUDADevice(compute_capability=DeviceCapability.SM_80)
        props = dev.get_properties()
        assert props["compute_capability"] == "8.0"

    def test_repr(self):
        dev = CUDADevice(device_id=0, name="TestGPU", sm_count=8)
        r = repr(dev)
        assert "TestGPU" in r
        assert "sm_count=8" in r


# =========================================================================
# CUDA Runtime
# =========================================================================

class TestCUDARuntime:
    """Verify the runtime API for device, memory, kernel, and stream management."""

    def test_init_creates_devices(self):
        rt = CUDARuntime(device_count=2)
        assert rt.device_count == 2

    def test_get_device(self):
        rt = CUDARuntime(device_count=1)
        dev = rt.get_device(0)
        assert isinstance(dev, CUDADevice)

    def test_get_device_invalid_raises(self):
        rt = CUDARuntime(device_count=1)
        with pytest.raises(CUDADeviceNotFoundError):
            rt.get_device(5)

    def test_list_devices(self):
        rt = CUDARuntime(device_count=3)
        devices = rt.list_devices()
        assert len(devices) == 3

    def test_create_device(self):
        rt = CUDARuntime(device_count=1)
        dev = rt.create_device(name="Extra GPU", sm_count=8)
        assert rt.device_count == 2
        assert dev.name == "Extra GPU"

    def test_allocate_and_transfer(self):
        rt = CUDARuntime(device_count=1)
        addr = rt.allocate(40)
        rt.memcpy_host_to_device(addr, [1, 2, 3])
        result = rt.memcpy_device_to_host(addr, 3)
        assert result == [1, 2, 3]

    def test_launch_unregistered_kernel_raises(self):
        rt = CUDARuntime(device_count=1)
        with pytest.raises(CUDAKernelLaunchError):
            rt.launch_kernel("nonexistent", Dim3(1), Dim3(32))

    def test_launch_registered_kernel(self):
        rt = CUDARuntime(device_count=1)
        kernel = CUDAKernel(name="test", func=lambda ctx, mem, shared, params: None)
        rt.register_kernel(kernel)
        stats = rt.launch_kernel("test", Dim3(1), Dim3(32))
        assert stats.active_threads == 32

    def test_synchronize_all_streams(self):
        rt = CUDARuntime(device_count=1)
        rt.create_stream()
        rt.synchronize()  # Should not raise

    def test_get_stats(self):
        rt = CUDARuntime(device_count=1)
        stats = rt.get_stats()
        assert stats["version"] == FIZZCUDA_VERSION
        assert stats["device_count"] == 1

    def test_set_device(self):
        rt = CUDARuntime(device_count=2)
        rt.set_device(1)
        assert rt.current_device.device_id == 1


# =========================================================================
# FizzBuzz Classification Kernel
# =========================================================================

class TestFizzBuzzKernel:
    """Verify FizzBuzz classification correctness on the virtual GPU."""

    def _classify_numbers(self, numbers):
        """Helper: run the FizzBuzz kernel and return classification codes."""
        rt = CUDARuntime(device_count=1)
        kernel = CUDAKernel(name="fizzbuzz_classify", func=fizzbuzz_classify_kernel)
        rt.register_kernel(kernel)

        count = len(numbers)
        input_addr = rt.allocate(count * 4)
        output_addr = rt.allocate(count * 4)
        rt.memcpy_host_to_device(input_addr, numbers)

        import math
        grid = Dim3(x=math.ceil(count / 256))
        block = Dim3(x=min(count, 256))

        rt.launch_kernel(
            "fizzbuzz_classify", grid, block,
            params={"input_addr": input_addr, "output_addr": output_addr, "count": count},
        )
        rt.synchronize()
        return rt.memcpy_device_to_host(output_addr, count)

    def test_fizzbuzz_15(self):
        codes = self._classify_numbers([15])
        assert codes[0] == CLASSIFY_FIZZBUZZ

    def test_fizz_3(self):
        codes = self._classify_numbers([3])
        assert codes[0] == CLASSIFY_FIZZ

    def test_buzz_5(self):
        codes = self._classify_numbers([5])
        assert codes[0] == CLASSIFY_BUZZ

    def test_none_7(self):
        codes = self._classify_numbers([7])
        assert codes[0] == CLASSIFY_NONE

    def test_range_1_to_20(self):
        numbers = list(range(1, 21))
        codes = self._classify_numbers(numbers)
        for i, n in enumerate(numbers):
            if n % 15 == 0:
                assert codes[i] == CLASSIFY_FIZZBUZZ, f"n={n}"
            elif n % 3 == 0:
                assert codes[i] == CLASSIFY_FIZZ, f"n={n}"
            elif n % 5 == 0:
                assert codes[i] == CLASSIFY_BUZZ, f"n={n}"
            else:
                assert codes[i] == CLASSIFY_NONE, f"n={n}"

    def test_classification_code_to_string(self):
        assert classification_code_to_string(CLASSIFY_FIZZBUZZ) == "FizzBuzz"
        assert classification_code_to_string(CLASSIFY_FIZZ) == "Fizz"
        assert classification_code_to_string(CLASSIFY_BUZZ) == "Buzz"
        assert classification_code_to_string(CLASSIFY_NONE) == ""


# =========================================================================
# Middleware
# =========================================================================

class TestCUDAMiddleware:
    """Verify middleware integration with the processing pipeline."""

    def test_get_name(self):
        rt = CUDARuntime(device_count=1)
        mw = CUDAMiddleware(rt)
        assert mw.get_name() == "fizzcuda"

    def test_get_priority(self):
        rt = CUDARuntime(device_count=1)
        mw = CUDAMiddleware(rt)
        assert mw.get_priority() == 238

    def test_process_sets_metadata(self):
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        rt = CUDARuntime(device_count=1)
        mw = CUDAMiddleware(rt)

        ctx = ProcessingContext(number=15, session_id="test-session")
        result = mw.process(ctx, lambda c: c)
        assert result.metadata.get("cuda_enabled") is True
        assert result.metadata.get("cuda_classification") == "FizzBuzz"

    def test_classify_numbers_batch(self):
        rt = CUDARuntime(device_count=1)
        mw = CUDAMiddleware(rt)
        results = mw.classify_numbers([3, 5, 15, 7])
        assert results[3] == "Fizz"
        assert results[5] == "Buzz"
        assert results[15] == "FizzBuzz"
        assert results[7] == ""

    def test_evaluations_counter(self):
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        rt = CUDARuntime(device_count=1)
        mw = CUDAMiddleware(rt)
        for n in [1, 2, 3]:
            ctx = ProcessingContext(number=n, session_id="test")
            mw.process(ctx, lambda c: c)
        assert mw.evaluations == 3


# =========================================================================
# Dashboard
# =========================================================================

class TestCUDADashboard:
    """Verify ASCII dashboard rendering."""

    def test_render_returns_string(self):
        rt = CUDARuntime(device_count=1)
        output = CUDADashboard.render(rt)
        assert isinstance(output, str)
        assert "FizzCUDA" in output

    def test_render_contains_device_info(self):
        rt = CUDARuntime(device_count=1)
        output = CUDADashboard.render(rt)
        assert "Device 0" in output
        assert "SM Count" in output

    def test_render_contains_version(self):
        rt = CUDARuntime(device_count=1)
        output = CUDADashboard.render(rt)
        assert FIZZCUDA_VERSION in output


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    """Verify the factory function creates a functional subsystem."""

    def test_create_returns_runtime_and_middleware(self):
        rt, mw = create_fizzcuda_subsystem()
        assert isinstance(rt, CUDARuntime)
        assert isinstance(mw, CUDAMiddleware)

    def test_factory_registers_kernel(self):
        rt, mw = create_fizzcuda_subsystem()
        stats = rt.get_stats()
        assert "fizzbuzz_classify" in stats["kernels"]

    def test_factory_custom_device_count(self):
        rt, mw = create_fizzcuda_subsystem(device_count=3, sm_count=8)
        assert rt.device_count == 3
        assert rt.get_device(2).sm_count == 8


# =========================================================================
# Exceptions
# =========================================================================

class TestExceptions:
    """Verify exception hierarchy and attributes."""

    def test_cuda_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions._base import FizzBuzzError
        err = CUDAError("test")
        assert isinstance(err, FizzBuzzError)

    def test_device_not_found_attributes(self):
        err = CUDADeviceNotFoundError(device_id=5, available=2)
        assert err.device_id == 5
        assert err.available == 2

    def test_kernel_launch_error_attributes(self):
        err = CUDAKernelLaunchError("my_kernel", "too many threads")
        assert err.kernel_name == "my_kernel"
        assert "too many threads" in str(err)

    def test_memory_error_attributes(self):
        err = CUDAMemoryError("allocate", 1024, 512)
        assert err.operation == "allocate"
        assert err.size_bytes == 1024

    def test_stream_error_attributes(self):
        err = CUDAStreamError(3, "destroyed")
        assert err.stream_id == 3

    def test_shared_memory_exceeded_attributes(self):
        err = CUDASharedMemoryExceededError(65536, 49152)
        assert err.requested == 65536
        assert err.capacity == 49152

    def test_synchronization_error(self):
        err = CUDASynchronizationError("kernel panic")
        assert "kernel panic" in str(err)
