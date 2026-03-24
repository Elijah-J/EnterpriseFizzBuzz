# Implementation Plan: FizzKubeV2 -- Container-Aware Orchestrator Upgrade

**Source:** Brainstorm Report v17, Idea 4
**Target File:** `enterprise_fizzbuzz/infrastructure/fizzkubev2.py`
**Target Lines:** ~3,400
**Target Tests:** ~450 (in `tests/test_fizzkubev2.py`)

---

## 1. Module Docstring

```python
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
```

---

## 2. Imports

```python
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

from enterprise_fizzbuzz.domain.exceptions import (
    KubeV2Error,
    KubeletV2Error,
    ImagePullError as KV2ImagePullError,
    ImagePullBackOffError,
    ImageNotPresentError,
    PullSecretError,
    InitContainerFailedError,
    InitContainerTimeoutError,
    SidecarInjectionError,
    SidecarLifecycleError,
    ProbeFailedError,
    ProbeTimeoutError,
    ReadinessProbeFailedError,
    LivenessProbeFailedError,
    StartupProbeFailedError,
    VolumeProvisionError,
    VolumeMountError,
    PVCNotFoundError,
    ContainerRestartBackoffError,
    PodTerminationError,
    KubeV2MiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)
```

---

## 3. Constants (~14)

| Constant | Value | Purpose |
|----------|-------|---------|
| `KUBEV2_VERSION` | `"2.0.0"` | KubeV2 API version |
| `DEFAULT_IMAGE_PULL_POLICY` | `"IfNotPresent"` | Default image pull policy |
| `DEFAULT_TERMINATION_GRACE_PERIOD` | `30.0` | Seconds to wait after SIGTERM before SIGKILL |
| `DEFAULT_RESTART_BACKOFF_BASE` | `10.0` | Base restart backoff in seconds |
| `DEFAULT_RESTART_BACKOFF_CAP` | `300.0` | Maximum restart backoff (5 minutes) |
| `DEFAULT_RESTART_BACKOFF_MULTIPLIER` | `2.0` | Backoff multiplier per restart |
| `DEFAULT_PROBE_INITIAL_DELAY` | `0.0` | Probe initial delay seconds |
| `DEFAULT_PROBE_PERIOD` | `10.0` | Probe period seconds |
| `DEFAULT_PROBE_TIMEOUT` | `1.0` | Probe timeout seconds |
| `DEFAULT_PROBE_SUCCESS_THRESHOLD` | `1` | Consecutive successes for probe pass |
| `DEFAULT_PROBE_FAILURE_THRESHOLD` | `3` | Consecutive failures for probe fail |
| `DEFAULT_MAX_INIT_CONTAINER_RETRIES` | `3` | Max init container restart attempts |
| `DEFAULT_DASHBOARD_WIDTH` | `72` | ASCII dashboard width |
| `MIDDLEWARE_PRIORITY` | `116` | Middleware pipeline priority |

---

## 4. Enums (~8)

### 4.1 `ImagePullPolicy`

```python
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
```

### 4.2 `ProbeType`

```python
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
```

### 4.3 `ProbeResult`

```python
class ProbeResult(Enum):
    """Result of a single probe execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"
```

### 4.4 `VolumeType`

```python
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
```

### 4.5 `ContainerRestartPolicy`

```python
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
```

### 4.6 `PodPhaseV2`

```python
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
```

### 4.7 `SidecarPolicy`

```python
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
```

### 4.8 `ProbeCategory`

```python
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
```

---

## 5. Data Classes (~12)

### 5.1 `PullProgress`

```python
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
        if self.bytes_total == 0:
            return 0.0
        return (self.bytes_downloaded / self.bytes_total) * 100.0
```

### 5.2 `PullSecret`

```python
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
```

### 5.3 `InitContainerSpec`

```python
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
```

### 5.4 `InitContainerResult`

```python
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
        return self.exit_code == 0
```

### 5.5 `SidecarContainerSpec`

```python
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
```

### 5.6 `InjectionPolicy`

```python
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
```

### 5.7 `ProbeConfig`

```python
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
```

### 5.8 `ProbeStatus`

```python
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
```

### 5.9 `VolumeMount`

```python
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
```

### 5.10 `VolumeSpec`

```python
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
```

### 5.11 `PVClaim`

```python
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
```

### 5.12 `PodV2Spec`

```python
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
```

---

## 6. Class Inventory (~8 classes)

### 6.1 `ImagePuller` (~300 lines)

Manages image acquisition with policy enforcement. Integrates with FizzContainerd's image service.

