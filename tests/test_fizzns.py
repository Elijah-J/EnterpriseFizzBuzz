"""
Enterprise FizzBuzz Platform - FizzNS Test Suite

Comprehensive tests for the Linux Namespace Isolation Engine.  Validates
all seven namespace types (PID, NET, MNT, UTS, IPC, USER, CGROUP),
the NamespaceManager singleton, the NamespaceSet collection, hierarchy
rendering, dashboard output, middleware integration, factory function
wiring, and all 18 exception classes.  Container isolation demands
the same verification rigor applied to every other subsystem.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzns import (
    CLONE_NEWCGROUP,
    CLONE_NEWIPC,
    CLONE_NEWNET,
    CLONE_NEWNS,
    CLONE_NEWPID,
    CLONE_NEWUSER,
    CLONE_NEWUTS,
    DEFAULT_DOMAINNAME,
    DEFAULT_HOSTNAME,
    LOOPBACK_INTERFACE,
    LOOPBACK_IPV4,
    LOOPBACK_IPV6,
    MAX_GID_MAP_ENTRIES,
    MAX_MSG_QUEUES,
    MAX_NAMESPACE_DEPTH,
    MAX_PID,
    MAX_SEMAPHORE_SETS,
    MAX_SHM_SEGMENTS,
    MAX_UID_MAP_ENTRIES,
    NOBODY_GID,
    NOBODY_UID,
    ROOT_GID,
    ROOT_UID,
    CGROUPNamespace,
    CgroupEntry,
    FizzNSDashboard,
    FizzNSMiddleware,
    GIDMapping,
    IPCNamespace,
    MNTNamespace,
    MessageQueue,
    MountEntry,
    NETNamespace,
    NamespaceManager,
    NamespaceSet,
    NamespaceState,
    NamespaceType,
    NetworkInterface,
    PIDNamespace,
    RoutingEntry,
    SHMSegment,
    SemaphoreSet,
    SocketBinding,
    UIDMapping,
    USERNamespace,
    UTSNamespace,
    VethPair,
    create_fizzns_subsystem,
)
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
from config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzns import _NamespaceManagerMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    _NamespaceManagerMeta.reset()
    yield
    _SingletonMeta.reset()
    _NamespaceManagerMeta.reset()


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate namespace constants match Linux kernel definitions."""

    def test_clone_newpid(self):
        assert CLONE_NEWPID == 0x20000000

    def test_clone_newnet(self):
        assert CLONE_NEWNET == 0x40000000

    def test_clone_newns(self):
        assert CLONE_NEWNS == 0x00020000

    def test_clone_newuts(self):
        assert CLONE_NEWUTS == 0x04000000

    def test_clone_newipc(self):
        assert CLONE_NEWIPC == 0x08000000

    def test_clone_newuser(self):
        assert CLONE_NEWUSER == 0x10000000

    def test_clone_newcgroup(self):
        assert CLONE_NEWCGROUP == 0x02000000

    def test_default_hostname(self):
        assert DEFAULT_HOSTNAME == "fizzbuzz-container"

    def test_default_domainname(self):
        assert DEFAULT_DOMAINNAME == "enterprise.local"

    def test_root_uid(self):
        assert ROOT_UID == 0

    def test_root_gid(self):
        assert ROOT_GID == 0

    def test_nobody_uid(self):
        assert NOBODY_UID == 65534

    def test_nobody_gid(self):
        assert NOBODY_GID == 65534

    def test_max_pid(self):
        assert MAX_PID == 32768

    def test_max_namespace_depth(self):
        assert MAX_NAMESPACE_DEPTH == 32

    def test_max_uid_map_entries(self):
        assert MAX_UID_MAP_ENTRIES == 340

    def test_max_gid_map_entries(self):
        assert MAX_GID_MAP_ENTRIES == 340

    def test_loopback_interface(self):
        assert LOOPBACK_INTERFACE == "lo"

    def test_loopback_ipv4(self):
        assert LOOPBACK_IPV4 == "127.0.0.1"

    def test_loopback_ipv6(self):
        assert LOOPBACK_IPV6 == "::1"

    def test_max_shm_segments(self):
        assert MAX_SHM_SEGMENTS == 4096

    def test_max_semaphore_sets(self):
        assert MAX_SEMAPHORE_SETS == 32000

    def test_max_msg_queues(self):
        assert MAX_MSG_QUEUES == 32000


# ============================================================
# NamespaceType Enum Tests
# ============================================================


class TestNamespaceType:
    """Validate NamespaceType enum members and flag values."""

    def test_pid_type(self):
        assert NamespaceType.PID.value == CLONE_NEWPID

    def test_net_type(self):
        assert NamespaceType.NET.value == CLONE_NEWNET

    def test_mnt_type(self):
        assert NamespaceType.MNT.value == CLONE_NEWNS

    def test_uts_type(self):
        assert NamespaceType.UTS.value == CLONE_NEWUTS

    def test_ipc_type(self):
        assert NamespaceType.IPC.value == CLONE_NEWIPC

    def test_user_type(self):
        assert NamespaceType.USER.value == CLONE_NEWUSER

    def test_cgroup_type(self):
        assert NamespaceType.CGROUP.value == CLONE_NEWCGROUP

    def test_member_count(self):
        assert len(NamespaceType) == 7

    def test_all_unique_values(self):
        values = [t.value for t in NamespaceType]
        assert len(values) == len(set(values))

    def test_flag_composition(self):
        all_flags = 0
        for t in NamespaceType:
            all_flags |= t.value
        assert all_flags > 0

    def test_pid_name(self):
        assert NamespaceType.PID.name == "PID"

    def test_net_name(self):
        assert NamespaceType.NET.name == "NET"

    def test_mnt_name(self):
        assert NamespaceType.MNT.name == "MNT"


# ============================================================
# NamespaceState Enum Tests
# ============================================================


class TestNamespaceState:
    """Validate NamespaceState enum members."""

    def test_active_state(self):
        assert NamespaceState.ACTIVE.value == "active"

    def test_destroying_state(self):
        assert NamespaceState.DESTROYING.value == "destroying"

    def test_destroyed_state(self):
        assert NamespaceState.DESTROYED.value == "destroyed"

    def test_member_count(self):
        assert len(NamespaceState) == 3


# ============================================================
# Namespace Base Tests
# ============================================================


class TestNamespaceBase:
    """Validate abstract Namespace base class behavior."""

    def test_pid_namespace_is_namespace(self):
        ns = PIDNamespace(ns_id="test-ns")
        assert ns.ns_type == NamespaceType.PID

    def test_namespace_id_auto_generated(self):
        ns = PIDNamespace()
        assert ns.ns_id.startswith("ns-pid-")

    def test_namespace_id_custom(self):
        ns = PIDNamespace(ns_id="custom-id")
        assert ns.ns_id == "custom-id"

    def test_initial_state_active(self):
        ns = PIDNamespace()
        assert ns.state == NamespaceState.ACTIVE

    def test_initial_ref_count_zero(self):
        ns = PIDNamespace()
        assert ns.ref_count == 0

    def test_initial_no_members(self):
        ns = PIDNamespace()
        assert len(ns.member_pids) == 0

    def test_root_namespace_no_parent(self):
        ns = PIDNamespace()
        assert ns.parent is None
        assert ns.is_root is True

    def test_child_namespace_has_parent(self):
        parent = PIDNamespace(ns_id="parent")
        child = PIDNamespace(parent=parent, ns_id="child")
        assert child.parent is parent
        assert child.is_root is False

    def test_parent_has_child(self):
        parent = PIDNamespace(ns_id="parent")
        child = PIDNamespace(parent=parent, ns_id="child")
        assert child in parent.children

    def test_depth_root(self):
        ns = PIDNamespace()
        assert ns.depth == 0

    def test_depth_child(self):
        parent = PIDNamespace()
        child = PIDNamespace(parent=parent)
        assert child.depth == 1

    def test_depth_grandchild(self):
        root = PIDNamespace()
        child = PIDNamespace(parent=root)
        grandchild = PIDNamespace(parent=child)
        assert grandchild.depth == 2

    def test_add_ref(self):
        ns = PIDNamespace()
        result = ns.add_ref()
        assert result == 1
        assert ns.ref_count == 1

    def test_release_ref(self):
        ns = PIDNamespace()
        ns.add_ref()
        result = ns.release_ref()
        assert result == 0

    def test_release_ref_underflow(self):
        ns = PIDNamespace()
        with pytest.raises(NamespaceRefCountError):
            ns.release_ref()

    def test_add_member(self):
        ns = NETNamespace()
        ns.add_member(100)
        assert 100 in ns.member_pids
        assert ns.ref_count == 1

    def test_remove_member(self):
        ns = NETNamespace()
        ns.add_member(100)
        ns.remove_member(100)
        assert 100 not in ns.member_pids
        assert ns.ref_count == 0

    def test_remove_nonexistent_member(self):
        ns = NETNamespace()
        with pytest.raises(NamespaceLeaveError):
            ns.remove_member(999)

    def test_metadata(self):
        ns = PIDNamespace()
        ns.set_metadata("key", "value")
        assert ns.get_metadata("key") == "value"

    def test_metadata_default(self):
        ns = PIDNamespace()
        assert ns.get_metadata("missing", "default") == "default"

    def test_created_at(self):
        ns = PIDNamespace()
        assert ns.created_at > 0

    def test_hierarchy_from_root(self):
        root = PIDNamespace(ns_id="root")
        child = PIDNamespace(parent=root, ns_id="child")
        grandchild = PIDNamespace(parent=child, ns_id="gc")
        hierarchy = grandchild.get_hierarchy()
        assert len(hierarchy) == 3
        assert hierarchy[0] is root
        assert hierarchy[2] is grandchild

    def test_descendants(self):
        root = PIDNamespace(ns_id="root")
        child1 = PIDNamespace(parent=root, ns_id="c1")
        child2 = PIDNamespace(parent=root, ns_id="c2")
        grandchild = PIDNamespace(parent=child1, ns_id="gc")
        descendants = root.get_descendants()
        assert len(descendants) == 3

    def test_repr(self):
        ns = PIDNamespace(ns_id="test-repr")
        r = repr(ns)
        assert "PIDNamespace" in r
        assert "test-repr" in r

    def test_add_member_to_destroyed_namespace(self):
        ns = NETNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(NamespaceEntryError):
            ns.add_member(100)

    def test_add_ref_to_destroyed_namespace(self):
        ns = PIDNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(NamespaceRefCountError):
            ns.add_ref()


