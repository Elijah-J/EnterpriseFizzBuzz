"""
Enterprise FizzBuzz Platform - OCI Container Runtime Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class OCIRuntimeError(FizzBuzzError):
    """Base exception for all OCI container runtime errors.

    The OCI runtime specification (v1.0.2) defines a standard
    interface for low-level container runtimes. When this interface
    encounters a failure — whether during configuration parsing,
    container lifecycle management, or resource setup — it raises
    an OCIRuntimeError or one of its specialized subclasses. Every
    failure is traceable to a specific phase of container operations.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-OCI0"),
            context=kwargs.pop("context", {}),
        )


class OCIConfigError(OCIRuntimeError):
    """Raised when an OCI runtime configuration is invalid.

    The OCI config.json schema defines required fields, type
    constraints, and semantic rules. When a configuration fails
    validation — missing oci_version, invalid root path, or
    malformed process specification — this exception provides
    the details needed to correct the configuration.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"OCI configuration error: {reason}",
            error_code="EFP-OCI01",
            context={"reason": reason},
        )


class OCIConfigSchemaError(OCIRuntimeError):
    """Raised when an OCI config.json fails schema validation.

    Schema validation catches structural errors before the runtime
    attempts to interpret the configuration. Missing required fields,
    incorrect types, and constraint violations are reported with
    the specific JSON path that triggered the failure.
    """

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(
            f"OCI config schema error at '{field}': {reason}",
            error_code="EFP-OCI02",
            context={"field": field, "reason": reason},
        )


class OCIBundleError(OCIRuntimeError):
    """Raised when an OCI runtime bundle is invalid or inaccessible.

    An OCI bundle is a directory containing config.json and a rootfs
    directory. If either component is missing, unreadable, or
    structurally invalid, the runtime cannot create a container
    from the bundle.
    """

    def __init__(self, bundle_path: str, reason: str) -> None:
        super().__init__(
            f"OCI bundle error at '{bundle_path}': {reason}",
            error_code="EFP-OCI03",
            context={"bundle_path": bundle_path, "reason": reason},
        )


class OCIContainerError(OCIRuntimeError):
    """Raised when a container-level operation fails.

    Container errors encompass failures that occur after the
    container has been registered with the runtime but before
    a more specific lifecycle phase is identified.
    """

    def __init__(self, container_id: str, reason: str) -> None:
        super().__init__(
            f"OCI container error for '{container_id}': {reason}",
            error_code="EFP-OCI04",
            context={"container_id": container_id, "reason": reason},
        )


class OCIStateTransitionError(OCIRuntimeError):
    """Raised when a container state transition is invalid.

    The OCI lifecycle state machine permits only specific transitions:
    Creating->Created, Created->Running, Running->Stopped. Any
    attempt to perform an operation that would violate this state
    machine is rejected with this exception.
    """

    def __init__(self, container_id: str, current_state: str, target_state: str) -> None:
        super().__init__(
            f"Invalid state transition for container '{container_id}': "
            f"{current_state} -> {target_state}",
            error_code="EFP-OCI05",
            context={
                "container_id": container_id,
                "current_state": current_state,
                "target_state": target_state,
            },
        )


class OCIContainerNotFoundError(OCIRuntimeError):
    """Raised when a container ID is not found in the runtime registry.

    The runtime maintains a registry of all containers it manages.
    Operations on a container ID that does not exist in the registry
    are rejected with this exception.
    """

    def __init__(self, container_id: str) -> None:
        super().__init__(
            f"Container '{container_id}' not found in the runtime registry",
            error_code="EFP-OCI06",
            context={"container_id": container_id},
        )


class OCIContainerExistsError(OCIRuntimeError):
    """Raised when attempting to create a container with a duplicate ID.

    Container IDs must be unique within the runtime. Attempting to
    create a container with an ID that is already registered
    results in this exception.
    """

    def __init__(self, container_id: str) -> None:
        super().__init__(
            f"Container '{container_id}' already exists in the runtime registry",
            error_code="EFP-OCI07",
            context={"container_id": container_id},
        )


class OCICreateError(OCIRuntimeError):
    """Raised when the container creation operation fails.

    Container creation involves parsing configuration, setting up
    namespaces, configuring cgroups, preparing the root filesystem,
    processing mounts, and executing lifecycle hooks. Failure at
    any of these steps triggers this exception.
    """

    def __init__(self, container_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to create container '{container_id}': {reason}",
            error_code="EFP-OCI08",
            context={"container_id": container_id, "reason": reason},
        )


class OCIStartError(OCIRuntimeError):
    """Raised when the container start operation fails.

    Starting a container involves executing the startContainer hook
    and launching the entrypoint process with the configured user,
    capabilities, environment, and resource limits. Failure at any
    step triggers this exception.
    """

    def __init__(self, container_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to start container '{container_id}': {reason}",
            error_code="EFP-OCI09",
            context={"container_id": container_id, "reason": reason},
        )


class OCIKillError(OCIRuntimeError):
    """Raised when the container kill operation fails.

    Killing a container sends a signal to the container's init
    process. If signal delivery fails or the process cannot be
    located, this exception is raised.
    """

    def __init__(self, container_id: str, signal: str, reason: str) -> None:
        super().__init__(
            f"Failed to send signal {signal} to container '{container_id}': {reason}",
            error_code="EFP-OCI10",
            context={"container_id": container_id, "signal": signal, "reason": reason},
        )


class OCIDeleteError(OCIRuntimeError):
    """Raised when the container delete operation fails.

    Deleting a container cleans up namespaces, removes cgroup nodes,
    unmounts filesystems, and executes poststop hooks. If cleanup
    fails or the container is not in the STOPPED state, this
    exception is raised.
    """

    def __init__(self, container_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to delete container '{container_id}': {reason}",
            error_code="EFP-OCI11",
            context={"container_id": container_id, "reason": reason},
        )


class SeccompError(OCIRuntimeError):
    """Raised when a seccomp profile operation fails.

    Seccomp (secure computing) provides syscall filtering for
    container security. Profile validation, rule compilation,
    and syscall evaluation failures are covered by this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Seccomp error: {reason}",
            error_code="EFP-OCI12",
            context={"reason": reason},
        )