**Constructor parameters:**
- `cri_service` -- reference to FizzContainerd's CRI service (or daemon)
- `default_policy: ImagePullPolicy` -- default pull policy
- `pull_timeout: float` -- maximum seconds for a single pull
- `stall_threshold: float` -- seconds without progress before marking pull stalled
- `event_bus: Optional[Any]` -- event bus for KUBEV2_IMAGE_* events

**Methods:**
- `pull(image: str, policy: ImagePullPolicy, pull_secrets: List[PullSecret]) -> PullProgress` -- Pull image according to policy. For `ALWAYS`, always issue CRI PullImage. For `IF_NOT_PRESENT`, check daemon's image service first. For `NEVER`, fail if not present.
- `is_present(image: str) -> bool` -- Check if image is in local cache.
- `_authenticate(registry: str, secrets: List[PullSecret]) -> Optional[PullSecret]` -- Resolve credentials for a registry.
- `_simulate_pull(image: str) -> PullProgress` -- Simulate image pull with progress tracking (generate synthetic layer data, compute SHA-256 digest, ingest into content store).
- `_detect_stall(progress: PullProgress) -> bool` -- Check if pull has stalled.

**Properties:** `total_pulls`, `failed_pulls`, `pull_history`.

**Events emitted:** `KUBEV2_IMAGE_PULL_STARTED`, `KUBEV2_IMAGE_PULLED`, `KUBEV2_IMAGE_PULL_FAILED`, `KUBEV2_IMAGE_PULL_STALLED`.

### 6.2 `InitContainerRunner` (~300 lines)

Executes init containers sequentially before application containers start.

**Constructor parameters:**
- `cri_service` -- CRI service reference
- `max_retries: int` -- max restart attempts per init container
- `event_bus: Optional[Any]`

**Methods:**
- `run_all(sandbox_id: str, init_specs: List[InitContainerSpec], restart_policy: ContainerRestartPolicy) -> List[InitContainerResult]` -- Execute all init containers in order. Each must exit 0 before the next starts. On failure, apply restart policy up to `max_retries`. If all retries exhausted and policy is `NEVER`, raise `InitContainerFailedError`.
- `_run_one(sandbox_id: str, spec: InitContainerSpec) -> InitContainerResult` -- Create container via CRI `CreateContainer`, start via `StartContainer`, wait for exit, collect logs.
- `_wait_for_completion(container_id: str, timeout: float) -> int` -- Poll CRI `ContainerStatus` until exit code is available or timeout expires.

**Properties:** `total_runs`, `total_failures`, `run_history`.

**Events emitted:** `KUBEV2_INIT_STARTED`, `KUBEV2_INIT_COMPLETED`, `KUBEV2_INIT_FAILED`.

### 6.3 `SidecarInjector` (~300 lines)

Inspects pod specs and injects sidecar containers based on injection policies.

**Constructor parameters:**
- `policies: List[InjectionPolicy]` -- registered injection policies
- `default_sidecars: List[SidecarContainerSpec]` -- default sidecars injected into all pods unless opted out
- `event_bus: Optional[Any]`

**Methods:**
- `inject(pod_spec: PodV2Spec) -> Tuple[List[SidecarContainerSpec], List[VolumeSpec], List[InitContainerSpec]]` -- Determine which sidecars to inject based on pod labels, namespace, and annotations. Returns injected sidecar specs, additional volumes, and additional init containers. Respects `fizzbuzz.io/inject-sidecars: "false"` opt-out annotation.
- `_matches_policy(pod_spec: PodV2Spec, policy: InjectionPolicy) -> bool` -- Check if a pod matches a policy's label/namespace selectors.
- `_resolve_sidecar_policy(pod_spec: PodV2Spec) -> SidecarPolicy` -- Determine injection policy from pod annotations.
- `add_policy(policy: InjectionPolicy) -> None` -- Register a new injection policy.
- `remove_policy(name: str) -> None` -- Remove a policy by name.

**Properties:** `total_injections`, `active_policies`, `injection_history`.

**Events emitted:** `KUBEV2_SIDECAR_INJECTED`, `KUBEV2_SIDECAR_SKIPPED`.

**Default sidecars (4):**
1. `fizzbuzz-sidecar-log` -- logging sidecar
2. `fizzbuzz-sidecar-metrics` -- metrics sidecar
3. `fizzbuzz-sidecar-trace` -- tracing sidecar
4. `fizzbuzz-sidecar-proxy` -- network proxy sidecar

### 6.4 `ProbeRunner` (~400 lines)

Executes readiness, liveness, and startup probes for all containers in a pod.

**Constructor parameters:**
- `cri_service` -- CRI service reference
- `event_bus: Optional[Any]`

