"""
Enterprise FizzBuzz Platform - FizzCXL Exceptions (EFP-CXL0 through EFP-CXL7)

Exception hierarchy for the Compute Express Link subsystem. These exceptions
cover CXL device class errors, memory pooling failures, coherency engine
faults, HDM decoder misconfigurations, and back-invalidation anomalies
that may arise during CXL-accelerated FizzBuzz evaluation.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class CXLError(FizzBuzzError):
    """Base exception for all FizzCXL errors.

    The FizzCXL subsystem implements the Compute Express Link protocol
    with Type 1/2/3 device classes, memory pooling, a coherency engine,
    HDM decoder, and back-invalidation for cache-coherent FizzBuzz
    evaluation across heterogeneous compute.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CXL0"),
            context=kwargs.pop("context", {}),
        )


class CXLDeviceError(CXLError):
    """Raised when a CXL device cannot be initialized or accessed."""

    def __init__(self, device_id: str, device_type: int, reason: str) -> None:
        super().__init__(
            f"CXL Type-{device_type} device '{device_id}' error: {reason}",
            error_code="EFP-CXL1",
            context={"device_id": device_id, "device_type": device_type, "reason": reason},
        )
        self.device_id = device_id
        self.device_type = device_type
        self.reason = reason


class CXLMemoryPoolError(CXLError):
    """Raised when CXL memory pooling fails."""

    def __init__(self, pool_id: str, reason: str) -> None:
        super().__init__(
            f"CXL memory pool '{pool_id}' error: {reason}",
            error_code="EFP-CXL2",
            context={"pool_id": pool_id, "reason": reason},
        )
        self.pool_id = pool_id
        self.reason = reason


class CXLCoherencyError(CXLError):
    """Raised when the CXL coherency engine detects a protocol violation."""

    def __init__(self, cache_line: int, reason: str) -> None:
        super().__init__(
            f"CXL coherency violation at cache line 0x{cache_line:08x}: {reason}",
            error_code="EFP-CXL3",
            context={"cache_line": cache_line, "reason": reason},
        )
        self.cache_line = cache_line
        self.reason = reason


class CXLHDMDecoderError(CXLError):
    """Raised when HDM decoder configuration or address resolution fails."""

    def __init__(self, decoder_id: int, reason: str) -> None:
        super().__init__(
            f"CXL HDM decoder {decoder_id} error: {reason}",
            error_code="EFP-CXL4",
            context={"decoder_id": decoder_id, "reason": reason},
        )
        self.decoder_id = decoder_id
        self.reason = reason


class CXLBackInvalidationError(CXLError):
    """Raised when a back-invalidation request cannot be completed."""

    def __init__(self, device_id: str, address: int) -> None:
        super().__init__(
            f"CXL back-invalidation failed for device '{device_id}' "
            f"at address 0x{address:016x}",
            error_code="EFP-CXL5",
            context={"device_id": device_id, "address": address},
        )
        self.device_id = device_id
        self.address = address


class CXLFlitError(CXLError):
    """Raised when a CXL flit transmission or reception fails."""

    def __init__(self, flit_type: str, reason: str) -> None:
        super().__init__(
            f"CXL {flit_type} flit error: {reason}",
            error_code="EFP-CXL6",
            context={"flit_type": flit_type, "reason": reason},
        )
        self.flit_type = flit_type
        self.reason = reason


class CXLBISnpError(CXLError):
    """Raised when a back-invalidation snoop fails."""

    def __init__(self, address: int, snoop_type: str) -> None:
        super().__init__(
            f"CXL BI snoop ({snoop_type}) at 0x{address:016x} failed",
            error_code="EFP-CXL7",
            context={"address": address, "snoop_type": snoop_type},
        )
        self.address = address
        self.snoop_type = snoop_type
