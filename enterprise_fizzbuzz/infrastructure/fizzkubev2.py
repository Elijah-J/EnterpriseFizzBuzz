"""
Enterprise FizzBuzz Platform - FizzKubeV2: Container-Aware Orchestrator Upgrade

Upgrades the FizzKube container orchestrator from a scheduling simulator
into a complete container orchestrator by integrating with the Round 16
container runtime stack via the Container Runtime Interface (CRI).

FizzKube was introduced in Round 5.  It implements the Kubernetes control
plane faithfully: an API server, an etcd-backed state store, a scheduler
with predicate/priority scoring, a controller manager with reconciliation
loops for Deployments, ReplicaSets, and HPAs, and a kubelet that manages
pod lifecycle.  FizzKube schedules workloads, enforces replica counts,
scales horizontally, and manages rolling updates.  Its kubelet does not
call CRI.  It does not pull images.  It does not run init containers.  It
does not inject sidecars.  It does not execute readiness or liveness
probes.  It does not manage volumes.  When FizzKube "creates a pod," the
kubelet instantiates a Python dataclass and calls its entry point.  There
is no image pull.  There is no container creation.  There is no namespace
isolation.  There is no cgroup resource enforcement.

Round 16 built the entire container runtime stack beneath FizzKube.
FizzContainerd exposes a CRI service with RunPodSandbox, CreateContainer,
StartContainer, PullImage, and all other CRI operations.  The CRI service
is complete and operational.  FizzKube's kubelet does not call it.

FizzKubeV2 connects FizzKube to FizzContainerd.  The CRI-integrated
KubeletV2 pulls images via ImagePuller, creates pod sandboxes, runs init
containers in sequence via InitContainerRunner, injects sidecar
containers via SidecarInjector, starts application containers, executes
readiness/liveness/startup probes via ProbeRunner, manages container
restarts with exponential backoff, handles graceful pod termination, and
provisions volumes via VolumeManager.

Architecture reference: Kubernetes kubelet v1.29
  (https://kubernetes.io/docs/reference/command-line-tools-reference/kubelet/)
"""

from __future__ import annotations

import copy
import hashlib
import logging
import math
import random
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzkubev2")


# ============================================================
# Constants
# ============================================================

KUBEV2_VERSION = "2.0.0"
"""KubeV2 API version."""

DEFAULT_IMAGE_PULL_POLICY = "IfNotPresent"
"""Default image pull policy for container images."""

DEFAULT_TERMINATION_GRACE_PERIOD = 30.0
"""Seconds to wait after SIGTERM before SIGKILL."""

DEFAULT_RESTART_BACKOFF_BASE = 10.0
"""Base restart backoff in seconds."""

DEFAULT_RESTART_BACKOFF_CAP = 300.0
"""Maximum restart backoff (5 minutes)."""

DEFAULT_RESTART_BACKOFF_MULTIPLIER = 2.0
"""Backoff multiplier per restart."""

DEFAULT_PROBE_INITIAL_DELAY = 0.0
"""Probe initial delay seconds."""

DEFAULT_PROBE_PERIOD = 10.0
"""Probe period seconds."""

DEFAULT_PROBE_TIMEOUT = 1.0
"""Probe timeout seconds."""

DEFAULT_PROBE_SUCCESS_THRESHOLD = 1
"""Consecutive successes for probe pass."""

DEFAULT_PROBE_FAILURE_THRESHOLD = 3
"""Consecutive failures for probe fail."""

DEFAULT_MAX_INIT_CONTAINER_RETRIES = 3
"""Max init container restart attempts."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIDDLEWARE_PRIORITY = 116
"""Middleware pipeline priority for FizzKubeV2."""


# ============================================================
# Event Type Constants
# ============================================================

KUBEV2_POD_CREATED = "kubev2.pod.created"
"""Emitted when a new PodV2 is created."""

KUBEV2_POD_SCHEDULED = "kubev2.pod.scheduled"
"""Emitted when a PodV2 is assigned to a node."""

KUBEV2_POD_RUNNING = "kubev2.pod.running"
"""Emitted when a PodV2 enters the RUNNING phase."""

KUBEV2_POD_SUCCEEDED = "kubev2.pod.succeeded"
"""Emitted when a PodV2 completes successfully."""

KUBEV2_POD_FAILED = "kubev2.pod.failed"
"""Emitted when a PodV2 fails."""

KUBEV2_POD_TERMINATING = "kubev2.pod.terminating"
"""Emitted when a PodV2 begins graceful termination."""

KUBEV2_IMAGE_PULL_STARTED = "kubev2.image.pull.started"
"""Emitted when an image pull begins."""

KUBEV2_IMAGE_PULLED = "kubev2.image.pulled"
"""Emitted when an image pull completes successfully."""

KUBEV2_IMAGE_PULL_FAILED = "kubev2.image.pull.failed"
"""Emitted when an image pull fails."""

KUBEV2_IMAGE_PULL_STALLED = "kubev2.image.pull.stalled"
"""Emitted when an image pull stalls (no progress)."""

KUBEV2_INIT_STARTED = "kubev2.init.started"
"""Emitted when an init container begins execution."""

KUBEV2_INIT_COMPLETED = "kubev2.init.completed"
"""Emitted when an init container completes successfully."""

KUBEV2_INIT_FAILED = "kubev2.init.failed"
"""Emitted when an init container fails."""

KUBEV2_SIDECAR_INJECTED = "kubev2.sidecar.injected"
"""Emitted when sidecars are injected into a pod."""

KUBEV2_SIDECAR_SKIPPED = "kubev2.sidecar.skipped"
"""Emitted when sidecar injection is skipped for a pod."""

KUBEV2_PROBE_EXECUTED = "kubev2.probe.executed"
"""Emitted when a health probe is executed."""

KUBEV2_PROBE_SUCCEEDED = "kubev2.probe.succeeded"
"""Emitted when a health probe succeeds."""

KUBEV2_PROBE_FAILED = "kubev2.probe.failed"
"""Emitted when a health probe fails."""

KUBEV2_READINESS_CHANGED = "kubev2.readiness.changed"
"""Emitted when a container's readiness state changes."""

KUBEV2_LIVENESS_FAILED = "kubev2.liveness.failed"
"""Emitted when a liveness probe failure triggers container restart."""

KUBEV2_VOLUME_PROVISIONED = "kubev2.volume.provisioned"
"""Emitted when a volume is provisioned for a pod."""

KUBEV2_VOLUME_MOUNTED = "kubev2.volume.mounted"
"""Emitted when a volume is mounted into a container."""

KUBEV2_VOLUME_CLEANED = "kubev2.volume.cleaned"
"""Emitted when a volume is cleaned up after pod termination."""

KUBEV2_PVC_BOUND = "kubev2.pvc.bound"
"""Emitted when a PersistentVolumeClaim is bound to a volume."""

KUBEV2_CONTAINER_STARTED = "kubev2.container.started"
"""Emitted when a container is started via CRI."""

KUBEV2_CONTAINER_RESTARTED = "kubev2.container.restarted"
"""Emitted when a container is restarted after failure."""

KUBEV2_DASHBOARD_RENDERED = "kubev2.dashboard.rendered"
"""Emitted when the KubeV2 dashboard is rendered."""


# ============================================================
# Exceptions
# ============================================================


class KubeV2Error(Exception):
    """Base exception for all FizzKubeV2 errors.

    Every failure mode in the CRI-integrated orchestrator traces back
    to this class.  Error codes follow the EFP-KV2xx convention.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-KV200",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.context = context or {}


class KubeletV2Error(KubeV2Error):
    """Raised when the CRI-integrated kubelet encounters a lifecycle failure.

    The kubelet coordinates image pulls, sandbox creation, init container
    execution, sidecar injection, probe registration, and volume provisioning.
    Failures at any stage of this pipeline trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"KubeletV2 error: {reason}",
            error_code="EFP-KV201",
            context={"reason": reason},
        )


class KV2ImagePullError(KubeV2Error):
    """Raised when an image pull operation fails.

    Image pulls can fail due to registry unavailability, authentication
    errors, network timeouts, or content integrity failures.
    """

    def __init__(self, image: str, policy: str, reason: str) -> None:
        super().__init__(
            f"Failed to pull image '{image}' with policy {policy}: {reason}",
            error_code="EFP-KV202",
            context={"image": image, "policy": policy, "reason": reason},
        )


class ImagePullBackOffError(KubeV2Error):
    """Raised when an image pull enters exponential backoff.

    After repeated pull failures, the kubelet enters a backoff state
    to prevent overwhelming the registry with retry requests.
    """

    def __init__(self, image: str, attempt: int, backoff_seconds: float) -> None:
        super().__init__(
            f"Image '{image}' in pull backoff (attempt {attempt}, "
            f"next retry in {backoff_seconds:.1f}s)",
            error_code="EFP-KV203",
            context={
                "image": image,
                "attempt": attempt,
                "backoff_seconds": backoff_seconds,
            },
        )


class ImageNotPresentError(KubeV2Error):
    """Raised when an image is not present locally and the pull policy is Never.

    Air-gapped deployments require all images to be pre-provisioned.
    This exception indicates an image was referenced that has not been
    loaded into the local content store.
    """

    def __init__(self, image: str) -> None:
        super().__init__(
            f"Image '{image}' not present locally and pull policy is Never",
            error_code="EFP-KV204",
            context={"image": image},
        )


class PullSecretError(KubeV2Error):
    """Raised when pull secret retrieval or authentication fails.

    Private registries require credentials to be provided via pull secrets.
    This exception covers missing secrets, invalid credentials, and
    registry authentication failures.
    """

    def __init__(self, secret_name: str, registry: str, reason: str) -> None:
        super().__init__(
            f"Pull secret '{secret_name}' failed for registry '{registry}': {reason}",
            error_code="EFP-KV205",
            context={
                "secret_name": secret_name,
                "registry": registry,
                "reason": reason,
            },
        )


class InitContainerFailedError(KubeV2Error):
    """Raised when an init container exits with a non-zero code.

    Init containers must complete successfully before application
    containers can start.  A non-zero exit code halts the pod
    startup sequence.
    """

    def __init__(self, init_name: str, exit_code: int, pod_name: str) -> None:
        super().__init__(
            f"Init container '{init_name}' in pod '{pod_name}' "
            f"failed with exit code {exit_code}",
            error_code="EFP-KV206",
            context={
                "init_name": init_name,
                "exit_code": exit_code,
                "pod_name": pod_name,
            },
        )


class InitContainerTimeoutError(KubeV2Error):
    """Raised when an init container exceeds its execution timeout.

    Init containers have a configurable timeout to prevent indefinite
    blocking of the pod startup sequence.
    """

    def __init__(self, init_name: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Init container '{init_name}' timed out after {timeout_seconds:.1f}s",
            error_code="EFP-KV207",
            context={
                "init_name": init_name,
                "timeout_seconds": timeout_seconds,
            },
        )


class SidecarInjectionError(KubeV2Error):
    """Raised when sidecar injection fails for a pod.

    Sidecar injection involves modifying the pod spec to add additional
    containers, volumes, and init containers.  Failures can occur due
    to conflicting container names, resource quota violations, or
    invalid injection policy configurations.
    """

    def __init__(self, pod_name: str, sidecar_name: str, reason: str) -> None:
        super().__init__(
            f"Sidecar '{sidecar_name}' injection failed for pod '{pod_name}': {reason}",
            error_code="EFP-KV208",
            context={
                "pod_name": pod_name,
                "sidecar_name": sidecar_name,
                "reason": reason,
            },
        )


class SidecarLifecycleError(KubeV2Error):
    """Raised when a sidecar container lifecycle ordering is violated.

    Sidecars must reach their expected state before the main container
    can start.  This exception indicates a state machine violation.
    """

    def __init__(
        self, sidecar_name: str, expected_state: str, actual_state: str
    ) -> None:
        super().__init__(
            f"Sidecar '{sidecar_name}' expected state '{expected_state}' "
            f"but found '{actual_state}'",
            error_code="EFP-KV209",
            context={
                "sidecar_name": sidecar_name,
                "expected_state": expected_state,
                "actual_state": actual_state,
            },
        )


class ProbeFailedError(KubeV2Error):
    """Raised when a health probe fails.

    Generic probe failure covering HTTP, TCP, and exec probe types
    across readiness, liveness, and startup categories.
    """

    def __init__(
        self,
        container_id: str,
        probe_category: str,
        probe_type: str,
        reason: str,
    ) -> None:
        super().__init__(
            f"Probe {probe_category}/{probe_type} failed for container "
            f"'{container_id}': {reason}",
            error_code="EFP-KV210",
            context={
                "container_id": container_id,
                "probe_category": probe_category,
                "probe_type": probe_type,
                "reason": reason,
            },
        )


class ProbeTimeoutError(KubeV2Error):
    """Raised when a probe execution exceeds its timeout.

    Probes have a configurable timeout to prevent indefinite blocking
    of the health check cycle.
    """

    def __init__(
        self, container_id: str, probe_category: str, timeout_seconds: float
    ) -> None:
        super().__init__(
            f"Probe {probe_category} timed out for container '{container_id}' "
            f"after {timeout_seconds:.1f}s",
            error_code="EFP-KV211",
            context={
                "container_id": container_id,
                "probe_category": probe_category,
                "timeout_seconds": timeout_seconds,
            },
        )


class ReadinessProbeFailedError(ProbeFailedError):
    """Raised when the readiness probe threshold is breached.

    Readiness failures remove the container from service endpoints
    but do not trigger a restart.
    """

    def __init__(
        self, container_id: str, consecutive_failures: int, threshold: int
    ) -> None:
        super().__init__(
            container_id=container_id,
            probe_category="readiness",
            probe_type="threshold",
            reason=(
                f"Consecutive failures ({consecutive_failures}) "
                f"reached threshold ({threshold})"
            ),
        )
        self.error_code = "EFP-KV212"
        self.context["consecutive_failures"] = consecutive_failures
        self.context["threshold"] = threshold