**Methods:**
- `register_probe(container_id: str, config: ProbeConfig) -> None` -- Register a probe for a container.
- `execute_probe(container_id: str, category: ProbeCategory) -> ProbeResult` -- Execute a single probe. Dispatches to type-specific handler.
- `execute_all(container_id: str) -> Dict[ProbeCategory, ProbeResult]` -- Execute all registered probes for a container.
- `evaluate_status(container_id: str, category: ProbeCategory) -> ProbeStatus` -- Get current probe status with threshold evaluation.
- `_probe_http(container_id: str, config: ProbeConfig) -> ProbeResult` -- Execute HTTP GET probe. Simulate HTTP request to container port/path. 2xx = success.
- `_probe_tcp(container_id: str, config: ProbeConfig) -> ProbeResult` -- Execute TCP socket probe. Simulate TCP connection to container port. Connection = success.
- `_probe_exec(container_id: str, config: ProbeConfig) -> ProbeResult` -- Execute command probe via CRI exec. Exit code 0 = success.
- `is_ready(container_id: str) -> bool` -- Check if container passes readiness probe.
- `is_alive(container_id: str) -> bool` -- Check if container passes liveness probe.
- `has_started(container_id: str) -> bool` -- Check if container passes startup probe.
- `clear(container_id: str) -> None` -- Remove all probes for a container.

**Properties:** `total_probes_executed`, `probe_statuses`.

**Events emitted:** `KUBEV2_PROBE_EXECUTED`, `KUBEV2_PROBE_SUCCEEDED`, `KUBEV2_PROBE_FAILED`, `KUBEV2_READINESS_CHANGED`, `KUBEV2_LIVENESS_FAILED`.

### 6.5 `VolumeManager` (~350 lines)

Provisions and manages volumes for containers.

**Constructor parameters:**
- `storage_pool_bytes: int` -- total storage pool for PVC provisioning
- `event_bus: Optional[Any]`

**Methods:**
- `provision_volumes(volumes: List[VolumeSpec]) -> Dict[str, str]` -- Provision all volumes for a pod. Returns mapping of volume name to volume ID.
- `mount_volumes(container_id: str, volume_mounts: List[VolumeMount], provisioned: Dict[str, str]) -> None` -- Mount provisioned volumes into a container.
- `cleanup_volumes(volume_ids: List[str], preserve_pvcs: bool = True) -> int` -- Clean up volumes. Delete emptyDir/configMap/secret volumes. Preserve PVC volumes unless explicitly requested.
- `_provision_empty_dir(spec: VolumeSpec) -> str` -- Create an ephemeral overlay layer.
- `_provision_pvc(spec: VolumeSpec) -> str` -- Bind a PVC to a persistent overlay layer. Raise `PVCNotFoundError` if claim does not exist.
- `_provision_config_map(spec: VolumeSpec) -> str` -- Project ConfigMap key-value data as files.
- `_provision_secret(spec: VolumeSpec) -> str` -- Project Secret data as files in tmpfs.
- `create_pvc(claim: PVClaim) -> str` -- Create a new PVC.
- `delete_pvc(name: str) -> None` -- Delete a PVC and release storage.
- `list_pvcs() -> List[PVClaim]` -- List all PVCs.

**Properties:** `total_provisioned`, `active_volumes`, `storage_used_bytes`, `storage_available_bytes`.

**Events emitted:** `KUBEV2_VOLUME_PROVISIONED`, `KUBEV2_VOLUME_MOUNTED`, `KUBEV2_VOLUME_CLEANED`, `KUBEV2_PVC_BOUND`.

### 6.6 `KubeletV2` (~500 lines)

The CRI-integrated kubelet. The central class. Orchestrates the full pod lifecycle through the container runtime stack.

**Constructor parameters:**
- `cri_service` -- FizzContainerd CRI service (or daemon instance)
- `image_puller: ImagePuller`
- `init_runner: InitContainerRunner`
- `sidecar_injector: SidecarInjector`
- `probe_runner: ProbeRunner`
- `volume_manager: VolumeManager`
- `restart_backoff_base: float`
- `restart_backoff_cap: float`
- `restart_backoff_multiplier: float`
- `rules: Optional[List[Dict]]` -- FizzBuzz evaluation rules
- `event_bus: Optional[Any]`

**Methods:**
- `create_pod(spec: PodV2Spec) -> PodV2` -- Full pod creation lifecycle:
  1. Set phase to `IMAGE_PULLING`. Pull all images (main + init + sidecar) via ImagePuller.
  2. Create pod sandbox via CRI `RunPodSandbox`.
  3. Provision volumes via VolumeManager.
  4. Set phase to `INIT_RUNNING`. Run init containers via InitContainerRunner.
  5. Inject sidecars via SidecarInjector. Create and start sidecar containers via CRI.
  6. Wait for sidecar readiness probes.
  7. Set phase to `CONTAINER_CREATING`. Create and start main container via CRI.
  8. Register probes with ProbeRunner.
  9. Set phase to `RUNNING`. Begin probe execution.
  10. Return PodV2 object.