# ============================================================
# NamespaceSet Tests
# ============================================================


class TestNamespaceSet:
    """Validate NamespaceSet frozen collection behavior."""

    def test_empty_set(self):
        ns_set = NamespaceSet()
        assert ns_set.count == 0

    def test_set_with_namespace(self):
        pid_ns = PIDNamespace()
        ns_set = NamespaceSet({NamespaceType.PID: pid_ns})
        assert ns_set.count == 1

    def test_get_existing_type(self):
        pid_ns = PIDNamespace()
        ns_set = NamespaceSet({NamespaceType.PID: pid_ns})
        assert ns_set.get(NamespaceType.PID) is pid_ns

    def test_get_missing_type(self):
        ns_set = NamespaceSet()
        assert ns_set.get(NamespaceType.PID) is None

    def test_has_type(self):
        pid_ns = PIDNamespace()
        ns_set = NamespaceSet({NamespaceType.PID: pid_ns})
        assert ns_set.has(NamespaceType.PID) is True
        assert ns_set.has(NamespaceType.NET) is False

    def test_contains(self):
        pid_ns = PIDNamespace()
        ns_set = NamespaceSet({NamespaceType.PID: pid_ns})
        assert NamespaceType.PID in ns_set
        assert NamespaceType.NET not in ns_set

    def test_len(self):
        pid_ns = PIDNamespace()
        net_ns = NETNamespace()
        ns_set = NamespaceSet({NamespaceType.PID: pid_ns, NamespaceType.NET: net_ns})
        assert len(ns_set) == 2

    def test_iter(self):
        pid_ns = PIDNamespace()
        ns_set = NamespaceSet({NamespaceType.PID: pid_ns})
        types = list(ns_set)
        assert NamespaceType.PID in types

    def test_types_property(self):
        pid_ns = PIDNamespace()
        net_ns = NETNamespace()
        ns_set = NamespaceSet({NamespaceType.PID: pid_ns, NamespaceType.NET: net_ns})
        assert ns_set.types == {NamespaceType.PID, NamespaceType.NET}

    def test_to_dict(self):
        pid_ns = PIDNamespace(ns_id="test-pid")
        ns_set = NamespaceSet({NamespaceType.PID: pid_ns})
        d = ns_set.to_dict()
        assert d["PID"] == "test-pid"

    def test_get_all(self):
        pid_ns = PIDNamespace()
        net_ns = NETNamespace()
        ns_set = NamespaceSet({NamespaceType.PID: pid_ns, NamespaceType.NET: net_ns})
        all_ns = ns_set.get_all()
        assert len(all_ns) == 2

    def test_clone_flags(self):
        pid_ns = PIDNamespace()
        net_ns = NETNamespace()
        ns_set = NamespaceSet({NamespaceType.PID: pid_ns, NamespaceType.NET: net_ns})
        flags = ns_set.get_clone_flags()
        assert flags & CLONE_NEWPID
        assert flags & CLONE_NEWNET

    def test_set_id_auto(self):
        ns_set = NamespaceSet()
        assert ns_set.set_id.startswith("nsset-")

    def test_set_id_custom(self):
        ns_set = NamespaceSet(set_id="custom-set")
        assert ns_set.set_id == "custom-set"

    def test_created_at(self):
        ns_set = NamespaceSet()
        assert ns_set.created_at > 0

    def test_repr(self):
        ns_set = NamespaceSet(set_id="test-repr")
        r = repr(ns_set)
        assert "NamespaceSet" in r
        assert "test-repr" in r

    def test_full_set(self):
        namespaces = {
            NamespaceType.PID: PIDNamespace(),
            NamespaceType.NET: NETNamespace(),
            NamespaceType.MNT: MNTNamespace(),
            NamespaceType.UTS: UTSNamespace(),
            NamespaceType.IPC: IPCNamespace(),
            NamespaceType.USER: USERNamespace(),
            NamespaceType.CGROUP: CGROUPNamespace(),
        }
        ns_set = NamespaceSet(namespaces)
        assert ns_set.count == 7


# ============================================================
# PIDNamespace Tests
# ============================================================


