"""
Enterprise FizzBuzz Platform - FizzOCI Test Suite

Comprehensive tests for the OCI-Compliant Container Runtime.
Validates the complete OCI lifecycle state machine (Creating ->
Created -> Running -> Stopped), the five OCI operations (create,
start, kill, delete, state), seccomp profile engine, mount
processing, hook execution, capability management, rlimit
validation, container registry, middleware integration, dashboard
rendering, factory wiring, and all 20 exception classes.

The OCI runtime specification demands conformance.  These tests
enforce it.
"""

from __future__ import annotations

import copy
import json
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzoci import (
    ALL_CAPABILITIES,
    DANGEROUS_SYSCALLS,
    DEFAULT_CAPABILITIES,
    DEFAULT_DASHBOARD_WIDTH,
    DEFAULT_HOOK_TIMEOUT,
    DEFAULT_MAX_CONTAINERS,
    DEFAULT_MOUNTS,
    DEFAULT_SECCOMP_PROFILE,
    KNOWN_SYSCALLS,
    MASKED_PATHS,
    MIDDLEWARE_PRIORITY,
    OCI_SPEC_VERSION,
    READONLY_PATHS,
    SIGNAL_MAP,
    SIGNAL_MAP_REVERSE,
    VALID_RLIMIT_TYPES,
    CapabilitySet,
    ContainerCreator,
    ContainerHooks,
    ContainerProcess,
    DeviceRule,
    HookExecutor,
    HookSpec,
    HookType,
    LinuxConfig,
    LinuxNamespaceConfig,
    LinuxResources,
    LinuxResourcesCPU,
    LinuxResourcesIO,
    LinuxResourcesMemory,
    LinuxResourcesPIDs,
    MountPropagation,
    MountProcessor,
    MountSpec,
    OCIBundle,
    OCIConfig,
    OCIContainer,
    OCIDashboard,
    OCIRoot,
    OCIRuntime,
    OCIRuntimeMiddleware,
    OCIState,
    OCIStateReport,
    RlimitConfig,
    SeccompAction,
    SeccompArg,
    SeccompEngine,
    SeccompOperator,
    SeccompProfile,
    SeccompRule,
    UserSpec,
    create_fizzoci_subsystem,
)
from enterprise_fizzbuzz.infrastructure.fizzoci import _OCIRuntimeMeta
from enterprise_fizzbuzz.domain.exceptions import (
    HookError,
    HookTimeoutError,
    MountError,
    OCIBundleError,
    OCIConfigError,
    OCIConfigSchemaError,
    OCIContainerError,
    OCIContainerExistsError,
    OCIContainerNotFoundError,
    OCICreateError,
    OCIDashboardError,
    OCIDeleteError,
    OCIKillError,
    OCIRuntimeError,
    OCIRuntimeMiddlewareError,
    OCIStartError,
    OCIStateTransitionError,
    RlimitError,
    SeccompError,
    SeccompRuleError,
)
from enterprise_fizzbuzz.domain.exceptions.oci_runtime import (
    MountError as OCIMountError,
)
from config import _SingletonMeta
from models import EventType, FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    _OCIRuntimeMeta.reset()
    yield
    _SingletonMeta.reset()
    _OCIRuntimeMeta.reset()


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate OCI constants match specification values."""

    def test_oci_spec_version(self):
        assert OCI_SPEC_VERSION == "1.0.2"

    def test_default_hook_timeout(self):
        assert DEFAULT_HOOK_TIMEOUT == 30.0

    def test_default_max_containers(self):
        assert DEFAULT_MAX_CONTAINERS == 256

    def test_default_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 72

    def test_default_seccomp_profile(self):
        assert DEFAULT_SECCOMP_PROFILE == "default"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 108

    def test_signal_map_sigterm(self):
        assert SIGNAL_MAP["SIGTERM"] == 15

    def test_signal_map_sigkill(self):
        assert SIGNAL_MAP["SIGKILL"] == 9

    def test_signal_map_sighup(self):
        assert SIGNAL_MAP["SIGHUP"] == 1

    def test_signal_map_reverse(self):
        assert SIGNAL_MAP_REVERSE[15] == "SIGTERM"
        assert SIGNAL_MAP_REVERSE[9] == "SIGKILL"

    def test_default_capabilities_contains_chown(self):
        assert "CAP_CHOWN" in DEFAULT_CAPABILITIES

    def test_default_capabilities_contains_net_bind(self):
        assert "CAP_NET_BIND_SERVICE" in DEFAULT_CAPABILITIES

    def test_all_capabilities_contains_sys_admin(self):
        assert "CAP_SYS_ADMIN" in ALL_CAPABILITIES

    def test_all_capabilities_superset_of_default(self):
        for cap in DEFAULT_CAPABILITIES:
            assert cap in ALL_CAPABILITIES

    def test_masked_paths_contains_proc_kcore(self):
        assert "/proc/kcore" in MASKED_PATHS

    def test_readonly_paths_contains_proc_sys(self):
        assert "/proc/sys" in READONLY_PATHS

    def test_default_mounts_has_proc(self):
        assert any(m["destination"] == "/proc" for m in DEFAULT_MOUNTS)

    def test_default_mounts_has_dev(self):
        assert any(m["destination"] == "/dev" for m in DEFAULT_MOUNTS)

    def test_valid_rlimit_types_contains_nofile(self):
        assert "RLIMIT_NOFILE" in VALID_RLIMIT_TYPES

    def test_valid_rlimit_types_contains_nproc(self):
        assert "RLIMIT_NPROC" in VALID_RLIMIT_TYPES

    def test_known_syscalls_contains_read(self):
        assert "read" in KNOWN_SYSCALLS

    def test_known_syscalls_contains_write(self):
        assert "write" in KNOWN_SYSCALLS

    def test_dangerous_syscalls_contains_reboot(self):
        assert "reboot" in DANGEROUS_SYSCALLS

    def test_dangerous_syscalls_contains_mount(self):
        assert "mount" in DANGEROUS_SYSCALLS

    def test_dangerous_syscalls_subset_of_known(self):
        for s in DANGEROUS_SYSCALLS:
            assert s in KNOWN_SYSCALLS


# ============================================================
# Enum Tests
# ============================================================


class TestOCIState:
    """Validate OCI lifecycle state enum."""

    def test_creating(self):
        assert OCIState.CREATING.value == "creating"

    def test_created(self):
        assert OCIState.CREATED.value == "created"

    def test_running(self):
        assert OCIState.RUNNING.value == "running"

    def test_stopped(self):
        assert OCIState.STOPPED.value == "stopped"

    def test_all_states(self):
        assert len(OCIState) == 4


class TestSeccompAction:
    """Validate seccomp action enum."""

    def test_allow(self):
        assert SeccompAction.SCMP_ACT_ALLOW.value == "SCMP_ACT_ALLOW"

    def test_errno(self):
        assert SeccompAction.SCMP_ACT_ERRNO.value == "SCMP_ACT_ERRNO"

    def test_kill(self):
        assert SeccompAction.SCMP_ACT_KILL.value == "SCMP_ACT_KILL"

    def test_trap(self):
        assert SeccompAction.SCMP_ACT_TRAP.value == "SCMP_ACT_TRAP"

    def test_log(self):
        assert SeccompAction.SCMP_ACT_LOG.value == "SCMP_ACT_LOG"

    def test_all_actions(self):
        assert len(SeccompAction) == 8


class TestSeccompOperator:
    """Validate seccomp comparison operator enum."""

    def test_eq(self):
        assert SeccompOperator.SCMP_CMP_EQ.value == "SCMP_CMP_EQ"

    def test_ne(self):
        assert SeccompOperator.SCMP_CMP_NE.value == "SCMP_CMP_NE"

    def test_masked_eq(self):
        assert SeccompOperator.SCMP_CMP_MASKED_EQ.value == "SCMP_CMP_MASKED_EQ"

    def test_all_operators(self):
        assert len(SeccompOperator) == 7


class TestMountPropagation:
    """Validate mount propagation enum."""

    def test_private(self):
        assert MountPropagation.PRIVATE.value == "private"

    def test_rprivate(self):
        assert MountPropagation.RPRIVATE.value == "rprivate"

    def test_shared(self):
        assert MountPropagation.SHARED.value == "shared"

    def test_all_modes(self):
        assert len(MountPropagation) == 6


class TestHookType:
    """Validate hook type enum."""

    def test_prestart(self):
        assert HookType.PRESTART.value == "prestart"

    def test_create_runtime(self):
        assert HookType.CREATE_RUNTIME.value == "createRuntime"

    def test_poststop(self):
        assert HookType.POSTSTOP.value == "poststop"

    def test_all_hooks(self):
        assert len(HookType) == 6


# ============================================================
# Dataclass Tests
# ============================================================


class TestOCIRoot:
    """Validate OCIRoot dataclass."""

    def test_defaults(self):
        root = OCIRoot()
        assert root.path == "rootfs"
        assert root.readonly is False

    def test_custom(self):
        root = OCIRoot(path="/custom", readonly=True)
        assert root.path == "/custom"
        assert root.readonly is True


class TestMountSpec:
    """Validate MountSpec dataclass."""

    def test_defaults(self):
        m = MountSpec()
        assert m.destination == ""
        assert m.type == ""
        assert m.options == []

    def test_custom(self):
        m = MountSpec(destination="/proc", type="proc", source="proc", options=["nosuid"])
        assert m.destination == "/proc"
        assert "nosuid" in m.options


class TestRlimitConfig:
    """Validate RlimitConfig dataclass."""

    def test_defaults(self):
        r = RlimitConfig()
        assert r.type == "RLIMIT_NOFILE"
        assert r.soft == 1024
        assert r.hard == 1024

    def test_validate_valid(self):
        r = RlimitConfig(type="RLIMIT_NOFILE", soft=512, hard=1024)
        r.validate()

    def test_validate_unknown_type(self):
        r = RlimitConfig(type="RLIMIT_NONEXISTENT", soft=0, hard=0)
        with pytest.raises(RlimitError):
            r.validate()

    def test_validate_soft_exceeds_hard(self):
        r = RlimitConfig(type="RLIMIT_NOFILE", soft=2048, hard=1024)
        with pytest.raises(RlimitError):
            r.validate()

    def test_validate_negative_soft(self):
        r = RlimitConfig(type="RLIMIT_NOFILE", soft=-1, hard=1024)
        with pytest.raises(RlimitError):
            r.validate()

    def test_validate_negative_hard(self):
        r = RlimitConfig(type="RLIMIT_NOFILE", soft=0, hard=-1)
        with pytest.raises(RlimitError):
            r.validate()


class TestUserSpec:
    """Validate UserSpec dataclass."""

    def test_defaults(self):
        u = UserSpec()
        assert u.uid == 0
        assert u.gid == 0
        assert u.umask == 0o022

    def test_custom(self):
        u = UserSpec(uid=1000, gid=1000, additional_gids=[100, 200])
        assert u.uid == 1000
        assert len(u.additional_gids) == 2


class TestCapabilitySet:
    """Validate CapabilitySet dataclass."""

    def test_defaults(self):
        caps = CapabilitySet()
        assert len(caps.bounding) > 0
        assert len(caps.effective) > 0
        assert len(caps.inheritable) == 0

    def test_validate_valid(self):
        caps = CapabilitySet()
        caps.validate()

    def test_validate_unknown_cap(self):
        caps = CapabilitySet(bounding=["CAP_NONEXISTENT"])
        with pytest.raises(OCIConfigError):
            caps.validate()

    def test_drop_to(self):
        caps = CapabilitySet()
        dropped = caps.drop_to(["CAP_CHOWN", "CAP_KILL"])
        assert "CAP_CHOWN" in dropped.bounding
        assert "CAP_KILL" in dropped.bounding
        assert "CAP_NET_RAW" not in dropped.bounding


class TestContainerProcess:
    """Validate ContainerProcess dataclass."""

    def test_defaults(self):
        p = ContainerProcess()
        assert p.args == ["/bin/sh"]
        assert p.cwd == "/"
        assert p.no_new_privileges is True

    def test_validate_valid(self):
        p = ContainerProcess()
        p.validate()

    def test_validate_empty_args(self):
        p = ContainerProcess(args=[])
        with pytest.raises(OCIConfigError):
            p.validate()

    def test_validate_relative_cwd(self):
        p = ContainerProcess(cwd="relative/path")
        with pytest.raises(OCIConfigError):
            p.validate()


class TestSeccompArg:
    """Validate SeccompArg dataclass."""

    def test_defaults(self):
        a = SeccompArg()
        assert a.index == 0
        assert a.op == SeccompOperator.SCMP_CMP_EQ

    def test_validate_valid(self):
        a = SeccompArg(index=3, value=42)
        a.validate()

    def test_validate_invalid_index(self):
        a = SeccompArg(index=7)
        with pytest.raises(SeccompRuleError):
            a.validate()


class TestSeccompRule:
    """Validate SeccompRule dataclass."""

    def test_validate_valid(self):
        r = SeccompRule(names=["read", "write"], action=SeccompAction.SCMP_ACT_ALLOW)
        r.validate()

    def test_validate_empty_names(self):
        r = SeccompRule(names=[])
        with pytest.raises(SeccompRuleError):
            r.validate()

    def test_validate_unknown_syscall(self):
        r = SeccompRule(names=["nonexistent_syscall"])
        with pytest.raises(SeccompRuleError):
            r.validate()


class TestSeccompProfile:
    """Validate SeccompProfile dataclass."""

    def test_default_profile(self):
        p = SeccompProfile.default_profile()
        assert p.default_action == SeccompAction.SCMP_ACT_ERRNO
        assert len(p.syscalls) > 0

    def test_strict_profile(self):
        p = SeccompProfile.strict_profile()
        assert p.default_action == SeccompAction.SCMP_ACT_KILL
        assert len(p.syscalls) > 0

    def test_unconfined_profile(self):
        p = SeccompProfile.unconfined_profile()
        assert p.default_action == SeccompAction.SCMP_ACT_ALLOW
        assert len(p.syscalls) == 0

    def test_validate_valid(self):
        p = SeccompProfile.default_profile()
        p.validate()

    def test_to_dict(self):
        p = SeccompProfile.default_profile()
        d = p.to_dict()
        assert d["defaultAction"] == "SCMP_ACT_ERRNO"
        assert "syscalls" in d

    def test_default_profile_blocks_dangerous(self):
        p = SeccompProfile.default_profile()
        allowed_syscalls = set()
        for rule in p.syscalls:
            if rule.action == SeccompAction.SCMP_ACT_ALLOW:
                allowed_syscalls.update(rule.names)
        for dangerous in DANGEROUS_SYSCALLS:
            assert dangerous not in allowed_syscalls


class TestHookSpec:
    """Validate HookSpec dataclass."""

    def test_defaults(self):
        h = HookSpec()
        assert h.path == ""
        assert h.timeout is None

    def test_validate_empty_path(self):
        h = HookSpec()
        with pytest.raises(HookError):
            h.validate()

    def test_validate_negative_timeout(self):
        h = HookSpec(path="/bin/hook", timeout=-1)
        with pytest.raises(HookError):
            h.validate()

    def test_validate_valid(self):
        h = HookSpec(path="/bin/hook", args=["--flag"], timeout=10.0)
        h.validate()


class TestContainerHooks:
    """Validate ContainerHooks dataclass."""

    def test_defaults(self):
        h = ContainerHooks()
        assert len(h.prestart) == 0
        assert len(h.poststop) == 0

    def test_get_hooks(self):
        h = ContainerHooks(prestart=[HookSpec(path="/a")])
        assert len(h.get_hooks(HookType.PRESTART)) == 1
        assert len(h.get_hooks(HookType.POSTSTOP)) == 0

    def test_validate(self):
        h = ContainerHooks(prestart=[HookSpec(path="/a")])
        h.validate()


class TestLinuxNamespaceConfig:
    """Validate LinuxNamespaceConfig dataclass."""

    def test_defaults(self):
        ns = LinuxNamespaceConfig()
        assert ns.type == ""
        assert ns.path == ""

    def test_custom(self):
        ns = LinuxNamespaceConfig(type="pid", path="/proc/1/ns/pid")
        assert ns.type == "pid"


class TestLinuxResources:
    """Validate Linux resource limit dataclasses."""

    def test_cpu_defaults(self):
        cpu = LinuxResourcesCPU()
        assert cpu.shares == 1024
        assert cpu.quota == -1
        assert cpu.period == 100000

    def test_memory_defaults(self):
        mem = LinuxResourcesMemory()
        assert mem.limit == -1
        assert mem.swap == -1

    def test_pids_defaults(self):
        pids = LinuxResourcesPIDs()
        assert pids.limit == -1

    def test_io_defaults(self):
        io = LinuxResourcesIO()
        assert io.weight == 100

    def test_aggregate_defaults(self):
        r = LinuxResources()
        assert r.cpu.shares == 1024
        assert r.memory.limit == -1


class TestDeviceRule:
    """Validate DeviceRule dataclass."""

    def test_defaults(self):
        d = DeviceRule()
        assert d.allow is False
        assert d.type == "a"

    def test_matches_exact(self):
        d = DeviceRule(allow=True, type="c", major=1, minor=3)
        assert d.matches("c", 1, 3) is True
        assert d.matches("c", 1, 5) is False
        assert d.matches("b", 1, 3) is False

    def test_matches_wildcard(self):
        d = DeviceRule(allow=True, type="a", major=-1, minor=-1)
        assert d.matches("c", 1, 3) is True
        assert d.matches("b", 8, 0) is True


class TestLinuxConfig:
    """Validate LinuxConfig dataclass."""

    def test_defaults(self):
        lc = LinuxConfig()
        assert len(lc.namespaces) > 0
        assert lc.rootfs_propagation == MountPropagation.RPRIVATE

    def test_validate_valid(self):
        lc = LinuxConfig()
        lc.validate()

    def test_validate_unknown_ns_type(self):
        lc = LinuxConfig(namespaces=[LinuxNamespaceConfig(type="invalid")])
        with pytest.raises(OCIConfigError):
            lc.validate()


# ============================================================
# OCIConfig Tests
# ============================================================


class TestOCIConfig:
    """Validate OCIConfig parsing, serialization, and validation."""

    def test_defaults(self):
        c = OCIConfig()
        assert c.oci_version == OCI_SPEC_VERSION
        assert c.hostname == "fizzbuzz-container"

    def test_validate_valid(self):
        c = OCIConfig()
        c.validate()

    def test_validate_bad_version(self):
        c = OCIConfig(oci_version="not-semver")
        with pytest.raises(OCIConfigSchemaError):
            c.validate()

    def test_validate_empty_root_path(self):
        c = OCIConfig(root=OCIRoot(path=""))
        with pytest.raises(OCIConfigSchemaError):
            c.validate()

    def test_from_dict_minimal(self):
        data = {"ociVersion": "1.0.2"}
        c = OCIConfig.from_dict(data)
        assert c.oci_version == "1.0.2"

    def test_from_dict_missing_version(self):
        with pytest.raises(OCIConfigSchemaError):
            OCIConfig.from_dict({})

    def test_from_dict_full(self):
        data = {
            "ociVersion": "1.0.2",
            "root": {"path": "rootfs", "readonly": True},
            "process": {
                "args": ["/bin/fizzbuzz"],
                "cwd": "/app",
                "env": ["PATH=/bin"],
                "user": {"uid": 1000, "gid": 1000},
                "noNewPrivileges": True,
            },
            "hostname": "test-container",
            "mounts": [
                {"destination": "/proc", "type": "proc", "source": "proc", "options": ["nosuid"]},
            ],
            "linux": {
                "namespaces": [{"type": "pid"}, {"type": "network"}],
                "cgroupsPath": "/test/cgroup",
                "resources": {
                    "cpu": {"shares": 512, "quota": 50000},
                    "memory": {"limit": 268435456},
                    "pids": {"limit": 100},
                },
                "maskedPaths": ["/proc/kcore"],
                "readonlyPaths": ["/proc/sys"],
            },
            "annotations": {"fizzbuzz.version": "1.0"},
        }
        c = OCIConfig.from_dict(data)
        assert c.root.readonly is True
        assert c.process.args == ["/bin/fizzbuzz"]
        assert c.process.user.uid == 1000
        assert c.hostname == "test-container"
        assert len(c.mounts) == 1
        assert c.linux.resources.cpu.shares == 512
        assert c.linux.resources.memory.limit == 268435456
        assert c.annotations["fizzbuzz.version"] == "1.0"

    def test_to_dict(self):
        c = OCIConfig()
        d = c.to_dict()
        assert d["ociVersion"] == OCI_SPEC_VERSION
        assert "root" in d
        assert "process" in d
        assert "linux" in d

    def test_round_trip(self):
        c1 = OCIConfig()
        d = c1.to_dict()
        c2 = OCIConfig.from_dict(d)
        assert c2.oci_version == c1.oci_version
        assert c2.hostname == c1.hostname

    def test_from_dict_with_seccomp(self):
        data = {
            "ociVersion": "1.0.2",
            "linux": {
                "seccomp": {
                    "defaultAction": "SCMP_ACT_ERRNO",
                    "syscalls": [
                        {
                            "names": ["read", "write"],
                            "action": "SCMP_ACT_ALLOW",
                            "args": [
                                {"index": 0, "value": 1, "op": "SCMP_CMP_EQ"},
                            ],
                        }
                    ],
                }
            },
        }
        c = OCIConfig.from_dict(data)
        assert c.linux.seccomp is not None
        assert c.linux.seccomp.default_action == SeccompAction.SCMP_ACT_ERRNO
        assert len(c.linux.seccomp.syscalls) == 1

    def test_from_dict_with_hooks(self):
        data = {
            "ociVersion": "1.0.2",
            "hooks": {
                "prestart": [{"path": "/bin/pre", "args": ["--flag"]}],
                "poststop": [{"path": "/bin/post"}],
            },
        }
        c = OCIConfig.from_dict(data)
        assert len(c.hooks.prestart) == 1
        assert len(c.hooks.poststop) == 1
        assert c.hooks.prestart[0].path == "/bin/pre"


class TestOCIBundle:
    """Validate OCIBundle dataclass."""

    def test_defaults(self):
        b = OCIBundle()
        assert b.bundle_path == ""

    def test_validate_empty_path(self):
        b = OCIBundle()
        with pytest.raises(OCIBundleError):
            b.validate()

    def test_validate_valid(self):
        b = OCIBundle(bundle_path="/tmp/bundle")
        b.validate()


class TestOCIStateReport:
    """Validate OCIStateReport dataclass."""

    def test_defaults(self):
        r = OCIStateReport()
        assert r.status == "stopped"
        assert r.pid == -1

    def test_to_dict(self):
        r = OCIStateReport(id="test-123", status="running", pid=1001)
        d = r.to_dict()
        assert d["id"] == "test-123"
        assert d["status"] == "running"
        assert d["pid"] == 1001


# ============================================================
# OCIContainer Tests
# ============================================================


class TestOCIContainer:
    """Validate OCIContainer state machine."""

    def _make_container(self, container_id="test-1"):
        config = OCIConfig()
        bundle = OCIBundle(bundle_path="/tmp/bundle", config=config)
        return OCIContainer(container_id=container_id, bundle=bundle)

    def test_initial_state(self):
        c = self._make_container()
        assert c.state == OCIState.CREATING
        assert c.pid == -1
        assert c.exit_code == -1

    def test_container_id(self):
        c = self._make_container("my-container")
        assert c.container_id == "my-container"

    def test_transition_creating_to_created(self):
        c = self._make_container()
        c.transition_to(OCIState.CREATED)
        assert c.state == OCIState.CREATED

    def test_transition_created_to_running(self):
        c = self._make_container()
        c.transition_to(OCIState.CREATED)
        c.transition_to(OCIState.RUNNING)
        assert c.state == OCIState.RUNNING
        assert c.started_at is not None

    def test_transition_running_to_stopped(self):
        c = self._make_container()
        c.transition_to(OCIState.CREATED)
        c.transition_to(OCIState.RUNNING)
        c.transition_to(OCIState.STOPPED)
        assert c.state == OCIState.STOPPED
        assert c.stopped_at is not None

    def test_invalid_transition_creating_to_running(self):
        c = self._make_container()
        with pytest.raises(OCIStateTransitionError):
            c.transition_to(OCIState.RUNNING)

    def test_invalid_transition_creating_to_stopped(self):
        c = self._make_container()
        with pytest.raises(OCIStateTransitionError):
            c.transition_to(OCIState.STOPPED)

    def test_invalid_transition_stopped_to_running(self):
        c = self._make_container()
        c.transition_to(OCIState.CREATED)
        c.transition_to(OCIState.RUNNING)
        c.transition_to(OCIState.STOPPED)
        with pytest.raises(OCIStateTransitionError):
            c.transition_to(OCIState.RUNNING)

    def test_set_pid(self):
        c = self._make_container()
        c.set_pid(42)
        assert c.pid == 42

    def test_set_namespace_ids(self):
        c = self._make_container()
        c.set_namespace_ids(["ns-1", "ns-2"])
        assert len(c.namespace_ids) == 2

    def test_set_cgroup_path(self):
        c = self._make_container()
        c.set_cgroup_path("/test/cgroup")
        assert c.cgroup_path == "/test/cgroup"

    def test_mark_seccomp(self):
        c = self._make_container()
        assert c.seccomp_applied is False
        c.mark_seccomp_applied()
        assert c.seccomp_applied is True

    def test_mark_capabilities(self):
        c = self._make_container()
        assert c.capabilities_dropped is False
        c.mark_capabilities_dropped()
        assert c.capabilities_dropped is True

    def test_mark_rlimits(self):
        c = self._make_container()
        assert c.rlimits_applied is False
        c.mark_rlimits_applied()
        assert c.rlimits_applied is True

    def test_set_exit_code(self):
        c = self._make_container()
        c.set_exit_code(0)
        assert c.exit_code == 0

    def test_record_hook_execution(self):
        c = self._make_container()
        c.record_hook_execution("prestart", "/bin/hook")
        assert "prestart" in c.hooks_executed
        assert "/bin/hook" in c.hooks_executed["prestart"]

    def test_get_state_report(self):
        c = self._make_container("rpt-1")
        report = c.get_state_report()
        assert report.id == "rpt-1"
        assert report.status == "creating"

    def test_uptime_not_started(self):
        c = self._make_container()
        assert c.uptime_seconds() == 0.0

    def test_uptime_after_start(self):
        c = self._make_container()
        c.transition_to(OCIState.CREATED)
        c.transition_to(OCIState.RUNNING)
        assert c.uptime_seconds() >= 0.0

    def test_lifecycle_events_recorded(self):
        c = self._make_container()
        assert len(c.lifecycle_events) > 0

    def test_repr(self):
        c = self._make_container("repr-test")
        r = repr(c)
        assert "repr-test" in r
        assert "creating" in r

    def test_annotations(self):
        config = OCIConfig(annotations={"key": "value"})
        bundle = OCIBundle(bundle_path="/tmp/b", config=config)
        c = OCIContainer(container_id="ann-1", bundle=bundle)
        assert c.annotations["key"] == "value"

    def test_mounts_processed(self):
        c = self._make_container()
        m = MountSpec(destination="/proc", type="proc")
        c.add_processed_mount(m)
        assert len(c.mounts_processed) == 1


# ============================================================
# HookExecutor Tests
# ============================================================


class TestHookExecutor:
    """Validate lifecycle hook execution."""

    def _make_container(self):
        config = OCIConfig()
        bundle = OCIBundle(bundle_path="/tmp/bundle", config=config)
        return OCIContainer(container_id="hook-test", bundle=bundle)

    def test_default_timeout(self):
        he = HookExecutor()
        assert he.default_timeout == DEFAULT_HOOK_TIMEOUT

    def test_custom_timeout(self):
        he = HookExecutor(default_timeout=10.0)
        assert he.default_timeout == 10.0

    def test_execute_empty_hooks(self):
        he = HookExecutor()
        c = self._make_container()
        hooks = ContainerHooks()
        results = he.execute_hooks(c, HookType.PRESTART, hooks)
        assert results == []

    def test_execute_single_hook(self):
        he = HookExecutor()
        c = self._make_container()
        hooks = ContainerHooks(prestart=[HookSpec(path="/bin/hook")])
        results = he.execute_hooks(c, HookType.PRESTART, hooks)
        assert len(results) == 1
        assert results[0]["exit_code"] == 0

    def test_execute_multiple_hooks(self):
        he = HookExecutor()
        c = self._make_container()
        hooks = ContainerHooks(prestart=[
            HookSpec(path="/bin/hook1"),
            HookSpec(path="/bin/hook2"),
        ])
        results = he.execute_hooks(c, HookType.PRESTART, hooks)
        assert len(results) == 2

    def test_failing_hook(self):
        he = HookExecutor()
        c = self._make_container()
        hooks = ContainerHooks(prestart=[HookSpec(path="/bin/fail_hook")])
        with pytest.raises(HookError):
            he.execute_hooks(c, HookType.PRESTART, hooks)

    def test_execution_log(self):
        he = HookExecutor()
        c = self._make_container()
        hooks = ContainerHooks(prestart=[HookSpec(path="/bin/hook")])
        he.execute_hooks(c, HookType.PRESTART, hooks)
        assert len(he.execution_log) == 1

    def test_get_log_for_container(self):
        he = HookExecutor()
        c1 = self._make_container()
        c2_config = OCIConfig()
        c2_bundle = OCIBundle(bundle_path="/tmp/b2", config=c2_config)
        c2 = OCIContainer(container_id="other", bundle=c2_bundle)

        hooks = ContainerHooks(prestart=[HookSpec(path="/bin/hook")])
        he.execute_hooks(c1, HookType.PRESTART, hooks)
        he.execute_hooks(c2, HookType.PRESTART, hooks)

        log1 = he.get_log_for_container("hook-test")
        assert len(log1) == 1

    def test_clear_log(self):
        he = HookExecutor()
        c = self._make_container()
        hooks = ContainerHooks(prestart=[HookSpec(path="/bin/hook")])
        he.execute_hooks(c, HookType.PRESTART, hooks)
        he.clear_log()
        assert len(he.execution_log) == 0


# ============================================================
# SeccompEngine Tests
# ============================================================


class TestSeccompEngine:
    """Validate seccomp syscall filtering engine."""

    def test_predefined_profiles(self):
        se = SeccompEngine()
        assert "default" in se.profiles
        assert "strict" in se.profiles
        assert "unconfined" in se.profiles

    def test_register_profile(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_ALLOW,
            syscalls=[],
        )
        se.register_profile("custom", profile)
        assert "custom" in se.profiles

    def test_get_profile(self):
        se = SeccompEngine()
        p = se.get_profile("default")
        assert p.default_action == SeccompAction.SCMP_ACT_ERRNO

    def test_get_nonexistent_profile(self):
        se = SeccompEngine()
        with pytest.raises(SeccompError):
            se.get_profile("nonexistent")

    def test_evaluate_allow(self):
        se = SeccompEngine()
        profile = SeccompProfile.unconfined_profile()
        action = se.evaluate_syscall(profile, "read")
        assert action == SeccompAction.SCMP_ACT_ALLOW

    def test_evaluate_deny_default(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_KILL,
            syscalls=[],
        )
        action = se.evaluate_syscall(profile, "read")
        assert action == SeccompAction.SCMP_ACT_KILL

    def test_evaluate_rule_match(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_KILL,
            syscalls=[SeccompRule(names=["read"], action=SeccompAction.SCMP_ACT_ALLOW)],
        )
        assert se.evaluate_syscall(profile, "read") == SeccompAction.SCMP_ACT_ALLOW
        assert se.evaluate_syscall(profile, "write") == SeccompAction.SCMP_ACT_KILL

    def test_evaluate_with_args(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_ERRNO,
            syscalls=[
                SeccompRule(
                    names=["read"],
                    action=SeccompAction.SCMP_ACT_ALLOW,
                    args=[SeccompArg(index=0, value=3, op=SeccompOperator.SCMP_CMP_EQ)],
                )
            ],
        )
        assert se.evaluate_syscall(profile, "read", [3]) == SeccompAction.SCMP_ACT_ALLOW
        assert se.evaluate_syscall(profile, "read", [4]) == SeccompAction.SCMP_ACT_ERRNO

    def test_evaluate_masked_eq(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_ERRNO,
            syscalls=[
                SeccompRule(
                    names=["read"],
                    action=SeccompAction.SCMP_ACT_ALLOW,
                    args=[SeccompArg(index=0, value=0xFF, value_two=0x0F, op=SeccompOperator.SCMP_CMP_MASKED_EQ)],
                )
            ],
        )
        # 0xFF & 0xFF = 0xFF, which != 0x0F
        assert se.evaluate_syscall(profile, "read", [0xFF]) == SeccompAction.SCMP_ACT_ERRNO
        # 0x0F & 0xFF = 0x0F, which == 0x0F
        assert se.evaluate_syscall(profile, "read", [0x0F]) == SeccompAction.SCMP_ACT_ALLOW

    def test_evaluation_count(self):
        se = SeccompEngine()
        profile = SeccompProfile.unconfined_profile()
        se.evaluate_syscall(profile, "read")
        se.evaluate_syscall(profile, "write")
        assert se.evaluation_count == 2

    def test_denied_count(self):
        se = SeccompEngine()
        profile = SeccompProfile(default_action=SeccompAction.SCMP_ACT_KILL, syscalls=[])
        se.evaluate_syscall(profile, "read")
        assert se.denied_count == 1

    def test_validate_profile_warnings(self):
        se = SeccompEngine()
        profile = SeccompProfile.unconfined_profile()
        warnings = se.validate_profile(profile)
        assert len(warnings) > 0  # Should warn about ALLOW default

    def test_validate_profile_duplicate_syscalls(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_ERRNO,
            syscalls=[
                SeccompRule(names=["read"], action=SeccompAction.SCMP_ACT_ALLOW),
                SeccompRule(names=["read"], action=SeccompAction.SCMP_ACT_ALLOW),
            ],
        )
        warnings = se.validate_profile(profile)
        assert any("read" in w for w in warnings)

    def test_get_stats(self):
        se = SeccompEngine()
        stats = se.get_stats()
        assert stats["profiles_registered"] == 3

    def test_evaluation_log(self):
        se = SeccompEngine()
        profile = SeccompProfile.unconfined_profile()
        se.evaluate_syscall(profile, "read")
        assert len(se.evaluation_log) == 1
        assert se.evaluation_log[0]["syscall"] == "read"

    def test_evaluate_ne_operator(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_ERRNO,
            syscalls=[
                SeccompRule(
                    names=["write"],
                    action=SeccompAction.SCMP_ACT_ALLOW,
                    args=[SeccompArg(index=0, value=2, op=SeccompOperator.SCMP_CMP_NE)],
                )
            ],
        )
        assert se.evaluate_syscall(profile, "write", [3]) == SeccompAction.SCMP_ACT_ALLOW
        assert se.evaluate_syscall(profile, "write", [2]) == SeccompAction.SCMP_ACT_ERRNO

    def test_evaluate_lt_operator(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_ERRNO,
            syscalls=[
                SeccompRule(
                    names=["read"],
                    action=SeccompAction.SCMP_ACT_ALLOW,
                    args=[SeccompArg(index=0, value=10, op=SeccompOperator.SCMP_CMP_LT)],
                )
            ],
        )
        assert se.evaluate_syscall(profile, "read", [5]) == SeccompAction.SCMP_ACT_ALLOW
        assert se.evaluate_syscall(profile, "read", [10]) == SeccompAction.SCMP_ACT_ERRNO

    def test_evaluate_le_operator(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_ERRNO,
            syscalls=[
                SeccompRule(
                    names=["read"],
                    action=SeccompAction.SCMP_ACT_ALLOW,
                    args=[SeccompArg(index=0, value=10, op=SeccompOperator.SCMP_CMP_LE)],
                )
            ],
        )
        assert se.evaluate_syscall(profile, "read", [10]) == SeccompAction.SCMP_ACT_ALLOW
        assert se.evaluate_syscall(profile, "read", [11]) == SeccompAction.SCMP_ACT_ERRNO

    def test_evaluate_ge_operator(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_ERRNO,
            syscalls=[
                SeccompRule(
                    names=["read"],
                    action=SeccompAction.SCMP_ACT_ALLOW,
                    args=[SeccompArg(index=0, value=10, op=SeccompOperator.SCMP_CMP_GE)],
                )
            ],
        )
        assert se.evaluate_syscall(profile, "read", [10]) == SeccompAction.SCMP_ACT_ALLOW
        assert se.evaluate_syscall(profile, "read", [9]) == SeccompAction.SCMP_ACT_ERRNO

    def test_evaluate_gt_operator(self):
        se = SeccompEngine()
        profile = SeccompProfile(
            default_action=SeccompAction.SCMP_ACT_ERRNO,
            syscalls=[
                SeccompRule(
                    names=["read"],
                    action=SeccompAction.SCMP_ACT_ALLOW,
                    args=[SeccompArg(index=0, value=10, op=SeccompOperator.SCMP_CMP_GT)],
                )
            ],
        )
        assert se.evaluate_syscall(profile, "read", [11]) == SeccompAction.SCMP_ACT_ALLOW
        assert se.evaluate_syscall(profile, "read", [10]) == SeccompAction.SCMP_ACT_ERRNO


# ============================================================
# MountProcessor Tests
# ============================================================


class TestMountProcessor:
    """Validate mount processing engine."""

    def _make_container(self):
        config = OCIConfig()
        bundle = OCIBundle(bundle_path="/tmp/bundle", config=config)
        return OCIContainer(container_id="mount-test", bundle=bundle)

    def test_process_single_mount(self):
        mp = MountProcessor()
        c = self._make_container()
        mounts = [MountSpec(destination="/proc", type="proc", source="proc")]
        processed = mp.process_mounts(c, mounts)
        assert len(processed) == 1
        assert c.mounts_processed[0].destination == "/proc"

    def test_process_multiple_mounts(self):
        mp = MountProcessor()
        c = self._make_container()
        mounts = [
            MountSpec(destination="/proc", type="proc"),
            MountSpec(destination="/dev", type="tmpfs"),
        ]
        processed = mp.process_mounts(c, mounts)
        assert len(processed) == 2

    def test_process_empty_destination(self):
        mp = MountProcessor()
        c = self._make_container()
        with pytest.raises(OCIMountError):
            mp.process_mounts(c, [MountSpec(destination="")])

    def test_process_relative_destination(self):
        mp = MountProcessor()
        c = self._make_container()
        with pytest.raises(OCIMountError):
            mp.process_mounts(c, [MountSpec(destination="relative/path")])

    def test_mount_log(self):
        mp = MountProcessor()
        c = self._make_container()
        mp.process_mounts(c, [MountSpec(destination="/proc", type="proc")])
        assert len(mp.mount_log) == 1

    def test_apply_masked_paths(self):
        mp = MountProcessor()
        c = self._make_container()
        mp.apply_masked_paths(c, ["/proc/kcore", "/proc/keys"])
        assert mp.get_masked_paths("mount-test") == ["/proc/kcore", "/proc/keys"]

    def test_apply_readonly_paths(self):
        mp = MountProcessor()
        c = self._make_container()
        mp.apply_readonly_paths(c, ["/proc/sys"])
        assert mp.get_readonly_paths("mount-test") == ["/proc/sys"]

    def test_check_device_access_allowed(self):
        mp = MountProcessor()
        rules = [DeviceRule(allow=True, type="c", major=1, minor=3)]
        assert mp.check_device_access(rules, "c", 1, 3) is True

    def test_check_device_access_denied(self):
        mp = MountProcessor()
        rules = [DeviceRule(allow=False, type="a")]
        assert mp.check_device_access(rules, "c", 1, 3) is False

    def test_check_device_access_no_match(self):
        mp = MountProcessor()
        rules = [DeviceRule(allow=True, type="c", major=1, minor=3)]
        assert mp.check_device_access(rules, "b", 8, 0) is False

    def test_cleanup_container(self):
        mp = MountProcessor()
        c = self._make_container()
        mp.apply_masked_paths(c, ["/proc/kcore"])
        mp.apply_readonly_paths(c, ["/proc/sys"])
        mp.cleanup_container("mount-test")
        assert mp.get_masked_paths("mount-test") == []
        assert mp.get_readonly_paths("mount-test") == []


# ============================================================
# ContainerCreator Tests
# ============================================================


class TestContainerCreator:
    """Validate container creation orchestration."""

    def _make_creator(self, **kwargs):
        return ContainerCreator(
            hook_executor=HookExecutor(),
            seccomp_engine=SeccompEngine(),
            mount_processor=MountProcessor(),
            **kwargs,
        )

    def _make_container(self, container_id="create-test", config=None):
        if config is None:
            config = OCIConfig()
        bundle = OCIBundle(bundle_path="/tmp/bundle", config=config)
        return OCIContainer(container_id=container_id, bundle=bundle)

    def test_create_basic(self):
        creator = self._make_creator()
        c = self._make_container()
        creator.create(c)
        assert c.state == OCIState.CREATED
        assert c.pid > 0

    def test_create_with_seccomp(self):
        creator = self._make_creator()
        config = OCIConfig()
        config.linux.seccomp = SeccompProfile.default_profile()
        c = self._make_container(config=config)
        creator.create(c)
        assert c.seccomp_applied is True

    def test_create_with_rlimits(self):
        creator = self._make_creator()
        c = self._make_container()
        creator.create(c)
        assert c.rlimits_applied is True

    def test_create_drops_capabilities(self):
        creator = self._make_creator()
        c = self._make_container()
        creator.create(c)
        assert c.capabilities_dropped is True

    def test_create_processes_mounts(self):
        creator = self._make_creator()
        c = self._make_container()
        creator.create(c)
        assert len(c.mounts_processed) > 0

    def test_create_sets_namespaces(self):
        creator = self._make_creator()
        c = self._make_container()
        creator.create(c)
        assert len(c.namespace_ids) > 0

    def test_create_sets_cgroup_path(self):
        creator = self._make_creator()
        c = self._make_container()
        creator.create(c)
        assert c.cgroup_path != ""

    def test_create_with_hooks(self):
        creator = self._make_creator()
        config = OCIConfig()
        config.hooks = ContainerHooks(
            create_runtime=[HookSpec(path="/bin/runtime_hook")],
            create_container=[HookSpec(path="/bin/container_hook")],
        )
        c = self._make_container(config=config)
        creator.create(c)
        assert "createRuntime" in c.hooks_executed
        assert "createContainer" in c.hooks_executed

    def test_create_with_failing_hook(self):
        creator = self._make_creator()
        config = OCIConfig()
        config.hooks = ContainerHooks(
            create_runtime=[HookSpec(path="/bin/fail_hook")],
        )
        c = self._make_container(config=config)
        with pytest.raises(OCICreateError):
            creator.create(c)

    def test_create_with_invalid_config(self):
        creator = self._make_creator()
        config = OCIConfig(oci_version="invalid")
        c = self._make_container(config=config)
        with pytest.raises(OCICreateError):
            creator.create(c)

    def test_create_with_invalid_rlimit(self):
        creator = self._make_creator()
        config = OCIConfig()
        config.process.rlimits = [RlimitConfig(type="RLIMIT_NONEXISTENT")]
        c = self._make_container(config=config)
        with pytest.raises(OCICreateError):
            creator.create(c)

    def test_create_with_namespace_manager(self):
        ns_manager = MagicMock()
        creator = self._make_creator(namespace_manager=ns_manager)
        c = self._make_container()
        creator.create(c)
        assert len(c.namespace_ids) > 0

    def test_create_with_cgroup_manager(self):
        cg_manager = MagicMock()
        creator = self._make_creator(cgroup_manager=cg_manager)
        c = self._make_container()
        creator.create(c)
        assert c.cgroup_path != ""

    def test_create_with_event_bus(self):
        bus = MagicMock()
        creator = self._make_creator(event_bus=bus)
        c = self._make_container()
        creator.create(c)
        assert bus.publish.called

    def test_create_assigns_unique_pids(self):
        creator = self._make_creator()
        c1 = self._make_container("c1")
        c2 = self._make_container("c2")
        creator.create(c1)
        creator.create(c2)
        assert c1.pid != c2.pid


# ============================================================
# OCIRuntime Tests
# ============================================================


class TestOCIRuntime:
    """Validate the top-level OCI runtime."""

    def _make_runtime(self, **kwargs):
        return OCIRuntime(**kwargs)

    def test_create_container(self):
        rt = self._make_runtime()
        c = rt.create("/tmp/bundle", "test-1")
        assert c.state == OCIState.CREATED
        assert c.container_id == "test-1"

    def test_create_auto_id(self):
        rt = self._make_runtime()
        c = rt.create("/tmp/bundle")
        assert c.container_id != ""
        assert c.state == OCIState.CREATED

    def test_create_with_config_dict(self):
        rt = self._make_runtime()
        config = {"ociVersion": "1.0.2", "hostname": "custom-host"}
        c = rt.create("/tmp/bundle", "cfg-1", config_dict=config)
        assert c.config.hostname == "custom-host"

    def test_create_duplicate_id(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "dup-1")
        with pytest.raises(OCIContainerExistsError):
            rt.create("/tmp/bundle", "dup-1")

    def test_create_max_containers(self):
        rt = self._make_runtime(max_containers=2)
        rt.create("/tmp/bundle", "max-1")
        rt.create("/tmp/bundle", "max-2")
        with pytest.raises(OCICreateError):
            rt.create("/tmp/bundle", "max-3")

    def test_start_container(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "start-1")
        rt.start("start-1")
        c = rt.containers["start-1"]
        assert c.state == OCIState.RUNNING

    def test_start_not_created(self):
        rt = self._make_runtime()
        c = rt.create("/tmp/bundle", "start-bad")
        rt.start("start-bad")
        with pytest.raises(OCIStartError):
            rt.start("start-bad")

    def test_start_not_found(self):
        rt = self._make_runtime()
        with pytest.raises(OCIContainerNotFoundError):
            rt.start("nonexistent")

    def test_kill_container(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "kill-1")
        rt.start("kill-1")
        rt.kill("kill-1", "SIGTERM")
        c = rt.containers["kill-1"]
        assert c.state == OCIState.STOPPED
        assert c.exit_code == 128 + SIGNAL_MAP["SIGTERM"]

    def test_kill_sigkill(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "kill-2")
        rt.start("kill-2")
        rt.kill("kill-2", "SIGKILL")
        c = rt.containers["kill-2"]
        assert c.state == OCIState.STOPPED
        assert c.exit_code == 128 + 9

    def test_kill_non_terminal_signal(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "kill-3")
        rt.start("kill-3")
        rt.kill("kill-3", "SIGUSR1")
        c = rt.containers["kill-3"]
        assert c.state == OCIState.RUNNING  # Non-terminal signal

    def test_kill_not_running(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "kill-bad")
        with pytest.raises(OCIKillError):
            rt.kill("kill-bad", "SIGTERM")

    def test_kill_unknown_signal(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "kill-sig")
        rt.start("kill-sig")
        with pytest.raises(OCIKillError):
            rt.kill("kill-sig", "SIGNONEXISTENT")

    def test_delete_container(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "del-1")
        rt.start("del-1")
        rt.kill("del-1", "SIGTERM")
        rt.delete("del-1")
        assert "del-1" not in rt.containers

    def test_delete_not_stopped(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "del-bad")
        with pytest.raises(OCIDeleteError):
            rt.delete("del-bad")

    def test_delete_not_found(self):
        rt = self._make_runtime()
        with pytest.raises(OCIContainerNotFoundError):
            rt.delete("nonexistent")

    def test_state_query(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "state-1")
        report = rt.state("state-1")
        assert report.id == "state-1"
        assert report.status == "created"

    def test_state_not_found(self):
        rt = self._make_runtime()
        with pytest.raises(OCIContainerNotFoundError):
            rt.state("nonexistent")

    def test_list_containers(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "list-1")
        rt.create("/tmp/bundle", "list-2")
        containers = rt.list_containers()
        assert len(containers) == 2

    def test_list_containers_filter(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "filter-1")
        rt.create("/tmp/bundle", "filter-2")
        rt.start("filter-1")
        created = rt.list_containers(state_filter=OCIState.CREATED)
        running = rt.list_containers(state_filter=OCIState.RUNNING)
        assert len(created) == 1
        assert len(running) == 1

    def test_container_count(self):
        rt = self._make_runtime()
        assert rt.container_count == 0
        rt.create("/tmp/bundle", "count-1")
        assert rt.container_count == 1

    def test_generate_default_spec(self):
        rt = self._make_runtime()
        spec = rt.generate_default_spec()
        assert spec["ociVersion"] == OCI_SPEC_VERSION
        assert "root" in spec
        assert "process" in spec

    def test_get_stats(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "stats-1")
        stats = rt.get_stats()
        assert stats["total_containers"] == 1
        assert stats["oci_version"] == OCI_SPEC_VERSION

    def test_operation_log(self):
        rt = self._make_runtime()
        rt.create("/tmp/bundle", "log-1")
        assert len(rt.operation_log) >= 1

    def test_full_lifecycle(self):
        rt = self._make_runtime()
        c = rt.create("/tmp/bundle", "lifecycle-1")
        assert c.state == OCIState.CREATED

        rt.start("lifecycle-1")
        assert c.state == OCIState.RUNNING

        report = rt.state("lifecycle-1")
        assert report.status == "running"

        rt.kill("lifecycle-1", "SIGTERM")
        assert c.state == OCIState.STOPPED

        rt.delete("lifecycle-1")
        assert "lifecycle-1" not in rt.containers

    def test_properties(self):
        rt = self._make_runtime()
        assert rt.max_containers == DEFAULT_MAX_CONTAINERS
        assert isinstance(rt.hook_executor, HookExecutor)
        assert isinstance(rt.seccomp_engine, SeccompEngine)
        assert isinstance(rt.mount_processor, MountProcessor)

    def test_runtime_with_namespace_manager(self):
        ns_mgr = MagicMock()
        rt = self._make_runtime(namespace_manager=ns_mgr)
        c = rt.create("/tmp/bundle", "ns-1")
        assert c.state == OCIState.CREATED

    def test_runtime_with_cgroup_manager(self):
        cg_mgr = MagicMock()
        rt = self._make_runtime(cgroup_manager=cg_mgr)
        c = rt.create("/tmp/bundle", "cg-1")
        assert c.state == OCIState.CREATED

    def test_start_with_hooks(self):
        rt = self._make_runtime()
        config = {
            "ociVersion": "1.0.2",
            "hooks": {
                "startContainer": [{"path": "/bin/start_hook"}],
                "poststart": [{"path": "/bin/post_hook"}],
            },
        }
        rt.create("/tmp/bundle", "hook-start", config_dict=config)
        rt.start("hook-start")
        c = rt.containers["hook-start"]
        assert c.state == OCIState.RUNNING

    def test_delete_with_poststop_hooks(self):
        rt = self._make_runtime()
        config = {
            "ociVersion": "1.0.2",
            "hooks": {
                "poststop": [{"path": "/bin/poststop"}],
            },
        }
        rt.create("/tmp/bundle", "hook-del", config_dict=config)
        rt.start("hook-del")
        rt.kill("hook-del", "SIGTERM")
        rt.delete("hook-del")
        assert "hook-del" not in rt.containers


# ============================================================
# OCIRuntimeMiddleware Tests
# ============================================================


class TestOCIRuntimeMiddleware:
    """Validate middleware pipeline integration."""

    def _make_context(self, number=42):
        return ProcessingContext(number=number, session_id="test-session", metadata={})

    def _make_middleware(self, **kwargs):
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime()
        return OCIRuntimeMiddleware(runtime=runtime, **kwargs)

    def test_get_name(self):
        mw = self._make_middleware()
        assert mw.get_name() == "OCIRuntimeMiddleware"

    def test_get_priority(self):
        mw = self._make_middleware()
        assert mw.get_priority() == 108

    def test_process_evaluation(self):
        mw = self._make_middleware()
        ctx = self._make_context()
        result = mw.process(ctx, lambda c: c)
        assert result is not None
        assert mw.evaluation_count == 1

    def test_process_increments_counters(self):
        mw = self._make_middleware()
        mw.process(self._make_context(1), lambda c: c)
        mw.process(self._make_context(2), lambda c: c)
        assert mw.evaluation_count == 2
        assert mw.containers_created >= 2

    def test_process_fallback_on_error(self):
        """Middleware should fall back gracefully on runtime errors."""
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime(max_containers=0)
        mw = OCIRuntimeMiddleware(runtime=runtime)
        ctx = self._make_context()
        result = mw.process(ctx, lambda c: c)
        assert result is not None

    def test_render_dashboard(self):
        mw = self._make_middleware()
        dashboard = mw.render_dashboard()
        assert "FIZZOCI" in dashboard

    def test_render_dashboard_with_dashboard_enabled(self):
        mw = self._make_middleware(enable_dashboard=True)
        dashboard = mw.render_dashboard()
        assert "FIZZOCI" in dashboard

    def test_render_container_list_empty(self):
        mw = self._make_middleware()
        result = mw.render_container_list()
        assert "No containers" in result

    def test_render_container_state(self):
        mw = self._make_middleware()
        result = mw.render_container_state("nonexistent")
        assert "not found" in result

    def test_render_default_spec(self):
        mw = self._make_middleware()
        spec = mw.render_default_spec()
        parsed = json.loads(spec)
        assert parsed["ociVersion"] == OCI_SPEC_VERSION

    def test_render_lifecycle_empty(self):
        mw = self._make_middleware()
        result = mw.render_lifecycle()
        assert "No lifecycle" in result

    def test_properties(self):
        mw = self._make_middleware()
        assert isinstance(mw.runtime, OCIRuntime)
        assert mw.containers_completed == 0


# ============================================================
# OCIDashboard Tests
# ============================================================


class TestOCIDashboard:
    """Validate ASCII dashboard rendering."""

    def _make_dashboard(self):
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime()
        return OCIDashboard(runtime=runtime)

    def test_render_empty(self):
        db = self._make_dashboard()
        result = db.render()
        assert "FIZZOCI" in result
        assert OCI_SPEC_VERSION in result

    def test_render_with_containers(self):
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime()
        runtime.create("/tmp/bundle", "dash-1")
        db = OCIDashboard(runtime=runtime)
        result = db.render()
        assert "dash-1" in result

    def test_render_container_list_empty(self):
        db = self._make_dashboard()
        result = db.render_container_list()
        assert "No containers" in result

    def test_render_container_list_with_containers(self):
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime()
        runtime.create("/tmp/bundle", "list-dash-1")
        db = OCIDashboard(runtime=runtime)
        result = db.render_container_list()
        assert "list-dash-1" in result

    def test_render_lifecycle_empty(self):
        db = self._make_dashboard()
        result = db.render_lifecycle()
        assert "No lifecycle" in result

    def test_render_lifecycle_with_ops(self):
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime()
        runtime.create("/tmp/bundle", "life-1")
        db = OCIDashboard(runtime=runtime)
        result = db.render_lifecycle()
        assert "create" in result

    def test_width(self):
        db = self._make_dashboard()
        assert db.width == DEFAULT_DASHBOARD_WIDTH

    def test_custom_width(self):
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime()
        db = OCIDashboard(runtime=runtime, width=100)
        assert db.width == 100


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateFizzociSubsystem:
    """Validate factory function wiring."""

    def test_default_creation(self):
        runtime, middleware = create_fizzoci_subsystem()
        assert isinstance(runtime, OCIRuntime)
        assert isinstance(middleware, OCIRuntimeMiddleware)

    def test_custom_parameters(self):
        runtime, middleware = create_fizzoci_subsystem(
            default_seccomp_profile="strict",
            default_hook_timeout=10.0,
            max_containers=50,
            dashboard_width=100,
        )
        assert runtime.max_containers == 50

    def test_with_namespace_manager(self):
        ns_mgr = MagicMock()
        runtime, middleware = create_fizzoci_subsystem(namespace_manager=ns_mgr)
        assert runtime is not None

    def test_with_cgroup_manager(self):
        cg_mgr = MagicMock()
        runtime, middleware = create_fizzoci_subsystem(cgroup_manager=cg_mgr)
        assert runtime is not None

    def test_with_event_bus(self):
        bus = MagicMock()
        runtime, middleware = create_fizzoci_subsystem(event_bus=bus)
        assert runtime is not None

    def test_with_dashboard_enabled(self):
        runtime, middleware = create_fizzoci_subsystem(enable_dashboard=True)
        assert middleware.dashboard is not None

    def test_dashboard_disabled_by_default(self):
        runtime, middleware = create_fizzoci_subsystem()
        assert middleware.dashboard is None


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Validate all 20 OCI exception classes."""

    def test_oci_runtime_error(self):
        e = OCIRuntimeError("test")
        assert "test" in str(e)

    def test_oci_config_error(self):
        e = OCIConfigError("bad config")
        assert "bad config" in str(e)
        assert "EFP-OCI01" in e.error_code

    def test_oci_config_schema_error(self):
        e = OCIConfigSchemaError("root.path", "missing")
        assert "root.path" in str(e)
        assert "EFP-OCI02" in e.error_code

    def test_oci_bundle_error(self):
        e = OCIBundleError("/tmp/bundle", "no rootfs")
        assert "/tmp/bundle" in str(e)
        assert "EFP-OCI03" in e.error_code

    def test_oci_container_error(self):
        e = OCIContainerError("c-1", "failed")
        assert "c-1" in str(e)
        assert "EFP-OCI04" in e.error_code

    def test_oci_state_transition_error(self):
        e = OCIStateTransitionError("c-1", "creating", "running")
        assert "creating" in str(e)
        assert "running" in str(e)
        assert "EFP-OCI05" in e.error_code

    def test_oci_container_not_found_error(self):
        e = OCIContainerNotFoundError("c-1")
        assert "c-1" in str(e)
        assert "EFP-OCI06" in e.error_code

    def test_oci_container_exists_error(self):
        e = OCIContainerExistsError("c-1")
        assert "c-1" in str(e)
        assert "EFP-OCI07" in e.error_code

    def test_oci_create_error(self):
        e = OCICreateError("c-1", "namespace failed")
        assert "c-1" in str(e)
        assert "EFP-OCI08" in e.error_code

    def test_oci_start_error(self):
        e = OCIStartError("c-1", "hook failed")
        assert "c-1" in str(e)
        assert "EFP-OCI09" in e.error_code

    def test_oci_kill_error(self):
        e = OCIKillError("c-1", "SIGTERM", "not running")
        assert "SIGTERM" in str(e)
        assert "EFP-OCI10" in e.error_code

    def test_oci_delete_error(self):
        e = OCIDeleteError("c-1", "not stopped")
        assert "c-1" in str(e)
        assert "EFP-OCI11" in e.error_code

    def test_seccomp_error(self):
        e = SeccompError("profile invalid")
        assert "profile invalid" in str(e)
        assert "EFP-OCI12" in e.error_code

    def test_seccomp_rule_error(self):
        e = SeccompRuleError("read", "invalid args")
        assert "read" in str(e)
        assert "EFP-OCI13" in e.error_code

    def test_hook_error(self):
        e = HookError("prestart", "exit code 1")
        assert "prestart" in str(e)
        assert "EFP-OCI14" in e.error_code

    def test_hook_timeout_error(self):
        e = HookTimeoutError("createRuntime", 30.0)
        assert "30.0" in str(e)
        assert "EFP-OCI15" in e.error_code

    def test_rlimit_error(self):
        e = RlimitError("RLIMIT_NOFILE", "too high")
        assert "RLIMIT_NOFILE" in str(e)
        assert "EFP-OCI16" in e.error_code

    def test_mount_error(self):
        e = MountError("unit1", "/proc", "/mnt/proc", "permission denied")
        assert "/proc" in str(e)
        assert "EFP-SYD15" in e.error_code

    def test_oci_runtime_middleware_error(self):
        e = OCIRuntimeMiddlewareError(42, "container failed")
        assert "42" in str(e)
        assert "EFP-OCI18" in e.error_code
        assert e.evaluation_number == 42

    def test_oci_dashboard_error(self):
        e = OCIDashboardError("render failed")
        assert "render failed" in str(e)
        assert "EFP-OCI19" in e.error_code

    def test_all_inherit_from_oci_runtime_error(self):
        """All OCI exceptions must inherit from OCIRuntimeError."""
        classes = [
            OCIConfigError, OCIConfigSchemaError, OCIBundleError,
            OCIContainerError, OCIStateTransitionError,
            OCIContainerNotFoundError, OCIContainerExistsError,
            OCICreateError, OCIStartError, OCIKillError,
            OCIDeleteError, SeccompError, SeccompRuleError,
            HookError, HookTimeoutError, RlimitError,
            OCIRuntimeMiddlewareError, OCIDashboardError,
        ]
        for cls in classes:
            assert issubclass(cls, OCIRuntimeError), f"{cls.__name__} must inherit from OCIRuntimeError"
        # MountError now inherits from SystemdError rather than OCIRuntimeError
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(MountError, FizzBuzzError)