- `evaluate(number: int, spec: Optional[PodV2Spec] = None) -> Tuple[str, PodV2]` -- Create a pod, evaluate FizzBuzz for the number, complete the pod.
- `terminate_pod(pod: PodV2) -> None` -- Graceful pod termination:
  1. Set phase to `TERMINATING`.
  2. Send SIGTERM to main container via CRI.
  3. Wait `termination_grace_period` seconds.
  4. Send SIGKILL to any remaining containers.
  5. Stop and remove sidecar containers.
  6. Remove pod sandbox via CRI `StopPodSandbox` + `RemovePodSandbox`.
  7. Clean up volumes.
  8. Set phase to `SUCCEEDED` or `FAILED`.
- `restart_container(pod: PodV2, container_id: str, restart_count: int) -> None` -- Restart a container with exponential backoff: `min(base * multiplier^count, cap)`.
- `_evaluate_fizzbuzz(number: int) -> str` -- Apply configured rules to evaluate the number. Same logic as FizzKubeControlPlane.
- `get_pod_status(pod: PodV2) -> Dict[str, Any]` -- Detailed pod status including all containers, init containers, sidecars, probes, volumes.

**Properties:** `total_pods_created`, `active_pods`, `total_restarts`, `restart_history`.

**Events emitted:** `KUBEV2_POD_CREATED`, `KUBEV2_POD_SCHEDULED`, `KUBEV2_POD_RUNNING`, `KUBEV2_POD_SUCCEEDED`, `KUBEV2_POD_FAILED`, `KUBEV2_POD_TERMINATING`, `KUBEV2_CONTAINER_STARTED`, `KUBEV2_CONTAINER_RESTARTED`.

### 6.7 `KubeV2Dashboard` (~200 lines)

ASCII dashboard for FizzKubeV2 state visualization.

**Constructor parameters:**
- `width: int` -- dashboard width

**Methods:**
- `render(kubelet: KubeletV2) -> str` -- Full dashboard: pod inventory, container status, probe results, volume status, image pull history, restart events.
- `render_pods(kubelet: KubeletV2) -> str` -- Pod list with phases and container counts.
- `render_pod_detail(pod: PodV2) -> str` -- Detailed pod view: init containers, sidecars, probes, volumes, events.
- `render_probes(kubelet: KubeletV2) -> str` -- Probe status for all containers.
- `render_images(kubelet: KubeletV2) -> str` -- Image pull history.
- `render_events(kubelet: KubeletV2) -> str` -- Recent kubelet events.
- `_center(text: str) -> str` -- Center text within width.
- `_format_bytes(n: int) -> str` -- Format bytes with units.

### 6.8 `FizzKubeV2Middleware` (~200 lines)

IMiddleware implementation routing FizzBuzz evaluations through the CRI-backed kubelet.

**Constructor parameters:**
- `kubelet: KubeletV2`
- `dashboard_width: int`
- `enable_dashboard: bool`

**IMiddleware interface:**
- `get_name() -> str` -- Returns `"FizzKubeV2Middleware"`.
- `get_priority() -> int` -- Returns `MIDDLEWARE_PRIORITY` (116).
- `process(context, next_handler) -> ProcessingContext` -- Create a PodV2, evaluate via kubelet, inject metadata into context, return result or delegate to next handler.
- `name` property -- `"FizzKubeV2Middleware"`.
- `priority` property -- `MIDDLEWARE_PRIORITY`.

**Additional methods:**
- `render_dashboard() -> str`
- `render_pods() -> str`
- `render_pod_detail(pod_name: str) -> str`
- `render_probes() -> str`
- `render_images() -> str`
- `render_events() -> str`
- `render_stats() -> str`

---

## 7. PodV2 Dataclass

```python
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
```

---

## 8. Exception Classes (~20, prefix EFP-KV2)

Add to `enterprise_fizzbuzz/domain/exceptions.py` in a new section:

```
# ============================================================
# FizzKubeV2 Container-Aware Orchestrator Exceptions
# ============================================================
# FizzKube's kubelet has been creating "containers" that are
# Python dataclasses since Round 5.  FizzKubeV2 connects the
# orchestrator to FizzContainerd's CRI service, which means
# the kubelet now has 20 new and exciting ways to fail.  Image
# pulls can stall.  Init containers can refuse to exit.  Sidecar
# injection policies can conflict.  Readiness probes can lie.
# Liveness probes can kill healthy containers.  Volumes can fail
# to provision.  Containers can enter restart backoff loops.
# Graceful termination can be neither graceful nor terminal.
# These exceptions document every failure mode with the solemnity
# of a post-incident review.
# ============================================================
```

