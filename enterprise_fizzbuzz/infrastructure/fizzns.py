"""
Enterprise FizzBuzz Platform - Linux Namespace Isolation Engine (FizzNS)

Implements comprehensive Linux namespace isolation semantics for the
Enterprise FizzBuzz Platform, providing all seven namespace types defined
by the Linux kernel: PID, NET, MNT, UTS, IPC, USER, and CGROUP.  Each
namespace type partitions kernel resources so that processes inside a
namespace observe an isolated view of the system, precisely matching the
semantics of the Linux kernel's clone(2) and unshare(2) system calls.

Linux namespaces are the foundational isolation mechanism of every
container runtime.  Introduced incrementally between Linux 2.4.19
(mount namespaces, 2002) and Linux 4.6 (cgroup namespaces, 2016),
namespaces enable containers to operate as if they are the only tenants
on the system.  Without namespace isolation, processes share the host's
PID table, network stack, mount table, hostname, IPC channels, user
credentials, and cgroup hierarchy.  With namespace isolation, each
container receives its own isolated instance of every resource.

The Enterprise FizzBuzz Platform has operated FizzKube -- a full
Kubernetes-style container orchestrator -- since Round 5.  FizzKube
schedules pods, manages deployments and replica sets, runs horizontal
pod autoscalers, and enforces resource quotas.  But the pods it
schedules are Python dataclass instances sharing every host resource.
The orchestrator exists; the isolation does not.  FizzNS provides
the isolation layer that transforms FizzKube's dataclass pods into
properly namespaced containers.

The seven namespace types implemented:

  - **PID Namespace**: Isolated process ID spaces.  Each PID namespace
    maintains its own PID allocation table starting from PID 1.  The
    first process becomes the init process, inheriting orphans and
    triggering SIGKILL to all members upon exit.  PIDs are visible
    hierarchically: parent namespaces see child PIDs mapped into
    their PID space; child namespaces cannot observe parent PIDs.

  - **NET Namespace**: Isolated network stacks.  Each NET namespace has
    its own network interfaces, IP addresses, routing table, and socket
    bindings.  New NET namespaces start with only a loopback interface.
    Virtual ethernet (veth) pairs bridge namespaces for connectivity.

  - **MNT Namespace**: Isolated mount tables.  Each MNT namespace
    receives a copy of the parent's mount table at creation time.
    Subsequent mount and umount operations are invisible to the parent.
    pivot_root() replaces the namespace's root filesystem -- the
    mechanism containers use to switch from host rootfs to container
    rootfs.

  - **UTS Namespace**: Isolated hostname and domain name.  Each UTS
    namespace has independent hostname and domainname, allowing
    containers to set their hostname without affecting the host.

  - **IPC Namespace**: Isolated IPC resources.  Each IPC namespace has
    its own System V IPC identifier space for shared memory segments,
    semaphore sets, and message queues.  IPC objects in one namespace
    are invisible to processes in other namespaces.

  - **USER Namespace**: UID/GID mapping.  USER namespaces map container
    UIDs to host UIDs, enabling rootless container operation.  A process
    can be root (UID 0) inside a USER namespace while being unprivileged
    on the host.  Capability bounding sets are namespace-scoped.

  - **CGROUP Namespace**: Virtualized cgroup view.  CGROUP namespaces
    virtualize the cgroup hierarchy so processes see their own cgroup
    as the root, preventing containers from discovering or manipulating
    the host's cgroup tree.

Key design decisions:

  - Middleware priority is 106, after OrgMiddleware (105) and before
    Archaeology (900).  Namespace isolation logically follows
    organizational hierarchy: the org chart defines who operates the
    containers; the namespace engine defines where those containers
    execute in isolation.

  - All seven Linux namespace types are implemented as first-class
    objects with individual resource tracking, hierarchy support,
    and reference counting.

  - The NamespaceManager singleton manages the global namespace
    registry, providing clone(), unshare(), and setns() operations
    that mirror the Linux kernel's system call semantics.

  - Root namespaces (one per type) represent the host's default
    namespaces, matching the Linux kernel's initial namespace set.

  - Namespace garbage collection reclaims destroyed namespaces
    whose reference counts have reached zero.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CGROUPNamespaceError,
    IPCNamespaceError,
    MNTNamespaceError,
    NETNamespaceError,
    NamespaceCreationError,
    NamespaceDashboardError,
    NamespaceDestroyError,
    NamespaceEntryError,
    NamespaceError,
    NamespaceHierarchyError,
    NamespaceLeaveError,
    NamespaceManagerError,
    NamespaceMiddlewareError,
    NamespaceRefCountError,
    NamespaceTypeError,
    PIDNamespaceError,
    USERNamespaceError,
    UTSNamespaceError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

# Clone flags matching Linux kernel definitions from include/uapi/linux/sched.h.
# These constants define which namespace types are created during clone(2) or
# unshare(2) operations.  The values match the kernel's bitmask positions,
# ensuring compatibility with tools that inspect clone flags.

CLONE_NEWPID = 0x20000000
"""Create a new PID namespace (CLONE_NEWPID, Linux 2.6.24)."""

CLONE_NEWNET = 0x40000000
"""Create a new network namespace (CLONE_NEWNET, Linux 2.6.24)."""

CLONE_NEWNS = 0x00020000
"""Create a new mount namespace (CLONE_NEWNS, Linux 2.4.19)."""

CLONE_NEWUTS = 0x04000000
"""Create a new UTS namespace (CLONE_NEWUTS, Linux 2.6.19)."""

CLONE_NEWIPC = 0x08000000
"""Create a new IPC namespace (CLONE_NEWIPC, Linux 2.6.19)."""

CLONE_NEWUSER = 0x10000000
"""Create a new user namespace (CLONE_NEWUSER, Linux 3.8)."""

CLONE_NEWCGROUP = 0x02000000
"""Create a new cgroup namespace (CLONE_NEWCGROUP, Linux 4.6)."""

DEFAULT_HOSTNAME = "fizzbuzz-container"
"""Default hostname assigned to new UTS namespaces."""

DEFAULT_DOMAINNAME = "enterprise.local"
"""Default domain name assigned to new UTS namespaces."""

ROOT_UID = 0
"""Root user ID inside a USER namespace."""

ROOT_GID = 0
"""Root group ID inside a USER namespace."""

NOBODY_UID = 65534
"""Nobody user ID, used for unmapped UIDs."""

NOBODY_GID = 65534
"""Nobody group ID, used for unmapped GIDs."""

MAX_PID = 32768
"""Maximum PID value for PID namespaces (matching Linux default)."""

MAX_NAMESPACE_DEPTH = 32
"""Maximum nesting depth for namespace hierarchies."""

MAX_UID_MAP_ENTRIES = 340
"""Maximum number of UID map entries per USER namespace."""

MAX_GID_MAP_ENTRIES = 340
"""Maximum number of GID map entries per USER namespace."""

LOOPBACK_INTERFACE = "lo"
"""Name of the loopback interface created in each NET namespace."""

LOOPBACK_IPV4 = "127.0.0.1"
"""IPv4 address for the loopback interface."""

LOOPBACK_IPV6 = "::1"
"""IPv6 address for the loopback interface."""

MAX_SHM_SEGMENTS = 4096
"""Maximum shared memory segments per IPC namespace."""

MAX_SEMAPHORE_SETS = 32000
"""Maximum semaphore sets per IPC namespace."""

MAX_MSG_QUEUES = 32000
"""Maximum message queues per IPC namespace."""


# ══════════════════════════════════════════════════════════════════════
# Enumerations
# ══════════════════════════════════════════════════════════════════════


class NamespaceType(Enum):
    """Linux namespace type classification.

    The Linux kernel defines seven distinct namespace types, each
    isolating a different category of kernel resource.  Every container
    runtime uses some or all of these namespace types to establish
    isolation boundaries between containers and between containers
    and the host.

    Each member stores the corresponding CLONE_NEW* flag value from
    the Linux kernel headers, enabling direct flag composition for
    clone(2) and unshare(2) system call emulation.

    Attributes:
        PID: Process ID namespace (CLONE_NEWPID, 0x20000000).
        NET: Network namespace (CLONE_NEWNET, 0x40000000).
        MNT: Mount namespace (CLONE_NEWNS, 0x00020000).
        UTS: UTS namespace (CLONE_NEWUTS, 0x04000000).
        IPC: IPC namespace (CLONE_NEWIPC, 0x08000000).
        USER: User namespace (CLONE_NEWUSER, 0x10000000).
        CGROUP: Cgroup namespace (CLONE_NEWCGROUP, 0x02000000).
    """

    PID = CLONE_NEWPID
    NET = CLONE_NEWNET
    MNT = CLONE_NEWNS
    UTS = CLONE_NEWUTS
    IPC = CLONE_NEWIPC
    USER = CLONE_NEWUSER
    CGROUP = CLONE_NEWCGROUP


class NamespaceState(Enum):
    """Lifecycle state of a namespace instance.

    Namespaces transition through three states during their lifecycle.
    The state machine is strictly monotonic: once a namespace enters
    DESTROYING, it cannot return to ACTIVE; once it enters DESTROYED,
    no further operations are permitted.

    Attributes:
        ACTIVE: The namespace is operational and accepting processes.
        DESTROYING: The namespace is being torn down; no new processes
            may enter, but existing processes may still be running.
        DESTROYED: The namespace has been fully cleaned up and all
            resources released.
    """

    ACTIVE = "active"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"


# ══════════════════════════════════════════════════════════════════════
# Data Classes
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class VethPair:
    """Virtual ethernet pair connecting two network namespaces.

    A veth pair consists of two virtual network interfaces that act as
    a tunnel between network namespaces.  Packets sent on one end of
    the pair are immediately received on the other end.  This is the
    primary mechanism for providing network connectivity to containers.

    Attributes:
        pair_id: Unique identifier for this veth pair.
        host_interface: Name of the interface in the host namespace.
        container_interface: Name of the interface in the container namespace.
        host_ns_id: Namespace ID of the host end.
        container_ns_id: Namespace ID of the container end.
        created_at: Timestamp when the pair was created.
    """

    pair_id: str
    host_interface: str
    container_interface: str
    host_ns_id: str
    container_ns_id: str
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class MountEntry:
    """Entry in a mount namespace's mount table.

    Each mount entry represents a single filesystem mount within a
    mount namespace.  The mount table is copied from the parent
    namespace at creation time, and subsequent modifications are
    local to the namespace.

    Attributes:
        mount_id: Unique identifier for this mount entry.
        source: Source device or filesystem path.
        target: Mount point path within the namespace.
        fs_type: Filesystem type (e.g., 'ext4', 'tmpfs', 'proc').
        options: Mount options string.
        propagation: Mount propagation type ('private', 'shared',
            'slave', 'unbindable').
        created_at: Timestamp when the mount was performed.
    """

    mount_id: str
    source: str
    target: str
    fs_type: str
    options: str = "rw"
    propagation: str = "private"
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class UIDMapping:
    """UID mapping entry for a USER namespace.

    Maps a range of UIDs from inside the namespace to UIDs in the
    parent namespace.  This is the mechanism that enables rootless
    containers: UID 0 inside the namespace can map to an unprivileged
    UID on the host.

    Attributes:
        inner_start: Starting UID inside the namespace.
        outer_start: Starting UID in the parent namespace.
        count: Number of UIDs in the mapping range.
    """

    inner_start: int
    outer_start: int
    count: int


@dataclass(frozen=True)
class GIDMapping:
    """GID mapping entry for a USER namespace.

    Maps a range of GIDs from inside the namespace to GIDs in the
    parent namespace, following the same semantics as UID mappings.

    Attributes:
        inner_start: Starting GID inside the namespace.
        outer_start: Starting GID in the parent namespace.
        count: Number of GIDs in the mapping range.
    """

    inner_start: int
    outer_start: int
    count: int


@dataclass
class NetworkInterface:
    """Network interface within a NET namespace.

    Represents a virtual or physical network interface with its
    associated addresses, state, and statistics.

    Attributes:
        name: Interface name (e.g., 'eth0', 'lo', 'veth0').
        mac_address: MAC address of the interface.
        ipv4_addresses: List of IPv4 addresses assigned.
        ipv6_addresses: List of IPv6 addresses assigned.
        mtu: Maximum transmission unit.
        state: Interface state ('up' or 'down').
        rx_bytes: Total bytes received.
        tx_bytes: Total bytes transmitted.
        rx_packets: Total packets received.
        tx_packets: Total packets transmitted.
    """

    name: str
    mac_address: str = ""
    ipv4_addresses: list[str] = field(default_factory=list)
    ipv6_addresses: list[str] = field(default_factory=list)
    mtu: int = 1500
    state: str = "down"
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0


@dataclass
class RoutingEntry:
    """Routing table entry within a NET namespace.

    Each routing entry defines how packets destined for a particular
    network prefix should be forwarded.

    Attributes:
        destination: Destination network prefix (e.g., '0.0.0.0/0').
        gateway: Next-hop gateway address.
        interface: Outgoing interface name.
        metric: Route metric (lower is preferred).
        flags: Routing flags string.
    """

    destination: str
    gateway: str
    interface: str
    metric: int = 0
    flags: str = "UG"


@dataclass
class SocketBinding:
    """Socket binding within a NET namespace.

    Records an active socket binding (listen or connected) within
    a network namespace.  Two processes in different NET namespaces
    can both bind to the same port without conflict.

    Attributes:
        protocol: Protocol type ('tcp', 'udp', 'raw').
        address: Bound address.
        port: Bound port number.
        state: Socket state ('listening', 'established', 'closed').
        pid: PID of the process holding the socket.
    """

    protocol: str
    address: str
    port: int
    state: str = "listening"
    pid: int = 0


@dataclass
class SHMSegment:
    """Shared memory segment in an IPC namespace.

    System V shared memory segments are scoped to IPC namespaces.
    Segments created in one IPC namespace are invisible to processes
    in other IPC namespaces.

    Attributes:
        shm_id: Shared memory segment identifier.
        key: IPC key used to create or look up the segment.
        size: Segment size in bytes.
        owner_pid: PID of the creating process.
        attached_pids: Set of PIDs currently attached.
        created_at: Creation timestamp.
    """

    shm_id: int
    key: int
    size: int
    owner_pid: int = 0
    attached_pids: set[int] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)


@dataclass
class SemaphoreSet:
    """Semaphore set in an IPC namespace.

    System V semaphore sets provide inter-process synchronization.
    Each semaphore set is scoped to its IPC namespace.

    Attributes:
        sem_id: Semaphore set identifier.
        key: IPC key used to create or look up the set.
        num_sems: Number of semaphores in the set.
        owner_pid: PID of the creating process.
        created_at: Creation timestamp.
    """

    sem_id: int
    key: int
    num_sems: int
    owner_pid: int = 0
    created_at: float = field(default_factory=time.time)


@dataclass
class MessageQueue:
    """Message queue in an IPC namespace.

    System V message queues provide inter-process messaging.
    Each message queue is scoped to its IPC namespace.

    Attributes:
        msq_id: Message queue identifier.
        key: IPC key used to create or look up the queue.
        max_bytes: Maximum queue size in bytes.
        owner_pid: PID of the creating process.
        message_count: Number of messages currently in the queue.
        created_at: Creation timestamp.
    """

    msq_id: int
    key: int
    max_bytes: int = 16384
    owner_pid: int = 0
    message_count: int = 0
    created_at: float = field(default_factory=time.time)


@dataclass
class CgroupEntry:
    """Cgroup entry in a CGROUP namespace.

    Represents a cgroup path and its associated controllers as
    visible within a CGROUP namespace.

    Attributes:
        path: Cgroup path relative to the namespace root.
        controllers: Set of active controllers (e.g., 'cpu', 'memory').
        processes: Set of PIDs in this cgroup.
    """

    path: str
    controllers: set[str] = field(default_factory=set)
    processes: set[int] = field(default_factory=set)


# ══════════════════════════════════════════════════════════════════════
# Abstract Base: Namespace
# ══════════════════════════════════════════════════════════════════════


class Namespace(ABC):
    """Abstract base class for all namespace types.

    Provides the common infrastructure shared by all seven namespace
    types: unique identification, parent-child hierarchy, reference
    counting, member process tracking, and lifecycle state management.

    Each concrete namespace implementation adds type-specific resource
    isolation.  The abstract methods define the interface contract that
    every namespace type must honor.

    Attributes:
        ns_id: Unique namespace identifier.
        ns_type: The type of namespace (PID, NET, MNT, etc.).
        parent: The parent namespace, or None for root namespaces.
        children: List of child namespaces.
        ref_count: Number of active references (processes + bind-mounts).
        state: Current lifecycle state.
        member_pids: Set of PIDs currently in this namespace.
        created_at: Timestamp when the namespace was created.
        metadata: Arbitrary metadata dictionary.
    """

    def __init__(
        self,
        ns_type: NamespaceType,
        parent: Optional[Namespace] = None,
        ns_id: Optional[str] = None,
    ) -> None:
        """Initialize the namespace.

        Args:
            ns_type: The namespace type.
            parent: Optional parent namespace for hierarchy.
            ns_id: Optional namespace ID; auto-generated if not provided.

        Raises:
            NamespaceHierarchyError: If nesting depth exceeds maximum.
        """
        self._ns_id = ns_id or f"ns-{ns_type.name.lower()}-{uuid.uuid4().hex[:12]}"
        self._ns_type = ns_type
        self._parent = parent
        self._children: list[Namespace] = []
        self._ref_count = 0
        self._state = NamespaceState.ACTIVE
        self._member_pids: set[int] = set()
        self._created_at = time.time()
        self._metadata: dict[str, Any] = {}

        # Validate hierarchy depth
        depth = self._compute_depth()
        if depth > MAX_NAMESPACE_DEPTH:
            raise NamespaceHierarchyError(
                f"Namespace nesting depth {depth} exceeds maximum {MAX_NAMESPACE_DEPTH}"
            )

        # Register with parent
        if parent is not None:
            parent._children.append(self)

        logger.debug(
            "Namespace created: id=%s type=%s parent=%s depth=%d",
            self._ns_id,
            ns_type.name,
            parent._ns_id if parent else "root",
            depth,
        )

    def _compute_depth(self) -> int:
        """Compute the nesting depth of this namespace.

        Returns:
            The depth (0 for root namespaces, 1 for children of root, etc.).
        """
        depth = 0
        current = self._parent
        while current is not None:
            depth += 1
            current = current._parent
        return depth

    @property
    def ns_id(self) -> str:
        """Return the unique namespace identifier."""
        return self._ns_id

    @property
    def ns_type(self) -> NamespaceType:
        """Return the namespace type."""
        return self._ns_type

    @property
    def parent(self) -> Optional[Namespace]:
        """Return the parent namespace."""
        return self._parent

    @property
    def children(self) -> list[Namespace]:
        """Return the list of child namespaces."""
        return list(self._children)

    @property
    def ref_count(self) -> int:
        """Return the current reference count."""
        return self._ref_count

    @property
    def state(self) -> NamespaceState:
        """Return the current lifecycle state."""
        return self._state

    @property
    def member_pids(self) -> set[int]:
        """Return the set of member PIDs."""
        return set(self._member_pids)

    @property
    def created_at(self) -> float:
        """Return the creation timestamp."""
        return self._created_at

    @property
    def metadata(self) -> dict[str, Any]:
        """Return the metadata dictionary."""
        return dict(self._metadata)

    @property
    def depth(self) -> int:
        """Return the nesting depth."""
        return self._compute_depth()

    @property
    def is_root(self) -> bool:
        """Return True if this is a root namespace."""
        return self._parent is None

    def add_ref(self) -> int:
        """Increment the reference count.

        Returns:
            The new reference count.

        Raises:
            NamespaceRefCountError: If the namespace is not active.
        """
        if self._state != NamespaceState.ACTIVE:
            raise NamespaceRefCountError(
                f"Cannot add reference to namespace {self._ns_id} "
                f"in state {self._state.value}"
            )
        self._ref_count += 1
        return self._ref_count

    def release_ref(self) -> int:
        """Decrement the reference count.

        Returns:
            The new reference count.

        Raises:
            NamespaceRefCountError: If the reference count would go negative.
        """
        if self._ref_count <= 0:
            raise NamespaceRefCountError(
                f"Reference count underflow for namespace {self._ns_id}: "
                f"current count is {self._ref_count}"
            )
        self._ref_count -= 1
        return self._ref_count

    def add_member(self, pid: int) -> None:
        """Add a process to this namespace.

        Args:
            pid: The process ID to add.

        Raises:
            NamespaceEntryError: If the namespace is not active.
        """
        if self._state != NamespaceState.ACTIVE:
            raise NamespaceEntryError(
                f"Cannot add PID {pid} to namespace {self._ns_id} "
                f"in state {self._state.value}"
            )
        self._member_pids.add(pid)
        self.add_ref()

    def remove_member(self, pid: int) -> None:
        """Remove a process from this namespace.

        Args:
            pid: The process ID to remove.

        Raises:
            NamespaceLeaveError: If the PID is not a member.
        """
        if pid not in self._member_pids:
            raise NamespaceLeaveError(
                f"PID {pid} is not a member of namespace {self._ns_id}"
            )
        self._member_pids.discard(pid)
        self.release_ref()

    def set_metadata(self, key: str, value: Any) -> None:
        """Set a metadata key-value pair.

        Args:
            key: Metadata key.
            value: Metadata value.
        """
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata value.

        Args:
            key: Metadata key.
            default: Default value if key not found.

        Returns:
            The metadata value or the default.
        """
        return self._metadata.get(key, default)

    @abstractmethod
    def isolate(self, pid: int) -> None:
        """Isolate a process within this namespace.

        Creates the namespace-specific resource isolation for the given
        process.  The exact semantics depend on the namespace type.

        Args:
            pid: The process ID to isolate.

        Raises:
            NamespaceError: If isolation fails.
        """

    @abstractmethod
    def enter(self, pid: int) -> None:
        """Enter this namespace (setns semantics).

        Moves the specified process into this namespace, making it
        a member and giving it access to the namespace's isolated
        resources.

        Args:
            pid: The process ID entering the namespace.

        Raises:
            NamespaceEntryError: If entry fails.
        """

    @abstractmethod
    def leave(self, pid: int) -> None:
        """Leave this namespace.

        Removes the specified process from this namespace, returning
        it to the parent namespace's resource view.

        Args:
            pid: The process ID leaving the namespace.

        Raises:
            NamespaceLeaveError: If leaving fails.
        """

    @abstractmethod
    def destroy(self) -> None:
        """Destroy this namespace and release all resources.

        Transitions the namespace to DESTROYED state.  All member
        processes must have exited before destruction.

        Raises:
            NamespaceDestroyError: If destruction fails.
        """

    def get_hierarchy(self) -> list[Namespace]:
        """Return the full hierarchy from root to this namespace.

        Returns:
            List of namespaces from root to self.
        """
        hierarchy: list[Namespace] = []
        current: Optional[Namespace] = self
        while current is not None:
            hierarchy.append(current)
            current = current._parent
        hierarchy.reverse()
        return hierarchy

    def get_descendants(self) -> list[Namespace]:
        """Return all descendant namespaces.

        Returns:
            List of all namespaces in the subtree rooted at self.
        """
        descendants: list[Namespace] = []
        stack = list(self._children)
        while stack:
            child = stack.pop()
            descendants.append(child)
            stack.extend(child._children)
        return descendants

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<{self.__class__.__name__} "
            f"id={self._ns_id} "
            f"type={self._ns_type.name} "
            f"state={self._state.value} "
            f"refs={self._ref_count} "
            f"members={len(self._member_pids)}>"
        )


