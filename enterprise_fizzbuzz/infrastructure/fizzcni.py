"""
Enterprise FizzBuzz Platform - FizzCNI: Container Network Interface Plugin System

A CNI-specification-compliant plugin system providing container network
connectivity through four network drivers: bridge, host, none, and overlay.
Each driver handles interface creation, IP address assignment, routing,
and cleanup following the Container Network Interface specification v1.0.0.

The bridge plugin creates a virtual bridge (fizzbr0) connecting containers
via veth pairs.  The overlay plugin implements VXLAN encapsulation for
multi-host container networking.  The IPAM plugin manages subnet allocation
with DHCP-style leases.  The port mapper provides DNAT rules for container
port exposure.  Container DNS resolves names within the cluster network.
Network policies implement microsegmentation based on label selectors.

CNI Specification: https://github.com/containernetworking/cni/blob/spec-v1.0.0/SPEC.md
"""

from __future__ import annotations

import copy
import hashlib
import ipaddress
import logging
import math
import random
import struct
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions import (
    BridgeError,
    CNIAddError,
    CNICheckError,
    CNIDashboardError,
    CNIDeleteError,
    CNIError,
    CNIMiddlewareError,
    CNIPluginNotFoundError,
    ContainerDNSError,
    IPAMConflictError,
    IPAMError,
    IPAMExhaustedError,
    IPAMLeaseExpiredError,
    NetworkPolicyError,
    OverlayNetworkError,
    PortConflictError,
    PortMappingError,
    VethCreationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzcni")


# ============================================================
# Constants
# ============================================================

CNI_SPEC_VERSION = "1.0.0"
"""CNI specification version implemented by this plugin system."""

DEFAULT_BRIDGE_NAME = "fizzbr0"
"""Default bridge interface name for the bridge plugin."""

DEFAULT_SUBNET = "10.244.0.0/16"
"""Default pod network CIDR range."""

DEFAULT_GATEWAY = "10.244.0.1"
"""Default gateway IP address for the pod network."""

DEFAULT_LEASE_DURATION = 3600.0
"""Default DHCP lease duration in seconds (1 hour)."""

DEFAULT_MTU = 1500
"""Default Maximum Transmission Unit in bytes."""

DEFAULT_VXLAN_PORT = 4789
"""Standard IANA-assigned VXLAN UDP port."""

DEFAULT_VNI = 1
"""Default VXLAN Network Identifier."""

DEFAULT_DNS_DOMAIN = "cluster.fizz"
"""Default DNS domain for container name resolution."""

DEFAULT_DNS_TTL = 30
"""Default DNS record TTL in seconds."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default ASCII dashboard width in characters."""

MIDDLEWARE_PRIORITY = 111
"""FizzCNI middleware priority in the pipeline."""

MAX_VETH_PAIRS = 4096
"""Maximum concurrent veth pairs per bridge."""

MAX_PORT_MAPPINGS = 65535
"""Maximum port mapping entries (one per ephemeral port)."""

MAX_DNS_RECORDS = 8192
"""Maximum DNS records in the container DNS cache."""

MAX_POLICIES = 1024
"""Maximum active network policies."""

BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"
"""Ethernet broadcast MAC address."""

STP_HELLO_INTERVAL = 2.0
"""STP hello timer interval in seconds."""

STP_MAX_AGE = 20.0
"""STP max age timer in seconds."""

STP_FORWARD_DELAY = 15.0
"""STP forward delay timer in seconds."""

NAT_TABLE_SIZE = 16384
"""Maximum entries in the NAT connection tracking table."""


# ============================================================
# Enums
# ============================================================


class CNIOperation(Enum):
    """CNI plugin operations as defined by the specification.

    The CNI specification defines three operations that every plugin
    must implement: ADD (configure networking), DEL (remove networking),
    and CHECK (verify configuration).  VERSION returns the plugin's
    supported CNI specification versions.
    """

    ADD = auto()
    DEL = auto()
    CHECK = auto()
    VERSION = auto()


class PluginType(Enum):
    """Available CNI plugin types.

    Each plugin type provides a different network topology:
    - BRIDGE: containers connected via a virtual bridge on the host
    - HOST: containers share the host's network namespace
    - NONE: containers have only a loopback interface
    - OVERLAY: containers connected across hosts via VXLAN tunnels
    """

    BRIDGE = "bridge"
    HOST = "host"
    NONE = "none"
    OVERLAY = "overlay"


class InterfaceState(Enum):
    """Network interface operational states.

    Interfaces transition through these states during their lifecycle:
    DOWN when created but not yet configured, UP when operational,
    and DELETED when torn down during container removal.
    """

    DOWN = auto()
    UP = auto()
    DELETED = auto()


class LeaseState(Enum):
    """DHCP lease lifecycle states.

    ACTIVE leases have a valid unexpired allocation.  EXPIRED leases
    have passed their TTL and are candidates for reclamation.
    RELEASED leases have been explicitly freed by the container
    during orderly shutdown.
    """

    ACTIVE = auto()
    EXPIRED = auto()
    RELEASED = auto()


class PolicyAction(Enum):
    """Network policy actions for matched traffic.

    ALLOW permits the packet to proceed.  DENY drops the packet
    silently, following the Kubernetes NetworkPolicy semantics
    where denied traffic receives no ICMP unreachable response.
    """

    ALLOW = auto()
    DENY = auto()


class PolicyDirection(Enum):
    """Traffic direction for network policy rules.

    INGRESS rules control incoming traffic to selected containers.
    EGRESS rules control outgoing traffic from selected containers.
    A container may have both ingress and egress policies applied
    simultaneously.
    """

    INGRESS = auto()
    EGRESS = auto()


class STPPortState(Enum):
    """Spanning Tree Protocol port states.

    The Spanning Tree Protocol (IEEE 802.1D) prevents broadcast
    storms in bridged networks by placing ports in one of five
    states.  Only FORWARDING ports actively pass user traffic.
    BLOCKING ports drop all non-STP traffic.  LISTENING and
    LEARNING are transitional states.  DISABLED ports are
    administratively shut down.
    """

    DISABLED = auto()
    BLOCKING = auto()
    LISTENING = auto()
    LEARNING = auto()
    FORWARDING = auto()


class DNSRecordType(Enum):
    """DNS record types supported by the container DNS server.

    A records map names to IPv4 addresses.  AAAA records map names
    to IPv6 addresses.  SRV records provide service discovery with
    port and priority information.  PTR records enable reverse DNS
    lookups.  CNAME records provide name aliasing.
    """

    A = "A"
    AAAA = "AAAA"
    SRV = "SRV"
    PTR = "PTR"
    CNAME = "CNAME"


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class CNIConfig:
    """CNI plugin invocation configuration.

    Follows the CNI specification configuration format: the runtime
    passes this configuration to the plugin for each operation.
    The configuration identifies the network, plugin type, and
    plugin-specific parameters including IPAM and DNS settings.

    Attributes:
        cni_version: CNI specification version string.
        name: Network name (unique identifier for this network).
        plugin_type: Plugin type to invoke (bridge, host, none, overlay).
        args: Plugin-specific arguments.
        ipam: IPAM configuration (subnet, gateway, ranges).
        dns: DNS configuration (nameservers, domain, search).
        mtu: Maximum Transmission Unit for created interfaces.
        bridge_name: Bridge interface name (bridge plugin only).
        vxlan_id: VXLAN Network Identifier (overlay plugin only).
        vxlan_port: VXLAN UDP port (overlay plugin only).
    """

    cni_version: str = CNI_SPEC_VERSION
    name: str = "fizzbuzz-net"
    plugin_type: str = "bridge"
    args: Dict[str, Any] = field(default_factory=dict)
    ipam: Dict[str, Any] = field(default_factory=dict)
    dns: Dict[str, Any] = field(default_factory=dict)
    mtu: int = DEFAULT_MTU
    bridge_name: str = DEFAULT_BRIDGE_NAME
    vxlan_id: int = DEFAULT_VNI
    vxlan_port: int = DEFAULT_VXLAN_PORT


@dataclass
class CNIResult:
    """Result of a CNI ADD operation.

    Contains the network configuration applied to the container:
    created interfaces with MAC addresses, IP configurations with
    gateways and masks, routing entries, and DNS settings.

    Attributes:
        cni_version: CNI specification version string.
        interfaces: List of created interfaces.
        ips: List of IP configurations.
        routes: List of route entries.
        dns: DNS configuration.
    """

    cni_version: str = CNI_SPEC_VERSION
    interfaces: List[Dict[str, Any]] = field(default_factory=list)
    ips: List[Dict[str, Any]] = field(default_factory=list)
    routes: List[Dict[str, Any]] = field(default_factory=list)
    dns: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VethPair:
    """Virtual Ethernet pair connecting a container to a bridge.

    A veth pair consists of two connected virtual ethernet interfaces.
    Traffic sent to one end emerges from the other.  One end resides
    in the container's network namespace (the container interface),
    the other on the host attached to the bridge (the host interface).

    Attributes:
        pair_id: Unique identifier for this veth pair.
        host_ifname: Interface name on the host side.
        container_ifname: Interface name in the container.
        host_mac: MAC address of the host-side interface.
        container_mac: MAC address of the container-side interface.
        container_id: ID of the container this pair belongs to.
        bridge_name: Bridge the host end is attached to.
        state: Current operational state.
        created_at: Creation timestamp (UTC).
        mtu: Maximum Transmission Unit.
    """

    pair_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    host_ifname: str = ""
    container_ifname: str = "eth0"
    host_mac: str = ""
    container_mac: str = ""
    container_id: str = ""
    bridge_name: str = DEFAULT_BRIDGE_NAME
    state: InterfaceState = InterfaceState.DOWN
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    mtu: int = DEFAULT_MTU


@dataclass
class BridgeInterface:
    """Virtual bridge device connecting container veth endpoints.

    The bridge operates as a Layer 2 switch, maintaining a MAC
    address table for intelligent frame forwarding.  STP (Spanning
    Tree Protocol) prevents broadcast storms when multiple bridges
    are interconnected.  NAT enables container-to-external traffic.

    Attributes:
        name: Bridge interface name (e.g., fizzbr0).
        ip_address: Bridge IP address (serves as container gateway).
        subnet: Bridge subnet in CIDR notation.
        mac: Bridge interface MAC address.
        mtu: Maximum Transmission Unit.
        ports: Attached veth host endpoints.
        mac_table: MAC address learning table.
        stp_enabled: Whether STP is active.
        stp_root: Whether this bridge is the STP root.
        stp_priority: STP bridge priority (lower wins).
        nat_enabled: Whether NAT is enabled for outbound traffic.
        nat_table: NAT connection tracking entries.
        created_at: Creation timestamp (UTC).
    """

    name: str = DEFAULT_BRIDGE_NAME
    ip_address: str = DEFAULT_GATEWAY
    subnet: str = DEFAULT_SUBNET
    mac: str = ""
    mtu: int = DEFAULT_MTU
    ports: Dict[str, STPPortState] = field(default_factory=dict)
    mac_table: Dict[str, str] = field(default_factory=dict)
    stp_enabled: bool = True
    stp_root: bool = True
    stp_priority: int = 32768
    nat_enabled: bool = True
    nat_table: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class IPAllocation:
    """IP address allocation record.

    Tracks the assignment of an IP address from a subnet to a
    container.  Allocations are created during CNI ADD and released
    during CNI DEL.  The allocation includes the gateway and mask
    information needed to configure the container's network stack.

    Attributes:
        allocation_id: Unique allocation identifier.
        ip_address: Allocated IP address string.
        subnet: Subnet from which the address was allocated.
        gateway: Gateway IP for the subnet.
        prefix_length: CIDR prefix length.
        container_id: Container holding this allocation.
        interface_name: Interface this address is bound to.
        allocated_at: Allocation timestamp (UTC).
    """

    allocation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ip_address: str = ""
    subnet: str = ""
    gateway: str = ""
    prefix_length: int = 24
    container_id: str = ""
    interface_name: str = "eth0"
    allocated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Lease:
    """DHCP-style IP address lease.

    Leases provide time-bounded address allocations with renewal
    semantics.  Active leases can be renewed to extend their TTL.
    Expired leases have their addresses reclaimed and returned to
    the free pool.  Released leases are freed immediately during
    orderly container shutdown.

    Attributes:
        lease_id: Unique lease identifier.
        allocation: The IP allocation this lease covers.
        state: Current lease state.
        duration: Lease duration in seconds.
        granted_at: When the lease was granted (UTC).
        expires_at: When the lease expires (UTC).
        renewed_at: When the lease was last renewed (UTC).
        renewal_count: Number of times this lease has been renewed.
    """

    lease_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    allocation: Optional[IPAllocation] = None
    state: LeaseState = LeaseState.ACTIVE
    duration: float = DEFAULT_LEASE_DURATION
    granted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    renewed_at: Optional[datetime] = None
    renewal_count: int = 0

    def is_expired(self) -> bool:
        """Check whether this lease has passed its expiration time."""
        return datetime.now(timezone.utc) >= self.expires_at

    def remaining_seconds(self) -> float:
        """Return seconds remaining until lease expiration."""
        delta = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)