| # | Class | Code | Inherits | Constructor Signature | Purpose |
|---|-------|------|----------|----------------------|---------|
| 1 | `KubeV2Error` | `EFP-KV200` | `FizzBuzzError` | `(message, *, error_code="EFP-KV200", context=None)` | Base exception for all FizzKubeV2 errors |
| 2 | `KubeletV2Error` | `EFP-KV201` | `KubeV2Error` | `(reason)` | General kubelet lifecycle failure |
| 3 | `KV2ImagePullError` | `EFP-KV202` | `KubeV2Error` | `(image, policy, reason)` | Image pull failed |
| 4 | `ImagePullBackOffError` | `EFP-KV203` | `KubeV2Error` | `(image, attempt, backoff_seconds)` | Image pull in exponential backoff |
| 5 | `ImageNotPresentError` | `EFP-KV204` | `KubeV2Error` | `(image)` | Image not found locally with policy Never |
| 6 | `PullSecretError` | `EFP-KV205` | `KubeV2Error` | `(secret_name, registry, reason)` | Pull secret retrieval or auth failed |
| 7 | `InitContainerFailedError` | `EFP-KV206` | `KubeV2Error` | `(init_name, exit_code, pod_name)` | Init container exited non-zero |
| 8 | `InitContainerTimeoutError` | `EFP-KV207` | `KubeV2Error` | `(init_name, timeout_seconds)` | Init container exceeded timeout |
| 9 | `SidecarInjectionError` | `EFP-KV208` | `KubeV2Error` | `(pod_name, sidecar_name, reason)` | Sidecar injection failed |
| 10 | `SidecarLifecycleError` | `EFP-KV209` | `KubeV2Error` | `(sidecar_name, expected_state, actual_state)` | Sidecar lifecycle ordering violation |
| 11 | `ProbeFailedError` | `EFP-KV210` | `KubeV2Error` | `(container_id, probe_category, probe_type, reason)` | Generic probe failure |
| 12 | `ProbeTimeoutError` | `EFP-KV211` | `KubeV2Error` | `(container_id, probe_category, timeout_seconds)` | Probe execution timed out |
| 13 | `ReadinessProbeFailedError` | `EFP-KV212` | `ProbeFailedError` | `(container_id, consecutive_failures, threshold)` | Readiness threshold breached |
| 14 | `LivenessProbeFailedError` | `EFP-KV213` | `ProbeFailedError` | `(container_id, consecutive_failures, threshold)` | Liveness threshold breached, container will restart |
| 15 | `StartupProbeFailedError` | `EFP-KV214` | `ProbeFailedError` | `(container_id, elapsed_seconds)` | Startup probe never succeeded |
| 16 | `VolumeProvisionError` | `EFP-KV215` | `KubeV2Error` | `(volume_name, volume_type, reason)` | Volume provisioning failed |
| 17 | `VolumeMountError` | `EFP-KV216` | `KubeV2Error` | `(volume_name, container_id, mount_path, reason)` | Volume mount into container failed |
| 18 | `PVCNotFoundError` | `EFP-KV217` | `KubeV2Error` | `(claim_name)` | PersistentVolumeClaim not found |
| 19 | `ContainerRestartBackoffError` | `EFP-KV218` | `KubeV2Error` | `(container_id, restart_count, backoff_seconds)` | Container in restart backoff, not eligible for restart yet |
| 20 | `PodTerminationError` | `EFP-KV219` | `KubeV2Error` | `(pod_name, reason)` | Graceful pod termination failed |
| 21 | `KubeV2MiddlewareError` | `EFP-KV220` | `KubeV2Error` | `(evaluation_number, reason)` | Middleware processing failed |

Each exception follows the codebase pattern: `super().__init__(descriptive_message, error_code="EFP-KV2##", context={...})` with deadpan docstrings.

---

## 9. EventType Entries (~15)

Add to `enterprise_fizzbuzz/domain/models.py` in the `EventType` enum:

