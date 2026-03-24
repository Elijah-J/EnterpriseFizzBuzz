"""
Enterprise FizzBuzz Platform - FizzNet TCP/IP Protocol Stack exceptions (EFP-NET0 through EFP-NET7)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzNetError(FizzBuzzError):
    """Base exception for all FizzNet TCP/IP Protocol Stack errors.

    The FizzNet subsystem implements a complete TCP/IP stack for
    in-memory FizzBuzz classification delivery. Any failure at any
    layer of the stack — Ethernet, IP, TCP, or the application-layer
    FizzBuzz Protocol — is represented by a subclass of this exception.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-NET0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FizzNetChecksumError(FizzNetError):
    """Raised when a packet or frame fails integrity verification.

    Checksums are the last line of defense against data corruption in
    transit. When a checksum fails on an in-memory packet that never
    left the process, it suggests something far more troubling than
    a flipped bit on a wire — it suggests a bug in the checksum
    computation itself, which is an existential crisis for a protocol
    stack.
    """

    def __init__(self, layer: str, expected: int, actual: int) -> None:
        super().__init__(
            f"{layer} checksum verification failed: expected 0x{expected:04X}, "
            f"got 0x{actual:04X}",
            error_code="EFP-NET1",
            context={"layer": layer, "expected": expected, "actual": actual},
        )


class FizzNetConnectionRefusedError(FizzNetError):
    """Raised when a TCP connection attempt is refused by the remote host.

    The destination endpoint has no listening socket on the requested
    port, or the backlog queue is full. In a real network, this would
    result in an RST segment. In FizzNet, it means the FizzBuzz server
    is not running, which is a deployment failure of the highest order.
    """

    def __init__(self, ip: str, port: int) -> None:
        super().__init__(
            f"Connection refused by {ip}:{port}. No FizzBuzz service is "
            f"accepting connections on this endpoint.",
            error_code="EFP-NET2",
            context={"ip": ip, "port": port},
        )


class FizzNetConnectionResetError(FizzNetError):
    """Raised when a TCP connection is reset by the remote host.

    An RST segment was received, indicating that the remote endpoint
    has abruptly terminated the connection. This may occur if the
    FizzBuzz server encounters an unrecoverable error mid-classification.
    """

    def __init__(self, ip: str, port: int) -> None:
        super().__init__(
            f"Connection to {ip}:{port} was reset by the remote host.",
            error_code="EFP-NET3",
            context={"ip": ip, "port": port},
        )


class FizzNetTimeoutError(FizzNetError):
    """Raised when a TCP operation exceeds the configured timeout.

    In a real network, timeouts account for propagation delay, queuing
    delay, and processing delay. In FizzNet, the only delay is the
    time it takes Python to execute a few method calls, so a timeout
    here would be genuinely alarming.
    """

    def __init__(self, operation: str, timeout_ms: float) -> None:
        super().__init__(
            f"FizzNet operation '{operation}' timed out after {timeout_ms:.1f}ms.",
            error_code="EFP-NET4",
            context={"operation": operation, "timeout_ms": timeout_ms},
        )


class FizzNetARPResolutionError(FizzNetError):
    """Raised when ARP cannot resolve an IP address to a MAC address.

    The ARP table does not contain a mapping for the requested IP,
    and no interface with that IP is registered in the network stack.
    The packet is undeliverable at Layer 2.
    """

    def __init__(self, ip: str) -> None:
        super().__init__(
            f"ARP resolution failed for {ip}. No MAC address mapping exists.",
            error_code="EFP-NET5",
            context={"ip": ip},
        )


class FizzNetTTLExpiredError(FizzNetError):
    """Raised when an IPv4 packet's TTL reaches zero.

    The packet has been forwarded through too many hops and must be
    discarded. Given that FizzNet has zero hops (all interfaces are
    in the same process), a TTL expiration suggests the initial TTL
    was set to zero, which is a configuration error.
    """

    def __init__(self, src_ip: str, dst_ip: str, original_ttl: int) -> None:
        super().__init__(
            f"TTL expired for packet from {src_ip} to {dst_ip} "
            f"(original TTL: {original_ttl}).",
            error_code="EFP-NET6",
            context={"src_ip": src_ip, "dst_ip": dst_ip, "original_ttl": original_ttl},
        )


class FizzNetProtocolError(FizzNetError):
    """Raised when a protocol-level error occurs in the FizzNet stack.

    This covers malformed segments, invalid state transitions, and
    any other protocol violation that prevents normal operation of
    the TCP/IP stack or the FizzBuzz Protocol layer.
    """

    def __init__(self, message: str, protocol: str) -> None:
        super().__init__(
            f"FizzNet {protocol} protocol error: {message}",
            error_code="EFP-NET7",
            context={"protocol": protocol},
        )

