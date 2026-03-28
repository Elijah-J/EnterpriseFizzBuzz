"""
Enterprise FizzBuzz Platform - FizzCUDA GPU Compute Framework

Implements a complete CUDA-style GPU compute framework for massively parallel
FizzBuzz classification. NVIDIA's CUDA programming model organizes computation
into a hierarchy of grids, thread blocks, and individual threads, enabling
thousands of lightweight threads to execute the same kernel function across
different data elements simultaneously.

The FizzCUDA subsystem faithfully models this execution hierarchy:

    CUDARuntime
        ├── CUDADevice[]           (virtual GPU devices with SM arrays)
        │     ├── GPUMemory        (device global memory with allocation tracking)
        │     └── SharedMemory     (per-block fast on-chip SRAM)
        ├── CUDAStream[]           (ordered command queues)
        └── CUDAKernel[]           (compiled device functions)

The FizzBuzz classification kernel assigns one thread per input number,
computes n % 3 and n % 5 in parallel across all threads in a warp of 32,
and writes classification results to device memory. Host-device memory
transfers handle data marshalling between the Python runtime and the
virtual GPU address space.

Thread block dimensions are validated against device compute capability
limits. Shared memory is allocated per-block and accessible only by
threads within that block, providing fast inter-thread communication
for reduction operations that would otherwise require expensive global
memory round-trips.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

FIZZCUDA_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 238

WARP_SIZE = 32
MAX_THREADS_PER_BLOCK = 1024
MAX_BLOCK_DIM_X = 1024
MAX_BLOCK_DIM_Y = 1024
MAX_BLOCK_DIM_Z = 64
MAX_GRID_DIM_X = 2**31 - 1
MAX_GRID_DIM_Y = 65535
MAX_GRID_DIM_Z = 65535
DEFAULT_SHARED_MEMORY_PER_BLOCK = 49152  # 48 KiB
DEFAULT_GLOBAL_MEMORY_BYTES = 8 * 1024 * 1024 * 1024  # 8 GiB
DEFAULT_SM_COUNT = 4
DEFAULT_BLOCK_SIZE = 256
REGISTERS_PER_SM = 65536
MAX_WARPS_PER_SM = 48

# FizzBuzz classification codes written to device output buffers
CLASSIFY_FIZZBUZZ = 15
CLASSIFY_FIZZ = 3
CLASSIFY_BUZZ = 5
CLASSIFY_NONE = 0


# ============================================================================
# Enums
# ============================================================================

class MemoryDirection(Enum):
    """Direction of host-device memory transfer."""
    HOST_TO_DEVICE = "H2D"
    DEVICE_TO_HOST = "D2H"
    DEVICE_TO_DEVICE = "D2D"


class StreamState(Enum):
    """Execution state of a CUDA stream."""
    IDLE = "idle"
    EXECUTING = "executing"
    SYNCHRONIZED = "synchronized"
    ERROR = "error"


class KernelState(Enum):
    """Lifecycle state of a CUDA kernel."""
    COMPILED = "compiled"
    LAUNCHED = "launched"
    COMPLETE = "complete"
    FAILED = "failed"


class DeviceCapability(Enum):
    """Compute capability tiers for FizzCUDA virtual devices."""
    SM_70 = "7.0"   # Volta
    SM_75 = "7.5"   # Turing
    SM_80 = "8.0"   # Ampere
    SM_86 = "8.6"   # GA106
    SM_90 = "9.0"   # Hopper


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class Dim3:
    """Three-dimensional index used for grid and block dimensions.

    Mirrors CUDA's dim3 type. Any unspecified component defaults to 1,
    ensuring that a 1D launch configuration does not require the caller
    to explicitly set y=1, z=1.
    """
    x: int = 1
    y: int = 1
    z: int = 1

    @property
    def total(self) -> int:
        return self.x * self.y * self.z

    def as_tuple(self) -> tuple:
        return (self.x, self.y, self.z)


@dataclass
class MemoryAllocation:
    """Tracks a single device memory allocation.

    Each allocation has a base address, size, and liveness flag.
    The allocator uses a simple bump-pointer strategy within the
    device's global memory address space.
    """
    address: int
    size_bytes: int
    freed: bool = False


@dataclass
class TransferRecord:
    """Records a single host-device memory transfer for profiling."""
    direction: MemoryDirection
    size_bytes: int
    timestamp: float = 0.0
    stream_id: int = 0


@dataclass
class ThreadContext:
    """Execution context for a single GPU thread.

    Each thread knows its position within the block and the grid,
    enabling it to compute its global thread index for data-parallel
    access patterns.
    """
    thread_idx: Dim3 = field(default_factory=Dim3)
    block_idx: Dim3 = field(default_factory=Dim3)
    block_dim: Dim3 = field(default_factory=Dim3)
    grid_dim: Dim3 = field(default_factory=Dim3)

    @property
    def global_thread_id(self) -> int:
        """Compute the flattened global thread index.

        Equivalent to blockIdx.x * blockDim.x + threadIdx.x for 1D launches.
        Extended to 3D with the standard linearization formula.
        """
        block_offset = (
            self.block_idx.x
            + self.block_idx.y * self.grid_dim.x
            + self.block_idx.z * self.grid_dim.x * self.grid_dim.y
        )
        thread_offset = (
            self.thread_idx.x
            + self.thread_idx.y * self.block_dim.x
            + self.thread_idx.z * self.block_dim.x * self.block_dim.y
        )
        return block_offset * self.block_dim.total + thread_offset


@dataclass
class KernelStats:
    """Execution statistics for a kernel launch."""
    kernel_name: str = ""
    grid_dim: Dim3 = field(default_factory=Dim3)
    block_dim: Dim3 = field(default_factory=Dim3)
    total_threads: int = 0
    active_threads: int = 0
    elapsed_ms: float = 0.0
    shared_memory_bytes: int = 0
    classifications: dict = field(default_factory=dict)


# ============================================================================
# GPU Memory
# ============================================================================

class GPUMemory:
    """Device global memory manager with allocation tracking.

    Implements a linear allocator over the virtual GPU's global memory
    address space. All allocations are tracked for leak detection, and
    the total utilization is exposed for capacity monitoring.

    The memory contents are stored in a Python dictionary keyed by
    address, which provides O(1) access without requiring a contiguous
    backing array for the full 8 GiB address space.
    """

    def __init__(self, capacity_bytes: int = DEFAULT_GLOBAL_MEMORY_BYTES) -> None:
        self.capacity_bytes = capacity_bytes
        self._allocations: list[MemoryAllocation] = []
        self._data: dict[int, Any] = {}
        self._next_address = 0x1000  # Start at 4 KiB to catch null-pointer bugs
        self._bytes_allocated = 0

    @property
    def bytes_allocated(self) -> int:
        return self._bytes_allocated

    @property
    def bytes_free(self) -> int:
        return self.capacity_bytes - self._bytes_allocated

    @property
    def utilization(self) -> float:
        if self.capacity_bytes == 0:
            return 0.0
        return self._bytes_allocated / self.capacity_bytes

    def allocate(self, size_bytes: int) -> int:
        """Allocate device memory and return the base address.

        Raises:
            CUDAMemoryError: If insufficient memory is available.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzcuda import CUDAMemoryError

        if size_bytes <= 0:
            raise CUDAMemoryError("allocate", size_bytes, self.bytes_free)
        if size_bytes > self.bytes_free:
            raise CUDAMemoryError("allocate", size_bytes, self.bytes_free)

        address = self._next_address
        # Align to 256-byte boundary for coalesced access
        aligned_size = ((size_bytes + 255) // 256) * 256
        self._next_address += aligned_size
        self._bytes_allocated += aligned_size
        self._allocations.append(MemoryAllocation(
            address=address,
            size_bytes=aligned_size,
        ))

        logger.debug(
            "GPU memory allocated: %d bytes at 0x%08X (aligned to %d)",
            size_bytes, address, aligned_size,
        )
        return address

    def free(self, address: int) -> None:
        """Free a previously allocated device memory region."""
        for alloc in self._allocations:
            if alloc.address == address and not alloc.freed:
                alloc.freed = True
                self._bytes_allocated -= alloc.size_bytes
                # Remove data entries in the freed region
                to_remove = [
                    a for a in self._data
                    if alloc.address <= a < alloc.address + alloc.size_bytes
                ]
                for a in to_remove:
                    del self._data[a]
                logger.debug("GPU memory freed: 0x%08X (%d bytes)", address, alloc.size_bytes)
                return
        logger.warning("Attempted to free unknown GPU address: 0x%08X", address)

    def write(self, address: int, data: list[int]) -> None:
        """Write a list of integers to device memory starting at address."""
        for i, value in enumerate(data):
            self._data[address + i * 4] = value

    def read(self, address: int, count: int) -> list[int]:
        """Read count integers from device memory starting at address."""
        return [self._data.get(address + i * 4, 0) for i in range(count)]

    def get_stats(self) -> dict:
        """Return memory utilization statistics."""
        active = sum(1 for a in self._allocations if not a.freed)
        freed = sum(1 for a in self._allocations if a.freed)
        return {
            "capacity_bytes": self.capacity_bytes,
            "allocated_bytes": self._bytes_allocated,
            "free_bytes": self.bytes_free,
            "utilization": self.utilization,
            "active_allocations": active,
            "freed_allocations": freed,
            "total_allocations": len(self._allocations),
        }


# ============================================================================
# Shared Memory
# ============================================================================

class SharedMemory:
    """Per-block shared memory region.

    Shared memory is a fast on-chip SRAM visible to all threads within a
    thread block. It provides low-latency data sharing between threads
    that would otherwise require global memory round-trips with 100x
    higher latency.

    Each thread block receives its own independent shared memory region,
    initialized to zero at block launch.
    """

    def __init__(self, size_bytes: int = DEFAULT_SHARED_MEMORY_PER_BLOCK) -> None:
        self.size_bytes = size_bytes
        self._data: dict[int, int] = {}

    def store(self, offset: int, value: int) -> None:
        """Store a value at the given byte offset in shared memory.

        Raises:
            CUDASharedMemoryExceededError: If offset exceeds capacity.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzcuda import (
            CUDASharedMemoryExceededError,
        )

        if offset < 0 or offset >= self.size_bytes:
            raise CUDASharedMemoryExceededError(offset + 4, self.size_bytes)
        self._data[offset] = value

    def load(self, offset: int) -> int:
        """Load a value from the given byte offset in shared memory."""
        return self._data.get(offset, 0)

    def clear(self) -> None:
        """Reset shared memory contents to zero."""
        self._data.clear()


# ============================================================================
# CUDA Stream
# ============================================================================

class CUDAStream:
    """An ordered sequence of GPU operations.

    CUDA streams provide a mechanism for overlapping computation and
    data transfers. Operations submitted to the same stream execute
    in order; operations on different streams may execute concurrently.

    The default stream (stream 0) is implicitly synchronized with all
    other streams, providing sequential semantics when no explicit
    stream management is desired.
    """

    _next_id = 0

    def __init__(self, stream_id: Optional[int] = None) -> None:
        if stream_id is not None:
            self.stream_id = stream_id
        else:
            self.stream_id = CUDAStream._next_id
            CUDAStream._next_id += 1
        self.state = StreamState.IDLE
        self._operations: list[dict] = []
        self._error: Optional[str] = None

    def record_operation(self, op_type: str, **kwargs: Any) -> None:
        """Record an operation submitted to this stream."""
        self._operations.append({
            "type": op_type,
            "timestamp": time.monotonic(),
            **kwargs,
        })
        self.state = StreamState.EXECUTING

    def synchronize(self) -> None:
        """Wait for all operations on this stream to complete.

        Raises:
            CUDAStreamError: If the stream has encountered an error.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzcuda import CUDAStreamError

        if self.state == StreamState.ERROR:
            raise CUDAStreamError(self.stream_id, self._error or "unknown error")
        self.state = StreamState.SYNCHRONIZED
        logger.debug("Stream %d synchronized (%d operations)", self.stream_id, len(self._operations))

    def set_error(self, reason: str) -> None:
        """Mark this stream as having encountered an error."""
        self.state = StreamState.ERROR
        self._error = reason

    @property
    def operation_count(self) -> int:
        return len(self._operations)

    def get_stats(self) -> dict:
        return {
            "stream_id": self.stream_id,
            "state": self.state.value,
            "operations": self.operation_count,
        }


# ============================================================================
# CUDA Kernel
# ============================================================================

class CUDAKernel:
    """A compiled GPU kernel function.

    Kernels are the unit of work launched on the GPU. Each kernel is a
    function that executes identically on every thread, with each thread
    computing its unique global index to determine which data element
    to process.

    The FizzBuzz classification kernel computes n % 3 and n % 5 for each
    input number, producing a classification code (0, 3, 5, or 15) that
    encodes the FizzBuzz result.
    """

    def __init__(
        self,
        name: str,
        func: Callable[[ThreadContext, GPUMemory, SharedMemory, dict], None],
    ) -> None:
        self.name = name
        self.func = func
        self.state = KernelState.COMPILED
        self.launch_count = 0
        self.total_threads_launched = 0
        self._stats_history: list[KernelStats] = []

    def execute(
        self,
        grid_dim: Dim3,
        block_dim: Dim3,
        memory: GPUMemory,
        shared_mem_bytes: int = 0,
        params: Optional[dict] = None,
    ) -> KernelStats:
        """Execute the kernel across all threads in the grid.

        Iterates over every block in the grid, and every thread in each
        block, invoking the kernel function with the appropriate thread
        context. This is a serial simulation of the massively parallel
        execution that occurs on real GPU hardware.

        Args:
            grid_dim: Number of thread blocks in each dimension.
            block_dim: Number of threads per block in each dimension.
            memory: Device global memory.
            shared_mem_bytes: Dynamic shared memory allocation per block.
            params: Additional kernel parameters.

        Returns:
            Execution statistics for this launch.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzcuda import CUDAKernelLaunchError

        # Validate block dimensions
        total_block_threads = block_dim.total
        if total_block_threads > MAX_THREADS_PER_BLOCK:
            raise CUDAKernelLaunchError(
                self.name,
                f"Block size {total_block_threads} exceeds maximum "
                f"{MAX_THREADS_PER_BLOCK} threads per block",
            )

        if shared_mem_bytes > DEFAULT_SHARED_MEMORY_PER_BLOCK:
            from enterprise_fizzbuzz.domain.exceptions.fizzcuda import (
                CUDASharedMemoryExceededError,
            )
            raise CUDASharedMemoryExceededError(
                shared_mem_bytes, DEFAULT_SHARED_MEMORY_PER_BLOCK,
            )

        start_time = time.monotonic()
        self.state = KernelState.LAUNCHED
        params = params or {}

        total_threads = grid_dim.total * block_dim.total
        active_count = 0
        classifications = {"fizzbuzz": 0, "fizz": 0, "buzz": 0, "none": 0}

        for bz in range(grid_dim.z):
            for by in range(grid_dim.y):
                for bx in range(grid_dim.x):
                    block_shared = SharedMemory(
                        max(shared_mem_bytes, DEFAULT_SHARED_MEMORY_PER_BLOCK),
                    )
                    for tz in range(block_dim.z):
                        for ty in range(block_dim.y):
                            for tx in range(block_dim.x):
                                ctx = ThreadContext(
                                    thread_idx=Dim3(tx, ty, tz),
                                    block_idx=Dim3(bx, by, bz),
                                    block_dim=block_dim,
                                    grid_dim=grid_dim,
                                )
                                self.func(ctx, memory, block_shared, params)
                                active_count += 1

        elapsed = (time.monotonic() - start_time) * 1000.0
        self.state = KernelState.COMPLETE
        self.launch_count += 1
        self.total_threads_launched += total_threads

        stats = KernelStats(
            kernel_name=self.name,
            grid_dim=grid_dim,
            block_dim=block_dim,
            total_threads=total_threads,
            active_threads=active_count,
            elapsed_ms=elapsed,
            shared_memory_bytes=shared_mem_bytes,
            classifications=classifications,
        )
        self._stats_history.append(stats)

        logger.info(
            "Kernel '%s' complete: %d threads, %.3f ms, grid=(%d,%d,%d), block=(%d,%d,%d)",
            self.name, active_count, elapsed,
            grid_dim.x, grid_dim.y, grid_dim.z,
            block_dim.x, block_dim.y, block_dim.z,
        )
        return stats

    @property
    def last_stats(self) -> Optional[KernelStats]:
        if self._stats_history:
            return self._stats_history[-1]
        return None


# ============================================================================
# CUDA Device
# ============================================================================

class CUDADevice:
    """A virtual CUDA-capable GPU device.

    Each device represents a discrete GPU with its own global memory,
    streaming multiprocessor array, and compute capability. The device
    maintains memory allocation state and provides hardware property
    queries used by the runtime to validate kernel launch configurations.
    """

    def __init__(
        self,
        device_id: int = 0,
        name: str = "FizzCUDA Virtual GPU",
        sm_count: int = DEFAULT_SM_COUNT,
        compute_capability: DeviceCapability = DeviceCapability.SM_90,
        global_memory_bytes: int = DEFAULT_GLOBAL_MEMORY_BYTES,
    ) -> None:
        self.device_id = device_id
        self.name = name
        self.sm_count = sm_count
        self.compute_capability = compute_capability
        self.memory = GPUMemory(global_memory_bytes)
        self._is_current = False

    @property
    def max_threads_per_block(self) -> int:
        return MAX_THREADS_PER_BLOCK

    @property
    def max_threads_per_sm(self) -> int:
        return MAX_WARPS_PER_SM * WARP_SIZE

    @property
    def max_shared_memory_per_block(self) -> int:
        return DEFAULT_SHARED_MEMORY_PER_BLOCK

    @property
    def warp_size(self) -> int:
        return WARP_SIZE

    def get_properties(self) -> dict:
        """Return device properties as a dictionary."""
        return {
            "device_id": self.device_id,
            "name": self.name,
            "compute_capability": self.compute_capability.value,
            "sm_count": self.sm_count,
            "max_threads_per_block": self.max_threads_per_block,
            "max_threads_per_sm": self.max_threads_per_sm,
            "max_shared_memory_per_block": self.max_shared_memory_per_block,
            "warp_size": self.warp_size,
            "global_memory_bytes": self.memory.capacity_bytes,
            "global_memory_free_bytes": self.memory.bytes_free,
            "registers_per_sm": REGISTERS_PER_SM,
        }

    def __repr__(self) -> str:
        return (
            f"CUDADevice(id={self.device_id}, name='{self.name}', "
            f"sm_count={self.sm_count}, cc={self.compute_capability.value})"
        )


# ============================================================================
# CUDA Runtime
# ============================================================================

class CUDARuntime:
    """The FizzCUDA runtime API.

    Provides the primary interface for GPU compute operations: device
    management, memory allocation and transfer, kernel compilation and
    launch, and stream synchronization. This API mirrors the essential
    surface of the CUDA Runtime API (cudaRT) that application code
    interacts with.

    The runtime manages a pool of virtual GPU devices and provides
    host-device memory transfer primitives that shuttle data between
    the Python heap and GPU device memory.
    """

    def __init__(self, device_count: int = 1, sm_count: int = DEFAULT_SM_COUNT) -> None:
        self._devices: list[CUDADevice] = []
        self._streams: list[CUDAStream] = []
        self._kernels: dict[str, CUDAKernel] = {}
        self._transfers: list[TransferRecord] = []
        self._current_device_id = 0
        self._launch_count = 0

        # Initialize devices
        for i in range(device_count):
            device = CUDADevice(
                device_id=i,
                name=f"FizzCUDA Virtual GPU {i}",
                sm_count=sm_count,
            )
            self._devices.append(device)
            logger.info("Initialized CUDA device %d: %s (%d SMs)", i, device.name, sm_count)

        # Create default stream
        self._default_stream = CUDAStream(stream_id=0)
        self._streams.append(self._default_stream)

        if self._devices:
            self._devices[0]._is_current = True

    def create_device(self, name: str = "FizzCUDA Virtual GPU", sm_count: int = DEFAULT_SM_COUNT) -> CUDADevice:
        """Create and register a new virtual GPU device.

        Returns:
            The newly created device.
        """
        device_id = len(self._devices)
        device = CUDADevice(
            device_id=device_id,
            name=name,
            sm_count=sm_count,
        )
        self._devices.append(device)
        logger.info("Created CUDA device %d: %s", device_id, name)
        return device

    def get_device(self, device_id: int = 0) -> CUDADevice:
        """Get a device by ordinal index.

        Raises:
            CUDADeviceNotFoundError: If the device does not exist.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzcuda import CUDADeviceNotFoundError

        if device_id < 0 or device_id >= len(self._devices):
            raise CUDADeviceNotFoundError(device_id, len(self._devices))
        return self._devices[device_id]

    def list_devices(self) -> list[CUDADevice]:
        """Return the list of all available CUDA devices."""
        return list(self._devices)

    @property
    def device_count(self) -> int:
        return len(self._devices)

    @property
    def current_device(self) -> CUDADevice:
        return self._devices[self._current_device_id]

    def set_device(self, device_id: int) -> None:
        """Set the current device for subsequent operations.

        Raises:
            CUDADeviceNotFoundError: If the device does not exist.
        """
        device = self.get_device(device_id)
        self._devices[self._current_device_id]._is_current = False
        self._current_device_id = device_id
        device._is_current = True

    def allocate(self, size_bytes: int, device_id: Optional[int] = None) -> int:
        """Allocate memory on the specified (or current) device.

        Returns:
            The base address of the allocation.
        """
        did = device_id if device_id is not None else self._current_device_id
        device = self.get_device(did)
        return device.memory.allocate(size_bytes)

    def free(self, address: int, device_id: Optional[int] = None) -> None:
        """Free device memory at the given address."""
        did = device_id if device_id is not None else self._current_device_id
        device = self.get_device(did)
        device.memory.free(address)

    def memcpy_host_to_device(
        self,
        dst_address: int,
        host_data: list[int],
        device_id: Optional[int] = None,
        stream_id: Optional[int] = None,
    ) -> None:
        """Copy data from host memory to device memory.

        Args:
            dst_address: Device memory address to write to.
            host_data: List of integers to transfer.
            device_id: Target device (defaults to current).
            stream_id: Stream for the transfer (defaults to default stream).
        """
        did = device_id if device_id is not None else self._current_device_id
        device = self.get_device(did)
        device.memory.write(dst_address, host_data)

        size = len(host_data) * 4
        stream = self._get_stream(stream_id)
        stream.record_operation("memcpy_h2d", size=size, address=dst_address)
        self._transfers.append(TransferRecord(
            direction=MemoryDirection.HOST_TO_DEVICE,
            size_bytes=size,
            timestamp=time.monotonic(),
            stream_id=stream.stream_id,
        ))
        logger.debug("H2D transfer: %d integers to 0x%08X", len(host_data), dst_address)

    def memcpy_device_to_host(
        self,
        src_address: int,
        count: int,
        device_id: Optional[int] = None,
        stream_id: Optional[int] = None,
    ) -> list[int]:
        """Copy data from device memory to host memory.

        Args:
            src_address: Device memory address to read from.
            count: Number of integers to transfer.
            device_id: Source device (defaults to current).
            stream_id: Stream for the transfer (defaults to default stream).

        Returns:
            List of integers read from device memory.
        """
        did = device_id if device_id is not None else self._current_device_id
        device = self.get_device(did)
        result = device.memory.read(src_address, count)

        size = count * 4
        stream = self._get_stream(stream_id)
        stream.record_operation("memcpy_d2h", size=size, address=src_address)
        self._transfers.append(TransferRecord(
            direction=MemoryDirection.DEVICE_TO_HOST,
            size_bytes=size,
            timestamp=time.monotonic(),
            stream_id=stream.stream_id,
        ))
        logger.debug("D2H transfer: %d integers from 0x%08X", count, src_address)
        return result

    def register_kernel(self, kernel: CUDAKernel) -> None:
        """Register a compiled kernel with the runtime."""
        self._kernels[kernel.name] = kernel
        logger.info("Registered CUDA kernel: '%s'", kernel.name)

    def launch_kernel(
        self,
        kernel_name: str,
        grid_dim: Dim3,
        block_dim: Dim3,
        shared_mem_bytes: int = 0,
        stream_id: Optional[int] = None,
        params: Optional[dict] = None,
        device_id: Optional[int] = None,
    ) -> KernelStats:
        """Launch a registered kernel on the GPU.

        Args:
            kernel_name: Name of the previously registered kernel.
            grid_dim: Grid dimensions (number of blocks).
            block_dim: Block dimensions (threads per block).
            shared_mem_bytes: Dynamic shared memory per block.
            stream_id: Execution stream.
            params: Kernel parameters.
            device_id: Target device (defaults to current).

        Returns:
            Kernel execution statistics.

        Raises:
            CUDAKernelLaunchError: If the kernel is not found or
                launch configuration is invalid.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzcuda import CUDAKernelLaunchError

        if kernel_name not in self._kernels:
            raise CUDAKernelLaunchError(kernel_name, "Kernel not registered")

        kernel = self._kernels[kernel_name]
        did = device_id if device_id is not None else self._current_device_id
        device = self.get_device(did)

        stream = self._get_stream(stream_id)
        stream.record_operation("kernel_launch", kernel=kernel_name)

        stats = kernel.execute(
            grid_dim=grid_dim,
            block_dim=block_dim,
            memory=device.memory,
            shared_mem_bytes=shared_mem_bytes,
            params=params,
        )

        self._launch_count += 1
        return stats

    def synchronize(self, stream_id: Optional[int] = None) -> None:
        """Synchronize the specified stream, or all streams if None.

        Raises:
            CUDASynchronizationError: If an asynchronous error is detected.
        """
        if stream_id is not None:
            stream = self._get_stream(stream_id)
            stream.synchronize()
        else:
            for stream in self._streams:
                stream.synchronize()

    def create_stream(self) -> CUDAStream:
        """Create a new CUDA stream."""
        stream = CUDAStream()
        self._streams.append(stream)
        logger.debug("Created CUDA stream %d", stream.stream_id)
        return stream

    def _get_stream(self, stream_id: Optional[int] = None) -> CUDAStream:
        """Get a stream by ID, defaulting to stream 0."""
        if stream_id is None:
            return self._default_stream
        for stream in self._streams:
            if stream.stream_id == stream_id:
                return stream
        from enterprise_fizzbuzz.domain.exceptions.fizzcuda import CUDAStreamError
        raise CUDAStreamError(stream_id, "Stream not found")

    def get_stats(self) -> dict:
        """Return comprehensive runtime statistics."""
        h2d_bytes = sum(
            t.size_bytes for t in self._transfers
            if t.direction == MemoryDirection.HOST_TO_DEVICE
        )
        d2h_bytes = sum(
            t.size_bytes for t in self._transfers
            if t.direction == MemoryDirection.DEVICE_TO_HOST
        )
        return {
            "version": FIZZCUDA_VERSION,
            "device_count": self.device_count,
            "current_device": self._current_device_id,
            "kernel_count": len(self._kernels),
            "total_launches": self._launch_count,
            "stream_count": len(self._streams),
            "total_transfers": len(self._transfers),
            "h2d_bytes": h2d_bytes,
            "d2h_bytes": d2h_bytes,
            "devices": [d.get_properties() for d in self._devices],
            "streams": [s.get_stats() for s in self._streams],
            "kernels": {
                name: {
                    "launches": k.launch_count,
                    "total_threads": k.total_threads_launched,
                    "state": k.state.value,
                }
                for name, k in self._kernels.items()
            },
        }


# ============================================================================
# FizzBuzz Classification Kernel
# ============================================================================

def fizzbuzz_classify_kernel(
    ctx: ThreadContext,
    memory: GPUMemory,
    shared: SharedMemory,
    params: dict,
) -> None:
    """CUDA kernel that classifies a single number for FizzBuzz.

    Each thread reads its assigned number from the input buffer, computes
    the FizzBuzz classification via modulo operations, and writes the
    result code to the output buffer.

    Classification codes:
        15 -> FizzBuzz (divisible by both 3 and 5)
         3 -> Fizz (divisible by 3 only)
         5 -> Buzz (divisible by 5 only)
         0 -> None (not divisible by 3 or 5)

    Args:
        ctx: Thread execution context with block/thread indices.
        memory: Device global memory containing input and output buffers.
        shared: Per-block shared memory (used for warp-level reduction).
        params: Must contain 'input_addr', 'output_addr', and 'count'.
    """
    gid = ctx.global_thread_id
    count = params.get("count", 0)
    if gid >= count:
        return

    input_addr = params["input_addr"]
    output_addr = params["output_addr"]

    # Read input number from global memory
    number = memory._data.get(input_addr + gid * 4, 0)

    # Classify using modular arithmetic
    if number == 0:
        result = CLASSIFY_NONE
    elif number % 15 == 0:
        result = CLASSIFY_FIZZBUZZ
    elif number % 3 == 0:
        result = CLASSIFY_FIZZ
    elif number % 5 == 0:
        result = CLASSIFY_BUZZ
    else:
        result = CLASSIFY_NONE

    # Write classification to output buffer
    memory._data[output_addr + gid * 4] = result

    # Store partial count in shared memory for block-level statistics
    tid = ctx.thread_idx.x
    if result == CLASSIFY_FIZZBUZZ:
        current = shared.load(0)
        shared.store(0, current + 1)
    elif result == CLASSIFY_FIZZ:
        current = shared.load(4)
        shared.store(4, current + 1)
    elif result == CLASSIFY_BUZZ:
        current = shared.load(8)
        shared.store(8, current + 1)


def classification_code_to_string(code: int) -> str:
    """Convert a numeric classification code to its string representation."""
    if code == CLASSIFY_FIZZBUZZ:
        return "FizzBuzz"
    elif code == CLASSIFY_FIZZ:
        return "Fizz"
    elif code == CLASSIFY_BUZZ:
        return "Buzz"
    return ""


# ============================================================================
# Dashboard
# ============================================================================

class CUDADashboard:
    """ASCII dashboard for the FizzCUDA GPU compute framework.

    Renders a comprehensive overview of GPU device status, memory
    utilization, kernel execution statistics, and data transfer
    volumes in a fixed-width terminal-friendly format.
    """

    @staticmethod
    def render(runtime: CUDARuntime, width: int = 72) -> str:
        """Render the FizzCUDA dashboard."""
        stats = runtime.get_stats()
        sep = "+" + "-" * (width - 2) + "+"

        lines = [
            sep,
            _center(f"FizzCUDA GPU Compute Dashboard v{FIZZCUDA_VERSION}", width),
            sep,
        ]

        # Runtime overview
        lines.append(_center("Runtime Overview", width))
        lines.append(sep)
        lines.append(_kv("Devices", str(stats["device_count"]), width))
        lines.append(_kv("Registered Kernels", str(stats["kernel_count"]), width))
        lines.append(_kv("Total Launches", str(stats["total_launches"]), width))
        lines.append(_kv("Active Streams", str(stats["stream_count"]), width))
        lines.append(_kv("Total Transfers", str(stats["total_transfers"]), width))
        lines.append(_kv("H2D Bytes", f"{stats['h2d_bytes']:,}", width))
        lines.append(_kv("D2H Bytes", f"{stats['d2h_bytes']:,}", width))
        lines.append(sep)

        # Device details
        for dev in stats["devices"]:
            lines.append(_center(f"Device {dev['device_id']}: {dev['name']}", width))
            lines.append(sep)
            lines.append(_kv("Compute Capability", dev["compute_capability"], width))
            lines.append(_kv("SM Count", str(dev["sm_count"]), width))
            lines.append(_kv("Max Threads/Block", str(dev["max_threads_per_block"]), width))
            lines.append(_kv("Warp Size", str(dev["warp_size"]), width))

            # Memory bar
            total = dev["global_memory_bytes"]
            free = dev["global_memory_free_bytes"]
            used = total - free
            util = (used / total * 100) if total > 0 else 0.0
            bar_width = width - 30
            filled = int(util / 100.0 * bar_width)
            bar = "#" * filled + "." * (bar_width - filled)
            lines.append(_kv("Memory", f"[{bar}] {util:.1f}%", width))
            lines.append(sep)

        # Kernel stats
        if stats["kernels"]:
            lines.append(_center("Kernel Statistics", width))
            lines.append(sep)
            for name, kstats in stats["kernels"].items():
                lines.append(_kv(f"  {name}", f"{kstats['launches']} launches, {kstats['total_threads']} threads", width))
            lines.append(sep)

        return "\n".join(lines)


def _center(text: str, width: int) -> str:
    """Center text within the dashboard border."""
    inner = width - 4
    return f"| {text:^{inner}} |"


def _kv(key: str, value: str, width: int) -> str:
    """Format a key-value pair within the dashboard border."""
    inner = width - 4
    key_width = inner - len(value) - 2
    if key_width < 1:
        key_width = 1
    return f"| {key:<{key_width}} {value:>{len(value)}} |"


# ============================================================================
# Middleware
# ============================================================================

class CUDAMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through the FizzCUDA GPU.

    When enabled, this middleware intercepts evaluation requests and
    dispatches them as GPU kernel invocations. Each number is assigned
    to a GPU thread, classified in parallel across the virtual device's
    streaming multiprocessor array, and the result is stored in the
    processing context metadata.

    The middleware pre-compiles and registers the FizzBuzz classification
    kernel at construction time, so kernel launch latency during
    evaluation is limited to the actual thread execution time.
    """

    def __init__(self, runtime: CUDARuntime) -> None:
        self.runtime = runtime
        self.evaluations = 0
        self._results_cache: dict[int, str] = {}

        # Register the FizzBuzz kernel
        kernel = CUDAKernel(
            name="fizzbuzz_classify",
            func=fizzbuzz_classify_kernel,
        )
        self.runtime.register_kernel(kernel)

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        """Process a FizzBuzz evaluation through the GPU compute pipeline."""
        from enterprise_fizzbuzz.domain.models import ProcessingContext

        number = context.number

        if number not in self._results_cache:
            self._classify_batch([number])

        self.evaluations += 1

        if number in self._results_cache:
            context.metadata["cuda_classification"] = self._results_cache[number]
            context.metadata["cuda_enabled"] = True

        return next_handler(context)

    def _classify_batch(self, numbers: list[int]) -> dict[int, str]:
        """Classify a batch of numbers through the GPU pipeline."""
        device = self.runtime.current_device
        count = len(numbers)

        # Allocate input and output buffers
        input_size = count * 4
        output_size = count * 4
        input_addr = self.runtime.allocate(input_size)
        output_addr = self.runtime.allocate(output_size)

        # Transfer input data to device
        self.runtime.memcpy_host_to_device(input_addr, numbers)

        # Calculate grid dimensions
        block_size = min(DEFAULT_BLOCK_SIZE, MAX_THREADS_PER_BLOCK)
        grid_size = math.ceil(count / block_size)

        # Launch kernel
        self.runtime.launch_kernel(
            kernel_name="fizzbuzz_classify",
            grid_dim=Dim3(x=grid_size),
            block_dim=Dim3(x=block_size),
            params={
                "input_addr": input_addr,
                "output_addr": output_addr,
                "count": count,
            },
        )

        # Synchronize and transfer results back
        self.runtime.synchronize()
        codes = self.runtime.memcpy_device_to_host(output_addr, count)

        # Convert codes to strings and cache
        results = {}
        for i, num in enumerate(numbers):
            label = classification_code_to_string(codes[i])
            results[num] = label
            self._results_cache[num] = label

        # Free device memory
        self.runtime.free(input_addr)
        self.runtime.free(output_addr)

        return results

    def classify_numbers(self, numbers: list[int]) -> dict[int, str]:
        """Public API for batch GPU classification."""
        return self._classify_batch(numbers)

    def get_name(self) -> str:
        return "fizzcuda"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzcuda_subsystem(
    device_count: int = 1,
    sm_count: int = DEFAULT_SM_COUNT,
) -> tuple[CUDARuntime, CUDAMiddleware]:
    """Create and configure the complete FizzCUDA subsystem.

    Initializes the CUDA runtime with the specified number of virtual
    GPU devices, registers the FizzBuzz classification kernel, and
    creates the middleware component for pipeline integration.

    Args:
        device_count: Number of virtual GPU devices to initialize.
        sm_count: Streaming multiprocessor count per device.

    Returns:
        Tuple of (CUDARuntime, CUDAMiddleware).
    """
    runtime = CUDARuntime(device_count=device_count, sm_count=sm_count)
    middleware = CUDAMiddleware(runtime)

    logger.info(
        "FizzCUDA subsystem initialized: %d device(s), %d SMs per device, "
        "kernel 'fizzbuzz_classify' registered",
        device_count, sm_count,
    )

    return runtime, middleware