```python
    # FizzKubeV2 Container-Aware Orchestrator events
    KUBEV2_POD_CREATED = auto()
    KUBEV2_POD_SCHEDULED = auto()
    KUBEV2_POD_RUNNING = auto()
    KUBEV2_POD_SUCCEEDED = auto()
    KUBEV2_POD_FAILED = auto()
    KUBEV2_POD_TERMINATING = auto()
    KUBEV2_IMAGE_PULL_STARTED = auto()
    KUBEV2_IMAGE_PULLED = auto()
    KUBEV2_IMAGE_PULL_FAILED = auto()
    KUBEV2_IMAGE_PULL_STALLED = auto()
    KUBEV2_INIT_STARTED = auto()
    KUBEV2_INIT_COMPLETED = auto()
    KUBEV2_INIT_FAILED = auto()
    KUBEV2_SIDECAR_INJECTED = auto()
    KUBEV2_SIDECAR_SKIPPED = auto()
    KUBEV2_PROBE_EXECUTED = auto()
    KUBEV2_PROBE_SUCCEEDED = auto()
    KUBEV2_PROBE_FAILED = auto()
    KUBEV2_READINESS_CHANGED = auto()
    KUBEV2_LIVENESS_FAILED = auto()
    KUBEV2_VOLUME_PROVISIONED = auto()
    KUBEV2_VOLUME_MOUNTED = auto()
    KUBEV2_VOLUME_CLEANED = auto()
    KUBEV2_PVC_BOUND = auto()
    KUBEV2_CONTAINER_STARTED = auto()
    KUBEV2_CONTAINER_RESTARTED = auto()
    KUBEV2_DASHBOARD_RENDERED = auto()
```

---

## 10. Config Properties (~12)

Add to `enterprise_fizzbuzz/infrastructure/configuration.py` in `ConfigurationManager`:

| Property | YAML Key | Type | Default | CLI Override |
|----------|----------|------|---------|-------------|
| `fizzkubev2_enabled` | `fizzkubev2.enabled` | `bool` | `False` | `--fizzkubev2` |
| `fizzkubev2_default_pull_policy` | `fizzkubev2.default_pull_policy` | `str` | `"IfNotPresent"` | `--fizzkubev2-pull-policy` |
| `fizzkubev2_probe_initial_delay` | `fizzkubev2.probe_initial_delay` | `float` | `0.0` | n/a |
| `fizzkubev2_probe_period` | `fizzkubev2.probe_period` | `float` | `10.0` | n/a |
| `fizzkubev2_probe_failure_threshold` | `fizzkubev2.probe_failure_threshold` | `int` | `3` | n/a |
| `fizzkubev2_termination_grace_period` | `fizzkubev2.termination_grace_period` | `float` | `30.0` | n/a |
| `fizzkubev2_restart_backoff_base` | `fizzkubev2.restart_backoff_base` | `float` | `10.0` | n/a |
| `fizzkubev2_restart_backoff_cap` | `fizzkubev2.restart_backoff_cap` | `float` | `300.0` | n/a |
| `fizzkubev2_inject_sidecars` | `fizzkubev2.inject_sidecars` | `bool` | `True` | `--fizzkubev2-no-sidecars` |
| `fizzkubev2_storage_pool_bytes` | `fizzkubev2.storage_pool_bytes` | `int` | `10485760` | n/a |
| `fizzkubev2_max_init_retries` | `fizzkubev2.max_init_retries` | `int` | `3` | n/a |
| `fizzkubev2_dashboard_width` | `fizzkubev2.dashboard_width` | `int` | `72` | n/a |

---

## 11. YAML Config Section

Add to `config.yaml`:

```yaml
fizzkubev2:
  enabled: false
  default_pull_policy: "IfNotPresent"
  probe_initial_delay: 0.0
  probe_period: 10.0
  probe_failure_threshold: 3
  termination_grace_period: 30.0
  restart_backoff_base: 10.0
  restart_backoff_cap: 300.0
  inject_sidecars: true
  storage_pool_bytes: 10485760
  max_init_retries: 3
  dashboard_width: 72
```

---

## 12. CLI Flags (~8)

Add to `enterprise_fizzbuzz/__main__.py`:

| Flag | Type | Description |
|------|------|-------------|
| `--fizzkubev2` | `store_true` | Enable FizzKubeV2 CRI-integrated orchestrator |
| `--fizzkubev2-pods` | `store_true` | List pods with container status, init results, sidecar info |
| `--fizzkubev2-describe-pod` | `str` | Show detailed pod status (init containers, sidecars, probes, volumes) |
| `--fizzkubev2-logs` | `str` (nargs=2) | Stream container logs: `<pod> <container>` |
| `--fizzkubev2-exec` | `str` (nargs=3) | Exec into a container: `<pod> <container> <command>` |
| `--fizzkubev2-images` | `store_true` | List images with pull status and progress |
| `--fizzkubev2-events` | `store_true` | List recent kubelet events |
| `--fizzkubev2-probe-status` | `str` | Show probe results for all containers in a pod |

---

## 13. Middleware Integration

