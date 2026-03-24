"""
Enterprise FizzBuzz Platform - FizzSystemd: Service Manager & Init System Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._base import FizzBuzzError


class SystemdError(FizzBuzzError):
    """Base exception for FizzSystemd service manager errors.

    All exceptions originating from the service manager and init system
    inherit from this class.  FizzSystemd manages the lifecycle of every
    infrastructure service in the Enterprise FizzBuzz Platform, and errors
    in this subsystem can affect the availability of the entire platform.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-SYD00"
        self.context = {"reason": reason}


class UnitFileParseError(SystemdError):
    """Raised when a unit file contains invalid syntax or structure.

    The unit file parser encountered malformed INI syntax, an unknown
    section, a missing required field, or an invalid value in a unit
    file.  The unit cannot be loaded until the file is corrected.
    """

    def __init__(self, unit_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to parse unit file '{unit_name}': {reason}. "
            f"The unit file's INI structure does not conform to the "
            f"systemd.unit(5) specification."
        )
        self.error_code = "EFP-SYD01"
        self.context = {"unit_name": unit_name, "reason": reason}


class UnitNotFoundError(SystemdError):
    """Raised when a referenced unit does not exist."""

    def __init__(self, unit_name: str) -> None:
        super().__init__(
            f"Unit '{unit_name}' not found. The unit file does not exist "
            f"in the unit directory and no transient unit with this name "
            f"has been created."
        )
        self.error_code = "EFP-SYD02"
        self.context = {"unit_name": unit_name}


class UnitMaskedError(SystemdError):
    """Raised when attempting to start a masked unit."""

    def __init__(self, unit_name: str) -> None:
        super().__init__(
            f"Unit '{unit_name}' is masked. Masked units cannot be started "
            f"by any means. Use 'fizzctl unmask {unit_name}' to remove the mask."
        )
        self.error_code = "EFP-SYD03"
        self.context = {"unit_name": unit_name}


class DependencyCycleError(SystemdError):
    """Raised when the dependency graph contains a cycle."""

    def __init__(self, cycle: List[str]) -> None:
        cycle_str = " -> ".join(cycle)
        super().__init__(
            f"Dependency cycle detected: {cycle_str}. Topological sort is "
            f"impossible. Break the cycle by removing or restructuring "
            f"unit dependencies."
        )
        self.error_code = "EFP-SYD04"
        self.context = {"cycle": cycle}


class DependencyConflictError(SystemdError):
    """Raised when a transaction includes conflicting units."""

    def __init__(self, unit_a: str, unit_b: str) -> None:
        super().__init__(
            f"Units '{unit_a}' and '{unit_b}' are in conflict. Starting "
            f"one requires stopping the other. The transaction cannot "
            f"satisfy both simultaneously."
        )
        self.error_code = "EFP-SYD05"
        self.context = {"unit_a": unit_a, "unit_b": unit_b}


class TransactionError(SystemdError):
    """Raised when a transaction cannot be committed."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Transaction failed: {reason}. The requested operation "
            f"could not be executed atomically."
        )
        self.error_code = "EFP-SYD06"
        self.context = {"reason": reason}


class ServiceStartError(SystemdError):
    """Raised when a service fails to start."""

    def __init__(self, unit_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to start '{unit_name}': {reason}."
        )
        self.error_code = "EFP-SYD07"
        self.context = {"unit_name": unit_name, "reason": reason}


class ServiceStopError(SystemdError):
    """Raised when a service fails to stop within the timeout."""

    def __init__(self, unit_name: str, timeout: float) -> None:
        super().__init__(
            f"Service '{unit_name}' did not stop within {timeout:.0f} seconds. "
            f"The service will be forcefully terminated."
        )
        self.error_code = "EFP-SYD08"
        self.context = {"unit_name": unit_name, "timeout": timeout}


class ServiceTimeoutError(SystemdError):
    """Raised when a service exceeds its startup or runtime deadline."""

    def __init__(self, unit_name: str, phase: str, timeout: float) -> None:
        super().__init__(
            f"Service '{unit_name}' timed out during {phase} after "
            f"{timeout:.0f} seconds."
        )
        self.error_code = "EFP-SYD09"
        self.context = {"unit_name": unit_name, "phase": phase, "timeout": timeout}


class WatchdogTimeoutError(SystemdError):
    """Raised when a service fails to ping the watchdog within its deadline."""

    def __init__(self, unit_name: str, watchdog_sec: float, last_ping_ago: float) -> None:
        super().__init__(
            f"Watchdog timeout for '{unit_name}': deadline was {watchdog_sec:.1f}s, "
            f"last ping was {last_ping_ago:.1f}s ago. The service is considered hung."
        )
        self.error_code = "EFP-SYD10"
        self.context = {"unit_name": unit_name, "watchdog_sec": watchdog_sec, "last_ping_ago": last_ping_ago}


class RestartLimitHitError(SystemdError):
    """Raised when a service exceeds its restart rate limit."""

    def __init__(self, unit_name: str, burst: int, interval: float) -> None:
        super().__init__(
            f"Service '{unit_name}' restarted {burst} times within "
            f"{interval:.0f} seconds. Restart rate limit hit. "
            f"No further automatic restarts will be attempted."
        )
        self.error_code = "EFP-SYD11"
        self.context = {"unit_name": unit_name, "burst": burst, "interval": interval}


class SocketActivationError(SystemdError):
    """Raised when socket activation fails."""

    def __init__(self, socket_unit: str, reason: str) -> None:
        super().__init__(
            f"Socket activation failed for '{socket_unit}': {reason}."
        )
        self.error_code = "EFP-SYD12"
        self.context = {"socket_unit": socket_unit, "reason": reason}


class SocketBindError(SystemdError):
    """Raised when a socket cannot be bound to its configured address."""

    def __init__(self, socket_unit: str, address: str, reason: str) -> None:
        super().__init__(
            f"Failed to bind socket '{socket_unit}' to '{address}': {reason}."
        )
        self.error_code = "EFP-SYD13"
        self.context = {"socket_unit": socket_unit, "address": address, "reason": reason}


class TimerParseError(SystemdError):
    """Raised when a calendar expression cannot be parsed."""

    def __init__(self, expression: str, reason: str) -> None:
        super().__init__(
            f"Failed to parse calendar expression '{expression}': {reason}. "
            f"Calendar expressions must follow systemd.time(7) format."
        )
        self.error_code = "EFP-SYD14"
        self.context = {"expression": expression, "reason": reason}


class MountError(SystemdError):
    """Raised when a mount operation fails."""

    def __init__(self, unit_name: str, what: str, where: str, reason: str) -> None:
        super().__init__(
            f"Failed to mount '{what}' at '{where}' for unit '{unit_name}': {reason}."
        )
        self.error_code = "EFP-SYD15"
        self.context = {"unit_name": unit_name, "what": what, "where": where, "reason": reason}


class JournalError(SystemdError):
    """Raised when a journal operation fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Journal error: {reason}."
        )
        self.error_code = "EFP-SYD16"
        self.context = {"reason": reason}


