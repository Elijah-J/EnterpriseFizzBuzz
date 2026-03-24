"""
Enterprise FizzBuzz Platform - ── FizzCNI: Container Network Interface Plugin System ───────
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class CNIError(FizzBuzzError):
    """Base exception for all Container Network Interface errors.

    The CNI subsystem provides container networking through a plugin
    architecture following the CNI specification.  Bridge, host, none,
    and overlay plugins create the network plumbing that connects
    isolated containers to each other and to external networks.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"CNI error: {reason}",
            error_code="EFP-CNI00",
            context={"reason": reason},
        )


class CNIPluginNotFoundError(CNIError):
    """Raised when a requested CNI plugin type is not registered.

    The CNI manager maintains a registry of available plugins.  If
    a container requests a plugin type that has not been registered,
    this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI01"
        self.context = {"reason": reason}


class CNIAddError(CNIError):
    """Raised when a CNI ADD operation fails.

    The ADD operation attaches a container to a network by creating
    interfaces, assigning IP addresses, and configuring routes.
    Failures at any stage of this process trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI02"
        self.context = {"reason": reason}


class CNIDeleteError(CNIError):
    """Raised when a CNI DEL operation fails.

    The DEL operation detaches a container from a network by removing
    interfaces, releasing IP addresses, and cleaning up routes.
    Failures during teardown trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI03"
        self.context = {"reason": reason}


class CNICheckError(CNIError):
    """Raised when a CNI CHECK operation fails.

    The CHECK operation verifies that a container's network
    configuration is consistent with the expected state.  Drift
    detection or interface validation failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI04"
        self.context = {"reason": reason}


class VethCreationError(CNIError):
    """Raised when virtual ethernet pair creation fails.

    Veth pairs are the fundamental connectivity mechanism for bridge
    networking.  One end resides in the container's network namespace,
    the other on the host bridge.  Creation failures indicate resource
    exhaustion or namespace configuration errors.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI05"
        self.context = {"reason": reason}


class BridgeError(CNIError):
    """Raised when bridge interface operations fail.

    The bridge plugin manages a software bridge (fizzbr0) that
    connects container veth endpoints.  Bridge creation, port
    attachment, STP configuration, or MAC learning failures
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI06"
        self.context = {"reason": reason}


class IPAMError(CNIError):
    """Raised when IPAM (IP Address Management) operations fail.

    The IPAM plugin manages subnet allocation, IP assignment, and
    DHCP lease lifecycle.  General IPAM failures that do not fall
    into a more specific category trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI07"
        self.context = {"reason": reason}


class IPAMExhaustedError(CNIError):
    """Raised when the IPAM address pool is fully allocated.

    Every subnet has a finite number of assignable addresses.  When
    all addresses in the configured subnet are allocated to active
    leases, new allocation requests cannot be fulfilled.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI08"
        self.context = {"reason": reason}


class IPAMLeaseExpiredError(CNIError):
    """Raised when an operation references an expired DHCP lease.

    DHCP leases have a configurable duration.  Operations that
    reference a lease past its expiration time encounter this
    exception.  The address may have been reclaimed and reassigned.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI09"
        self.context = {"reason": reason}


class IPAMConflictError(CNIError):
    """Raised when an IP address allocation conflict is detected.

    Conflict detection identifies duplicate address assignments
    within a subnet.  This indicates a consistency violation in the
    allocation table that must be resolved before networking can
    proceed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI10"
        self.context = {"reason": reason}


class PortMappingError(CNIError):
    """Raised when port mapping (DNAT) operations fail.

    The port mapper creates destination NAT rules that forward
    host port traffic to container IP:port endpoints.  Rule
    creation, deletion, or validation failures trigger this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI11"
        self.context = {"reason": reason}


class PortConflictError(CNIError):
    """Raised when a requested host port is already in use.

    Each host port can be mapped to at most one container endpoint
    per protocol.  Attempting to map a port that is already bound
    triggers this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI12"
        self.context = {"reason": reason}


class ContainerDNSError(CNIError):
    """Raised when container DNS operations fail.

    The container DNS server manages A, SRV, PTR, AAAA, and CNAME
    records for container name resolution within the cluster
    network.  Record creation, deletion, or lookup failures
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI13"
        self.context = {"reason": reason}


class NetworkPolicyError(CNIError):
    """Raised when network policy operations fail.

    Network policies control ingress and egress traffic for
    containers based on label selectors, namespaces, and port
    specifications.  Policy creation, evaluation, or enforcement
    failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI14"
        self.context = {"reason": reason}


class OverlayNetworkError(CNIError):
    """Raised when overlay network operations fail.

    The overlay plugin implements VXLAN encapsulation for
    multi-host container networking.  VTEP configuration,
    FDB management, or encapsulation failures trigger this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI15"
        self.context = {"reason": reason}


class CNIDashboardError(CNIError):
    """Raised when the CNI dashboard rendering fails.

    The dashboard renders network topology, IPAM statistics,
    port mappings, DNS records, and policy summaries in ASCII
    format.  Data retrieval or rendering failures trigger this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CNI16"
        self.context = {"reason": reason}


class CNIMiddlewareError(CNIError):
    """Raised when the CNI middleware fails to process an evaluation.

    The middleware intercepts each FizzBuzz evaluation to ensure
    container network configuration is applied before evaluation
    begins in a containerized context.  If network setup or
    teardown fails during middleware processing, this exception
    is raised.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"CNI middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-CNI17"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number