# ══════════════════════════════════════════════════════════════════════
# NamespaceSet
# ══════════════════════════════════════════════════════════════════════


class NamespaceSet:
    """Frozen collection of namespaces defining a container's isolation boundary.

    A NamespaceSet contains at most one namespace of each type, defining
    which resources are isolated for a container.  Containers may share
    some namespace types with their parent while isolating others -- for
    example, a container might have its own PID namespace but share the
    host's NET namespace for direct network access.

    The set is frozen after creation: namespace slots cannot be modified.
    This enforces the Linux kernel's constraint that namespace membership
    is fixed for the lifetime of a process (barring explicit setns calls).

    Attributes:
        set_id: Unique identifier for this namespace set.
        namespaces: Dictionary mapping NamespaceType to Namespace.
        created_at: Creation timestamp.
    """

    def __init__(
        self,
        namespaces: Optional[dict[NamespaceType, Namespace]] = None,
        set_id: Optional[str] = None,
    ) -> None:
        """Initialize the namespace set.

        Args:
            namespaces: Optional mapping of namespace types to instances.
            set_id: Optional set ID; auto-generated if not provided.
        """
        self._set_id = set_id or f"nsset-{uuid.uuid4().hex[:12]}"
        self._namespaces: dict[NamespaceType, Namespace] = dict(namespaces or {})
        self._created_at = time.time()
        self._frozen = True

    @property
    def set_id(self) -> str:
        """Return the unique set identifier."""
        return self._set_id

    @property
    def created_at(self) -> float:
        """Return the creation timestamp."""
        return self._created_at

    def get(self, ns_type: NamespaceType) -> Optional[Namespace]:
        """Get the namespace for a given type.

        Args:
            ns_type: The namespace type to look up.

        Returns:
            The namespace instance, or None if not set.
        """
        return self._namespaces.get(ns_type)

    def has(self, ns_type: NamespaceType) -> bool:
        """Check if a namespace type is present.

        Args:
            ns_type: The namespace type to check.

        Returns:
            True if the type has a namespace in this set.
        """
        return ns_type in self._namespaces

    @property
    def types(self) -> set[NamespaceType]:
        """Return the set of namespace types present."""
        return set(self._namespaces.keys())

    @property
    def count(self) -> int:
        """Return the number of namespaces in the set."""
        return len(self._namespaces)

    def to_dict(self) -> dict[str, str]:
        """Serialize to a dictionary.

        Returns:
            Dictionary mapping type names to namespace IDs.
        """
        return {
            ns_type.name: ns.ns_id
            for ns_type, ns in self._namespaces.items()
        }

    def get_all(self) -> list[Namespace]:
        """Return all namespaces in the set.

        Returns:
            List of all namespace instances.
        """
        return list(self._namespaces.values())

    def get_clone_flags(self) -> int:
        """Compute the combined clone flags for this set.

        Returns:
            Bitwise OR of all namespace type flags.
        """
        flags = 0
        for ns_type in self._namespaces:
            flags |= ns_type.value
        return flags

    def __contains__(self, ns_type: NamespaceType) -> bool:
        """Check membership using 'in' operator."""
        return ns_type in self._namespaces

    def __len__(self) -> int:
        """Return the number of namespaces."""
        return len(self._namespaces)

    def __iter__(self):
        """Iterate over namespace types."""
        return iter(self._namespaces)

    def __repr__(self) -> str:
        """Return string representation."""
        types = ", ".join(t.name for t in sorted(self._namespaces.keys(), key=lambda t: t.name))
        return f"<NamespaceSet id={self._set_id} types=[{types}]>"


# ══════════════════════════════════════════════════════════════════════
# PIDNamespace
# ══════════════════════════════════════════════════════════════════════