# ============================================================
# EventType Tests
# ============================================================


class TestEventTypes:
    """Validate OCI EventType members exist."""

    def test_oci_container_creating(self):
        assert hasattr(EventType, "OCI_CONTAINER_CREATING")

    def test_oci_container_created(self):
        assert hasattr(EventType, "OCI_CONTAINER_CREATED")

    def test_oci_container_started(self):
        assert hasattr(EventType, "OCI_CONTAINER_STARTED")

    def test_oci_container_killed(self):
        assert hasattr(EventType, "OCI_CONTAINER_KILLED")

    def test_oci_container_stopped(self):
        assert hasattr(EventType, "OCI_CONTAINER_STOPPED")

    def test_oci_container_deleted(self):
        assert hasattr(EventType, "OCI_CONTAINER_DELETED")

    def test_oci_state_queried(self):
        assert hasattr(EventType, "OCI_STATE_QUERIED")

    def test_oci_namespace_setup(self):
        assert hasattr(EventType, "OCI_NAMESPACE_SETUP")

    def test_oci_cgroup_configured(self):
        assert hasattr(EventType, "OCI_CGROUP_CONFIGURED")

    def test_oci_rootfs_prepared(self):
        assert hasattr(EventType, "OCI_ROOTFS_PREPARED")

    def test_oci_mount_processed(self):
        assert hasattr(EventType, "OCI_MOUNT_PROCESSED")

    def test_oci_seccomp_applied(self):
        assert hasattr(EventType, "OCI_SECCOMP_APPLIED")

    def test_oci_hook_executed(self):
        assert hasattr(EventType, "OCI_HOOK_EXECUTED")

    def test_oci_rlimit_applied(self):
        assert hasattr(EventType, "OCI_RLIMIT_APPLIED")

    def test_oci_capability_dropped(self):
        assert hasattr(EventType, "OCI_CAPABILITY_DROPPED")

    def test_oci_spec_generated(self):
        assert hasattr(EventType, "OCI_SPEC_GENERATED")

    def test_oci_dashboard_rendered(self):
        assert hasattr(EventType, "OCI_DASHBOARD_RENDERED")


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_lifecycle_with_event_bus(self):
        bus = MagicMock()
        runtime, middleware = create_fizzoci_subsystem(event_bus=bus)
        c = runtime.create("/tmp/bundle", "integ-1")
        runtime.start("integ-1")
        runtime.kill("integ-1", "SIGTERM")
        runtime.delete("integ-1")
        assert bus.publish.call_count > 0

    def test_middleware_pipeline_simulation(self):
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime()
        middleware = OCIRuntimeMiddleware(runtime=runtime)

        results = []
        for i in range(1, 6):
            ctx = ProcessingContext(number=i, session_id="test-session", metadata={})
            result = middleware.process(ctx, lambda c: c)
            results.append(result)

        assert middleware.evaluation_count == 5
        assert middleware.containers_completed == 5

    def test_seccomp_evaluation_in_container(self):
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime()
        c = runtime.create("/tmp/bundle", "seccomp-integ")
        se = runtime.seccomp_engine
        profile = se.get_profile("default")

        # read should be allowed
        assert se.evaluate_syscall(profile, "read") == SeccompAction.SCMP_ACT_ALLOW

        # reboot should be denied (not in allowed list)
        assert se.evaluate_syscall(profile, "reboot") == SeccompAction.SCMP_ACT_ERRNO

    def test_concurrent_container_creation(self):
        import threading

        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime(max_containers=100)
        errors = []
        containers = []
        lock = threading.Lock()

        def create_container(idx):
            try:
                c = runtime.create(f"/tmp/bundle-{idx}", f"concurrent-{idx}")
                with lock:
                    containers.append(c)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=create_container, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(containers) == 10

    def test_graceful_degradation_without_fizzns(self):
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime(namespace_manager=None)
        c = runtime.create("/tmp/bundle", "no-ns")
        assert c.state == OCIState.CREATED
        assert len(c.namespace_ids) > 0  # Placeholder IDs

    def test_graceful_degradation_without_fizzcgroup(self):
        _OCIRuntimeMeta.reset()
        runtime = OCIRuntime(cgroup_manager=None)
        c = runtime.create("/tmp/bundle", "no-cg")
        assert c.state == OCIState.CREATED
        assert c.cgroup_path != ""
