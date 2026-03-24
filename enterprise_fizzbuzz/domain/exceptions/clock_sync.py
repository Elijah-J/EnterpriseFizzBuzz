"""
Enterprise FizzBuzz Platform - Clock Synchronization Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ClockSyncError(FizzBuzzError):
    """Base exception for all NTP/PTP clock synchronization errors.

    Clock synchronization is critical for maintaining causal ordering
    of FizzBuzz evaluation timestamps across distributed nodes. Any
    failure in the synchronization pipeline — from NTP packet exchange
    to PI controller discipline — raises a subclass of this exception.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-NTP0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ClockDriftExceededError(ClockSyncError):
    """Raised when a clock's drift rate exceeds the correctable range.

    The PI controller can compensate for drift rates up to approximately
    500 ppm through frequency slewing. Beyond that threshold, the
    oscillator's frequency offset is too severe for gradual correction
    and indicates a hardware-level failure in the simulated clock
    crystal, which is impressive given that the crystal does not exist.
    """

    def __init__(self, clock_name: str, drift_ppm: float, max_ppm: float) -> None:
        super().__init__(
            f"Clock '{clock_name}' drift rate {drift_ppm:.2f} ppm exceeds "
            f"maximum correctable range of {max_ppm:.2f} ppm",
            error_code="EFP-NTP1",
            context={
                "clock_name": clock_name,
                "drift_ppm": drift_ppm,
                "max_ppm": max_ppm,
            },
        )
        self.clock_name = clock_name
        self.drift_ppm = drift_ppm
        self.max_ppm = max_ppm


class StratumError(ClockSyncError):
    """Raised when the stratum hierarchy encounters an invalid configuration.

    Stratum levels must fall within the range 0-16, where stratum 16
    indicates an unsynchronized clock per RFC 5905. Attempting to create
    nodes beyond stratum 16, or referencing nonexistent parent nodes,
    triggers this exception.
    """

    def __init__(self, stratum: int, reason: str) -> None:
        super().__init__(
            f"Stratum hierarchy error at level {stratum}: {reason}",
            error_code="EFP-NTP2",
            context={"stratum": stratum, "reason": reason},
        )
        self.stratum = stratum
        self.reason = reason


class NTPPacketError(ClockSyncError):
    """Raised when an NTP packet fails validation.

    NTP v4 packets must conform to the format specified in RFC 5905.
    Invalid version numbers, malformed timestamps, or unsupported
    modes cause this exception. In the FizzBuzz platform, packets are
    Python dataclasses rather than raw UDP datagrams, but validation
    standards remain equally rigorous.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        super().__init__(
            f"NTP packet validation error in field '{field_name}': {reason}",
            error_code="EFP-NTP3",
            context={"field_name": field_name, "reason": reason},
        )
        self.field_name = field_name
        self.reason = reason