class LivenessProbeFailedError(ProbeFailedError):
    """Raised when the liveness probe threshold is breached.

    Liveness failures cause the container to be killed and restarted
    according to the pod's restart policy.
    """

    def __init__(
        self, container_id: str, consecutive_failures: int, threshold: int
    ) -> None:
        super().__init__(
            container_id=container_id,
            probe_category="liveness",
            probe_type="threshold",
            reason=(
                f"Consecutive failures ({consecutive_failures}) "
                f"reached threshold ({threshold}), container will restart"
            ),
        )
        self.error_code = "EFP-KV213"
        self.context["consecutive_failures"] = consecutive_failures
        self.context["threshold"] = threshold


class StartupProbeFailedError(ProbeFailedError):
    """Raised when the startup probe never succeeds within the allowed time.

    Startup probe failure indicates the container did not become ready
    within its allotted startup period.
    """

    def __init__(self, container_id: str, elapsed_seconds: float) -> None:
        super().__init__(
            container_id=container_id,
            probe_category="startup",
            probe_type="timeout",
            reason=f"Startup probe never succeeded after {elapsed_seconds:.1f}s",
        )
        self.error_code = "EFP-KV214"
        self.context["elapsed_seconds"] = elapsed_seconds


class VolumeProvisionError(KubeV2Error):
    """Raised when volume provisioning fails.

    Volume provisioning allocates storage for emptyDir, PVC, configMap,
    and secret volume types.  Failures include storage exhaustion,
    invalid volume configurations, and backend errors.
    """

    def __init__(self, volume_name: str, volume_type: str, reason: str) -> None:
        super().__init__(
            f"Volume '{volume_name}' ({volume_type}) provisioning failed: {reason}",
            error_code="EFP-KV215",
            context={
                "volume_name": volume_name,
                "volume_type": volume_type,
                "reason": reason,
            },
        )


class VolumeMountError(KubeV2Error):
    """Raised when a volume mount into a container fails.

    Volume mounts can fail due to conflicting mount paths, read-only
    filesystem violations, or invalid sub-path references.
    """

    def __init__(
        self,
        volume_name: str,
        container_id: str,
        mount_path: str,
        reason: str,
    ) -> None:
        super().__init__(
            f"Volume '{volume_name}' mount at '{mount_path}' in container "
            f"'{container_id}' failed: {reason}",
            error_code="EFP-KV216",
            context={
                "volume_name": volume_name,
                "container_id": container_id,
                "mount_path": mount_path,
                "reason": reason,
            },
        )


class PVCNotFoundError(KubeV2Error):
    """Raised when a referenced PersistentVolumeClaim does not exist.

    Pods referencing PVCs that have not been created will fail to start
    because the volume cannot be provisioned without a bound claim.
    """

    def __init__(self, claim_name: str) -> None:
        super().__init__(
            f"PersistentVolumeClaim '{claim_name}' not found",
            error_code="EFP-KV217",
            context={"claim_name": claim_name},
        )


class ContainerRestartBackoffError(KubeV2Error):
    """Raised when a container is in restart backoff.

    After repeated failures, the kubelet applies exponential backoff
    before allowing the next restart attempt.
    """

    def __init__(
        self, container_id: str, restart_count: int, backoff_seconds: float
    ) -> None:
        super().__init__(
            f"Container '{container_id}' in restart backoff "
            f"(restarts={restart_count}, next in {backoff_seconds:.1f}s)",
            error_code="EFP-KV218",
            context={
                "container_id": container_id,
                "restart_count": restart_count,
                "backoff_seconds": backoff_seconds,
            },
        )


class PodTerminationError(KubeV2Error):
    """Raised when graceful pod termination fails.

    Pod termination involves sending SIGTERM to all containers, waiting
    the grace period, then sending SIGKILL.  This exception is raised
    when the termination sequence encounters errors that prevent clean
    shutdown.
    """

    def __init__(self, pod_name: str, reason: str) -> None:
        super().__init__(
            f"Pod '{pod_name}' termination failed: {reason}",
            error_code="EFP-KV219",
            context={"pod_name": pod_name, "reason": reason},
        )


class KubeV2MiddlewareError(KubeV2Error):
    """Raised when the FizzKubeV2 middleware fails to process an evaluation.

    The middleware wraps each evaluation in a full pod lifecycle.  Errors
    during any phase (image pull, init, sidecar, probe, volume, evaluation)
    are wrapped in this exception after best-effort cleanup.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"FizzKubeV2 middleware error at evaluation {evaluation_number}: {reason}",
            error_code="EFP-KV220",
            context={"evaluation_number": evaluation_number, "reason": reason},
        )
        self.evaluation_number = evaluation_number


# ============================================================
# Enums
# ============================================================


class ImagePullPolicy(Enum):
    """Policy controlling when images are pulled from the registry.

    ALWAYS: Pull the image on every container creation, regardless of
        local cache state.  Used for mutable tags such as 'latest',
        where the registry content may have changed since the last pull.
    IF_NOT_PRESENT: Pull only if the image is not already cached locally.
        The default policy for immutable tags (semantic versions, digest
        references).  Minimizes registry traffic while ensuring images
        are available.
    NEVER: Never pull the image.  Fail with ImageNotPresentError if the
        image is not already present locally.  Used in air-gapped
        deployments where images are pre-provisioned.
    """

    ALWAYS = "Always"
    IF_NOT_PRESENT = "IfNotPresent"
    NEVER = "Never"


class ProbeType(Enum):
    """Type of health probe to execute against a container.

    HTTP_GET: Send an HTTP GET request to a specified path and port.
        The probe succeeds if the response status code is 2xx.
    TCP_SOCKET: Attempt a TCP connection to a specified port.  The
        probe succeeds if the connection is established.
    EXEC: Execute a command inside the container via CRI exec.  The
        probe succeeds if the command exits with code 0.
    """

    HTTP_GET = "httpGet"
    TCP_SOCKET = "tcpSocket"
    EXEC = "exec"


class ProbeResult(Enum):
    """Result of a single probe execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class VolumeType(Enum):
    """Type of volume that can be mounted into a container.

    EMPTY_DIR: Ephemeral volume backed by a temporary FizzOverlay layer.
        Created when the pod starts, deleted when the pod terminates.
        Shared between containers in the same pod.
    PERSISTENT_VOLUME_CLAIM: Persistent volume backed by a named
        FizzOverlay persistent layer.  Survives pod restarts.
    CONFIG_MAP: Volume populated from a ConfigMap resource, projected
        as files at the mount path.
    SECRET: Volume populated from a Secret resource, projected as files
        in a tmpfs mount that is never written to overlay layers.
    """

    EMPTY_DIR = "emptyDir"
    PERSISTENT_VOLUME_CLAIM = "persistentVolumeClaim"
    CONFIG_MAP = "configMap"
    SECRET = "secret"


class ContainerRestartPolicy(Enum):
    """Restart policy applied when a container exits unexpectedly.

    ALWAYS: Restart the container regardless of exit code.  The default
        for long-running service containers and sidecars.
    ON_FAILURE: Restart only if the container exits with a non-zero
        code.  Used for batch jobs that should not retry on success.
    NEVER: Never restart.  Used for one-shot containers (init
        containers, debug containers) and pods that must not be
        rescheduled.
    """

    ALWAYS = "Always"
    ON_FAILURE = "OnFailure"
    NEVER = "Never"


class PodPhaseV2(Enum):
    """Extended lifecycle phases for a FizzKubeV2 pod.

    Extends the original PodPhase with CRI-aware intermediate states.
    IMAGE_PULLING indicates the kubelet is pulling container images.
    INIT_RUNNING indicates init containers are executing sequentially.
    CONTAINER_CREATING indicates application containers are being
    created through CRI.  TERMINATING indicates a graceful shutdown
    is in progress.
    """

    PENDING = auto()
    IMAGE_PULLING = auto()
    INIT_RUNNING = auto()
    CONTAINER_CREATING = auto()
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    TERMINATING = auto()
    INIT_FAILURE = auto()
    IMAGE_PULL_BACKOFF = auto()


class SidecarPolicy(Enum):
    """Policy for sidecar injection decisions.

    INJECT: Inject sidecars into the pod.
    SKIP: Do not inject sidecars (pod opted out via annotation).
    REQUIRED: Sidecars are mandatory; pod creation fails if
        injection cannot be completed.
    """

    INJECT = "inject"
    SKIP = "skip"
    REQUIRED = "required"


class ProbeCategory(Enum):
    """Category of health probe.

    READINESS: Determines whether a container is ready to receive
        traffic.  Failure removes the container from service endpoints
        but does not restart it.
    LIVENESS: Determines whether a container is still alive.  Failure
        causes the container to be killed and restarted.
    STARTUP: Protects slow-starting containers from premature liveness
        failures.  Once the startup probe succeeds, it is not executed
        again; the liveness probe takes over.
    """

    READINESS = "readiness"
    LIVENESS = "liveness"
    STARTUP = "startup"


# ============================================================
# Data Classes
# ============================================================


@dataclass
class PullProgress:
    """Tracks image pull progress for status reporting.

    Attributes:
        image: Image reference being pulled.
        bytes_downloaded: Bytes downloaded so far.
        bytes_total: Total image size in bytes.
        started_at: When the pull started.
        completed_at: When the pull completed (None if in progress).
        stalled: Whether the pull has stalled (no progress for 30s).
        error: Error message if the pull failed.
    """

    image: str
    bytes_downloaded: int = 0
    bytes_total: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    stalled: bool = False
    error: str = ""

    @property
    def percent(self) -> float:
        """Return download progress as a percentage."""
        if self.bytes_total == 0:
            return 0.0
        return (self.bytes_downloaded / self.bytes_total) * 100.0


@dataclass
class PullSecret:
    """Credentials for authenticated image pulls.

    Attributes:
        name: Secret name (reference into the secrets vault).
        registry: Registry hostname these credentials apply to.
        username: Registry username.
        token: Registry auth token.
    """

    name: str
    registry: str = ""
    username: str = ""
    token: str = ""


@dataclass
class InitContainerSpec:
    """Specification for an init container within a pod.

    Attributes:
        name: Init container name.
        image: Image reference.
        command: Entrypoint command override.
        args: Entrypoint arguments.
        env: Environment variables.
        volume_mounts: Volumes to mount.
        timeout_seconds: Maximum execution time before timeout.
    """

    name: str
    image: str = "fizzbuzz-base:latest"
    command: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    volume_mounts: List[str] = field(default_factory=list)
    timeout_seconds: float = 60.0


@dataclass
class InitContainerResult:
    """Result of an init container execution.

    Attributes:
        name: Init container name.
        exit_code: Exit code (0 = success).
        started_at: When execution started.
        completed_at: When execution completed.
        duration_ms: Execution duration in milliseconds.
        container_id: CRI container ID.
        logs: Captured stdout/stderr output.
        error: Error message if failed.
    """

    name: str
    exit_code: int = -1
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    container_id: str = ""
    logs: str = ""
    error: str = ""

    @property
    def succeeded(self) -> bool:
        """Return True if the init container exited successfully."""
        return self.exit_code == 0


@dataclass
class VolumeMount:
    """A volume mount specification.

    Attributes:
        name: Volume name (references a volume in the pod spec).
        mount_path: Path inside the container to mount the volume.
        read_only: Whether the mount is read-only.
        sub_path: Subdirectory within the volume to mount.
    """

    name: str
    mount_path: str = "/data"
    read_only: bool = False
    sub_path: str = ""


@dataclass
class ProbeConfig:
    """Configuration for a container health probe.

    Attributes:
        probe_type: Type of probe (HTTP, TCP, exec).
        category: Probe category (readiness, liveness, startup).
        path: HTTP path for HTTP_GET probes.
        port: Port for HTTP_GET and TCP_SOCKET probes.
        command: Command for EXEC probes.
        initial_delay_seconds: Delay before first probe execution.
        period_seconds: Interval between probe executions.
        timeout_seconds: Probe execution timeout.
        success_threshold: Consecutive successes required to pass.
        failure_threshold: Consecutive failures required to fail.
    """

    probe_type: ProbeType = ProbeType.EXEC
    category: ProbeCategory = ProbeCategory.READINESS
    path: str = "/healthz"
    port: int = 8080
    command: List[str] = field(default_factory=lambda: ["fizzbuzz-health"])
    initial_delay_seconds: float = DEFAULT_PROBE_INITIAL_DELAY
    period_seconds: float = DEFAULT_PROBE_PERIOD
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT
    success_threshold: int = DEFAULT_PROBE_SUCCESS_THRESHOLD
    failure_threshold: int = DEFAULT_PROBE_FAILURE_THRESHOLD


@dataclass
class SidecarContainerSpec:
    """Specification for a sidecar container to inject.

    Attributes:
        name: Sidecar container name.
        image: Image reference.
        args: Entrypoint arguments.
        env: Environment variables.
        volume_mounts: Volumes to mount.
        readiness_probe: Optional readiness probe config.
        resource_cpu_millifizz: CPU request in milliFizz.
        resource_memory_fizzbytes: Memory request in FizzBytes.
    """

    name: str
    image: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    volume_mounts: List[str] = field(default_factory=list)
    readiness_probe: Optional[ProbeConfig] = None
    resource_cpu_millifizz: int = 50
    resource_memory_fizzbytes: int = 64


@dataclass
class InjectionPolicy:
    """Policy determining which pods receive sidecar injection.

    Attributes:
        name: Policy name.
        selector_labels: Pods matching these labels receive injection.
        selector_namespaces: Pods in these namespaces receive injection.
        containers: Sidecar container specs to inject.
        volumes: Additional volumes required by the sidecars.
        init_containers: Init containers required by sidecars.
        enabled: Whether this policy is active.
    """

    name: str
    selector_labels: Dict[str, str] = field(default_factory=dict)
    selector_namespaces: List[str] = field(default_factory=list)
    containers: List[SidecarContainerSpec] = field(default_factory=list)
    volumes: List[VolumeMount] = field(default_factory=list)
    init_containers: List[InitContainerSpec] = field(default_factory=list)
    enabled: bool = True