class PIDNamespace(Namespace):
    """PID namespace providing isolated process ID spaces.

    Each PID namespace maintains its own PID allocation table, starting
    from PID 1.  The first process created in a new PID namespace
    becomes the init process (PID 1) for that namespace.  The init
    process has special responsibilities:

      - It inherits orphaned processes within the namespace.
      - If PID 1 exits, all remaining processes in the namespace
        receive SIGKILL, matching the Linux kernel's behavior.
      - It is the only process that cannot be killed by signals
        from within the namespace (unless it installs a handler).

    PID namespaces support hierarchical visibility: a parent PID
    namespace can see processes in child namespaces (mapped to PIDs
    in the parent's PID space), but child namespaces cannot observe
    processes in parent namespaces.  This one-way visibility ensures
    that containerized processes cannot discover or interfere with
    host processes.

    The PID translation table maps namespace-local PIDs to parent-
    namespace PIDs, enabling the hierarchical visibility model.  When
    a process in a child namespace is viewed from the parent, its PID
    is translated to the parent-allocated PID.

    Attributes:
        _pid_table: Maps namespace-local PIDs to process metadata.
        _next_pid: Next PID to allocate.
        _init_pid: PID of the init process (PID 1), or None.
        _pid_to_parent: Maps local PIDs to parent namespace PIDs.
        _parent_to_local: Maps parent PIDs to local PIDs.
        _orphaned_pids: Set of PIDs orphaned by parent process exit.
        _killed_pids: Set of PIDs killed by init exit.
    """

    def __init__(
        self,
        parent: Optional[Namespace] = None,
        ns_id: Optional[str] = None,
    ) -> None:
        """Initialize the PID namespace.

        Args:
            parent: Optional parent PID namespace.
            ns_id: Optional namespace ID.
        """
        super().__init__(NamespaceType.PID, parent=parent, ns_id=ns_id)
        self._pid_table: dict[int, dict[str, Any]] = {}
        self._next_pid = 1
        self._init_pid: Optional[int] = None
        self._pid_to_parent: dict[int, int] = {}
        self._parent_to_local: dict[int, int] = {}
        self._orphaned_pids: set[int] = set()
        self._killed_pids: set[int] = set()
        self._parent_next_pid = 1000  # Start parent PIDs at 1000 for child namespaces
        self._signal_log: list[dict[str, Any]] = []

    @property
    def init_pid(self) -> Optional[int]:
        """Return the init process PID, or None if not set."""
        return self._init_pid

    @property
    def pid_count(self) -> int:
        """Return the number of allocated PIDs."""
        return len(self._pid_table)

    @property
    def orphaned_pids(self) -> set[int]:
        """Return the set of orphaned PIDs."""
        return set(self._orphaned_pids)

    @property
    def killed_pids(self) -> set[int]:
        """Return the set of PIDs killed by init exit."""
        return set(self._killed_pids)

    @property
    def signal_log(self) -> list[dict[str, Any]]:
        """Return the signal delivery log."""
        return list(self._signal_log)

    def allocate_pid(self, process_name: str = "process", parent_pid: Optional[int] = None) -> int:
        """Allocate a new PID in this namespace.

        The first PID allocated is always 1 (init).  Subsequent PIDs
        are allocated sequentially.  If the namespace has a parent PID
        namespace, the process is also assigned a PID in the parent's
        space for hierarchical visibility.

        Args:
            process_name: Human-readable process name.
            parent_pid: Optional parent process PID within this namespace.

        Returns:
            The allocated namespace-local PID.

        Raises:
            PIDNamespaceError: If PID allocation fails.
        """
        if self._state != NamespaceState.ACTIVE:
            raise PIDNamespaceError(
                f"Cannot allocate PID in namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )

        if self._next_pid > MAX_PID:
            raise PIDNamespaceError(
                f"PID space exhausted in namespace {self._ns_id}: "
                f"maximum PID {MAX_PID} reached"
            )

        local_pid = self._next_pid
        self._next_pid += 1

        # Create PID table entry
        entry: dict[str, Any] = {
            "pid": local_pid,
            "process_name": process_name,
            "parent_pid": parent_pid,
            "state": "running",
            "created_at": time.time(),
            "children": [],
        }
        self._pid_table[local_pid] = entry

        # First PID becomes init
        if local_pid == 1:
            self._init_pid = 1
            entry["is_init"] = True
            logger.debug(
                "Init process (PID 1) set in namespace %s: %s",
                self._ns_id,
                process_name,
            )

        # Register parent-child relationship
        if parent_pid is not None and parent_pid in self._pid_table:
            self._pid_table[parent_pid]["children"].append(local_pid)

        # Allocate a PID in the parent namespace for visibility
        if self._parent is not None and isinstance(self._parent, PIDNamespace):
            parent_mapped_pid = self._parent_next_pid
            self._parent_next_pid += 1
            self._pid_to_parent[local_pid] = parent_mapped_pid
            self._parent_to_local[parent_mapped_pid] = local_pid

        # Add to member set
        self._member_pids.add(local_pid)
        self._ref_count += 1

        logger.debug(
            "PID %d allocated in namespace %s: %s",
            local_pid,
            self._ns_id,
            process_name,
        )

        return local_pid

    def deallocate_pid(self, pid: int) -> None:
        """Deallocate a PID and handle orphan adoption.

        When a process exits, its children are orphaned and adopted
        by the init process (PID 1).  If PID 1 itself exits, all
        remaining processes in the namespace receive SIGKILL.

        Args:
            pid: The PID to deallocate.

        Raises:
            PIDNamespaceError: If the PID is not allocated.
        """
        if pid not in self._pid_table:
            raise PIDNamespaceError(
                f"PID {pid} not found in namespace {self._ns_id}"
            )

        entry = self._pid_table[pid]

        # If this is init (PID 1), kill all remaining processes
        if pid == self._init_pid:
            self._handle_init_exit()
            return

        # Orphan children and adopt them to init
        for child_pid in entry.get("children", []):
            if child_pid in self._pid_table:
                self._pid_table[child_pid]["parent_pid"] = self._init_pid
                self._orphaned_pids.add(child_pid)
                if self._init_pid is not None and self._init_pid in self._pid_table:
                    self._pid_table[self._init_pid]["children"].append(child_pid)
                logger.debug(
                    "PID %d orphaned, adopted by init (PID 1) in namespace %s",
                    child_pid,
                    self._ns_id,
                )

        # Remove from parent's children list
        parent_pid = entry.get("parent_pid")
        if parent_pid is not None and parent_pid in self._pid_table:
            parent_entry = self._pid_table[parent_pid]
            if pid in parent_entry["children"]:
                parent_entry["children"].remove(pid)

        # Mark as exited
        entry["state"] = "exited"
        entry["exited_at"] = time.time()

        # Remove from member set
        self._member_pids.discard(pid)
        if self._ref_count > 0:
            self._ref_count -= 1

        # Clean up parent mapping
        if pid in self._pid_to_parent:
            parent_mapped = self._pid_to_parent.pop(pid)
            self._parent_to_local.pop(parent_mapped, None)

        # Remove from PID table
        del self._pid_table[pid]

        logger.debug("PID %d deallocated from namespace %s", pid, self._ns_id)

    def _handle_init_exit(self) -> None:
        """Handle the exit of the init process (PID 1).

        When PID 1 exits, all remaining processes in the namespace
        receive SIGKILL.  This matches the Linux kernel's behavior:
        the init process is the anchor of the PID namespace, and its
        exit triggers namespace teardown.
        """
        logger.debug(
            "Init process (PID 1) exiting in namespace %s, "
            "sending SIGKILL to %d remaining processes",
            self._ns_id,
            len(self._pid_table) - 1,
        )

        # Collect all PIDs except init
        pids_to_kill = [
            pid for pid in list(self._pid_table.keys()) if pid != self._init_pid
        ]

        # Send SIGKILL to all
        for pid in pids_to_kill:
            self._signal_log.append({
                "signal": "SIGKILL",
                "target_pid": pid,
                "source": "init_exit",
                "timestamp": time.time(),
            })
            self._killed_pids.add(pid)
            if pid in self._pid_table:
                self._pid_table[pid]["state"] = "killed"

            # Clean up parent mappings
            if pid in self._pid_to_parent:
                parent_mapped = self._pid_to_parent.pop(pid)
                self._parent_to_local.pop(parent_mapped, None)

            self._member_pids.discard(pid)
            if pid in self._pid_table:
                del self._pid_table[pid]

        # Now remove init itself
        if self._init_pid in self._pid_table:
            self._pid_table[self._init_pid]["state"] = "exited"
            self._pid_table[self._init_pid]["exited_at"] = time.time()
            del self._pid_table[self._init_pid]

        if self._init_pid in self._pid_to_parent:
            parent_mapped = self._pid_to_parent.pop(self._init_pid)
            self._parent_to_local.pop(parent_mapped, None)

        self._member_pids.discard(self._init_pid)
        self._ref_count = 0
        self._init_pid = None

        logger.debug(
            "Namespace %s: init exit complete, %d processes killed",
            self._ns_id,
            len(pids_to_kill),
        )

    def translate_pid_to_parent(self, local_pid: int) -> Optional[int]:
        """Translate a namespace-local PID to the parent namespace PID.

        Args:
            local_pid: PID in this namespace.

        Returns:
            The corresponding PID in the parent namespace, or None.
        """
        return self._pid_to_parent.get(local_pid)

    def translate_pid_from_parent(self, parent_pid: int) -> Optional[int]:
        """Translate a parent namespace PID to this namespace's local PID.

        Args:
            parent_pid: PID in the parent namespace.

        Returns:
            The corresponding local PID, or None.
        """
        return self._parent_to_local.get(parent_pid)

    def get_process_info(self, pid: int) -> Optional[dict[str, Any]]:
        """Get process information for a PID.

        Args:
            pid: The PID to look up.

        Returns:
            Process info dictionary, or None if not found.
        """
        return dict(self._pid_table[pid]) if pid in self._pid_table else None

    def get_children_of(self, pid: int) -> list[int]:
        """Get child PIDs of a process.

        Args:
            pid: The parent PID.

        Returns:
            List of child PIDs.
        """
        if pid in self._pid_table:
            return list(self._pid_table[pid].get("children", []))
        return []

    def get_visible_pids(self) -> set[int]:
        """Get all PIDs visible from this namespace.

        Includes PIDs in this namespace and all descendant namespaces.
        Descendant PIDs are returned as their parent-mapped values.

        Returns:
            Set of visible PIDs.
        """
        visible = set(self._pid_table.keys())

        # Add PIDs from child PID namespaces (mapped to our PID space)
        for child in self._children:
            if isinstance(child, PIDNamespace):
                for local_pid in child._pid_table:
                    parent_pid = child._pid_to_parent.get(local_pid)
                    if parent_pid is not None:
                        visible.add(parent_pid)

        return visible

    def send_signal(self, target_pid: int, signal: str, sender_pid: int = 0) -> bool:
        """Send a signal to a process within this namespace.

        Signals are namespace-scoped: a process can only send signals
        to processes in its own namespace or descendant namespaces.

        Args:
            target_pid: The target PID.
            signal: Signal name (e.g., 'SIGTERM', 'SIGKILL').
            sender_pid: The sending PID.

        Returns:
            True if the signal was delivered.

        Raises:
            PIDNamespaceError: If the target PID is not found.
        """
        if target_pid not in self._pid_table:
            raise PIDNamespaceError(
                f"Cannot send {signal} to PID {target_pid}: "
                f"not found in namespace {self._ns_id}"
            )

        # PID 1 ignores signals it doesn't handle (unless SIGKILL)
        if target_pid == self._init_pid and signal != "SIGKILL":
            self._signal_log.append({
                "signal": signal,
                "target_pid": target_pid,
                "sender_pid": sender_pid,
                "result": "ignored_by_init",
                "timestamp": time.time(),
            })
            return False

        self._signal_log.append({
            "signal": signal,
            "target_pid": target_pid,
            "sender_pid": sender_pid,
            "result": "delivered",
            "timestamp": time.time(),
        })

        if signal == "SIGKILL":
            self.deallocate_pid(target_pid)

        return True

    def get_pid_table_snapshot(self) -> dict[int, dict[str, Any]]:
        """Return a snapshot of the PID table.

        Returns:
            Dictionary mapping PIDs to process info.
        """
        return {pid: dict(info) for pid, info in self._pid_table.items()}

    def isolate(self, pid: int) -> None:
        """Isolate a process within the PID namespace.

        Allocates a new PID for the process in this namespace.

        Args:
            pid: The process ID to isolate.
        """
        self.allocate_pid(process_name=f"process-{pid}", parent_pid=None)

    def enter(self, pid: int) -> None:
        """Enter the PID namespace.

        Args:
            pid: The process ID entering.

        Raises:
            NamespaceEntryError: If the namespace is not active.
        """
        if self._state != NamespaceState.ACTIVE:
            raise NamespaceEntryError(
                f"Cannot enter PID namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )
        self.allocate_pid(process_name=f"entered-{pid}")

    def leave(self, pid: int) -> None:
        """Leave the PID namespace.

        Args:
            pid: The process ID leaving.

        Raises:
            NamespaceLeaveError: If the PID is not a member.
        """
        if pid not in self._pid_table:
            # Try to find by the original PID in member set
            if pid in self._member_pids:
                self._member_pids.discard(pid)
                if self._ref_count > 0:
                    self._ref_count -= 1
                return
            raise NamespaceLeaveError(
                f"PID {pid} is not in PID namespace {self._ns_id}"
            )
        self.deallocate_pid(pid)

    def destroy(self) -> None:
        """Destroy the PID namespace.

        All processes must have exited before destruction.

        Raises:
            NamespaceDestroyError: If processes are still running.
        """
        if self._pid_table:
            raise NamespaceDestroyError(
                f"Cannot destroy PID namespace {self._ns_id}: "
                f"{len(self._pid_table)} processes still running"
            )
        self._state = NamespaceState.DESTROYING

        # Detach from parent
        if self._parent is not None:
            if self in self._parent._children:
                self._parent._children.remove(self)

        self._state = NamespaceState.DESTROYED
        logger.debug("PID namespace %s destroyed", self._ns_id)


# ══════════════════════════════════════════════════════════════════════
# NETNamespace
# ══════════════════════════════════════════════════════════════════════


class NETNamespace(Namespace):
    """NET namespace providing isolated network stacks.

    Each NET namespace has its own set of network interfaces, IP
    addresses, routing table, and socket bindings.  A new NET namespace
    starts with only a loopback interface.  Connectivity to external
    networks requires a virtual ethernet (veth) pair bridging the
    namespace to the host or another namespace.

    Two processes in different NET namespaces can both bind to port 80
    without conflict, because each namespace maintains its own port
    binding table.  This is the mechanism that allows containers to
    expose services on standard ports without requiring port mapping
    at the namespace level (though port mapping is still needed at the
    host level for external access).

    The NET namespace also maintains its own routing table, which
    determines how packets are forwarded within the namespace's
    network stack.  The initial routing table contains only the
    loopback route.

    Attributes:
        _interfaces: Dictionary of network interfaces by name.
        _routing_table: List of routing entries.
        _socket_bindings: List of active socket bindings.
        _veth_pairs: List of veth pairs attached to this namespace.
        _arp_table: ARP table mapping IP addresses to MAC addresses.
    """

    def __init__(
        self,
        parent: Optional[Namespace] = None,
        ns_id: Optional[str] = None,
    ) -> None:
        """Initialize the NET namespace.

        Creates the namespace with a loopback interface (lo) that is
        automatically brought up with the standard loopback addresses.

        Args:
            parent: Optional parent NET namespace.
            ns_id: Optional namespace ID.
        """
        super().__init__(NamespaceType.NET, parent=parent, ns_id=ns_id)
        self._interfaces: dict[str, NetworkInterface] = {}
        self._routing_table: list[RoutingEntry] = []
        self._socket_bindings: list[SocketBinding] = []
        self._veth_pairs: list[VethPair] = []
        self._arp_table: dict[str, str] = {}

        # Create loopback interface
        self._create_loopback()

    def _create_loopback(self) -> None:
        """Create the standard loopback interface.

        Every NET namespace starts with a loopback interface (lo) that
        is automatically brought up.  The loopback interface provides
        connectivity to localhost services within the namespace.
        """
        lo = NetworkInterface(
            name=LOOPBACK_INTERFACE,
            mac_address="00:00:00:00:00:00",
            ipv4_addresses=[LOOPBACK_IPV4],
            ipv6_addresses=[LOOPBACK_IPV6],
            mtu=65536,
            state="up",
        )
        self._interfaces[LOOPBACK_INTERFACE] = lo

        # Add loopback route
        self._routing_table.append(RoutingEntry(
            destination="127.0.0.0/8",
            gateway="127.0.0.1",
            interface=LOOPBACK_INTERFACE,
            metric=0,
            flags="U",
        ))

        logger.debug(
            "Loopback interface created in NET namespace %s",
            self._ns_id,
        )

    @property
    def interfaces(self) -> dict[str, NetworkInterface]:
        """Return the network interfaces."""
        return dict(self._interfaces)

    @property
    def routing_table(self) -> list[RoutingEntry]:
        """Return the routing table."""
        return list(self._routing_table)

    @property
    def socket_bindings(self) -> list[SocketBinding]:
        """Return the socket bindings."""
        return list(self._socket_bindings)

    @property
    def veth_pairs(self) -> list[VethPair]:
        """Return the veth pairs."""
        return list(self._veth_pairs)

    @property
    def arp_table(self) -> dict[str, str]:
        """Return the ARP table."""
        return dict(self._arp_table)

    def add_interface(
        self,
        name: str,
        mac_address: str = "",
        mtu: int = 1500,
    ) -> NetworkInterface:
        """Add a network interface to this namespace.

        Args:
            name: Interface name.
            mac_address: MAC address; auto-generated if empty.
            mtu: Maximum transmission unit.

        Returns:
            The created NetworkInterface.

        Raises:
            NETNamespaceError: If the interface already exists.
        """
        if name in self._interfaces:
            raise NETNamespaceError(
                f"Interface {name} already exists in namespace {self._ns_id}"
            )

        if not mac_address:
            # Generate a deterministic MAC based on namespace and interface name
            mac_hash = hashlib.md5(
                f"{self._ns_id}:{name}".encode()
            ).hexdigest()[:12]
            mac_address = ":".join(
                mac_hash[i:i+2] for i in range(0, 12, 2)
            )

        iface = NetworkInterface(
            name=name,
            mac_address=mac_address,
            mtu=mtu,
            state="down",
        )
        self._interfaces[name] = iface

        logger.debug(
            "Interface %s added to NET namespace %s",
            name,
            self._ns_id,
        )

        return iface

    def remove_interface(self, name: str) -> None:
        """Remove a network interface from this namespace.

        Args:
            name: Interface name to remove.

        Raises:
            NETNamespaceError: If the interface doesn't exist or is loopback.
        """
        if name == LOOPBACK_INTERFACE:
            raise NETNamespaceError(
                f"Cannot remove loopback interface from namespace {self._ns_id}"
            )
        if name not in self._interfaces:
            raise NETNamespaceError(
                f"Interface {name} not found in namespace {self._ns_id}"
            )

        # Remove associated socket bindings
        self._socket_bindings = [
            sb for sb in self._socket_bindings
            if not (sb.address in self._interfaces[name].ipv4_addresses)
        ]

        # Remove associated routes
        self._routing_table = [
            rt for rt in self._routing_table if rt.interface != name
        ]

        del self._interfaces[name]

        logger.debug(
            "Interface %s removed from NET namespace %s",
            name,
            self._ns_id,
        )

    def set_interface_state(self, name: str, state: str) -> None:
        """Set the state of a network interface.

        Args:
            name: Interface name.
            state: New state ('up' or 'down').

        Raises:
            NETNamespaceError: If the interface doesn't exist.
        """
        if name not in self._interfaces:
            raise NETNamespaceError(
                f"Interface {name} not found in namespace {self._ns_id}"
            )
        if state not in ("up", "down"):
            raise NETNamespaceError(
                f"Invalid interface state: {state} (must be 'up' or 'down')"
            )
        self._interfaces[name].state = state

    def assign_ipv4(self, interface_name: str, address: str) -> None:
        """Assign an IPv4 address to an interface.

        Args:
            interface_name: Target interface name.
            address: IPv4 address to assign.

        Raises:
            NETNamespaceError: If the interface doesn't exist.
        """
        if interface_name not in self._interfaces:
            raise NETNamespaceError(
                f"Interface {interface_name} not found in namespace {self._ns_id}"
            )
        iface = self._interfaces[interface_name]
        if address not in iface.ipv4_addresses:
            iface.ipv4_addresses.append(address)

    def assign_ipv6(self, interface_name: str, address: str) -> None:
        """Assign an IPv6 address to an interface.

        Args:
            interface_name: Target interface name.
            address: IPv6 address to assign.

        Raises:
            NETNamespaceError: If the interface doesn't exist.
        """
        if interface_name not in self._interfaces:
            raise NETNamespaceError(
                f"Interface {interface_name} not found in namespace {self._ns_id}"
            )
        iface = self._interfaces[interface_name]
        if address not in iface.ipv6_addresses:
            iface.ipv6_addresses.append(address)

    def add_route(
        self,
        destination: str,
        gateway: str,
        interface: str,
        metric: int = 0,
    ) -> RoutingEntry:
        """Add a routing table entry.

        Args:
            destination: Destination network prefix.
            gateway: Next-hop gateway address.
            interface: Outgoing interface name.
            metric: Route metric.

        Returns:
            The created RoutingEntry.

        Raises:
            NETNamespaceError: If the interface doesn't exist.
        """
        if interface not in self._interfaces:
            raise NETNamespaceError(
                f"Interface {interface} not found in namespace {self._ns_id}"
            )

        entry = RoutingEntry(
            destination=destination,
            gateway=gateway,
            interface=interface,
            metric=metric,
        )
        self._routing_table.append(entry)
        return entry

    def remove_route(self, destination: str) -> None:
        """Remove a routing table entry by destination.

        Args:
            destination: Destination prefix to remove.

        Raises:
            NETNamespaceError: If the route is not found.
        """
        original_len = len(self._routing_table)
        self._routing_table = [
            rt for rt in self._routing_table if rt.destination != destination
        ]
        if len(self._routing_table) == original_len:
            raise NETNamespaceError(
                f"Route to {destination} not found in namespace {self._ns_id}"
            )

    def bind_socket(
        self,
        protocol: str,
        address: str,
        port: int,
        pid: int = 0,
    ) -> SocketBinding:
        """Bind a socket to an address and port.

        Two processes in different NET namespaces can both bind to the
        same port without conflict.

        Args:
            protocol: Protocol type ('tcp', 'udp').
            address: Bind address.
            port: Port number.
            pid: PID of the binding process.

        Returns:
            The created SocketBinding.

        Raises:
            NETNamespaceError: If the port is already bound.
        """
        for existing in self._socket_bindings:
            if (
                existing.protocol == protocol
                and existing.address == address
                and existing.port == port
                and existing.state != "closed"
            ):
                raise NETNamespaceError(
                    f"Port {port}/{protocol} already bound on {address} "
                    f"in namespace {self._ns_id}"
                )

        binding = SocketBinding(
            protocol=protocol,
            address=address,
            port=port,
            state="listening",
            pid=pid,
        )
        self._socket_bindings.append(binding)
        return binding

    def unbind_socket(self, protocol: str, address: str, port: int) -> None:
        """Unbind a socket.

        Args:
            protocol: Protocol type.
            address: Bound address.
            port: Port number.
        """
        for binding in self._socket_bindings:
            if (
                binding.protocol == protocol
                and binding.address == address
                and binding.port == port
            ):
                binding.state = "closed"
                return

        raise NETNamespaceError(
            f"Socket {protocol}://{address}:{port} not found "
            f"in namespace {self._ns_id}"
        )

    def create_veth_pair(
        self,
        peer_namespace: NETNamespace,
        host_name: str = "veth0",
        container_name: str = "eth0",
    ) -> VethPair:
        """Create a virtual ethernet pair between this and another namespace.

        Args:
            peer_namespace: The namespace for the other end.
            host_name: Interface name in this namespace.
            container_name: Interface name in the peer namespace.

        Returns:
            The created VethPair.
        """
        pair = VethPair(
            pair_id=f"veth-{uuid.uuid4().hex[:8]}",
            host_interface=host_name,
            container_interface=container_name,
            host_ns_id=self._ns_id,
            container_ns_id=peer_namespace.ns_id,
        )

        # Add interfaces to both namespaces
        self.add_interface(host_name)
        peer_namespace.add_interface(container_name)

        self._veth_pairs.append(pair)
        peer_namespace._veth_pairs.append(pair)

        logger.debug(
            "Veth pair created: %s(%s) <-> %s(%s)",
            self._ns_id,
            host_name,
            peer_namespace.ns_id,
            container_name,
        )

        return pair

    def get_interface_count(self) -> int:
        """Return the number of interfaces."""
        return len(self._interfaces)

    def get_binding_count(self) -> int:
        """Return the number of active socket bindings."""
        return sum(1 for b in self._socket_bindings if b.state != "closed")

    def isolate(self, pid: int) -> None:
        """Isolate a process within the NET namespace.

        Args:
            pid: The process ID to isolate.
        """
        self.add_member(pid)

    def enter(self, pid: int) -> None:
        """Enter the NET namespace.

        Args:
            pid: The process ID entering.
        """
        if self._state != NamespaceState.ACTIVE:
            raise NamespaceEntryError(
                f"Cannot enter NET namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )
        self.add_member(pid)

    def leave(self, pid: int) -> None:
        """Leave the NET namespace.

        Args:
            pid: The process ID leaving.
        """
        self.remove_member(pid)

    def destroy(self) -> None:
        """Destroy the NET namespace.

        Raises:
            NamespaceDestroyError: If members still exist.
        """
        if self._member_pids:
            raise NamespaceDestroyError(
                f"Cannot destroy NET namespace {self._ns_id}: "
                f"{len(self._member_pids)} members still present"
            )

        self._state = NamespaceState.DESTROYING

        # Clean up interfaces (except loopback which is just data)
        self._interfaces.clear()
        self._routing_table.clear()
        self._socket_bindings.clear()
        self._veth_pairs.clear()
        self._arp_table.clear()

        if self._parent is not None:
            if self in self._parent._children:
                self._parent._children.remove(self)

        self._state = NamespaceState.DESTROYED
        logger.debug("NET namespace %s destroyed", self._ns_id)


# ══════════════════════════════════════════════════════════════════════
# MNTNamespace
# ══════════════════════════════════════════════════════════════════════


class MNTNamespace(Namespace):
    """MNT namespace providing isolated mount tables.

    Each MNT namespace maintains its own mount table.  When a new MNT
    namespace is created, it receives a copy of the parent's mount table.
    Subsequent mount and umount operations within the namespace are
    invisible to the parent and to other namespaces.

    The pivot_root() operation replaces the namespace's root filesystem
    entirely.  This is the mechanism containers use to switch from the
    host's root filesystem to the container's rootfs (typically an
    unpacked OCI image layer).  After pivot_root(), the old root
    becomes accessible at a specified mount point, and the new root
    becomes /.

    Mount propagation controls whether mounts performed in one namespace
    are visible in related namespaces.  The propagation types are:

      - private: Mounts are completely isolated (container default).
      - shared: Mounts propagate bidirectionally.
      - slave: Mounts propagate from master to slave only.
      - unbindable: Like private, but bind mounts are forbidden.

    Attributes:
        _mount_table: List of mount entries.
        _root_path: Current root filesystem path.
        _old_root_path: Previous root after pivot_root.
        _propagation_default: Default propagation type for new mounts.
    """

    def __init__(
        self,
        parent: Optional[Namespace] = None,
        ns_id: Optional[str] = None,
    ) -> None:
        """Initialize the MNT namespace.

        Copies the parent's mount table if a parent is provided.
        Otherwise, creates a default mount table with standard entries.

        Args:
            parent: Optional parent MNT namespace.
            ns_id: Optional namespace ID.
        """
        super().__init__(NamespaceType.MNT, parent=parent, ns_id=ns_id)
        self._mount_table: list[MountEntry] = []
        self._root_path = "/"
        self._old_root_path: Optional[str] = None
        self._propagation_default = "private"

        # Copy parent's mount table or create defaults
        if parent is not None and isinstance(parent, MNTNamespace):
            self._mount_table = list(parent._mount_table)
            self._root_path = parent._root_path
        else:
            self._create_default_mounts()

    def _create_default_mounts(self) -> None:
        """Create the default mount table entries.

        The default mount table mirrors a minimal Linux root filesystem
        with proc, sys, dev, and tmp mounts.
        """
        defaults = [
            ("/", "/dev/sda1", "ext4", "rw,relatime"),
            ("/proc", "proc", "proc", "rw,nosuid,nodev,noexec"),
            ("/sys", "sysfs", "sysfs", "ro,nosuid,nodev,noexec"),
            ("/dev", "devtmpfs", "devtmpfs", "rw,nosuid"),
            ("/dev/pts", "devpts", "devpts", "rw,nosuid,noexec"),
            ("/dev/shm", "shm", "tmpfs", "rw,nosuid,nodev"),
            ("/tmp", "tmpfs", "tmpfs", "rw,nosuid,nodev"),
            ("/run", "tmpfs", "tmpfs", "rw,nosuid,nodev"),
        ]
        for target, source, fs_type, options in defaults:
            self._mount_table.append(MountEntry(
                mount_id=f"mnt-{uuid.uuid4().hex[:8]}",
                source=source,
                target=target,
                fs_type=fs_type,
                options=options,
                propagation=self._propagation_default,
            ))

    @property
    def mount_table(self) -> list[MountEntry]:
        """Return the mount table."""
        return list(self._mount_table)

    @property
    def root_path(self) -> str:
        """Return the current root filesystem path."""
        return self._root_path

    @property
    def old_root_path(self) -> Optional[str]:
        """Return the old root path after pivot_root."""
        return self._old_root_path

    @property
    def mount_count(self) -> int:
        """Return the number of mounts."""
        return len(self._mount_table)

    def mount(
        self,
        source: str,
        target: str,
        fs_type: str,
        options: str = "rw",
        propagation: Optional[str] = None,
    ) -> MountEntry:
        """Mount a filesystem at the specified mount point.

        Args:
            source: Source device or filesystem path.
            target: Mount point path.
            fs_type: Filesystem type.
            options: Mount options.
            propagation: Propagation type; uses default if not specified.

        Returns:
            The created MountEntry.

        Raises:
            MNTNamespaceError: If the mount fails.
        """
        if self._state != NamespaceState.ACTIVE:
            raise MNTNamespaceError(
                f"Cannot mount in namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )

        prop = propagation or self._propagation_default
        if prop not in ("private", "shared", "slave", "unbindable"):
            raise MNTNamespaceError(
                f"Invalid propagation type: {prop}"
            )

        entry = MountEntry(
            mount_id=f"mnt-{uuid.uuid4().hex[:8]}",
            source=source,
            target=target,
            fs_type=fs_type,
            options=options,
            propagation=prop,
        )
        self._mount_table.append(entry)

        logger.debug(
            "Mounted %s on %s (type=%s) in namespace %s",
            source,
            target,
            fs_type,
            self._ns_id,
        )

        return entry

    def umount(self, target: str) -> None:
        """Unmount the filesystem at the specified mount point.

        Args:
            target: Mount point to unmount.

        Raises:
            MNTNamespaceError: If the mount point is not found.
        """
        if self._state != NamespaceState.ACTIVE:
            raise MNTNamespaceError(
                f"Cannot umount in namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )

        original_len = len(self._mount_table)
        self._mount_table = [
            m for m in self._mount_table if m.target != target
        ]
        if len(self._mount_table) == original_len:
            raise MNTNamespaceError(
                f"Mount point {target} not found in namespace {self._ns_id}"
            )

        logger.debug(
            "Unmounted %s in namespace %s",
            target,
            self._ns_id,
        )

    def pivot_root(self, new_root: str, put_old: str) -> None:
        """Replace the root filesystem.

        Implements pivot_root(2) semantics: the current root is moved
        to put_old, and new_root becomes the new root filesystem.

        Args:
            new_root: Path to the new root filesystem.
            put_old: Path where the old root will be mounted.

        Raises:
            MNTNamespaceError: If the pivot_root operation fails.
        """
        if self._state != NamespaceState.ACTIVE:
            raise MNTNamespaceError(
                f"Cannot pivot_root in namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )

        if not new_root:
            raise MNTNamespaceError("new_root path cannot be empty")
        if not put_old:
            raise MNTNamespaceError("put_old path cannot be empty")

        self._old_root_path = self._root_path
        self._root_path = new_root

        # Add mount entry for old root
        self._mount_table.append(MountEntry(
            mount_id=f"mnt-{uuid.uuid4().hex[:8]}",
            source=self._old_root_path,
            target=put_old,
            fs_type="bind",
            options="rw",
            propagation="private",
        ))

        # Add mount entry for new root
        self._mount_table.append(MountEntry(
            mount_id=f"mnt-{uuid.uuid4().hex[:8]}",
            source=new_root,
            target="/",
            fs_type="bind",
            options="rw",
            propagation="private",
        ))

        logger.debug(
            "pivot_root in namespace %s: new_root=%s, put_old=%s",
            self._ns_id,
            new_root,
            put_old,
        )

    def find_mount(self, target: str) -> Optional[MountEntry]:
        """Find a mount entry by target path.

        Args:
            target: Mount point path to search for.

        Returns:
            The MountEntry if found, None otherwise.
        """
        for entry in self._mount_table:
            if entry.target == target:
                return entry
        return None

    def get_mounts_by_type(self, fs_type: str) -> list[MountEntry]:
        """Get all mounts of a given filesystem type.

        Args:
            fs_type: Filesystem type to filter by.

        Returns:
            List of matching mount entries.
        """
        return [m for m in self._mount_table if m.fs_type == fs_type]

    def set_propagation(self, target: str, propagation: str) -> None:
        """Set the propagation type for a mount point.

        Args:
            target: Mount point path.
            propagation: New propagation type.

        Raises:
            MNTNamespaceError: If the mount point is not found.
        """
        if propagation not in ("private", "shared", "slave", "unbindable"):
            raise MNTNamespaceError(f"Invalid propagation type: {propagation}")

        for i, entry in enumerate(self._mount_table):
            if entry.target == target:
                # MountEntry is frozen, so replace it
                self._mount_table[i] = MountEntry(
                    mount_id=entry.mount_id,
                    source=entry.source,
                    target=entry.target,
                    fs_type=entry.fs_type,
                    options=entry.options,
                    propagation=propagation,
                    created_at=entry.created_at,
                )
                return

        raise MNTNamespaceError(
            f"Mount point {target} not found in namespace {self._ns_id}"
        )

    def isolate(self, pid: int) -> None:
        """Isolate a process within the MNT namespace.

        Args:
            pid: The process ID to isolate.
        """
        self.add_member(pid)

    def enter(self, pid: int) -> None:
        """Enter the MNT namespace.

        Args:
            pid: The process ID entering.
        """
        if self._state != NamespaceState.ACTIVE:
            raise NamespaceEntryError(
                f"Cannot enter MNT namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )
        self.add_member(pid)

    def leave(self, pid: int) -> None:
        """Leave the MNT namespace.

        Args:
            pid: The process ID leaving.
        """
        self.remove_member(pid)

    def destroy(self) -> None:
        """Destroy the MNT namespace.

        Raises:
            NamespaceDestroyError: If members still exist.
        """
        if self._member_pids:
            raise NamespaceDestroyError(
                f"Cannot destroy MNT namespace {self._ns_id}: "
                f"{len(self._member_pids)} members still present"
            )

        self._state = NamespaceState.DESTROYING
        self._mount_table.clear()

        if self._parent is not None:
            if self in self._parent._children:
                self._parent._children.remove(self)

        self._state = NamespaceState.DESTROYED
        logger.debug("MNT namespace %s destroyed", self._ns_id)


# ══════════════════════════════════════════════════════════════════════
# UTSNamespace
# ══════════════════════════════════════════════════════════════════════


class UTSNamespace(Namespace):
    """UTS namespace providing isolated hostname and domain name.

    UTS (Unix Timesharing System) namespaces isolate two system
    identifiers: the hostname and the NIS domain name.  Each UTS
    namespace has its own values for these identifiers, allowing
    containers to set their hostname without affecting the host
    or other containers.

    The hostname is typically the container's short name or ID.
    The domain name is used for NIS (Network Information Service)
    domain resolution.  Both are namespace-scoped: gethostname()
    and getdomainname() return the values for the calling process's
    UTS namespace.

    Attributes:
        _hostname: The namespace's hostname.
        _domainname: The namespace's domain name.
        _hostname_history: List of previous hostname values.
    """

    def __init__(
        self,
        hostname: str = DEFAULT_HOSTNAME,
        domainname: str = DEFAULT_DOMAINNAME,
        parent: Optional[Namespace] = None,
        ns_id: Optional[str] = None,
    ) -> None:
        """Initialize the UTS namespace.

        Args:
            hostname: Initial hostname.
            domainname: Initial domain name.
            parent: Optional parent UTS namespace.
            ns_id: Optional namespace ID.
        """
        super().__init__(NamespaceType.UTS, parent=parent, ns_id=ns_id)
        self._hostname = hostname
        self._domainname = domainname
        self._hostname_history: list[dict[str, Any]] = [
            {"hostname": hostname, "timestamp": time.time(), "action": "initial"},
        ]

    @property
    def hostname(self) -> str:
        """Return the current hostname."""
        return self._hostname

    @property
    def domainname(self) -> str:
        """Return the current domain name."""
        return self._domainname

    @property
    def hostname_history(self) -> list[dict[str, Any]]:
        """Return the hostname change history."""
        return list(self._hostname_history)

    def sethostname(self, hostname: str) -> None:
        """Set the hostname for this namespace.

        Args:
            hostname: The new hostname.

        Raises:
            UTSNamespaceError: If the hostname is invalid.
        """
        if not hostname:
            raise UTSNamespaceError("Hostname cannot be empty")
        if len(hostname) > 64:
            raise UTSNamespaceError(
                f"Hostname exceeds maximum length of 64 characters: "
                f"{len(hostname)}"
            )
        if self._state != NamespaceState.ACTIVE:
            raise UTSNamespaceError(
                f"Cannot set hostname in namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )

        old_hostname = self._hostname
        self._hostname = hostname
        self._hostname_history.append({
            "hostname": hostname,
            "previous": old_hostname,
            "timestamp": time.time(),
            "action": "sethostname",
        })

        logger.debug(
            "Hostname set to %s in UTS namespace %s (was %s)",
            hostname,
            self._ns_id,
            old_hostname,
        )

    def setdomainname(self, domainname: str) -> None:
        """Set the domain name for this namespace.

        Args:
            domainname: The new domain name.

        Raises:
            UTSNamespaceError: If the domain name is invalid.
        """
        if self._state != NamespaceState.ACTIVE:
            raise UTSNamespaceError(
                f"Cannot set domainname in namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )
        if len(domainname) > 64:
            raise UTSNamespaceError(
                f"Domain name exceeds maximum length of 64 characters: "
                f"{len(domainname)}"
            )

        self._domainname = domainname

        logger.debug(
            "Domain name set to %s in UTS namespace %s",
            domainname,
            self._ns_id,
        )

    def gethostname(self) -> str:
        """Get the hostname (namespace-scoped).

        Returns:
            The namespace's hostname.
        """
        return self._hostname

    def getdomainname(self) -> str:
        """Get the domain name (namespace-scoped).

        Returns:
            The namespace's domain name.
        """
        return self._domainname

    def isolate(self, pid: int) -> None:
        """Isolate a process within the UTS namespace.

        Args:
            pid: The process ID to isolate.
        """
        self.add_member(pid)

    def enter(self, pid: int) -> None:
        """Enter the UTS namespace.

        Args:
            pid: The process ID entering.
        """
        if self._state != NamespaceState.ACTIVE:
            raise NamespaceEntryError(
                f"Cannot enter UTS namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )
        self.add_member(pid)

    def leave(self, pid: int) -> None:
        """Leave the UTS namespace.

        Args:
            pid: The process ID leaving.
        """
        self.remove_member(pid)

    def destroy(self) -> None:
        """Destroy the UTS namespace.

        Raises:
            NamespaceDestroyError: If members still exist.
        """
        if self._member_pids:
            raise NamespaceDestroyError(
                f"Cannot destroy UTS namespace {self._ns_id}: "
                f"{len(self._member_pids)} members still present"
            )

        self._state = NamespaceState.DESTROYING

        if self._parent is not None:
            if self in self._parent._children:
                self._parent._children.remove(self)

        self._state = NamespaceState.DESTROYED
        logger.debug("UTS namespace %s destroyed", self._ns_id)


# ══════════════════════════════════════════════════════════════════════
# IPCNamespace
# ══════════════════════════════════════════════════════════════════════


class IPCNamespace(Namespace):
    """IPC namespace providing isolated System V IPC resources.

    Each IPC namespace has its own identifier space for three types
    of System V IPC objects:

      - Shared memory segments (shmget/shmat/shmdt/shmctl)
      - Semaphore sets (semget/semop/semctl)
      - Message queues (msgget/msgsnd/msgrcv/msgctl)

    IPC objects created in one namespace are invisible to processes
    in other namespaces, even if the numeric IPC ID is the same.
    This prevents inter-container information leakage through shared
    memory or IPC channels.

    POSIX message queues (mq_open, etc.) are also scoped to the
    IPC namespace, providing complete isolation of all inter-process
    communication primitives.

    Attributes:
        _shm_segments: Dictionary of shared memory segments by ID.
        _semaphore_sets: Dictionary of semaphore sets by ID.
        _message_queues: Dictionary of message queues by ID.
        _next_shm_id: Next shared memory segment ID.
        _next_sem_id: Next semaphore set ID.
        _next_msq_id: Next message queue ID.
    """

    def __init__(
        self,
        parent: Optional[Namespace] = None,
        ns_id: Optional[str] = None,
    ) -> None:
        """Initialize the IPC namespace.

        Args:
            parent: Optional parent IPC namespace.
            ns_id: Optional namespace ID.
        """
        super().__init__(NamespaceType.IPC, parent=parent, ns_id=ns_id)
        self._shm_segments: dict[int, SHMSegment] = {}
        self._semaphore_sets: dict[int, SemaphoreSet] = {}
        self._message_queues: dict[int, MessageQueue] = {}
        self._next_shm_id = 0
        self._next_sem_id = 0
        self._next_msq_id = 0

    @property
    def shm_segments(self) -> dict[int, SHMSegment]:
        """Return the shared memory segments."""
        return dict(self._shm_segments)

    @property
    def semaphore_sets(self) -> dict[int, SemaphoreSet]:
        """Return the semaphore sets."""
        return dict(self._semaphore_sets)

    @property
    def message_queues(self) -> dict[int, MessageQueue]:
        """Return the message queues."""
        return dict(self._message_queues)

    @property
    def shm_count(self) -> int:
        """Return the number of shared memory segments."""
        return len(self._shm_segments)

    @property
    def sem_count(self) -> int:
        """Return the number of semaphore sets."""
        return len(self._semaphore_sets)

    @property
    def msq_count(self) -> int:
        """Return the number of message queues."""
        return len(self._message_queues)

    def shmget(self, key: int, size: int, owner_pid: int = 0) -> int:
        """Create or access a shared memory segment.

        Args:
            key: IPC key.
            size: Segment size in bytes.
            owner_pid: PID of the creating process.

        Returns:
            The shared memory segment ID.

        Raises:
            IPCNamespaceError: If creation fails.
        """
        if self._state != NamespaceState.ACTIVE:
            raise IPCNamespaceError(
                f"Cannot create SHM in namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )

        if len(self._shm_segments) >= MAX_SHM_SEGMENTS:
            raise IPCNamespaceError(
                f"SHM segment limit reached in namespace {self._ns_id}: "
                f"maximum {MAX_SHM_SEGMENTS}"
            )

        # Check if key already exists
        for seg in self._shm_segments.values():
            if seg.key == key:
                return seg.shm_id

        shm_id = self._next_shm_id
        self._next_shm_id += 1

        segment = SHMSegment(
            shm_id=shm_id,
            key=key,
            size=size,
            owner_pid=owner_pid,
        )
        self._shm_segments[shm_id] = segment

        logger.debug(
            "SHM segment %d created in IPC namespace %s (key=%d, size=%d)",
            shm_id,
            self._ns_id,
            key,
            size,
        )

        return shm_id

    def shmctl_rm(self, shm_id: int) -> None:
        """Remove a shared memory segment.

        Args:
            shm_id: Segment ID to remove.

        Raises:
            IPCNamespaceError: If the segment is not found.
        """
        if shm_id not in self._shm_segments:
            raise IPCNamespaceError(
                f"SHM segment {shm_id} not found in namespace {self._ns_id}"
            )
        del self._shm_segments[shm_id]

    def shmat(self, shm_id: int, pid: int) -> None:
        """Attach a process to a shared memory segment.

        Args:
            shm_id: Segment ID.
            pid: PID to attach.

        Raises:
            IPCNamespaceError: If the segment is not found.
        """
        if shm_id not in self._shm_segments:
            raise IPCNamespaceError(
                f"SHM segment {shm_id} not found in namespace {self._ns_id}"
            )
        self._shm_segments[shm_id].attached_pids.add(pid)

    def shmdt(self, shm_id: int, pid: int) -> None:
        """Detach a process from a shared memory segment.

        Args:
            shm_id: Segment ID.
            pid: PID to detach.

        Raises:
            IPCNamespaceError: If the segment is not found.
        """
        if shm_id not in self._shm_segments:
            raise IPCNamespaceError(
                f"SHM segment {shm_id} not found in namespace {self._ns_id}"
            )
        self._shm_segments[shm_id].attached_pids.discard(pid)

    def semget(self, key: int, num_sems: int, owner_pid: int = 0) -> int:
        """Create or access a semaphore set.

        Args:
            key: IPC key.
            num_sems: Number of semaphores in the set.
            owner_pid: PID of the creating process.

        Returns:
            The semaphore set ID.

        Raises:
            IPCNamespaceError: If creation fails.
        """
        if self._state != NamespaceState.ACTIVE:
            raise IPCNamespaceError(
                f"Cannot create semaphore set in namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )

        if len(self._semaphore_sets) >= MAX_SEMAPHORE_SETS:
            raise IPCNamespaceError(
                f"Semaphore set limit reached in namespace {self._ns_id}: "
                f"maximum {MAX_SEMAPHORE_SETS}"
            )

        # Check if key already exists
        for sem_set in self._semaphore_sets.values():
            if sem_set.key == key:
                return sem_set.sem_id

        sem_id = self._next_sem_id
        self._next_sem_id += 1

        sem_set = SemaphoreSet(
            sem_id=sem_id,
            key=key,
            num_sems=num_sems,
            owner_pid=owner_pid,
        )
        self._semaphore_sets[sem_id] = sem_set

        return sem_id

    def semctl_rm(self, sem_id: int) -> None:
        """Remove a semaphore set.

        Args:
            sem_id: Semaphore set ID to remove.

        Raises:
            IPCNamespaceError: If the set is not found.
        """
        if sem_id not in self._semaphore_sets:
            raise IPCNamespaceError(
                f"Semaphore set {sem_id} not found in namespace {self._ns_id}"
            )
        del self._semaphore_sets[sem_id]

    def msgget(self, key: int, max_bytes: int = 16384, owner_pid: int = 0) -> int:
        """Create or access a message queue.

        Args:
            key: IPC key.
            max_bytes: Maximum queue size in bytes.
            owner_pid: PID of the creating process.

        Returns:
            The message queue ID.

        Raises:
            IPCNamespaceError: If creation fails.
        """
        if self._state != NamespaceState.ACTIVE:
            raise IPCNamespaceError(
                f"Cannot create message queue in namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )

        if len(self._message_queues) >= MAX_MSG_QUEUES:
            raise IPCNamespaceError(
                f"Message queue limit reached in namespace {self._ns_id}: "
                f"maximum {MAX_MSG_QUEUES}"
            )

        # Check if key already exists
        for queue in self._message_queues.values():
            if queue.key == key:
                return queue.msq_id

        msq_id = self._next_msq_id
        self._next_msq_id += 1

        queue = MessageQueue(
            msq_id=msq_id,
            key=key,
            max_bytes=max_bytes,
            owner_pid=owner_pid,
        )
        self._message_queues[msq_id] = queue

        return msq_id

    def msgctl_rm(self, msq_id: int) -> None:
        """Remove a message queue.

        Args:
            msq_id: Message queue ID to remove.

        Raises:
            IPCNamespaceError: If the queue is not found.
        """
        if msq_id not in self._message_queues:
            raise IPCNamespaceError(
                f"Message queue {msq_id} not found in namespace {self._ns_id}"
            )
        del self._message_queues[msq_id]

    def msgsnd(self, msq_id: int) -> None:
        """Send a message to a queue.

        Args:
            msq_id: Target queue ID.

        Raises:
            IPCNamespaceError: If the queue is not found.
        """
        if msq_id not in self._message_queues:
            raise IPCNamespaceError(
                f"Message queue {msq_id} not found in namespace {self._ns_id}"
            )
        self._message_queues[msq_id].message_count += 1

    def msgrcv(self, msq_id: int) -> None:
        """Receive a message from a queue.

        Args:
            msq_id: Source queue ID.

        Raises:
            IPCNamespaceError: If the queue is not found or empty.
        """
        if msq_id not in self._message_queues:
            raise IPCNamespaceError(
                f"Message queue {msq_id} not found in namespace {self._ns_id}"
            )
        queue = self._message_queues[msq_id]
        if queue.message_count <= 0:
            raise IPCNamespaceError(
                f"Message queue {msq_id} is empty in namespace {self._ns_id}"
            )
        queue.message_count -= 1

    def get_total_ipc_objects(self) -> int:
        """Return the total number of IPC objects."""
        return self.shm_count + self.sem_count + self.msq_count

    def isolate(self, pid: int) -> None:
        """Isolate a process within the IPC namespace.

        Args:
            pid: The process ID to isolate.
        """
        self.add_member(pid)

    def enter(self, pid: int) -> None:
        """Enter the IPC namespace.

        Args:
            pid: The process ID entering.
        """
        if self._state != NamespaceState.ACTIVE:
            raise NamespaceEntryError(
                f"Cannot enter IPC namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )
        self.add_member(pid)

    def leave(self, pid: int) -> None:
        """Leave the IPC namespace.

        Args:
            pid: The process ID leaving.
        """
        self.remove_member(pid)

    def destroy(self) -> None:
        """Destroy the IPC namespace.

        Raises:
            NamespaceDestroyError: If members still exist.
        """
        if self._member_pids:
            raise NamespaceDestroyError(
                f"Cannot destroy IPC namespace {self._ns_id}: "
                f"{len(self._member_pids)} members still present"
            )

        self._state = NamespaceState.DESTROYING

        self._shm_segments.clear()
        self._semaphore_sets.clear()
        self._message_queues.clear()

        if self._parent is not None:
            if self in self._parent._children:
                self._parent._children.remove(self)

        self._state = NamespaceState.DESTROYED
        logger.debug("IPC namespace %s destroyed", self._ns_id)


# ══════════════════════════════════════════════════════════════════════
# USERNamespace
# ══════════════════════════════════════════════════════════════════════


class USERNamespace(Namespace):
    """USER namespace providing UID/GID mapping and capability isolation.

    USER namespaces map UIDs and GIDs between the namespace and its
    parent, enabling rootless container operation.  A process can be
    root (UID 0) inside a USER namespace while being an unprivileged
    user on the host.  This is the foundation of rootless containers:
    no host root privileges are required to create or operate within
    a USER namespace.

    The UID/GID mappings are defined by uid_map and gid_map entries,
    following the same format as /proc/[pid]/uid_map and
    /proc/[pid]/gid_map in the Linux kernel.  Each entry maps a
    contiguous range of IDs from the namespace to the parent.

    Capability bounding sets are namespace-scoped: a process gains
    the full capability set inside its USER namespace but retains
    only the capabilities corresponding to its mapped UID in the
    parent namespace.  This allows container processes to perform
    privileged operations (mount, network configuration, etc.)
    within their namespace without affecting the host.

    Attributes:
        _uid_map: List of UID mappings.
        _gid_map: List of GID mappings.
        _capabilities: Set of capabilities in the bounding set.
        _is_rootless: Whether this is a rootless namespace.
        _owner_uid: Host UID of the namespace owner.
        _owner_gid: Host GID of the namespace owner.
    """

    # Standard Linux capabilities
    ALL_CAPABILITIES = frozenset({
        "CAP_CHOWN", "CAP_DAC_OVERRIDE", "CAP_DAC_READ_SEARCH",
        "CAP_FOWNER", "CAP_FSETID", "CAP_KILL", "CAP_SETGID",
        "CAP_SETUID", "CAP_SETPCAP", "CAP_LINUX_IMMUTABLE",
        "CAP_NET_BIND_SERVICE", "CAP_NET_BROADCAST", "CAP_NET_ADMIN",
        "CAP_NET_RAW", "CAP_IPC_LOCK", "CAP_IPC_OWNER",
        "CAP_SYS_MODULE", "CAP_SYS_RAWIO", "CAP_SYS_CHROOT",
        "CAP_SYS_PTRACE", "CAP_SYS_PACCT", "CAP_SYS_ADMIN",
        "CAP_SYS_BOOT", "CAP_SYS_NICE", "CAP_SYS_RESOURCE",
        "CAP_SYS_TIME", "CAP_SYS_TTY_CONFIG", "CAP_MKNOD",
        "CAP_LEASE", "CAP_AUDIT_WRITE", "CAP_AUDIT_CONTROL",
        "CAP_SETFCAP", "CAP_MAC_OVERRIDE", "CAP_MAC_ADMIN",
        "CAP_SYSLOG", "CAP_WAKE_ALARM", "CAP_BLOCK_SUSPEND",
        "CAP_AUDIT_READ", "CAP_PERFMON", "CAP_BPF",
        "CAP_CHECKPOINT_RESTORE",
    })

    def __init__(
        self,
        owner_uid: int = 1000,
        owner_gid: int = 1000,
        parent: Optional[Namespace] = None,
        ns_id: Optional[str] = None,
    ) -> None:
        """Initialize the USER namespace.

        Args:
            owner_uid: Host UID of the namespace owner.
            owner_gid: Host GID of the namespace owner.
            parent: Optional parent USER namespace.
            ns_id: Optional namespace ID.
        """
        super().__init__(NamespaceType.USER, parent=parent, ns_id=ns_id)
        self._uid_map: list[UIDMapping] = []
        self._gid_map: list[GIDMapping] = []
        self._capabilities: set[str] = set(self.ALL_CAPABILITIES)
        self._is_rootless = owner_uid != ROOT_UID
        self._owner_uid = owner_uid
        self._owner_gid = owner_gid

    @property
    def uid_map(self) -> list[UIDMapping]:
        """Return the UID mappings."""
        return list(self._uid_map)

    @property
    def gid_map(self) -> list[GIDMapping]:
        """Return the GID mappings."""
        return list(self._gid_map)

    @property
    def capabilities(self) -> set[str]:
        """Return the capability bounding set."""
        return set(self._capabilities)

    @property
    def is_rootless(self) -> bool:
        """Return whether this is a rootless namespace."""
        return self._is_rootless

    @property
    def owner_uid(self) -> int:
        """Return the host UID of the namespace owner."""
        return self._owner_uid

    @property
    def owner_gid(self) -> int:
        """Return the host GID of the namespace owner."""
        return self._owner_gid

    def add_uid_mapping(
        self,
        inner_start: int,
        outer_start: int,
        count: int,
    ) -> None:
        """Add a UID mapping entry.

        Args:
            inner_start: Starting UID inside the namespace.
            outer_start: Starting UID in the parent namespace.
            count: Number of UIDs in the range.

        Raises:
            USERNamespaceError: If the mapping is invalid.
        """
        if count <= 0:
            raise USERNamespaceError("UID mapping count must be positive")
        if len(self._uid_map) >= MAX_UID_MAP_ENTRIES:
            raise USERNamespaceError(
                f"UID map entry limit reached: maximum {MAX_UID_MAP_ENTRIES}"
            )

        # Check for overlapping ranges
        for existing in self._uid_map:
            if (inner_start < existing.inner_start + existing.count and
                    inner_start + count > existing.inner_start):
                raise USERNamespaceError(
                    f"UID mapping range [{inner_start}, {inner_start + count}) "
                    f"overlaps with existing range "
                    f"[{existing.inner_start}, {existing.inner_start + existing.count})"
                )

        mapping = UIDMapping(
            inner_start=inner_start,
            outer_start=outer_start,
            count=count,
        )
        self._uid_map.append(mapping)

        logger.debug(
            "UID mapping added in USER namespace %s: %d-%d -> %d-%d",
            self._ns_id,
            inner_start,
            inner_start + count - 1,
            outer_start,
            outer_start + count - 1,
        )

    def add_gid_mapping(
        self,
        inner_start: int,
        outer_start: int,
        count: int,
    ) -> None:
        """Add a GID mapping entry.

        Args:
            inner_start: Starting GID inside the namespace.
            outer_start: Starting GID in the parent namespace.
            count: Number of GIDs in the range.

        Raises:
            USERNamespaceError: If the mapping is invalid.
        """
        if count <= 0:
            raise USERNamespaceError("GID mapping count must be positive")
        if len(self._gid_map) >= MAX_GID_MAP_ENTRIES:
            raise USERNamespaceError(
                f"GID map entry limit reached: maximum {MAX_GID_MAP_ENTRIES}"
            )

        # Check for overlapping ranges
        for existing in self._gid_map:
            if (inner_start < existing.inner_start + existing.count and
                    inner_start + count > existing.inner_start):
                raise USERNamespaceError(
                    f"GID mapping range [{inner_start}, {inner_start + count}) "
                    f"overlaps with existing range "
                    f"[{existing.inner_start}, {existing.inner_start + existing.count})"
                )

        mapping = GIDMapping(
            inner_start=inner_start,
            outer_start=outer_start,
            count=count,
        )
        self._gid_map.append(mapping)

        logger.debug(
            "GID mapping added in USER namespace %s: %d-%d -> %d-%d",
            self._ns_id,
            inner_start,
            inner_start + count - 1,
            outer_start,
            outer_start + count - 1,
        )

    def translate_uid_to_host(self, inner_uid: int) -> int:
        """Translate a namespace UID to the host UID.

        Args:
            inner_uid: UID inside the namespace.

        Returns:
            The corresponding host UID, or NOBODY_UID if unmapped.
        """
        for mapping in self._uid_map:
            if mapping.inner_start <= inner_uid < mapping.inner_start + mapping.count:
                offset = inner_uid - mapping.inner_start
                return mapping.outer_start + offset
        return NOBODY_UID

    def translate_uid_from_host(self, outer_uid: int) -> int:
        """Translate a host UID to the namespace UID.

        Args:
            outer_uid: UID on the host.

        Returns:
            The corresponding namespace UID, or NOBODY_UID if unmapped.
        """
        for mapping in self._uid_map:
            if mapping.outer_start <= outer_uid < mapping.outer_start + mapping.count:
                offset = outer_uid - mapping.outer_start
                return mapping.inner_start + offset
        return NOBODY_UID

    def translate_gid_to_host(self, inner_gid: int) -> int:
        """Translate a namespace GID to the host GID.

        Args:
            inner_gid: GID inside the namespace.

        Returns:
            The corresponding host GID, or NOBODY_GID if unmapped.
        """
        for mapping in self._gid_map:
            if mapping.inner_start <= inner_gid < mapping.inner_start + mapping.count:
                offset = inner_gid - mapping.inner_start
                return mapping.outer_start + offset
        return NOBODY_GID

    def translate_gid_from_host(self, outer_gid: int) -> int:
        """Translate a host GID to the namespace GID.

        Args:
            outer_gid: GID on the host.

        Returns:
            The corresponding namespace GID, or NOBODY_GID if unmapped.
        """
        for mapping in self._gid_map:
            if mapping.outer_start <= outer_gid < mapping.outer_start + mapping.count:
                offset = outer_gid - mapping.outer_start
                return mapping.inner_start + offset
        return NOBODY_GID

    def has_capability(self, capability: str) -> bool:
        """Check if a capability is in the bounding set.

        Args:
            capability: Capability name (e.g., 'CAP_NET_ADMIN').

        Returns:
            True if the capability is present.
        """
        return capability in self._capabilities

    def drop_capability(self, capability: str) -> None:
        """Drop a capability from the bounding set.

        Args:
            capability: Capability to drop.

        Raises:
            USERNamespaceError: If the capability is not recognized.
        """
        if capability not in self.ALL_CAPABILITIES:
            raise USERNamespaceError(
                f"Unknown capability: {capability}"
            )
        self._capabilities.discard(capability)

    def add_capability(self, capability: str) -> None:
        """Add a capability to the bounding set.

        Args:
            capability: Capability to add.

        Raises:
            USERNamespaceError: If the capability is not recognized.
        """
        if capability not in self.ALL_CAPABILITIES:
            raise USERNamespaceError(
                f"Unknown capability: {capability}"
            )
        self._capabilities.add(capability)

    def set_rootless(self) -> None:
        """Configure this namespace for rootless operation.

        Sets up default UID/GID mappings for rootless containers:
        UID 0 inside maps to the owner UID on the host.
        """
        if not self._uid_map:
            self.add_uid_mapping(0, self._owner_uid, 1)
        if not self._gid_map:
            self.add_gid_mapping(0, self._owner_gid, 1)
        self._is_rootless = True

    def get_effective_uid(self, inner_uid: int) -> dict[str, Any]:
        """Get the effective UID information.

        Args:
            inner_uid: UID inside the namespace.

        Returns:
            Dictionary with inner_uid, outer_uid, and is_root.
        """
        outer_uid = self.translate_uid_to_host(inner_uid)
        return {
            "inner_uid": inner_uid,
            "outer_uid": outer_uid,
            "is_root_inside": inner_uid == ROOT_UID,
            "is_root_outside": outer_uid == ROOT_UID,
            "is_mapped": outer_uid != NOBODY_UID,
        }

    def isolate(self, pid: int) -> None:
        """Isolate a process within the USER namespace.

        Args:
            pid: The process ID to isolate.
        """
        self.add_member(pid)

    def enter(self, pid: int) -> None:
        """Enter the USER namespace.

        Args:
            pid: The process ID entering.
        """
        if self._state != NamespaceState.ACTIVE:
            raise NamespaceEntryError(
                f"Cannot enter USER namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )
        self.add_member(pid)

    def leave(self, pid: int) -> None:
        """Leave the USER namespace.

        Args:
            pid: The process ID leaving.
        """
        self.remove_member(pid)

    def destroy(self) -> None:
        """Destroy the USER namespace.

        Raises:
            NamespaceDestroyError: If members still exist.
        """
        if self._member_pids:
            raise NamespaceDestroyError(
                f"Cannot destroy USER namespace {self._ns_id}: "
                f"{len(self._member_pids)} members still present"
            )

        self._state = NamespaceState.DESTROYING

        self._uid_map.clear()
        self._gid_map.clear()
        self._capabilities.clear()

        if self._parent is not None:
            if self in self._parent._children:
                self._parent._children.remove(self)

        self._state = NamespaceState.DESTROYED
        logger.debug("USER namespace %s destroyed", self._ns_id)


# ══════════════════════════════════════════════════════════════════════
# CGROUPNamespace
# ══════════════════════════════════════════════════════════════════════


class CGROUPNamespace(Namespace):
    """CGROUP namespace providing virtualized cgroup hierarchy views.

    CGROUP namespaces virtualize the cgroup hierarchy so that a process
    inside the namespace sees its own cgroup as the root.  This prevents
    containers from discovering the host's cgroup tree structure, which
    could leak information about other containers or the host's resource
    organization.

    When a CGROUP namespace is created, the creating process's current
    cgroup becomes the root of the namespace's virtualized view.  All
    cgroup paths within the namespace are relative to this root.

    For example, if a container's cgroup is /sys/fs/cgroup/docker/abc123,
    then inside the container's CGROUP namespace, that path appears as /.
    The container cannot see /sys/fs/cgroup/docker/def456 (another
    container's cgroup) or /sys/fs/cgroup (the host's cgroup root).

    Attributes:
        _cgroup_root: The host cgroup path that serves as this
            namespace's root.
        _cgroup_entries: Dictionary of visible cgroup entries.
        _controllers: Set of available cgroup controllers.
        _parent_cgroup_root: The parent namespace's cgroup root.
    """

    # Standard cgroup v2 controllers
    STANDARD_CONTROLLERS = frozenset({
        "cpu", "cpuacct", "cpuset", "memory", "io", "pids",
        "rdma", "hugetlb", "misc",
    })

    def __init__(
        self,
        cgroup_root: str = "/",
        parent: Optional[Namespace] = None,
        ns_id: Optional[str] = None,
    ) -> None:
        """Initialize the CGROUP namespace.

        Args:
            cgroup_root: Host cgroup path for the namespace root.
            parent: Optional parent CGROUP namespace.
            ns_id: Optional namespace ID.
        """
        super().__init__(NamespaceType.CGROUP, parent=parent, ns_id=ns_id)
        self._cgroup_root = cgroup_root
        self._cgroup_entries: dict[str, CgroupEntry] = {}
        self._controllers: set[str] = set(self.STANDARD_CONTROLLERS)
        self._parent_cgroup_root = (
            parent._cgroup_root
            if parent is not None and isinstance(parent, CGROUPNamespace)
            else "/"
        )

        # Create root entry
        self._cgroup_entries["/"] = CgroupEntry(
            path="/",
            controllers=set(self._controllers),
        )

    @property
    def cgroup_root(self) -> str:
        """Return the cgroup root path."""
        return self._cgroup_root

    @property
    def cgroup_entries(self) -> dict[str, CgroupEntry]:
        """Return the cgroup entries."""
        return dict(self._cgroup_entries)

    @property
    def controllers(self) -> set[str]:
        """Return the available controllers."""
        return set(self._controllers)

    @property
    def entry_count(self) -> int:
        """Return the number of cgroup entries."""
        return len(self._cgroup_entries)

    def add_cgroup(
        self,
        path: str,
        controllers: Optional[set[str]] = None,
    ) -> CgroupEntry:
        """Add a cgroup entry to the namespace view.

        Args:
            path: Cgroup path relative to the namespace root.
            controllers: Set of controllers; uses defaults if not specified.

        Returns:
            The created CgroupEntry.

        Raises:
            CGROUPNamespaceError: If the path already exists.
        """
        if self._state != NamespaceState.ACTIVE:
            raise CGROUPNamespaceError(
                f"Cannot add cgroup in namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )

        if path in self._cgroup_entries:
            raise CGROUPNamespaceError(
                f"Cgroup path {path} already exists in namespace {self._ns_id}"
            )

        entry = CgroupEntry(
            path=path,
            controllers=controllers or set(self._controllers),
        )
        self._cgroup_entries[path] = entry
        return entry

    def remove_cgroup(self, path: str) -> None:
        """Remove a cgroup entry.

        Args:
            path: Cgroup path to remove.

        Raises:
            CGROUPNamespaceError: If the path is not found or is root.
        """
        if path == "/":
            raise CGROUPNamespaceError(
                "Cannot remove the root cgroup"
            )
        if path not in self._cgroup_entries:
            raise CGROUPNamespaceError(
                f"Cgroup path {path} not found in namespace {self._ns_id}"
            )
        del self._cgroup_entries[path]

    def add_process_to_cgroup(self, path: str, pid: int) -> None:
        """Add a process to a cgroup.

        Args:
            path: Cgroup path.
            pid: Process ID to add.

        Raises:
            CGROUPNamespaceError: If the path is not found.
        """
        if path not in self._cgroup_entries:
            raise CGROUPNamespaceError(
                f"Cgroup path {path} not found in namespace {self._ns_id}"
            )
        self._cgroup_entries[path].processes.add(pid)

    def remove_process_from_cgroup(self, path: str, pid: int) -> None:
        """Remove a process from a cgroup.

        Args:
            path: Cgroup path.
            pid: Process ID to remove.

        Raises:
            CGROUPNamespaceError: If the path is not found.
        """
        if path not in self._cgroup_entries:
            raise CGROUPNamespaceError(
                f"Cgroup path {path} not found in namespace {self._ns_id}"
            )
        self._cgroup_entries[path].processes.discard(pid)

    def virtualize_path(self, host_path: str) -> str:
        """Virtualize a host cgroup path to the namespace view.

        Translates a host cgroup path to the path as seen inside this
        namespace.  If the host path is not within this namespace's
        cgroup root, it is invisible.

        Args:
            host_path: The host cgroup path.

        Returns:
            The virtualized path, or empty string if invisible.
        """
        if not host_path.startswith(self._cgroup_root):
            return ""

        relative = host_path[len(self._cgroup_root):]
        if not relative:
            return "/"
        if not relative.startswith("/"):
            relative = "/" + relative
        return relative

    def is_visible(self, host_path: str) -> bool:
        """Check if a host cgroup path is visible in this namespace.

        Args:
            host_path: The host cgroup path.

        Returns:
            True if the path is within this namespace's root.
        """
        return host_path.startswith(self._cgroup_root)

    def get_controllers_for_path(self, path: str) -> set[str]:
        """Get the controllers available for a cgroup path.

        Args:
            path: Cgroup path.

        Returns:
            Set of controller names.

        Raises:
            CGROUPNamespaceError: If the path is not found.
        """
        if path not in self._cgroup_entries:
            raise CGROUPNamespaceError(
                f"Cgroup path {path} not found in namespace {self._ns_id}"
            )
        return set(self._cgroup_entries[path].controllers)

    def isolate(self, pid: int) -> None:
        """Isolate a process within the CGROUP namespace.

        Args:
            pid: The process ID to isolate.
        """
        self.add_member(pid)
        self.add_process_to_cgroup("/", pid)

    def enter(self, pid: int) -> None:
        """Enter the CGROUP namespace.

        Args:
            pid: The process ID entering.
        """
        if self._state != NamespaceState.ACTIVE:
            raise NamespaceEntryError(
                f"Cannot enter CGROUP namespace {self._ns_id}: "
                f"state is {self._state.value}"
            )
        self.add_member(pid)
        self.add_process_to_cgroup("/", pid)

    def leave(self, pid: int) -> None:
        """Leave the CGROUP namespace.

        Args:
            pid: The process ID leaving.
        """
        # Remove from all cgroups
        for entry in self._cgroup_entries.values():
            entry.processes.discard(pid)
        self.remove_member(pid)

    def destroy(self) -> None:
        """Destroy the CGROUP namespace.

        Raises:
            NamespaceDestroyError: If members still exist.
        """
        if self._member_pids:
            raise NamespaceDestroyError(
                f"Cannot destroy CGROUP namespace {self._ns_id}: "
                f"{len(self._member_pids)} members still present"
            )

        self._state = NamespaceState.DESTROYING
        self._cgroup_entries.clear()

        if self._parent is not None:
            if self in self._parent._children:
                self._parent._children.remove(self)

        self._state = NamespaceState.DESTROYED
        logger.debug("CGROUP namespace %s destroyed", self._ns_id)


# ══════════════════════════════════════════════════════════════════════
# NamespaceManager
# ══════════════════════════════════════════════════════════════════════


class _NamespaceManagerMeta(type):
    """Metaclass for NamespaceManager singleton."""

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def reset(mcs) -> None:
        """Reset all singleton instances."""
        mcs._instances.clear()


class NamespaceManager(metaclass=_NamespaceManagerMeta):
    """Singleton manager for all namespace lifecycle operations.

    The NamespaceManager is the central authority for namespace creation,
    entry, exit, and destruction.  It provides the three fundamental
    namespace operations matching the Linux kernel's system calls:

      - clone(): Create a new child process in new namespaces.
      - unshare(): Move the calling process into new namespaces.
      - setns(): Move the calling process into an existing namespace.

    The manager maintains a global registry of all active namespaces,
    tracks namespace-to-process mappings, manages reference counts,
    and performs garbage collection of unreferenced namespaces.

    Root namespaces (one per type) represent the host's default
    namespace set.  All namespace hierarchies originate from the
    root namespaces.

    Attributes:
        _registry: Dictionary mapping namespace IDs to instances.
        _root_namespaces: The root namespace set (host defaults).
        _process_namespaces: Maps PIDs to their current namespace sets.
        _gc_count: Number of garbage collection cycles run.
        _total_created: Total namespaces created since initialization.
        _total_destroyed: Total namespaces destroyed since initialization.
    """

    def __init__(
        self,
        default_hostname: str = DEFAULT_HOSTNAME,
        default_domainname: str = DEFAULT_DOMAINNAME,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the namespace manager.

        Creates root namespaces for all seven types, representing
        the host's default namespace set.

        Args:
            default_hostname: Default hostname for UTS namespaces.
            default_domainname: Default domain name for UTS namespaces.
            event_bus: Optional event bus for publishing events.
        """
        self._default_hostname = default_hostname
        self._default_domainname = default_domainname
        self._event_bus = event_bus
        self._registry: dict[str, Namespace] = {}
        self._process_namespaces: dict[int, NamespaceSet] = {}
        self._gc_count = 0
        self._total_created = 0
        self._total_destroyed = 0
        self._clone_log: list[dict[str, Any]] = []
        self._unshare_log: list[dict[str, Any]] = []
        self._setns_log: list[dict[str, Any]] = []

        # Create root namespaces
        self._root_namespaces = self._create_root_namespaces()

        logger.debug(
            "NamespaceManager initialized with %d root namespaces",
            len(self._root_namespaces.types),
        )

    def _create_root_namespaces(self) -> NamespaceSet:
        """Create the root namespace set (host defaults).

        Returns:
            NamespaceSet containing one root namespace per type.
        """
        root_ns: dict[NamespaceType, Namespace] = {}

        # PID root
        pid_ns = PIDNamespace(ns_id="ns-pid-root")
        self._register(pid_ns)
        root_ns[NamespaceType.PID] = pid_ns

        # NET root
        net_ns = NETNamespace(ns_id="ns-net-root")
        self._register(net_ns)
        root_ns[NamespaceType.NET] = net_ns

        # MNT root
        mnt_ns = MNTNamespace(ns_id="ns-mnt-root")
        self._register(mnt_ns)
        root_ns[NamespaceType.MNT] = mnt_ns

        # UTS root
        uts_ns = UTSNamespace(
            hostname=self._default_hostname,
            domainname=self._default_domainname,
            ns_id="ns-uts-root",
        )
        self._register(uts_ns)
        root_ns[NamespaceType.UTS] = uts_ns

        # IPC root
        ipc_ns = IPCNamespace(ns_id="ns-ipc-root")
        self._register(ipc_ns)
        root_ns[NamespaceType.IPC] = ipc_ns

        # USER root
        user_ns = USERNamespace(
            owner_uid=ROOT_UID,
            owner_gid=ROOT_GID,
            ns_id="ns-user-root",
        )
        self._register(user_ns)
        root_ns[NamespaceType.USER] = user_ns

        # CGROUP root
        cgroup_ns = CGROUPNamespace(
            cgroup_root="/",
            ns_id="ns-cgroup-root",
        )
        self._register(cgroup_ns)
        root_ns[NamespaceType.CGROUP] = cgroup_ns

        return NamespaceSet(root_ns, set_id="nsset-root")

    def _register(self, namespace: Namespace) -> None:
        """Register a namespace in the global registry.

        Args:
            namespace: The namespace to register.
        """
        self._registry[namespace.ns_id] = namespace
        self._total_created += 1

    def _publish_event(self, event_type: Any, data: dict[str, Any]) -> None:
        """Publish an event to the event bus if available.

        Args:
            event_type: The event type to publish.
            data: Event data dictionary.
        """
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                logger.debug("Failed to publish event: %s", event_type)

    @property
    def root_namespaces(self) -> NamespaceSet:
        """Return the root namespace set."""
        return self._root_namespaces

    @property
    def registry(self) -> dict[str, Namespace]:
        """Return the namespace registry."""
        return dict(self._registry)

    @property
    def process_namespaces(self) -> dict[int, NamespaceSet]:
        """Return the process-to-namespace mappings."""
        return dict(self._process_namespaces)

    @property
    def total_created(self) -> int:
        """Return total namespaces created."""
        return self._total_created

    @property
    def total_destroyed(self) -> int:
        """Return total namespaces destroyed."""
        return self._total_destroyed

    @property
    def active_count(self) -> int:
        """Return the number of active namespaces."""
        return sum(
            1 for ns in self._registry.values()
            if ns.state == NamespaceState.ACTIVE
        )

    @property
    def gc_count(self) -> int:
        """Return the number of GC cycles run."""
        return self._gc_count

    def get_namespace(self, ns_id: str) -> Optional[Namespace]:
        """Look up a namespace by ID.

        Args:
            ns_id: The namespace ID.

        Returns:
            The Namespace instance, or None if not found.
        """
        return self._registry.get(ns_id)

    def get_namespaces_by_type(self, ns_type: NamespaceType) -> list[Namespace]:
        """Get all namespaces of a given type.

        Args:
            ns_type: The namespace type to filter by.

        Returns:
            List of matching namespaces.
        """
        return [
            ns for ns in self._registry.values()
            if ns.ns_type == ns_type and ns.state == NamespaceState.ACTIVE
        ]

    def clone(
        self,
        pid: int,
        flags: int,
        parent_pid: Optional[int] = None,
    ) -> NamespaceSet:
        """Create new namespaces for a process (clone semantics).

        Creates new namespace instances for each type specified by the
        flags, with the current namespaces as parents.  The process is
        placed into the new namespaces.

        Args:
            pid: The PID of the new process.
            flags: Bitwise OR of CLONE_NEW* flags.
            parent_pid: Optional parent PID for PID namespace.

        Returns:
            The NamespaceSet for the new process.

        Raises:
            NamespaceCreationError: If namespace creation fails.
        """
        try:
            new_ns: dict[NamespaceType, Namespace] = {}

            # Determine parent namespace set
            parent_set = (
                self._process_namespaces.get(parent_pid, self._root_namespaces)
                if parent_pid is not None
                else self._root_namespaces
            )

            # Create requested namespaces
            for ns_type in NamespaceType:
                if flags & ns_type.value:
                    parent_ns = parent_set.get(ns_type)
                    ns = self._create_namespace(ns_type, parent=parent_ns)
                    new_ns[ns_type] = ns
                else:
                    # Share parent's namespace
                    existing = parent_set.get(ns_type)
                    if existing is not None:
                        new_ns[ns_type] = existing

            ns_set = NamespaceSet(new_ns)
            self._process_namespaces[pid] = ns_set

            # Log the clone operation
            self._clone_log.append({
                "pid": pid,
                "flags": flags,
                "parent_pid": parent_pid,
                "namespace_set_id": ns_set.set_id,
                "timestamp": time.time(),
            })

            # Publish event
            from enterprise_fizzbuzz.domain.models import EventType
            self._publish_event(EventType.NS_NAMESPACE_CREATED, {
                "pid": pid,
                "flags": flags,
                "ns_types": [t.name for t in new_ns if flags & t.value],
            })

            logger.debug(
                "clone(): PID %d created with flags 0x%08x, %d new namespaces",
                pid,
                flags,
                sum(1 for t in NamespaceType if flags & t.value),
            )

            return ns_set

        except NamespaceError:
            raise
        except Exception as e:
            raise NamespaceCreationError(
                f"Failed to clone namespaces for PID {pid}: {e}"
            ) from e

    def unshare(self, pid: int, flags: int) -> NamespaceSet:
        """Move a process into new namespaces (unshare semantics).

        Creates new namespace instances for each type specified by the
        flags and moves the calling process into them.  Unlike clone(),
        this does not create a new process.

        Args:
            pid: The PID of the calling process.
            flags: Bitwise OR of CLONE_NEW* flags.

        Returns:
            The updated NamespaceSet for the process.

        Raises:
            NamespaceCreationError: If namespace creation fails.
        """
        try:
            current_set = self._process_namespaces.get(pid, self._root_namespaces)
            new_ns: dict[NamespaceType, Namespace] = {}

            for ns_type in NamespaceType:
                if flags & ns_type.value:
                    parent_ns = current_set.get(ns_type)
                    ns = self._create_namespace(ns_type, parent=parent_ns)
                    new_ns[ns_type] = ns
                else:
                    existing = current_set.get(ns_type)
                    if existing is not None:
                        new_ns[ns_type] = existing

            ns_set = NamespaceSet(new_ns)
            self._process_namespaces[pid] = ns_set

            self._unshare_log.append({
                "pid": pid,
                "flags": flags,
                "namespace_set_id": ns_set.set_id,
                "timestamp": time.time(),
            })

            logger.debug(
                "unshare(): PID %d moved into %d new namespaces",
                pid,
                sum(1 for t in NamespaceType if flags & t.value),
            )

            return ns_set

        except NamespaceError:
            raise
        except Exception as e:
            raise NamespaceCreationError(
                f"Failed to unshare namespaces for PID {pid}: {e}"
            ) from e

    def setns(self, pid: int, ns_id: str) -> None:
        """Move a process into an existing namespace (setns semantics).

        Args:
            pid: The PID of the calling process.
            ns_id: The target namespace ID.

        Raises:
            NamespaceEntryError: If the namespace is not found or not active.
        """
        target_ns = self._registry.get(ns_id)
        if target_ns is None:
            raise NamespaceEntryError(
                f"Namespace {ns_id} not found"
            )
        if target_ns.state != NamespaceState.ACTIVE:
            raise NamespaceEntryError(
                f"Namespace {ns_id} is not active: {target_ns.state.value}"
            )

        current_set = self._process_namespaces.get(pid, self._root_namespaces)

        # Build new namespace set with the target replacing its type
        new_ns: dict[NamespaceType, Namespace] = {}
        for ns_type in NamespaceType:
            if ns_type == target_ns.ns_type:
                new_ns[ns_type] = target_ns
            else:
                existing = current_set.get(ns_type)
                if existing is not None:
                    new_ns[ns_type] = existing

        ns_set = NamespaceSet(new_ns)
        self._process_namespaces[pid] = ns_set

        # Add as member
        target_ns.add_member(pid)

        self._setns_log.append({
            "pid": pid,
            "ns_id": ns_id,
            "ns_type": target_ns.ns_type.name,
            "timestamp": time.time(),
        })

        # Publish event
        from enterprise_fizzbuzz.domain.models import EventType
        self._publish_event(EventType.NS_PROCESS_ENTERED, {
            "pid": pid,
            "ns_id": ns_id,
            "ns_type": target_ns.ns_type.name,
        })

        logger.debug(
            "setns(): PID %d entered namespace %s (type=%s)",
            pid,
            ns_id,
            target_ns.ns_type.name,
        )

    def _create_namespace(
        self,
        ns_type: NamespaceType,
        parent: Optional[Namespace] = None,
    ) -> Namespace:
        """Create a new namespace of the specified type.

        Args:
            ns_type: The namespace type to create.
            parent: Optional parent namespace.

        Returns:
            The created Namespace instance.

        Raises:
            NamespaceCreationError: If creation fails.
        """
        try:
            ns: Namespace
            if ns_type == NamespaceType.PID:
                ns = PIDNamespace(parent=parent)
            elif ns_type == NamespaceType.NET:
                ns = NETNamespace(parent=parent)
            elif ns_type == NamespaceType.MNT:
                ns = MNTNamespace(parent=parent)
            elif ns_type == NamespaceType.UTS:
                ns = UTSNamespace(
                    hostname=self._default_hostname,
                    domainname=self._default_domainname,
                    parent=parent,
                )
            elif ns_type == NamespaceType.IPC:
                ns = IPCNamespace(parent=parent)
            elif ns_type == NamespaceType.USER:
                ns = USERNamespace(parent=parent)
            elif ns_type == NamespaceType.CGROUP:
                ns = CGROUPNamespace(parent=parent)
            else:
                raise NamespaceTypeError(
                    f"Unknown namespace type: {ns_type}"
                )

            self._register(ns)
            return ns

        except NamespaceError:
            raise
        except Exception as e:
            raise NamespaceCreationError(
                f"Failed to create {ns_type.name} namespace: {e}"
            ) from e

    def destroy_namespace(self, ns_id: str) -> None:
        """Destroy a namespace by ID.

        Args:
            ns_id: The namespace ID to destroy.

        Raises:
            NamespaceDestroyError: If destruction fails.
            NamespaceManagerError: If the namespace is not found.
        """
        ns = self._registry.get(ns_id)
        if ns is None:
            raise NamespaceManagerError(
                f"Namespace {ns_id} not found in registry"
            )

        if ns.is_root:
            raise NamespaceDestroyError(
                f"Cannot destroy root namespace {ns_id}"
            )

        ns.destroy()
        self._total_destroyed += 1

        # Publish event
        from enterprise_fizzbuzz.domain.models import EventType
        self._publish_event(EventType.NS_NAMESPACE_DESTROYED, {
            "ns_id": ns_id,
            "ns_type": ns.ns_type.name,
        })

        logger.debug("Namespace %s destroyed via manager", ns_id)

    def garbage_collect(self) -> int:
        """Run garbage collection on unreferenced namespaces.

        Identifies namespaces with zero references and no member
        processes, then destroys them.  Root namespaces are never
        garbage collected.

        Returns:
            The number of namespaces collected.
        """
        collected = 0
        to_collect = []

        for ns_id, ns in self._registry.items():
            if (
                ns.state == NamespaceState.ACTIVE
                and not ns.is_root
                and ns.ref_count == 0
                and len(ns.member_pids) == 0
            ):
                to_collect.append(ns_id)

        for ns_id in to_collect:
            try:
                ns = self._registry[ns_id]
                ns.destroy()
                self._total_destroyed += 1
                collected += 1
            except Exception:
                logger.debug("GC: failed to collect namespace %s", ns_id)

        self._gc_count += 1

        if collected > 0:
            logger.debug(
                "GC cycle %d: collected %d namespaces",
                self._gc_count,
                collected,
            )

        return collected

    def get_process_namespace(
        self,
        pid: int,
        ns_type: NamespaceType,
    ) -> Optional[Namespace]:
        """Get the namespace of a specific type for a process.

        Args:
            pid: The process ID.
            ns_type: The namespace type.

        Returns:
            The Namespace instance, or None.
        """
        ns_set = self._process_namespaces.get(pid)
        if ns_set is None:
            return None
        return ns_set.get(ns_type)

    def remove_process(self, pid: int) -> None:
        """Remove a process from all its namespaces.

        Args:
            pid: The process ID to remove.
        """
        ns_set = self._process_namespaces.pop(pid, None)
        if ns_set is not None:
            for ns in ns_set.get_all():
                if pid in ns.member_pids:
                    try:
                        ns.remove_member(pid)
                    except Exception:
                        pass

        # Publish event
        from enterprise_fizzbuzz.domain.models import EventType
        self._publish_event(EventType.NS_PROCESS_LEFT, {"pid": pid})

    def get_statistics(self) -> dict[str, Any]:
        """Get namespace manager statistics.

        Returns:
            Dictionary of statistics.
        """
        type_counts: dict[str, int] = {}
        for ns_type in NamespaceType:
            type_counts[ns_type.name] = len(self.get_namespaces_by_type(ns_type))

        return {
            "total_created": self._total_created,
            "total_destroyed": self._total_destroyed,
            "active_count": self.active_count,
            "registered_count": len(self._registry),
            "process_count": len(self._process_namespaces),
            "gc_cycles": self._gc_count,
            "type_counts": type_counts,
            "clone_operations": len(self._clone_log),
            "unshare_operations": len(self._unshare_log),
            "setns_operations": len(self._setns_log),
        }

    def render_hierarchy(self, ns_type: Optional[NamespaceType] = None) -> str:
        """Render an ASCII tree of the namespace hierarchy.

        Args:
            ns_type: Optional type filter; if None, shows all types.

        Returns:
            ASCII tree string.
        """
        lines: list[str] = []
        lines.append("Namespace Hierarchy")
        lines.append("=" * 60)

        types_to_render = [ns_type] if ns_type else list(NamespaceType)

        for nst in types_to_render:
            root_ns = self._root_namespaces.get(nst)
            if root_ns is None:
                continue

            lines.append(f"\n{nst.name} Namespaces:")
            lines.append("-" * 40)
            self._render_tree_node(root_ns, lines, prefix="", is_last=True)

        # Publish event
        from enterprise_fizzbuzz.domain.models import EventType
        self._publish_event(EventType.NS_HIERARCHY_RENDERED, {
            "type_filter": ns_type.name if ns_type else "all",
        })

        return "\n".join(lines)

    def _render_tree_node(
        self,
        ns: Namespace,
        lines: list[str],
        prefix: str,
        is_last: bool,
    ) -> None:
        """Render a single node in the hierarchy tree.

        Args:
            ns: The namespace to render.
            lines: Output lines list.
            prefix: Current indentation prefix.
            is_last: Whether this is the last child at this level.
        """
        connector = "+-- " if is_last else "|-- "
        state_indicator = (
            "[ACTIVE]" if ns.state == NamespaceState.ACTIVE
            else "[DESTROYING]" if ns.state == NamespaceState.DESTROYING
            else "[DESTROYED]"
        )

        lines.append(
            f"{prefix}{connector}{ns.ns_id} {state_indicator} "
            f"refs={ns.ref_count} members={len(ns.member_pids)}"
        )

        child_prefix = prefix + ("    " if is_last else "|   ")
        active_children = [
            c for c in ns.children
            if c.state != NamespaceState.DESTROYED
        ]
        for i, child in enumerate(active_children):
            self._render_tree_node(
                child,
                lines,
                child_prefix,
                is_last=(i == len(active_children) - 1),
            )

    def list_namespaces(
        self,
        ns_type: Optional[NamespaceType] = None,
    ) -> list[dict[str, Any]]:
        """List all active namespaces with their details.

        Args:
            ns_type: Optional type filter.

        Returns:
            List of namespace information dictionaries.
        """
        result = []
        for ns in self._registry.values():
            if ns.state != NamespaceState.ACTIVE:
                continue
            if ns_type is not None and ns.ns_type != ns_type:
                continue

            info: dict[str, Any] = {
                "ns_id": ns.ns_id,
                "type": ns.ns_type.name,
                "state": ns.state.value,
                "ref_count": ns.ref_count,
                "member_count": len(ns.member_pids),
                "is_root": ns.is_root,
                "depth": ns.depth,
                "parent_id": ns.parent.ns_id if ns.parent else None,
                "children_count": len(ns.children),
                "created_at": ns.created_at,
            }
            result.append(info)

        return result

    def inspect_namespace(self, ns_id: str) -> dict[str, Any]:
        """Get detailed information about a namespace.

        Args:
            ns_id: The namespace ID to inspect.

        Returns:
            Detailed namespace information.

        Raises:
            NamespaceManagerError: If the namespace is not found.
        """
        ns = self._registry.get(ns_id)
        if ns is None:
            raise NamespaceManagerError(
                f"Namespace {ns_id} not found"
            )

        info: dict[str, Any] = {
            "ns_id": ns.ns_id,
            "type": ns.ns_type.name,
            "state": ns.state.value,
            "ref_count": ns.ref_count,
            "member_pids": sorted(ns.member_pids),
            "is_root": ns.is_root,
            "depth": ns.depth,
            "parent_id": ns.parent.ns_id if ns.parent else None,
            "children": [c.ns_id for c in ns.children],
            "created_at": ns.created_at,
            "metadata": ns.metadata,
        }

        # Add type-specific information
        if isinstance(ns, PIDNamespace):
            info["init_pid"] = ns.init_pid
            info["pid_count"] = ns.pid_count
            info["pid_table"] = ns.get_pid_table_snapshot()
        elif isinstance(ns, NETNamespace):
            info["interface_count"] = ns.get_interface_count()
            info["interfaces"] = {
                name: {
                    "state": iface.state,
                    "ipv4": iface.ipv4_addresses,
                    "mac": iface.mac_address,
                }
                for name, iface in ns.interfaces.items()
            }
            info["route_count"] = len(ns.routing_table)
            info["binding_count"] = ns.get_binding_count()
        elif isinstance(ns, MNTNamespace):
            info["mount_count"] = ns.mount_count
            info["root_path"] = ns.root_path
            info["mounts"] = [
                {"target": m.target, "source": m.source, "type": m.fs_type}
                for m in ns.mount_table
            ]
        elif isinstance(ns, UTSNamespace):
            info["hostname"] = ns.hostname
            info["domainname"] = ns.domainname
        elif isinstance(ns, IPCNamespace):
            info["shm_count"] = ns.shm_count
            info["sem_count"] = ns.sem_count
            info["msq_count"] = ns.msq_count
            info["total_ipc_objects"] = ns.get_total_ipc_objects()
        elif isinstance(ns, USERNamespace):
            info["uid_mappings"] = len(ns.uid_map)
            info["gid_mappings"] = len(ns.gid_map)
            info["capability_count"] = len(ns.capabilities)
            info["is_rootless"] = ns.is_rootless
            info["owner_uid"] = ns.owner_uid
        elif isinstance(ns, CGROUPNamespace):
            info["cgroup_root"] = ns.cgroup_root
            info["entry_count"] = ns.entry_count
            info["controllers"] = sorted(ns.controllers)

        return info


# ══════════════════════════════════════════════════════════════════════
# FizzNSDashboard
# ══════════════════════════════════════════════════════════════════════


class FizzNSDashboard:
    """ASCII dashboard for the FizzNS namespace isolation engine.

    Renders a comprehensive text-based dashboard showing namespace
    counts by type, process-to-namespace mappings, namespace hierarchy
    trees, and operational statistics.  The dashboard follows the
    visual conventions established by other infrastructure dashboards
    in the Enterprise FizzBuzz Platform.
    """

    @staticmethod
    def render(
        manager: NamespaceManager,
        width: int = 72,
    ) -> str:
        """Render the FizzNS dashboard.

        Args:
            manager: The NamespaceManager instance to visualize.
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        thin_border = "+" + "-" * (width - 2) + "+"
        inner_width = width - 4  # Account for "| " and " |"

        def add_line(text: str) -> None:
            """Add a line padded to the dashboard width."""
            lines.append(f"| {text:<{inner_width}} |")

        # Header
        lines.append(border)
        add_line("FIZZNS: LINUX NAMESPACE ISOLATION ENGINE")
        lines.append(thin_border)

        # Statistics
        stats = manager.get_statistics()
        add_line(f"Total Created: {stats['total_created']}")
        add_line(f"Total Destroyed: {stats['total_destroyed']}")
        add_line(f"Active Namespaces: {stats['active_count']}")
        add_line(f"Tracked Processes: {stats['process_count']}")
        add_line(f"GC Cycles: {stats['gc_cycles']}")
        lines.append(thin_border)

        # Type breakdown
        add_line("Namespace Type Breakdown:")
        type_counts = stats.get("type_counts", {})
        for ns_type in NamespaceType:
            count = type_counts.get(ns_type.name, 0)
            bar_len = min(count * 3, inner_width - 20)
            bar = "#" * bar_len
            add_line(f"  {ns_type.name:<8} {count:>4}  {bar}")
        lines.append(thin_border)

        # Operations
        add_line("Operations:")
        add_line(f"  clone():   {stats.get('clone_operations', 0)}")
        add_line(f"  unshare(): {stats.get('unshare_operations', 0)}")
        add_line(f"  setns():   {stats.get('setns_operations', 0)}")
        lines.append(thin_border)

        # Process mappings (show first 10)
        add_line("Process Namespace Mappings (first 10):")
        proc_ns = manager.process_namespaces
        shown = 0
        for pid, ns_set in sorted(proc_ns.items()):
            if shown >= 10:
                remaining = len(proc_ns) - shown
                add_line(f"  ... and {remaining} more processes")
                break
            types = ", ".join(t.name for t in sorted(ns_set.types, key=lambda t: t.name))
            add_line(f"  PID {pid:>6}: [{types}]")
            shown += 1
        if not proc_ns:
            add_line("  (no tracked processes)")

        # Footer
        lines.append(border)

        # Publish event
        from enterprise_fizzbuzz.domain.models import EventType
        if manager._event_bus:
            try:
                manager._event_bus.publish(
                    EventType.NS_DASHBOARD_RENDERED,
                    {"width": width},
                )
            except Exception:
                pass

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# FizzNSMiddleware
# ══════════════════════════════════════════════════════════════════════


class FizzNSMiddleware(IMiddleware):
    """Middleware integrating the FizzNS engine into the evaluation pipeline.

    Intercepts every FizzBuzz evaluation and injects namespace isolation
    metadata into the processing context.  The metadata includes the
    number of active namespaces, namespace types in use, and the
    process-to-namespace mapping count.

    Priority 106 places this middleware after OrgMiddleware (105)
    and before Archaeology (900).  This ordering reflects the
    infrastructure layering: organizational hierarchy defines the
    operational context; namespace isolation defines the execution
    boundary within that context.

    Attributes:
        _manager: The NamespaceManager instance.
        _enable_dashboard: Whether to enable the dashboard.
        _event_bus: Optional event bus for publishing events.
        _evaluations_processed: Counter of evaluations processed.
    """

    def __init__(
        self,
        manager: NamespaceManager,
        enable_dashboard: bool = False,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the FizzNSMiddleware.

        Args:
            manager: The NamespaceManager instance.
            enable_dashboard: Whether to enable the dashboard.
            event_bus: Optional event bus for publishing events.
        """
        self._manager = manager
        self._enable_dashboard = enable_dashboard
        self._event_bus = event_bus
        self._evaluations_processed = 0

        logger.debug(
            "FizzNSMiddleware initialized: dashboard=%s",
            enable_dashboard,
        )

    @property
    def manager(self) -> NamespaceManager:
        """Return the NamespaceManager instance."""
        return self._manager

    @property
    def evaluations_processed(self) -> int:
        """Return the number of evaluations processed."""
        return self._evaluations_processed

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the namespace engine.

        Calls the next handler first, then injects namespace isolation
        metadata into the result context.

        Args:
            context: The processing context.
            next_handler: The next middleware handler.

        Returns:
            The processed context with namespace metadata.
        """
        try:
            result = next_handler(context)
            self._evaluations_processed += 1

            stats = self._manager.get_statistics()
            result.metadata["fizzns_active_namespaces"] = stats["active_count"]
            result.metadata["fizzns_total_created"] = stats["total_created"]
            result.metadata["fizzns_process_count"] = stats["process_count"]
            result.metadata["fizzns_type_counts"] = stats["type_counts"]

            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.NS_EVALUATION_PROCESSED,
                        {
                            "number": getattr(context, "number", None),
                            "active_namespaces": stats["active_count"],
                        },
                    )
                except Exception:
                    pass

            return result

        except NamespaceError:
            raise
        except Exception as e:
            raise NamespaceMiddlewareError(
                evaluation_number=getattr(context, "number", 0),
                reason=str(e),
            )

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "FizzNSMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority.

        Priority 106 places this after OrgMiddleware (105)
        and before Archaeology (900).
        """
        return 106

    def render_dashboard(self, width: int = 72) -> str:
        """Render the FizzNS ASCII dashboard.

        Args:
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        return FizzNSDashboard.render(self._manager, width=width)

    def render_hierarchy(self, ns_type: Optional[NamespaceType] = None) -> str:
        """Render the namespace hierarchy tree.

        Args:
            ns_type: Optional type filter.

        Returns:
            The rendered hierarchy string.
        """
        return self._manager.render_hierarchy(ns_type=ns_type)

    def list_namespaces(
        self,
        ns_type: Optional[NamespaceType] = None,
    ) -> str:
        """Render a namespace listing.

        Args:
            ns_type: Optional type filter.

        Returns:
            Formatted namespace listing string.
        """
        namespaces = self._manager.list_namespaces(ns_type=ns_type)

        if not namespaces:
            return "No active namespaces found."

        lines: list[str] = []
        lines.append(f"Active Namespaces ({len(namespaces)} total):")
        lines.append("=" * 70)
        lines.append(
            f"{'ID':<30} {'Type':<8} {'Refs':>5} {'Members':>8} {'Root':>5} {'Depth':>6}"
        )
        lines.append("-" * 70)

        for ns_info in sorted(namespaces, key=lambda x: (x["type"], x["ns_id"])):
            root_marker = "yes" if ns_info["is_root"] else "no"
            lines.append(
                f"{ns_info['ns_id']:<30} {ns_info['type']:<8} "
                f"{ns_info['ref_count']:>5} {ns_info['member_count']:>8} "
                f"{root_marker:>5} {ns_info['depth']:>6}"
            )

        lines.append("=" * 70)
        return "\n".join(lines)

    def inspect_namespace(self, ns_id: str) -> str:
        """Render detailed namespace inspection.

        Args:
            ns_id: The namespace ID to inspect.

        Returns:
            Formatted inspection string.
        """
        try:
            info = self._manager.inspect_namespace(ns_id)
        except NamespaceManagerError as e:
            return f"Error: {e}"

        lines: list[str] = []
        lines.append(f"Namespace Inspection: {ns_id}")
        lines.append("=" * 60)

        for key, value in sorted(info.items()):
            if isinstance(value, dict):
                lines.append(f"  {key}:")
                for k, v in sorted(value.items()):
                    lines.append(f"    {k}: {v}")
            elif isinstance(value, (list, set)):
                lines.append(f"  {key}: [{', '.join(str(v) for v in value)}]")
            else:
                lines.append(f"  {key}: {value}")

        lines.append("=" * 60)
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Factory Function
# ══════════════════════════════════════════════════════════════════════


def create_fizzns_subsystem(
    default_hostname: str = DEFAULT_HOSTNAME,
    default_domainname: str = DEFAULT_DOMAINNAME,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[NamespaceManager, FizzNSMiddleware]:
    """Create and wire the complete FizzNS subsystem.

    Factory function that instantiates the NamespaceManager and
    FizzNSMiddleware, ready for integration into the FizzBuzz
    evaluation pipeline.

    Args:
        default_hostname: Default hostname for new UTS namespaces.
        default_domainname: Default domain name for new UTS namespaces.
        enable_dashboard: Whether to enable the post-execution dashboard.
        event_bus: Optional event bus for publishing events.

    Returns:
        A tuple of (NamespaceManager, FizzNSMiddleware).
    """
    manager = NamespaceManager(
        default_hostname=default_hostname,
        default_domainname=default_domainname,
        event_bus=event_bus,
    )

    middleware = FizzNSMiddleware(
        manager=manager,
        enable_dashboard=enable_dashboard,
        event_bus=event_bus,
    )

    logger.info(
        "FizzNS subsystem created: hostname=%s, domainname=%s, "
        "root namespaces=%d",
        default_hostname,
        default_domainname,
        manager.root_namespaces.count,
    )

    return manager, middleware