class TestPIDNamespace:
    """Validate PID namespace isolation, init process, and hierarchy."""

    def test_create(self):
        ns = PIDNamespace()
        assert ns.ns_type == NamespaceType.PID
        assert ns.pid_count == 0

    def test_allocate_first_pid_is_init(self):
        ns = PIDNamespace()
        pid = ns.allocate_pid("init")
        assert pid == 1
        assert ns.init_pid == 1

    def test_allocate_sequential_pids(self):
        ns = PIDNamespace()
        p1 = ns.allocate_pid("init")
        p2 = ns.allocate_pid("process-2")
        p3 = ns.allocate_pid("process-3")
        assert p1 == 1
        assert p2 == 2
        assert p3 == 3
        assert ns.pid_count == 3

    def test_allocate_with_parent_pid(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        pid = ns.allocate_pid("child", parent_pid=1)
        assert pid == 2
        children = ns.get_children_of(1)
        assert 2 in children

    def test_deallocate_pid(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        ns.allocate_pid("worker")
        ns.deallocate_pid(2)
        assert ns.pid_count == 1

    def test_deallocate_nonexistent_pid(self):
        ns = PIDNamespace()
        with pytest.raises(PIDNamespaceError):
            ns.deallocate_pid(999)

    def test_orphan_adoption(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        ns.allocate_pid("parent", parent_pid=1)
        ns.allocate_pid("child", parent_pid=2)
        ns.deallocate_pid(2)
        assert 3 in ns.orphaned_pids

    def test_init_exit_kills_all(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        ns.allocate_pid("worker-1")
        ns.allocate_pid("worker-2")
        ns.allocate_pid("worker-3")
        ns.deallocate_pid(1)
        assert ns.pid_count == 0
        assert ns.init_pid is None
        assert len(ns.killed_pids) == 3

    def test_pid_translation_to_parent(self):
        parent = PIDNamespace(ns_id="parent")
        child = PIDNamespace(parent=parent, ns_id="child")
        child.allocate_pid("init")
        parent_pid = child.translate_pid_to_parent(1)
        assert parent_pid is not None

    def test_pid_translation_from_parent(self):
        parent = PIDNamespace(ns_id="parent")
        child = PIDNamespace(parent=parent, ns_id="child")
        child.allocate_pid("init")
        parent_pid = child.translate_pid_to_parent(1)
        local_pid = child.translate_pid_from_parent(parent_pid)
        assert local_pid == 1

    def test_pid_translation_nonexistent(self):
        ns = PIDNamespace()
        assert ns.translate_pid_to_parent(999) is None
        assert ns.translate_pid_from_parent(999) is None

    def test_get_process_info(self):
        ns = PIDNamespace()
        ns.allocate_pid("test-process")
        info = ns.get_process_info(1)
        assert info is not None
        assert info["process_name"] == "test-process"
        assert info["pid"] == 1

    def test_get_process_info_nonexistent(self):
        ns = PIDNamespace()
        assert ns.get_process_info(999) is None

    def test_get_visible_pids(self):
        parent = PIDNamespace(ns_id="parent")
        parent.allocate_pid("host-init")
        child = PIDNamespace(parent=parent, ns_id="child")
        child.allocate_pid("container-init")
        visible = parent.get_visible_pids()
        assert 1 in visible  # parent's own PID
        assert len(visible) >= 1

    def test_send_signal(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        ns.allocate_pid("worker")
        result = ns.send_signal(2, "SIGTERM", sender_pid=1)
        assert result is True

    def test_send_signal_to_init_ignored(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        result = ns.send_signal(1, "SIGTERM", sender_pid=0)
        assert result is False

    def test_send_signal_sigkill_to_init(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        ns.allocate_pid("worker")
        ns.send_signal(2, "SIGKILL", sender_pid=1)
        assert ns.pid_count == 1  # Only init remains

    def test_send_signal_nonexistent_pid(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        with pytest.raises(PIDNamespaceError):
            ns.send_signal(999, "SIGTERM")

    def test_signal_log(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        ns.allocate_pid("worker")
        ns.send_signal(2, "SIGTERM")
        assert len(ns.signal_log) == 1

    def test_pid_table_snapshot(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        ns.allocate_pid("worker")
        snapshot = ns.get_pid_table_snapshot()
        assert 1 in snapshot
        assert 2 in snapshot

    def test_isolate(self):
        ns = PIDNamespace()
        ns.isolate(100)
        assert ns.pid_count == 1

    def test_enter(self):
        ns = PIDNamespace()
        ns.enter(100)
        assert ns.pid_count == 1

    def test_enter_destroyed(self):
        ns = PIDNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(NamespaceEntryError):
            ns.enter(100)

    def test_leave(self):
        ns = PIDNamespace()
        pid = ns.allocate_pid("worker")
        ns.leave(pid)
        assert ns.pid_count == 0

    def test_destroy_empty(self):
        ns = PIDNamespace()
        ns.destroy()
        assert ns.state == NamespaceState.DESTROYED

    def test_destroy_with_processes(self):
        ns = PIDNamespace()
        ns.allocate_pid("init")
        with pytest.raises(NamespaceDestroyError):
            ns.destroy()

    def test_destroy_detaches_from_parent(self):
        parent = PIDNamespace(ns_id="parent")
        child = PIDNamespace(parent=parent, ns_id="child")
        assert child in parent.children
        child.destroy()
        assert child not in parent.children

    def test_allocate_in_destroyed_namespace(self):
        ns = PIDNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(PIDNamespaceError):
            ns.allocate_pid("test")

    def test_hierarchical_visibility(self):
        parent = PIDNamespace(ns_id="parent")
        parent.allocate_pid("host-init")
        child = PIDNamespace(parent=parent, ns_id="child")
        child.allocate_pid("container-init")
        child.allocate_pid("container-worker")
        # Parent should see its own PIDs plus child PIDs mapped
        visible = parent.get_visible_pids()
        assert 1 in visible  # parent's init

    def test_multiple_children(self):
        parent = PIDNamespace(ns_id="parent")
        child1 = PIDNamespace(parent=parent, ns_id="child1")
        child2 = PIDNamespace(parent=parent, ns_id="child2")
        assert len(parent.children) == 2

    def test_get_children_of_nonexistent(self):
        ns = PIDNamespace()
        assert ns.get_children_of(999) == []

    def test_leave_member_only(self):
        ns = PIDNamespace()
        ns._member_pids.add(42)
        ns._ref_count = 1
        ns.leave(42)
        assert 42 not in ns.member_pids


# ============================================================
# NETNamespace Tests
# ============================================================


class TestNETNamespace:
    """Validate NET namespace network stack isolation."""

    def test_create_with_loopback(self):
        ns = NETNamespace()
        assert LOOPBACK_INTERFACE in ns.interfaces
        lo = ns.interfaces[LOOPBACK_INTERFACE]
        assert lo.state == "up"
        assert LOOPBACK_IPV4 in lo.ipv4_addresses

    def test_add_interface(self):
        ns = NETNamespace()
        iface = ns.add_interface("eth0")
        assert "eth0" in ns.interfaces
        assert iface.state == "down"

    def test_add_duplicate_interface(self):
        ns = NETNamespace()
        ns.add_interface("eth0")
        with pytest.raises(NETNamespaceError):
            ns.add_interface("eth0")

    def test_remove_interface(self):
        ns = NETNamespace()
        ns.add_interface("eth0")
        ns.remove_interface("eth0")
        assert "eth0" not in ns.interfaces

    def test_remove_loopback_fails(self):
        ns = NETNamespace()
        with pytest.raises(NETNamespaceError):
            ns.remove_interface(LOOPBACK_INTERFACE)

    def test_remove_nonexistent_interface(self):
        ns = NETNamespace()
        with pytest.raises(NETNamespaceError):
            ns.remove_interface("nonexistent")

    def test_set_interface_state(self):
        ns = NETNamespace()
        ns.add_interface("eth0")
        ns.set_interface_state("eth0", "up")
        assert ns.interfaces["eth0"].state == "up"

    def test_set_invalid_state(self):
        ns = NETNamespace()
        ns.add_interface("eth0")
        with pytest.raises(NETNamespaceError):
            ns.set_interface_state("eth0", "invalid")

    def test_assign_ipv4(self):
        ns = NETNamespace()
        ns.add_interface("eth0")
        ns.assign_ipv4("eth0", "10.0.0.1")
        assert "10.0.0.1" in ns.interfaces["eth0"].ipv4_addresses

    def test_assign_ipv6(self):
        ns = NETNamespace()
        ns.add_interface("eth0")
        ns.assign_ipv6("eth0", "fe80::1")
        assert "fe80::1" in ns.interfaces["eth0"].ipv6_addresses

    def test_assign_ip_nonexistent_interface(self):
        ns = NETNamespace()
        with pytest.raises(NETNamespaceError):
            ns.assign_ipv4("nonexistent", "10.0.0.1")

    def test_add_route(self):
        ns = NETNamespace()
        entry = ns.add_route("0.0.0.0/0", "10.0.0.1", LOOPBACK_INTERFACE)
        assert entry.destination == "0.0.0.0/0"
        assert len(ns.routing_table) == 2  # loopback route + new

    def test_add_route_nonexistent_interface(self):
        ns = NETNamespace()
        with pytest.raises(NETNamespaceError):
            ns.add_route("0.0.0.0/0", "10.0.0.1", "nonexistent")

    def test_remove_route(self):
        ns = NETNamespace()
        ns.add_route("10.0.0.0/24", "10.0.0.1", LOOPBACK_INTERFACE)
        ns.remove_route("10.0.0.0/24")
        assert not any(r.destination == "10.0.0.0/24" for r in ns.routing_table)

    def test_remove_nonexistent_route(self):
        ns = NETNamespace()
        with pytest.raises(NETNamespaceError):
            ns.remove_route("192.168.0.0/16")

    def test_bind_socket(self):
        ns = NETNamespace()
        binding = ns.bind_socket("tcp", "0.0.0.0", 80, pid=1)
        assert binding.port == 80
        assert binding.state == "listening"

    def test_bind_duplicate_socket(self):
        ns = NETNamespace()
        ns.bind_socket("tcp", "0.0.0.0", 80)
        with pytest.raises(NETNamespaceError):
            ns.bind_socket("tcp", "0.0.0.0", 80)

    def test_unbind_socket(self):
        ns = NETNamespace()
        ns.bind_socket("tcp", "0.0.0.0", 80)
        ns.unbind_socket("tcp", "0.0.0.0", 80)
        assert all(b.state == "closed" for b in ns.socket_bindings if b.port == 80)

    def test_unbind_nonexistent_socket(self):
        ns = NETNamespace()
        with pytest.raises(NETNamespaceError):
            ns.unbind_socket("tcp", "0.0.0.0", 9999)

    def test_port_isolation_between_namespaces(self):
        ns1 = NETNamespace()
        ns2 = NETNamespace()
        ns1.bind_socket("tcp", "0.0.0.0", 80)
        ns2.bind_socket("tcp", "0.0.0.0", 80)  # Should not conflict
        assert ns1.get_binding_count() == 1
        assert ns2.get_binding_count() == 1

    def test_veth_pair(self):
        ns1 = NETNamespace()
        ns2 = NETNamespace()
        pair = ns1.create_veth_pair(ns2, "veth0", "eth0")
        assert pair.host_ns_id == ns1.ns_id
        assert pair.container_ns_id == ns2.ns_id
        assert "veth0" in ns1.interfaces
        assert "eth0" in ns2.interfaces

    def test_interface_count(self):
        ns = NETNamespace()
        assert ns.get_interface_count() == 1  # loopback
        ns.add_interface("eth0")
        assert ns.get_interface_count() == 2

    def test_auto_mac_address(self):
        ns = NETNamespace()
        iface = ns.add_interface("eth0")
        assert len(iface.mac_address) > 0

    def test_arp_table(self):
        ns = NETNamespace()
        assert isinstance(ns.arp_table, dict)

    def test_enter_and_leave(self):
        ns = NETNamespace()
        ns.enter(100)
        assert 100 in ns.member_pids
        ns.leave(100)
        assert 100 not in ns.member_pids

    def test_destroy_empty(self):
        ns = NETNamespace()
        ns.destroy()
        assert ns.state == NamespaceState.DESTROYED

    def test_destroy_with_members(self):
        ns = NETNamespace()
        ns.add_member(100)
        with pytest.raises(NamespaceDestroyError):
            ns.destroy()

    def test_enter_destroyed(self):
        ns = NETNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(NamespaceEntryError):
            ns.enter(100)

    def test_veth_pair_id(self):
        ns1 = NETNamespace()
        ns2 = NETNamespace()
        pair = ns1.create_veth_pair(ns2)
        assert pair.pair_id.startswith("veth-")

    def test_loopback_ipv6(self):
        ns = NETNamespace()
        lo = ns.interfaces[LOOPBACK_INTERFACE]
        assert LOOPBACK_IPV6 in lo.ipv6_addresses

    def test_loopback_mtu(self):
        ns = NETNamespace()
        lo = ns.interfaces[LOOPBACK_INTERFACE]
        assert lo.mtu == 65536

    def test_routing_table_has_loopback_route(self):
        ns = NETNamespace()
        assert any(r.destination == "127.0.0.0/8" for r in ns.routing_table)


# ============================================================
# MNTNamespace Tests
# ============================================================


class TestMNTNamespace:
    """Validate MNT namespace mount table isolation."""

    def test_create_with_defaults(self):
        ns = MNTNamespace()
        assert ns.mount_count > 0
        assert ns.root_path == "/"

    def test_copy_parent_mounts(self):
        parent = MNTNamespace()
        parent_count = parent.mount_count
        child = MNTNamespace(parent=parent)
        assert child.mount_count == parent_count

    def test_mount(self):
        ns = MNTNamespace()
        initial_count = ns.mount_count
        entry = ns.mount("/dev/sdb1", "/data", "ext4")
        assert ns.mount_count == initial_count + 1
        assert entry.target == "/data"

    def test_mount_with_options(self):
        ns = MNTNamespace()
        entry = ns.mount("/dev/sdb1", "/data", "ext4", options="ro,noexec")
        assert entry.options == "ro,noexec"

    def test_mount_with_propagation(self):
        ns = MNTNamespace()
        entry = ns.mount("/dev/sdb1", "/data", "ext4", propagation="shared")
        assert entry.propagation == "shared"

    def test_mount_invalid_propagation(self):
        ns = MNTNamespace()
        with pytest.raises(MNTNamespaceError):
            ns.mount("/dev/sdb1", "/data", "ext4", propagation="invalid")

    def test_umount(self):
        ns = MNTNamespace()
        ns.mount("/dev/sdb1", "/data", "ext4")
        initial_count = ns.mount_count
        ns.umount("/data")
        assert ns.mount_count == initial_count - 1

    def test_umount_nonexistent(self):
        ns = MNTNamespace()
        with pytest.raises(MNTNamespaceError):
            ns.umount("/nonexistent")

    def test_pivot_root(self):
        ns = MNTNamespace()
        ns.pivot_root("/newroot", "/oldroot")
        assert ns.root_path == "/newroot"
        assert ns.old_root_path == "/"

    def test_pivot_root_empty_new_root(self):
        ns = MNTNamespace()
        with pytest.raises(MNTNamespaceError):
            ns.pivot_root("", "/oldroot")

    def test_pivot_root_empty_put_old(self):
        ns = MNTNamespace()
        with pytest.raises(MNTNamespaceError):
            ns.pivot_root("/newroot", "")

    def test_find_mount(self):
        ns = MNTNamespace()
        mount = ns.find_mount("/")
        assert mount is not None
        assert mount.target == "/"

    def test_find_mount_nonexistent(self):
        ns = MNTNamespace()
        assert ns.find_mount("/nonexistent") is None

    def test_get_mounts_by_type(self):
        ns = MNTNamespace()
        tmpfs_mounts = ns.get_mounts_by_type("tmpfs")
        assert len(tmpfs_mounts) > 0

    def test_set_propagation(self):
        ns = MNTNamespace()
        ns.set_propagation("/", "shared")
        mount = ns.find_mount("/")
        assert mount.propagation == "shared"

    def test_set_propagation_invalid(self):
        ns = MNTNamespace()
        with pytest.raises(MNTNamespaceError):
            ns.set_propagation("/", "invalid")

    def test_set_propagation_nonexistent(self):
        ns = MNTNamespace()
        with pytest.raises(MNTNamespaceError):
            ns.set_propagation("/nonexistent", "shared")

    def test_mount_isolation(self):
        parent = MNTNamespace()
        child = MNTNamespace(parent=parent)
        initial_parent_count = parent.mount_count
        child.mount("/container-data", "tmpfs", "tmpfs")
        assert parent.mount_count == initial_parent_count  # Parent unaffected

    def test_mount_in_destroyed(self):
        ns = MNTNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(MNTNamespaceError):
            ns.mount("/data", "src", "ext4")

    def test_umount_in_destroyed(self):
        ns = MNTNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(MNTNamespaceError):
            ns.umount("/tmp")

    def test_pivot_root_in_destroyed(self):
        ns = MNTNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(MNTNamespaceError):
            ns.pivot_root("/new", "/old")

    def test_enter_and_leave(self):
        ns = MNTNamespace()
        ns.enter(100)
        assert 100 in ns.member_pids
        ns.leave(100)
        assert 100 not in ns.member_pids

    def test_destroy(self):
        ns = MNTNamespace()
        ns.destroy()
        assert ns.state == NamespaceState.DESTROYED

    def test_destroy_with_members(self):
        ns = MNTNamespace()
        ns.add_member(100)
        with pytest.raises(NamespaceDestroyError):
            ns.destroy()

    def test_default_mount_table_has_proc(self):
        ns = MNTNamespace()
        proc = ns.find_mount("/proc")
        assert proc is not None
        assert proc.fs_type == "proc"

    def test_default_mount_table_has_dev(self):
        ns = MNTNamespace()
        dev = ns.find_mount("/dev")
        assert dev is not None

    def test_mount_entry_is_frozen(self):
        ns = MNTNamespace()
        entry = ns.mount("/test", "src", "tmpfs")
        with pytest.raises(AttributeError):
            entry.target = "/changed"


# ============================================================
# UTSNamespace Tests
# ============================================================


class TestUTSNamespace:
    """Validate UTS namespace hostname/domainname isolation."""

    def test_default_hostname(self):
        ns = UTSNamespace()
        assert ns.hostname == DEFAULT_HOSTNAME

    def test_default_domainname(self):
        ns = UTSNamespace()
        assert ns.domainname == DEFAULT_DOMAINNAME

    def test_custom_hostname(self):
        ns = UTSNamespace(hostname="custom-host")
        assert ns.hostname == "custom-host"

    def test_sethostname(self):
        ns = UTSNamespace()
        ns.sethostname("new-host")
        assert ns.hostname == "new-host"
        assert ns.gethostname() == "new-host"

    def test_sethostname_empty(self):
        ns = UTSNamespace()
        with pytest.raises(UTSNamespaceError):
            ns.sethostname("")

    def test_sethostname_too_long(self):
        ns = UTSNamespace()
        with pytest.raises(UTSNamespaceError):
            ns.sethostname("a" * 65)

    def test_setdomainname(self):
        ns = UTSNamespace()
        ns.setdomainname("new.domain")
        assert ns.domainname == "new.domain"
        assert ns.getdomainname() == "new.domain"

    def test_setdomainname_too_long(self):
        ns = UTSNamespace()
        with pytest.raises(UTSNamespaceError):
            ns.setdomainname("a" * 65)

    def test_hostname_history(self):
        ns = UTSNamespace()
        ns.sethostname("host-2")
        ns.sethostname("host-3")
        history = ns.hostname_history
        assert len(history) == 3  # initial + 2 changes
        assert history[0]["action"] == "initial"

    def test_hostname_isolation(self):
        ns1 = UTSNamespace(hostname="host-1")
        ns2 = UTSNamespace(hostname="host-2")
        assert ns1.hostname != ns2.hostname
        ns1.sethostname("changed")
        assert ns2.hostname == "host-2"  # Unaffected

    def test_enter_and_leave(self):
        ns = UTSNamespace()
        ns.enter(100)
        assert 100 in ns.member_pids
        ns.leave(100)
        assert 100 not in ns.member_pids

    def test_destroy(self):
        ns = UTSNamespace()
        ns.destroy()
        assert ns.state == NamespaceState.DESTROYED

    def test_destroy_with_members(self):
        ns = UTSNamespace()
        ns.add_member(100)
        with pytest.raises(NamespaceDestroyError):
            ns.destroy()

    def test_sethostname_in_destroyed(self):
        ns = UTSNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(UTSNamespaceError):
            ns.sethostname("test")

    def test_setdomainname_in_destroyed(self):
        ns = UTSNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(UTSNamespaceError):
            ns.setdomainname("test")


# ============================================================
# IPCNamespace Tests
# ============================================================


class TestIPCNamespace:
    """Validate IPC namespace System V IPC isolation."""

    def test_create_empty(self):
        ns = IPCNamespace()
        assert ns.shm_count == 0
        assert ns.sem_count == 0
        assert ns.msq_count == 0

    def test_shmget(self):
        ns = IPCNamespace()
        shm_id = ns.shmget(key=100, size=4096)
        assert shm_id == 0
        assert ns.shm_count == 1

    def test_shmget_existing_key(self):
        ns = IPCNamespace()
        id1 = ns.shmget(key=100, size=4096)
        id2 = ns.shmget(key=100, size=4096)
        assert id1 == id2
        assert ns.shm_count == 1

    def test_shmctl_rm(self):
        ns = IPCNamespace()
        shm_id = ns.shmget(key=100, size=4096)
        ns.shmctl_rm(shm_id)
        assert ns.shm_count == 0

    def test_shmctl_rm_nonexistent(self):
        ns = IPCNamespace()
        with pytest.raises(IPCNamespaceError):
            ns.shmctl_rm(999)

    def test_shmat(self):
        ns = IPCNamespace()
        shm_id = ns.shmget(key=100, size=4096)
        ns.shmat(shm_id, pid=1)
        assert 1 in ns.shm_segments[shm_id].attached_pids

    def test_shmdt(self):
        ns = IPCNamespace()
        shm_id = ns.shmget(key=100, size=4096)
        ns.shmat(shm_id, pid=1)
        ns.shmdt(shm_id, pid=1)
        assert 1 not in ns.shm_segments[shm_id].attached_pids

    def test_semget(self):
        ns = IPCNamespace()
        sem_id = ns.semget(key=200, num_sems=4)
        assert sem_id == 0
        assert ns.sem_count == 1

    def test_semget_existing_key(self):
        ns = IPCNamespace()
        id1 = ns.semget(key=200, num_sems=4)
        id2 = ns.semget(key=200, num_sems=4)
        assert id1 == id2

    def test_semctl_rm(self):
        ns = IPCNamespace()
        sem_id = ns.semget(key=200, num_sems=4)
        ns.semctl_rm(sem_id)
        assert ns.sem_count == 0

    def test_semctl_rm_nonexistent(self):
        ns = IPCNamespace()
        with pytest.raises(IPCNamespaceError):
            ns.semctl_rm(999)

    def test_msgget(self):
        ns = IPCNamespace()
        msq_id = ns.msgget(key=300)
        assert msq_id == 0
        assert ns.msq_count == 1

    def test_msgget_existing_key(self):
        ns = IPCNamespace()
        id1 = ns.msgget(key=300)
        id2 = ns.msgget(key=300)
        assert id1 == id2

    def test_msgctl_rm(self):
        ns = IPCNamespace()
        msq_id = ns.msgget(key=300)
        ns.msgctl_rm(msq_id)
        assert ns.msq_count == 0

    def test_msgctl_rm_nonexistent(self):
        ns = IPCNamespace()
        with pytest.raises(IPCNamespaceError):
            ns.msgctl_rm(999)

    def test_msgsnd(self):
        ns = IPCNamespace()
        msq_id = ns.msgget(key=300)
        ns.msgsnd(msq_id)
        assert ns.message_queues[msq_id].message_count == 1

    def test_msgrcv(self):
        ns = IPCNamespace()
        msq_id = ns.msgget(key=300)
        ns.msgsnd(msq_id)
        ns.msgrcv(msq_id)
        assert ns.message_queues[msq_id].message_count == 0

    def test_msgrcv_empty_queue(self):
        ns = IPCNamespace()
        msq_id = ns.msgget(key=300)
        with pytest.raises(IPCNamespaceError):
            ns.msgrcv(msq_id)

    def test_ipc_isolation(self):
        ns1 = IPCNamespace()
        ns2 = IPCNamespace()
        ns1.shmget(key=100, size=4096)
        assert ns2.shm_count == 0  # Isolated

    def test_total_ipc_objects(self):
        ns = IPCNamespace()
        ns.shmget(key=100, size=4096)
        ns.semget(key=200, num_sems=4)
        ns.msgget(key=300)
        assert ns.get_total_ipc_objects() == 3

    def test_enter_and_leave(self):
        ns = IPCNamespace()
        ns.enter(100)
        assert 100 in ns.member_pids
        ns.leave(100)
        assert 100 not in ns.member_pids

    def test_destroy(self):
        ns = IPCNamespace()
        ns.shmget(key=100, size=4096)
        ns.destroy()
        assert ns.state == NamespaceState.DESTROYED
        assert ns.shm_count == 0

    def test_destroy_with_members(self):
        ns = IPCNamespace()
        ns.add_member(100)
        with pytest.raises(NamespaceDestroyError):
            ns.destroy()

    def test_shmget_in_destroyed(self):
        ns = IPCNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(IPCNamespaceError):
            ns.shmget(key=100, size=4096)


# ============================================================
# USERNamespace Tests
# ============================================================


class TestUSERNamespace:
    """Validate USER namespace UID/GID mapping and capability isolation."""

    def test_create_default(self):
        ns = USERNamespace()
        assert ns.owner_uid == 1000
        assert ns.owner_gid == 1000
        assert ns.is_rootless is True

    def test_create_root(self):
        ns = USERNamespace(owner_uid=0, owner_gid=0)
        assert ns.is_rootless is False

    def test_add_uid_mapping(self):
        ns = USERNamespace()
        ns.add_uid_mapping(0, 1000, 1)
        assert len(ns.uid_map) == 1

    def test_add_gid_mapping(self):
        ns = USERNamespace()
        ns.add_gid_mapping(0, 1000, 1)
        assert len(ns.gid_map) == 1

    def test_uid_mapping_zero_count(self):
        ns = USERNamespace()
        with pytest.raises(USERNamespaceError):
            ns.add_uid_mapping(0, 1000, 0)

    def test_gid_mapping_zero_count(self):
        ns = USERNamespace()
        with pytest.raises(USERNamespaceError):
            ns.add_gid_mapping(0, 1000, 0)

    def test_overlapping_uid_mapping(self):
        ns = USERNamespace()
        ns.add_uid_mapping(0, 1000, 10)
        with pytest.raises(USERNamespaceError):
            ns.add_uid_mapping(5, 2000, 10)

    def test_overlapping_gid_mapping(self):
        ns = USERNamespace()
        ns.add_gid_mapping(0, 1000, 10)
        with pytest.raises(USERNamespaceError):
            ns.add_gid_mapping(5, 2000, 10)

    def test_translate_uid_to_host(self):
        ns = USERNamespace()
        ns.add_uid_mapping(0, 1000, 65536)
        assert ns.translate_uid_to_host(0) == 1000
        assert ns.translate_uid_to_host(1000) == 2000

    def test_translate_uid_unmapped(self):
        ns = USERNamespace()
        assert ns.translate_uid_to_host(0) == NOBODY_UID

    def test_translate_uid_from_host(self):
        ns = USERNamespace()
        ns.add_uid_mapping(0, 1000, 65536)
        assert ns.translate_uid_from_host(1000) == 0

    def test_translate_gid_to_host(self):
        ns = USERNamespace()
        ns.add_gid_mapping(0, 1000, 65536)
        assert ns.translate_gid_to_host(0) == 1000

    def test_translate_gid_unmapped(self):
        ns = USERNamespace()
        assert ns.translate_gid_to_host(0) == NOBODY_GID

    def test_translate_gid_from_host(self):
        ns = USERNamespace()
        ns.add_gid_mapping(0, 1000, 65536)
        assert ns.translate_gid_from_host(1000) == 0

    def test_capabilities_initial(self):
        ns = USERNamespace()
        assert len(ns.capabilities) == len(USERNamespace.ALL_CAPABILITIES)

    def test_has_capability(self):
        ns = USERNamespace()
        assert ns.has_capability("CAP_NET_ADMIN") is True

    def test_drop_capability(self):
        ns = USERNamespace()
        ns.drop_capability("CAP_NET_ADMIN")
        assert ns.has_capability("CAP_NET_ADMIN") is False

    def test_add_capability(self):
        ns = USERNamespace()
        ns.drop_capability("CAP_NET_ADMIN")
        ns.add_capability("CAP_NET_ADMIN")
        assert ns.has_capability("CAP_NET_ADMIN") is True

    def test_drop_unknown_capability(self):
        ns = USERNamespace()
        with pytest.raises(USERNamespaceError):
            ns.drop_capability("CAP_UNKNOWN")

    def test_add_unknown_capability(self):
        ns = USERNamespace()
        with pytest.raises(USERNamespaceError):
            ns.add_capability("CAP_UNKNOWN")

    def test_set_rootless(self):
        ns = USERNamespace()
        ns.set_rootless()
        assert ns.is_rootless is True
        assert len(ns.uid_map) == 1
        assert len(ns.gid_map) == 1

    def test_set_rootless_idempotent(self):
        ns = USERNamespace()
        ns.set_rootless()
        ns.set_rootless()  # Should not add duplicate mappings
        assert len(ns.uid_map) == 1

    def test_get_effective_uid(self):
        ns = USERNamespace()
        ns.add_uid_mapping(0, 1000, 1)
        info = ns.get_effective_uid(0)
        assert info["is_root_inside"] is True
        assert info["is_root_outside"] is False
        assert info["is_mapped"] is True

    def test_uid_isolation_between_namespaces(self):
        ns1 = USERNamespace()
        ns2 = USERNamespace()
        ns1.add_uid_mapping(0, 1000, 1)
        ns2.add_uid_mapping(0, 2000, 1)
        assert ns1.translate_uid_to_host(0) == 1000
        assert ns2.translate_uid_to_host(0) == 2000

    def test_enter_and_leave(self):
        ns = USERNamespace()
        ns.enter(100)
        assert 100 in ns.member_pids
        ns.leave(100)
        assert 100 not in ns.member_pids

    def test_destroy(self):
        ns = USERNamespace()
        ns.destroy()
        assert ns.state == NamespaceState.DESTROYED

    def test_destroy_with_members(self):
        ns = USERNamespace()
        ns.add_member(100)
        with pytest.raises(NamespaceDestroyError):
            ns.destroy()

    def test_multiple_uid_ranges(self):
        ns = USERNamespace()
        ns.add_uid_mapping(0, 1000, 100)
        ns.add_uid_mapping(100, 2000, 100)
        assert ns.translate_uid_to_host(0) == 1000
        assert ns.translate_uid_to_host(100) == 2000

    def test_nobody_uid_for_unmapped(self):
        ns = USERNamespace()
        ns.add_uid_mapping(0, 1000, 1)
        assert ns.translate_uid_to_host(999) == NOBODY_UID

    def test_nobody_gid_for_unmapped(self):
        ns = USERNamespace()
        ns.add_gid_mapping(0, 1000, 1)
        assert ns.translate_gid_to_host(999) == NOBODY_GID


# ============================================================
# CGROUPNamespace Tests
# ============================================================


class TestCGROUPNamespace:
    """Validate CGROUP namespace hierarchy virtualization."""

    def test_create_with_root(self):
        ns = CGROUPNamespace()
        assert ns.cgroup_root == "/"
        assert "/" in ns.cgroup_entries

    def test_custom_root(self):
        ns = CGROUPNamespace(cgroup_root="/docker/abc123")
        assert ns.cgroup_root == "/docker/abc123"

    def test_add_cgroup(self):
        ns = CGROUPNamespace()
        entry = ns.add_cgroup("/app")
        assert entry.path == "/app"
        assert ns.entry_count == 2  # root + /app

    def test_add_duplicate_cgroup(self):
        ns = CGROUPNamespace()
        ns.add_cgroup("/app")
        with pytest.raises(CGROUPNamespaceError):
            ns.add_cgroup("/app")

    def test_remove_cgroup(self):
        ns = CGROUPNamespace()
        ns.add_cgroup("/app")
        ns.remove_cgroup("/app")
        assert ns.entry_count == 1

    def test_remove_root_cgroup(self):
        ns = CGROUPNamespace()
        with pytest.raises(CGROUPNamespaceError):
            ns.remove_cgroup("/")

    def test_remove_nonexistent_cgroup(self):
        ns = CGROUPNamespace()
        with pytest.raises(CGROUPNamespaceError):
            ns.remove_cgroup("/nonexistent")

    def test_add_process_to_cgroup(self):
        ns = CGROUPNamespace()
        ns.add_process_to_cgroup("/", 100)
        assert 100 in ns.cgroup_entries["/"].processes

    def test_remove_process_from_cgroup(self):
        ns = CGROUPNamespace()
        ns.add_process_to_cgroup("/", 100)
        ns.remove_process_from_cgroup("/", 100)
        assert 100 not in ns.cgroup_entries["/"].processes

    def test_virtualize_path_visible(self):
        ns = CGROUPNamespace(cgroup_root="/docker/abc123")
        result = ns.virtualize_path("/docker/abc123/memory")
        assert result == "/memory"

    def test_virtualize_path_root(self):
        ns = CGROUPNamespace(cgroup_root="/docker/abc123")
        result = ns.virtualize_path("/docker/abc123")
        assert result == "/"

    def test_virtualize_path_invisible(self):
        ns = CGROUPNamespace(cgroup_root="/docker/abc123")
        result = ns.virtualize_path("/docker/def456")
        assert result == ""

    def test_is_visible(self):
        ns = CGROUPNamespace(cgroup_root="/docker/abc123")
        assert ns.is_visible("/docker/abc123/cpu") is True
        assert ns.is_visible("/docker/def456") is False

    def test_controllers(self):
        ns = CGROUPNamespace()
        assert "cpu" in ns.controllers
        assert "memory" in ns.controllers

    def test_get_controllers_for_path(self):
        ns = CGROUPNamespace()
        controllers = ns.get_controllers_for_path("/")
        assert "cpu" in controllers

    def test_get_controllers_nonexistent_path(self):
        ns = CGROUPNamespace()
        with pytest.raises(CGROUPNamespaceError):
            ns.get_controllers_for_path("/nonexistent")

    def test_isolate_adds_to_root_cgroup(self):
        ns = CGROUPNamespace()
        ns.isolate(100)
        assert 100 in ns.cgroup_entries["/"].processes
        assert 100 in ns.member_pids

    def test_enter_adds_to_root_cgroup(self):
        ns = CGROUPNamespace()
        ns.enter(100)
        assert 100 in ns.cgroup_entries["/"].processes

    def test_leave_removes_from_all_cgroups(self):
        ns = CGROUPNamespace()
        ns.enter(100)
        ns.leave(100)
        assert 100 not in ns.cgroup_entries["/"].processes
        assert 100 not in ns.member_pids

    def test_destroy(self):
        ns = CGROUPNamespace()
        ns.destroy()
        assert ns.state == NamespaceState.DESTROYED

    def test_destroy_with_members(self):
        ns = CGROUPNamespace()
        ns.add_member(100)
        with pytest.raises(NamespaceDestroyError):
            ns.destroy()

    def test_add_cgroup_in_destroyed(self):
        ns = CGROUPNamespace()
        ns._state = NamespaceState.DESTROYED
        with pytest.raises(CGROUPNamespaceError):
            ns.add_cgroup("/app")


# ============================================================
# VethPair Tests
# ============================================================


class TestVethPair:
    """Validate VethPair dataclass."""

    def test_create(self):
        pair = VethPair(
            pair_id="veth-001",
            host_interface="veth0",
            container_interface="eth0",
            host_ns_id="ns-host",
            container_ns_id="ns-container",
        )
        assert pair.pair_id == "veth-001"
        assert pair.host_interface == "veth0"
        assert pair.container_interface == "eth0"

    def test_frozen(self):
        pair = VethPair(
            pair_id="veth-001",
            host_interface="veth0",
            container_interface="eth0",
            host_ns_id="ns-host",
            container_ns_id="ns-container",
        )
        with pytest.raises(AttributeError):
            pair.pair_id = "changed"

    def test_created_at(self):
        pair = VethPair(
            pair_id="veth-001",
            host_interface="veth0",
            container_interface="eth0",
            host_ns_id="ns-host",
            container_ns_id="ns-container",
        )
        assert pair.created_at > 0


# ============================================================
# MountEntry Tests
# ============================================================


class TestMountEntry:
    """Validate MountEntry dataclass."""

    def test_create(self):
        entry = MountEntry(
            mount_id="mnt-001",
            source="/dev/sda1",
            target="/",
            fs_type="ext4",
        )
        assert entry.target == "/"
        assert entry.options == "rw"
        assert entry.propagation == "private"

    def test_frozen(self):
        entry = MountEntry(
            mount_id="mnt-001",
            source="/dev/sda1",
            target="/",
            fs_type="ext4",
        )
        with pytest.raises(AttributeError):
            entry.target = "/changed"


# ============================================================
# NamespaceManager Tests
# ============================================================


class TestNamespaceManager:
    """Validate NamespaceManager singleton lifecycle management."""

    def test_singleton(self):
        m1 = NamespaceManager()
        m2 = NamespaceManager()
        assert m1 is m2

    def test_root_namespaces_created(self):
        manager = NamespaceManager()
        root = manager.root_namespaces
        assert root.count == 7
        for ns_type in NamespaceType:
            assert root.has(ns_type)

    def test_root_namespace_ids(self):
        manager = NamespaceManager()
        root = manager.root_namespaces
        pid_ns = root.get(NamespaceType.PID)
        assert pid_ns.ns_id == "ns-pid-root"

    def test_clone_all_namespaces(self):
        manager = NamespaceManager()
        flags = CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWIPC | CLONE_NEWUSER | CLONE_NEWCGROUP
        ns_set = manager.clone(pid=100, flags=flags)
        assert ns_set.count == 7
        # Check that new namespaces are different from root
        for ns_type in NamespaceType:
            ns = ns_set.get(ns_type)
            root_ns = manager.root_namespaces.get(ns_type)
            assert ns is not root_ns

    def test_clone_partial(self):
        manager = NamespaceManager()
        ns_set = manager.clone(pid=100, flags=CLONE_NEWPID)
        pid_ns = ns_set.get(NamespaceType.PID)
        net_ns = ns_set.get(NamespaceType.NET)
        # PID should be new, NET should be root
        root_pid = manager.root_namespaces.get(NamespaceType.PID)
        root_net = manager.root_namespaces.get(NamespaceType.NET)
        assert pid_ns is not root_pid
        assert net_ns is root_net

    def test_unshare(self):
        manager = NamespaceManager()
        ns_set = manager.unshare(pid=100, flags=CLONE_NEWUTS)
        uts_ns = ns_set.get(NamespaceType.UTS)
        root_uts = manager.root_namespaces.get(NamespaceType.UTS)
        assert uts_ns is not root_uts

    def test_setns(self):
        manager = NamespaceManager()
        # Create a new PID namespace
        ns_set = manager.clone(pid=100, flags=CLONE_NEWPID)
        target_pid_ns = ns_set.get(NamespaceType.PID)
        # Move another process into it
        manager.setns(200, target_pid_ns.ns_id)
        assert 200 in target_pid_ns.member_pids

    def test_setns_nonexistent(self):
        manager = NamespaceManager()
        with pytest.raises(NamespaceEntryError):
            manager.setns(100, "nonexistent-ns-id")

    def test_get_namespace(self):
        manager = NamespaceManager()
        ns = manager.get_namespace("ns-pid-root")
        assert ns is not None
        assert ns.ns_type == NamespaceType.PID

    def test_get_namespace_nonexistent(self):
        manager = NamespaceManager()
        assert manager.get_namespace("nonexistent") is None

    def test_get_namespaces_by_type(self):
        manager = NamespaceManager()
        pid_nss = manager.get_namespaces_by_type(NamespaceType.PID)
        assert len(pid_nss) >= 1

    def test_destroy_namespace(self):
        manager = NamespaceManager()
        ns_set = manager.clone(pid=100, flags=CLONE_NEWUTS)
        uts_ns = ns_set.get(NamespaceType.UTS)
        # Remove process first
        manager.remove_process(100)
        manager.destroy_namespace(uts_ns.ns_id)
        assert uts_ns.state == NamespaceState.DESTROYED

    def test_destroy_root_namespace(self):
        manager = NamespaceManager()
        with pytest.raises(NamespaceDestroyError):
            manager.destroy_namespace("ns-pid-root")

    def test_destroy_nonexistent(self):
        manager = NamespaceManager()
        with pytest.raises(NamespaceManagerError):
            manager.destroy_namespace("nonexistent")

    def test_garbage_collect(self):
        manager = NamespaceManager()
        manager.clone(pid=100, flags=CLONE_NEWUTS)
        manager.remove_process(100)
        collected = manager.garbage_collect()
        assert collected >= 0
        assert manager.gc_count == 1

    def test_remove_process(self):
        manager = NamespaceManager()
        ns_set = manager.clone(pid=100, flags=CLONE_NEWNET)
        net_ns = ns_set.get(NamespaceType.NET)
        manager.setns(100, net_ns.ns_id)
        manager.remove_process(100)
        assert 100 not in manager.process_namespaces

    def test_get_process_namespace(self):
        manager = NamespaceManager()
        manager.clone(pid=100, flags=CLONE_NEWPID)
        ns = manager.get_process_namespace(100, NamespaceType.PID)
        assert ns is not None

    def test_get_process_namespace_no_process(self):
        manager = NamespaceManager()
        assert manager.get_process_namespace(999, NamespaceType.PID) is None

    def test_statistics(self):
        manager = NamespaceManager()
        stats = manager.get_statistics()
        assert stats["total_created"] == 7
        assert stats["active_count"] == 7
        assert "type_counts" in stats

    def test_total_created_increments(self):
        manager = NamespaceManager()
        initial = manager.total_created
        manager.clone(pid=100, flags=CLONE_NEWPID)
        assert manager.total_created > initial

    def test_active_count(self):
        manager = NamespaceManager()
        assert manager.active_count == 7  # Root namespaces

    def test_render_hierarchy(self):
        manager = NamespaceManager()
        manager.clone(pid=100, flags=CLONE_NEWPID | CLONE_NEWNET)
        output = manager.render_hierarchy()
        assert "Namespace Hierarchy" in output
        assert "PID Namespaces:" in output

    def test_render_hierarchy_filtered(self):
        manager = NamespaceManager()
        output = manager.render_hierarchy(ns_type=NamespaceType.PID)
        assert "PID Namespaces:" in output
        assert "NET Namespaces:" not in output

    def test_list_namespaces(self):
        manager = NamespaceManager()
        ns_list = manager.list_namespaces()
        assert len(ns_list) == 7  # Root namespaces
        assert all("ns_id" in ns for ns in ns_list)

    def test_list_namespaces_filtered(self):
        manager = NamespaceManager()
        ns_list = manager.list_namespaces(ns_type=NamespaceType.PID)
        assert len(ns_list) == 1

    def test_inspect_namespace(self):
        manager = NamespaceManager()
        info = manager.inspect_namespace("ns-pid-root")
        assert info["ns_id"] == "ns-pid-root"
        assert info["type"] == "PID"
        assert info["is_root"] is True

    def test_inspect_nonexistent(self):
        manager = NamespaceManager()
        with pytest.raises(NamespaceManagerError):
            manager.inspect_namespace("nonexistent")

    def test_inspect_pid_namespace(self):
        manager = NamespaceManager()
        info = manager.inspect_namespace("ns-pid-root")
        assert "init_pid" in info
        assert "pid_count" in info

    def test_inspect_net_namespace(self):
        manager = NamespaceManager()
        info = manager.inspect_namespace("ns-net-root")
        assert "interface_count" in info

    def test_inspect_mnt_namespace(self):
        manager = NamespaceManager()
        info = manager.inspect_namespace("ns-mnt-root")
        assert "mount_count" in info

    def test_inspect_uts_namespace(self):
        manager = NamespaceManager()
        info = manager.inspect_namespace("ns-uts-root")
        assert "hostname" in info

    def test_inspect_ipc_namespace(self):
        manager = NamespaceManager()
        info = manager.inspect_namespace("ns-ipc-root")
        assert "shm_count" in info

    def test_inspect_user_namespace(self):
        manager = NamespaceManager()
        info = manager.inspect_namespace("ns-user-root")
        assert "is_rootless" in info

    def test_inspect_cgroup_namespace(self):
        manager = NamespaceManager()
        info = manager.inspect_namespace("ns-cgroup-root")
        assert "cgroup_root" in info

    def test_clone_with_parent_pid(self):
        manager = NamespaceManager()
        manager.clone(pid=100, flags=CLONE_NEWPID)
        ns_set = manager.clone(pid=200, flags=CLONE_NEWPID, parent_pid=100)
        assert ns_set.count == 7

    def test_default_hostname_propagates(self):
        manager = NamespaceManager(default_hostname="custom-host")
        ns_set = manager.clone(pid=100, flags=CLONE_NEWUTS)
        uts_ns = ns_set.get(NamespaceType.UTS)
        assert uts_ns.hostname == "custom-host"

    def test_event_bus_integration(self):
        bus = MagicMock()
        manager = NamespaceManager(event_bus=bus)
        manager.clone(pid=100, flags=CLONE_NEWPID)
        assert bus.publish.called


# ============================================================
# FizzNSDashboard Tests
# ============================================================


class TestFizzNSDashboard:
    """Validate FizzNS dashboard rendering."""

    def test_render(self):
        manager = NamespaceManager()
        output = FizzNSDashboard.render(manager)
        assert "FIZZNS: LINUX NAMESPACE ISOLATION ENGINE" in output
        assert "Total Created:" in output
        assert "Active Namespaces:" in output

    def test_render_with_width(self):
        manager = NamespaceManager()
        output = FizzNSDashboard.render(manager, width=80)
        lines = output.split("\n")
        for line in lines:
            assert len(line) <= 80

    def test_render_type_breakdown(self):
        manager = NamespaceManager()
        output = FizzNSDashboard.render(manager)
        assert "PID" in output
        assert "NET" in output
        assert "MNT" in output

    def test_render_operations(self):
        manager = NamespaceManager()
        output = FizzNSDashboard.render(manager)
        assert "clone():" in output
        assert "unshare():" in output
        assert "setns():" in output

    def test_render_process_mappings(self):
        manager = NamespaceManager()
        manager.clone(pid=100, flags=CLONE_NEWPID)
        output = FizzNSDashboard.render(manager)
        assert "PID" in output

    def test_render_no_processes(self):
        manager = NamespaceManager()
        output = FizzNSDashboard.render(manager)
        assert "(no tracked processes)" in output

    def test_render_with_event_bus(self):
        bus = MagicMock()
        manager = NamespaceManager(event_bus=bus)
        FizzNSDashboard.render(manager)
        assert bus.publish.called


# ============================================================
# FizzNSMiddleware Tests
# ============================================================


class TestFizzNSMiddleware:
    """Validate FizzNS middleware pipeline integration."""

    def _make_context(self, number: int = 15) -> ProcessingContext:
        """Create a test ProcessingContext."""
        return ProcessingContext(
            number=number,
            session_id="test-session",
            results=[FizzBuzzResult(
                number=number,
                output="FizzBuzz",
            )],
            metadata={},
        )

    def test_priority(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        assert middleware.get_priority() == 106

    def test_process(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        context = self._make_context()

        def next_handler(ctx):
            return ctx

        result = middleware.process(context, next_handler)
        assert "fizzns_active_namespaces" in result.metadata
        assert result.metadata["fizzns_active_namespaces"] == 7

    def test_process_increments_counter(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        context = self._make_context()

        def next_handler(ctx):
            return ctx

        middleware.process(context, next_handler)
        assert middleware.evaluations_processed == 1

    def test_process_with_event_bus(self):
        bus = MagicMock()
        manager = NamespaceManager(event_bus=bus)
        middleware = FizzNSMiddleware(manager=manager, event_bus=bus)
        context = self._make_context()

        def next_handler(ctx):
            return ctx

        middleware.process(context, next_handler)
        assert bus.publish.called

    def test_manager_property(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        assert middleware.manager is manager

    def test_render_dashboard(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        output = middleware.render_dashboard()
        assert "FIZZNS" in output

    def test_render_hierarchy(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        output = middleware.render_hierarchy()
        assert "Namespace Hierarchy" in output

    def test_render_hierarchy_filtered(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        output = middleware.render_hierarchy(ns_type=NamespaceType.PID)
        assert "PID" in output

    def test_list_namespaces(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        output = middleware.list_namespaces()
        assert "Active Namespaces" in output

    def test_list_namespaces_filtered(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        output = middleware.list_namespaces(ns_type=NamespaceType.NET)
        assert "NET" in output

    def test_inspect_namespace(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        output = middleware.inspect_namespace("ns-pid-root")
        assert "ns-pid-root" in output

    def test_inspect_nonexistent(self):
        manager = NamespaceManager()
        middleware = FizzNSMiddleware(manager=manager)
        output = middleware.inspect_namespace("nonexistent")
        assert "Error" in output


# ============================================================
# Factory Function Tests
# ============================================================


class TestFactory:
    """Validate create_fizzns_subsystem factory."""

    def test_create(self):
        manager, middleware = create_fizzns_subsystem()
        assert isinstance(manager, NamespaceManager)
        assert isinstance(middleware, FizzNSMiddleware)

    def test_custom_hostname(self):
        manager, _ = create_fizzns_subsystem(default_hostname="custom")
        uts_ns = manager.root_namespaces.get(NamespaceType.UTS)
        assert uts_ns.hostname == "custom"

    def test_custom_domainname(self):
        manager, _ = create_fizzns_subsystem(default_domainname="custom.local")
        uts_ns = manager.root_namespaces.get(NamespaceType.UTS)
        assert uts_ns.domainname == "custom.local"

    def test_event_bus(self):
        bus = MagicMock()
        manager, middleware = create_fizzns_subsystem(event_bus=bus)
        assert manager._event_bus is bus

    def test_root_namespaces_count(self):
        manager, _ = create_fizzns_subsystem()
        assert manager.root_namespaces.count == 7

    def test_middleware_priority(self):
        _, middleware = create_fizzns_subsystem()
        assert middleware.get_priority() == 106


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Validate all 18 FizzNS exception classes."""

    def test_namespace_error(self):
        with pytest.raises(NamespaceError):
            raise NamespaceError("test error")

    def test_namespace_error_code(self):
        try:
            raise NamespaceError("test")
        except NamespaceError as e:
            assert e.error_code == "EFP-NS00"

    def test_namespace_creation_error(self):
        e = NamespaceCreationError("creation failed")
        assert e.error_code == "EFP-NS01"
        assert isinstance(e, NamespaceError)

    def test_namespace_destroy_error(self):
        e = NamespaceDestroyError("destroy failed")
        assert e.error_code == "EFP-NS02"
        assert isinstance(e, NamespaceError)

    def test_namespace_entry_error(self):
        e = NamespaceEntryError("entry failed")
        assert e.error_code == "EFP-NS03"
        assert isinstance(e, NamespaceError)

    def test_namespace_leave_error(self):
        e = NamespaceLeaveError("leave failed")
        assert e.error_code == "EFP-NS04"
        assert isinstance(e, NamespaceError)

    def test_namespace_ref_count_error(self):
        e = NamespaceRefCountError("ref count error")
        assert e.error_code == "EFP-NS05"
        assert isinstance(e, NamespaceError)

    def test_namespace_hierarchy_error(self):
        e = NamespaceHierarchyError("hierarchy error")
        assert e.error_code == "EFP-NS06"
        assert isinstance(e, NamespaceError)

    def test_namespace_type_error(self):
        e = NamespaceTypeError("type error")
        assert e.error_code == "EFP-NS07"
        assert isinstance(e, NamespaceError)

    def test_pid_namespace_error(self):
        e = PIDNamespaceError("pid error")
        assert e.error_code == "EFP-NS08"
        assert isinstance(e, NamespaceError)

    def test_net_namespace_error(self):
        e = NETNamespaceError("net error")
        assert e.error_code == "EFP-NS09"
        assert isinstance(e, NamespaceError)

    def test_mnt_namespace_error(self):
        e = MNTNamespaceError("mnt error")
        assert e.error_code == "EFP-NS10"
        assert isinstance(e, NamespaceError)

    def test_uts_namespace_error(self):
        e = UTSNamespaceError("uts error")
        assert e.error_code == "EFP-NS11"
        assert isinstance(e, NamespaceError)

    def test_ipc_namespace_error(self):
        e = IPCNamespaceError("ipc error")
        assert e.error_code == "EFP-NS12"
        assert isinstance(e, NamespaceError)

    def test_user_namespace_error(self):
        e = USERNamespaceError("user error")
        assert e.error_code == "EFP-NS13"
        assert isinstance(e, NamespaceError)

    def test_cgroup_namespace_error(self):
        e = CGROUPNamespaceError("cgroup error")
        assert e.error_code == "EFP-NS14"
        assert isinstance(e, NamespaceError)

    def test_namespace_manager_error(self):
        e = NamespaceManagerError("manager error")
        assert e.error_code == "EFP-NS15"
        assert isinstance(e, NamespaceError)

    def test_namespace_dashboard_error(self):
        e = NamespaceDashboardError("dashboard error")
        assert e.error_code == "EFP-NS16"
        assert isinstance(e, NamespaceError)

    def test_namespace_middleware_error(self):
        e = NamespaceMiddlewareError(42, "middleware error")
        assert e.error_code == "EFP-NS17"
        assert isinstance(e, NamespaceError)
        assert e.evaluation_number == 42

    def test_all_inherit_from_namespace_error(self):
        exceptions = [
            NamespaceCreationError("t"),
            NamespaceDestroyError("t"),
            NamespaceEntryError("t"),
            NamespaceLeaveError("t"),
            NamespaceRefCountError("t"),
            NamespaceHierarchyError("t"),
            NamespaceTypeError("t"),
            PIDNamespaceError("t"),
            NETNamespaceError("t"),
            MNTNamespaceError("t"),
            UTSNamespaceError("t"),
            IPCNamespaceError("t"),
            USERNamespaceError("t"),
            CGROUPNamespaceError("t"),
            NamespaceManagerError("t"),
            NamespaceDashboardError("t"),
            NamespaceMiddlewareError(0, "t"),
        ]
        for exc in exceptions:
            assert isinstance(exc, NamespaceError)


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """End-to-end integration tests for the FizzNS engine."""

    def test_container_lifecycle(self):
        """Simulate full container creation and teardown."""
        manager = NamespaceManager()
        all_flags = (
            CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWNS |
            CLONE_NEWUTS | CLONE_NEWIPC | CLONE_NEWUSER |
            CLONE_NEWCGROUP
        )

        # Clone all namespaces for container PID 100
        ns_set = manager.clone(pid=100, flags=all_flags)
        assert ns_set.count == 7

        # Set container hostname
        uts_ns = ns_set.get(NamespaceType.UTS)
        uts_ns.sethostname("my-container")
        assert uts_ns.hostname == "my-container"

        # Allocate PID in container
        pid_ns = ns_set.get(NamespaceType.PID)
        pid_ns.allocate_pid("container-init")
        assert pid_ns.init_pid == 1

        # Configure networking
        net_ns = ns_set.get(NamespaceType.NET)
        net_ns.add_interface("eth0")
        net_ns.assign_ipv4("eth0", "10.0.0.2")
        net_ns.set_interface_state("eth0", "up")
        net_ns.bind_socket("tcp", "0.0.0.0", 8080, pid=1)

        # Mount container filesystem
        mnt_ns = ns_set.get(NamespaceType.MNT)
        mnt_ns.mount("/app", "overlay", "overlay")

        # Create IPC resources
        ipc_ns = ns_set.get(NamespaceType.IPC)
        ipc_ns.shmget(key=1, size=4096, owner_pid=1)

        # Configure user mapping
        user_ns = ns_set.get(NamespaceType.USER)
        user_ns.add_uid_mapping(0, 1000, 1)
        assert user_ns.translate_uid_to_host(0) == 1000

        # Verify cgroup isolation
        cgroup_ns = ns_set.get(NamespaceType.CGROUP)
        assert cgroup_ns.cgroup_root == "/"

        # Tear down: remove process
        manager.remove_process(100)

    def test_nested_namespaces(self):
        """Test namespace hierarchy nesting."""
        manager = NamespaceManager()

        # Create parent container
        parent_set = manager.clone(pid=100, flags=CLONE_NEWPID)
        parent_pid_ns = parent_set.get(NamespaceType.PID)

        # Create child container nested inside parent
        child_set = manager.clone(pid=200, flags=CLONE_NEWPID, parent_pid=100)
        child_pid_ns = child_set.get(NamespaceType.PID)

        assert child_pid_ns.parent is parent_pid_ns
        assert child_pid_ns in parent_pid_ns.children

    def test_multiple_containers(self):
        """Test multiple isolated containers."""
        manager = NamespaceManager()
        flags = CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWUTS

        ns1 = manager.clone(pid=100, flags=flags)
        ns2 = manager.clone(pid=200, flags=flags)

        # Both containers can have the same hostname
        uts1 = ns1.get(NamespaceType.UTS)
        uts2 = ns2.get(NamespaceType.UTS)
        uts1.sethostname("container-1")
        uts2.sethostname("container-2")
        assert uts1.hostname != uts2.hostname

        # Both containers can bind the same port
        net1 = ns1.get(NamespaceType.NET)
        net2 = ns2.get(NamespaceType.NET)
        net1.bind_socket("tcp", "0.0.0.0", 80)
        net2.bind_socket("tcp", "0.0.0.0", 80)

    def test_setns_cross_container(self):
        """Test process moving between containers."""
        manager = NamespaceManager()
        ns1 = manager.clone(pid=100, flags=CLONE_NEWNET)
        ns2 = manager.clone(pid=200, flags=CLONE_NEWNET)

        # Move PID 300 into container 1's NET namespace
        net1 = ns1.get(NamespaceType.NET)
        manager.setns(300, net1.ns_id)
        assert 300 in net1.member_pids

        # Move PID 300 into container 2's NET namespace
        net2 = ns2.get(NamespaceType.NET)
        manager.setns(300, net2.ns_id)
        assert 300 in net2.member_pids

    def test_garbage_collection(self):
        """Test namespace GC after container teardown."""
        manager = NamespaceManager()
        manager.clone(pid=100, flags=CLONE_NEWUTS)
        manager.remove_process(100)

        collected = manager.garbage_collect()
        assert collected >= 0
        assert manager.gc_count >= 1

    def test_dashboard_after_operations(self):
        """Test dashboard rendering with active containers."""
        manager = NamespaceManager()
        manager.clone(pid=100, flags=CLONE_NEWPID | CLONE_NEWNET)
        manager.clone(pid=200, flags=CLONE_NEWPID | CLONE_NEWNET)

        output = FizzNSDashboard.render(manager)
        assert "PID" in output

    def test_middleware_pipeline(self):
        """Test middleware processing with active namespaces."""
        manager, middleware = create_fizzns_subsystem()
        manager.clone(pid=100, flags=CLONE_NEWPID)

        context = ProcessingContext(
            number=15,
            session_id="test-session",
            results=[FizzBuzzResult(
                number=15,
                output="FizzBuzz",
            )],
            metadata={},
        )

        def next_handler(ctx):
            return ctx

        result = middleware.process(context, next_handler)
        assert result.metadata["fizzns_active_namespaces"] > 7

    def test_hierarchy_rendering(self):
        """Test hierarchy rendering with nested namespaces."""
        manager = NamespaceManager()
        manager.clone(pid=100, flags=CLONE_NEWPID)
        manager.clone(pid=200, flags=CLONE_NEWPID, parent_pid=100)

        output = manager.render_hierarchy(ns_type=NamespaceType.PID)
        assert "PID Namespaces:" in output

    def test_inspect_after_operations(self):
        """Test namespace inspection with state."""
        manager = NamespaceManager()
        ns_set = manager.clone(pid=100, flags=CLONE_NEWPID)
        pid_ns = ns_set.get(NamespaceType.PID)
        pid_ns.allocate_pid("container-init")

        info = manager.inspect_namespace(pid_ns.ns_id)
        assert info["pid_count"] == 1
        assert info["init_pid"] == 1

    def test_veth_pair_between_namespaces(self):
        """Test veth pair connecting two network namespaces."""
        manager = NamespaceManager()
        ns1 = manager.clone(pid=100, flags=CLONE_NEWNET)
        ns2 = manager.clone(pid=200, flags=CLONE_NEWNET)

        net1 = ns1.get(NamespaceType.NET)
        net2 = ns2.get(NamespaceType.NET)

        pair = net1.create_veth_pair(net2, "veth0", "eth0")
        assert "veth0" in net1.interfaces
        assert "eth0" in net2.interfaces
        assert pair.host_ns_id == net1.ns_id
        assert pair.container_ns_id == net2.ns_id

    def test_rootless_container(self):
        """Test rootless container setup."""
        manager = NamespaceManager()
        ns_set = manager.clone(pid=100, flags=CLONE_NEWUSER)
        user_ns = ns_set.get(NamespaceType.USER)
        user_ns.set_rootless()

        assert user_ns.is_rootless is True
        assert user_ns.translate_uid_to_host(0) == user_ns.owner_uid

    def test_pivot_root_container(self):
        """Test pivot_root for container rootfs setup."""
        manager = NamespaceManager()
        ns_set = manager.clone(pid=100, flags=CLONE_NEWNS)
        mnt_ns = ns_set.get(NamespaceType.MNT)

        mnt_ns.pivot_root("/var/lib/containers/rootfs", "/.pivot")
        assert mnt_ns.root_path == "/var/lib/containers/rootfs"
        assert mnt_ns.old_root_path == "/"

    def test_init_process_semantics(self):
        """Test PID 1 init process behavior."""
        manager = NamespaceManager()
        ns_set = manager.clone(pid=100, flags=CLONE_NEWPID)
        pid_ns = ns_set.get(NamespaceType.PID)

        pid_ns.allocate_pid("init")
        pid_ns.allocate_pid("worker-1")
        pid_ns.allocate_pid("worker-2")

        # Kill init - should kill all others
        pid_ns.deallocate_pid(1)
        assert pid_ns.pid_count == 0
        assert len(pid_ns.killed_pids) == 2

    def test_ipc_isolation_between_containers(self):
        """Test IPC namespace isolation."""
        manager = NamespaceManager()
        ns1 = manager.clone(pid=100, flags=CLONE_NEWIPC)
        ns2 = manager.clone(pid=200, flags=CLONE_NEWIPC)

        ipc1 = ns1.get(NamespaceType.IPC)
        ipc2 = ns2.get(NamespaceType.IPC)

        ipc1.shmget(key=1, size=4096)
        assert ipc1.shm_count == 1
        assert ipc2.shm_count == 0  # Isolated

    def test_capability_dropping(self):
        """Test capability bounding set manipulation."""
        manager = NamespaceManager()
        ns_set = manager.clone(pid=100, flags=CLONE_NEWUSER)
        user_ns = ns_set.get(NamespaceType.USER)

        assert user_ns.has_capability("CAP_NET_ADMIN")
        user_ns.drop_capability("CAP_NET_ADMIN")
        assert not user_ns.has_capability("CAP_NET_ADMIN")

    def test_cgroup_visibility(self):
        """Test cgroup path virtualization."""
        manager = NamespaceManager()
        ns_set = manager.clone(pid=100, flags=CLONE_NEWCGROUP)
        cgroup_ns = ns_set.get(NamespaceType.CGROUP)

        cgroup_ns.add_cgroup("/app")
        assert cgroup_ns.entry_count == 2  # root + /app

    def test_statistics_accuracy(self):
        """Test that statistics reflect actual state."""
        manager = NamespaceManager()
        initial_stats = manager.get_statistics()

        manager.clone(pid=100, flags=CLONE_NEWPID | CLONE_NEWNET)
        after_stats = manager.get_statistics()

        assert after_stats["total_created"] > initial_stats["total_created"]
        assert after_stats["process_count"] == 1

    def test_unshare_preserves_existing(self):
        """Test that unshare preserves non-specified namespaces."""
        manager = NamespaceManager()
        initial_set = manager.clone(pid=100, flags=CLONE_NEWPID | CLONE_NEWNET)
        original_net = initial_set.get(NamespaceType.NET)

        new_set = manager.unshare(pid=100, flags=CLONE_NEWPID)
        new_pid = new_set.get(NamespaceType.PID)
        kept_net = new_set.get(NamespaceType.NET)

        # PID should be new
        assert new_pid is not initial_set.get(NamespaceType.PID)
        # NET should be preserved
        assert kept_net is original_net

    def test_list_namespaces_rendering(self):
        """Test namespace listing string output."""
        manager, middleware = create_fizzns_subsystem()
        output = middleware.list_namespaces()
        assert "Active Namespaces" in output
        assert "Type" in output

    def test_inspect_rendering(self):
        """Test namespace inspection string output."""
        manager, middleware = create_fizzns_subsystem()
        output = middleware.inspect_namespace("ns-pid-root")
        assert "Namespace Inspection" in output
        assert "ns-pid-root" in output

    def test_full_clone_flags(self):
        """Test combining all namespace flags."""
        all_flags = (
            CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWNS |
            CLONE_NEWUTS | CLONE_NEWIPC | CLONE_NEWUSER |
            CLONE_NEWCGROUP
        )
        manager = NamespaceManager()
        ns_set = manager.clone(pid=100, flags=all_flags)
        assert ns_set.get_clone_flags() == all_flags
