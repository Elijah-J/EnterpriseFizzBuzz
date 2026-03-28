"""
Enterprise FizzBuzz Platform - FizzAVX Exceptions (EFP-AVX0 through EFP-AVX7)

Exception hierarchy for the SIMD/AVX instruction engine. These exceptions
cover register file violations, lane index out-of-range errors, unsupported
operation modes, mask validation failures, and vector width mismatches that
may arise during AVX-accelerated FizzBuzz classification.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class AVXError(FizzBuzzError):
    """Base exception for all FizzAVX SIMD engine errors.

    The FizzAVX subsystem provides a 256-bit SIMD instruction engine for
    data-parallel FizzBuzz classification. When the virtual vector unit
    encounters invalid register references, lane overflows, or mask
    mismatches, this exception hierarchy provides precise diagnostics.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-AVX0"),
            context=kwargs.pop("context", {}),
        )


class AVXRegisterError(AVXError):
    """Raised when a register index is out of range."""

    def __init__(self, register: int, max_registers: int) -> None:
        super().__init__(
            f"AVX register ymm{register} out of range "
            f"(max: ymm{max_registers - 1})",
            error_code="EFP-AVX1",
            context={"register": register, "max_registers": max_registers},
        )
        self.register = register
        self.max_registers = max_registers


class AVXLaneError(AVXError):
    """Raised when a lane index exceeds the vector width."""

    def __init__(self, lane: int, width: int) -> None:
        super().__init__(
            f"Lane index {lane} exceeds vector width {width}",
            error_code="EFP-AVX2",
            context={"lane": lane, "width": width},
        )
        self.lane = lane
        self.width = width


class AVXWidthMismatchError(AVXError):
    """Raised when operand vector widths do not match."""

    def __init__(self, left: int, right: int) -> None:
        super().__init__(
            f"Vector width mismatch: left has {left} lanes, right has {right} lanes",
            error_code="EFP-AVX3",
            context={"left_width": left, "right_width": right},
        )
        self.left_width = left
        self.right_width = right


class AVXMaskError(AVXError):
    """Raised when a mask operand has an invalid bit pattern."""

    def __init__(self, mask_value: int, expected_bits: int) -> None:
        super().__init__(
            f"Invalid mask value 0x{mask_value:X}: "
            f"expected {expected_bits}-bit mask",
            error_code="EFP-AVX4",
            context={"mask_value": mask_value, "expected_bits": expected_bits},
        )
        self.mask_value = mask_value
        self.expected_bits = expected_bits


class AVXShuffleError(AVXError):
    """Raised when a shuffle control word references invalid lanes."""

    def __init__(self, control: tuple, num_lanes: int) -> None:
        super().__init__(
            f"Shuffle control {control} references lane >= {num_lanes}",
            error_code="EFP-AVX5",
            context={"control": str(control), "num_lanes": num_lanes},
        )
        self.control = control
        self.num_lanes = num_lanes


class AVXAlignmentError(AVXError):
    """Raised when memory operands are not aligned to vector boundaries."""

    def __init__(self, address: int, required_alignment: int) -> None:
        super().__init__(
            f"Address 0x{address:X} not aligned to {required_alignment}-byte boundary",
            error_code="EFP-AVX6",
            context={"address": address, "required_alignment": required_alignment},
        )
        self.address = address
        self.required_alignment = required_alignment


class AVXUnsupportedOperationError(AVXError):
    """Raised when an unsupported SIMD operation is requested."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"Unsupported AVX operation: {operation}",
            error_code="EFP-AVX7",
            context={"operation": operation},
        )
        self.operation = operation