**Class:** `FizzKubeV2Middleware`
**Priority:** 116
**Pipeline behavior:** For each evaluation, the middleware creates a PodV2 with full CRI lifecycle (image pull, sandbox creation, init containers, sidecar injection, probe registration, volume provisioning), delegates evaluation to the kubelet, enriches the processing context with pod metadata (`fizzkubev2_pod`, `fizzkubev2_sandbox`, `fizzkubev2_phase`, `fizzkubev2_init_count`, `fizzkubev2_sidecar_count`, `fizzkubev2_probe_status`), cleans up the pod, and returns the result. On error, best-effort cleanup is performed and `KubeV2MiddlewareError` is raised.

---

## 14. Factory Function

```python
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
        ... (all parameters documented)

    Returns:
        Tuple of (KubeletV2, FizzKubeV2Middleware).
    """
```

The factory:
1. Resolves CRI service from `cri_service` or `containerd_daemon.cri_service`.
2. Creates `ImagePuller(cri_service, policy, event_bus)`.
3. Creates `InitContainerRunner(cri_service, max_retries, event_bus)`.
4. Creates `SidecarInjector(policies=[], default_sidecars=DEFAULT_SIDECARS if inject_sidecars else [], event_bus)`.
5. Creates `ProbeRunner(cri_service, event_bus)`.
6. Creates `VolumeManager(storage_pool_bytes, event_bus)`.
7. Creates `KubeletV2(cri_service, image_puller, init_runner, sidecar_injector, probe_runner, volume_manager, ..., rules, event_bus)`.
8. Creates `FizzKubeV2Middleware(kubelet, dashboard_width, enable_dashboard)`.
9. Returns `(kubelet, middleware)`.

---

## 15. Re-export Stub

Create `fizzkubev2.py` at repository root:

```python
"""Re-export stub for backward compatibility.

Provides top-level access to the FizzKubeV2 Container-Aware Orchestrator
Upgrade module.
"""

from enterprise_fizzbuzz.infrastructure.fizzkubev2 import (  # noqa: F401
    ContainerRestartPolicy,
    FizzKubeV2Middleware,
    ImagePullPolicy,
    ImagePuller,
    InjectionPolicy,
    InitContainerResult,
    InitContainerRunner,
    InitContainerSpec,
    KubeV2Dashboard,
    KubeletV2,
    PodPhaseV2,
    PodV2,
    PodV2Spec,
    ProbeCategory,
    ProbeConfig,
    ProbeResult,
    ProbeRunner,
    ProbeStatus,
    ProbeType,
    PullProgress,
    PullSecret,
    PVClaim,
    SidecarContainerSpec,
    SidecarInjector,
    SidecarPolicy,
    VolumeManager,
    VolumeMount,
    VolumeSpec,
    VolumeType,
    create_fizzkubev2_subsystem,
)
```

---

## 16. Test Classes (~450 tests in `tests/test_fizzkubev2.py`)

| Test Class | Test Count | Focus |
|------------|-----------|-------|
| `TestImagePullPolicy` | ~15 | Enum values, string conversion |
| `TestProbeType` | ~8 | Enum values |
| `TestProbeResult` | ~8 | Enum values |
| `TestVolumeType` | ~8 | Enum values |
| `TestContainerRestartPolicy` | ~8 | Enum values |
| `TestPodPhaseV2` | ~12 | Extended phases, transitions |
| `TestSidecarPolicy` | ~6 | Enum values |
| `TestProbeCategory` | ~6 | Enum values |
| `TestPullProgress` | ~10 | Progress tracking, percent calc, stall detection |
| `TestPullSecret` | ~6 | Secret creation, field defaults |
| `TestInitContainerSpec` | ~8 | Spec creation, field defaults |
| `TestInitContainerResult` | ~10 | Result creation, succeeded property |
| `TestSidecarContainerSpec` | ~6 | Spec creation |
| `TestInjectionPolicy` | ~8 | Policy creation, selector matching |
| `TestProbeConfig` | ~10 | Config creation, defaults, all probe types |
| `TestProbeStatus` | ~8 | Status tracking, threshold evaluation |
| `TestVolumeMount` | ~6 | Mount creation, defaults |
| `TestVolumeSpec` | ~8 | Spec creation, all volume types |
| `TestPVClaim` | ~8 | Claim creation, binding |
| `TestPodV2Spec` | ~12 | Spec creation, all fields |
| `TestPodV2` | ~15 | Pod creation, auto-name, lifecycle |
| `TestImagePuller` | ~30 | Always/IfNotPresent/Never policies, pull secrets, progress, stall detection, errors |
| `TestInitContainerRunner` | ~25 | Sequential execution, failure handling, restart policy, timeout |
| `TestSidecarInjector` | ~25 | Injection policies, label matching, namespace matching, opt-out, default sidecars |
| `TestProbeRunner` | ~35 | HTTP/TCP/exec probes, readiness/liveness/startup, thresholds, timeout |
| `TestVolumeManager` | ~30 | emptyDir/PVC/configMap/secret provisioning, mount, cleanup, PVC lifecycle |
| `TestKubeletV2` | ~45 | Full pod lifecycle, CRI integration, termination, restart backoff, evaluate |
| `TestKubeV2Dashboard` | ~15 | Dashboard rendering, pod detail, probes, images, events |
| `TestFizzKubeV2Middleware` | ~20 | Middleware process, priority, name, error handling, context enrichment |
| `TestCreateFizzKubeV2Subsystem` | ~12 | Factory wiring, default params, custom params |
| `TestKubeV2Exceptions` | ~21 | All 21 exception classes: error codes, messages, context |