@dataclass
class ProbeStatus:
    """Current status of a probe for a specific container.

    Attributes:
        container_id: Container being probed.
        category: Probe category.
        consecutive_successes: Consecutive successful probes.
        consecutive_failures: Consecutive failed probes.
        last_result: Result of the most recent probe.
        last_probe_time: Timestamp of the most recent probe.
        total_probes: Total probe executions.
        passed: Whether the probe is currently passing.
        message: Human-readable status message.
    """

    container_id: str
    category: ProbeCategory
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    last_result: ProbeResult = ProbeResult.UNKNOWN
    last_probe_time: Optional[datetime] = None
    total_probes: int = 0
    passed: bool = False
    message: str = "Probe not yet executed"


@dataclass
class VolumeSpec:
    """Specification for a pod-level volume.

    Attributes:
        name: Volume name.
        volume_type: Type of volume.
        claim_name: PVC name (for PERSISTENT_VOLUME_CLAIM type).
        config_map_name: ConfigMap name (for CONFIG_MAP type).
        secret_name: Secret name (for SECRET type).
        size_bytes: Size for emptyDir or PVC.
        medium: Storage medium (empty = default, "Memory" = tmpfs).
        data: Key-value data for configMap/secret volumes.
    """

    name: str
    volume_type: VolumeType = VolumeType.EMPTY_DIR
    claim_name: str = ""
    config_map_name: str = ""
    secret_name: str = ""
    size_bytes: int = 1048576  # 1MB default
    medium: str = ""
    data: Dict[str, str] = field(default_factory=dict)


@dataclass
class PVClaim:
    """Persistent Volume Claim.

    Attributes:
        name: Claim name.
        storage_class: Storage class name.
        requested_bytes: Requested storage size.
        bound: Whether the claim is bound to a volume.
        volume_id: Bound volume identifier.
        created_at: When the claim was created.
    """

    name: str
    storage_class: str = "fizz-standard"
    requested_bytes: int = 1048576
    bound: bool = False
    volume_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PodV2Spec:
    """Extended pod specification for FizzKubeV2.

    Extends the original PodSpec with CRI-aware fields: image pull
    policy, init containers, sidecar annotations, probe configs,
    volume mounts, restart policy, and termination grace period.

    Attributes:
        image: Main container image reference.
        image_pull_policy: When to pull the image.
        pull_secrets: Image pull secret references.
        init_containers: Ordered list of init container specs.
        sidecar_annotations: Annotations controlling sidecar injection.
        readiness_probe: Readiness probe configuration.
        liveness_probe: Liveness probe configuration.
        startup_probe: Startup probe configuration.
        volumes: Pod-level volume definitions.
        volume_mounts: Main container volume mounts.
        restart_policy: Container restart policy.
        termination_grace_period: Seconds to wait after SIGTERM.
        cpu_request: CPU request in milliFizz.
        cpu_limit: CPU limit in milliFizz.
        memory_request: Memory request in FizzBytes.
        memory_limit: Memory limit in FizzBytes.
        namespace: Namespace for this pod.
        number: Number to evaluate.
        labels: Pod labels.
        annotations: Pod annotations.
    """

    image: str = "fizzbuzz-eval:latest"
    image_pull_policy: ImagePullPolicy = ImagePullPolicy.IF_NOT_PRESENT
    pull_secrets: List[PullSecret] = field(default_factory=list)
    init_containers: List[InitContainerSpec] = field(default_factory=list)
    sidecar_annotations: Dict[str, str] = field(default_factory=dict)
    readiness_probe: Optional[ProbeConfig] = None
    liveness_probe: Optional[ProbeConfig] = None
    startup_probe: Optional[ProbeConfig] = None
    volumes: List[VolumeSpec] = field(default_factory=list)
    volume_mounts: List[VolumeMount] = field(default_factory=list)
    restart_policy: ContainerRestartPolicy = ContainerRestartPolicy.ALWAYS
    termination_grace_period: float = DEFAULT_TERMINATION_GRACE_PERIOD
    cpu_request: int = 100
    cpu_limit: int = 200
    memory_request: int = 128
    memory_limit: int = 256
    namespace: str = "fizzbuzz-production"
    number: int = 0
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)


@dataclass
class PodV2:
    """A FizzKubeV2 pod with full CRI-backed container lifecycle.

    Attributes:
        name: Unique pod identifier.
        phase: Current lifecycle phase.
        spec: Pod specification.
        node_name: Assigned worker node.
        sandbox_id: CRI pod sandbox ID.
        main_container_id: CRI container ID for the main container.
        sidecar_container_ids: CRI container IDs for sidecars.
        init_results: Results from init container execution.
        probe_statuses: Current probe statuses per container.
        volume_ids: Provisioned volume IDs.
        restart_counts: Per-container restart counts.
        created_at: Pod creation timestamp.
        started_at: When the pod entered RUNNING phase.
        finished_at: When the pod completed.
        result: FizzBuzz evaluation result.
        execution_time_ns: Evaluation time in nanoseconds.
        events: Pod event history.
    """

    name: str = ""
    phase: PodPhaseV2 = PodPhaseV2.PENDING
    spec: PodV2Spec = field(default_factory=PodV2Spec)
    node_name: Optional[str] = None
    sandbox_id: str = ""
    main_container_id: str = ""
    sidecar_container_ids: List[str] = field(default_factory=list)
    init_results: List[InitContainerResult] = field(default_factory=list)
    probe_statuses: Dict[str, Dict[str, ProbeStatus]] = field(default_factory=dict)
    volume_ids: List[str] = field(default_factory=list)
    restart_counts: Dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[str] = None
    execution_time_ns: int = 0
    events: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name:
            suffix = uuid.uuid4().hex[:8]
            self.name = f"fizzbuzz-v2-{suffix}"


# ============================================================
# Default Sidecars
# ============================================================

DEFAULT_SIDECARS: List[SidecarContainerSpec] = [
    SidecarContainerSpec(
        name="fizzbuzz-sidecar-log",
        image="fizzbuzz-sidecar-log:latest",
        args=["--collect-logs", "--forward"],
        env={"LOG_LEVEL": "INFO", "LOG_FORMAT": "json"},
    ),
    SidecarContainerSpec(
        name="fizzbuzz-sidecar-metrics",
        image="fizzbuzz-sidecar-metrics:latest",
        args=["--port", "9090", "--path", "/metrics"],
        env={"METRICS_INTERVAL": "15"},
    ),
    SidecarContainerSpec(
        name="fizzbuzz-sidecar-trace",
        image="fizzbuzz-sidecar-trace:latest",
        args=["--endpoint", "http://jaeger:14268"],
        env={"TRACE_SAMPLE_RATE": "1.0"},
    ),
    SidecarContainerSpec(
        name="fizzbuzz-sidecar-proxy",
        image="fizzbuzz-sidecar-proxy:latest",
        args=["--listen", "0.0.0.0:15001", "--upstream", "localhost:8080"],
        env={"PROXY_PROTOCOL": "http"},
    ),
]


# ============================================================
# CRI Stub — lightweight CRI facade for standalone operation
# ============================================================