class SeccompRuleError(OCIRuntimeError):
    """Raised when a seccomp rule is malformed or invalid.

    Individual seccomp rules specify syscall names, argument
    conditions, and actions. If a rule references an unknown
    syscall, specifies invalid argument indices, or uses
    unsupported operators, this exception is raised.
    """

    def __init__(self, syscall: str, reason: str) -> None:
        super().__init__(
            f"Seccomp rule error for syscall '{syscall}': {reason}",
            error_code="EFP-OCI13",
            context={"syscall": syscall, "reason": reason},
        )


class HookError(OCIRuntimeError):
    """Raised when a container lifecycle hook fails.

    OCI lifecycle hooks (prestart, createRuntime, createContainer,
    startContainer, poststart, poststop) are executable callbacks
    invoked at specific points in the container lifecycle. If a
    hook returns a non-zero exit code, this exception is raised.
    """

    def __init__(self, hook_type: str, reason: str) -> None:
        super().__init__(
            f"Hook '{hook_type}' failed: {reason}",
            error_code="EFP-OCI14",
            context={"hook_type": hook_type, "reason": reason},
        )


class HookTimeoutError(OCIRuntimeError):
    """Raised when a container lifecycle hook exceeds its timeout.

    Each hook may specify a timeout in seconds. If the hook does
    not complete within the timeout, the runtime terminates the
    hook process and raises this exception.
    """

    def __init__(self, hook_type: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Hook '{hook_type}' timed out after {timeout_seconds:.1f}s",
            error_code="EFP-OCI15",
            context={"hook_type": hook_type, "timeout_seconds": timeout_seconds},
        )


class RlimitError(OCIRuntimeError):
    """Raised when a resource limit configuration is invalid.

    POSIX rlimits (RLIMIT_NOFILE, RLIMIT_NPROC, RLIMIT_AS, etc.)
    constrain per-process resource usage. If a limit type is
    unrecognized or the soft limit exceeds the hard limit, this
    exception is raised.
    """

    def __init__(self, limit_type: str, reason: str) -> None:
        super().__init__(
            f"Rlimit error for '{limit_type}': {reason}",
            error_code="EFP-OCI16",
            context={"limit_type": limit_type, "reason": reason},
        )


class MountError(OCIRuntimeError):
    """Raised when a container mount operation fails.

    Container mounts bind host paths, tmpfs volumes, or device
    nodes into the container filesystem. If a mount source does
    not exist, the destination path is invalid, or mount options
    are unsupported, this exception is raised.
    """

    def __init__(self, destination: str, reason: str) -> None:
        super().__init__(
            f"Mount error at '{destination}': {reason}",
            error_code="EFP-OCI17",
            context={"destination": destination, "reason": reason},
        )


class OCIRuntimeMiddlewareError(OCIRuntimeError):
    """Raised when the OCI runtime middleware fails to process an evaluation.

    The middleware intercepts each FizzBuzz evaluation to ensure it
    runs inside a properly configured OCI container. If container
    creation, lifecycle management, or resource setup fails during
    middleware processing, this exception is raised.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"OCI runtime middleware error at evaluation {evaluation_number}: {reason}",
            error_code="EFP-OCI18",
            context={"evaluation_number": evaluation_number, "reason": reason},
        )
        self.evaluation_number = evaluation_number


class OCIDashboardError(OCIRuntimeError):
    """Raised when the OCI runtime dashboard rendering fails.

    The dashboard renders container state, lifecycle events,
    seccomp profiles, mount tables, and resource summaries in
    ASCII format. Data retrieval or rendering failures trigger
    this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"OCI dashboard rendering failed: {reason}",
            error_code="EFP-OCI19",
            context={"reason": reason},
        )