**Total: ~450 tests**

Each test file includes:
- `@pytest.fixture` for `SingletonMeta.reset()` (if needed)
- No `conftest.py` dependency
- Per-test setup of CRI mocks (lightweight stub objects mimicking FizzContainerd's CRI service)

---

## 17. Implementation Sequence

1. **Exceptions** -- Add the 21 exception classes to `domain/exceptions.py`.
2. **EventTypes** -- Add the 27 event type entries to `domain/models.py`.
3. **Main module** -- Create `enterprise_fizzbuzz/infrastructure/fizzkubev2.py`:
   a. Module docstring, imports, constants
   b. Enums (8)
   c. Data classes (12 + PodV2)
   d. `ImagePuller`
   e. `InitContainerRunner`
   f. `SidecarInjector`
   g. `ProbeRunner`
   h. `VolumeManager`
   i. `KubeletV2`
   j. `KubeV2Dashboard`
   k. `FizzKubeV2Middleware`
   l. Factory function
4. **Config** -- Add properties to `ConfigurationManager`, YAML section to `config.yaml`.
5. **CLI** -- Add flags to `__main__.py`.
6. **Re-export** -- Create root `fizzkubev2.py`.
7. **Tests** -- Create `tests/test_fizzkubev2.py`.

---

## 18. Wiring in `__main__.py`

```python
if config.fizzkubev2_enabled:
    from enterprise_fizzbuzz.infrastructure.fizzkubev2 import create_fizzkubev2_subsystem

    kubelet_v2, kubev2_middleware = create_fizzkubev2_subsystem(
        containerd_daemon=containerd_daemon,  # from fizzcontainerd wiring
        default_pull_policy=config.fizzkubev2_default_pull_policy,
        probe_initial_delay=config.fizzkubev2_probe_initial_delay,
        probe_period=config.fizzkubev2_probe_period,
        probe_failure_threshold=config.fizzkubev2_probe_failure_threshold,
        termination_grace_period=config.fizzkubev2_termination_grace_period,
        restart_backoff_base=config.fizzkubev2_restart_backoff_base,
        restart_backoff_cap=config.fizzkubev2_restart_backoff_cap,
        inject_sidecars=config.fizzkubev2_inject_sidecars,
        storage_pool_bytes=config.fizzkubev2_storage_pool_bytes,
        max_init_retries=config.fizzkubev2_max_init_retries,
        dashboard_width=config.fizzkubev2_dashboard_width,
        enable_dashboard=args.fizzkubev2_pods or args.fizzkubev2_describe_pod,
        rules=rules,
        event_bus=event_bus,
    )
    builder.add_middleware(kubev2_middleware)

    # CLI output handlers
    if args.fizzkubev2_pods:
        print(kubev2_middleware.render_pods())
    if args.fizzkubev2_describe_pod:
        print(kubev2_middleware.render_pod_detail(args.fizzkubev2_describe_pod))
    if args.fizzkubev2_images:
        print(kubev2_middleware.render_images())
    if args.fizzkubev2_events:
        print(kubev2_middleware.render_events())
    if args.fizzkubev2_probe_status:
        print(kubev2_middleware.render_probes())
```

---

## 19. Line Budget

| Section | Estimated Lines |
|---------|----------------|
| Module docstring + imports | ~50 |
| Constants | ~40 |
| Enums (8) | ~120 |
| Data classes (13 including PodV2) | ~350 |
| `ImagePuller` | ~300 |
| `InitContainerRunner` | ~300 |
| `SidecarInjector` | ~300 |
| `ProbeRunner` | ~400 |
| `VolumeManager` | ~350 |
| `KubeletV2` | ~500 |
| `KubeV2Dashboard` | ~200 |
| `FizzKubeV2Middleware` | ~200 |
| Factory function | ~90 |
| **Total** | **~3,200-3,400** |
| Exceptions (in exceptions.py) | ~300 |
| EventTypes (in models.py) | ~30 |
| Tests | ~1,200 |