@dataclass
class PortMapping:
    """DNAT port mapping from host port to container endpoint.

    Maps incoming traffic on a host port to a container's IP and
    port.  The port mapper maintains DNAT rules that rewrite
    destination addresses and ports for incoming packets, enabling
    external access to container services.

    Attributes:
        mapping_id: Unique mapping identifier.
        host_port: Port on the host network.
        container_ip: Container IP address.
        container_port: Port in the container.
        protocol: Transport protocol (tcp or udp).
        container_id: Container this mapping belongs to.
        created_at: Creation timestamp (UTC).
    """

    mapping_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    host_port: int = 0
    container_ip: str = ""
    container_port: int = 0
    protocol: str = "tcp"
    container_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DNSRecord:
    """Container DNS record entry.

    Stores a DNS record for container name resolution within the
    cluster network.  Records are created when containers join
    the network and removed when containers leave.

    Attributes:
        record_id: Unique record identifier.
        name: DNS name (e.g., web-container-1.cluster.fizz).
        record_type: DNS record type (A, AAAA, SRV, PTR, CNAME).
        value: Record value (IP address, target name, etc.).
        ttl: Time to live in seconds.
        container_id: Container this record belongs to.
        created_at: Creation timestamp (UTC).
        priority: SRV record priority (0 for non-SRV records).
        port: SRV record port (0 for non-SRV records).
        weight: SRV record weight (0 for non-SRV records).
    """

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    record_type: DNSRecordType = DNSRecordType.A
    value: str = ""
    ttl: int = DEFAULT_DNS_TTL
    container_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: int = 0
    port: int = 0
    weight: int = 0


@dataclass
class NetworkPolicyRule:
    """A single rule within a network policy.

    Specifies traffic matching criteria: direction (ingress/egress),
    label selectors for source/destination pods, allowed ports and
    protocols, and the action to take on matched traffic.

    Attributes:
        rule_id: Unique rule identifier.
        direction: Whether this rule applies to ingress or egress.
        action: Action to take on matched traffic.
        selector_labels: Label key-value pairs for pod selection.
        ports: Allowed ports (empty means all ports).
        protocols: Allowed protocols (empty means all protocols).
        cidr_blocks: Allowed CIDR blocks (empty means all).
    """

    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    direction: PolicyDirection = PolicyDirection.INGRESS
    action: PolicyAction = PolicyAction.ALLOW
    selector_labels: Dict[str, str] = field(default_factory=dict)
    ports: List[int] = field(default_factory=list)
    protocols: List[str] = field(default_factory=list)
    cidr_blocks: List[str] = field(default_factory=list)


@dataclass
class NetworkPolicySpec:
    """Network policy specification for container microsegmentation.

    A network policy selects containers by label and defines
    ingress and egress rules controlling traffic flow.  When
    a policy is applied, containers matching the pod selector
    operate in default-deny mode: only traffic explicitly
    permitted by a rule is allowed.

    Attributes:
        policy_id: Unique policy identifier.
        name: Human-readable policy name.
        namespace: Namespace this policy applies to.
        pod_selector: Labels selecting pods this policy governs.
        ingress_rules: Rules controlling incoming traffic.
        egress_rules: Rules controlling outgoing traffic.
        created_at: Creation timestamp (UTC).
    """

    policy_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    namespace: str = "default"
    pod_selector: Dict[str, str] = field(default_factory=dict)
    ingress_rules: List[NetworkPolicyRule] = field(default_factory=list)
    egress_rules: List[NetworkPolicyRule] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CNIStats:
    """Aggregate statistics for the CNI subsystem.

    Tracks operation counts, resource utilization, and error
    rates across all CNI plugins, IPAM, port mapping, DNS,
    and network policy subsystems.

    Attributes:
        total_add_ops: Total CNI ADD operations performed.
        total_del_ops: Total CNI DEL operations performed.
        total_check_ops: Total CNI CHECK operations performed.
        active_containers: Currently connected containers.
        active_veth_pairs: Currently active veth pairs.
        allocated_ips: Currently allocated IP addresses.
        active_leases: Currently active DHCP leases.
        expired_leases: Total expired leases.
        active_port_mappings: Currently active port mappings.
        dns_records: Total DNS records.
        dns_queries: Total DNS queries served.
        active_policies: Currently active network policies.
        policy_evaluations: Total policy evaluations.
        packets_allowed: Packets allowed by policy.
        packets_denied: Packets denied by policy.
        errors: Total error count across all operations.
    """

    total_add_ops: int = 0
    total_del_ops: int = 0
    total_check_ops: int = 0
    active_containers: int = 0
    active_veth_pairs: int = 0
    allocated_ips: int = 0
    active_leases: int = 0
    expired_leases: int = 0
    active_port_mappings: int = 0
    dns_records: int = 0
    dns_queries: int = 0
    active_policies: int = 0
    policy_evaluations: int = 0
    packets_allowed: int = 0
    packets_denied: int = 0
    errors: int = 0


# ============================================================
# MAC Address Generation
# ============================================================


def _generate_mac() -> str:
    """Generate a locally administered unicast MAC address.

    Sets the locally administered bit (bit 1 of the first octet)
    and clears the multicast bit (bit 0), following IEEE 802
    conventions for software-generated MAC addresses.

    Returns:
        MAC address string in colon-separated hex notation.
    """
    octets = [random.randint(0, 255) for _ in range(6)]
    octets[0] = (octets[0] | 0x02) & 0xFE  # locally administered, unicast
    return ":".join(f"{b:02x}" for b in octets)


# ============================================================
# CNI Plugin Abstract Base Class
# ============================================================


