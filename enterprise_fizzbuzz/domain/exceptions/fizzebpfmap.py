"""
Enterprise FizzBuzz Platform - FizzEBPFMap Exceptions (EFP-EBPF0 through EFP-EBPF7)

Exception hierarchy for the eBPF map data structures subsystem. These exceptions
cover map creation failures, key/value size violations, capacity overflows,
lookup misses, trie prefix errors, and ring buffer drain conditions.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class EBPFMapError(FizzBuzzError):
    """Base exception for all FizzEBPFMap errors.

    The FizzEBPFMap subsystem provides kernel-style eBPF map data structures
    for high-performance FizzBuzz classification data storage. When map
    operations encounter invalid keys, capacity exhaustion, or type
    mismatches, this hierarchy provides structured diagnostics.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-EBPF0"),
            context=kwargs.pop("context", {}),
        )


class EBPFMapNotFoundError(EBPFMapError):
    """Raised when a map lookup by ID or name returns no result."""

    def __init__(self, map_id: str) -> None:
        super().__init__(
            f"eBPF map '{map_id}' not found in registry",
            error_code="EFP-EBPF1",
            context={"map_id": map_id},
        )
        self.map_id = map_id


class EBPFMapFullError(EBPFMapError):
    """Raised when a map has reached its maximum entry capacity."""

    def __init__(self, map_name: str, max_entries: int) -> None:
        super().__init__(
            f"eBPF map '{map_name}' is full (max_entries: {max_entries})",
            error_code="EFP-EBPF2",
            context={"map_name": map_name, "max_entries": max_entries},
        )
        self.map_name = map_name
        self.max_entries = max_entries


class EBPFMapKeyError(EBPFMapError):
    """Raised when a key does not exist in the map during lookup or delete."""

    def __init__(self, map_name: str, key: Any) -> None:
        super().__init__(
            f"Key not found in eBPF map '{map_name}': {key}",
            error_code="EFP-EBPF3",
            context={"map_name": map_name, "key": str(key)},
        )
        self.map_name = map_name
        self.key = key


class EBPFMapKeySizeError(EBPFMapError):
    """Raised when a key exceeds the configured key size for the map."""

    def __init__(self, map_name: str, actual: int, expected: int) -> None:
        super().__init__(
            f"Key size mismatch in eBPF map '{map_name}': "
            f"got {actual} bytes, expected {expected} bytes",
            error_code="EFP-EBPF4",
            context={"map_name": map_name, "actual": actual, "expected": expected},
        )
        self.map_name = map_name
        self.actual = actual
        self.expected = expected


class EBPFMapValueSizeError(EBPFMapError):
    """Raised when a value exceeds the configured value size for the map."""

    def __init__(self, map_name: str, actual: int, expected: int) -> None:
        super().__init__(
            f"Value size mismatch in eBPF map '{map_name}': "
            f"got {actual} bytes, expected {expected} bytes",
            error_code="EFP-EBPF5",
            context={"map_name": map_name, "actual": actual, "expected": expected},
        )
        self.map_name = map_name
        self.actual = actual
        self.expected = expected


class EBPFRingBufferError(EBPFMapError):
    """Raised when a ring buffer operation fails."""

    def __init__(self, buffer_name: str, reason: str) -> None:
        super().__init__(
            f"Ring buffer '{buffer_name}' error: {reason}",
            error_code="EFP-EBPF6",
            context={"buffer_name": buffer_name, "reason": reason},
        )
        self.buffer_name = buffer_name
        self.reason = reason


class EBPFLPMTrieError(EBPFMapError):
    """Raised when an LPM trie operation encounters an invalid prefix."""

    def __init__(self, prefix_len: int, max_prefix_len: int) -> None:
        super().__init__(
            f"LPM trie prefix length {prefix_len} exceeds maximum {max_prefix_len}",
            error_code="EFP-EBPF7",
            context={"prefix_len": prefix_len, "max_prefix_len": max_prefix_len},
        )
        self.prefix_len = prefix_len
        self.max_prefix_len = max_prefix_len