class JournalSealVerificationError(SystemdError):
    """Raised when journal seal verification detects tampering."""

    def __init__(self, seal_id: int, reason: str) -> None:
        super().__init__(
            f"Journal seal verification failed at seal #{seal_id}: {reason}. "
            f"The journal may have been tampered with."
        )
        self.error_code = "EFP-SYD17"
        self.context = {"seal_id": seal_id, "reason": reason}


class CgroupDelegationError(SystemdError):
    """Raised when cgroup delegation for a service fails."""

    def __init__(self, unit_name: str, controller: str, reason: str) -> None:
        super().__init__(
            f"Failed to configure cgroup {controller} controller for "
            f"'{unit_name}': {reason}."
        )
        self.error_code = "EFP-SYD18"
        self.context = {"unit_name": unit_name, "controller": controller, "reason": reason}


class InhibitorLockError(SystemdError):
    """Raised when an inhibitor lock operation fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Inhibitor lock error: {reason}."
        )
        self.error_code = "EFP-SYD19"
        self.context = {"reason": reason}


class ShutdownInhibitedError(SystemdError):
    """Raised when shutdown is blocked by active inhibitor locks."""

    def __init__(self, lock_holders: List[str]) -> None:
        holders_str = ", ".join(lock_holders)
        super().__init__(
            f"Shutdown inhibited by: {holders_str}. Active inhibitor locks "
            f"are preventing the shutdown sequence. Use 'fizzctl poweroff --force' "
            f"to bypass inhibitor locks."
        )
        self.error_code = "EFP-SYD20"
        self.context = {"lock_holders": lock_holders}


class BusError(SystemdError):
    """Raised when a D-Bus IPC operation fails."""

    def __init__(self, method: str, reason: str) -> None:
        super().__init__(
            f"D-Bus method call '{method}' failed: {reason}."
        )
        self.error_code = "EFP-SYD21"
        self.context = {"method": method, "reason": reason}


class TransientUnitError(SystemdError):
    """Raised when a transient unit operation fails."""

    def __init__(self, unit_name: str, reason: str) -> None:
        super().__init__(
            f"Transient unit '{unit_name}' error: {reason}."
        )
        self.error_code = "EFP-SYD22"
        self.context = {"unit_name": unit_name, "reason": reason}


class BootFailureError(SystemdError):
    """Raised when the boot sequence fails to reach the default target."""

    def __init__(self, target: str, failed_units: List[str]) -> None:
        failed_str = ", ".join(failed_units)
        super().__init__(
            f"Boot failed: could not reach target '{target}'. "
            f"Failed units: {failed_str}."
        )
        self.error_code = "EFP-SYD23"
        self.context = {"target": target, "failed_units": failed_units}


class SystemdMiddlewareError(SystemdError):
    """Raised when the FizzSystemd middleware encounters an error."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzSystemd middleware error: {reason}."
        )
        self.error_code = "EFP-SYD24"
        self.context = {"reason": reason}