class _CRIStub:
    """Lightweight CRI stub for standalone FizzKubeV2 operation.

    When FizzKubeV2 operates without a full FizzContainerd daemon,
    this stub provides a minimal CRI interface that simulates
    container lifecycle operations in memory.  The stub maintains
    sandboxes, containers, and task states sufficient for the
    kubelet to exercise its full lifecycle logic.
    """

    def __init__(self) -> None:
        self._sandboxes: Dict[str, Dict[str, Any]] = {}
        self._containers: Dict[str, Dict[str, Any]] = {}
        self._images: Dict[str, Dict[str, Any]] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def run_pod_sandbox(
        self, labels: Optional[Dict[str, str]] = None
    ) -> str:
        """Create a pod sandbox and return its ID."""
        with self._lock:
            sandbox_id = f"sandbox-{uuid.uuid4().hex[:12]}"
            self._sandboxes[sandbox_id] = {
                "id": sandbox_id,
                "state": "ready",
                "labels": dict(labels or {}),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "containers": [],
            }
            return sandbox_id

    def stop_pod_sandbox(self, sandbox_id: str) -> None:
        """Stop a pod sandbox."""
        with self._lock:
            if sandbox_id in self._sandboxes:
                self._sandboxes[sandbox_id]["state"] = "stopped"
                for cid in self._sandboxes[sandbox_id].get("containers", []):
                    if cid in self._containers:
                        self._containers[cid]["status"] = "stopped"
                        self._containers[cid]["exit_code"] = 0

    def remove_pod_sandbox(self, sandbox_id: str) -> None:
        """Remove a pod sandbox and all its containers."""
        with self._lock:
            if sandbox_id in self._sandboxes:
                for cid in list(
                    self._sandboxes[sandbox_id].get("containers", [])
                ):
                    self._containers.pop(cid, None)
                del self._sandboxes[sandbox_id]

    def create_container(
        self,
        sandbox_id: str,
        image: str,
        name: str = "",
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a container in a sandbox and return its ID."""
        with self._lock:
            self._counter += 1
            container_id = name or f"ctr-{uuid.uuid4().hex[:12]}"
            self._containers[container_id] = {
                "id": container_id,
                "sandbox_id": sandbox_id,
                "image": image,
                "status": "created",
                "pid": 1000 + self._counter,
                "exit_code": -1,
                "config": config or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "stdout": "",
                "stderr": "",
            }
            if sandbox_id in self._sandboxes:
                self._sandboxes[sandbox_id]["containers"].append(container_id)
            return container_id

    def start_container(self, container_id: str) -> Dict[str, Any]:
        """Start a container and return status."""
        with self._lock:
            if container_id in self._containers:
                self._containers[container_id]["status"] = "running"
                return {
                    "pid": self._containers[container_id]["pid"],
                    "state": "running",
                }
            return {"pid": 0, "state": "unknown"}

    def stop_container(self, container_id: str, timeout: float = 10.0) -> None:
        """Stop a container."""
        with self._lock:
            if container_id in self._containers:
                self._containers[container_id]["status"] = "stopped"
                if self._containers[container_id]["exit_code"] == -1:
                    self._containers[container_id]["exit_code"] = 0

    def remove_container(self, container_id: str) -> None:
        """Remove a container."""
        with self._lock:
            if container_id in self._containers:
                sandbox_id = self._containers[container_id].get("sandbox_id", "")
                if sandbox_id in self._sandboxes:
                    containers = self._sandboxes[sandbox_id].get("containers", [])
                    if container_id in containers:
                        containers.remove(container_id)
                del self._containers[container_id]

    def container_status(self, container_id: str) -> Dict[str, Any]:
        """Return container status."""
        with self._lock:
            if container_id in self._containers:
                ctr = self._containers[container_id]
                return {
                    "id": container_id,
                    "status": ctr["status"],
                    "pid": ctr["pid"],
                    "exit_code": ctr["exit_code"],
                    "image": ctr["image"],
                }
            return {"id": container_id, "status": "unknown", "pid": 0, "exit_code": -1}

    def pull_image(self, image: str) -> Dict[str, Any]:
        """Pull an image (simulate)."""
        with self._lock:
            size = random.randint(10000, 500000)
            digest = hashlib.sha256(image.encode()).hexdigest()
            self._images[image] = {
                "image": image,
                "digest": f"sha256:{digest}",
                "size": size,
                "pulled_at": datetime.now(timezone.utc).isoformat(),
            }
            return self._images[image]

    def image_exists(self, image: str) -> bool:
        """Check if an image exists locally."""
        with self._lock:
            return image in self._images

    def exec_container(
        self, container_id: str, command: List[str]
    ) -> Dict[str, Any]:
        """Execute a command in a container."""
        with self._lock:
            if container_id in self._containers:
                ctr = self._containers[container_id]
                if ctr["status"] == "running":
                    return {"exit_code": 0, "stdout": "ok", "stderr": ""}
            return {"exit_code": 1, "stdout": "", "stderr": "container not running"}

    def sandbox_status(self, sandbox_id: str) -> Dict[str, Any]:
        """Return sandbox status."""
        with self._lock:
            if sandbox_id in self._sandboxes:
                return dict(self._sandboxes[sandbox_id])
            return {"id": sandbox_id, "state": "unknown"}

    @property
    def sandbox_count(self) -> int:
        """Return number of sandboxes."""
        with self._lock:
            return len(self._sandboxes)

    @property
    def container_count(self) -> int:
        """Return number of containers."""
        with self._lock:
            return len(self._containers)

    @property
    def image_count(self) -> int:
        """Return number of cached images."""
        with self._lock:
            return len(self._images)


# ============================================================
# ImagePuller — image acquisition with policy enforcement
# ============================================================


class ImagePuller:
    """Manages image acquisition with policy enforcement.

    The ImagePuller integrates with the CRI service (or CRI stub) to
    pull container images according to the configured pull policy.
    It supports Always, IfNotPresent, and Never policies, authenticated
    pulls via pull secrets, progress tracking, and stall detection.

    Each pull generates a PullProgress record that tracks bytes
    downloaded, total size, completion state, and any errors.
    """

    def __init__(
        self,
        cri_service: Any,
        default_policy: ImagePullPolicy = ImagePullPolicy.IF_NOT_PRESENT,
        pull_timeout: float = 120.0,
        stall_threshold: float = 30.0,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the ImagePuller.

        Args:
            cri_service: CRI service or stub for image operations.
            default_policy: Default pull policy.
            pull_timeout: Maximum seconds for a single pull.
            stall_threshold: Seconds without progress before stall.
            event_bus: Optional event bus for image events.
        """
        self._cri = cri_service
        self._default_policy = default_policy
        self._pull_timeout = pull_timeout
        self._stall_threshold = stall_threshold
        self._event_bus = event_bus
        self._pull_history: List[PullProgress] = []
        self._failed_pulls = 0
        self._lock = threading.Lock()

    def pull(
        self,
        image: str,
        policy: Optional[ImagePullPolicy] = None,
        pull_secrets: Optional[List[PullSecret]] = None,
    ) -> PullProgress:
        """Pull an image according to the specified policy.

        Args:
            image: Image reference to pull.
            policy: Pull policy (defaults to constructor default).
            pull_secrets: Credentials for authenticated pulls.

        Returns:
            PullProgress record.

        Raises:
            ImageNotPresentError: If policy is Never and image not local.
            KV2ImagePullError: If the pull fails.
        """
        effective_policy = policy or self._default_policy
        secrets = pull_secrets or []

        self._emit(KUBEV2_IMAGE_PULL_STARTED, {
            "image": image,
            "policy": effective_policy.value,
        })

        # Never policy: fail if not present
        if effective_policy == ImagePullPolicy.NEVER:
            if not self.is_present(image):
                self._failed_pulls += 1
                raise ImageNotPresentError(image)
            progress = PullProgress(
                image=image,
                bytes_downloaded=0,
                bytes_total=0,
                completed_at=datetime.now(timezone.utc),
            )
            with self._lock:
                self._pull_history.append(progress)
            return progress

        # IfNotPresent policy: skip pull if cached
        if effective_policy == ImagePullPolicy.IF_NOT_PRESENT:
            if self.is_present(image):
                progress = PullProgress(
                    image=image,
                    bytes_downloaded=0,
                    bytes_total=0,
                    completed_at=datetime.now(timezone.utc),
                )
                with self._lock:
                    self._pull_history.append(progress)
                self._emit(KUBEV2_IMAGE_PULLED, {
                    "image": image,
                    "cached": True,
                })
                return progress

        # Always or IfNotPresent (not cached): perform pull
        if secrets:
            registry = image.split("/")[0] if "/" in image else "docker.io"
            secret = self._authenticate(registry, secrets)
            if secret is None:
                self._failed_pulls += 1
                raise PullSecretError(
                    secrets[0].name, registry, "No matching credentials"
                )

        try:
            progress = self._simulate_pull(image)
            if self._detect_stall(progress):
                progress.stalled = True
                self._emit(KUBEV2_IMAGE_PULL_STALLED, {"image": image})

            self._emit(KUBEV2_IMAGE_PULLED, {
                "image": image,
                "size": progress.bytes_total,
                "cached": False,
            })
            return progress
        except Exception as exc:
            self._failed_pulls += 1
            error_progress = PullProgress(
                image=image,
                error=str(exc),
            )
            with self._lock:
                self._pull_history.append(error_progress)
            self._emit(KUBEV2_IMAGE_PULL_FAILED, {
                "image": image,
                "error": str(exc),
            })
            raise KV2ImagePullError(
                image, effective_policy.value, str(exc)
            ) from exc

    def is_present(self, image: str) -> bool:
        """Check if an image is in the local cache.

        Args:
            image: Image reference to check.

        Returns:
            True if the image is cached locally.
        """
        if hasattr(self._cri, "image_exists"):
            return self._cri.image_exists(image)
        return False

    def _authenticate(
        self, registry: str, secrets: List[PullSecret]
    ) -> Optional[PullSecret]:
        """Resolve credentials for a registry.

        Args:
            registry: Registry hostname.
            secrets: Available pull secrets.

        Returns:
            Matching PullSecret or None.
        """
        for secret in secrets:
            if secret.registry == registry or not secret.registry:
                return secret
        return None

    def _simulate_pull(self, image: str) -> PullProgress:
        """Simulate an image pull with progress tracking.

        Generates synthetic layer data, computes a SHA-256 digest,
        and records the pull in the CRI service.

        Args:
            image: Image reference to pull.

        Returns:
            Completed PullProgress record.
        """
        started = datetime.now(timezone.utc)
        total_size = random.randint(50000, 500000)

        # Simulate layered download
        downloaded = 0
        layer_count = random.randint(3, 8)
        layer_size = total_size // layer_count

        for i in range(layer_count):
            chunk = layer_size if i < layer_count - 1 else total_size - downloaded
            downloaded += chunk

        # Issue CRI pull
        if hasattr(self._cri, "pull_image"):
            self._cri.pull_image(image)

        progress = PullProgress(
            image=image,
            bytes_downloaded=total_size,
            bytes_total=total_size,
            started_at=started,
            completed_at=datetime.now(timezone.utc),
        )

        with self._lock:
            self._pull_history.append(progress)
        return progress

    def _detect_stall(self, progress: PullProgress) -> bool:
        """Check if a pull has stalled.

        A pull is considered stalled if the download has not completed
        and the elapsed time exceeds the stall threshold.

        Args:
            progress: Pull progress to check.

        Returns:
            True if the pull is stalled.
        """
        if progress.completed_at is not None:
            return False
        elapsed = (datetime.now(timezone.utc) - progress.started_at).total_seconds()
        return elapsed > self._stall_threshold

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        if self._event_bus and hasattr(self._event_bus, "publish"):
            self._event_bus.publish(event_type, data)

    @property
    def total_pulls(self) -> int:
        """Return total number of pull operations."""
        with self._lock:
            return len(self._pull_history)

    @property
    def failed_pulls(self) -> int:
        """Return total number of failed pull operations."""
        return self._failed_pulls

    @property
    def pull_history(self) -> List[PullProgress]:
        """Return the pull history."""
        with self._lock:
            return list(self._pull_history)


# ============================================================
# InitContainerRunner — sequential init container execution
# ============================================================


class InitContainerRunner:
    """Executes init containers sequentially before application containers start.

    Init containers run one at a time, in order.  Each must exit
    successfully (exit code 0) before the next one starts.  If an init
    container fails and the restart policy allows retries, the runner
    restarts it up to max_retries times before declaring failure.

    The init container pattern ensures prerequisites (database migrations,
    config generation, dependency checks) are satisfied before the
    application container starts.
    """

    def __init__(
        self,
        cri_service: Any,
        max_retries: int = DEFAULT_MAX_INIT_CONTAINER_RETRIES,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the InitContainerRunner.

        Args:
            cri_service: CRI service or stub for container operations.
            max_retries: Maximum restart attempts per init container.
            event_bus: Optional event bus for init container events.
        """
        self._cri = cri_service
        self._max_retries = max_retries
        self._event_bus = event_bus
        self._run_history: List[InitContainerResult] = []
        self._total_failures = 0
        self._lock = threading.Lock()

    def run_all(
        self,
        sandbox_id: str,
        init_specs: List[InitContainerSpec],
        restart_policy: ContainerRestartPolicy = ContainerRestartPolicy.ON_FAILURE,
    ) -> List[InitContainerResult]:
        """Execute all init containers in order.

        Each init container must exit 0 before the next starts.
        On failure, the restart policy is applied up to max_retries.

        Args:
            sandbox_id: CRI pod sandbox ID.
            init_specs: Ordered list of init container specifications.
            restart_policy: How to handle init container failures.

        Returns:
            List of InitContainerResult records.

        Raises:
            InitContainerFailedError: If an init container exhausts retries.
            InitContainerTimeoutError: If an init container exceeds timeout.
        """
        results: List[InitContainerResult] = []

        for spec in init_specs:
            self._emit(KUBEV2_INIT_STARTED, {
                "name": spec.name,
                "image": spec.image,
                "sandbox_id": sandbox_id,
            })

            result = self._run_with_retries(sandbox_id, spec, restart_policy)
            results.append(result)

            with self._lock:
                self._run_history.append(result)

            if result.succeeded:
                self._emit(KUBEV2_INIT_COMPLETED, {
                    "name": spec.name,
                    "duration_ms": result.duration_ms,
                    "container_id": result.container_id,
                })
            else:
                self._total_failures += 1
                self._emit(KUBEV2_INIT_FAILED, {
                    "name": spec.name,
                    "exit_code": result.exit_code,
                    "error": result.error,
                })
                raise InitContainerFailedError(
                    spec.name, result.exit_code, sandbox_id
                )

        return results

    def _run_with_retries(
        self,
        sandbox_id: str,
        spec: InitContainerSpec,
        restart_policy: ContainerRestartPolicy,
    ) -> InitContainerResult:
        """Run a single init container with retry logic.

        Args:
            sandbox_id: CRI pod sandbox ID.
            spec: Init container specification.
            restart_policy: Restart policy for failures.

        Returns:
            InitContainerResult record.
        """
        last_result: Optional[InitContainerResult] = None

        for attempt in range(self._max_retries + 1):
            result = self._run_one(sandbox_id, spec)
            last_result = result

            if result.succeeded:
                return result

            if restart_policy == ContainerRestartPolicy.NEVER:
                return result

            if restart_policy == ContainerRestartPolicy.ON_FAILURE and attempt < self._max_retries:
                logger.info(
                    "Init container '%s' failed (attempt %d/%d), retrying",
                    spec.name,
                    attempt + 1,
                    self._max_retries + 1,
                )
                continue

            if attempt >= self._max_retries:
                break

        return last_result  # type: ignore[return-value]

    def _run_one(
        self, sandbox_id: str, spec: InitContainerSpec
    ) -> InitContainerResult:
        """Create, start, and wait for a single init container.

        Args:
            sandbox_id: CRI pod sandbox ID.
            spec: Init container specification.

        Returns:
            InitContainerResult record.
        """
        started = datetime.now(timezone.utc)
        result = InitContainerResult(name=spec.name, started_at=started)

        try:
            # Create container via CRI
            container_id = self._cri.create_container(
                sandbox_id=sandbox_id,
                image=spec.image,
                name=f"init-{spec.name}-{uuid.uuid4().hex[:6]}",
                config={
                    "command": spec.command,
                    "args": spec.args,
                    "env": [f"{k}={v}" for k, v in spec.env.items()],
                },
            )
            result.container_id = container_id

            # Start container
            self._cri.start_container(container_id)

            # Wait for completion
            exit_code = self._wait_for_completion(
                container_id, spec.timeout_seconds
            )
            result.exit_code = exit_code

            completed = datetime.now(timezone.utc)
            result.completed_at = completed
            result.duration_ms = (
                (completed - started).total_seconds() * 1000
            )

            # Collect logs
            status = self._cri.container_status(container_id)
            result.logs = status.get("stdout", "")

            if exit_code != 0:
                result.error = f"Exit code {exit_code}"

            # Cleanup init container
            try:
                self._cri.stop_container(container_id)
            except Exception:
                pass
            try:
                self._cri.remove_container(container_id)
            except Exception:
                pass

            return result

        except Exception as exc:
            result.completed_at = datetime.now(timezone.utc)
            result.error = str(exc)
            result.exit_code = 1
            result.duration_ms = (
                (result.completed_at - started).total_seconds() * 1000
            )
            return result

    def _wait_for_completion(
        self, container_id: str, timeout: float
    ) -> int:
        """Poll CRI ContainerStatus until exit code is available.

        Args:
            container_id: Container to poll.
            timeout: Maximum wait time in seconds.

        Returns:
            Container exit code.

        Raises:
            InitContainerTimeoutError: If timeout expires.
        """
        start_time = time.monotonic()
        while True:
            status = self._cri.container_status(container_id)
            container_state = status.get("status", "unknown")
            if container_state == "stopped":
                return status.get("exit_code", 0)

            elapsed = time.monotonic() - start_time
            if elapsed > timeout:
                raise InitContainerTimeoutError(container_id, timeout)

            # Simulate completion for containers in non-stopped state
            if container_state in ("running", "created"):
                # Mark as completed for simulation purposes
                self._cri.stop_container(container_id)
                return 0

            break

        return 0

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        if self._event_bus and hasattr(self._event_bus, "publish"):
            self._event_bus.publish(event_type, data)

    @property
    def total_runs(self) -> int:
        """Return total init container executions."""
        with self._lock:
            return len(self._run_history)

    @property
    def total_failures(self) -> int:
        """Return total init container failures."""
        return self._total_failures

    @property
    def run_history(self) -> List[InitContainerResult]:
        """Return the init container execution history."""
        with self._lock:
            return list(self._run_history)


# ============================================================
# SidecarInjector — sidecar container injection
# ============================================================


class SidecarInjector:
    """Inspects pod specs and injects sidecar containers based on policies.

    The SidecarInjector evaluates injection policies against pod labels,
    namespaces, and annotations to determine which sidecar containers
    to inject.  Default sidecars (logging, metrics, tracing, proxy) are
    injected into all pods unless the pod opts out via the
    fizzbuzz.io/inject-sidecars annotation.

    Injection policies support label selectors and namespace selectors
    for fine-grained control over which pods receive which sidecars.
    """

    def __init__(
        self,
        policies: Optional[List[InjectionPolicy]] = None,
        default_sidecars: Optional[List[SidecarContainerSpec]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the SidecarInjector.

        Args:
            policies: Registered injection policies.
            default_sidecars: Default sidecars for all pods.
            event_bus: Optional event bus for sidecar events.
        """
        self._policies: List[InjectionPolicy] = list(policies or [])
        self._default_sidecars: List[SidecarContainerSpec] = list(
            default_sidecars or []
        )
        self._event_bus = event_bus
        self._injection_history: List[Dict[str, Any]] = []
        self._total_injections = 0
        self._lock = threading.Lock()

    def inject(
        self, pod_spec: PodV2Spec
    ) -> Tuple[
        List[SidecarContainerSpec], List[VolumeSpec], List[InitContainerSpec]
    ]:
        """Determine which sidecars to inject into a pod.

        Evaluates the pod's labels, namespace, and annotations against
        registered injection policies and default sidecars.

        Args:
            pod_spec: Pod specification to evaluate.

        Returns:
            Tuple of (sidecar specs, additional volumes, additional init containers).
        """
        policy = self._resolve_sidecar_policy(pod_spec)

        if policy == SidecarPolicy.SKIP:
            self._emit(KUBEV2_SIDECAR_SKIPPED, {
                "namespace": pod_spec.namespace,
                "reason": "opt-out annotation",
            })
            with self._lock:
                self._injection_history.append({
                    "namespace": pod_spec.namespace,
                    "policy": "skip",
                    "sidecars": [],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            return [], [], []

        sidecars: List[SidecarContainerSpec] = []
        volumes: List[VolumeSpec] = []
        init_containers: List[InitContainerSpec] = []

        # Add default sidecars
        sidecars.extend(self._default_sidecars)

        # Evaluate policies
        for injection_policy in self._policies:
            if not injection_policy.enabled:
                continue
            if self._matches_policy(pod_spec, injection_policy):
                sidecars.extend(injection_policy.containers)
                for vol in injection_policy.volumes:
                    volumes.append(VolumeSpec(name=vol.name))
                init_containers.extend(injection_policy.init_containers)

        if policy == SidecarPolicy.REQUIRED and not sidecars:
            raise SidecarInjectionError(
                "unknown",
                "required",
                "Required sidecars but none matched",
            )

        self._total_injections += 1
        record = {
            "namespace": pod_spec.namespace,
            "policy": policy.value,
            "sidecars": [s.name for s in sidecars],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._injection_history.append(record)

        if sidecars:
            self._emit(KUBEV2_SIDECAR_INJECTED, {
                "count": len(sidecars),
                "names": [s.name for s in sidecars],
            })

        return sidecars, volumes, init_containers

    def _matches_policy(
        self, pod_spec: PodV2Spec, policy: InjectionPolicy
    ) -> bool:
        """Check if a pod matches a policy's selectors.

        Args:
            pod_spec: Pod specification.
            policy: Injection policy to check.

        Returns:
            True if the pod matches.
        """
        # Check label selectors
        if policy.selector_labels:
            for key, value in policy.selector_labels.items():
                if pod_spec.labels.get(key) != value:
                    return False

        # Check namespace selectors
        if policy.selector_namespaces:
            if pod_spec.namespace not in policy.selector_namespaces:
                return False

        return True

    def _resolve_sidecar_policy(self, pod_spec: PodV2Spec) -> SidecarPolicy:
        """Determine injection policy from pod annotations.

        The annotation 'fizzbuzz.io/inject-sidecars' controls injection:
        - "false": Skip injection
        - "required": Injection is mandatory
        - Any other value or missing: Inject normally

        Args:
            pod_spec: Pod specification.

        Returns:
            Resolved SidecarPolicy.
        """
        annotation = pod_spec.sidecar_annotations.get(
            "fizzbuzz.io/inject-sidecars", ""
        )
        if not annotation:
            annotation = pod_spec.annotations.get(
                "fizzbuzz.io/inject-sidecars", ""
            )

        if annotation == "false":
            return SidecarPolicy.SKIP
        if annotation == "required":
            return SidecarPolicy.REQUIRED
        return SidecarPolicy.INJECT

    def add_policy(self, policy: InjectionPolicy) -> None:
        """Register a new injection policy.

        Args:
            policy: Policy to register.
        """
        self._policies.append(policy)

    def remove_policy(self, name: str) -> None:
        """Remove a policy by name.

        Args:
            name: Policy name to remove.
        """
        self._policies = [p for p in self._policies if p.name != name]

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        if self._event_bus and hasattr(self._event_bus, "publish"):
            self._event_bus.publish(event_type, data)

    @property
    def total_injections(self) -> int:
        """Return total injection operations."""
        return self._total_injections

    @property
    def active_policies(self) -> List[InjectionPolicy]:
        """Return active injection policies."""
        return [p for p in self._policies if p.enabled]

    @property
    def injection_history(self) -> List[Dict[str, Any]]:
        """Return the injection history."""
        with self._lock:
            return list(self._injection_history)


# ============================================================
# ProbeRunner — health probe execution
# ============================================================


class ProbeRunner:
    """Executes readiness, liveness, and startup probes for containers.

    The ProbeRunner manages probe registration, execution, and threshold
    evaluation for all containers in a pod.  It supports HTTP GET, TCP
    socket, and exec probe types, with configurable initial delays,
    periods, timeouts, and success/failure thresholds.

    Probe results determine container readiness (traffic routing),
    liveness (restart decisions), and startup status (premature
    liveness suppression).
    """

    def __init__(
        self,
        cri_service: Any,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the ProbeRunner.

        Args:
            cri_service: CRI service or stub for exec probes.
            event_bus: Optional event bus for probe events.
        """
        self._cri = cri_service
        self._event_bus = event_bus
        self._probes: Dict[str, Dict[str, ProbeConfig]] = defaultdict(dict)
        self._statuses: Dict[str, Dict[str, ProbeStatus]] = defaultdict(dict)
        self._total_probes_executed = 0
        self._lock = threading.Lock()

    def register_probe(
        self, container_id: str, config: ProbeConfig
    ) -> None:
        """Register a probe for a container.

        Args:
            container_id: Container to probe.
            config: Probe configuration.
        """
        category_key = config.category.value
        with self._lock:
            self._probes[container_id][category_key] = config
            self._statuses[container_id][category_key] = ProbeStatus(
                container_id=container_id,
                category=config.category,
            )

    def execute_probe(
        self, container_id: str, category: ProbeCategory
    ) -> ProbeResult:
        """Execute a single probe for a container.

        Args:
            container_id: Container to probe.
            category: Probe category to execute.

        Returns:
            ProbeResult indicating success or failure.
        """
        category_key = category.value
        with self._lock:
            config = self._probes.get(container_id, {}).get(category_key)
            if config is None:
                return ProbeResult.UNKNOWN

        # Dispatch to type-specific handler
        if config.probe_type == ProbeType.HTTP_GET:
            result = self._probe_http(container_id, config)
        elif config.probe_type == ProbeType.TCP_SOCKET:
            result = self._probe_tcp(container_id, config)
        elif config.probe_type == ProbeType.EXEC:
            result = self._probe_exec(container_id, config)
        else:
            result = ProbeResult.UNKNOWN

        # Update status
        self._update_status(container_id, category, result, config)
        self._total_probes_executed += 1

        self._emit(KUBEV2_PROBE_EXECUTED, {
            "container_id": container_id,
            "category": category.value,
            "result": result.value,
        })

        if result == ProbeResult.SUCCESS:
            self._emit(KUBEV2_PROBE_SUCCEEDED, {
                "container_id": container_id,
                "category": category.value,
            })
        else:
            self._emit(KUBEV2_PROBE_FAILED, {
                "container_id": container_id,
                "category": category.value,
                "result": result.value,
            })

        return result

    def execute_all(
        self, container_id: str
    ) -> Dict[ProbeCategory, ProbeResult]:
        """Execute all registered probes for a container.

        Args:
            container_id: Container to probe.

        Returns:
            Mapping of probe category to result.
        """
        results: Dict[ProbeCategory, ProbeResult] = {}
        with self._lock:
            categories = list(self._probes.get(container_id, {}).keys())

        for category_key in categories:
            category = ProbeCategory(category_key)
            results[category] = self.execute_probe(container_id, category)

        return results

    def evaluate_status(
        self, container_id: str, category: ProbeCategory
    ) -> ProbeStatus:
        """Get current probe status with threshold evaluation.

        Args:
            container_id: Container to check.
            category: Probe category.

        Returns:
            Current ProbeStatus.
        """
        category_key = category.value
        with self._lock:
            status = self._statuses.get(container_id, {}).get(category_key)
            if status is None:
                return ProbeStatus(
                    container_id=container_id,
                    category=category,
                    message="No probe registered",
                )
            return copy.copy(status)

    def _probe_http(
        self, container_id: str, config: ProbeConfig
    ) -> ProbeResult:
        """Execute an HTTP GET probe.

        Simulates an HTTP request to the container's port and path.
        The probe succeeds if the simulated response status is 2xx.

        Args:
            container_id: Container to probe.
            config: Probe configuration.

        Returns:
            ProbeResult.
        """
        # Simulate HTTP probe by checking container is running
        status = self._cri.container_status(container_id)
        container_state = status.get("status", "unknown")
        if container_state == "running":
            # Simulate 200 OK response
            hash_val = hashlib.md5(
                f"{container_id}:{config.port}:{config.path}".encode()
            ).hexdigest()
            # Deterministic success based on container state
            return ProbeResult.SUCCESS
        return ProbeResult.FAILURE

    def _probe_tcp(
        self, container_id: str, config: ProbeConfig
    ) -> ProbeResult:
        """Execute a TCP socket probe.

        Simulates a TCP connection attempt to the container's port.
        The probe succeeds if the container is running (port reachable).

        Args:
            container_id: Container to probe.
            config: Probe configuration.

        Returns:
            ProbeResult.
        """
        status = self._cri.container_status(container_id)
        container_state = status.get("status", "unknown")
        if container_state == "running":
            return ProbeResult.SUCCESS
        return ProbeResult.FAILURE

    def _probe_exec(
        self, container_id: str, config: ProbeConfig
    ) -> ProbeResult:
        """Execute a command probe via CRI exec.

        Runs the configured command inside the container.  Exit code 0
        indicates success.

        Args:
            container_id: Container to probe.
            config: Probe configuration.

        Returns:
            ProbeResult.
        """
        try:
            exec_result = self._cri.exec_container(
                container_id, config.command
            )
            if exec_result.get("exit_code", 1) == 0:
                return ProbeResult.SUCCESS
            return ProbeResult.FAILURE
        except Exception:
            return ProbeResult.FAILURE

    def _update_status(
        self,
        container_id: str,
        category: ProbeCategory,
        result: ProbeResult,
        config: ProbeConfig,
    ) -> None:
        """Update probe status with the latest result.

        Tracks consecutive successes and failures and evaluates
        whether the probe passes based on configured thresholds.
        """
        category_key = category.value
        now = datetime.now(timezone.utc)

        with self._lock:
            status = self._statuses.get(container_id, {}).get(category_key)
            if status is None:
                return

            status.last_result = result
            status.last_probe_time = now
            status.total_probes += 1

            was_passing = status.passed

            if result == ProbeResult.SUCCESS:
                status.consecutive_successes += 1
                status.consecutive_failures = 0
                if status.consecutive_successes >= config.success_threshold:
                    status.passed = True
                    status.message = (
                        f"Probe passing ({status.consecutive_successes} "
                        f"consecutive successes)"
                    )
            else:
                status.consecutive_failures += 1
                status.consecutive_successes = 0
                if status.consecutive_failures >= config.failure_threshold:
                    status.passed = False
                    status.message = (
                        f"Probe failing ({status.consecutive_failures} "
                        f"consecutive failures)"
                    )
                else:
                    status.message = (
                        f"Probe failed ({status.consecutive_failures}/"
                        f"{config.failure_threshold} threshold)"
                    )

            # Emit readiness change events
            if category == ProbeCategory.READINESS and was_passing != status.passed:
                self._emit(KUBEV2_READINESS_CHANGED, {
                    "container_id": container_id,
                    "ready": status.passed,
                })

            # Emit liveness failure events
            if (
                category == ProbeCategory.LIVENESS
                and status.consecutive_failures >= config.failure_threshold
            ):
                self._emit(KUBEV2_LIVENESS_FAILED, {
                    "container_id": container_id,
                    "failures": status.consecutive_failures,
                })

    def is_ready(self, container_id: str) -> bool:
        """Check if a container passes its readiness probe.

        Args:
            container_id: Container to check.

        Returns:
            True if the readiness probe is passing.
        """
        status = self.evaluate_status(container_id, ProbeCategory.READINESS)
        return status.passed

    def is_alive(self, container_id: str) -> bool:
        """Check if a container passes its liveness probe.

        Args:
            container_id: Container to check.

        Returns:
            True if the liveness probe is passing.
        """
        status = self.evaluate_status(container_id, ProbeCategory.LIVENESS)
        return status.passed

    def has_started(self, container_id: str) -> bool:
        """Check if a container passes its startup probe.

        Args:
            container_id: Container to check.

        Returns:
            True if the startup probe is passing.
        """
        status = self.evaluate_status(container_id, ProbeCategory.STARTUP)
        return status.passed

    def clear(self, container_id: str) -> None:
        """Remove all probes for a container.

        Args:
            container_id: Container whose probes to remove.
        """
        with self._lock:
            self._probes.pop(container_id, None)
            self._statuses.pop(container_id, None)

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        if self._event_bus and hasattr(self._event_bus, "publish"):
            self._event_bus.publish(event_type, data)

    @property
    def total_probes_executed(self) -> int:
        """Return total probe executions."""
        return self._total_probes_executed

    @property
    def probe_statuses(self) -> Dict[str, Dict[str, ProbeStatus]]:
        """Return all probe statuses."""
        with self._lock:
            result: Dict[str, Dict[str, ProbeStatus]] = {}
            for cid, categories in self._statuses.items():
                result[cid] = {k: copy.copy(v) for k, v in categories.items()}
            return result


# ============================================================
# VolumeManager — volume provisioning and lifecycle
# ============================================================


class VolumeManager:
    """Provisions and manages volumes for containers.

    The VolumeManager handles four volume types: emptyDir (ephemeral
    overlay layers), PVC (persistent overlay layers), configMap
    (projected key-value files), and secret (tmpfs-backed projected
    files).  Each volume is tracked by a unique volume ID and can be
    mounted into multiple containers within a pod.

    Storage is drawn from a configurable storage pool that enforces
    capacity limits.
    """

    def __init__(
        self,
        storage_pool_bytes: int = 10485760,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the VolumeManager.

        Args:
            storage_pool_bytes: Total storage pool for volume provisioning.
            event_bus: Optional event bus for volume events.
        """
        self._storage_pool = storage_pool_bytes
        self._storage_used = 0
        self._event_bus = event_bus
        self._volumes: Dict[str, Dict[str, Any]] = {}
        self._mounts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._pvcs: Dict[str, PVClaim] = {}
        self._total_provisioned = 0
        self._lock = threading.Lock()

    def provision_volumes(
        self, volumes: List[VolumeSpec]
    ) -> Dict[str, str]:
        """Provision all volumes for a pod.

        Args:
            volumes: Volume specifications to provision.

        Returns:
            Mapping of volume name to volume ID.

        Raises:
            VolumeProvisionError: If provisioning fails.
        """
        provisioned: Dict[str, str] = {}

        for spec in volumes:
            if spec.volume_type == VolumeType.EMPTY_DIR:
                vid = self._provision_empty_dir(spec)
            elif spec.volume_type == VolumeType.PERSISTENT_VOLUME_CLAIM:
                vid = self._provision_pvc(spec)
            elif spec.volume_type == VolumeType.CONFIG_MAP:
                vid = self._provision_config_map(spec)
            elif spec.volume_type == VolumeType.SECRET:
                vid = self._provision_secret(spec)
            else:
                raise VolumeProvisionError(
                    spec.name, "unknown", f"Unknown volume type: {spec.volume_type}"
                )

            provisioned[spec.name] = vid
            self._total_provisioned += 1

            self._emit(KUBEV2_VOLUME_PROVISIONED, {
                "name": spec.name,
                "type": spec.volume_type.value,
                "volume_id": vid,
            })

        return provisioned

    def mount_volumes(
        self,
        container_id: str,
        volume_mounts: List[VolumeMount],
        provisioned: Dict[str, str],
    ) -> None:
        """Mount provisioned volumes into a container.

        Args:
            container_id: Container to mount volumes into.
            volume_mounts: Volume mount specifications.
            provisioned: Mapping of volume name to volume ID.

        Raises:
            VolumeMountError: If mounting fails.
        """
        for mount in volume_mounts:
            volume_id = provisioned.get(mount.name)
            if volume_id is None:
                raise VolumeMountError(
                    mount.name, container_id, mount.mount_path,
                    f"Volume '{mount.name}' not provisioned",
                )

            with self._lock:
                self._mounts[container_id].append({
                    "volume_name": mount.name,
                    "volume_id": volume_id,
                    "mount_path": mount.mount_path,
                    "read_only": mount.read_only,
                    "sub_path": mount.sub_path,
                })

            self._emit(KUBEV2_VOLUME_MOUNTED, {
                "container_id": container_id,
                "volume_name": mount.name,
                "mount_path": mount.mount_path,
            })

    def cleanup_volumes(
        self, volume_ids: List[str], preserve_pvcs: bool = True
    ) -> int:
        """Clean up volumes after pod termination.

        Args:
            volume_ids: Volume IDs to clean up.
            preserve_pvcs: Whether to preserve PVC-backed volumes.

        Returns:
            Number of volumes cleaned up.
        """
        cleaned = 0
        with self._lock:
            for vid in volume_ids:
                vol = self._volumes.get(vid)
                if vol is None:
                    continue
                if preserve_pvcs and vol.get("type") == VolumeType.PERSISTENT_VOLUME_CLAIM.value:
                    continue
                size = vol.get("size", 0)
                self._storage_used = max(0, self._storage_used - size)
                del self._volumes[vid]
                cleaned += 1

        if cleaned > 0:
            self._emit(KUBEV2_VOLUME_CLEANED, {
                "count": cleaned,
                "volume_ids": volume_ids,
            })

        return cleaned

    def _provision_empty_dir(self, spec: VolumeSpec) -> str:
        """Provision an ephemeral emptyDir volume.

        Args:
            spec: Volume specification.

        Returns:
            Volume ID.

        Raises:
            VolumeProvisionError: If storage pool exhausted.
        """
        volume_id = f"vol-empty-{uuid.uuid4().hex[:8]}"

        with self._lock:
            if self._storage_used + spec.size_bytes > self._storage_pool:
                raise VolumeProvisionError(
                    spec.name, "emptyDir",
                    f"Insufficient storage: {spec.size_bytes} bytes requested, "
                    f"{self._storage_pool - self._storage_used} available",
                )
            self._storage_used += spec.size_bytes
            self._volumes[volume_id] = {
                "id": volume_id,
                "name": spec.name,
                "type": VolumeType.EMPTY_DIR.value,
                "size": spec.size_bytes,
                "medium": spec.medium,
                "data": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        return volume_id

    def _provision_pvc(self, spec: VolumeSpec) -> str:
        """Bind a PVC to a persistent volume.

        Args:
            spec: Volume specification.

        Returns:
            Volume ID.

        Raises:
            PVCNotFoundError: If PVC does not exist.
        """
        if spec.claim_name not in self._pvcs:
            raise PVCNotFoundError(spec.claim_name)

        claim = self._pvcs[spec.claim_name]
        volume_id = f"vol-pvc-{uuid.uuid4().hex[:8]}"

        with self._lock:
            claim.bound = True
            claim.volume_id = volume_id
            self._volumes[volume_id] = {
                "id": volume_id,
                "name": spec.name,
                "type": VolumeType.PERSISTENT_VOLUME_CLAIM.value,
                "size": claim.requested_bytes,
                "claim_name": spec.claim_name,
                "data": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._storage_used += claim.requested_bytes

        self._emit(KUBEV2_PVC_BOUND, {
            "claim_name": spec.claim_name,
            "volume_id": volume_id,
        })

        return volume_id

    def _provision_config_map(self, spec: VolumeSpec) -> str:
        """Project a ConfigMap as files.

        Args:
            spec: Volume specification.

        Returns:
            Volume ID.
        """
        volume_id = f"vol-cm-{uuid.uuid4().hex[:8]}"

        with self._lock:
            self._volumes[volume_id] = {
                "id": volume_id,
                "name": spec.name,
                "type": VolumeType.CONFIG_MAP.value,
                "size": 0,
                "config_map_name": spec.config_map_name,
                "data": dict(spec.data),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        return volume_id

    def _provision_secret(self, spec: VolumeSpec) -> str:
        """Project a Secret as tmpfs-backed files.

        Args:
            spec: Volume specification.

        Returns:
            Volume ID.
        """
        volume_id = f"vol-secret-{uuid.uuid4().hex[:8]}"

        with self._lock:
            self._volumes[volume_id] = {
                "id": volume_id,
                "name": spec.name,
                "type": VolumeType.SECRET.value,
                "size": 0,
                "secret_name": spec.secret_name,
                "data": dict(spec.data),
                "medium": "Memory",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        return volume_id

    def create_pvc(self, claim: PVClaim) -> str:
        """Create a new PersistentVolumeClaim.

        Args:
            claim: PVC specification.

        Returns:
            Claim name.
        """
        self._pvcs[claim.name] = claim
        return claim.name

    def delete_pvc(self, name: str) -> None:
        """Delete a PVC and release storage.

        Args:
            name: Claim name to delete.
        """
        claim = self._pvcs.pop(name, None)
        if claim and claim.volume_id:
            with self._lock:
                vol = self._volumes.pop(claim.volume_id, None)
                if vol:
                    self._storage_used = max(
                        0, self._storage_used - vol.get("size", 0)
                    )

    def list_pvcs(self) -> List[PVClaim]:
        """List all PersistentVolumeClaims.

        Returns:
            List of PVClaim objects.
        """
        return list(self._pvcs.values())

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        if self._event_bus and hasattr(self._event_bus, "publish"):
            self._event_bus.publish(event_type, data)

    @property
    def total_provisioned(self) -> int:
        """Return total volumes provisioned."""
        return self._total_provisioned

    @property
    def active_volumes(self) -> int:
        """Return number of active volumes."""
        with self._lock:
            return len(self._volumes)

    @property
    def storage_used_bytes(self) -> int:
        """Return storage bytes in use."""
        return self._storage_used

    @property
    def storage_available_bytes(self) -> int:
        """Return storage bytes available."""
        return max(0, self._storage_pool - self._storage_used)


# ============================================================
# KubeletV2 — CRI-integrated kubelet
# ============================================================


class KubeletV2:
    """CRI-integrated kubelet for FizzKubeV2.

    The central class that orchestrates the full pod lifecycle through
    the container runtime stack.  The KubeletV2 replaces the original
    kubelet's dataclass-instantiation "container creation" with actual
    CRI calls: image pulls, pod sandbox creation, init container
    execution, sidecar injection, container creation and startup,
    probe registration and execution, volume provisioning and mounting,
    restart backoff management, and graceful pod termination.

    Each pod lifecycle follows the Kubernetes kubelet v1.29 state machine
    with the addition of CRI-specific intermediate phases.
    """

    def __init__(
        self,
        cri_service: Any,
        image_puller: ImagePuller,
        init_runner: InitContainerRunner,
        sidecar_injector: SidecarInjector,
        probe_runner: ProbeRunner,
        volume_manager: VolumeManager,
        restart_backoff_base: float = DEFAULT_RESTART_BACKOFF_BASE,
        restart_backoff_cap: float = DEFAULT_RESTART_BACKOFF_CAP,
        restart_backoff_multiplier: float = DEFAULT_RESTART_BACKOFF_MULTIPLIER,
        rules: Optional[List[Dict]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the KubeletV2.

        Args:
            cri_service: CRI service or stub.
            image_puller: ImagePuller instance.
            init_runner: InitContainerRunner instance.
            sidecar_injector: SidecarInjector instance.
            probe_runner: ProbeRunner instance.
            volume_manager: VolumeManager instance.
            restart_backoff_base: Base restart backoff seconds.
            restart_backoff_cap: Maximum restart backoff seconds.
            restart_backoff_multiplier: Backoff multiplier.
            rules: FizzBuzz evaluation rules.
            event_bus: Optional event bus.
        """
        self._cri = cri_service
        self._image_puller = image_puller
        self._init_runner = init_runner
        self._sidecar_injector = sidecar_injector
        self._probe_runner = probe_runner
        self._volume_manager = volume_manager
        self._restart_backoff_base = restart_backoff_base
        self._restart_backoff_cap = restart_backoff_cap
        self._restart_backoff_multiplier = restart_backoff_multiplier
        self._rules = rules or [
            {"divisor": 3, "label": "Fizz", "priority": 1},
            {"divisor": 5, "label": "Buzz", "priority": 2},
        ]
        self._event_bus = event_bus
        self._pods: Dict[str, PodV2] = {}
        self._total_pods_created = 0
        self._total_restarts = 0
        self._restart_history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def create_pod(self, spec: PodV2Spec) -> PodV2:
        """Execute the full pod creation lifecycle.

        1. Set phase to IMAGE_PULLING.  Pull all images.
        2. Create pod sandbox via CRI RunPodSandbox.
        3. Provision volumes via VolumeManager.
        4. Set phase to INIT_RUNNING.  Run init containers.
        5. Inject sidecars.  Create and start sidecar containers.
        6. Wait for sidecar readiness probes.
        7. Set phase to CONTAINER_CREATING.  Create and start main container.
        8. Register probes with ProbeRunner.
        9. Set phase to RUNNING.
        10. Return PodV2 object.

        Args:
            spec: Pod specification.

        Returns:
            Created PodV2 with all lifecycle phases completed.

        Raises:
            KubeletV2Error: If any lifecycle phase fails.
        """
        pod = PodV2(spec=spec)
        pod.node_name = f"fizz-node-{random.randint(1, 8):02d}"

        self._emit(KUBEV2_POD_CREATED, {
            "pod": pod.name,
            "namespace": spec.namespace,
            "image": spec.image,
        })
        self._emit(KUBEV2_POD_SCHEDULED, {
            "pod": pod.name,
            "node": pod.node_name,
        })

        try:
            # Phase 1: Pull images
            pod.phase = PodPhaseV2.IMAGE_PULLING
            self._pull_all_images(pod)

            # Phase 2: Create pod sandbox
            sandbox_id = self._cri.run_pod_sandbox(
                labels={
                    "app": "fizzbuzz",
                    "pod": pod.name,
                    "namespace": spec.namespace,
                }
            )
            pod.sandbox_id = sandbox_id

            # Phase 3: Provision volumes
            if spec.volumes:
                provisioned = self._volume_manager.provision_volumes(spec.volumes)
                pod.volume_ids = list(provisioned.values())
            else:
                provisioned = {}

            # Phase 4: Run init containers
            if spec.init_containers:
                pod.phase = PodPhaseV2.INIT_RUNNING
                try:
                    init_results = self._init_runner.run_all(
                        sandbox_id, spec.init_containers, spec.restart_policy
                    )
                    pod.init_results = init_results
                except InitContainerFailedError:
                    pod.phase = PodPhaseV2.INIT_FAILURE
                    raise

            # Phase 5: Inject sidecars
            sidecar_specs, extra_volumes, extra_inits = (
                self._sidecar_injector.inject(spec)
            )

            # Run additional init containers from sidecars
            if extra_inits:
                extra_results = self._init_runner.run_all(
                    sandbox_id, extra_inits, spec.restart_policy
                )
                pod.init_results.extend(extra_results)

            # Create and start sidecar containers
            for sidecar_spec in sidecar_specs:
                sidecar_cid = self._cri.create_container(
                    sandbox_id=sandbox_id,
                    image=sidecar_spec.image,
                    name=f"sidecar-{sidecar_spec.name}-{uuid.uuid4().hex[:6]}",
                    config={
                        "args": sidecar_spec.args,
                        "env": [f"{k}={v}" for k, v in sidecar_spec.env.items()],
                    },
                )
                self._cri.start_container(sidecar_cid)
                pod.sidecar_container_ids.append(sidecar_cid)

                self._emit(KUBEV2_CONTAINER_STARTED, {
                    "pod": pod.name,
                    "container_id": sidecar_cid,
                    "type": "sidecar",
                    "name": sidecar_spec.name,
                })

                # Register sidecar readiness probe
                if sidecar_spec.readiness_probe:
                    self._probe_runner.register_probe(
                        sidecar_cid, sidecar_spec.readiness_probe
                    )

            # Phase 6: Wait for sidecar readiness
            for sidecar_cid in pod.sidecar_container_ids:
                probe_categories = list(
                    self._probe_runner._probes.get(sidecar_cid, {}).keys()
                )
                if probe_categories:
                    for cat_key in probe_categories:
                        self._probe_runner.execute_probe(
                            sidecar_cid, ProbeCategory(cat_key)
                        )

            # Phase 7: Create and start main container
            pod.phase = PodPhaseV2.CONTAINER_CREATING
            main_cid = self._cri.create_container(
                sandbox_id=sandbox_id,
                image=spec.image,
                name=f"main-{pod.name}",
                config={
                    "args": [],
                    "env": [f"FIZZBUZZ_NUMBER={spec.number}"],
                },
            )
            pod.main_container_id = main_cid
            self._cri.start_container(main_cid)

            # Mount volumes to main container
            if spec.volume_mounts and provisioned:
                self._volume_manager.mount_volumes(
                    main_cid, spec.volume_mounts, provisioned
                )

            self._emit(KUBEV2_CONTAINER_STARTED, {
                "pod": pod.name,
                "container_id": main_cid,
                "type": "main",
            })

            # Phase 8: Register probes
            if spec.readiness_probe:
                self._probe_runner.register_probe(main_cid, spec.readiness_probe)
            if spec.liveness_probe:
                self._probe_runner.register_probe(main_cid, spec.liveness_probe)
            if spec.startup_probe:
                self._probe_runner.register_probe(main_cid, spec.startup_probe)

            # Execute initial probes
            self._probe_runner.execute_all(main_cid)

            # Collect probe statuses
            pod.probe_statuses = self._probe_runner.probe_statuses

            # Phase 9: Running
            pod.phase = PodPhaseV2.RUNNING
            pod.started_at = datetime.now(timezone.utc)

            self._emit(KUBEV2_POD_RUNNING, {
                "pod": pod.name,
                "main_container": main_cid,
                "sidecar_count": len(pod.sidecar_container_ids),
            })

            # Register pod
            self._total_pods_created += 1
            with self._lock:
                self._pods[pod.name] = pod

            return pod

        except (
            KubeV2Error,
            ImageNotPresentError,
            InitContainerFailedError,
            InitContainerTimeoutError,
            SidecarInjectionError,
            VolumeProvisionError,
            PVCNotFoundError,
        ) as exc:
            pod.phase = PodPhaseV2.FAILED
            pod.finished_at = datetime.now(timezone.utc)
            self._emit(KUBEV2_POD_FAILED, {
                "pod": pod.name,
                "error": str(exc),
            })
            with self._lock:
                self._pods[pod.name] = pod
            raise KubeletV2Error(str(exc)) from exc

    def evaluate(
        self, number: int, spec: Optional[PodV2Spec] = None
    ) -> Tuple[str, PodV2]:
        """Create a pod, evaluate FizzBuzz, and complete the pod.

        Args:
            number: Number to evaluate.
            spec: Optional pod specification.

        Returns:
            Tuple of (FizzBuzz result string, PodV2).
        """
        if spec is None:
            spec = PodV2Spec(number=number)
        else:
            spec.number = number

        pod = self.create_pod(spec)

        # Evaluate FizzBuzz
        start_ns = time.monotonic_ns()
        result = self._evaluate_fizzbuzz(number)
        elapsed_ns = time.monotonic_ns() - start_ns

        pod.result = result
        pod.execution_time_ns = elapsed_ns
        pod.phase = PodPhaseV2.SUCCEEDED
        pod.finished_at = datetime.now(timezone.utc)

        pod.events.append({
            "type": "evaluation",
            "number": number,
            "result": result,
            "time_ns": elapsed_ns,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        self._emit(KUBEV2_POD_SUCCEEDED, {
            "pod": pod.name,
            "result": result,
            "time_ns": elapsed_ns,
        })

        # Terminate the pod
        self.terminate_pod(pod)

        return result, pod

    def terminate_pod(self, pod: PodV2) -> None:
        """Execute graceful pod termination.

        1. Set phase to TERMINATING.
        2. Send SIGTERM to main container via CRI.
        3. Wait termination_grace_period seconds.
        4. Send SIGKILL to remaining containers.
        5. Stop and remove sidecar containers.
        6. Remove pod sandbox.
        7. Clean up volumes.
        8. Set final phase.

        Args:
            pod: Pod to terminate.
        """
        previous_phase = pod.phase
        pod.phase = PodPhaseV2.TERMINATING

        self._emit(KUBEV2_POD_TERMINATING, {
            "pod": pod.name,
            "previous_phase": previous_phase.name,
        })

        try:
            # Stop main container
            if pod.main_container_id:
                try:
                    self._cri.stop_container(
                        pod.main_container_id,
                        timeout=pod.spec.termination_grace_period,
                    )
                except Exception:
                    pass
                try:
                    self._cri.remove_container(pod.main_container_id)
                except Exception:
                    pass

            # Stop and remove sidecars
            for sidecar_cid in pod.sidecar_container_ids:
                try:
                    self._cri.stop_container(sidecar_cid)
                except Exception:
                    pass
                try:
                    self._cri.remove_container(sidecar_cid)
                except Exception:
                    pass

            # Clear probes
            if pod.main_container_id:
                self._probe_runner.clear(pod.main_container_id)
            for sidecar_cid in pod.sidecar_container_ids:
                self._probe_runner.clear(sidecar_cid)

            # Remove pod sandbox
            if pod.sandbox_id:
                try:
                    self._cri.stop_pod_sandbox(pod.sandbox_id)
                except Exception:
                    pass
                try:
                    self._cri.remove_pod_sandbox(pod.sandbox_id)
                except Exception:
                    pass

            # Clean up volumes
            if pod.volume_ids:
                self._volume_manager.cleanup_volumes(pod.volume_ids)

            # Set final phase
            if previous_phase == PodPhaseV2.SUCCEEDED or pod.result is not None:
                pod.phase = PodPhaseV2.SUCCEEDED
            else:
                pod.phase = PodPhaseV2.FAILED

            if pod.finished_at is None:
                pod.finished_at = datetime.now(timezone.utc)

        except Exception as exc:
            pod.phase = PodPhaseV2.FAILED
            pod.finished_at = datetime.now(timezone.utc)
            raise PodTerminationError(pod.name, str(exc)) from exc

    def restart_container(
        self, pod: PodV2, container_id: str, restart_count: int
    ) -> None:
        """Restart a container with exponential backoff.

        Backoff calculation: min(base * multiplier^count, cap)

        Args:
            pod: Pod containing the container.
            container_id: Container to restart.
            restart_count: Current restart count.
        """
        backoff = min(
            self._restart_backoff_base
            * (self._restart_backoff_multiplier ** restart_count),
            self._restart_backoff_cap,
        )

        # Stop existing container
        try:
            self._cri.stop_container(container_id)
        except Exception:
            pass

        # Start container
        self._cri.start_container(container_id)

        pod.restart_counts[container_id] = restart_count + 1
        self._total_restarts += 1

        restart_record = {
            "pod": pod.name,
            "container_id": container_id,
            "restart_count": restart_count + 1,
            "backoff_seconds": backoff,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._restart_history.append(restart_record)

        self._emit(KUBEV2_CONTAINER_RESTARTED, restart_record)

    def _pull_all_images(self, pod: PodV2) -> None:
        """Pull all images required by the pod.

        Pulls the main container image, init container images, and
        sidecar images according to the pod's pull policy.

        Args:
            pod: Pod whose images to pull.
        """
        spec = pod.spec
        images_to_pull: Set[str] = {spec.image}

        for init_spec in spec.init_containers:
            images_to_pull.add(init_spec.image)

        # Pull each unique image
        for image in sorted(images_to_pull):
            self._image_puller.pull(
                image,
                policy=spec.image_pull_policy,
                pull_secrets=spec.pull_secrets,
            )

    def _evaluate_fizzbuzz(self, number: int) -> str:
        """Apply configured rules to evaluate the number.

        Handles both RuleDefinition dataclass objects and raw dicts.

        Args:
            number: Number to evaluate.

        Returns:
            FizzBuzz result string.
        """

        def _get_attr(rule: Any, key: str, default: Any = None) -> Any:
            if isinstance(rule, dict):
                return rule.get(key, default)
            return getattr(rule, key, default)

        labels: List[str] = []
        for rule in sorted(
            self._rules, key=lambda r: _get_attr(r, "priority", 0)
        ):
            divisor = _get_attr(rule, "divisor", 0)
            if divisor and number % divisor == 0:
                labels.append(_get_attr(rule, "label", ""))
        return "".join(labels) if labels else str(number)

    def get_pod_status(self, pod: PodV2) -> Dict[str, Any]:
        """Get detailed pod status.

        Args:
            pod: Pod to inspect.

        Returns:
            Detailed status dictionary.
        """
        status: Dict[str, Any] = {
            "name": pod.name,
            "phase": pod.phase.name,
            "node": pod.node_name,
            "sandbox_id": pod.sandbox_id,
            "main_container_id": pod.main_container_id,
            "sidecar_count": len(pod.sidecar_container_ids),
            "init_container_results": [
                {
                    "name": r.name,
                    "exit_code": r.exit_code,
                    "succeeded": r.succeeded,
                    "duration_ms": r.duration_ms,
                }
                for r in pod.init_results
            ],
            "volumes": pod.volume_ids,
            "restart_counts": dict(pod.restart_counts),
            "created_at": pod.created_at.isoformat(),
            "started_at": pod.started_at.isoformat() if pod.started_at else None,
            "finished_at": pod.finished_at.isoformat() if pod.finished_at else None,
            "result": pod.result,
            "execution_time_ns": pod.execution_time_ns,
        }

        # Add probe statuses
        if pod.main_container_id:
            status["probes"] = {}
            for cat in ProbeCategory:
                probe_status = self._probe_runner.evaluate_status(
                    pod.main_container_id, cat
                )
                status["probes"][cat.value] = {
                    "passed": probe_status.passed,
                    "total_probes": probe_status.total_probes,
                    "consecutive_successes": probe_status.consecutive_successes,
                    "consecutive_failures": probe_status.consecutive_failures,
                    "message": probe_status.message,
                }

        return status

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        if self._event_bus and hasattr(self._event_bus, "publish"):
            self._event_bus.publish(event_type, data)

    @property
    def total_pods_created(self) -> int:
        """Return total pods created."""
        return self._total_pods_created

    @property
    def active_pods(self) -> Dict[str, PodV2]:
        """Return all tracked pods."""
        with self._lock:
            return dict(self._pods)

    @property
    def total_restarts(self) -> int:
        """Return total container restarts."""
        return self._total_restarts

    @property
    def restart_history(self) -> List[Dict[str, Any]]:
        """Return restart history."""
        return list(self._restart_history)

    @property
    def image_puller(self) -> ImagePuller:
        """Return the image puller."""
        return self._image_puller

    @property
    def init_runner(self) -> InitContainerRunner:
        """Return the init container runner."""
        return self._init_runner

    @property
    def sidecar_injector(self) -> SidecarInjector:
        """Return the sidecar injector."""
        return self._sidecar_injector

    @property
    def probe_runner(self) -> ProbeRunner:
        """Return the probe runner."""
        return self._probe_runner

    @property
    def volume_manager(self) -> VolumeManager:
        """Return the volume manager."""
        return self._volume_manager


# ============================================================
# KubeV2Dashboard — ASCII dashboard
# ============================================================


class KubeV2Dashboard:
    """ASCII dashboard for FizzKubeV2 state visualization.

    Renders pod inventory, container status, probe results, volume
    status, image pull history, and restart events in a compact
    ASCII format suitable for terminal display.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        """Initialize the dashboard.

        Args:
            width: Dashboard character width.
        """
        self._width = width

    def render(self, kubelet: KubeletV2) -> str:
        """Render the full dashboard.

        Args:
            kubelet: KubeletV2 instance to visualize.

        Returns:
            ASCII dashboard string.
        """
        lines: List[str] = []
        lines.append("=" * self._width)
        lines.append(self._center("FizzKubeV2 Dashboard"))
        lines.append(self._center(f"Version {KUBEV2_VERSION}"))
        lines.append("=" * self._width)
        lines.append("")

        # Stats summary
        lines.append(f"  Pods Created:      {kubelet.total_pods_created}")
        lines.append(f"  Active Pods:       {len(kubelet.active_pods)}")
        lines.append(f"  Total Restarts:    {kubelet.total_restarts}")
        lines.append(f"  Images Pulled:     {kubelet.image_puller.total_pulls}")
        lines.append(f"  Init Runs:         {kubelet.init_runner.total_runs}")
        lines.append(
            f"  Sidecar Injections: {kubelet.sidecar_injector.total_injections}"
        )
        lines.append(
            f"  Probes Executed:   {kubelet.probe_runner.total_probes_executed}"
        )
        lines.append(
            f"  Volumes Provisioned: {kubelet.volume_manager.total_provisioned}"
        )
        lines.append(
            f"  Storage Used:      {self._format_bytes(kubelet.volume_manager.storage_used_bytes)}"
        )
        lines.append("")

        # Pod list
        lines.append("-" * self._width)
        lines.append(self._center("Pods"))
        lines.append("-" * self._width)
        lines.append(self.render_pods(kubelet))

        # Probe status
        lines.append("-" * self._width)
        lines.append(self._center("Probe Status"))
        lines.append("-" * self._width)
        lines.append(self.render_probes(kubelet))

        # Image history
        lines.append("-" * self._width)
        lines.append(self._center("Image Pull History"))
        lines.append("-" * self._width)
        lines.append(self.render_images(kubelet))

        # Events
        lines.append("-" * self._width)
        lines.append(self._center("Recent Events"))
        lines.append("-" * self._width)
        lines.append(self.render_events(kubelet))

        lines.append("=" * self._width)
        return "\n".join(lines)

    def render_pods(self, kubelet: KubeletV2) -> str:
        """Render pod list with phases and container counts.

        Args:
            kubelet: KubeletV2 instance.

        Returns:
            ASCII pod list.
        """
        lines: List[str] = []
        pods = kubelet.active_pods

        if not pods:
            lines.append("  No pods")
            return "\n".join(lines)

        lines.append(
            f"  {'NAME':<30} {'PHASE':<18} {'INIT':<6} {'SCARS':<6} {'RESTARTS':<8}"
        )
        for name, pod in sorted(pods.items()):
            init_count = len(pod.init_results)
            sidecar_count = len(pod.sidecar_container_ids)
            restart_total = sum(pod.restart_counts.values())
            lines.append(
                f"  {name:<30} {pod.phase.name:<18} "
                f"{init_count:<6} {sidecar_count:<6} {restart_total:<8}"
            )

        return "\n".join(lines)

    def render_pod_detail(self, pod: PodV2) -> str:
        """Render detailed pod view.

        Args:
            pod: Pod to detail.

        Returns:
            ASCII pod detail.
        """
        lines: List[str] = []
        lines.append(f"  Pod: {pod.name}")
        lines.append(f"  Phase: {pod.phase.name}")
        lines.append(f"  Node: {pod.node_name or 'unscheduled'}")
        lines.append(f"  Sandbox: {pod.sandbox_id}")
        lines.append(f"  Main Container: {pod.main_container_id}")
        lines.append(f"  Image: {pod.spec.image}")
        lines.append(f"  Namespace: {pod.spec.namespace}")
        lines.append("")

        # Init containers
        if pod.init_results:
            lines.append("  Init Containers:")
            for result in pod.init_results:
                status = "OK" if result.succeeded else f"FAIL({result.exit_code})"
                lines.append(
                    f"    {result.name}: {status} "
                    f"({result.duration_ms:.1f}ms)"
                )
            lines.append("")

        # Sidecars
        if pod.sidecar_container_ids:
            lines.append("  Sidecars:")
            for cid in pod.sidecar_container_ids:
                lines.append(f"    {cid}")
            lines.append("")

        # Volumes
        if pod.volume_ids:
            lines.append("  Volumes:")
            for vid in pod.volume_ids:
                lines.append(f"    {vid}")
            lines.append("")

        # Result
        if pod.result is not None:
            lines.append(f"  Result: {pod.result}")
            lines.append(f"  Execution Time: {pod.execution_time_ns}ns")

        return "\n".join(lines)

    def render_probes(self, kubelet: KubeletV2) -> str:
        """Render probe status for all containers.

        Args:
            kubelet: KubeletV2 instance.

        Returns:
            ASCII probe status.
        """
        lines: List[str] = []
        statuses = kubelet.probe_runner.probe_statuses

        if not statuses:
            lines.append("  No probes registered")
            return "\n".join(lines)

        for cid, categories in sorted(statuses.items()):
            for cat_key, status in sorted(categories.items()):
                passed = "PASS" if status.passed else "FAIL"
                lines.append(
                    f"  {cid[:24]:<24} {cat_key:<12} {passed:<6} "
                    f"S:{status.consecutive_successes} F:{status.consecutive_failures}"
                )

        return "\n".join(lines)

    def render_images(self, kubelet: KubeletV2) -> str:
        """Render image pull history.

        Args:
            kubelet: KubeletV2 instance.

        Returns:
            ASCII image list.
        """
        lines: List[str] = []
        history = kubelet.image_puller.pull_history

        if not history:
            lines.append("  No images pulled")
            return "\n".join(lines)

        for progress in history[-10:]:
            status = "OK" if not progress.error else f"ERR: {progress.error[:30]}"
            size_str = self._format_bytes(progress.bytes_total)
            lines.append(
                f"  {progress.image[:35]:<35} {size_str:>8} {status}"
            )

        return "\n".join(lines)

    def render_events(self, kubelet: KubeletV2) -> str:
        """Render recent kubelet events.

        Args:
            kubelet: KubeletV2 instance.

        Returns:
            ASCII event list.
        """
        lines: List[str] = []
        all_events: List[Dict[str, Any]] = []

        for pod in kubelet.active_pods.values():
            for event in pod.events:
                all_events.append({
                    "pod": pod.name,
                    **event,
                })

        if not all_events:
            lines.append("  No events")
            return "\n".join(lines)

        for event in all_events[-10:]:
            event_type = event.get("type", "unknown")
            pod_name = event.get("pod", "")
            lines.append(f"  {pod_name[:25]:<25} {event_type}")

        return "\n".join(lines)

    def _center(self, text: str) -> str:
        """Center text within dashboard width.

        Args:
            text: Text to center.

        Returns:
            Centered text.
        """
        return text.center(self._width)

    def _format_bytes(self, n: int) -> str:
        """Format bytes with human-readable units.

        Args:
            n: Number of bytes.

        Returns:
            Formatted string (e.g., "1.5 MB").
        """
        if n < 1024:
            return f"{n} B"
        elif n < 1048576:
            return f"{n / 1024:.1f} KB"
        elif n < 1073741824:
            return f"{n / 1048576:.1f} MB"
        else:
            return f"{n / 1073741824:.1f} GB"


# ============================================================
# FizzKubeV2Middleware — IMiddleware implementation
# ============================================================


class FizzKubeV2Middleware(IMiddleware):
    """Middleware routing FizzBuzz evaluations through the CRI-backed kubelet.

    For each evaluation, the middleware creates a PodV2 with the full CRI
    lifecycle (image pull, sandbox creation, init containers, sidecar
    injection, probe registration, volume provisioning), delegates
    evaluation to the kubelet, enriches the processing context with pod
    metadata, cleans up the pod, and returns the result.
    """

    def __init__(
        self,
        kubelet: KubeletV2,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
        enable_dashboard: bool = False,
    ) -> None:
        """Initialize the middleware.

        Args:
            kubelet: KubeletV2 instance.
            dashboard_width: ASCII dashboard width.
            enable_dashboard: Whether to enable dashboard rendering.
        """
        self._kubelet = kubelet
        self.dashboard = KubeV2Dashboard(width=dashboard_width)
        self._enable_dashboard = enable_dashboard
        self._evaluation_count = 0
        self._errors = 0

    def get_name(self) -> str:
        """Return the middleware name."""
        return "FizzKubeV2Middleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Return middleware priority (116)."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return the middleware name."""
        return "FizzKubeV2Middleware"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the CRI-backed kubelet.

        Creates a PodV2, evaluates via kubelet, injects metadata into
        context, cleans up, and returns the result.

        Args:
            context: Processing context.
            next_handler: Next middleware in the pipeline.

        Returns:
            Processed context.

        Raises:
            KubeV2MiddlewareError: If processing fails.
        """
        self._evaluation_count += 1
        number = context.number if hasattr(context, "number") else 0

        try:
            result_str, pod = self._kubelet.evaluate(number)

            # Enrich context metadata
            if hasattr(context, "metadata") and isinstance(context.metadata, dict):
                context.metadata["fizzkubev2_pod"] = pod.name
                context.metadata["fizzkubev2_sandbox"] = pod.sandbox_id
                context.metadata["fizzkubev2_phase"] = pod.phase.name
                context.metadata["fizzkubev2_init_count"] = len(pod.init_results)
                context.metadata["fizzkubev2_sidecar_count"] = len(
                    pod.sidecar_container_ids
                )
                context.metadata["fizzkubev2_result"] = result_str
                probe_summary: Dict[str, bool] = {}
                for cat in ProbeCategory:
                    status = self._kubelet.probe_runner.evaluate_status(
                        pod.main_container_id, cat
                    )
                    probe_summary[cat.value] = status.passed
                context.metadata["fizzkubev2_probe_status"] = probe_summary

            # Delegate to next handler
            return next_handler(context)

        except KubeV2Error as exc:
            self._errors += 1
            raise KubeV2MiddlewareError(number, str(exc)) from exc
        except Exception as exc:
            self._errors += 1
            raise KubeV2MiddlewareError(number, str(exc)) from exc

    def render_dashboard(self) -> str:
        """Render the KubeV2 dashboard."""
        return self.dashboard.render(self._kubelet)

    def render_pods(self) -> str:
        """Render the pod list."""
        return self.dashboard.render_pods(self._kubelet)

    def render_pod_detail(self, pod_name: str) -> str:
        """Render detailed pod view."""
        pods = self._kubelet.active_pods
        pod = pods.get(pod_name)
        if pod is None:
            return f"Pod '{pod_name}' not found"
        return self.dashboard.render_pod_detail(pod)

    def render_probes(self) -> str:
        """Render probe status."""
        return self.dashboard.render_probes(self._kubelet)

    def render_images(self) -> str:
        """Render image pull history."""
        return self.dashboard.render_images(self._kubelet)

    def render_events(self) -> str:
        """Render recent events."""
        return self.dashboard.render_events(self._kubelet)

    def render_stats(self) -> str:
        """Render aggregate statistics."""
        lines: List[str] = []
        lines.append(f"  Evaluations:       {self._evaluation_count}")
        lines.append(f"  Errors:            {self._errors}")
        lines.append(f"  Pods Created:      {self._kubelet.total_pods_created}")
        lines.append(f"  Total Restarts:    {self._kubelet.total_restarts}")
        lines.append(
            f"  Images Pulled:     {self._kubelet.image_puller.total_pulls}"
        )
        lines.append(
            f"  Probes Executed:   "
            f"{self._kubelet.probe_runner.total_probes_executed}"
        )
        return "\n".join(lines)


# ============================================================
# Factory Function
# ============================================================


def create_fizzkubev2_subsystem(
    cri_service: Any = None,
    containerd_daemon: Any = None,
    default_pull_policy: str = DEFAULT_IMAGE_PULL_POLICY,
    probe_initial_delay: float = DEFAULT_PROBE_INITIAL_DELAY,
    probe_period: float = DEFAULT_PROBE_PERIOD,
    probe_failure_threshold: int = DEFAULT_PROBE_FAILURE_THRESHOLD,
    termination_grace_period: float = DEFAULT_TERMINATION_GRACE_PERIOD,
    restart_backoff_base: float = DEFAULT_RESTART_BACKOFF_BASE,
    restart_backoff_cap: float = DEFAULT_RESTART_BACKOFF_CAP,
    restart_backoff_multiplier: float = DEFAULT_RESTART_BACKOFF_MULTIPLIER,
    inject_sidecars: bool = True,
    storage_pool_bytes: int = 10485760,
    max_init_retries: int = DEFAULT_MAX_INIT_CONTAINER_RETRIES,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    rules: Optional[list] = None,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzKubeV2 subsystem.

    Factory function that instantiates the KubeletV2 with all
    sub-managers (ImagePuller, InitContainerRunner, SidecarInjector,
    ProbeRunner, VolumeManager) and the middleware, ready for
    integration into the FizzBuzz evaluation pipeline.

    Args:
        cri_service: FizzContainerd CRI service instance.
        containerd_daemon: FizzContainerd daemon (used if cri_service not provided).
        default_pull_policy: Default image pull policy.
        probe_initial_delay: Probe initial delay seconds.
        probe_period: Probe period seconds.
        probe_failure_threshold: Consecutive failures for probe fail.
        termination_grace_period: Seconds to wait after SIGTERM.
        restart_backoff_base: Base restart backoff seconds.
        restart_backoff_cap: Maximum restart backoff seconds.
        restart_backoff_multiplier: Backoff multiplier.
        inject_sidecars: Whether to inject default sidecars.
        storage_pool_bytes: Total storage pool for volumes.
        max_init_retries: Maximum init container restart attempts.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable dashboard rendering.
        rules: FizzBuzz evaluation rules.
        event_bus: Optional event bus.

    Returns:
        Tuple of (KubeletV2, FizzKubeV2Middleware).
    """
    # Resolve CRI service
    if cri_service is None:
        if containerd_daemon is not None and hasattr(containerd_daemon, "cri_service"):
            cri_service = containerd_daemon.cri_service
        else:
            cri_service = _CRIStub()

    # Resolve pull policy
    try:
        policy = ImagePullPolicy(default_pull_policy)
    except ValueError:
        policy = ImagePullPolicy.IF_NOT_PRESENT

    # Create sub-managers
    image_puller = ImagePuller(
        cri_service=cri_service,
        default_policy=policy,
        event_bus=event_bus,
    )

    init_runner = InitContainerRunner(
        cri_service=cri_service,
        max_retries=max_init_retries,
        event_bus=event_bus,
    )

    default_sidecar_list = list(DEFAULT_SIDECARS) if inject_sidecars else []
    sidecar_injector = SidecarInjector(
        policies=[],
        default_sidecars=default_sidecar_list,
        event_bus=event_bus,
    )

    probe_runner = ProbeRunner(
        cri_service=cri_service,
        event_bus=event_bus,
    )

    volume_manager = VolumeManager(
        storage_pool_bytes=storage_pool_bytes,
        event_bus=event_bus,
    )

    # Create KubeletV2
    kubelet = KubeletV2(
        cri_service=cri_service,
        image_puller=image_puller,
        init_runner=init_runner,
        sidecar_injector=sidecar_injector,
        probe_runner=probe_runner,
        volume_manager=volume_manager,
        restart_backoff_base=restart_backoff_base,
        restart_backoff_cap=restart_backoff_cap,
        restart_backoff_multiplier=restart_backoff_multiplier,
        rules=rules,
        event_bus=event_bus,
    )

    # Create middleware
    middleware = FizzKubeV2Middleware(
        kubelet=kubelet,
        dashboard_width=dashboard_width,
        enable_dashboard=enable_dashboard,
    )

    logger.info(
        "FizzKubeV2 subsystem created (pull_policy=%s, sidecars=%s, "
        "storage=%d bytes)",
        policy.value,
        inject_sidecars,
        storage_pool_bytes,
    )

    return kubelet, middleware