class CNIPlugin(ABC):
    """Abstract base class for CNI plugins.

    Every CNI plugin must implement the three standard operations
    defined by the CNI specification: ADD (configure networking),
    DEL (remove networking), and CHECK (verify configuration).
    The VERSION method returns supported specification versions.

    This interface follows the CNI specification v1.0.0 semantics:
    ADD is idempotent (calling ADD twice with the same parameters
    must succeed), DEL is best-effort (partial cleanup is acceptable),
    and CHECK validates the current state against expected configuration.
    """

    @abstractmethod
    def add(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> CNIResult:
        """Configure networking for a container (CNI ADD).

        Creates network interfaces, assigns IP addresses, configures
        routes, and returns the resulting network configuration.

        Args:
            container_id: Unique container identifier.
            netns: Path to the container's network namespace.
            ifname: Interface name to create in the container.
            config: CNI plugin configuration.

        Returns:
            CNIResult describing the applied configuration.
        """

    @abstractmethod
    def delete(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> None:
        """Remove networking for a container (CNI DEL).

        Deletes network interfaces, releases IP addresses, and
        cleans up routes.  Best-effort: partial cleanup is acceptable.

        Args:
            container_id: Unique container identifier.
            netns: Path to the container's network namespace.
            ifname: Interface name to remove from the container.
            config: CNI plugin configuration.
        """

    @abstractmethod
    def check(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> bool:
        """Verify networking for a container (CNI CHECK).

        Validates that the container's network configuration matches
        the expected state.  Returns True if consistent, raises
        CNICheckError if drift is detected.

        Args:
            container_id: Unique container identifier.
            netns: Path to the container's network namespace.
            ifname: Interface name to check in the container.
            config: CNI plugin configuration.

        Returns:
            True if the configuration is consistent.
        """

    def version(self) -> List[str]:
        """Return supported CNI specification versions.

        Returns:
            List of supported version strings.
        """
        return [CNI_SPEC_VERSION]

    @abstractmethod
    def plugin_type(self) -> PluginType:
        """Return the plugin type identifier.

        Returns:
            PluginType enum value.
        """


# ============================================================
# Bridge Plugin
# ============================================================


class BridgePlugin(CNIPlugin):
    """Bridge CNI plugin for host-local container networking.

    The bridge plugin is the most common CNI plugin for single-host
    deployments.  It creates a virtual bridge (fizzbr0 by default)
    on the host and connects each container to it via a veth pair.
    One end of the veth pair resides in the container's network
    namespace, the other on the host attached to the bridge.

    The bridge maintains a MAC address learning table for intelligent
    L2 frame forwarding, implements STP (Spanning Tree Protocol) for
    loop prevention, and provides NAT (Network Address Translation)
    for container-to-external connectivity.

    Attributes:
        bridge: The BridgeInterface managed by this plugin.
        veth_pairs: Registry of active veth pairs by container ID.
        ipam: IPAM plugin for address management.
        event_bus: Optional event bus for lifecycle events.
    """

    def __init__(
        self,
        bridge_name: str = DEFAULT_BRIDGE_NAME,
        gateway: str = DEFAULT_GATEWAY,
        subnet: str = DEFAULT_SUBNET,
        mtu: int = DEFAULT_MTU,
        stp_enabled: bool = True,
        nat_enabled: bool = True,
        ipam: Optional["IPAMPlugin"] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._lock = threading.Lock()
        self.bridge = BridgeInterface(
            name=bridge_name,
            ip_address=gateway,
            subnet=subnet,
            mac=_generate_mac(),
            mtu=mtu,
            stp_enabled=stp_enabled,
            nat_enabled=nat_enabled,
        )
        self.veth_pairs: Dict[str, VethPair] = {}
        self.ipam = ipam
        self._event_bus = event_bus
        self._stats = CNIStats()
        logger.info(
            "Bridge plugin initialized: bridge=%s gateway=%s subnet=%s",
            bridge_name, gateway, subnet,
        )

    def plugin_type(self) -> PluginType:
        """Return the bridge plugin type."""
        return PluginType.BRIDGE

    def _emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data or {})
            except Exception:
                pass

    def _create_veth_pair(
        self, container_id: str, ifname: str, mtu: int
    ) -> VethPair:
        """Create a virtual ethernet pair for a container.

        Generates a host-side interface name derived from the
        container ID, assigns locally administered MAC addresses
        to both ends, and registers the pair.

        Args:
            container_id: Container identifier.
            ifname: Container-side interface name.
            mtu: Maximum Transmission Unit.

        Returns:
            The created VethPair.

        Raises:
            VethCreationError: If the maximum veth pair count is exceeded.
        """
        if len(self.veth_pairs) >= MAX_VETH_PAIRS:
            raise VethCreationError(
                f"Maximum veth pair count ({MAX_VETH_PAIRS}) exceeded"
            )

        short_id = container_id[:8] if len(container_id) > 8 else container_id
        host_ifname = f"veth{short_id}"

        pair = VethPair(
            host_ifname=host_ifname,
            container_ifname=ifname,
            host_mac=_generate_mac(),
            container_mac=_generate_mac(),
            container_id=container_id,
            bridge_name=self.bridge.name,
            state=InterfaceState.UP,
            mtu=mtu,
        )

        self.veth_pairs[container_id] = pair
        self._emit(EventType.CNI_VETH_CREATED, {
            "container_id": container_id,
            "host_ifname": host_ifname,
            "container_ifname": ifname,
        })

        logger.debug(
            "Created veth pair: host=%s container=%s for %s",
            host_ifname, ifname, container_id,
        )
        return pair

    def _delete_veth_pair(self, container_id: str) -> None:
        """Delete a virtual ethernet pair for a container.

        Removes the veth pair from the registry and marks it as
        deleted.  Removes the host-side endpoint from the bridge.

        Args:
            container_id: Container identifier.
        """
        pair = self.veth_pairs.pop(container_id, None)
        if pair is not None:
            pair.state = InterfaceState.DELETED
            self.bridge.ports.pop(pair.host_ifname, None)
            self.bridge.mac_table.pop(pair.container_mac, None)
            self._emit(EventType.CNI_VETH_DELETED, {
                "container_id": container_id,
                "host_ifname": pair.host_ifname,
            })
            logger.debug("Deleted veth pair for container %s", container_id)

    def _attach_to_bridge(self, pair: VethPair) -> None:
        """Attach a veth host endpoint to the bridge.

        Adds the host-side interface to the bridge's port list and
        learns the container's MAC address for frame forwarding.

        Args:
            pair: The VethPair to attach.

        Raises:
            BridgeError: If the bridge cannot accept more ports.
        """
        if len(self.bridge.ports) >= MAX_VETH_PAIRS:
            raise BridgeError(
                f"Bridge {self.bridge.name} at maximum port capacity"
            )

        # Set STP port state
        if self.bridge.stp_enabled:
            self.bridge.ports[pair.host_ifname] = STPPortState.FORWARDING
        else:
            self.bridge.ports[pair.host_ifname] = STPPortState.FORWARDING

        # Learn MAC address
        self.bridge.mac_table[pair.container_mac] = pair.host_ifname

        logger.debug(
            "Attached %s to bridge %s (MAC %s)",
            pair.host_ifname, self.bridge.name, pair.container_mac,
        )

    def _add_nat_entry(
        self, container_id: str, container_ip: str, container_mac: str
    ) -> None:
        """Add a NAT masquerade entry for outbound container traffic.

        Enables containers to reach external networks by masquerading
        their source IP with the bridge's IP address.

        Args:
            container_id: Container identifier.
            container_ip: Container's assigned IP address.
            container_mac: Container's MAC address.
        """
        if not self.bridge.nat_enabled:
            return

        if len(self.bridge.nat_table) >= NAT_TABLE_SIZE:
            # Evict oldest entry
            oldest_key = next(iter(self.bridge.nat_table))
            del self.bridge.nat_table[oldest_key]

        self.bridge.nat_table[container_id] = {
            "container_ip": container_ip,
            "container_mac": container_mac,
            "bridge_ip": self.bridge.ip_address,
            "masquerade": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _remove_nat_entry(self, container_id: str) -> None:
        """Remove a NAT entry for a container."""
        self.bridge.nat_table.pop(container_id, None)

    def _stp_evaluate_port(self, ifname: str) -> STPPortState:
        """Evaluate STP state for a bridge port.

        In a single-bridge topology, all ports transition to
        FORWARDING.  In multi-bridge topologies, the STP algorithm
        would compute root bridge, root ports, and designated ports.
        This implementation handles the common single-bridge case
        and supports future multi-bridge extension.

        Args:
            ifname: Interface name of the port.

        Returns:
            The computed STP port state.
        """
        if not self.bridge.stp_enabled:
            return STPPortState.FORWARDING

        # Single-bridge topology: this bridge is root, all ports forward
        if self.bridge.stp_root:
            return STPPortState.FORWARDING

        # Non-root bridge: all ports start in LISTENING, transition
        # through LEARNING to FORWARDING after forward delay
        current = self.bridge.ports.get(ifname, STPPortState.DISABLED)
        if current == STPPortState.DISABLED:
            return STPPortState.LISTENING
        return current

    def mac_lookup(self, mac: str) -> Optional[str]:
        """Look up the bridge port for a MAC address.

        The MAC learning table maps container MAC addresses to the
        host-side veth interface they are reachable through.

        Args:
            mac: MAC address to look up.

        Returns:
            Interface name if found, None otherwise.
        """
        return self.bridge.mac_table.get(mac)

    def add(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> CNIResult:
        """Configure bridge networking for a container.

        Creates a veth pair, attaches the host end to the bridge,
        allocates an IP address via IPAM, configures NAT, and
        returns the resulting network configuration.

        Args:
            container_id: Container identifier.
            netns: Container's network namespace path.
            ifname: Interface name in the container.
            config: CNI configuration.

        Returns:
            CNIResult with interface, IP, route, and DNS details.

        Raises:
            CNIAddError: If any step of the configuration fails.
        """
        with self._lock:
            try:
                mtu = config.mtu if config.mtu else self.bridge.mtu

                # Create veth pair
                pair = self._create_veth_pair(container_id, ifname, mtu)

                # Attach host end to bridge
                self._attach_to_bridge(pair)

                # Allocate IP via IPAM
                allocation = None
                if self.ipam is not None:
                    allocation = self.ipam.allocate(
                        container_id=container_id,
                        ifname=ifname,
                    )

                # Set up NAT
                if allocation is not None:
                    self._add_nat_entry(
                        container_id, allocation.ip_address, pair.container_mac
                    )

                # Build result
                result = CNIResult(
                    interfaces=[
                        {
                            "name": pair.host_ifname,
                            "mac": pair.host_mac,
                            "sandbox": "",
                        },
                        {
                            "name": pair.container_ifname,
                            "mac": pair.container_mac,
                            "sandbox": netns,
                        },
                    ],
                )

                if allocation is not None:
                    result.ips = [
                        {
                            "address": f"{allocation.ip_address}/{allocation.prefix_length}",
                            "gateway": allocation.gateway,
                            "interface": 1,
                        }
                    ]
                    result.routes = [
                        {
                            "dst": "0.0.0.0/0",
                            "gw": allocation.gateway,
                        }
                    ]

                result.dns = {
                    "nameservers": [self.bridge.ip_address],
                    "domain": DEFAULT_DNS_DOMAIN,
                    "search": [DEFAULT_DNS_DOMAIN],
                }

                self._stats.total_add_ops += 1
                self._stats.active_containers += 1
                self._stats.active_veth_pairs = len(self.veth_pairs)

                self._emit(EventType.CNI_CONTAINER_ADDED, {
                    "container_id": container_id,
                    "plugin": "bridge",
                    "netns": netns,
                })

                logger.info(
                    "Bridge ADD: container=%s ifname=%s ip=%s",
                    container_id, ifname,
                    allocation.ip_address if allocation else "none",
                )

                return result

            except (VethCreationError, BridgeError, IPAMError) as exc:
                self._stats.errors += 1
                # Best-effort cleanup
                self._delete_veth_pair(container_id)
                raise CNIAddError(
                    f"Bridge ADD failed for {container_id}: {exc}"
                ) from exc

    def delete(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> None:
        """Remove bridge networking for a container.

        Deletes the veth pair, releases the IP address via IPAM,
        and removes the NAT entry.

        Args:
            container_id: Container identifier.
            netns: Container's network namespace path.
            ifname: Interface name to remove.
            config: CNI configuration.
        """
        with self._lock:
            try:
                # Release IP
                if self.ipam is not None:
                    self.ipam.release(container_id)

                # Remove NAT
                self._remove_nat_entry(container_id)

                # Delete veth pair
                self._delete_veth_pair(container_id)

                self._stats.total_del_ops += 1
                self._stats.active_containers = max(
                    0, self._stats.active_containers - 1
                )
                self._stats.active_veth_pairs = len(self.veth_pairs)

                self._emit(EventType.CNI_CONTAINER_DELETED, {
                    "container_id": container_id,
                    "plugin": "bridge",
                })

                logger.info("Bridge DEL: container=%s", container_id)

            except Exception as exc:
                self._stats.errors += 1
                raise CNIDeleteError(
                    f"Bridge DEL failed for {container_id}: {exc}"
                ) from exc

    def check(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> bool:
        """Verify bridge networking for a container.

        Validates that the container has an active veth pair, the
        pair is attached to the bridge, and the IP allocation is
        consistent.

        Args:
            container_id: Container identifier.
            netns: Container's network namespace path.
            ifname: Interface name to check.
            config: CNI configuration.

        Returns:
            True if configuration is consistent.

        Raises:
            CNICheckError: If drift is detected.
        """
        with self._lock:
            self._stats.total_check_ops += 1

            pair = self.veth_pairs.get(container_id)
            if pair is None:
                raise CNICheckError(
                    f"No veth pair found for container {container_id}"
                )

            if pair.state != InterfaceState.UP:
                raise CNICheckError(
                    f"Veth pair for {container_id} is in state {pair.state.name}"
                )

            if pair.host_ifname not in self.bridge.ports:
                raise CNICheckError(
                    f"Veth {pair.host_ifname} not attached to bridge {self.bridge.name}"
                )

            stp_state = self.bridge.ports.get(pair.host_ifname)
            if stp_state != STPPortState.FORWARDING:
                raise CNICheckError(
                    f"Port {pair.host_ifname} in STP state {stp_state.name}, "
                    f"expected FORWARDING"
                )

            if self.ipam is not None:
                if not self.ipam.has_allocation(container_id):
                    raise CNICheckError(
                        f"No IP allocation for container {container_id}"
                    )

            self._emit(EventType.CNI_CONTAINER_CHECKED, {
                "container_id": container_id,
                "plugin": "bridge",
            })

            return True

    @property
    def stats(self) -> CNIStats:
        """Return bridge plugin statistics."""
        return self._stats


# ============================================================
# Host Plugin
# ============================================================


class HostPlugin(CNIPlugin):
    """Host CNI plugin sharing the host's network namespace.

    The host plugin does not create a new network namespace or any
    interfaces.  The container shares the host's full network stack,
    including all interfaces, IP addresses, routes, and port bindings.
    This is used for containers that need direct access to the host
    network, such as network infrastructure services.

    No isolation is provided: the container can see and modify all
    host network resources.  Port conflicts with other containers
    or host services are the caller's responsibility to avoid.
    """

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self._event_bus = event_bus
        self._stats = CNIStats()
        self._containers: Set[str] = set()

    def plugin_type(self) -> PluginType:
        """Return the host plugin type."""
        return PluginType.HOST

    def _emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data or {})
            except Exception:
                pass

    def add(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> CNIResult:
        """Configure host networking for a container.

        No interfaces are created.  The container uses the host
        network directly.  Returns a minimal CNIResult indicating
        host network sharing.

        Args:
            container_id: Container identifier.
            netns: Ignored (host namespace is used).
            ifname: Ignored (no interface created).
            config: CNI configuration.

        Returns:
            Minimal CNIResult.
        """
        self._containers.add(container_id)
        self._stats.total_add_ops += 1
        self._stats.active_containers += 1

        self._emit(EventType.CNI_CONTAINER_ADDED, {
            "container_id": container_id,
            "plugin": "host",
        })

        logger.info("Host ADD: container=%s (shared host network)", container_id)

        return CNIResult(
            interfaces=[
                {
                    "name": "host",
                    "mac": "00:00:00:00:00:00",
                    "sandbox": "",
                }
            ],
        )

    def delete(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> None:
        """Remove host networking for a container.

        No cleanup required since no interfaces were created.

        Args:
            container_id: Container identifier.
            netns: Ignored.
            ifname: Ignored.
            config: CNI configuration.
        """
        self._containers.discard(container_id)
        self._stats.total_del_ops += 1
        self._stats.active_containers = max(0, self._stats.active_containers - 1)

        self._emit(EventType.CNI_CONTAINER_DELETED, {
            "container_id": container_id,
            "plugin": "host",
        })

        logger.info("Host DEL: container=%s", container_id)

    def check(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> bool:
        """Verify host networking for a container.

        The host network is always available.  Checks only that the
        container was previously added.

        Args:
            container_id: Container identifier.
            netns: Ignored.
            ifname: Ignored.
            config: CNI configuration.

        Returns:
            True if the container is registered.

        Raises:
            CNICheckError: If the container is not registered.
        """
        self._stats.total_check_ops += 1

        if container_id not in self._containers:
            raise CNICheckError(
                f"Container {container_id} not registered with host plugin"
            )

        self._emit(EventType.CNI_CONTAINER_CHECKED, {
            "container_id": container_id,
            "plugin": "host",
        })

        return True

    @property
    def stats(self) -> CNIStats:
        """Return host plugin statistics."""
        return self._stats


# ============================================================
# None Plugin
# ============================================================


class NonePlugin(CNIPlugin):
    """None CNI plugin providing no networking.

    The none plugin creates a network namespace with only a loopback
    interface.  No external connectivity is available.  This is used
    for containers that do not require network access, such as batch
    processing or offline computation workloads.

    The container can communicate with itself via 127.0.0.1 but
    cannot reach any other container, the host, or external networks.
    """

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self._event_bus = event_bus
        self._stats = CNIStats()
        self._containers: Set[str] = set()

    def plugin_type(self) -> PluginType:
        """Return the none plugin type."""
        return PluginType.NONE

    def _emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data or {})
            except Exception:
                pass

    def add(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> CNIResult:
        """Configure none networking for a container.

        Creates a loopback-only network environment.  The container
        receives no external interfaces and no IP address.

        Args:
            container_id: Container identifier.
            netns: Container's network namespace path.
            ifname: Ignored (only loopback is created).
            config: CNI configuration.

        Returns:
            CNIResult with only a loopback interface.
        """
        self._containers.add(container_id)
        self._stats.total_add_ops += 1
        self._stats.active_containers += 1

        self._emit(EventType.CNI_CONTAINER_ADDED, {
            "container_id": container_id,
            "plugin": "none",
        })

        logger.info("None ADD: container=%s (loopback only)", container_id)

        return CNIResult(
            interfaces=[
                {
                    "name": "lo",
                    "mac": "00:00:00:00:00:00",
                    "sandbox": netns,
                }
            ],
            ips=[
                {
                    "address": "127.0.0.1/8",
                    "gateway": "",
                    "interface": 0,
                }
            ],
        )

    def delete(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> None:
        """Remove none networking for a container.

        No cleanup is required beyond deregistration.

        Args:
            container_id: Container identifier.
            netns: Ignored.
            ifname: Ignored.
            config: CNI configuration.
        """
        self._containers.discard(container_id)
        self._stats.total_del_ops += 1
        self._stats.active_containers = max(0, self._stats.active_containers - 1)

        self._emit(EventType.CNI_CONTAINER_DELETED, {
            "container_id": container_id,
            "plugin": "none",
        })

        logger.info("None DEL: container=%s", container_id)

    def check(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> bool:
        """Verify none networking for a container.

        Checks that the container was previously registered.

        Args:
            container_id: Container identifier.
            netns: Ignored.
            ifname: Ignored.
            config: CNI configuration.

        Returns:
            True if the container is registered.

        Raises:
            CNICheckError: If the container is not registered.
        """
        self._stats.total_check_ops += 1

        if container_id not in self._containers:
            raise CNICheckError(
                f"Container {container_id} not registered with none plugin"
            )

        self._emit(EventType.CNI_CONTAINER_CHECKED, {
            "container_id": container_id,
            "plugin": "none",
        })

        return True

    @property
    def stats(self) -> CNIStats:
        """Return none plugin statistics."""
        return self._stats


# ============================================================
# Overlay Plugin (VXLAN)
# ============================================================


class OverlayPlugin(CNIPlugin):
    """Overlay CNI plugin for cross-host container networking.

    The overlay plugin creates a VXLAN-based overlay network that
    connects containers across multiple hosts as if they were on
    the same Layer 2 network.  Each host has a VTEP (VXLAN Tunnel
    Endpoint) that encapsulates container traffic in UDP packets
    for transit across the physical network.

    VXLAN (Virtual Extensible LAN, RFC 7348) uses a 24-bit VNI
    (VXLAN Network Identifier) to support up to 16 million isolated
    overlay networks.  Encapsulated frames carry the full Ethernet
    header, enabling transparent L2 forwarding across L3 boundaries.

    Attributes:
        vni: VXLAN Network Identifier for this overlay.
        vtep_ip: Local VTEP IP address.
        vtep_port: VXLAN UDP port.
        fdb: Forwarding Database mapping MAC to VTEP IP.
        vtep_registry: Known VTEPs in the overlay network.
        ipam: IPAM plugin for address management.
        event_bus: Optional event bus for lifecycle events.
    """

    def __init__(
        self,
        vni: int = DEFAULT_VNI,
        vtep_ip: str = "192.168.1.1",
        vtep_port: int = DEFAULT_VXLAN_PORT,
        subnet: str = DEFAULT_SUBNET,
        gateway: str = DEFAULT_GATEWAY,
        mtu: int = DEFAULT_MTU,
        ipam: Optional["IPAMPlugin"] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._lock = threading.Lock()
        self.vni = vni
        self.vtep_ip = vtep_ip
        self.vtep_port = vtep_port
        self.subnet = subnet
        self.gateway = gateway
        self.mtu = mtu - 50  # VXLAN overhead: 50 bytes (8 VXLAN + 8 UDP + 20 IP + 14 ETH)
        self.fdb: Dict[str, str] = {}  # MAC -> VTEP IP
        self.vtep_registry: Dict[str, Dict[str, Any]] = {}  # VTEP IP -> metadata
        self.ipam = ipam
        self._event_bus = event_bus
        self._stats = CNIStats()
        self._containers: Dict[str, Dict[str, Any]] = {}

        # Register local VTEP
        self.vtep_registry[vtep_ip] = {
            "vtep_ip": vtep_ip,
            "vtep_port": vtep_port,
            "vni": vni,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Overlay plugin initialized: VNI=%d VTEP=%s:%d subnet=%s",
            vni, vtep_ip, vtep_port, subnet,
        )

    def plugin_type(self) -> PluginType:
        """Return the overlay plugin type."""
        return PluginType.OVERLAY

    def _emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data or {})
            except Exception:
                pass

    def register_vtep(self, vtep_ip: str, vtep_port: int = DEFAULT_VXLAN_PORT) -> None:
        """Register a remote VTEP for overlay traffic.

        Adds a remote host's VTEP to the registry, enabling
        this host to encapsulate traffic destined for containers
        on the remote host.

        Args:
            vtep_ip: Remote VTEP IP address.
            vtep_port: Remote VTEP UDP port.
        """
        self.vtep_registry[vtep_ip] = {
            "vtep_ip": vtep_ip,
            "vtep_port": vtep_port,
            "vni": self.vni,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.debug("Registered remote VTEP: %s:%d", vtep_ip, vtep_port)

    def learn_mac(self, mac: str, vtep_ip: str) -> None:
        """Learn a MAC-to-VTEP mapping in the FDB.

        When a frame arrives from a remote VTEP, the source MAC
        is learned and associated with the VTEP IP for future
        forwarding decisions.

        Args:
            mac: Source MAC address.
            vtep_ip: VTEP IP the frame arrived from.
        """
        self.fdb[mac] = vtep_ip
        logger.debug("FDB learned: MAC=%s -> VTEP=%s", mac, vtep_ip)

    def encapsulate(
        self, frame: bytes, src_mac: str, dst_mac: str
    ) -> Optional[Dict[str, Any]]:
        """Encapsulate an Ethernet frame in VXLAN.

        Looks up the destination MAC in the FDB to find the remote
        VTEP.  If found, constructs a VXLAN encapsulation header
        containing the VNI, and returns the encapsulated packet
        metadata.

        Args:
            frame: Raw Ethernet frame bytes.
            src_mac: Source MAC address.
            dst_mac: Destination MAC address.

        Returns:
            Encapsulation metadata dict, or None if destination unknown.
        """
        vtep_dst = self.fdb.get(dst_mac)
        if vtep_dst is None:
            return None

        # VXLAN header: 8 bytes
        # Flags (1 byte) + Reserved (3 bytes) + VNI (3 bytes) + Reserved (1 byte)
        vxlan_flags = 0x08  # I flag set (valid VNI)
        vxlan_header = struct.pack(
            "!B3xI",
            vxlan_flags,
            (self.vni << 8),
        )

        return {
            "vtep_src": self.vtep_ip,
            "vtep_dst": vtep_dst,
            "vtep_port": self.vtep_port,
            "vni": self.vni,
            "vxlan_header": vxlan_header,
            "inner_frame_size": len(frame),
            "outer_frame_size": len(frame) + 50,
        }

    def add(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> CNIResult:
        """Configure overlay networking for a container.

        Allocates an IP address, creates a virtual interface
        in the container's namespace, and registers the container's
        MAC in the local FDB for forwarding.

        Args:
            container_id: Container identifier.
            netns: Container's network namespace path.
            ifname: Interface name in the container.
            config: CNI configuration.

        Returns:
            CNIResult with overlay network configuration.

        Raises:
            CNIAddError: If overlay setup fails.
        """
        with self._lock:
            try:
                container_mac = _generate_mac()

                # Allocate IP
                allocation = None
                if self.ipam is not None:
                    allocation = self.ipam.allocate(
                        container_id=container_id,
                        ifname=ifname,
                    )

                # Register in FDB (local VTEP)
                self.fdb[container_mac] = self.vtep_ip

                # Track container
                self._containers[container_id] = {
                    "mac": container_mac,
                    "netns": netns,
                    "ifname": ifname,
                    "ip": allocation.ip_address if allocation else None,
                    "vtep": self.vtep_ip,
                }

                result = CNIResult(
                    interfaces=[
                        {
                            "name": ifname,
                            "mac": container_mac,
                            "sandbox": netns,
                        }
                    ],
                )

                if allocation is not None:
                    result.ips = [
                        {
                            "address": f"{allocation.ip_address}/{allocation.prefix_length}",
                            "gateway": allocation.gateway,
                            "interface": 0,
                        }
                    ]
                    result.routes = [
                        {
                            "dst": "0.0.0.0/0",
                            "gw": allocation.gateway,
                        }
                    ]

                result.dns = {
                    "nameservers": [self.gateway],
                    "domain": DEFAULT_DNS_DOMAIN,
                    "search": [DEFAULT_DNS_DOMAIN],
                }

                self._stats.total_add_ops += 1
                self._stats.active_containers += 1

                self._emit(EventType.CNI_CONTAINER_ADDED, {
                    "container_id": container_id,
                    "plugin": "overlay",
                    "vni": self.vni,
                })

                logger.info(
                    "Overlay ADD: container=%s VNI=%d ip=%s",
                    container_id, self.vni,
                    allocation.ip_address if allocation else "none",
                )

                return result

            except IPAMError as exc:
                self._stats.errors += 1
                raise CNIAddError(
                    f"Overlay ADD failed for {container_id}: {exc}"
                ) from exc

    def delete(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> None:
        """Remove overlay networking for a container.

        Releases the IP address, removes the MAC from the FDB,
        and deregisters the container.

        Args:
            container_id: Container identifier.
            netns: Container's network namespace path.
            ifname: Interface name to remove.
            config: CNI configuration.
        """
        with self._lock:
            try:
                info = self._containers.pop(container_id, None)
                if info is not None:
                    self.fdb.pop(info["mac"], None)

                if self.ipam is not None:
                    self.ipam.release(container_id)

                self._stats.total_del_ops += 1
                self._stats.active_containers = max(
                    0, self._stats.active_containers - 1
                )

                self._emit(EventType.CNI_CONTAINER_DELETED, {
                    "container_id": container_id,
                    "plugin": "overlay",
                })

                logger.info("Overlay DEL: container=%s", container_id)

            except Exception as exc:
                self._stats.errors += 1
                raise CNIDeleteError(
                    f"Overlay DEL failed for {container_id}: {exc}"
                ) from exc

    def check(
        self,
        container_id: str,
        netns: str,
        ifname: str,
        config: CNIConfig,
    ) -> bool:
        """Verify overlay networking for a container.

        Validates that the container is registered with the overlay,
        has an FDB entry, and has a valid IP allocation.

        Args:
            container_id: Container identifier.
            netns: Container's network namespace path.
            ifname: Interface name to check.
            config: CNI configuration.

        Returns:
            True if configuration is consistent.

        Raises:
            CNICheckError: If drift is detected.
        """
        with self._lock:
            self._stats.total_check_ops += 1

            if container_id not in self._containers:
                raise CNICheckError(
                    f"Container {container_id} not registered with overlay plugin"
                )

            info = self._containers[container_id]
            if info["mac"] not in self.fdb:
                raise CNICheckError(
                    f"MAC {info['mac']} not in FDB for container {container_id}"
                )

            if self.ipam is not None and not self.ipam.has_allocation(container_id):
                raise CNICheckError(
                    f"No IP allocation for container {container_id}"
                )

            self._emit(EventType.CNI_CONTAINER_CHECKED, {
                "container_id": container_id,
                "plugin": "overlay",
            })

            return True

    @property
    def stats(self) -> CNIStats:
        """Return overlay plugin statistics."""
        return self._stats


# ============================================================
# IPAM Plugin
# ============================================================


class IPAMPlugin:
    """IP Address Management plugin for container networks.

    Manages subnet allocation, IP address assignment, and DHCP-style
    lease lifecycle.  The IPAM plugin carves addresses from a
    configured CIDR range, tracks allocations, detects conflicts,
    and reclaims expired leases.

    The first usable address in each subnet is reserved for the
    gateway.  The broadcast address is excluded from allocation.
    Addresses are allocated sequentially from the available pool.

    Attributes:
        subnet: Network CIDR range for allocation.
        gateway: Gateway IP address (reserved, not allocatable).
        lease_duration: Default lease duration in seconds.
        allocations: Active IP allocations by container ID.
        leases: Active DHCP leases by container ID.
        allocated_set: Set of allocated IP address strings.
        event_bus: Optional event bus for lifecycle events.
    """

    def __init__(
        self,
        subnet: str = DEFAULT_SUBNET,
        gateway: str = DEFAULT_GATEWAY,
        lease_duration: float = DEFAULT_LEASE_DURATION,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._lock = threading.Lock()
        self.subnet = subnet
        self.gateway = gateway
        self.lease_duration = lease_duration
        self._event_bus = event_bus

        # Parse network
        self._network = ipaddress.IPv4Network(subnet, strict=False)
        self._gateway_ip = ipaddress.IPv4Address(gateway)

        # Build free pool (exclude network, broadcast, and gateway)
        self._free_pool: List[str] = []
        for host in self._network.hosts():
            if host != self._gateway_ip:
                self._free_pool.append(str(host))

        self.allocations: Dict[str, IPAllocation] = {}
        self.leases: Dict[str, Lease] = {}
        self.allocated_set: Set[str] = set()
        self._expired_count = 0

        logger.info(
            "IPAM initialized: subnet=%s gateway=%s pool_size=%d lease=%ds",
            subnet, gateway, len(self._free_pool), int(lease_duration),
        )

    def _emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data or {})
            except Exception:
                pass

    def allocate(
        self,
        container_id: str,
        ifname: str = "eth0",
    ) -> IPAllocation:
        """Allocate an IP address for a container.

        Assigns the next available address from the free pool,
        creates an allocation record and a DHCP lease.

        Args:
            container_id: Container identifier.
            ifname: Interface the address will be bound to.

        Returns:
            IPAllocation with the assigned address.

        Raises:
            IPAMExhaustedError: If no addresses are available.
            IPAMConflictError: If the container already has an allocation.
        """
        with self._lock:
            # Check for existing allocation
            if container_id in self.allocations:
                raise IPAMConflictError(
                    f"Container {container_id} already has an IP allocation"
                )

            # Reclaim expired leases first
            self._reclaim_expired()

            if not self._free_pool:
                raise IPAMExhaustedError(
                    f"No available addresses in subnet {self.subnet}"
                )

            ip_str = self._free_pool.pop(0)

            allocation = IPAllocation(
                ip_address=ip_str,
                subnet=self.subnet,
                gateway=self.gateway,
                prefix_length=self._network.prefixlen,
                container_id=container_id,
                interface_name=ifname,
            )

            now = datetime.now(timezone.utc)
            lease = Lease(
                allocation=allocation,
                state=LeaseState.ACTIVE,
                duration=self.lease_duration,
                granted_at=now,
                expires_at=datetime(
                    now.year, now.month, now.day,
                    now.hour, now.minute, now.second,
                    now.microsecond, tzinfo=timezone.utc,
                ),
            )
            # Compute expiration properly
            import datetime as dt_module
            lease.expires_at = now + dt_module.timedelta(seconds=self.lease_duration)

            self.allocations[container_id] = allocation
            self.leases[container_id] = lease
            self.allocated_set.add(ip_str)

            self._emit(EventType.CNI_IP_ALLOCATED, {
                "container_id": container_id,
                "ip_address": ip_str,
                "subnet": self.subnet,
            })
            self._emit(EventType.CNI_LEASE_GRANTED, {
                "container_id": container_id,
                "lease_id": lease.lease_id,
                "duration": self.lease_duration,
            })

            logger.info(
                "IPAM allocated: %s -> %s (lease %s, expires in %ds)",
                container_id, ip_str, lease.lease_id, int(self.lease_duration),
            )

            return allocation

    def release(self, container_id: str) -> None:
        """Release an IP allocation for a container.

        Returns the address to the free pool, marks the lease as
        released, and removes the allocation record.

        Args:
            container_id: Container identifier.
        """
        with self._lock:
            allocation = self.allocations.pop(container_id, None)
            if allocation is not None:
                self.allocated_set.discard(allocation.ip_address)
                self._free_pool.append(allocation.ip_address)

                self._emit(EventType.CNI_IP_RELEASED, {
                    "container_id": container_id,
                    "ip_address": allocation.ip_address,
                })

                logger.info(
                    "IPAM released: %s <- %s",
                    container_id, allocation.ip_address,
                )

            lease = self.leases.pop(container_id, None)
            if lease is not None:
                lease.state = LeaseState.RELEASED

    def renew(self, container_id: str) -> Lease:
        """Renew an existing DHCP lease.

        Extends the lease's expiration by the configured duration
        from the current time.

        Args:
            container_id: Container identifier.

        Returns:
            The renewed Lease.

        Raises:
            IPAMLeaseExpiredError: If the lease has already expired.
            IPAMError: If no lease exists for the container.
        """
        with self._lock:
            lease = self.leases.get(container_id)
            if lease is None:
                raise IPAMError(
                    f"No lease found for container {container_id}"
                )

            if lease.is_expired():
                raise IPAMLeaseExpiredError(
                    f"Lease for container {container_id} has expired"
                )

            now = datetime.now(timezone.utc)
            import datetime as dt_module
            lease.expires_at = now + dt_module.timedelta(seconds=self.lease_duration)
            lease.renewed_at = now
            lease.renewal_count += 1

            logger.debug(
                "IPAM renewed lease %s for %s (renewal #%d)",
                lease.lease_id, container_id, lease.renewal_count,
            )

            return lease

    def has_allocation(self, container_id: str) -> bool:
        """Check whether a container has an active IP allocation.

        Args:
            container_id: Container identifier.

        Returns:
            True if the container has an allocation.
        """
        return container_id in self.allocations

    def get_allocation(self, container_id: str) -> Optional[IPAllocation]:
        """Get the IP allocation for a container.

        Args:
            container_id: Container identifier.

        Returns:
            IPAllocation if found, None otherwise.
        """
        return self.allocations.get(container_id)

    def detect_conflicts(self) -> List[Tuple[str, str, str]]:
        """Detect IP address allocation conflicts.

        Scans all allocations for duplicate IP assignments within
        the same subnet.

        Returns:
            List of (ip_address, container_id_1, container_id_2) tuples.
        """
        ip_to_containers: Dict[str, List[str]] = defaultdict(list)
        for cid, alloc in self.allocations.items():
            ip_to_containers[alloc.ip_address].append(cid)

        conflicts = []
        for ip_addr, cids in ip_to_containers.items():
            if len(cids) > 1:
                for i in range(len(cids)):
                    for j in range(i + 1, len(cids)):
                        conflicts.append((ip_addr, cids[i], cids[j]))

        return conflicts

    def _reclaim_expired(self) -> int:
        """Reclaim IP addresses from expired leases.

        Returns addresses from expired leases to the free pool.

        Returns:
            Number of leases reclaimed.
        """
        reclaimed = 0
        expired_cids = []
        for cid, lease in self.leases.items():
            if lease.is_expired() and lease.state == LeaseState.ACTIVE:
                expired_cids.append(cid)

        for cid in expired_cids:
            lease = self.leases.pop(cid)
            lease.state = LeaseState.EXPIRED
            allocation = self.allocations.pop(cid, None)
            if allocation is not None:
                self.allocated_set.discard(allocation.ip_address)
                self._free_pool.append(allocation.ip_address)

                self._emit(EventType.CNI_LEASE_EXPIRED, {
                    "container_id": cid,
                    "ip_address": allocation.ip_address,
                })

            reclaimed += 1
            self._expired_count += 1

        return reclaimed

    @property
    def pool_size(self) -> int:
        """Return the number of available addresses in the free pool."""
        return len(self._free_pool)

    @property
    def total_allocated(self) -> int:
        """Return the number of currently allocated addresses."""
        return len(self.allocations)

    @property
    def total_expired(self) -> int:
        """Return the total number of expired leases."""
        return self._expired_count

    @property
    def utilization(self) -> float:
        """Return the IP pool utilization as a fraction (0.0 to 1.0)."""
        total = len(self._free_pool) + len(self.allocations)
        if total == 0:
            return 0.0
        return len(self.allocations) / total


# ============================================================
# Port Mapper
# ============================================================


class PortMapper:
    """Port mapping (DNAT) manager for container port exposure.

    The port mapper creates destination NAT rules that forward
    traffic arriving on host ports to container IP:port endpoints.
    This enables external access to services running inside
    containers.

    Each mapping specifies a host port, container IP, container port,
    and protocol (TCP or UDP).  Port conflicts (two containers
    requesting the same host port and protocol) are detected and
    rejected.

    Attributes:
        mappings: Active port mappings by mapping ID.
        host_port_index: Index of host port+protocol to mapping ID.
        container_index: Index of container ID to mapping IDs.
        event_bus: Optional event bus for lifecycle events.
    """

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self._lock = threading.Lock()
        self.mappings: Dict[str, PortMapping] = {}
        self.host_port_index: Dict[Tuple[int, str], str] = {}
        self.container_index: Dict[str, List[str]] = defaultdict(list)
        self._event_bus = event_bus

    def _emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data or {})
            except Exception:
                pass

    def add_mapping(
        self,
        host_port: int,
        container_ip: str,
        container_port: int,
        protocol: str = "tcp",
        container_id: str = "",
    ) -> PortMapping:
        """Create a port mapping from host to container.

        Args:
            host_port: Port on the host network.
            container_ip: Container IP address.
            container_port: Port in the container.
            protocol: Transport protocol (tcp or udp).
            container_id: Container this mapping belongs to.

        Returns:
            The created PortMapping.

        Raises:
            PortConflictError: If the host port is already mapped.
            PortMappingError: If the mapping count exceeds the limit.
        """
        with self._lock:
            protocol = protocol.lower()
            key = (host_port, protocol)

            if key in self.host_port_index:
                existing_id = self.host_port_index[key]
                existing = self.mappings.get(existing_id)
                raise PortConflictError(
                    f"Host port {host_port}/{protocol} already mapped to "
                    f"{existing.container_ip}:{existing.container_port}" if existing
                    else f"Host port {host_port}/{protocol} already in use"
                )

            if len(self.mappings) >= MAX_PORT_MAPPINGS:
                raise PortMappingError(
                    f"Maximum port mapping count ({MAX_PORT_MAPPINGS}) exceeded"
                )

            if host_port < 1 or host_port > 65535:
                raise PortMappingError(
                    f"Invalid host port: {host_port} (must be 1-65535)"
                )

            if container_port < 1 or container_port > 65535:
                raise PortMappingError(
                    f"Invalid container port: {container_port} (must be 1-65535)"
                )

            mapping = PortMapping(
                host_port=host_port,
                container_ip=container_ip,
                container_port=container_port,
                protocol=protocol,
                container_id=container_id,
            )

            self.mappings[mapping.mapping_id] = mapping
            self.host_port_index[key] = mapping.mapping_id
            self.container_index[container_id].append(mapping.mapping_id)

            self._emit(EventType.CNI_PORT_MAPPED, {
                "host_port": host_port,
                "container_ip": container_ip,
                "container_port": container_port,
                "protocol": protocol,
                "container_id": container_id,
            })

            logger.info(
                "Port mapped: %d/%s -> %s:%d (container %s)",
                host_port, protocol, container_ip, container_port, container_id,
            )

            return mapping

    def remove_mapping(self, mapping_id: str) -> None:
        """Remove a port mapping by ID.

        Args:
            mapping_id: Mapping identifier to remove.

        Raises:
            PortMappingError: If the mapping does not exist.
        """
        with self._lock:
            mapping = self.mappings.pop(mapping_id, None)
            if mapping is None:
                raise PortMappingError(
                    f"Port mapping {mapping_id} not found"
                )

            key = (mapping.host_port, mapping.protocol)
            self.host_port_index.pop(key, None)

            cid_mappings = self.container_index.get(mapping.container_id, [])
            if mapping_id in cid_mappings:
                cid_mappings.remove(mapping_id)

            self._emit(EventType.CNI_PORT_UNMAPPED, {
                "host_port": mapping.host_port,
                "container_id": mapping.container_id,
            })

            logger.info(
                "Port unmapped: %d/%s (container %s)",
                mapping.host_port, mapping.protocol, mapping.container_id,
            )

    def remove_container_mappings(self, container_id: str) -> int:
        """Remove all port mappings for a container.

        Args:
            container_id: Container identifier.

        Returns:
            Number of mappings removed.
        """
        with self._lock:
            mapping_ids = list(self.container_index.pop(container_id, []))
            removed = 0
            for mid in mapping_ids:
                mapping = self.mappings.pop(mid, None)
                if mapping is not None:
                    key = (mapping.host_port, mapping.protocol)
                    self.host_port_index.pop(key, None)
                    removed += 1

                    self._emit(EventType.CNI_PORT_UNMAPPED, {
                        "host_port": mapping.host_port,
                        "container_id": container_id,
                    })

            return removed

    def resolve(self, host_port: int, protocol: str = "tcp") -> Optional[PortMapping]:
        """Resolve a host port to its container endpoint.

        Args:
            host_port: Host port to resolve.
            protocol: Transport protocol.

        Returns:
            PortMapping if found, None otherwise.
        """
        key = (host_port, protocol.lower())
        mapping_id = self.host_port_index.get(key)
        if mapping_id is None:
            return None
        return self.mappings.get(mapping_id)

    def get_container_mappings(self, container_id: str) -> List[PortMapping]:
        """Get all port mappings for a container.

        Args:
            container_id: Container identifier.

        Returns:
            List of PortMapping objects.
        """
        mapping_ids = self.container_index.get(container_id, [])
        return [self.mappings[mid] for mid in mapping_ids if mid in self.mappings]

    @property
    def total_mappings(self) -> int:
        """Return the total number of active port mappings."""
        return len(self.mappings)


# ============================================================
# Container DNS
# ============================================================


class ContainerDNS:
    """Container DNS server for name resolution within the cluster.

    Provides DNS resolution for container names and service names
    within the container network.  Supports A (IPv4), AAAA (IPv6),
    SRV (service discovery), PTR (reverse lookup), and CNAME
    (aliasing) record types.

    Container names are automatically registered when containers
    join the network and removed when they leave.  Service names
    resolve to the service's cluster IP or load-balanced endpoints.

    Attributes:
        domain: DNS domain for container names.
        ttl: Default TTL for DNS records.
        records: DNS records indexed by name.
        ptr_records: Reverse DNS records indexed by IP.
        query_count: Total queries served.
        event_bus: Optional event bus for lifecycle events.
    """

    def __init__(
        self,
        domain: str = DEFAULT_DNS_DOMAIN,
        ttl: int = DEFAULT_DNS_TTL,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._lock = threading.Lock()
        self.domain = domain
        self.ttl = ttl
        self._event_bus = event_bus
        self.records: Dict[str, List[DNSRecord]] = defaultdict(list)
        self.ptr_records: Dict[str, DNSRecord] = {}
        self.container_records: Dict[str, List[str]] = defaultdict(list)
        self.query_count = 0
        self.query_miss_count = 0

        logger.info("Container DNS initialized: domain=%s ttl=%d", domain, ttl)

    def _emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data or {})
            except Exception:
                pass

    def _fqdn(self, name: str) -> str:
        """Convert a short name to a fully qualified domain name.

        Args:
            name: Short name (e.g., web-server).

        Returns:
            FQDN (e.g., web-server.cluster.fizz).
        """
        if name.endswith(f".{self.domain}"):
            return name
        return f"{name}.{self.domain}"

    def add_record(
        self,
        name: str,
        record_type: DNSRecordType,
        value: str,
        container_id: str = "",
        ttl: Optional[int] = None,
        priority: int = 0,
        port: int = 0,
        weight: int = 0,
    ) -> DNSRecord:
        """Add a DNS record.

        Args:
            name: DNS name for the record.
            record_type: Record type (A, AAAA, SRV, PTR, CNAME).
            value: Record value.
            container_id: Container this record belongs to.
            ttl: Record TTL (uses default if not specified).
            priority: SRV priority (0 for non-SRV).
            port: SRV port (0 for non-SRV).
            weight: SRV weight (0 for non-SRV).

        Returns:
            The created DNSRecord.

        Raises:
            ContainerDNSError: If record count exceeds the limit.
        """
        with self._lock:
            total = sum(len(recs) for recs in self.records.values())
            if total >= MAX_DNS_RECORDS:
                raise ContainerDNSError(
                    f"Maximum DNS record count ({MAX_DNS_RECORDS}) exceeded"
                )

            fqdn = self._fqdn(name) if record_type != DNSRecordType.PTR else name

            record = DNSRecord(
                name=fqdn,
                record_type=record_type,
                value=value,
                ttl=ttl if ttl is not None else self.ttl,
                container_id=container_id,
                priority=priority,
                port=port,
                weight=weight,
            )

            self.records[fqdn].append(record)

            if container_id:
                self.container_records[container_id].append(fqdn)

            # Auto-create PTR for A records
            if record_type == DNSRecordType.A:
                ptr_name = self._ip_to_ptr(value)
                ptr_record = DNSRecord(
                    name=ptr_name,
                    record_type=DNSRecordType.PTR,
                    value=fqdn,
                    ttl=ttl if ttl is not None else self.ttl,
                    container_id=container_id,
                )
                self.ptr_records[ptr_name] = ptr_record

            self._emit(EventType.CNI_DNS_RECORD_ADDED, {
                "name": fqdn,
                "type": record_type.value,
                "value": value,
                "container_id": container_id,
            })

            logger.debug(
                "DNS record added: %s %s %s (container %s)",
                fqdn, record_type.value, value, container_id,
            )

            return record

    def remove_container_records(self, container_id: str) -> int:
        """Remove all DNS records for a container.

        Args:
            container_id: Container identifier.

        Returns:
            Number of records removed.
        """
        with self._lock:
            fqdns = list(self.container_records.pop(container_id, []))
            removed = 0
            for fqdn in fqdns:
                if fqdn in self.records:
                    before = len(self.records[fqdn])
                    self.records[fqdn] = [
                        r for r in self.records[fqdn]
                        if r.container_id != container_id
                    ]
                    after = len(self.records[fqdn])
                    removed += before - after
                    if not self.records[fqdn]:
                        del self.records[fqdn]

            # Remove PTR records for this container
            ptr_to_remove = [
                k for k, v in self.ptr_records.items()
                if v.container_id == container_id
            ]
            for ptr_name in ptr_to_remove:
                del self.ptr_records[ptr_name]
                removed += 1

            return removed

    def resolve(
        self,
        name: str,
        record_type: DNSRecordType = DNSRecordType.A,
    ) -> List[DNSRecord]:
        """Resolve a DNS name to records.

        Args:
            name: DNS name to resolve.
            record_type: Record type to look for.

        Returns:
            List of matching DNSRecord objects.
        """
        with self._lock:
            self.query_count += 1

            # Try PTR lookup
            if record_type == DNSRecordType.PTR:
                ptr_name = name if name.endswith(".in-addr.arpa") else self._ip_to_ptr(name)
                record = self.ptr_records.get(ptr_name)
                if record is not None:
                    self._emit(EventType.CNI_DNS_RESOLVED, {
                        "name": ptr_name,
                        "type": "PTR",
                    })
                    return [record]
                self.query_miss_count += 1
                return []

            fqdn = self._fqdn(name)
            records = self.records.get(fqdn, [])
            matching = [r for r in records if r.record_type == record_type]

            if matching:
                self._emit(EventType.CNI_DNS_RESOLVED, {
                    "name": fqdn,
                    "type": record_type.value,
                    "count": len(matching),
                })
            else:
                self.query_miss_count += 1

            return matching

    def register_container(
        self,
        container_id: str,
        container_name: str,
        ip_address: str,
    ) -> List[DNSRecord]:
        """Register DNS records for a container.

        Creates an A record and a SRV record for the container.

        Args:
            container_id: Container identifier.
            container_name: Container name for DNS.
            ip_address: Container's IP address.

        Returns:
            List of created DNSRecord objects.
        """
        records = []

        # A record: name -> IP
        a_record = self.add_record(
            name=container_name,
            record_type=DNSRecordType.A,
            value=ip_address,
            container_id=container_id,
        )
        records.append(a_record)

        # SRV record for service discovery
        srv_record = self.add_record(
            name=f"_fizzbuzz._tcp.{container_name}",
            record_type=DNSRecordType.SRV,
            value=self._fqdn(container_name),
            container_id=container_id,
            priority=10,
            port=8080,
            weight=100,
        )
        records.append(srv_record)

        return records

    @staticmethod
    def _ip_to_ptr(ip_address: str) -> str:
        """Convert an IP address to a PTR record name.

        Args:
            ip_address: IPv4 address string.

        Returns:
            PTR name in in-addr.arpa format.
        """
        parts = ip_address.split(".")
        return ".".join(reversed(parts)) + ".in-addr.arpa"

    @property
    def total_records(self) -> int:
        """Return the total number of DNS records."""
        count = sum(len(recs) for recs in self.records.values())
        count += len(self.ptr_records)
        return count

    @property
    def total_queries(self) -> int:
        """Return the total number of DNS queries served."""
        return self.query_count


# ============================================================
# Network Policy Engine
# ============================================================


class NetworkPolicyEngine:
    """Network policy enforcement engine for container microsegmentation.

    Implements Kubernetes-style network policies that control ingress
    and egress traffic between containers based on label selectors,
    namespaces, and port/protocol specifications.

    When a policy is applied to a container (via pod selector matching),
    the container operates in default-deny mode for the policy's
    direction (ingress, egress, or both).  Only traffic explicitly
    permitted by a rule is allowed through.

    Attributes:
        policies: Active network policies by ID.
        container_labels: Labels assigned to containers.
        connection_table: Connection tracking table.
        event_bus: Optional event bus for lifecycle events.
    """

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self._lock = threading.Lock()
        self.policies: Dict[str, NetworkPolicySpec] = {}
        self.container_labels: Dict[str, Dict[str, str]] = {}
        self.connection_table: Dict[str, Dict[str, Any]] = {}
        self._event_bus = event_bus
        self._eval_count = 0
        self._allow_count = 0
        self._deny_count = 0

    def _emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data or {})
            except Exception:
                pass

    def add_policy(self, policy: NetworkPolicySpec) -> None:
        """Add a network policy.

        Args:
            policy: Network policy specification.

        Raises:
            NetworkPolicyError: If the policy count exceeds the limit.
        """
        with self._lock:
            if len(self.policies) >= MAX_POLICIES:
                raise NetworkPolicyError(
                    f"Maximum network policy count ({MAX_POLICIES}) exceeded"
                )

            self.policies[policy.policy_id] = policy
            logger.info(
                "Network policy added: %s (selector=%s)",
                policy.name, policy.pod_selector,
            )

    def remove_policy(self, policy_id: str) -> None:
        """Remove a network policy.

        Args:
            policy_id: Policy identifier.

        Raises:
            NetworkPolicyError: If the policy does not exist.
        """
        with self._lock:
            if policy_id not in self.policies:
                raise NetworkPolicyError(
                    f"Network policy {policy_id} not found"
                )
            policy = self.policies.pop(policy_id)
            logger.info("Network policy removed: %s", policy.name)

    def set_container_labels(
        self, container_id: str, labels: Dict[str, str]
    ) -> None:
        """Set labels for a container.

        Labels are used for policy selector matching.  A policy's
        pod_selector must match all specified label key-value pairs
        for the policy to apply to a container.

        Args:
            container_id: Container identifier.
            labels: Label key-value pairs.
        """
        with self._lock:
            self.container_labels[container_id] = dict(labels)

    def remove_container(self, container_id: str) -> None:
        """Remove a container from the policy engine.

        Args:
            container_id: Container identifier.
        """
        with self._lock:
            self.container_labels.pop(container_id, None)
            # Remove connection tracking entries for this container
            keys_to_remove = [
                k for k in self.connection_table
                if container_id in k
            ]
            for k in keys_to_remove:
                del self.connection_table[k]

    def _matches_selector(
        self, container_id: str, selector: Dict[str, str]
    ) -> bool:
        """Check whether a container matches a label selector.

        Args:
            container_id: Container identifier.
            selector: Label selector (all pairs must match).

        Returns:
            True if all selector labels match the container's labels.
        """
        if not selector:
            return True  # Empty selector matches all

        labels = self.container_labels.get(container_id, {})
        return all(labels.get(k) == v for k, v in selector.items())

    def _matches_cidr(self, ip_address: str, cidr_blocks: List[str]) -> bool:
        """Check whether an IP address falls within any CIDR block.

        Args:
            ip_address: IP address to check.
            cidr_blocks: List of CIDR blocks.

        Returns:
            True if the IP is in any block (or blocks list is empty).
        """
        if not cidr_blocks:
            return True

        try:
            addr = ipaddress.IPv4Address(ip_address)
            for cidr in cidr_blocks:
                network = ipaddress.IPv4Network(cidr, strict=False)
                if addr in network:
                    return True
        except (ValueError, ipaddress.AddressValueError):
            pass

        return False

    def evaluate(
        self,
        src_container_id: str,
        dst_container_id: str,
        src_ip: str = "",
        dst_ip: str = "",
        dst_port: int = 0,
        protocol: str = "tcp",
    ) -> PolicyAction:
        """Evaluate network policies for a traffic flow.

        Checks all applicable policies for both the source (egress)
        and destination (ingress) containers.  If any applicable
        policy denies the traffic, the packet is dropped.

        Args:
            src_container_id: Source container identifier.
            dst_container_id: Destination container identifier.
            src_ip: Source IP address.
            dst_ip: Destination IP address.
            dst_port: Destination port.
            protocol: Transport protocol.

        Returns:
            PolicyAction.ALLOW or PolicyAction.DENY.
        """
        with self._lock:
            self._eval_count += 1

            # Check connection tracking table
            conn_key = f"{src_container_id}({src_ip})->{dst_container_id}({dst_ip}):{dst_port}/{protocol}"
            if conn_key in self.connection_table:
                ct_entry = self.connection_table[conn_key]
                if ct_entry.get("action") == "allow":
                    self._allow_count += 1
                    return PolicyAction.ALLOW

            # Evaluate ingress policies on destination
            ingress_result = self._evaluate_direction(
                container_id=dst_container_id,
                direction=PolicyDirection.INGRESS,
                peer_id=src_container_id,
                peer_ip=src_ip,
                port=dst_port,
                protocol=protocol,
            )

            # Evaluate egress policies on source
            egress_result = self._evaluate_direction(
                container_id=src_container_id,
                direction=PolicyDirection.EGRESS,
                peer_id=dst_container_id,
                peer_ip=dst_ip,
                port=dst_port,
                protocol=protocol,
            )

            # Both must allow
            if ingress_result == PolicyAction.DENY or egress_result == PolicyAction.DENY:
                self._deny_count += 1

                self._emit(EventType.CNI_POLICY_EVALUATED, {
                    "src": src_container_id,
                    "dst": dst_container_id,
                    "action": "deny",
                })

                return PolicyAction.DENY

            # Track connection
            self.connection_table[conn_key] = {
                "action": "allow",
                "src": src_container_id,
                "dst": dst_container_id,
                "port": dst_port,
                "protocol": protocol,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self._allow_count += 1

            self._emit(EventType.CNI_POLICY_EVALUATED, {
                "src": src_container_id,
                "dst": dst_container_id,
                "action": "allow",
            })

            return PolicyAction.ALLOW

    def _evaluate_direction(
        self,
        container_id: str,
        direction: PolicyDirection,
        peer_id: str,
        peer_ip: str,
        port: int,
        protocol: str,
    ) -> PolicyAction:
        """Evaluate policies for a specific direction on a container.

        If no policies apply to this container for this direction,
        traffic is allowed (no policy = allow all).  If policies
        apply but no rule matches, traffic is denied (default-deny).

        Args:
            container_id: Container being evaluated.
            direction: INGRESS or EGRESS.
            peer_id: Peer container identifier.
            peer_ip: Peer IP address.
            port: Traffic port.
            protocol: Transport protocol.

        Returns:
            PolicyAction for this direction.
        """
        applicable_policies = []
        for policy in self.policies.values():
            if self._matches_selector(container_id, policy.pod_selector):
                applicable_policies.append(policy)

        if not applicable_policies:
            return PolicyAction.ALLOW  # No policy = allow all

        # Check rules in applicable policies
        for policy in applicable_policies:
            rules = (
                policy.ingress_rules if direction == PolicyDirection.INGRESS
                else policy.egress_rules
            )

            if not rules:
                continue  # No rules for this direction in this policy

            for rule in rules:
                if rule.direction != direction:
                    continue

                # Check selector match
                if not self._matches_selector(peer_id, rule.selector_labels):
                    continue

                # Check port match
                if rule.ports and port not in rule.ports:
                    continue

                # Check protocol match
                if rule.protocols and protocol not in rule.protocols:
                    continue

                # Check CIDR match
                if not self._matches_cidr(peer_ip, rule.cidr_blocks):
                    continue

                # Rule matches
                return rule.action

        # Policies apply but no rule matched = default deny
        return PolicyAction.DENY

    def get_applicable_policies(self, container_id: str) -> List[NetworkPolicySpec]:
        """Get all policies that apply to a container.

        Args:
            container_id: Container identifier.

        Returns:
            List of applicable NetworkPolicySpec objects.
        """
        with self._lock:
            return [
                p for p in self.policies.values()
                if self._matches_selector(container_id, p.pod_selector)
            ]

    @property
    def total_policies(self) -> int:
        """Return the total number of active policies."""
        return len(self.policies)

    @property
    def evaluation_count(self) -> int:
        """Return the total policy evaluation count."""
        return self._eval_count

    @property
    def allow_count(self) -> int:
        """Return the total allowed packet count."""
        return self._allow_count

    @property
    def deny_count(self) -> int:
        """Return the total denied packet count."""
        return self._deny_count


# ============================================================
# CNI Manager
# ============================================================


class CNIManager:
    """CNI plugin orchestrator.

    The CNI manager is the central dispatcher for container network
    operations.  It maintains a registry of available plugins,
    routes operations to the appropriate plugin based on configuration,
    manages IPAM, port mapping, DNS, and network policy subsystems,
    and provides aggregate statistics.

    Attributes:
        plugins: Registered CNI plugins by type.
        default_plugin_type: Default plugin type for new containers.
        ipam: IPAM plugin instance.
        port_mapper: Port mapper instance.
        dns: Container DNS instance.
        policy_engine: Network policy engine instance.
        event_bus: Optional event bus for lifecycle events.
    """

    def __init__(
        self,
        default_plugin_type: PluginType = PluginType.BRIDGE,
        subnet: str = DEFAULT_SUBNET,
        gateway: str = DEFAULT_GATEWAY,
        bridge_name: str = DEFAULT_BRIDGE_NAME,
        lease_duration: float = DEFAULT_LEASE_DURATION,
        mtu: int = DEFAULT_MTU,
        dns_domain: str = DEFAULT_DNS_DOMAIN,
        dns_ttl: int = DEFAULT_DNS_TTL,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._event_bus = event_bus
        self.default_plugin_type = default_plugin_type

        # Initialize IPAM
        self.ipam = IPAMPlugin(
            subnet=subnet,
            gateway=gateway,
            lease_duration=lease_duration,
            event_bus=event_bus,
        )

        # Initialize plugins
        self.plugins: Dict[PluginType, CNIPlugin] = {}

        bridge = BridgePlugin(
            bridge_name=bridge_name,
            gateway=gateway,
            subnet=subnet,
            mtu=mtu,
            ipam=self.ipam,
            event_bus=event_bus,
        )
        self.plugins[PluginType.BRIDGE] = bridge

        self.plugins[PluginType.HOST] = HostPlugin(event_bus=event_bus)
        self.plugins[PluginType.NONE] = NonePlugin(event_bus=event_bus)

        overlay_ipam = IPAMPlugin(
            subnet=subnet,
            gateway=gateway,
            lease_duration=lease_duration,
            event_bus=event_bus,
        )
        self.plugins[PluginType.OVERLAY] = OverlayPlugin(
            subnet=subnet,
            gateway=gateway,
            mtu=mtu,
            ipam=overlay_ipam,
            event_bus=event_bus,
        )

        # Initialize auxiliary subsystems
        self.port_mapper = PortMapper(event_bus=event_bus)
        self.dns = ContainerDNS(
            domain=dns_domain,
            ttl=dns_ttl,
            event_bus=event_bus,
        )
        self.policy_engine = NetworkPolicyEngine(event_bus=event_bus)

        # Container registry: container_id -> plugin_type
        self._container_plugins: Dict[str, PluginType] = {}

        logger.info(
            "CNI Manager initialized: default=%s subnet=%s gateway=%s",
            default_plugin_type.value, subnet, gateway,
        )

    def add(
        self,
        container_id: str,
        netns: str = "",
        ifname: str = "eth0",
        plugin_type: Optional[PluginType] = None,
        config: Optional[CNIConfig] = None,
        container_name: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> CNIResult:
        """Configure networking for a container.

        Dispatches to the appropriate plugin and registers DNS
        records for the container.

        Args:
            container_id: Container identifier.
            netns: Container's network namespace path.
            ifname: Interface name in the container.
            plugin_type: Plugin type (uses default if None).
            config: CNI configuration (generated if None).
            container_name: Container name for DNS (uses ID if None).
            labels: Container labels for policy matching.

        Returns:
            CNIResult from the plugin.

        Raises:
            CNIPluginNotFoundError: If the plugin type is not registered.
            CNIAddError: If the plugin ADD operation fails.
        """
        with self._lock:
            ptype = plugin_type or self.default_plugin_type

            plugin = self.plugins.get(ptype)
            if plugin is None:
                raise CNIPluginNotFoundError(
                    f"CNI plugin type '{ptype.value}' not registered"
                )

            if config is None:
                config = CNIConfig(plugin_type=ptype.value)

            result = plugin.add(container_id, netns, ifname, config)

            self._container_plugins[container_id] = ptype

            # Register DNS
            name = container_name or container_id[:12]
            if result.ips:
                ip_str = result.ips[0].get("address", "").split("/")[0]
                if ip_str:
                    self.dns.register_container(container_id, name, ip_str)

            # Set labels for policy engine
            if labels:
                self.policy_engine.set_container_labels(container_id, labels)

            return result

    def delete(
        self,
        container_id: str,
        netns: str = "",
        ifname: str = "eth0",
        config: Optional[CNIConfig] = None,
    ) -> None:
        """Remove networking for a container.

        Dispatches to the appropriate plugin, removes DNS records,
        and cleans up port mappings.

        Args:
            container_id: Container identifier.
            netns: Container's network namespace path.
            ifname: Interface name to remove.
            config: CNI configuration.

        Raises:
            CNIPluginNotFoundError: If the container's plugin is unknown.
        """
        with self._lock:
            ptype = self._container_plugins.pop(container_id, None)
            if ptype is None:
                raise CNIPluginNotFoundError(
                    f"No plugin registered for container {container_id}"
                )

            plugin = self.plugins.get(ptype)
            if plugin is None:
                raise CNIPluginNotFoundError(
                    f"CNI plugin type '{ptype.value}' not registered"
                )

            if config is None:
                config = CNIConfig(plugin_type=ptype.value)

            plugin.delete(container_id, netns, ifname, config)

            # Clean up DNS
            self.dns.remove_container_records(container_id)

            # Clean up port mappings
            self.port_mapper.remove_container_mappings(container_id)

            # Clean up policy engine
            self.policy_engine.remove_container(container_id)

    def check(
        self,
        container_id: str,
        netns: str = "",
        ifname: str = "eth0",
        config: Optional[CNIConfig] = None,
    ) -> bool:
        """Verify networking for a container.

        Args:
            container_id: Container identifier.
            netns: Container's network namespace path.
            ifname: Interface name to check.
            config: CNI configuration.

        Returns:
            True if configuration is consistent.

        Raises:
            CNIPluginNotFoundError: If the container's plugin is unknown.
            CNICheckError: If drift is detected.
        """
        with self._lock:
            ptype = self._container_plugins.get(container_id)
            if ptype is None:
                raise CNIPluginNotFoundError(
                    f"No plugin registered for container {container_id}"
                )

            plugin = self.plugins.get(ptype)
            if plugin is None:
                raise CNIPluginNotFoundError(
                    f"CNI plugin type '{ptype.value}' not registered"
                )

            if config is None:
                config = CNIConfig(plugin_type=ptype.value)

            return plugin.check(container_id, netns, ifname, config)

    def get_plugin(self, plugin_type: PluginType) -> Optional[CNIPlugin]:
        """Get a registered plugin by type.

        Args:
            plugin_type: Plugin type to retrieve.

        Returns:
            CNIPlugin instance if registered, None otherwise.
        """
        return self.plugins.get(plugin_type)

    def list_networks(self) -> List[Dict[str, Any]]:
        """List all configured networks.

        Returns:
            List of network description dicts.
        """
        networks = []
        for ptype, plugin in self.plugins.items():
            network = {
                "type": ptype.value,
                "active_containers": plugin.stats.active_containers,
                "total_add_ops": plugin.stats.total_add_ops,
                "total_del_ops": plugin.stats.total_del_ops,
            }
            if isinstance(plugin, BridgePlugin):
                network["bridge_name"] = plugin.bridge.name
                network["gateway"] = plugin.bridge.ip_address
                network["subnet"] = plugin.bridge.subnet
                network["stp_enabled"] = plugin.bridge.stp_enabled
                network["nat_enabled"] = plugin.bridge.nat_enabled
            elif isinstance(plugin, OverlayPlugin):
                network["vni"] = plugin.vni
                network["vtep_ip"] = plugin.vtep_ip
                network["vtep_count"] = len(plugin.vtep_registry)

            networks.append(network)
        return networks

    def get_stats(self) -> CNIStats:
        """Get aggregate statistics across all plugins.

        Returns:
            Aggregate CNIStats.
        """
        stats = CNIStats()
        for plugin in self.plugins.values():
            ps = plugin.stats
            stats.total_add_ops += ps.total_add_ops
            stats.total_del_ops += ps.total_del_ops
            stats.total_check_ops += ps.total_check_ops
            stats.active_containers += ps.active_containers
            stats.errors += ps.errors

        bridge = self.plugins.get(PluginType.BRIDGE)
        if isinstance(bridge, BridgePlugin):
            stats.active_veth_pairs = len(bridge.veth_pairs)

        stats.allocated_ips = self.ipam.total_allocated
        stats.active_leases = len(self.ipam.leases)
        stats.expired_leases = self.ipam.total_expired
        stats.active_port_mappings = self.port_mapper.total_mappings
        stats.dns_records = self.dns.total_records
        stats.dns_queries = self.dns.total_queries
        stats.active_policies = self.policy_engine.total_policies
        stats.policy_evaluations = self.policy_engine.evaluation_count
        stats.packets_allowed = self.policy_engine.allow_count
        stats.packets_denied = self.policy_engine.deny_count

        return stats

    @property
    def active_container_count(self) -> int:
        """Return the number of active containers across all plugins."""
        return len(self._container_plugins)


# ============================================================
# CNI Dashboard
# ============================================================


class CNIDashboard:
    """ASCII dashboard renderer for the CNI subsystem.

    Renders network topology, IPAM statistics, port mappings,
    DNS records, and policy summaries in a fixed-width ASCII
    format suitable for terminal display.

    Attributes:
        width: Dashboard width in characters.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self.width = width

    def render(self, manager: CNIManager) -> str:
        """Render the complete CNI dashboard.

        Args:
            manager: CNI manager to render statistics for.

        Returns:
            Multi-line ASCII dashboard string.

        Raises:
            CNIDashboardError: If rendering fails.
        """
        try:
            lines: List[str] = []
            iw = self.width - 4  # inner width (between "| " and " |")

            def border() -> str:
                return "  +" + "-" * (self.width - 2) + "+"

            def row(text: str) -> str:
                return f"  | {text:<{iw}} |"

            lines.append(border())
            lines.append(row("FIZZCNI: CONTAINER NETWORK INTERFACE"))
            lines.append(row("=" * iw))

            stats = manager.get_stats()

            # Overview
            lines.append(row(f"Active Containers: {stats.active_containers}"))
            lines.append(row(f"Total ADD/DEL/CHECK: {stats.total_add_ops}/{stats.total_del_ops}/{stats.total_check_ops}"))
            lines.append(row(f"Errors: {stats.errors}"))
            lines.append(row("-" * iw))

            # Networks
            lines.append(row("NETWORKS"))
            for net in manager.list_networks():
                line = f"  {net['type']:<10} containers={net['active_containers']}"
                if "bridge_name" in net:
                    line += f" bridge={net['bridge_name']}"
                if "vni" in net:
                    line += f" VNI={net['vni']}"
                lines.append(row(line))
            lines.append(row("-" * iw))

            # IPAM
            lines.append(row("IPAM"))
            lines.append(row(f"  Allocated IPs: {stats.allocated_ips}"))
            lines.append(row(f"  Active Leases: {stats.active_leases}"))
            lines.append(row(f"  Expired Leases: {stats.expired_leases}"))
            lines.append(row(f"  Pool Utilization: {manager.ipam.utilization * 100:.1f}%"))
            lines.append(row("-" * iw))

            # Port Mapping
            lines.append(row("PORT MAPPINGS"))
            lines.append(row(f"  Active Mappings: {stats.active_port_mappings}"))
            for _mid, mapping in list(manager.port_mapper.mappings.items())[:5]:
                lines.append(row(
                    f"  {mapping.host_port}/{mapping.protocol} -> "
                    f"{mapping.container_ip}:{mapping.container_port}"
                ))
            if stats.active_port_mappings > 5:
                lines.append(row(f"  ... and {stats.active_port_mappings - 5} more"))
            lines.append(row("-" * iw))

            # DNS
            lines.append(row("CONTAINER DNS"))
            lines.append(row(f"  Domain: {manager.dns.domain}"))
            lines.append(row(f"  Records: {stats.dns_records}"))
            lines.append(row(f"  Queries: {stats.dns_queries}"))
            lines.append(row("-" * iw))

            # Policies
            lines.append(row("NETWORK POLICIES"))
            lines.append(row(f"  Active Policies: {stats.active_policies}"))
            lines.append(row(f"  Evaluations: {stats.policy_evaluations}"))
            lines.append(row(f"  Allowed: {stats.packets_allowed}"))
            lines.append(row(f"  Denied: {stats.packets_denied}"))

            lines.append(border())

            return "\n".join(lines)

        except Exception as exc:
            raise CNIDashboardError(
                f"Dashboard rendering failed: {exc}"
            ) from exc

    def render_topology(self, manager: CNIManager) -> str:
        """Render network topology as ASCII art.

        Args:
            manager: CNI manager.

        Returns:
            ASCII topology diagram.
        """
        try:
            lines: List[str] = []
            iw = self.width - 4

            def border() -> str:
                return "  +" + "-" * (self.width - 2) + "+"

            def row(text: str) -> str:
                return f"  | {text:<{iw}} |"

            lines.append(border())
            lines.append(row("NETWORK TOPOLOGY"))
            lines.append(row("=" * iw))

            bridge = manager.plugins.get(PluginType.BRIDGE)
            if isinstance(bridge, BridgePlugin):
                lines.append(row(f"Bridge: {bridge.bridge.name}"))
                lines.append(row(f"  IP: {bridge.bridge.ip_address}"))
                lines.append(row(f"  MAC: {bridge.bridge.mac}"))
                lines.append(row(f"  STP: {'enabled' if bridge.bridge.stp_enabled else 'disabled'}"))
                lines.append(row(f"  NAT: {'enabled' if bridge.bridge.nat_enabled else 'disabled'}"))
                lines.append(row(f"  Ports: {len(bridge.bridge.ports)}"))
                lines.append(row(f"  MAC Table: {len(bridge.bridge.mac_table)} entries"))

                for cid, pair in list(bridge.veth_pairs.items())[:10]:
                    alloc = manager.ipam.get_allocation(cid)
                    ip_str = alloc.ip_address if alloc else "no-ip"
                    lines.append(row(
                        f"    |-- {pair.host_ifname} <-> "
                        f"{pair.container_ifname} ({ip_str}) [{cid[:8]}]"
                    ))

                if len(bridge.veth_pairs) > 10:
                    lines.append(row(
                        f"    |-- ... and {len(bridge.veth_pairs) - 10} more"
                    ))

            lines.append(border())
            return "\n".join(lines)

        except Exception as exc:
            raise CNIDashboardError(
                f"Topology rendering failed: {exc}"
            ) from exc

    def render_ipam_stats(self, manager: CNIManager) -> str:
        """Render IPAM statistics.

        Args:
            manager: CNI manager.

        Returns:
            ASCII IPAM statistics.
        """
        try:
            lines: List[str] = []
            iw = self.width - 4

            def border() -> str:
                return "  +" + "-" * (self.width - 2) + "+"

            def row(text: str) -> str:
                return f"  | {text:<{iw}} |"

            lines.append(border())
            lines.append(row("IPAM STATISTICS"))
            lines.append(row("=" * iw))
            lines.append(row(f"Subnet: {manager.ipam.subnet}"))
            lines.append(row(f"Gateway: {manager.ipam.gateway}"))
            lines.append(row(f"Pool Size: {manager.ipam.pool_size}"))
            lines.append(row(f"Allocated: {manager.ipam.total_allocated}"))
            lines.append(row(f"Utilization: {manager.ipam.utilization * 100:.1f}%"))
            lines.append(row(f"Expired Leases: {manager.ipam.total_expired}"))

            # List allocations
            lines.append(row("-" * iw))
            lines.append(row("ALLOCATIONS"))
            for cid, alloc in list(manager.ipam.allocations.items())[:10]:
                lease = manager.ipam.leases.get(cid)
                remaining = f"{lease.remaining_seconds():.0f}s" if lease else "n/a"
                lines.append(row(
                    f"  {alloc.ip_address:<16} {cid[:12]:<14} TTL={remaining}"
                ))

            if len(manager.ipam.allocations) > 10:
                lines.append(row(
                    f"  ... and {len(manager.ipam.allocations) - 10} more"
                ))

            # Conflict detection
            conflicts = manager.ipam.detect_conflicts()
            if conflicts:
                lines.append(row("-" * iw))
                lines.append(row("CONFLICTS DETECTED"))
                for ip_addr, c1, c2 in conflicts:
                    lines.append(row(f"  {ip_addr}: {c1[:8]} <-> {c2[:8]}"))

            lines.append(border())
            return "\n".join(lines)

        except Exception as exc:
            raise CNIDashboardError(
                f"IPAM stats rendering failed: {exc}"
            ) from exc

    def render_port_mappings(self, manager: CNIManager) -> str:
        """Render port mapping table.

        Args:
            manager: CNI manager.

        Returns:
            ASCII port mapping table.
        """
        try:
            lines: List[str] = []
            iw = self.width - 4

            def border() -> str:
                return "  +" + "-" * (self.width - 2) + "+"

            def row(text: str) -> str:
                return f"  | {text:<{iw}} |"

            lines.append(border())
            lines.append(row("PORT MAPPINGS"))
            lines.append(row("=" * iw))
            lines.append(row(f"Total: {manager.port_mapper.total_mappings}"))
            lines.append(row("-" * iw))
            lines.append(row(f"{'HOST PORT':<12} {'CONTAINER':<28} {'PROTO':<6}"))
            lines.append(row("-" * iw))

            for _mid, mapping in manager.port_mapper.mappings.items():
                target = f"{mapping.container_ip}:{mapping.container_port}"
                lines.append(row(
                    f"{mapping.host_port:<12} {target:<28} {mapping.protocol:<6}"
                ))

            lines.append(border())
            return "\n".join(lines)

        except Exception as exc:
            raise CNIDashboardError(
                f"Port mapping rendering failed: {exc}"
            ) from exc

    def render_policies(self, manager: CNIManager) -> str:
        """Render network policy summary.

        Args:
            manager: CNI manager.

        Returns:
            ASCII policy summary.
        """
        try:
            lines: List[str] = []
            iw = self.width - 4

            def border() -> str:
                return "  +" + "-" * (self.width - 2) + "+"

            def row(text: str) -> str:
                return f"  | {text:<{iw}} |"

            lines.append(border())
            lines.append(row("NETWORK POLICIES"))
            lines.append(row("=" * iw))
            lines.append(row(f"Policies: {manager.policy_engine.total_policies}"))
            lines.append(row(f"Evaluations: {manager.policy_engine.evaluation_count}"))
            lines.append(row(f"Allowed: {manager.policy_engine.allow_count}"))
            lines.append(row(f"Denied: {manager.policy_engine.deny_count}"))
            lines.append(row("-" * iw))

            for pid, policy in manager.policy_engine.policies.items():
                lines.append(row(f"Policy: {policy.name}"))
                lines.append(row(f"  Namespace: {policy.namespace}"))
                lines.append(row(f"  Selector: {policy.pod_selector}"))
                lines.append(row(f"  Ingress Rules: {len(policy.ingress_rules)}"))
                lines.append(row(f"  Egress Rules: {len(policy.egress_rules)}"))

            lines.append(border())
            return "\n".join(lines)

        except Exception as exc:
            raise CNIDashboardError(
                f"Policy rendering failed: {exc}"
            ) from exc


# ============================================================
# FizzCNI Middleware
# ============================================================


class FizzCNIMiddleware(IMiddleware):
    """Middleware integrating CNI with the FizzBuzz evaluation pipeline.

    Ensures container network configuration is applied before each
    FizzBuzz evaluation begins in a containerized context.  Tracks
    network operations and provides post-execution rendering for
    CLI output.

    Priority: 111 (runs after container runtime setup, before
    application-layer middleware).

    Attributes:
        manager: CNI manager instance.
        dashboard: CNI dashboard renderer.
        priority: Middleware pipeline priority.
    """

    def __init__(
        self,
        manager: CNIManager,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
        enable_dashboard: bool = False,
    ) -> None:
        self.manager = manager
        self.dashboard = CNIDashboard(width=dashboard_width)
        self._enable_dashboard = enable_dashboard
        self._evaluation_count = 0
        self._errors = 0
        self._container_counter = 0

    def get_name(self) -> str:
        """Return the middleware name."""
        return "FizzCNIMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Return middleware priority (111)."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return the middleware name (convenience property)."""
        return "FizzCNIMiddleware"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the CNI middleware.

        Simulates container network setup for each evaluation:
        creates a transient container, configures networking via
        the default CNI plugin, evaluates, and tears down.

        Args:
            context: Processing context.
            next_handler: Next middleware in the pipeline.

        Returns:
            The processed context.

        Raises:
            CNIMiddlewareError: If network setup fails.
        """
        self._evaluation_count += 1
        self._container_counter += 1

        number = context.number if hasattr(context, "number") else 0
        container_id = f"fizz-eval-{self._container_counter}"
        netns = f"/var/run/netns/{container_id}"

        try:
            # ADD
            cni_result = self.manager.add(
                container_id=container_id,
                netns=netns,
                ifname="eth0",
                container_name=f"eval-{number}",
                labels={"app": "fizzbuzz", "eval": str(number)},
            )

            # Enrich context metadata
            if hasattr(context, "metadata") and isinstance(context.metadata, dict):
                context.metadata["cni_container_id"] = container_id
                if cni_result.ips:
                    context.metadata["cni_ip"] = cni_result.ips[0].get("address", "")

            # Delegate to next handler
            result_context = next_handler(context)

            # DEL (teardown after evaluation)
            self.manager.delete(
                container_id=container_id,
                netns=netns,
                ifname="eth0",
            )

            return result_context

        except (CNIError, CNIPluginNotFoundError) as exc:
            self._errors += 1
            raise CNIMiddlewareError(
                evaluation_number=number,
                reason=str(exc),
            ) from exc

    def render_dashboard(self) -> str:
        """Render the CNI dashboard.

        Returns:
            ASCII dashboard string.
        """
        return self.dashboard.render(self.manager)

    def render_topology(self) -> str:
        """Render the network topology.

        Returns:
            ASCII topology string.
        """
        return self.dashboard.render_topology(self.manager)

    def render_ipam_stats(self) -> str:
        """Render IPAM statistics.

        Returns:
            ASCII IPAM stats string.
        """
        return self.dashboard.render_ipam_stats(self.manager)

    def render_port_mappings(self) -> str:
        """Render port mapping table.

        Returns:
            ASCII port mapping string.
        """
        return self.dashboard.render_port_mappings(self.manager)

    def render_policies(self) -> str:
        """Render network policy summary.

        Returns:
            ASCII policy summary string.
        """
        return self.dashboard.render_policies(self.manager)

    def render_stats(self) -> str:
        """Render aggregate statistics.

        Returns:
            Formatted statistics string.
        """
        stats = self.manager.get_stats()
        lines = [
            "  FizzCNI Statistics:",
            f"    Evaluations: {self._evaluation_count}",
            f"    Active Containers: {stats.active_containers}",
            f"    Total ADD/DEL/CHECK: {stats.total_add_ops}/{stats.total_del_ops}/{stats.total_check_ops}",
            f"    Allocated IPs: {stats.allocated_ips}",
            f"    Active Leases: {stats.active_leases}",
            f"    Port Mappings: {stats.active_port_mappings}",
            f"    DNS Records: {stats.dns_records}",
            f"    Policies: {stats.active_policies}",
            f"    Errors: {self._errors}",
        ]
        return "\n".join(lines)


# ============================================================
# Factory
# ============================================================


def create_fizzcni_subsystem(
    subnet: str = DEFAULT_SUBNET,
    gateway: str = DEFAULT_GATEWAY,
    bridge_name: str = DEFAULT_BRIDGE_NAME,
    lease_duration: float = DEFAULT_LEASE_DURATION,
    mtu: int = DEFAULT_MTU,
    dns_domain: str = DEFAULT_DNS_DOMAIN,
    dns_ttl: int = DEFAULT_DNS_TTL,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzCNI subsystem.

    Factory function that instantiates the CNI manager with all
    plugins (bridge, host, none, overlay), IPAM, port mapper,
    container DNS, network policy engine, and middleware, ready
    for integration into the FizzBuzz evaluation pipeline.

    Args:
        subnet: Pod network CIDR range.
        gateway: Gateway IP address.
        bridge_name: Bridge interface name.
        lease_duration: DHCP lease duration in seconds.
        mtu: Maximum Transmission Unit.
        dns_domain: Container DNS domain.
        dns_ttl: Default DNS TTL.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable post-execution dashboard.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (CNIManager, FizzCNIMiddleware).
    """
    manager = CNIManager(
        subnet=subnet,
        gateway=gateway,
        bridge_name=bridge_name,
        lease_duration=lease_duration,
        mtu=mtu,
        dns_domain=dns_domain,
        dns_ttl=dns_ttl,
        event_bus=event_bus,
    )

    middleware = FizzCNIMiddleware(
        manager=manager,
        dashboard_width=dashboard_width,
        enable_dashboard=enable_dashboard,
    )

    logger.info("FizzCNI subsystem created and wired")

    return manager, middleware
