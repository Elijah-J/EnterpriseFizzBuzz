"""
Enterprise FizzBuzz Platform - FizzCUDA Exceptions (EFP-CUDA0 through EFP-CUDA7)

Exception hierarchy for the CUDA-style GPU compute framework. These exceptions
cover device initialization failures, kernel launch errors, memory allocation
and transfer faults, stream synchronization violations, and thread block
configuration errors that may arise during GPU-accelerated FizzBuzz classification.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class CUDAError(FizzBuzzError):
    """Base exception for all FizzCUDA GPU compute errors.

    The FizzCUDA subsystem provides a CUDA-style programming model for
    massively parallel FizzBuzz classification. When the virtual GPU
    encounters an unrecoverable condition during device management,
    kernel execution, or memory operations, this exception hierarchy
    provides precise diagnostic information about the failure mode.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CUDA0"),
            context=kwargs.pop("context", {}),
        )


class CUDADeviceNotFoundError(CUDAError):
    """Raised when a requested GPU device does not exist.

    Each virtual GPU device is identified by an ordinal index. Requesting
    a device beyond the available count indicates either a misconfigured
    multi-GPU topology or an incorrect device ordinal in the application
    configuration.
    """

    def __init__(self, device_id: int, available: int) -> None:
        super().__init__(
            f"CUDA device {device_id} not found. "
            f"Available devices: {available}",
            error_code="EFP-CUDA1",
            context={"device_id": device_id, "available": available},
        )
        self.device_id = device_id
        self.available = available


class CUDAKernelLaunchError(CUDAError):
    """Raised when a kernel launch fails due to invalid configuration.

    Kernel launches require valid grid and block dimensions that do not
    exceed the device's maximum thread limits. This exception is raised
    when the launch configuration violates hardware constraints, such as
    exceeding the maximum threads per block or requesting more shared
    memory than available.
    """

    def __init__(self, kernel_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to launch kernel '{kernel_name}': {reason}",
            error_code="EFP-CUDA2",
            context={"kernel_name": kernel_name, "reason": reason},
        )
        self.kernel_name = kernel_name
        self.reason = reason


class CUDAMemoryError(CUDAError):
    """Raised when device memory allocation or transfer fails.

    GPU memory is a finite resource. When allocation requests exceed
    available device memory, or when host-device transfers reference
    invalid memory regions, this exception provides details about the
    failed operation and current memory utilization.
    """

    def __init__(self, operation: str, size_bytes: int, available_bytes: int) -> None:
        super().__init__(
            f"CUDA memory error during {operation}: requested {size_bytes} bytes, "
            f"{available_bytes} bytes available",
            error_code="EFP-CUDA3",
            context={
                "operation": operation,
                "size_bytes": size_bytes,
                "available_bytes": available_bytes,
            },
        )
        self.operation = operation
        self.size_bytes = size_bytes
        self.available_bytes = available_bytes


class CUDAStreamError(CUDAError):
    """Raised when a CUDA stream operation fails.

    Streams provide ordered sequences of GPU operations. Errors in stream
    management — such as synchronizing a destroyed stream or submitting
    work to a stream that has encountered a prior error — produce this
    exception with details about the stream state.
    """

    def __init__(self, stream_id: int, reason: str) -> None:
        super().__init__(
            f"CUDA stream {stream_id} error: {reason}",
            error_code="EFP-CUDA4",
            context={"stream_id": stream_id, "reason": reason},
        )
        self.stream_id = stream_id
        self.reason = reason


class CUDAInvalidBlockDimError(CUDAError):
    """Raised when thread block dimensions exceed device limits.

    CUDA thread blocks have maximum dimensions constrained by the GPU
    architecture. For the FizzCUDA virtual GPU, the maximum threads per
    block is 1024, and each dimension (x, y, z) has its own upper bound.
    Violating these constraints produces undefined behavior on real
    hardware; the virtual GPU raises this exception instead.
    """

    def __init__(self, block_dim: tuple, max_threads: int) -> None:
        total = block_dim[0] * block_dim[1] * block_dim[2]
        super().__init__(
            f"Invalid block dimensions {block_dim} "
            f"(total threads {total} exceeds maximum {max_threads})",
            error_code="EFP-CUDA5",
            context={
                "block_dim": block_dim,
                "total_threads": total,
                "max_threads": max_threads,
            },
        )
        self.block_dim = block_dim
        self.max_threads = max_threads


class CUDASharedMemoryExceededError(CUDAError):
    """Raised when shared memory request exceeds per-block capacity.

    Each thread block has access to a fixed amount of fast on-chip shared
    memory. Kernels that declare more shared memory than available cannot
    be launched. This is a compile-time constraint in real CUDA; the
    FizzCUDA runtime enforces it at launch time.
    """

    def __init__(self, requested: int, capacity: int) -> None:
        super().__init__(
            f"Shared memory request ({requested} bytes) exceeds "
            f"per-block capacity ({capacity} bytes)",
            error_code="EFP-CUDA6",
            context={"requested": requested, "capacity": capacity},
        )
        self.requested = requested
        self.capacity = capacity


class CUDASynchronizationError(CUDAError):
    """Raised when device synchronization detects an asynchronous error.

    GPU operations execute asynchronously. Errors that occur during kernel
    execution are not detected until the next synchronization point. This
    exception surfaces those deferred errors with the original failure
    context.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"CUDA synchronization detected asynchronous error: {detail}",
            error_code="EFP-CUDA7",
            context={"detail": detail},
        )
        self.detail = detail
