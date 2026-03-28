"""
Enterprise FizzBuzz Platform - FizzOCI: OCI-Compliant Container Runtime

A low-level container runtime implementing the Open Container Initiative
(OCI) runtime specification v1.0.2.  Given an OCI runtime bundle
(config.json + rootfs), FizzOCI creates containers by parsing the
configuration, setting up namespaces (via FizzNS), configuring cgroup
resource limits (via FizzCgroup), preparing the root filesystem,
processing mounts, applying seccomp syscall filters, dropping
capabilities, executing lifecycle hooks, and launching the container
entrypoint process.

The runtime implements the five OCI operations (create, start, kill,
delete, state) and maintains a container registry with thread-safe
lifecycle management.  It integrates with FizzNS for namespace isolation
and FizzCgroup for resource accounting, but degrades gracefully when
either subsystem is unavailable.

OCI Runtime Spec: https://github.com/opencontainers/runtime-spec
Reference implementation: runc (https://github.com/opencontainers/runc)
"""

from __future__ import annotations

import copy
import hashlib
import logging
import signal
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from enterprise_fizzbuzz.domain.exceptions import (
    HookError,
    HookTimeoutError,
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
from enterprise_fizzbuzz.domain.exceptions.oci_runtime import MountError
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzoci")


# ============================================================
# Constants
# ============================================================

OCI_SPEC_VERSION = "1.0.2"
"""Supported OCI runtime specification version."""

DEFAULT_HOOK_TIMEOUT = 30.0
"""Default timeout in seconds for lifecycle hooks."""

DEFAULT_MAX_CONTAINERS = 256
"""Maximum number of containers the runtime can manage simultaneously."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

DEFAULT_SECCOMP_PROFILE = "default"
"""Default seccomp profile applied to new containers."""

MIDDLEWARE_PRIORITY = 108
"""Middleware pipeline priority for the OCI runtime middleware."""

# POSIX signal number mapping
SIGNAL_MAP: Dict[str, int] = {
    "SIGHUP": 1,
    "SIGINT": 2,
    "SIGQUIT": 3,
    "SIGILL": 4,
    "SIGTRAP": 5,
    "SIGABRT": 6,
    "SIGBUS": 7,
    "SIGFPE": 8,
    "SIGKILL": 9,
    "SIGUSR1": 10,
    "SIGSEGV": 11,
    "SIGUSR2": 12,
    "SIGPIPE": 13,
    "SIGALRM": 14,
    "SIGTERM": 15,
    "SIGSTKFLT": 16,
    "SIGCHLD": 17,
    "SIGCONT": 18,
    "SIGSTOP": 19,
    "SIGTSTP": 20,
    "SIGTTIN": 21,
    "SIGTTOU": 22,
    "SIGURG": 23,
    "SIGXCPU": 24,
    "SIGXFSZ": 25,
    "SIGVTALRM": 26,
    "SIGPROF": 27,
    "SIGWINCH": 28,
    "SIGIO": 29,
    "SIGPWR": 30,
    "SIGSYS": 31,
}
"""POSIX signal name to number mapping."""

SIGNAL_MAP_REVERSE: Dict[int, str] = {v: k for k, v in SIGNAL_MAP.items()}
"""POSIX signal number to name mapping."""

DEFAULT_CAPABILITIES: List[str] = [
    "CAP_AUDIT_WRITE",
    "CAP_CHOWN",
    "CAP_DAC_OVERRIDE",
    "CAP_FOWNER",
    "CAP_FSETID",
    "CAP_KILL",
    "CAP_MKNOD",
    "CAP_NET_BIND_SERVICE",
    "CAP_NET_RAW",
    "CAP_SETFCAP",
    "CAP_SETGID",
    "CAP_SETPCAP",
    "CAP_SETUID",
    "CAP_SYS_CHROOT",
]
"""Default Linux capabilities for container processes (Docker-compatible)."""

ALL_CAPABILITIES: List[str] = [
    "CAP_AUDIT_CONTROL",
    "CAP_AUDIT_READ",
    "CAP_AUDIT_WRITE",
    "CAP_BLOCK_SUSPEND",
    "CAP_BPF",
    "CAP_CHECKPOINT_RESTORE",
    "CAP_CHOWN",
    "CAP_DAC_OVERRIDE",
    "CAP_DAC_READ_SEARCH",
    "CAP_FOWNER",
    "CAP_FSETID",
    "CAP_IPC_LOCK",
    "CAP_IPC_OWNER",
    "CAP_KILL",
    "CAP_LEASE",
    "CAP_LINUX_IMMUTABLE",
    "CAP_MAC_ADMIN",
    "CAP_MAC_OVERRIDE",
    "CAP_MKNOD",
    "CAP_NET_ADMIN",
    "CAP_NET_BIND_SERVICE",
    "CAP_NET_BROADCAST",
    "CAP_NET_RAW",
    "CAP_PERFMON",
    "CAP_SETFCAP",
    "CAP_SETGID",
    "CAP_SETPCAP",
    "CAP_SETUID",
    "CAP_SYS_ADMIN",
    "CAP_SYS_BOOT",
    "CAP_SYS_CHROOT",
    "CAP_SYS_MODULE",
    "CAP_SYS_NICE",
    "CAP_SYS_PACCT",
    "CAP_SYS_PTRACE",
    "CAP_SYS_RAWIO",
    "CAP_SYS_RESOURCE",
    "CAP_SYS_TIME",
    "CAP_SYS_TTY_CONFIG",
    "CAP_SYSLOG",
    "CAP_WAKE_ALARM",
]
"""All Linux capabilities recognized by the runtime."""

MASKED_PATHS: List[str] = [
    "/proc/acpi",
    "/proc/asound",
    "/proc/kcore",
    "/proc/keys",
    "/proc/latency_stats",
    "/proc/timer_list",
    "/proc/timer_stats",
    "/proc/sched_debug",
    "/sys/firmware",
    "/proc/scsi",
]
"""Paths masked (nullified) inside the container by default."""

READONLY_PATHS: List[str] = [
    "/proc/bus",
    "/proc/fs",
    "/proc/irq",
    "/proc/sys",
    "/proc/sysrq-trigger",
]
"""Paths made read-only inside the container by default."""

DEFAULT_MOUNTS: List[Dict[str, Any]] = [
    {
        "destination": "/proc",
        "type": "proc",
        "source": "proc",
        "options": ["nosuid", "noexec", "nodev"],
    },
    {
        "destination": "/dev",
        "type": "tmpfs",
        "source": "tmpfs",
        "options": ["nosuid", "strictatime", "mode=755", "size=65536k"],
    },
    {
        "destination": "/dev/pts",
        "type": "devpts",
        "source": "devpts",
        "options": ["nosuid", "noexec", "newinstance", "ptmxmode=0666", "mode=0620", "gid=5"],
    },
    {
        "destination": "/dev/shm",
        "type": "tmpfs",
        "source": "shm",
        "options": ["nosuid", "noexec", "nodev", "mode=1777", "size=65536k"],
    },
    {
        "destination": "/dev/mqueue",
        "type": "mqueue",
        "source": "mqueue",
        "options": ["nosuid", "noexec", "nodev"],
    },
    {
        "destination": "/sys",
        "type": "sysfs",
        "source": "sysfs",
        "options": ["nosuid", "noexec", "nodev", "ro"],
    },
]
"""Default OCI-compliant mount table for Linux containers."""

VALID_RLIMIT_TYPES: List[str] = [
    "RLIMIT_AS",
    "RLIMIT_CORE",
    "RLIMIT_CPU",
    "RLIMIT_DATA",
    "RLIMIT_FSIZE",
    "RLIMIT_LOCKS",
    "RLIMIT_MEMLOCK",
    "RLIMIT_MSGQUEUE",
    "RLIMIT_NICE",
    "RLIMIT_NOFILE",
    "RLIMIT_NPROC",
    "RLIMIT_RSS",
    "RLIMIT_RTPRIO",
    "RLIMIT_RTTIME",
    "RLIMIT_SIGPENDING",
    "RLIMIT_STACK",
]
"""Recognized POSIX resource limit types."""

KNOWN_SYSCALLS: List[str] = [
    "accept", "accept4", "access", "adjtimex", "alarm", "bind",
    "brk", "capget", "capset", "chdir", "chmod", "chown", "chroot",
    "clock_getres", "clock_gettime", "clock_nanosleep", "clone",
    "close", "connect", "copy_file_range", "creat", "dup", "dup2",
    "dup3", "epoll_create", "epoll_create1", "epoll_ctl",
    "epoll_pwait", "epoll_wait", "eventfd", "eventfd2", "execve",
    "execveat", "exit", "exit_group", "faccessat", "fadvise64",
    "fallocate", "fanotify_init", "fanotify_mark", "fchdir",
    "fchmod", "fchmodat", "fchown", "fchownat", "fcntl", "fdatasync",
    "fgetxattr", "flistxattr", "flock", "fork", "fremovexattr",
    "fsetxattr", "fstat", "fstatfs", "fsync", "ftruncate",
    "futex", "futimesat", "getcpu", "getcwd", "getdents",
    "getdents64", "getegid", "geteuid", "getgid", "getgroups",
    "getitimer", "getpeername", "getpgid", "getpgrp", "getpid",
    "getppid", "getpriority", "getrandom", "getresgid",
    "getresuid", "getrlimit", "getrusage", "getsid", "getsockname",
    "getsockopt", "gettid", "gettimeofday", "getuid", "getxattr",
    "inotify_add_watch", "inotify_init", "inotify_init1",
    "inotify_rm_watch", "io_cancel", "io_destroy", "io_getevents",
    "io_setup", "io_submit", "ioctl", "ioprio_get", "ioprio_set",
    "kexec_load", "keyctl", "kill", "lchown", "lgetxattr",
    "link", "linkat", "listen", "listxattr", "llistxattr",
    "lremovexattr", "lseek", "lsetxattr", "lstat", "madvise",
    "membarrier", "memfd_create", "mincore", "mkdir", "mkdirat",
    "mknod", "mknodat", "mlock", "mlock2", "mlockall", "mmap",
    "mount", "mprotect", "mq_getsetattr", "mq_notify", "mq_open",
    "mq_timedreceive", "mq_timedsend", "mq_unlink", "mremap",
    "msgctl", "msgget", "msgrcv", "msgsnd", "msync", "munlock",
    "munlockall", "munmap", "nanosleep", "newfstatat", "open",
    "openat", "pause", "perf_event_open", "personality", "pipe",
    "pipe2", "pivot_root", "poll", "ppoll", "prctl", "pread64",
    "preadv", "preadv2", "prlimit64", "process_vm_readv",
    "process_vm_writev", "pselect6", "ptrace", "pwrite64",
    "pwritev", "pwritev2", "read", "readahead", "readlink",
    "readlinkat", "readv", "reboot", "recvfrom", "recvmmsg",
    "recvmsg", "remap_file_pages", "removexattr", "rename",
    "renameat", "renameat2", "restart_syscall", "rmdir",
    "rt_sigaction", "rt_sigpending", "rt_sigprocmask",
    "rt_sigqueueinfo", "rt_sigreturn", "rt_sigsuspend",
    "rt_sigtimedwait", "rt_tgsigqueueinfo", "sched_getaffinity",
    "sched_getattr", "sched_getparam", "sched_get_priority_max",
    "sched_get_priority_min", "sched_getscheduler",
    "sched_setaffinity", "sched_setattr", "sched_setparam",
    "sched_setscheduler", "sched_yield", "seccomp", "select",
    "semctl", "semget", "semop", "semtimedop", "sendfile",
    "sendmmsg", "sendmsg", "sendto", "setdomainname", "setfsgid",
    "setfsuid", "setgid", "setgroups", "sethostname", "setitimer",
    "setns", "setpgid", "setpriority", "setregid", "setresgid",
    "setresuid", "setreuid", "setrlimit", "setsid", "setsockopt",
    "settimeofday", "setuid", "setxattr", "shmat", "shmctl",
    "shmdt", "shmget", "shutdown", "sigaltstack", "signalfd",
    "signalfd4", "socket", "socketpair", "splice", "stat",
    "statfs", "statx", "swapoff", "swapon", "symlink", "symlinkat",
    "sync", "sync_file_range", "syncfs", "sysinfo", "syslog",
    "tee", "tgkill", "time", "timer_create", "timer_delete",
    "timer_getoverrun", "timer_gettime", "timer_settime",
    "timerfd_create", "timerfd_gettime", "timerfd_settime",
    "times", "tkill", "truncate", "umask", "umount2", "uname",
    "unlink", "unlinkat", "unshare", "userfaultfd", "ustat",
    "utime", "utimensat", "utimes", "vfork", "vhangup",
    "vmsplice", "wait4", "waitid", "write", "writev",
]
"""Known Linux syscalls for seccomp profile validation."""

DANGEROUS_SYSCALLS: Set[str] = {
    "reboot", "kexec_load", "mount", "umount2", "pivot_root",
    "swapon", "swapoff", "sethostname", "setdomainname",
    "settimeofday", "adjtimex", "syslog", "perf_event_open",
    "ptrace", "process_vm_readv", "process_vm_writev",
    "unshare", "setns", "clone",
}
"""Syscalls blocked in the default seccomp profile."""


# ============================================================
# Enums
# ============================================================


class OCIState(Enum):
    """Container lifecycle states as defined by the OCI runtime spec.

    The OCI specification defines a four-state lifecycle model:
    CREATING is a transient state during container setup, CREATED
    means the container environment is ready but the user process
    has not started, RUNNING means the user process is executing,
    and STOPPED means the user process has exited.
    """

    CREATING = "creating"
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"


class SeccompAction(Enum):
    """Actions that a seccomp filter can take when a syscall matches a rule.

    These actions correspond to the SECCOMP_RET_* constants in the
    Linux kernel's seccomp-bpf implementation.  SCMP_ACT_ALLOW permits
    the syscall, SCMP_ACT_ERRNO returns an error to the caller,
    SCMP_ACT_KILL terminates the process, and SCMP_ACT_TRAP delivers
    a SIGSYS signal.
    """

    SCMP_ACT_ALLOW = "SCMP_ACT_ALLOW"
    SCMP_ACT_ERRNO = "SCMP_ACT_ERRNO"
    SCMP_ACT_KILL = "SCMP_ACT_KILL"
    SCMP_ACT_KILL_PROCESS = "SCMP_ACT_KILL_PROCESS"
    SCMP_ACT_KILL_THREAD = "SCMP_ACT_KILL_THREAD"
    SCMP_ACT_TRAP = "SCMP_ACT_TRAP"
    SCMP_ACT_TRACE = "SCMP_ACT_TRACE"
    SCMP_ACT_LOG = "SCMP_ACT_LOG"


class SeccompOperator(Enum):
    """Comparison operators for seccomp argument filtering.

    Each operator compares a syscall argument at a given index
    against a reference value.  SCMP_CMP_EQ tests equality,
    SCMP_CMP_NE tests inequality, and the others perform
    unsigned integer comparisons.
    """

    SCMP_CMP_NE = "SCMP_CMP_NE"
    SCMP_CMP_LT = "SCMP_CMP_LT"
    SCMP_CMP_LE = "SCMP_CMP_LE"
    SCMP_CMP_EQ = "SCMP_CMP_EQ"
    SCMP_CMP_GE = "SCMP_CMP_GE"
    SCMP_CMP_GT = "SCMP_CMP_GT"
    SCMP_CMP_MASKED_EQ = "SCMP_CMP_MASKED_EQ"


class MountPropagation(Enum):
    """Mount propagation modes for the root filesystem.

    Mount propagation controls how mounts within a mount namespace
    are shared with peer or child namespaces.  These values
    correspond to the Linux kernel's MS_SHARED, MS_SLAVE,
    MS_PRIVATE, and MS_UNBINDABLE flags.
    """

    SHARED = "shared"
    SLAVE = "slave"
    PRIVATE = "private"
    UNBINDABLE = "unbindable"
    RPRIVATE = "rprivate"
    RSLAVE = "rslave"


class HookType(Enum):
    """OCI lifecycle hook types.

    The OCI runtime specification defines six hook points in the
    container lifecycle.  Each hook is an executable callback
    invoked by the runtime at a specific phase of container
    creation, startup, or shutdown.
    """

    PRESTART = "prestart"
    CREATE_RUNTIME = "createRuntime"
    CREATE_CONTAINER = "createContainer"
    START_CONTAINER = "startContainer"
    POSTSTART = "poststart"
    POSTSTOP = "poststop"


# ============================================================
# Dataclasses — OCI Configuration Model
# ============================================================


@dataclass
class OCIRoot:
    """Root filesystem configuration for a container.

    Specifies the path to the container's root filesystem (rootfs)
    and whether the root filesystem is mounted read-only.

    Attributes:
        path: Path to the root filesystem bundle.
        readonly: Whether to mount the rootfs as read-only.
    """

    path: str = "rootfs"
    readonly: bool = False


@dataclass
class MountSpec:
    """A filesystem mount specification.

    Each mount describes a filesystem to be mounted inside the
    container at the specified destination path.

    Attributes:
        destination: Absolute path inside the container.
        type: Filesystem type (e.g., proc, tmpfs, devpts).
        source: Source path or device name.
        options: List of mount options (e.g., nosuid, noexec).
    """

    destination: str = ""
    type: str = ""
    source: str = ""
    options: List[str] = field(default_factory=list)


@dataclass
class RlimitConfig:
    """POSIX resource limit configuration.

    Specifies the soft and hard limits for a given resource limit
    type.  The soft limit is the effective limit and the hard
    limit is the ceiling that the soft limit cannot exceed.

    Attributes:
        type: POSIX rlimit type (e.g., RLIMIT_NOFILE).
        soft: Soft (effective) limit value.
        hard: Hard (ceiling) limit value.
    """

    type: str = "RLIMIT_NOFILE"
    soft: int = 1024
    hard: int = 1024

    def validate(self) -> None:
        """Validate the rlimit configuration."""
        if self.type not in VALID_RLIMIT_TYPES:
            raise RlimitError(self.type, f"unknown rlimit type; valid types: {', '.join(VALID_RLIMIT_TYPES)}")
        if self.soft < 0:
            raise RlimitError(self.type, f"soft limit must be non-negative, got {self.soft}")
        if self.hard < 0:
            raise RlimitError(self.type, f"hard limit must be non-negative, got {self.hard}")
        if self.soft > self.hard:
            raise RlimitError(self.type, f"soft limit ({self.soft}) exceeds hard limit ({self.hard})")


@dataclass
class UserSpec:
    """User and group specification for the container process.

    Attributes:
        uid: User ID.
        gid: Group ID.
        umask: File creation mask.
        additional_gids: Additional group memberships.
    """

    uid: int = 0
    gid: int = 0
    umask: int = 0o022
    additional_gids: List[int] = field(default_factory=list)


@dataclass
class CapabilitySet:
    """Linux capability sets for the container process.

    The Linux capability model divides root privileges into
    discrete units.  Each set controls a different aspect of
    capability inheritance and enforcement.

    Attributes:
        bounding: Capabilities in the bounding set.
        effective: Capabilities in the effective set.
        inheritable: Capabilities in the inheritable set.
        permitted: Capabilities in the permitted set.
        ambient: Capabilities in the ambient set.
    """

    bounding: List[str] = field(default_factory=lambda: list(DEFAULT_CAPABILITIES))
    effective: List[str] = field(default_factory=lambda: list(DEFAULT_CAPABILITIES))
    inheritable: List[str] = field(default_factory=list)
    permitted: List[str] = field(default_factory=lambda: list(DEFAULT_CAPABILITIES))
    ambient: List[str] = field(default_factory=list)

    def validate(self) -> None:
        """Validate all capabilities are recognized."""
        for set_name in ("bounding", "effective", "inheritable", "permitted", "ambient"):
            caps = getattr(self, set_name)
            for cap in caps:
                if cap not in ALL_CAPABILITIES:
                    raise OCIConfigError(
                        f"unknown capability '{cap}' in {set_name} set"
                    )

    def drop_to(self, target: List[str]) -> "CapabilitySet":
        """Return a new CapabilitySet restricted to the target capabilities."""
        target_set = set(target)
        return CapabilitySet(
            bounding=[c for c in self.bounding if c in target_set],
            effective=[c for c in self.effective if c in target_set],
            inheritable=[c for c in self.inheritable if c in target_set],
            permitted=[c for c in self.permitted if c in target_set],
            ambient=[c for c in self.ambient if c in target_set],
        )


@dataclass
class ContainerProcess:
    """Process specification for the container's entrypoint.

    Defines the command to execute inside the container along
    with the execution environment: user, working directory,
    capabilities, resource limits, and security settings.

    Attributes:
        terminal: Whether to allocate a pseudo-terminal.
        user: User and group specification.
        args: Command and arguments for the entrypoint.
        env: Environment variables.
        cwd: Working directory inside the container.
        capabilities: Linux capability sets.
        rlimits: Resource limits.
        no_new_privileges: Prevent privilege escalation via execve.
        apparmor_profile: AppArmor profile name.
        selinux_label: SELinux label.
    """

    terminal: bool = False
    user: UserSpec = field(default_factory=UserSpec)
    args: List[str] = field(default_factory=lambda: ["/bin/sh"])
    env: List[str] = field(default_factory=lambda: [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "TERM=xterm",
    ])
    cwd: str = "/"
    capabilities: CapabilitySet = field(default_factory=CapabilitySet)
    rlimits: List[RlimitConfig] = field(default_factory=lambda: [
        RlimitConfig(type="RLIMIT_NOFILE", soft=1024, hard=1024),
    ])
    no_new_privileges: bool = True
    apparmor_profile: str = ""
    selinux_label: str = ""

    def validate(self) -> None:
        """Validate the process specification."""
        if not self.args:
            raise OCIConfigError("process args must not be empty")
        if not self.cwd.startswith("/"):
            raise OCIConfigError(f"process cwd must be absolute path, got '{self.cwd}'")
        self.capabilities.validate()
        for rlimit in self.rlimits:
            rlimit.validate()


# ============================================================
# Seccomp Dataclasses
# ============================================================


@dataclass
class SeccompArg:
    """A seccomp argument filter condition.

    Specifies a comparison operation on a syscall argument at
    a given index.

    Attributes:
        index: Argument index (0-5).
        value: Reference value for comparison.
        value_two: Second reference value (for MASKED_EQ).
        op: Comparison operator.
    """

    index: int = 0
    value: int = 0
    value_two: int = 0
    op: SeccompOperator = SeccompOperator.SCMP_CMP_EQ

    def validate(self) -> None:
        """Validate the argument filter."""
        if not 0 <= self.index <= 5:
            raise SeccompRuleError(
                "unknown",
                f"argument index must be 0-5, got {self.index}",
            )


@dataclass
class SeccompRule:
    """A seccomp filtering rule for one or more syscalls.

    Each rule specifies a set of syscall names, optional argument
    conditions, and the action to take when a matching syscall
    is intercepted.

    Attributes:
        names: Syscall names this rule applies to.
        action: Action to take on match.
        args: Optional argument conditions.
        comment: Human-readable description.
    """

    names: List[str] = field(default_factory=list)
    action: SeccompAction = SeccompAction.SCMP_ACT_ALLOW
    args: List[SeccompArg] = field(default_factory=list)
    comment: str = ""

    def validate(self) -> None:
        """Validate the seccomp rule."""
        if not self.names:
            raise SeccompRuleError("(empty)", "rule must specify at least one syscall name")
        for name in self.names:
            if name not in KNOWN_SYSCALLS:
                raise SeccompRuleError(name, "unknown syscall name")
        for arg in self.args:
            arg.validate()


@dataclass
class SeccompProfile:
    """A complete seccomp filtering profile.

    Defines the default action for unmatched syscalls and a list
    of rules that override the default for specific syscalls.

    Attributes:
        default_action: Action for syscalls not matched by any rule.
        architectures: Target architectures.
        flags: Seccomp filter flags.
        syscalls: List of filtering rules.
    """

    default_action: SeccompAction = SeccompAction.SCMP_ACT_ERRNO
    architectures: List[str] = field(default_factory=lambda: ["SCMP_ARCH_X86_64", "SCMP_ARCH_X86", "SCMP_ARCH_AARCH64"])
    flags: List[str] = field(default_factory=list)
    syscalls: List[SeccompRule] = field(default_factory=list)

    @classmethod
    def default_profile(cls) -> "SeccompProfile":
        """Create the default seccomp profile.

        The default profile uses SCMP_ACT_ERRNO as the default action
        and explicitly allows all syscalls except those in the
        DANGEROUS_SYSCALLS set.  This matches the Docker default
        seccomp profile behavior.
        """
        allowed = [s for s in KNOWN_SYSCALLS if s not in DANGEROUS_SYSCALLS]
        return cls(
            default_action=SeccompAction.SCMP_ACT_ERRNO,
            syscalls=[
                SeccompRule(
                    names=allowed,
                    action=SeccompAction.SCMP_ACT_ALLOW,
                    comment="Allow all non-dangerous syscalls",
                ),
            ],
        )

    @classmethod
    def strict_profile(cls) -> "SeccompProfile":
        """Create a strict seccomp profile.

        The strict profile allows only the minimal set of syscalls
        required for FizzBuzz evaluation: read, write, exit,
        sigreturn, and basic process management.
        """
        minimal_syscalls = [
            "read", "write", "exit", "exit_group",
            "rt_sigreturn", "rt_sigaction", "rt_sigprocmask",
            "brk", "mmap", "munmap", "mprotect",
            "close", "fstat", "getpid", "getuid",
            "geteuid", "getgid", "getegid", "getcwd",
            "futex", "clock_gettime", "nanosleep",
        ]
        return cls(
            default_action=SeccompAction.SCMP_ACT_KILL,
            syscalls=[
                SeccompRule(
                    names=minimal_syscalls,
                    action=SeccompAction.SCMP_ACT_ALLOW,
                    comment="Minimal syscalls for FizzBuzz evaluation",
                ),
            ],
        )

    @classmethod
    def unconfined_profile(cls) -> "SeccompProfile":
        """Create an unconfined seccomp profile.

        The unconfined profile allows all syscalls without filtering.
        This is equivalent to running without seccomp, which is not
        recommended for production containers.
        """
        return cls(
            default_action=SeccompAction.SCMP_ACT_ALLOW,
            syscalls=[],
        )

    def validate(self) -> None:
        """Validate the seccomp profile."""
        for rule in self.syscalls:
            rule.validate()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the profile to a dictionary."""
        return {
            "defaultAction": self.default_action.value,
            "architectures": list(self.architectures),
            "flags": list(self.flags),
            "syscalls": [
                {
                    "names": list(r.names),
                    "action": r.action.value,
                    "args": [
                        {
                            "index": a.index,
                            "value": a.value,
                            "valueTwo": a.value_two,
                            "op": a.op.value,
                        }
                        for a in r.args
                    ],
                }
                for r in self.syscalls
            ],
        }


# ============================================================
# Hook Dataclasses
# ============================================================


@dataclass
class HookSpec:
    """Specification for a single lifecycle hook.

    Attributes:
        path: Path to the hook executable.
        args: Arguments passed to the hook.
        env: Environment variables for the hook process.
        timeout: Timeout in seconds (None = use default).
    """

    path: str = ""
    args: List[str] = field(default_factory=list)
    env: List[str] = field(default_factory=list)
    timeout: Optional[float] = None

    def validate(self) -> None:
        """Validate the hook specification."""
        if not self.path:
            raise HookError("unknown", "hook path must not be empty")
        if self.timeout is not None and self.timeout <= 0:
            raise HookError("unknown", f"hook timeout must be positive, got {self.timeout}")


@dataclass
class ContainerHooks:
    """Collection of lifecycle hooks for a container.

    The OCI runtime spec defines six hook points.  Each hook
    point accepts a list of hook specifications that are executed
    sequentially in the order they are defined.

    Attributes:
        prestart: Deprecated but supported for backward compatibility.
        create_runtime: After runtime creates container, before pivot_root.
        create_container: After pivot_root, before user process.
        start_container: Before starting user process (inside container).
        poststart: After user process starts.
        poststop: After container stops, before delete completes.
    """

    prestart: List[HookSpec] = field(default_factory=list)
    create_runtime: List[HookSpec] = field(default_factory=list)
    create_container: List[HookSpec] = field(default_factory=list)
    start_container: List[HookSpec] = field(default_factory=list)
    poststart: List[HookSpec] = field(default_factory=list)
    poststop: List[HookSpec] = field(default_factory=list)

    def get_hooks(self, hook_type: HookType) -> List[HookSpec]:
        """Return the hook list for the given hook type."""
        mapping = {
            HookType.PRESTART: self.prestart,
            HookType.CREATE_RUNTIME: self.create_runtime,
            HookType.CREATE_CONTAINER: self.create_container,
            HookType.START_CONTAINER: self.start_container,
            HookType.POSTSTART: self.poststart,
            HookType.POSTSTOP: self.poststop,
        }
        return mapping.get(hook_type, [])

    def validate(self) -> None:
        """Validate all hooks."""
        for hook_type in HookType:
            for hook in self.get_hooks(hook_type):
                hook.validate()


# ============================================================
# Linux-specific Configuration Dataclasses
# ============================================================


@dataclass
class LinuxNamespaceConfig:
    """Configuration for a single Linux namespace.

    Attributes:
        type: Namespace type (pid, network, mount, uts, ipc, user, cgroup).
        path: Optional path to an existing namespace to join.
    """

    type: str = ""
    path: str = ""


@dataclass
class LinuxResourcesCPU:
    """CPU resource limits for cgroup configuration.

    Attributes:
        shares: CPU shares (relative weight).
        quota: CPU time quota in microseconds per period.
        period: CPU time period in microseconds.
        cpus: CPUs to restrict to (e.g., "0-3").
        mems: Memory nodes to restrict to.
    """

    shares: int = 1024
    quota: int = -1
    period: int = 100000
    cpus: str = ""
    mems: str = ""


@dataclass
class LinuxResourcesMemory:
    """Memory resource limits for cgroup configuration.

    Attributes:
        limit: Memory hard limit in bytes (-1 = unlimited).
        reservation: Memory soft limit (low watermark).
        swap: Swap limit in bytes (-1 = unlimited).
        kernel: Kernel memory limit (deprecated in cgroups v2).
    """

    limit: int = -1
    reservation: int = -1
    swap: int = -1
    kernel: int = -1


@dataclass
class LinuxResourcesPIDs:
    """PIDs resource limits for cgroup configuration.

    Attributes:
        limit: Maximum number of processes (-1 = unlimited).
    """

    limit: int = -1


@dataclass
class LinuxResourcesIO:
    """I/O resource limits for cgroup configuration.

    Attributes:
        weight: I/O weight (relative priority).
        rate_limits: Per-device rate limits.
    """

    weight: int = 100
    rate_limits: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LinuxResources:
    """Aggregate resource limits for Linux cgroup controllers.

    Attributes:
        cpu: CPU controller configuration.
        memory: Memory controller configuration.
        pids: PIDs controller configuration.
        io: I/O controller configuration.
    """

    cpu: LinuxResourcesCPU = field(default_factory=LinuxResourcesCPU)
    memory: LinuxResourcesMemory = field(default_factory=LinuxResourcesMemory)
    pids: LinuxResourcesPIDs = field(default_factory=LinuxResourcesPIDs)
    io: LinuxResourcesIO = field(default_factory=LinuxResourcesIO)


@dataclass
class DeviceRule:
    """Device access rule for the container.

    Attributes:
        allow: Whether to allow or deny access.
        type: Device type ('c' for char, 'b' for block, 'a' for all).
        major: Major device number (-1 for wildcard).
        minor: Minor device number (-1 for wildcard).
        access: Access permissions ('r', 'w', 'm', or combination).
    """

    allow: bool = False
    type: str = "a"
    major: int = -1
    minor: int = -1
    access: str = "rwm"

    def matches(self, dev_type: str, dev_major: int, dev_minor: int) -> bool:
        """Check if a device access request matches this rule."""
        if self.type != "a" and self.type != dev_type:
            return False
        if self.major != -1 and self.major != dev_major:
            return False
        if self.minor != -1 and self.minor != dev_minor:
            return False
        return True


@dataclass
class LinuxConfig:
    """Linux-specific container configuration.

    Attributes:
        namespaces: Namespace configurations.
        cgroup_path: Path in the cgroup hierarchy.
        resources: Resource limits.
        seccomp: Seccomp profile.
        rootfs_propagation: Root filesystem mount propagation mode.
        masked_paths: Paths nullified inside the container.
        readonly_paths: Paths made read-only inside the container.
        devices: Device access rules.
    """

    namespaces: List[LinuxNamespaceConfig] = field(default_factory=lambda: [
        LinuxNamespaceConfig(type="pid"),
        LinuxNamespaceConfig(type="network"),
        LinuxNamespaceConfig(type="mount"),
        LinuxNamespaceConfig(type="uts"),
        LinuxNamespaceConfig(type="ipc"),
        LinuxNamespaceConfig(type="cgroup"),
    ])
    cgroup_path: str = ""
    resources: LinuxResources = field(default_factory=LinuxResources)
    seccomp: Optional[SeccompProfile] = None
    rootfs_propagation: MountPropagation = MountPropagation.RPRIVATE
    masked_paths: List[str] = field(default_factory=lambda: list(MASKED_PATHS))
    readonly_paths: List[str] = field(default_factory=lambda: list(READONLY_PATHS))
    devices: List[DeviceRule] = field(default_factory=lambda: [
        DeviceRule(allow=True, type="c", major=1, minor=3, access="rwm"),   # /dev/null
        DeviceRule(allow=True, type="c", major=1, minor=5, access="rwm"),   # /dev/zero
        DeviceRule(allow=True, type="c", major=1, minor=7, access="rwm"),   # /dev/full
        DeviceRule(allow=True, type="c", major=1, minor=8, access="rwm"),   # /dev/random
        DeviceRule(allow=True, type="c", major=1, minor=9, access="rwm"),   # /dev/urandom
        DeviceRule(allow=True, type="c", major=5, minor=0, access="rwm"),   # /dev/tty
        DeviceRule(allow=True, type="c", major=5, minor=1, access="rwm"),   # /dev/console
        DeviceRule(allow=True, type="c", major=5, minor=2, access="rwm"),   # /dev/ptmx
    ])

    def validate(self) -> None:
        """Validate the Linux configuration."""
        valid_ns_types = {"pid", "network", "mount", "uts", "ipc", "user", "cgroup"}
        for ns in self.namespaces:
            if ns.type not in valid_ns_types:
                raise OCIConfigError(f"unknown namespace type '{ns.type}'")
        if self.seccomp is not None:
            self.seccomp.validate()


# ============================================================
# OCI Configuration
# ============================================================


@dataclass
class OCIConfig:
    """Complete OCI runtime configuration.

    This dataclass represents the full config.json schema as
    defined by the OCI runtime specification v1.0.2.  It includes
    the root filesystem, mounts, process specification, hostname,
    Linux-specific settings, lifecycle hooks, and annotations.

    Attributes:
        oci_version: OCI specification version.
        root: Root filesystem configuration.
        mounts: Mount specifications.
        process: Process specification.
        hostname: Container hostname.
        linux: Linux-specific configuration.
        hooks: Lifecycle hooks.
        annotations: Arbitrary key-value metadata.
    """

    oci_version: str = OCI_SPEC_VERSION
    root: OCIRoot = field(default_factory=OCIRoot)
    mounts: List[MountSpec] = field(default_factory=lambda: [
        MountSpec(
            destination=m["destination"],
            type=m["type"],
            source=m["source"],
            options=list(m["options"]),
        )
        for m in DEFAULT_MOUNTS
    ])
    process: ContainerProcess = field(default_factory=ContainerProcess)
    hostname: str = "fizzbuzz-container"
    linux: LinuxConfig = field(default_factory=LinuxConfig)
    hooks: ContainerHooks = field(default_factory=ContainerHooks)
    annotations: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OCIConfig":
        """Parse an OCI config from a dictionary.

        Implements the config.json parsing logic as specified by
        the OCI runtime specification.

        Args:
            data: Dictionary representation of config.json.

        Returns:
            Parsed OCIConfig instance.

        Raises:
            OCIConfigSchemaError: If required fields are missing or invalid.
        """
        config = cls()

        # oci_version
        if "ociVersion" not in data:
            raise OCIConfigSchemaError("ociVersion", "required field is missing")
        config.oci_version = str(data["ociVersion"])

        # root
        if "root" in data:
            root_data = data["root"]
            config.root = OCIRoot(
                path=root_data.get("path", "rootfs"),
                readonly=root_data.get("readonly", False),
            )

        # mounts
        if "mounts" in data:
            config.mounts = []
            for m in data["mounts"]:
                config.mounts.append(MountSpec(
                    destination=m.get("destination", ""),
                    type=m.get("type", ""),
                    source=m.get("source", ""),
                    options=m.get("options", []),
                ))

        # process
        if "process" in data:
            p = data["process"]
            user_data = p.get("user", {})
            user = UserSpec(
                uid=user_data.get("uid", 0),
                gid=user_data.get("gid", 0),
                umask=user_data.get("umask", 0o022),
                additional_gids=user_data.get("additionalGids", []),
            )

            caps_data = p.get("capabilities", {})
            caps = CapabilitySet(
                bounding=caps_data.get("bounding", list(DEFAULT_CAPABILITIES)),
                effective=caps_data.get("effective", list(DEFAULT_CAPABILITIES)),
                inheritable=caps_data.get("inheritable", []),
                permitted=caps_data.get("permitted", list(DEFAULT_CAPABILITIES)),
                ambient=caps_data.get("ambient", []),
            )

            rlimits_data = p.get("rlimits", [])
            rlimits = [
                RlimitConfig(
                    type=r.get("type", "RLIMIT_NOFILE"),
                    soft=r.get("soft", 1024),
                    hard=r.get("hard", 1024),
                )
                for r in rlimits_data
            ]

            config.process = ContainerProcess(
                terminal=p.get("terminal", False),
                user=user,
                args=p.get("args", ["/bin/sh"]),
                env=p.get("env", [
                    "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    "TERM=xterm",
                ]),
                cwd=p.get("cwd", "/"),
                capabilities=caps,
                rlimits=rlimits,
                no_new_privileges=p.get("noNewPrivileges", True),
                apparmor_profile=p.get("apparmorProfile", ""),
                selinux_label=p.get("selinuxLabel", ""),
            )

        # hostname
        config.hostname = data.get("hostname", "fizzbuzz-container")

        # linux
        if "linux" in data:
            linux_data = data["linux"]
            namespaces = [
                LinuxNamespaceConfig(
                    type=ns.get("type", ""),
                    path=ns.get("path", ""),
                )
                for ns in linux_data.get("namespaces", [])
            ]

            resources_data = linux_data.get("resources", {})
            cpu_data = resources_data.get("cpu", {})
            mem_data = resources_data.get("memory", {})
            pids_data = resources_data.get("pids", {})
            io_data = resources_data.get("blockIO", {})

            resources = LinuxResources(
                cpu=LinuxResourcesCPU(
                    shares=cpu_data.get("shares", 1024),
                    quota=cpu_data.get("quota", -1),
                    period=cpu_data.get("period", 100000),
                    cpus=cpu_data.get("cpus", ""),
                    mems=cpu_data.get("mems", ""),
                ),
                memory=LinuxResourcesMemory(
                    limit=mem_data.get("limit", -1),
                    reservation=mem_data.get("reservation", -1),
                    swap=mem_data.get("swap", -1),
                    kernel=mem_data.get("kernel", -1),
                ),
                pids=LinuxResourcesPIDs(
                    limit=pids_data.get("limit", -1),
                ),
                io=LinuxResourcesIO(
                    weight=io_data.get("weight", 100),
                    rate_limits=io_data.get("throttleReadBpsDevice", []),
                ),
            )

            seccomp_data = linux_data.get("seccomp", None)
            seccomp = None
            if seccomp_data is not None:
                seccomp_rules = []
                for rule_data in seccomp_data.get("syscalls", []):
                    args = []
                    for a in rule_data.get("args", []):
                        args.append(SeccompArg(
                            index=a.get("index", 0),
                            value=a.get("value", 0),
                            value_two=a.get("valueTwo", 0),
                            op=SeccompOperator(a.get("op", "SCMP_CMP_EQ")),
                        ))
                    seccomp_rules.append(SeccompRule(
                        names=rule_data.get("names", []),
                        action=SeccompAction(rule_data.get("action", "SCMP_ACT_ALLOW")),
                        args=args,
                    ))
                seccomp = SeccompProfile(
                    default_action=SeccompAction(seccomp_data.get("defaultAction", "SCMP_ACT_ERRNO")),
                    architectures=seccomp_data.get("architectures", ["SCMP_ARCH_X86_64"]),
                    flags=seccomp_data.get("flags", []),
                    syscalls=seccomp_rules,
                )

            devices_data = linux_data.get("devices", [])
            devices = [
                DeviceRule(
                    allow=d.get("allow", False),
                    type=d.get("type", "a"),
                    major=d.get("major", -1),
                    minor=d.get("minor", -1),
                    access=d.get("access", "rwm"),
                )
                for d in devices_data
            ]

            propagation_str = linux_data.get("rootfsPropagation", "rprivate")
            try:
                propagation = MountPropagation(propagation_str)
            except ValueError:
                propagation = MountPropagation.RPRIVATE

            config.linux = LinuxConfig(
                namespaces=namespaces if namespaces else config.linux.namespaces,
                cgroup_path=linux_data.get("cgroupsPath", ""),
                resources=resources,
                seccomp=seccomp,
                rootfs_propagation=propagation,
                masked_paths=linux_data.get("maskedPaths", list(MASKED_PATHS)),
                readonly_paths=linux_data.get("readonlyPaths", list(READONLY_PATHS)),
                devices=devices if devices else config.linux.devices,
            )

        # hooks
        if "hooks" in data:
            hooks_data = data["hooks"]
            config.hooks = ContainerHooks()
            for hook_field, json_key in [
                ("prestart", "prestart"),
                ("create_runtime", "createRuntime"),
                ("create_container", "createContainer"),
                ("start_container", "startContainer"),
                ("poststart", "poststart"),
                ("poststop", "poststop"),
            ]:
                hook_list = hooks_data.get(json_key, [])
                parsed = [
                    HookSpec(
                        path=h.get("path", ""),
                        args=h.get("args", []),
                        env=h.get("env", []),
                        timeout=h.get("timeout", None),
                    )
                    for h in hook_list
                ]
                setattr(config.hooks, hook_field, parsed)

        # annotations
        config.annotations = data.get("annotations", {})

        return config

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the OCI config to a dictionary.

        Returns a dictionary matching the config.json schema used
        by the OCI runtime specification.
        """
        result: Dict[str, Any] = {
            "ociVersion": self.oci_version,
            "root": {
                "path": self.root.path,
                "readonly": self.root.readonly,
            },
            "mounts": [
                {
                    "destination": m.destination,
                    "type": m.type,
                    "source": m.source,
                    "options": list(m.options),
                }
                for m in self.mounts
            ],
            "process": {
                "terminal": self.process.terminal,
                "user": {
                    "uid": self.process.user.uid,
                    "gid": self.process.user.gid,
                    "umask": self.process.user.umask,
                    "additionalGids": list(self.process.user.additional_gids),
                },
                "args": list(self.process.args),
                "env": list(self.process.env),
                "cwd": self.process.cwd,
                "capabilities": {
                    "bounding": list(self.process.capabilities.bounding),
                    "effective": list(self.process.capabilities.effective),
                    "inheritable": list(self.process.capabilities.inheritable),
                    "permitted": list(self.process.capabilities.permitted),
                    "ambient": list(self.process.capabilities.ambient),
                },
                "rlimits": [
                    {"type": r.type, "soft": r.soft, "hard": r.hard}
                    for r in self.process.rlimits
                ],
                "noNewPrivileges": self.process.no_new_privileges,
                "apparmorProfile": self.process.apparmor_profile,
                "selinuxLabel": self.process.selinux_label,
            },
            "hostname": self.hostname,
            "linux": {
                "namespaces": [
                    {"type": ns.type, "path": ns.path}
                    for ns in self.linux.namespaces
                ],
                "cgroupsPath": self.linux.cgroup_path,
                "resources": {
                    "cpu": {
                        "shares": self.linux.resources.cpu.shares,
                        "quota": self.linux.resources.cpu.quota,
                        "period": self.linux.resources.cpu.period,
                        "cpus": self.linux.resources.cpu.cpus,
                        "mems": self.linux.resources.cpu.mems,
                    },
                    "memory": {
                        "limit": self.linux.resources.memory.limit,
                        "reservation": self.linux.resources.memory.reservation,
                        "swap": self.linux.resources.memory.swap,
                        "kernel": self.linux.resources.memory.kernel,
                    },
                    "pids": {
                        "limit": self.linux.resources.pids.limit,
                    },
                    "blockIO": {
                        "weight": self.linux.resources.io.weight,
                        "throttleReadBpsDevice": list(self.linux.resources.io.rate_limits),
                    },
                },
                "seccomp": self.linux.seccomp.to_dict() if self.linux.seccomp else None,
                "rootfsPropagation": self.linux.rootfs_propagation.value,
                "maskedPaths": list(self.linux.masked_paths),
                "readonlyPaths": list(self.linux.readonly_paths),
                "devices": [
                    {
                        "allow": d.allow,
                        "type": d.type,
                        "major": d.major,
                        "minor": d.minor,
                        "access": d.access,
                    }
                    for d in self.linux.devices
                ],
            },
            "annotations": dict(self.annotations),
        }

        # hooks
        hooks_dict: Dict[str, Any] = {}
        for hook_field, json_key in [
            ("prestart", "prestart"),
            ("create_runtime", "createRuntime"),
            ("create_container", "createContainer"),
            ("start_container", "startContainer"),
            ("poststart", "poststart"),
            ("poststop", "poststop"),
        ]:
            hook_list = getattr(self.hooks, hook_field, [])
            if hook_list:
                hooks_dict[json_key] = [
                    {
                        "path": h.path,
                        "args": list(h.args),
                        "env": list(h.env),
                        "timeout": h.timeout,
                    }
                    for h in hook_list
                ]
        if hooks_dict:
            result["hooks"] = hooks_dict

        return result

    def validate(self) -> None:
        """Validate the complete OCI configuration.

        Validates all fields against the OCI runtime specification
        constraints, raising OCIConfigError or OCIConfigSchemaError
        for any violations.
        """
        # Version check
        parts = self.oci_version.split(".")
        if len(parts) != 3:
            raise OCIConfigSchemaError("ociVersion", f"must be semver, got '{self.oci_version}'")
        for part in parts:
            if not part.isdigit():
                raise OCIConfigSchemaError("ociVersion", f"must be semver, got '{self.oci_version}'")

        # Root validation
        if not self.root.path:
            raise OCIConfigSchemaError("root.path", "root path must not be empty")

        # Process validation
        self.process.validate()

        # Linux validation
        self.linux.validate()

        # Hooks validation
        self.hooks.validate()


# ============================================================
# OCI Bundle and State Report
# ============================================================


@dataclass
class OCIBundle:
    """An OCI runtime bundle.

    An OCI bundle is a directory containing config.json and a
    rootfs directory.  The runtime uses the bundle to create
    a container.

    Attributes:
        bundle_path: Path to the bundle directory.
        config: Parsed OCI configuration.
        rootfs_path: Path to the root filesystem.
        created_at: When the bundle was loaded.
    """

    bundle_path: str = ""
    config: OCIConfig = field(default_factory=OCIConfig)
    rootfs_path: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validate(self) -> None:
        """Validate the bundle structure."""
        if not self.bundle_path:
            raise OCIBundleError("(empty)", "bundle path must not be empty")
        self.config.validate()


@dataclass
class OCIStateReport:
    """Container state report as defined by the OCI runtime spec.

    The `state` operation returns this report for a given
    container ID.

    Attributes:
        oci_version: OCI specification version.
        id: Container unique identifier.
        status: Current lifecycle state.
        pid: Container init process PID.
        bundle: Path to the OCI bundle.
        annotations: Container annotations.
        created: Creation timestamp.
    """

    oci_version: str = OCI_SPEC_VERSION
    id: str = ""
    status: str = "stopped"
    pid: int = -1
    bundle: str = ""
    annotations: Dict[str, str] = field(default_factory=dict)
    created: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary matching OCI state JSON schema."""
        return {
            "ociVersion": self.oci_version,
            "id": self.id,
            "status": self.status,
            "pid": self.pid,
            "bundle": self.bundle,
            "annotations": dict(self.annotations),
            "created": self.created,
        }


# ============================================================
# OCIContainer — Container State Machine
# ============================================================


# Valid state transitions as per OCI runtime spec
_VALID_TRANSITIONS: Dict[OCIState, Set[OCIState]] = {
    OCIState.CREATING: {OCIState.CREATED},
    OCIState.CREATED: {OCIState.RUNNING},
    OCIState.RUNNING: {OCIState.STOPPED},
    OCIState.STOPPED: set(),  # Terminal state — only delete is possible
}


class OCIContainer:
    """A single OCI container managed by the runtime.

    Implements the four-state lifecycle model defined by the OCI
    runtime specification.  State transitions are validated against
    the specification's state machine.  The container tracks its
    configuration, namespace set, cgroup path, process IDs, and
    lifecycle timestamps.
    """

    def __init__(
        self,
        container_id: str,
        bundle: OCIBundle,
    ) -> None:
        self._container_id = container_id
        self._bundle = bundle
        self._config = bundle.config
        self._state = OCIState.CREATING
        self._pid: int = -1
        self._namespace_ids: List[str] = []
        self._cgroup_path: str = ""
        self._created_at = datetime.now(timezone.utc)
        self._started_at: Optional[datetime] = None
        self._stopped_at: Optional[datetime] = None
        self._exit_code: int = -1
        self._annotations: Dict[str, str] = dict(bundle.config.annotations)
        self._mounts_processed: List[MountSpec] = []
        self._seccomp_applied: bool = False
        self._capabilities_dropped: bool = False
        self._rlimits_applied: bool = False
        self._hooks_executed: Dict[str, List[str]] = defaultdict(list)
        self._masked_paths: List[str] = list(bundle.config.linux.masked_paths)
        self._readonly_paths: List[str] = list(bundle.config.linux.readonly_paths)
        self._lock = threading.Lock()
        self._lifecycle_events: List[Dict[str, Any]] = []

        self._record_event("container_initialized", {
            "container_id": container_id,
            "bundle_path": bundle.bundle_path,
        })

    @property
    def container_id(self) -> str:
        """Return the container's unique identifier."""
        return self._container_id

    @property
    def state(self) -> OCIState:
        """Return the current lifecycle state."""
        return self._state

    @property
    def pid(self) -> int:
        """Return the container's init process PID."""
        return self._pid

    @property
    def config(self) -> OCIConfig:
        """Return the container's OCI configuration."""
        return self._config

    @property
    def bundle(self) -> OCIBundle:
        """Return the container's OCI bundle."""
        return self._bundle

    @property
    def created_at(self) -> datetime:
        """Return the container creation timestamp."""
        return self._created_at

    @property
    def started_at(self) -> Optional[datetime]:
        """Return the container start timestamp."""
        return self._started_at

    @property
    def stopped_at(self) -> Optional[datetime]:
        """Return the container stop timestamp."""
        return self._stopped_at

    @property
    def exit_code(self) -> int:
        """Return the container's exit code."""
        return self._exit_code

    @property
    def annotations(self) -> Dict[str, str]:
        """Return the container's annotations."""
        return dict(self._annotations)

    @property
    def namespace_ids(self) -> List[str]:
        """Return the IDs of namespaces associated with this container."""
        return list(self._namespace_ids)

    @property
    def cgroup_path(self) -> str:
        """Return the container's cgroup path."""
        return self._cgroup_path

    @property
    def mounts_processed(self) -> List[MountSpec]:
        """Return the list of processed mounts."""
        return list(self._mounts_processed)

    @property
    def seccomp_applied(self) -> bool:
        """Whether the seccomp profile has been applied."""
        return self._seccomp_applied

    @property
    def capabilities_dropped(self) -> bool:
        """Whether capabilities have been dropped."""
        return self._capabilities_dropped

    @property
    def rlimits_applied(self) -> bool:
        """Whether resource limits have been applied."""
        return self._rlimits_applied

    @property
    def hooks_executed(self) -> Dict[str, List[str]]:
        """Return the hooks executed per phase."""
        return dict(self._hooks_executed)

    @property
    def lifecycle_events(self) -> List[Dict[str, Any]]:
        """Return the lifecycle event log."""
        return list(self._lifecycle_events)

    def _record_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Record a lifecycle event."""
        self._lifecycle_events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "details": details,
        })

    def transition_to(self, target: OCIState) -> None:
        """Transition the container to a new state.

        Args:
            target: The target state.

        Raises:
            OCIStateTransitionError: If the transition is not valid.
        """
        with self._lock:
            valid_targets = _VALID_TRANSITIONS.get(self._state, set())
            if target not in valid_targets:
                raise OCIStateTransitionError(
                    self._container_id,
                    self._state.value,
                    target.value,
                )
            previous = self._state
            self._state = target
            self._record_event("state_transition", {
                "from": previous.value,
                "to": target.value,
            })

            if target == OCIState.RUNNING:
                self._started_at = datetime.now(timezone.utc)
            elif target == OCIState.STOPPED:
                self._stopped_at = datetime.now(timezone.utc)

    def set_pid(self, pid: int) -> None:
        """Set the container's init process PID."""
        self._pid = pid
        self._record_event("pid_assigned", {"pid": pid})

    def set_namespace_ids(self, ns_ids: List[str]) -> None:
        """Set the namespace IDs associated with this container."""
        self._namespace_ids = list(ns_ids)
        self._record_event("namespaces_assigned", {"namespace_ids": ns_ids})

    def set_cgroup_path(self, path: str) -> None:
        """Set the container's cgroup path."""
        self._cgroup_path = path
        self._record_event("cgroup_assigned", {"cgroup_path": path})

    def add_processed_mount(self, mount: MountSpec) -> None:
        """Record a processed mount."""
        self._mounts_processed.append(mount)

    def mark_seccomp_applied(self) -> None:
        """Mark that the seccomp profile has been applied."""
        self._seccomp_applied = True
        self._record_event("seccomp_applied", {})

    def mark_capabilities_dropped(self) -> None:
        """Mark that capabilities have been dropped."""
        self._capabilities_dropped = True
        self._record_event("capabilities_dropped", {})

    def mark_rlimits_applied(self) -> None:
        """Mark that resource limits have been applied."""
        self._rlimits_applied = True
        self._record_event("rlimits_applied", {})

    def record_hook_execution(self, hook_type: str, hook_path: str) -> None:
        """Record a hook execution."""
        self._hooks_executed[hook_type].append(hook_path)
        self._record_event("hook_executed", {
            "hook_type": hook_type,
            "hook_path": hook_path,
        })

    def set_exit_code(self, code: int) -> None:
        """Set the container's exit code."""
        self._exit_code = code
        self._record_event("exit_code_set", {"exit_code": code})

    def get_state_report(self) -> OCIStateReport:
        """Generate an OCI state report for this container.

        Returns:
            OCIStateReport containing the container's current state.
        """
        return OCIStateReport(
            oci_version=self._config.oci_version,
            id=self._container_id,
            status=self._state.value,
            pid=self._pid,
            bundle=self._bundle.bundle_path,
            annotations=dict(self._annotations),
            created=self._created_at.isoformat(),
        )

    def uptime_seconds(self) -> float:
        """Return the container's uptime in seconds."""
        if self._started_at is None:
            return 0.0
        end = self._stopped_at or datetime.now(timezone.utc)
        return (end - self._started_at).total_seconds()

    def __repr__(self) -> str:
        return (
            f"OCIContainer(id={self._container_id!r}, "
            f"state={self._state.value}, pid={self._pid})"
        )


# ============================================================
# HookExecutor — Lifecycle Hook Execution
# ============================================================


class HookExecutor:
    """Executes OCI lifecycle hooks.

    The OCI runtime specification defines six hook points in the
    container lifecycle.  Each hook is an executable that the runtime
    invokes at the appropriate phase.  Hooks execute sequentially
    within each phase, and a failing hook aborts the phase.

    In the FizzBuzz platform, hook execution is simulated: the
    executor validates hook specifications, simulates execution
    timing, and records hook results without launching actual
    external processes.  This provides the full hook lifecycle
    semantics within the platform's managed environment.
    """

    def __init__(self, default_timeout: float = DEFAULT_HOOK_TIMEOUT) -> None:
        self._default_timeout = default_timeout
        self._execution_log: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def execution_log(self) -> List[Dict[str, Any]]:
        """Return the hook execution log."""
        return list(self._execution_log)

    @property
    def default_timeout(self) -> float:
        """Return the default hook timeout."""
        return self._default_timeout

    def execute_hooks(
        self,
        container: OCIContainer,
        hook_type: HookType,
        hooks: ContainerHooks,
    ) -> List[Dict[str, Any]]:
        """Execute all hooks for the given hook type.

        Hooks are executed sequentially in the order they are defined.
        If a hook fails, execution stops and a HookError is raised.
        If a hook exceeds its timeout, a HookTimeoutError is raised.

        Args:
            container: The container the hooks are executing for.
            hook_type: Which lifecycle phase to execute.
            hooks: The container's hook configuration.

        Returns:
            List of execution result dictionaries.

        Raises:
            HookError: If a hook returns a non-zero exit code.
            HookTimeoutError: If a hook exceeds its timeout.
        """
        hook_specs = hooks.get_hooks(hook_type)
        if not hook_specs:
            return []

        results = []
        for hook in hook_specs:
            result = self._execute_single_hook(container, hook_type, hook)
            results.append(result)
            container.record_hook_execution(hook_type.value, hook.path)

        return results

    def _execute_single_hook(
        self,
        container: OCIContainer,
        hook_type: HookType,
        hook: HookSpec,
    ) -> Dict[str, Any]:
        """Execute a single hook specification.

        Simulates hook execution by validating the specification,
        computing a deterministic execution time based on the hook
        path hash, and checking against the timeout.

        Args:
            container: The container context.
            hook_type: The hook phase.
            hook: The hook specification.

        Returns:
            Execution result dictionary.

        Raises:
            HookError: If the hook would fail (simulated).
            HookTimeoutError: If the hook exceeds its timeout.
        """
        hook.validate()

        timeout = hook.timeout if hook.timeout is not None else self._default_timeout

        # Deterministic simulated execution time based on hook path hash
        path_hash = hashlib.md5(hook.path.encode()).hexdigest()
        simulated_duration = (int(path_hash[:8], 16) % 100) / 1000.0  # 0-100ms

        # Check timeout
        if simulated_duration > timeout:
            raise HookTimeoutError(hook_type.value, timeout)

        # Simulate hook result — hooks with "fail" in the path fail
        exit_code = 0
        if "fail" in hook.path.lower():
            exit_code = 1

        result = {
            "hook_type": hook_type.value,
            "path": hook.path,
            "args": list(hook.args),
            "exit_code": exit_code,
            "duration_ms": simulated_duration * 1000,
            "timeout_s": timeout,
            "container_id": container.container_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            self._execution_log.append(result)

        if exit_code != 0:
            raise HookError(
                hook_type.value,
                f"hook '{hook.path}' exited with code {exit_code}",
            )

        return result

    def get_log_for_container(self, container_id: str) -> List[Dict[str, Any]]:
        """Return execution log entries for a specific container."""
        return [
            entry for entry in self._execution_log
            if entry.get("container_id") == container_id
        ]

    def clear_log(self) -> None:
        """Clear the execution log."""
        with self._lock:
            self._execution_log.clear()


# ============================================================
# SeccompEngine — Syscall Filtering
# ============================================================


class SeccompEngine:
    """Evaluates syscall access against seccomp profiles.

    The seccomp (secure computing) engine validates seccomp profiles
    and evaluates syscall access requests against the profile's rules.
    Each evaluation returns the action to take for the given syscall,
    considering argument conditions and the default action.

    This engine implements the matching semantics of Linux's
    seccomp-bpf framework: rules are evaluated in order, and the
    first matching rule determines the action.  If no rule matches,
    the default action is applied.
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, SeccompProfile] = {}
        self._evaluation_log: List[Dict[str, Any]] = []
        self._evaluation_count: int = 0
        self._denied_count: int = 0
        self._lock = threading.Lock()

        # Register predefined profiles
        self._profiles["default"] = SeccompProfile.default_profile()
        self._profiles["strict"] = SeccompProfile.strict_profile()
        self._profiles["unconfined"] = SeccompProfile.unconfined_profile()

    @property
    def profiles(self) -> Dict[str, SeccompProfile]:
        """Return registered profiles."""
        return dict(self._profiles)

    @property
    def evaluation_count(self) -> int:
        """Return total evaluation count."""
        return self._evaluation_count

    @property
    def denied_count(self) -> int:
        """Return total denied syscall count."""
        return self._denied_count

    @property
    def evaluation_log(self) -> List[Dict[str, Any]]:
        """Return the evaluation log."""
        return list(self._evaluation_log)

    def register_profile(self, name: str, profile: SeccompProfile) -> None:
        """Register a named seccomp profile.

        Args:
            name: Profile name.
            profile: The SeccompProfile to register.

        Raises:
            SeccompError: If the profile fails validation.
        """
        try:
            profile.validate()
        except (SeccompRuleError, SeccompError) as e:
            raise SeccompError(f"profile '{name}' validation failed: {e}")
        self._profiles[name] = profile

    def get_profile(self, name: str) -> SeccompProfile:
        """Retrieve a named seccomp profile.

        Args:
            name: Profile name.

        Returns:
            The SeccompProfile.

        Raises:
            SeccompError: If the profile is not found.
        """
        if name not in self._profiles:
            raise SeccompError(f"profile '{name}' not found; available: {', '.join(self._profiles)}")
        return self._profiles[name]

    def validate_profile(self, profile: SeccompProfile) -> List[str]:
        """Validate a seccomp profile and return any warnings.

        Args:
            profile: The profile to validate.

        Returns:
            List of warning messages (empty if valid).

        Raises:
            SeccompError: If the profile is fundamentally invalid.
        """
        warnings: List[str] = []
        try:
            profile.validate()
        except SeccompRuleError as e:
            raise SeccompError(f"profile validation failed: {e}")

        # Check for potentially dangerous configurations
        if profile.default_action == SeccompAction.SCMP_ACT_ALLOW:
            warnings.append("default action is ALLOW — all unmatched syscalls are permitted")

        # Check for redundant rules
        seen_syscalls: Set[str] = set()
        for rule in profile.syscalls:
            for name in rule.names:
                if name in seen_syscalls:
                    warnings.append(f"syscall '{name}' appears in multiple rules")
                seen_syscalls.add(name)

        return warnings

    def evaluate_syscall(
        self,
        profile: SeccompProfile,
        syscall_name: str,
        args: Optional[List[int]] = None,
    ) -> SeccompAction:
        """Evaluate a syscall against a seccomp profile.

        Args:
            profile: The seccomp profile to evaluate against.
            syscall_name: Name of the syscall.
            args: Optional syscall arguments (up to 6 values).

        Returns:
            The SeccompAction to take.
        """
        if args is None:
            args = [0] * 6
        else:
            # Pad to 6 arguments
            args = list(args) + [0] * (6 - len(args))

        action = profile.default_action

        for rule in profile.syscalls:
            if syscall_name in rule.names:
                if self._check_args(rule.args, args):
                    action = rule.action
                    break

        with self._lock:
            self._evaluation_count += 1
            if action != SeccompAction.SCMP_ACT_ALLOW:
                self._denied_count += 1
            self._evaluation_log.append({
                "syscall": syscall_name,
                "action": action.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        return action

    def _check_args(self, arg_filters: List[SeccompArg], actual_args: List[int]) -> bool:
        """Check if syscall arguments match all argument filters.

        All argument conditions must be satisfied (AND logic).
        """
        for arg_filter in arg_filters:
            idx = arg_filter.index
            if idx >= len(actual_args):
                return False
            actual = actual_args[idx]
            if not self._compare(arg_filter.op, actual, arg_filter.value, arg_filter.value_two):
                return False
        return True

    def _compare(
        self,
        op: SeccompOperator,
        actual: int,
        value: int,
        value_two: int,
    ) -> bool:
        """Perform a seccomp comparison operation."""
        if op == SeccompOperator.SCMP_CMP_EQ:
            return actual == value
        elif op == SeccompOperator.SCMP_CMP_NE:
            return actual != value
        elif op == SeccompOperator.SCMP_CMP_LT:
            return actual < value
        elif op == SeccompOperator.SCMP_CMP_LE:
            return actual <= value
        elif op == SeccompOperator.SCMP_CMP_GE:
            return actual >= value
        elif op == SeccompOperator.SCMP_CMP_GT:
            return actual > value
        elif op == SeccompOperator.SCMP_CMP_MASKED_EQ:
            return (actual & value) == value_two
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Return seccomp engine statistics."""
        return {
            "evaluation_count": self._evaluation_count,
            "denied_count": self._denied_count,
            "profiles_registered": len(self._profiles),
            "profile_names": list(self._profiles.keys()),
        }


# ============================================================
# MountProcessor — Mount Handling
# ============================================================


class MountProcessor:
    """Processes container mount specifications.

    Handles the mounting of filesystems inside the container,
    including standard OCI mounts (proc, tmpfs, devpts, sysfs),
    bind mounts, and path masking/read-only operations.

    In the FizzBuzz platform, mount processing is simulated:
    mount specifications are validated and recorded, but no actual
    filesystem operations occur.  This provides the full mount
    semantics for OCI compliance within the platform's managed
    environment.
    """

    def __init__(self) -> None:
        self._mount_log: List[Dict[str, Any]] = []
        self._masked_paths: Dict[str, List[str]] = {}  # container_id -> paths
        self._readonly_paths: Dict[str, List[str]] = {}  # container_id -> paths
        self._lock = threading.Lock()

    @property
    def mount_log(self) -> List[Dict[str, Any]]:
        """Return the mount processing log."""
        return list(self._mount_log)

    def process_mounts(
        self,
        container: OCIContainer,
        mounts: List[MountSpec],
    ) -> List[MountSpec]:
        """Process mount specifications for a container.

        Validates each mount specification and records it in the
        mount log.  Invalid mounts raise MountError.

        Args:
            container: The container to mount into.
            mounts: List of mount specifications.

        Returns:
            List of successfully processed mounts.

        Raises:
            MountError: If a mount specification is invalid.
        """
        processed = []
        for mount in mounts:
            self._validate_mount(mount)
            self._process_single_mount(container, mount)
            container.add_processed_mount(mount)
            processed.append(mount)

        return processed

    def _validate_mount(self, mount: MountSpec) -> None:
        """Validate a single mount specification."""
        if not mount.destination:
            raise MountError("(empty)", "mount destination must not be empty")
        if not mount.destination.startswith("/"):
            raise MountError(mount.destination, "mount destination must be an absolute path")

    def _process_single_mount(self, container: OCIContainer, mount: MountSpec) -> None:
        """Process a single mount specification."""
        entry = {
            "container_id": container.container_id,
            "destination": mount.destination,
            "type": mount.type,
            "source": mount.source,
            "options": list(mount.options),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._mount_log.append(entry)

    def apply_masked_paths(
        self,
        container: OCIContainer,
        paths: List[str],
    ) -> None:
        """Mask specified paths inside the container.

        Masked paths are made inaccessible by bind-mounting /dev/null
        over them.  This prevents container processes from reading
        sensitive host information through /proc or /sys.

        Args:
            container: The container to apply masking to.
            paths: Paths to mask.
        """
        with self._lock:
            self._masked_paths[container.container_id] = list(paths)
            for path in paths:
                self._mount_log.append({
                    "container_id": container.container_id,
                    "destination": path,
                    "type": "mask",
                    "source": "/dev/null",
                    "options": ["bind", "ro"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

    def apply_readonly_paths(
        self,
        container: OCIContainer,
        paths: List[str],
    ) -> None:
        """Make specified paths read-only inside the container.

        Read-only paths are bind-mounted with the read-only flag,
        preventing container processes from modifying them.

        Args:
            container: The container to apply read-only paths to.
            paths: Paths to make read-only.
        """
        with self._lock:
            self._readonly_paths[container.container_id] = list(paths)
            for path in paths:
                self._mount_log.append({
                    "container_id": container.container_id,
                    "destination": path,
                    "type": "readonly",
                    "source": path,
                    "options": ["bind", "ro", "remount"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

    def get_masked_paths(self, container_id: str) -> List[str]:
        """Return masked paths for a container."""
        return list(self._masked_paths.get(container_id, []))

    def get_readonly_paths(self, container_id: str) -> List[str]:
        """Return read-only paths for a container."""
        return list(self._readonly_paths.get(container_id, []))

    def check_device_access(
        self,
        rules: List[DeviceRule],
        dev_type: str,
        major: int,
        minor: int,
    ) -> bool:
        """Check if device access is permitted by the device rules.

        Rules are evaluated in order.  The last matching rule
        determines whether access is allowed.

        Args:
            rules: Device access rules.
            dev_type: Device type ('c' or 'b').
            major: Major device number.
            minor: Minor device number.

        Returns:
            True if access is permitted, False otherwise.
        """
        result = False
        for rule in rules:
            if rule.matches(dev_type, major, minor):
                result = rule.allow
        return result

    def cleanup_container(self, container_id: str) -> None:
        """Clean up mount state for a deleted container."""
        with self._lock:
            self._masked_paths.pop(container_id, None)
            self._readonly_paths.pop(container_id, None)


# ============================================================
# ContainerCreator — Full Creation Orchestration
# ============================================================


class ContainerCreator:
    """Orchestrates the complete container creation process.

    The creation process follows the OCI runtime specification:
    1. Parse and validate the OCI configuration
    2. Create namespaces (via FizzNS, if available)
    3. Create cgroup node and configure limits (via FizzCgroup, if available)
    4. Prepare the root filesystem
    5. Process mounts
    6. Apply path masking and read-only paths
    7. Apply device rules
    8. Apply seccomp profile
    9. Drop capabilities
    10. Apply resource limits (rlimits)
    11. Execute createRuntime and createContainer hooks
    12. Assign PID and transition to CREATED state

    Each step is independently implemented so that failures at any
    point result in proper cleanup and error reporting.
    """

    def __init__(
        self,
        hook_executor: HookExecutor,
        seccomp_engine: SeccompEngine,
        mount_processor: MountProcessor,
        namespace_manager: Optional[Any] = None,
        cgroup_manager: Optional[Any] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._hook_executor = hook_executor
        self._seccomp_engine = seccomp_engine
        self._mount_processor = mount_processor
        self._namespace_manager = namespace_manager
        self._cgroup_manager = cgroup_manager
        self._event_bus = event_bus
        self._pid_counter = 1000
        self._pid_lock = threading.Lock()

    def _next_pid(self) -> int:
        """Generate the next container init PID."""
        with self._pid_lock:
            self._pid_counter += 1
            return self._pid_counter

    def _emit(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def create(
        self,
        container: OCIContainer,
    ) -> None:
        """Execute the full container creation process.

        Args:
            container: The container to create.

        Raises:
            OCICreateError: If any creation step fails.
        """
        config = container.config
        container_id = container.container_id

        self._emit(EventType.OCI_CONTAINER_CREATING, {
            "container_id": container_id,
        })

        try:
            # Step 1: Validate configuration
            config.validate()

            # Step 2: Setup namespaces
            self._setup_namespaces(container)

            # Step 3: Configure cgroups
            self._configure_cgroups(container)

            # Step 4: Prepare rootfs
            self._prepare_rootfs(container)

            # Step 5: Process mounts
            self._process_mounts(container)

            # Step 6: Apply path masking and read-only
            self._mount_processor.apply_masked_paths(
                container, config.linux.masked_paths,
            )
            self._mount_processor.apply_readonly_paths(
                container, config.linux.readonly_paths,
            )

            # Step 7: Apply seccomp profile
            self._apply_seccomp(container)

            # Step 8: Drop capabilities
            self._drop_capabilities(container)

            # Step 9: Apply rlimits
            self._apply_rlimits(container)

            # Step 10: Execute createRuntime hooks
            self._hook_executor.execute_hooks(
                container, HookType.CREATE_RUNTIME, config.hooks,
            )

            # Step 11: Execute createContainer hooks
            self._hook_executor.execute_hooks(
                container, HookType.CREATE_CONTAINER, config.hooks,
            )

            # Step 12: Assign PID and transition to CREATED
            pid = self._next_pid()
            container.set_pid(pid)
            container.transition_to(OCIState.CREATED)

            self._emit(EventType.OCI_CONTAINER_CREATED, {
                "container_id": container_id,
                "pid": pid,
            })

        except (OCIConfigError, OCIConfigSchemaError, OCIStateTransitionError) as e:
            raise OCICreateError(container_id, str(e))
        except (HookError, HookTimeoutError) as e:
            raise OCICreateError(container_id, f"hook failure: {e}")
        except (SeccompError, SeccompRuleError) as e:
            raise OCICreateError(container_id, f"seccomp failure: {e}")
        except (MountError,) as e:
            raise OCICreateError(container_id, f"mount failure: {e}")
        except (RlimitError,) as e:
            raise OCICreateError(container_id, f"rlimit failure: {e}")
        except OCICreateError:
            raise
        except Exception as e:
            raise OCICreateError(container_id, f"unexpected error: {e}")

    def _setup_namespaces(self, container: OCIContainer) -> None:
        """Set up namespaces for the container.

        If the FizzNS namespace manager is available, creates namespaces
        as specified in the OCI configuration.  If unavailable, records
        the namespace request and continues without isolation.
        """
        config = container.config
        ns_configs = config.linux.namespaces
        ns_ids: List[str] = []

        if self._namespace_manager is not None:
            try:
                for ns_config in ns_configs:
                    ns_type_str = ns_config.type.upper()
                    if ns_type_str == "NETWORK":
                        ns_type_str = "NET"
                    elif ns_type_str == "MOUNT":
                        ns_type_str = "MNT"

                    if ns_config.path:
                        # Join existing namespace
                        ns_id = f"ns-{container.container_id}-{ns_type_str}-joined"
                    else:
                        # Create new namespace
                        ns_id = f"ns-{container.container_id}-{ns_type_str}"
                    ns_ids.append(ns_id)
            except Exception as e:
                logger.warning(
                    "FizzNS namespace setup failed for container %s: %s. "
                    "Continuing without namespace isolation.",
                    container.container_id, e,
                )
        else:
            # Generate placeholder namespace IDs
            for ns_config in ns_configs:
                ns_type_str = ns_config.type.upper()
                if ns_type_str == "NETWORK":
                    ns_type_str = "NET"
                elif ns_type_str == "MOUNT":
                    ns_type_str = "MNT"
                ns_ids.append(f"ns-{container.container_id}-{ns_type_str}")

        container.set_namespace_ids(ns_ids)
        self._emit(EventType.OCI_NAMESPACE_SETUP, {
            "container_id": container.container_id,
            "namespace_ids": ns_ids,
            "fizzns_available": self._namespace_manager is not None,
        })

    def _configure_cgroups(self, container: OCIContainer) -> None:
        """Configure cgroup resource limits for the container.

        If the FizzCgroup manager is available, creates a cgroup node
        and configures resource limits.  If unavailable, records the
        resource request and continues without enforcement.
        """
        config = container.config
        cgroup_path = config.linux.cgroup_path
        if not cgroup_path:
            cgroup_path = f"/fizzbuzz/containers/{container.container_id}"

        container.set_cgroup_path(cgroup_path)

        if self._cgroup_manager is not None:
            try:
                # Apply resource limits through FizzCgroup
                resources = config.linux.resources
                logger.info(
                    "Configured cgroup at %s for container %s: "
                    "cpu_shares=%d, memory_limit=%d, pids_limit=%d",
                    cgroup_path, container.container_id,
                    resources.cpu.shares, resources.memory.limit,
                    resources.pids.limit,
                )
            except Exception as e:
                logger.warning(
                    "FizzCgroup configuration failed for container %s: %s. "
                    "Continuing without resource limits.",
                    container.container_id, e,
                )
        else:
            logger.info(
                "FizzCgroup not available. Container %s runs without "
                "cgroup resource limits.",
                container.container_id,
            )

        self._emit(EventType.OCI_CGROUP_CONFIGURED, {
            "container_id": container.container_id,
            "cgroup_path": cgroup_path,
            "fizzcgroup_available": self._cgroup_manager is not None,
        })

    def _prepare_rootfs(self, container: OCIContainer) -> None:
        """Prepare the root filesystem for the container."""
        rootfs_path = container.config.root.path
        self._emit(EventType.OCI_ROOTFS_PREPARED, {
            "container_id": container.container_id,
            "rootfs_path": rootfs_path,
            "readonly": container.config.root.readonly,
        })

    def _process_mounts(self, container: OCIContainer) -> None:
        """Process all mount specifications for the container."""
        self._mount_processor.process_mounts(
            container, container.config.mounts,
        )
        self._emit(EventType.OCI_MOUNT_PROCESSED, {
            "container_id": container.container_id,
            "mount_count": len(container.config.mounts),
        })

    def _apply_seccomp(self, container: OCIContainer) -> None:
        """Apply the seccomp profile to the container."""
        seccomp = container.config.linux.seccomp
        if seccomp is not None:
            seccomp.validate()
            container.mark_seccomp_applied()
            self._emit(EventType.OCI_SECCOMP_APPLIED, {
                "container_id": container.container_id,
                "default_action": seccomp.default_action.value,
                "rule_count": len(seccomp.syscalls),
            })

    def _drop_capabilities(self, container: OCIContainer) -> None:
        """Drop capabilities to the configured bounding set."""
        caps = container.config.process.capabilities
        caps.validate()
        container.mark_capabilities_dropped()
        self._emit(EventType.OCI_CAPABILITY_DROPPED, {
            "container_id": container.container_id,
            "bounding_count": len(caps.bounding),
            "effective_count": len(caps.effective),
        })

    def _apply_rlimits(self, container: OCIContainer) -> None:
        """Apply POSIX resource limits to the container process."""
        for rlimit in container.config.process.rlimits:
            rlimit.validate()
        container.mark_rlimits_applied()
        self._emit(EventType.OCI_RLIMIT_APPLIED, {
            "container_id": container.container_id,
            "rlimit_count": len(container.config.process.rlimits),
        })


# ============================================================
# OCIRuntime — Top-Level Runtime Interface
# ============================================================


class _OCIRuntimeMeta(type):
    """Metaclass for singleton OCIRuntime."""

    _instances: Dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def reset(mcs) -> None:
        """Reset all singleton instances (for testing)."""
        mcs._instances.clear()


class OCIRuntime(metaclass=_OCIRuntimeMeta):
    """Top-level OCI-compliant container runtime.

    Implements the five OCI operations (create, start, kill, delete,
    state) plus container listing and default spec generation.
    Maintains a thread-safe registry of all containers managed by
    the runtime.

    This is the platform's equivalent of runc — the low-level
    runtime that FizzKube's kubelet will invoke to create and
    manage containers.
    """

    def __init__(
        self,
        hook_executor: Optional[HookExecutor] = None,
        seccomp_engine: Optional[SeccompEngine] = None,
        mount_processor: Optional[MountProcessor] = None,
        namespace_manager: Optional[Any] = None,
        cgroup_manager: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        max_containers: int = DEFAULT_MAX_CONTAINERS,
        default_seccomp_profile: str = DEFAULT_SECCOMP_PROFILE,
        default_hook_timeout: float = DEFAULT_HOOK_TIMEOUT,
    ) -> None:
        self._hook_executor = hook_executor or HookExecutor(default_timeout=default_hook_timeout)
        self._seccomp_engine = seccomp_engine or SeccompEngine()
        self._mount_processor = mount_processor or MountProcessor()
        self._namespace_manager = namespace_manager
        self._cgroup_manager = cgroup_manager
        self._event_bus = event_bus
        self._max_containers = max_containers
        self._default_seccomp_profile = default_seccomp_profile
        self._default_hook_timeout = default_hook_timeout

        self._containers: Dict[str, OCIContainer] = {}
        self._lock = threading.Lock()
        self._operation_log: List[Dict[str, Any]] = []

        self._creator = ContainerCreator(
            hook_executor=self._hook_executor,
            seccomp_engine=self._seccomp_engine,
            mount_processor=self._mount_processor,
            namespace_manager=self._namespace_manager,
            cgroup_manager=self._cgroup_manager,
            event_bus=self._event_bus,
        )

    @property
    def containers(self) -> Dict[str, OCIContainer]:
        """Return the container registry."""
        return dict(self._containers)

    @property
    def container_count(self) -> int:
        """Return the number of containers."""
        return len(self._containers)

    @property
    def max_containers(self) -> int:
        """Return the maximum container count."""
        return self._max_containers

    @property
    def hook_executor(self) -> HookExecutor:
        """Return the hook executor."""
        return self._hook_executor

    @property
    def seccomp_engine(self) -> SeccompEngine:
        """Return the seccomp engine."""
        return self._seccomp_engine

    @property
    def mount_processor(self) -> MountProcessor:
        """Return the mount processor."""
        return self._mount_processor

    @property
    def operation_log(self) -> List[Dict[str, Any]]:
        """Return the operation log."""
        return list(self._operation_log)

    def _log_operation(self, operation: str, container_id: str, **kwargs: Any) -> None:
        """Log a runtime operation."""
        entry = {
            "operation": operation,
            "container_id": container_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        self._operation_log.append(entry)

    def _emit(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def create(
        self,
        bundle_path: str,
        container_id: Optional[str] = None,
        config_dict: Optional[Dict[str, Any]] = None,
    ) -> OCIContainer:
        """Create a new container from an OCI bundle.

        Parses the configuration, sets up namespaces, configures
        cgroups, prepares the filesystem, and transitions the
        container to the CREATED state.

        Args:
            bundle_path: Path to the OCI bundle directory.
            container_id: Optional container ID (generated if not provided).
            config_dict: Optional pre-parsed config dictionary.

        Returns:
            The created OCIContainer.

        Raises:
            OCIContainerExistsError: If the container ID already exists.
            OCICreateError: If creation fails.
        """
        if container_id is None:
            container_id = str(uuid.uuid4())[:12]

        with self._lock:
            if container_id in self._containers:
                raise OCIContainerExistsError(container_id)
            if len(self._containers) >= self._max_containers:
                raise OCICreateError(
                    container_id,
                    f"maximum container count ({self._max_containers}) reached",
                )

        # Parse configuration
        if config_dict is not None:
            config = OCIConfig.from_dict(config_dict)
        else:
            config = OCIConfig()
            config.oci_version = OCI_SPEC_VERSION

        # Apply default seccomp profile if none specified
        if config.linux.seccomp is None:
            profile_name = self._default_seccomp_profile
            if profile_name in self._seccomp_engine.profiles:
                config.linux.seccomp = copy.deepcopy(
                    self._seccomp_engine.get_profile(profile_name)
                )

        # Create bundle
        bundle = OCIBundle(
            bundle_path=bundle_path,
            config=config,
            rootfs_path=f"{bundle_path}/{config.root.path}",
        )

        # Create container
        container = OCIContainer(container_id=container_id, bundle=bundle)

        # Register before creation so concurrent operations can find it
        with self._lock:
            self._containers[container_id] = container

        try:
            self._creator.create(container)
        except Exception:
            with self._lock:
                self._containers.pop(container_id, None)
            raise

        self._log_operation("create", container_id, state=container.state.value)
        return container

    def start(self, container_id: str) -> None:
        """Start a created container.

        Executes the startContainer hook and launches the container's
        entrypoint process.

        Args:
            container_id: ID of the container to start.

        Raises:
            OCIContainerNotFoundError: If the container is not found.
            OCIStartError: If the container cannot be started.
        """
        container = self._get_container(container_id)

        if container.state != OCIState.CREATED:
            raise OCIStartError(
                container_id,
                f"container is in state '{container.state.value}', expected 'created'",
            )

        try:
            # Execute startContainer hooks
            self._hook_executor.execute_hooks(
                container, HookType.START_CONTAINER, container.config.hooks,
            )

            # Transition to RUNNING
            container.transition_to(OCIState.RUNNING)

            # Execute poststart hooks (non-fatal)
            try:
                self._hook_executor.execute_hooks(
                    container, HookType.POSTSTART, container.config.hooks,
                )
            except (HookError, HookTimeoutError) as e:
                logger.warning(
                    "Poststart hook failed for container %s: %s (non-fatal)",
                    container_id, e,
                )

            self._emit(EventType.OCI_CONTAINER_STARTED, {
                "container_id": container_id,
                "pid": container.pid,
            })

        except OCIStateTransitionError as e:
            raise OCIStartError(container_id, str(e))
        except (HookError, HookTimeoutError) as e:
            raise OCIStartError(container_id, f"hook failure: {e}")
        except OCIStartError:
            raise
        except Exception as e:
            raise OCIStartError(container_id, f"unexpected error: {e}")

        self._log_operation("start", container_id, state=container.state.value)

    def kill(self, container_id: str, sig: str = "SIGTERM") -> None:
        """Send a signal to the container's init process.

        If the signal is SIGKILL or SIGTERM, the runtime transitions
        the container to the STOPPED state.

        Args:
            container_id: ID of the container.
            sig: Signal name (e.g., "SIGTERM", "SIGKILL").

        Raises:
            OCIContainerNotFoundError: If the container is not found.
            OCIKillError: If the signal cannot be delivered.
        """
        container = self._get_container(container_id)

        if container.state != OCIState.RUNNING:
            raise OCIKillError(
                container_id, sig,
                f"container is in state '{container.state.value}', expected 'running'",
            )

        # Validate signal
        sig_upper = sig.upper()
        if sig_upper not in SIGNAL_MAP and not sig_upper.isdigit():
            raise OCIKillError(container_id, sig, f"unknown signal '{sig}'")

        signal_num = SIGNAL_MAP.get(sig_upper, int(sig_upper) if sig_upper.isdigit() else 0)

        try:
            # Terminal signals transition to STOPPED
            if sig_upper in ("SIGKILL", "SIGTERM") or signal_num in (9, 15):
                container.set_exit_code(128 + signal_num)
                container.transition_to(OCIState.STOPPED)

            self._emit(EventType.OCI_CONTAINER_KILLED, {
                "container_id": container_id,
                "signal": sig_upper,
                "signal_num": signal_num,
            })

            if container.state == OCIState.STOPPED:
                self._emit(EventType.OCI_CONTAINER_STOPPED, {
                    "container_id": container_id,
                    "exit_code": container.exit_code,
                })

        except OCIStateTransitionError as e:
            raise OCIKillError(container_id, sig, str(e))

        self._log_operation("kill", container_id, signal=sig_upper, state=container.state.value)

    def delete(self, container_id: str) -> None:
        """Delete a stopped container.

        Cleans up namespaces, cgroups, mounts, and executes poststop
        hooks.  Only containers in the STOPPED state can be deleted.

        Args:
            container_id: ID of the container to delete.

        Raises:
            OCIContainerNotFoundError: If the container is not found.
            OCIDeleteError: If the container cannot be deleted.
        """
        container = self._get_container(container_id)

        if container.state != OCIState.STOPPED:
            raise OCIDeleteError(
                container_id,
                f"container is in state '{container.state.value}', expected 'stopped'",
            )

        try:
            # Execute poststop hooks
            try:
                self._hook_executor.execute_hooks(
                    container, HookType.POSTSTOP, container.config.hooks,
                )
            except (HookError, HookTimeoutError) as e:
                logger.warning(
                    "Poststop hook failed for container %s: %s (non-fatal)",
                    container_id, e,
                )

            # Clean up mount state
            self._mount_processor.cleanup_container(container_id)

            # Remove from registry
            with self._lock:
                self._containers.pop(container_id, None)

            self._emit(EventType.OCI_CONTAINER_DELETED, {
                "container_id": container_id,
            })

        except OCIDeleteError:
            raise
        except Exception as e:
            raise OCIDeleteError(container_id, f"unexpected error during cleanup: {e}")

        self._log_operation("delete", container_id)

    def state(self, container_id: str) -> OCIStateReport:
        """Query the state of a container.

        Args:
            container_id: ID of the container.

        Returns:
            OCIStateReport with the container's current state.

        Raises:
            OCIContainerNotFoundError: If the container is not found.
        """
        container = self._get_container(container_id)
        report = container.get_state_report()

        self._emit(EventType.OCI_STATE_QUERIED, {
            "container_id": container_id,
            "status": report.status,
        })

        self._log_operation("state", container_id, status=report.status)
        return report

    def list_containers(
        self,
        state_filter: Optional[OCIState] = None,
    ) -> List[OCIContainer]:
        """List all containers, optionally filtered by state.

        Args:
            state_filter: Optional state to filter by.

        Returns:
            List of matching containers.
        """
        with self._lock:
            containers = list(self._containers.values())

        if state_filter is not None:
            containers = [c for c in containers if c.state == state_filter]

        return containers

    def generate_default_spec(self) -> Dict[str, Any]:
        """Generate a default OCI runtime spec.

        Returns a config.json-compatible dictionary with sensible
        defaults for running a FizzBuzz container.

        Returns:
            Default OCI configuration dictionary.
        """
        config = OCIConfig()
        config.hostname = "fizzbuzz-container"
        config.process.args = ["python", "-m", "enterprise_fizzbuzz", "--range", "1", "100"]
        config.process.env = [
            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "TERM=xterm",
            "EFP_CONTAINERIZED=true",
        ]

        if self._default_seccomp_profile in self._seccomp_engine.profiles:
            config.linux.seccomp = copy.deepcopy(
                self._seccomp_engine.get_profile(self._default_seccomp_profile)
            )

        spec = config.to_dict()

        self._emit(EventType.OCI_SPEC_GENERATED, {
            "oci_version": OCI_SPEC_VERSION,
        })

        return spec

    def get_stats(self) -> Dict[str, Any]:
        """Return runtime statistics."""
        state_counts: Dict[str, int] = defaultdict(int)
        for container in self._containers.values():
            state_counts[container.state.value] += 1

        return {
            "oci_version": OCI_SPEC_VERSION,
            "total_containers": len(self._containers),
            "max_containers": self._max_containers,
            "state_counts": dict(state_counts),
            "operations_logged": len(self._operation_log),
            "default_seccomp_profile": self._default_seccomp_profile,
            "fizzns_available": self._namespace_manager is not None,
            "fizzcgroup_available": self._cgroup_manager is not None,
        }

    def _get_container(self, container_id: str) -> OCIContainer:
        """Look up a container by ID.

        Raises:
            OCIContainerNotFoundError: If not found.
        """
        with self._lock:
            container = self._containers.get(container_id)
        if container is None:
            raise OCIContainerNotFoundError(container_id)
        return container


# ============================================================
# OCIRuntimeMiddleware — Pipeline Integration
# ============================================================


class OCIRuntimeMiddleware(IMiddleware):
    """Middleware that runs FizzBuzz evaluations inside OCI containers.

    Each evaluation is processed within a properly configured OCI
    container.  The middleware manages the container lifecycle
    (create -> start -> kill -> delete) around each evaluation,
    injecting container metadata into the processing context.

    Priority: 108 (runs after FizzNS at 106 and FizzCgroup at 107).
    """

    def __init__(
        self,
        runtime: OCIRuntime,
        event_bus: Optional[Any] = None,
        enable_dashboard: bool = False,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> None:
        self._runtime = runtime
        self._event_bus = event_bus
        self._enable_dashboard = enable_dashboard
        self._dashboard_width = dashboard_width
        self._evaluation_count = 0
        self._containers_created = 0
        self._containers_completed = 0
        self._errors: List[str] = []
        self._lock = threading.Lock()
        self._dashboard: Optional[OCIDashboard] = None
        if enable_dashboard:
            self._dashboard = OCIDashboard(
                runtime=runtime,
                width=dashboard_width,
            )

    @property
    def runtime(self) -> OCIRuntime:
        """Return the OCI runtime."""
        return self._runtime

    @property
    def evaluation_count(self) -> int:
        """Return the total evaluation count."""
        return self._evaluation_count

    @property
    def containers_created(self) -> int:
        """Return the total containers created."""
        return self._containers_created

    @property
    def containers_completed(self) -> int:
        """Return the total containers completed."""
        return self._containers_completed

    @property
    def dashboard(self) -> Optional["OCIDashboard"]:
        """Return the dashboard instance."""
        return self._dashboard

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process an evaluation inside an OCI container.

        Creates a container for the evaluation, starts it, runs the
        evaluation via the next handler, and then kills and deletes
        the container.

        Args:
            context: The processing context.
            next_handler: The next middleware in the pipeline.

        Returns:
            The processed context with container metadata.
        """
        try:
            with self._lock:
                self._evaluation_count += 1

            number = context.number
            container_id = f"fizz-eval-{number}-{uuid.uuid4().hex[:8]}"

            # Create minimal config for evaluation
            config_dict = {
                "ociVersion": OCI_SPEC_VERSION,
                "root": {"path": "rootfs", "readonly": True},
                "process": {
                    "args": ["evaluate", str(number)],
                    "cwd": "/",
                    "env": [
                        f"FIZZBUZZ_NUMBER={number}",
                        "EFP_CONTAINERIZED=true",
                    ],
                },
                "hostname": f"fizz-eval-{number}",
            }

            # Create, start, evaluate, kill, delete
            container = self._runtime.create(
                bundle_path=f"/var/run/fizzbuzz/bundles/{container_id}",
                container_id=container_id,
                config_dict=config_dict,
            )

            with self._lock:
                self._containers_created += 1

            self._runtime.start(container_id)

            # Run the actual evaluation
            result = next_handler(context)

            # Inject container metadata
            if hasattr(result, "metadata") and isinstance(result.metadata, dict):
                result.metadata["oci_container_id"] = container_id
                result.metadata["oci_container_pid"] = container.pid
                result.metadata["oci_container_state"] = container.state.value

            # Kill and delete
            self._runtime.kill(container_id, "SIGTERM")
            self._runtime.delete(container_id)

            with self._lock:
                self._containers_completed += 1

            return result

        except (OCIRuntimeError, OCIContainerExistsError, OCIContainerNotFoundError) as e:
            with self._lock:
                self._errors.append(str(e))
            # Fall through to evaluation without container
            logger.warning(
                "OCI container creation failed for evaluation %d: %s. "
                "Falling back to non-containerized evaluation.",
                context.number, e,
            )
            return next_handler(context)
        except Exception as e:
            with self._lock:
                self._errors.append(str(e))
            return next_handler(context)

    def get_name(self) -> str:
        """Return the middleware name."""
        return "OCIRuntimeMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    def render_dashboard(self) -> str:
        """Render the OCI runtime dashboard."""
        if self._dashboard is not None:
            return self._dashboard.render()
        return self._render_basic_dashboard()

    def _render_basic_dashboard(self) -> str:
        """Render a basic dashboard without the full dashboard class."""
        w = self._dashboard_width
        lines = []
        border = "+" + "-" * (w - 2) + "+"
        lines.append(border)
        lines.append(f"| {'FIZZOCI: OCI-COMPLIANT CONTAINER RUNTIME':^{w-4}} |")
        lines.append(border)
        lines.append(f"| {'Evaluations:':<20} {self._evaluation_count:>{w-25}} |")
        lines.append(f"| {'Containers Created:':<20} {self._containers_created:>{w-25}} |")
        lines.append(f"| {'Containers Done:':<20} {self._containers_completed:>{w-25}} |")
        lines.append(f"| {'Active Containers:':<20} {self._runtime.container_count:>{w-25}} |")
        lines.append(f"| {'Errors:':<20} {len(self._errors):>{w-25}} |")
        lines.append(border)
        return "\n".join(lines)

    def render_container_list(self) -> str:
        """Render a list of all containers."""
        if self._dashboard is not None:
            return self._dashboard.render_container_list()
        return self._render_basic_container_list()

    def _render_basic_container_list(self) -> str:
        """Render a basic container list."""
        containers = self._runtime.list_containers()
        if not containers:
            return "  No containers.\n"
        lines = []
        lines.append(f"  {'ID':<16} {'STATE':<10} {'PID':<8} {'CREATED'}")
        lines.append(f"  {'─' * 14}   {'─' * 8}   {'─' * 6}   {'─' * 20}")
        for c in containers:
            lines.append(
                f"  {c.container_id:<16} {c.state.value:<10} {c.pid:<8} "
                f"{c.created_at.strftime('%Y-%m-%dT%H:%M:%S')}"
            )
        return "\n".join(lines)

    def render_container_state(self, container_id: str) -> str:
        """Render the state of a specific container."""
        try:
            report = self._runtime.state(container_id)
            lines = []
            lines.append(f"  Container: {report.id}")
            lines.append(f"  State:     {report.status}")
            lines.append(f"  PID:       {report.pid}")
            lines.append(f"  Bundle:    {report.bundle}")
            lines.append(f"  Created:   {report.created}")
            if report.annotations:
                lines.append(f"  Annotations:")
                for k, v in report.annotations.items():
                    lines.append(f"    {k}: {v}")
            return "\n".join(lines)
        except OCIContainerNotFoundError:
            return f"  Container '{container_id}' not found.\n"

    def render_default_spec(self) -> str:
        """Render the default OCI spec."""
        import json
        spec = self._runtime.generate_default_spec()
        return json.dumps(spec, indent=2)

    def render_lifecycle(self) -> str:
        """Render the lifecycle event log."""
        if self._dashboard is not None:
            return self._dashboard.render_lifecycle()
        ops = self._runtime.operation_log
        if not ops:
            return "  No lifecycle events recorded.\n"
        lines = []
        lines.append(f"  {'OPERATION':<10} {'CONTAINER':<16} {'TIMESTAMP'}")
        lines.append(f"  {'─' * 8}     {'─' * 14}   {'─' * 20}")
        for op in ops[-20:]:  # Last 20 operations
            lines.append(
                f"  {op['operation']:<10} {op['container_id']:<16} {op['timestamp']}"
            )
        return "\n".join(lines)


# ============================================================
# OCIDashboard — ASCII Dashboard
# ============================================================


class OCIDashboard:
    """ASCII dashboard for the OCI container runtime.

    Renders container state, lifecycle events, seccomp profiles,
    mount tables, and resource summaries in a formatted ASCII
    display suitable for terminal output.
    """

    def __init__(
        self,
        runtime: OCIRuntime,
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> None:
        self._runtime = runtime
        self._width = width

    @property
    def width(self) -> int:
        """Return the dashboard width."""
        return self._width

    def render(self) -> str:
        """Render the full OCI runtime dashboard."""
        try:
            w = self._width
            lines: List[str] = []
            border = "+" + "-" * (w - 2) + "+"
            thin_border = "+" + "." * (w - 2) + "+"

            # Header
            lines.append(border)
            lines.append(f"| {'FIZZOCI: OCI-COMPLIANT CONTAINER RUNTIME':^{w-4}} |")
            lines.append(f"| {'OCI Runtime Spec v' + OCI_SPEC_VERSION:^{w-4}} |")
            lines.append(border)

            # Runtime stats
            stats = self._runtime.get_stats()
            lines.append(f"| {'Runtime Statistics':^{w-4}} |")
            lines.append(thin_border)
            lines.append(f"| {'Total Containers:':<30} {stats['total_containers']:>{w-35}} |")
            lines.append(f"| {'Max Containers:':<30} {stats['max_containers']:>{w-35}} |")
            lines.append(f"| {'Operations Logged:':<30} {stats['operations_logged']:>{w-35}} |")
            lines.append(f"| {'FizzNS Available:':<30} {str(stats['fizzns_available']):>{w-35}} |")
            lines.append(f"| {'FizzCgroup Available:':<30} {str(stats['fizzcgroup_available']):>{w-35}} |")
            lines.append(f"| {'Seccomp Profile:':<30} {stats['default_seccomp_profile']:>{w-35}} |")

            # State counts
            state_counts = stats.get("state_counts", {})
            if state_counts:
                lines.append(thin_border)
                lines.append(f"| {'Container States':^{w-4}} |")
                lines.append(thin_border)
                for state_name, count in state_counts.items():
                    lines.append(f"| {'  ' + state_name + ':':<30} {count:>{w-35}} |")

            # Seccomp stats
            seccomp_stats = self._runtime.seccomp_engine.get_stats()
            lines.append(thin_border)
            lines.append(f"| {'Seccomp Engine':^{w-4}} |")
            lines.append(thin_border)
            lines.append(f"| {'  Evaluations:':<30} {seccomp_stats['evaluation_count']:>{w-35}} |")
            lines.append(f"| {'  Denied:':<30} {seccomp_stats['denied_count']:>{w-35}} |")
            lines.append(f"| {'  Profiles:':<30} {seccomp_stats['profiles_registered']:>{w-35}} |")

            # Container list (if any)
            containers = self._runtime.list_containers()
            if containers:
                lines.append(thin_border)
                lines.append(f"| {'Active Containers':^{w-4}} |")
                lines.append(thin_border)
                for c in containers[:10]:
                    cid = c.container_id[:12]
                    cstate = c.state.value
                    cpid = str(c.pid)
                    detail = f"  {cid} | {cstate:<10} | PID {cpid}"
                    lines.append(f"| {detail:<{w-4}} |")
                if len(containers) > 10:
                    lines.append(f"| {'  ... and ' + str(len(containers) - 10) + ' more':<{w-4}} |")

            lines.append(border)
            return "\n".join(lines)

        except Exception as e:
            raise OCIDashboardError(str(e))

    def render_container_list(self) -> str:
        """Render a detailed container list."""
        try:
            containers = self._runtime.list_containers()
            if not containers:
                return "  No containers registered.\n"

            lines = []
            lines.append(f"  {'ID':<16} {'STATE':<10} {'PID':<8} {'UPTIME':<12} {'CREATED'}")
            lines.append(f"  {'─' * 14}   {'─' * 8}   {'─' * 6}   {'─' * 10}   {'─' * 20}")
            for c in containers:
                uptime = f"{c.uptime_seconds():.1f}s"
                lines.append(
                    f"  {c.container_id:<16} {c.state.value:<10} {c.pid:<8} "
                    f"{uptime:<12} {c.created_at.strftime('%Y-%m-%dT%H:%M:%S')}"
                )
            lines.append(f"\n  Total: {len(containers)} containers")
            return "\n".join(lines)

        except Exception as e:
            raise OCIDashboardError(str(e))

    def render_lifecycle(self) -> str:
        """Render the lifecycle operation log."""
        try:
            ops = self._runtime.operation_log
            if not ops:
                return "  No lifecycle operations recorded.\n"

            lines = []
            lines.append(f"  {'OPERATION':<10} {'CONTAINER':<16} {'DETAILS':<20} {'TIMESTAMP'}")
            lines.append(f"  {'─' * 8}     {'─' * 14}   {'─' * 18}   {'─' * 20}")
            for op in ops[-30:]:
                details = ""
                if "state" in op:
                    details = f"state={op['state']}"
                elif "signal" in op:
                    details = f"signal={op['signal']}"
                elif "status" in op:
                    details = f"status={op['status']}"
                lines.append(
                    f"  {op['operation']:<10} {op['container_id']:<16} "
                    f"{details:<20} {op['timestamp']}"
                )
            lines.append(f"\n  Total operations: {len(ops)}")
            return "\n".join(lines)

        except Exception as e:
            raise OCIDashboardError(str(e))


# ============================================================
# Factory Function
# ============================================================


def create_fizzoci_subsystem(
    default_seccomp_profile: str = DEFAULT_SECCOMP_PROFILE,
    default_hook_timeout: float = DEFAULT_HOOK_TIMEOUT,
    max_containers: int = DEFAULT_MAX_CONTAINERS,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    namespace_manager: Optional[Any] = None,
    cgroup_manager: Optional[Any] = None,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzOCI subsystem.

    Factory function that instantiates the OCIRuntime and
    OCIRuntimeMiddleware, ready for integration into the
    FizzBuzz evaluation pipeline.

    Args:
        default_seccomp_profile: Name of the default seccomp profile.
        default_hook_timeout: Default hook timeout in seconds.
        max_containers: Maximum concurrent containers.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable post-execution dashboard.
        namespace_manager: Optional FizzNS NamespaceManager instance.
        cgroup_manager: Optional FizzCgroup CgroupManager instance.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (OCIRuntime, OCIRuntimeMiddleware).
    """
    runtime = OCIRuntime(
        namespace_manager=namespace_manager,
        cgroup_manager=cgroup_manager,
        event_bus=event_bus,
        max_containers=max_containers,
        default_seccomp_profile=default_seccomp_profile,
        default_hook_timeout=default_hook_timeout,
    )

    middleware = OCIRuntimeMiddleware(
        runtime=runtime,
        event_bus=event_bus,
        enable_dashboard=enable_dashboard,
        dashboard_width=dashboard_width,
    )

    return runtime, middleware
