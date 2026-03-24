# Implementation Plan: FizzContainerChaos -- Container-Native Chaos Engineering

**Module**: `enterprise_fizzbuzz/infrastructure/fizzcontainerchaos.py`
**Target Size**: ~2,800 lines
**Tests**: `tests/test_fizzcontainerchaos.py` (~400 lines, ~85 tests)
**Re-export Stub**: `fizzcontainerchaos.py` (root)
**Middleware Priority**: 117

---

## 1. Module Docstring

```
Enterprise FizzBuzz Platform - FizzContainerChaos: Container-Native Chaos Engineering

A container-infrastructure-level chaos engineering system inspired by Chaos
Mesh and LitmusChaos, providing fault injection at the namespace, cgroup,
overlay, CNI, and container runtime layers.  Eight fault injection types
target the container stack: container kill, network partition, CPU stress,
memory pressure, disk fill, image pull failure, DNS failure, and network
latency.  A game day orchestrator composes multiple fault injections into
coordinated chaos scenarios with defined hypotheses, steady-state metrics,
blast radius limits, and automatic abort conditions.

The platform's existing chaos engineering subsystem (chaos.py) targets the
application layer -- rule failures, middleware timeouts, cache corruption.
FizzContainerChaos targets the infrastructure layer: containers dying,
networks partitioning, resources exhausting, images failing to pull, DNS
failing to resolve.  These are the failures that cause real production
outages.  AWS's 2017 S3 outage was caused by a process restart.
Cloudflare's 2019 outage was caused by CPU exhaustion.  Google's 2020
outage was caused by quota exhaustion.  Infrastructure failures cascade
differently than application failures, and testing them requires fault
injection at the infrastructure layer.

FizzBob cognitive load gating prevents chaos experiments from running when
the operator's NASA-TLX score exceeds the chaos threshold, because
injecting container-level faults while the sole operator is already
cognitively saturated would be reckless even by chaos engineering standards.

Architecture references: Chaos Mesh (https://chaos-mesh.org/),
LitmusChaos (https://litmuschaos.io/), Netflix Chaos Monkey
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
import statistics
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from enterprise_fizzbuzz.domain.exceptions import (
    ContainerChaosError,
    ChaosExperimentNotFoundError,
    ChaosExperimentAlreadyRunningError,
    ChaosExperimentAbortedError,
    ChaosExperimentFailedStartError,
    ChaosFaultInjectionError,
    ChaosFaultRemovalError,
    ChaosContainerKillError,
    ChaosNetworkPartitionError,
    ChaosCPUStressError,
    ChaosMemoryPressureError,
    ChaosDiskFillError,
    ChaosImagePullFailureError,
    ChaosDNSFailureError,
    ChaosNetworkLatencyError,
    ChaosGameDayError,
    ChaosGameDayAbortError,
    ChaosBlastRadiusExceededError,
    ChaosSteadyStateViolationError,
    ChaosCognitiveLoadGateError,
    ChaosScheduleError,
    ChaosReportGenerationError,
    ChaosTargetResolutionError,
    ChaosContainerChaosMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzcontainerchaos")
```

---

## 3. Constants (~14)

```python
CONTAINER_CHAOS_VERSION = "1.0.0"
"""FizzContainerChaos subsystem version."""

CHAOS_MESH_COMPAT_VERSION = "2.6"
"""Chaos Mesh compatibility version this implementation follows."""

DEFAULT_EXPERIMENT_TIMEOUT = 300.0
"""Default experiment timeout in seconds (5 minutes)."""

DEFAULT_OBSERVATION_INTERVAL = 5.0
"""Interval between abort condition checks during fault injection (seconds)."""

DEFAULT_COGNITIVE_LOAD_THRESHOLD = 60.0
"""NASA-TLX threshold below which chaos experiments are permitted."""

DEFAULT_BLAST_RADIUS_LIMIT = 0.50
"""Maximum fraction of containers that may be affected simultaneously."""

DEFAULT_STEADY_STATE_TOLERANCE = 0.15
"""Tolerance band for steady-state metric comparison (15%)."""

DEFAULT_GAMEDAY_TIMEOUT = 1800.0
"""Default game day timeout in seconds (30 minutes)."""

DEFAULT_LATENCY_MS = 200.0
"""Default network latency injection in milliseconds."""

DEFAULT_JITTER_MS = 50.0
"""Default network latency jitter in milliseconds."""

DEFAULT_CPU_STRESS_CORES = 2
"""Default number of CPU cores to stress."""

DEFAULT_MEMORY_PRESSURE_RATE = 1048576
"""Default memory allocation rate in bytes per second (1 MB/s)."""

DEFAULT_DISK_FILL_PERCENT = 90.0
"""Default overlay writable layer fill percentage."""

MIDDLEWARE_PRIORITY = 117
"""Middleware pipeline priority for FizzContainerChaos."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""
```

---

## 4. Enums (~6)

### 4.1 FaultType

```python
class FaultType(Enum):
    """Container-infrastructure fault injection types.

    Each fault type targets a specific layer of the container stack.
    Together they cover the eight most operationally impactful
    container failure modes identified by post-incident reviews
    across major cloud providers.
    """

    CONTAINER_KILL = "container_kill"
    NETWORK_PARTITION = "network_partition"
    CPU_STRESS = "cpu_stress"
    MEMORY_PRESSURE = "memory_pressure"
    DISK_FILL = "disk_fill"
    IMAGE_PULL_FAILURE = "image_pull_failure"
    DNS_FAILURE = "dns_failure"
    NETWORK_LATENCY = "network_latency"
```

### 4.2 ExperimentStatus

```python
class ExperimentStatus(Enum):
    """Lifecycle status of a chaos experiment.

    Experiments transition through these states during execution.
    PENDING -> RUNNING -> COMPLETED | ABORTED | FAILED.
    """

    PENDING = "pending"
    PRE_CHECK = "pre_check"
    MEASURING_BASELINE = "measuring_baseline"
    INJECTING = "injecting"
    OBSERVING = "observing"
    REMOVING_FAULT = "removing_fault"
    MEASURING_RECOVERY = "measuring_recovery"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"
```

### 4.3 GameDayStatus

```python
class GameDayStatus(Enum):
    """Lifecycle status of a game day exercise.

    Game days coordinate multiple experiments with a shared
    narrative and system-level hypothesis.
    """

    PLANNING = "planning"
    PRE_FLIGHT = "pre_flight"
    EXECUTING = "executing"
    COOLDOWN = "cooldown"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"
```

### 4.4 AbortReason

```python
class AbortReason(Enum):
    """Reason why a chaos experiment or game day was aborted.

    Automatic abort protects the platform from cascading failures
    when chaos injection exceeds safe operational boundaries.
    """

    STEADY_STATE_VIOLATION = "steady_state_violation"
    BLAST_RADIUS_EXCEEDED = "blast_radius_exceeded"
    COGNITIVE_LOAD_EXCEEDED = "cognitive_load_exceeded"
    TIMEOUT_EXPIRED = "timeout_expired"
    MANUAL_ABORT = "manual_abort"
    TARGET_UNHEALTHY = "target_unhealthy"
    CASCADING_FAILURE_DETECTED = "cascading_failure_detected"
    EMERGENCY_SHUTDOWN = "emergency_shutdown"
```

### 4.5 BlastRadiusScope

```python
class BlastRadiusScope(Enum):
    """Scope for blast radius calculation.

    Determines which container set is used as the denominator
    when computing the fraction of affected containers.
    """

    GLOBAL = "global"
    SERVICE_GROUP = "service_group"
    NAMESPACE = "namespace"
    POD = "pod"
```

### 4.6 ScheduleMode

```python
class ScheduleMode(Enum):
    """Scheduling mode for experiments within a game day.

    Controls how multiple experiments are executed relative
    to each other during a coordinated game day exercise.
    """

    SEQUENTIAL = "sequential"
    CONCURRENT = "concurrent"
    STAGGERED = "staggered"
```

---

## 5. Dataclasses (~8)

### 5.1 FaultConfig

```python
@dataclass
class FaultConfig:
    """Configuration for a specific fault injection.

    Each fault type accepts type-specific parameters that control
    the intensity, scope, and behavior of the injected fault.

    Attributes:
        fault_type: The type of fault to inject.
        target_container: Specific container ID, or empty for selector-based targeting.
        target_labels: Label selector for targeting containers (e.g., {"app": "fizzbuzz-core"}).
        target_count: Number of containers to affect (0 = all matching).
        duration: How long the fault remains injected (seconds).
        direction: For network faults, ingress/egress/both.
        target_peers: For partition faults, specific peer container IDs.
        cores: For CPU stress, number of cores to stress.
        load_percent: For CPU stress, percentage of quota to consume.
        target_bytes: For memory pressure, bytes to allocate.
        rate_bytes_per_second: For memory pressure, allocation rate.
        fill_percent: For disk fill, percentage of writable layer to consume.
        file_size: For disk fill, size of files created (bytes).
        error_type: For image pull failure (server_error, timeout, invalid_manifest, auth_failure).
        affected_images: For image pull failure, specific image names.
        failure_mode: For DNS failure (servfail, nxdomain, timeout, delayed).
        affected_domains: For DNS failure, specific domain patterns.
        delay_ms: For DNS delayed mode or network latency.
        latency_ms: For network latency, added delay.
        jitter_ms: For network latency, random variation.
        correlation_percent: For network latency, percentage of packets affected.
        interval: For container kill, interval between repeated kills (seconds).
    """

    fault_type: FaultType = FaultType.CONTAINER_KILL
    target_container: str = ""
    target_labels: Dict[str, str] = field(default_factory=dict)
    target_count: int = 1
    duration: float = 60.0
    direction: str = "both"
    target_peers: List[str] = field(default_factory=list)
    cores: int = DEFAULT_CPU_STRESS_CORES
    load_percent: float = 80.0
    target_bytes: int = 0
    rate_bytes_per_second: int = DEFAULT_MEMORY_PRESSURE_RATE
    fill_percent: float = DEFAULT_DISK_FILL_PERCENT
    file_size: int = 4096
    error_type: str = "server_error"
    affected_images: List[str] = field(default_factory=list)
    failure_mode: str = "servfail"
    affected_domains: List[str] = field(default_factory=list)
    delay_ms: float = 0.0
    latency_ms: float = DEFAULT_LATENCY_MS
    jitter_ms: float = DEFAULT_JITTER_MS
    correlation_percent: float = 100.0
    interval: float = 0.0
```

### 5.2 SteadyStateMetric

```python
@dataclass
class SteadyStateMetric:
    """A metric that defines normal system behavior.

    Steady-state metrics are measured before fault injection to
    establish a baseline, monitored during injection to detect
    violations, and measured after fault removal to verify recovery.

    Attributes:
        name: Metric name (e.g., "error_rate", "p99_latency_ms", "throughput_rps").
        baseline_value: Value measured before fault injection.
        during_value: Value measured during fault injection.
        recovery_value: Value measured after fault removal.
        threshold_upper: Upper bound for acceptable values.
        threshold_lower: Lower bound for acceptable values.
        unit: Human-readable unit (e.g., "ms", "%", "req/s").
        source: Where this metric is collected from (e.g., "fizzsli", "fizzcgroup").
    """

    name: str = ""
    baseline_value: float = 0.0
    during_value: float = 0.0
    recovery_value: float = 0.0
    threshold_upper: Optional[float] = None
    threshold_lower: Optional[float] = None
    unit: str = ""
    source: str = "fizzsli"
```

### 5.3 AbortCondition

```python
@dataclass
class AbortCondition:
    """Condition that triggers automatic experiment termination.

    Abort conditions are evaluated every observation interval during
    fault injection.  If any condition is met, the experiment is
    immediately aborted and the fault is removed.

    Attributes:
        metric_name: Name of the metric to monitor.
        operator: Comparison operator ("gt", "lt", "gte", "lte", "eq").
        threshold: Threshold value.
        duration_seconds: Condition must persist for this duration before aborting.
        description: Human-readable description (e.g., "Abort if error rate exceeds 50%").
        triggered: Whether this condition has been triggered.
        triggered_at: When the condition was first triggered.
    """

    metric_name: str = ""
    operator: str = "gt"
    threshold: float = 0.0
    duration_seconds: float = 0.0
    description: str = ""
    triggered: bool = False
    triggered_at: Optional[datetime] = None
```

### 5.4 ChaosExperiment

```python
@dataclass
class ChaosExperiment:
    """Defines a complete chaos experiment.

    A chaos experiment specifies what fault to inject, where to inject
    it, how long to maintain it, what behavior is expected during the
    fault (hypothesis), what metrics define normal operation (steady
    state), and what conditions trigger automatic termination (abort
    conditions).

    Attributes:
        experiment_id: Unique experiment identifier.
        name: Human-readable experiment name.
        description: Detailed description of the experiment's purpose.
        fault_config: Configuration for the fault to inject.
        hypothesis: Expected system behavior during the fault.
        steady_state_metrics: Metrics defining normal behavior.
        abort_conditions: Conditions triggering automatic termination.
        schedule: Optional cron expression for recurring experiments.
        status: Current experiment lifecycle status.
        blast_radius_scope: Scope for blast radius calculation.
        is_emergency: Emergency experiments bypass cognitive load gating.
        affected_containers: Container IDs currently affected by this experiment.
        timeline: Ordered list of (timestamp, event_description) tuples.
        created_at: When the experiment was created.
        started_at: When execution began.
        completed_at: When execution finished.
        abort_reason: Reason for abort, if aborted.
        error_message: Error details, if failed.
    """

    experiment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    fault_config: FaultConfig = field(default_factory=FaultConfig)
    hypothesis: str = ""
    steady_state_metrics: List[SteadyStateMetric] = field(default_factory=list)
    abort_conditions: List[AbortCondition] = field(default_factory=list)
    schedule: str = ""
    status: ExperimentStatus = ExperimentStatus.PENDING
    blast_radius_scope: BlastRadiusScope = BlastRadiusScope.GLOBAL
    is_emergency: bool = False
    affected_containers: List[str] = field(default_factory=list)
    timeline: List[Tuple[datetime, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    abort_reason: Optional[AbortReason] = None
    error_message: str = ""
```

### 5.5 ExperimentReport

```python
@dataclass
class ExperimentReport:
    """Post-experiment analysis report.

    Produced after an experiment completes (successfully, by abort,
    or by failure).  Compares steady-state metrics before, during,
    and after fault injection to evaluate the hypothesis.

    Attributes:
        experiment_id: ID of the experiment this report covers.
        experiment_name: Name of the experiment.
        fault_type: Type of fault that was injected.
        hypothesis: The stated hypothesis.
        hypothesis_validated: Whether the hypothesis held during the fault.
        steady_state_comparison: Before/during/after metric comparisons.
        affected_container_count: Number of containers affected.
        total_container_count: Total containers in scope.
        blast_radius_percent: Actual blast radius as percentage.
        duration_seconds: Total experiment duration.
        abort_reason: Reason if aborted.
        timeline: Chronological event log.
        recommendations: List of remediation recommendations.
        generated_at: When the report was generated.
    """

    experiment_id: str = ""
    experiment_name: str = ""
    fault_type: FaultType = FaultType.CONTAINER_KILL
    hypothesis: str = ""
    hypothesis_validated: bool = False
    steady_state_comparison: List[Dict[str, Any]] = field(default_factory=list)
    affected_container_count: int = 0
    total_container_count: int = 0
    blast_radius_percent: float = 0.0
    duration_seconds: float = 0.0
    abort_reason: Optional[AbortReason] = None
    timeline: List[Tuple[datetime, str]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

### 5.6 GameDay

```python
@dataclass
class GameDay:
    """A structured chaos exercise composing multiple experiments.

    Game days provide a coordinated, narrative-driven approach to
    chaos engineering.  Multiple experiments are scheduled according
    to a defined plan (sequential, concurrent, or staggered), with
    system-level hypotheses and blast radius limits that apply across
    all experiments in the exercise.

    Attributes:
        gameday_id: Unique game day identifier.
        title: Human-readable title.
        description: Narrative describing the scenario.
        hypothesis: System-level expected behavior.
        experiments: Ordered list of ChaosExperiments.
        schedule_mode: How experiments are scheduled relative to each other.
        stagger_interval: For staggered mode, delay between experiment starts (seconds).
        blast_radius_limit: Maximum fraction of containers affected across all experiments.
        blast_radius_scope: Scope for blast radius calculation.
        abort_conditions: System-level abort conditions.
        duration_limit: Maximum game day duration (seconds).
        status: Current game day status.
        affected_containers: All containers affected across all experiments.
        timeline: Chronological event log.
        created_at: When the game day was created.
        started_at: When execution began.
        completed_at: When execution finished.
        abort_reason: Reason if aborted.
    """

    gameday_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    hypothesis: str = ""
    experiments: List[ChaosExperiment] = field(default_factory=list)
    schedule_mode: ScheduleMode = ScheduleMode.SEQUENTIAL
    stagger_interval: float = 30.0
    blast_radius_limit: float = DEFAULT_BLAST_RADIUS_LIMIT
    blast_radius_scope: BlastRadiusScope = BlastRadiusScope.GLOBAL
    abort_conditions: List[AbortCondition] = field(default_factory=list)
    duration_limit: float = DEFAULT_GAMEDAY_TIMEOUT
    status: GameDayStatus = GameDayStatus.PLANNING
    affected_containers: Set[str] = field(default_factory=set)
    timeline: List[Tuple[datetime, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    abort_reason: Optional[AbortReason] = None
```

### 5.7 GameDayReport

```python
@dataclass
class GameDayReport:
    """Post-game-day analysis report.

    Aggregates individual experiment reports into a comprehensive
    assessment of system resilience across the game day scenario.

    Attributes:
        gameday_id: ID of the game day.
        title: Game day title.
        hypothesis: System-level hypothesis.
        hypothesis_validated: Whether the system-level hypothesis held.
        experiment_reports: Individual experiment reports.
        experiments_completed: Count of completed experiments.
        experiments_aborted: Count of aborted experiments.
        experiments_failed: Count of failed experiments.
        peak_blast_radius_percent: Maximum simultaneous blast radius.
        total_duration_seconds: Total game day duration.
        timeline: Chronological event log.
        resilience_gaps: Identified resilience gaps.
        recommendations: Remediation recommendations.
        generated_at: When the report was generated.
    """

    gameday_id: str = ""
    title: str = ""
    hypothesis: str = ""
    hypothesis_validated: bool = False
    experiment_reports: List[ExperimentReport] = field(default_factory=list)
    experiments_completed: int = 0
    experiments_aborted: int = 0
    experiments_failed: int = 0
    peak_blast_radius_percent: float = 0.0
    total_duration_seconds: float = 0.0
    timeline: List[Tuple[datetime, str]] = field(default_factory=list)
    resilience_gaps: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

### 5.8 ChaosSchedule

```python
@dataclass
class ChaosSchedule:
    """Schedule for recurring chaos experiments.

    Recurring experiments run on a cron-like schedule, enabling
    continuous resilience validation without manual intervention.

    Attributes:
        schedule_id: Unique schedule identifier.
        experiment_template: Template experiment to instantiate on each run.
        cron_expression: Cron expression (e.g., "0 */6 * * *" for every 6 hours).
        enabled: Whether the schedule is active.
        last_run_at: When the experiment last ran.
        next_run_at: When the experiment will next run.
        run_count: Total number of scheduled runs completed.
        max_runs: Maximum number of runs (0 = unlimited).
        created_at: When the schedule was created.
    """

    schedule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    experiment_template: ChaosExperiment = field(default_factory=ChaosExperiment)
    cron_expression: str = "0 */6 * * *"
    enabled: bool = True
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    run_count: int = 0
    max_runs: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 6. Exception Classes (~20, EFP-CCH prefix)

Add to `enterprise_fizzbuzz/domain/exceptions.py` after the FizzContainerd section:

```python
# -- FizzContainerChaos: Container-Native Chaos Engineering ----


class ContainerChaosError(FizzBuzzError):
    """Base exception for FizzContainerChaos chaos engineering errors.

    All exceptions originating from the container-native chaos
    engineering subsystem inherit from this class.  The subsystem
    provides fault injection at the namespace, cgroup, overlay,
    CNI, and container runtime layers.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH00"
        self.context = {"reason": reason}


class ChaosExperimentNotFoundError(ContainerChaosError):
    """Raised when a referenced chaos experiment does not exist.

    Experiment operations require the experiment to be registered
    in the chaos executor's experiment registry.  Referencing a
    nonexistent or previously deleted experiment triggers this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH01"
        self.context = {"reason": reason}


class ChaosExperimentAlreadyRunningError(ContainerChaosError):
    """Raised when attempting to start an experiment that is already running.

    Each experiment can only execute once.  Attempting to start an
    experiment whose status is RUNNING, INJECTING, or OBSERVING
    triggers this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH02"
        self.context = {"reason": reason}


class ChaosExperimentAbortedError(ContainerChaosError):
    """Raised when a chaos experiment is aborted due to safety conditions.

    Abort conditions protect the platform from cascading failures
    during chaos injection.  When an abort condition is triggered,
    fault injection is immediately halted and this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH03"
        self.context = {"reason": reason}


class ChaosExperimentFailedStartError(ContainerChaosError):
    """Raised when a chaos experiment fails during the pre-check phase.

    Pre-checks verify that target containers exist and are healthy,
    that the operator's cognitive load permits chaos injection, and
    that blast radius limits would not be exceeded.  Failure at any
    pre-check stage triggers this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH04"
        self.context = {"reason": reason}


class ChaosFaultInjectionError(ContainerChaosError):
    """Raised when fault injection fails.

    Fault injection requires interaction with the container runtime
    layer (FizzContainerd, FizzCgroup, FizzCNI, FizzOverlay).
    Failures in any of these subsystems during fault injection
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH05"
        self.context = {"reason": reason}


class ChaosFaultRemovalError(ContainerChaosError):
    """Raised when fault removal fails.

    After experiment completion, injected faults must be removed
    to restore normal operation.  If fault removal fails, the
    system may remain in a degraded state.  This exception signals
    that manual intervention may be required.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH06"
        self.context = {"reason": reason}


class ChaosContainerKillError(ContainerChaosError):
    """Raised when the container kill fault fails to terminate a container.

    Container kill sends SIGKILL to the container's init process
    via FizzContainerd's task service.  If the signal delivery or
    process termination fails, this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH07"
        self.context = {"reason": reason}


class ChaosNetworkPartitionError(ContainerChaosError):
    """Raised when the network partition fault fails.

    Network partition isolates a container by dropping traffic on
    its veth interface via FizzCNI.  Failures in packet filter rule
    installation or veth endpoint access trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH08"
        self.context = {"reason": reason}


class ChaosCPUStressError(ContainerChaosError):
    """Raised when the CPU stress fault fails.

    CPU stress runs a busy-loop process inside the target container's
    cgroup to consume CPU quota.  Failures in process creation or
    cgroup attachment trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH09"
        self.context = {"reason": reason}


class ChaosMemoryPressureError(ContainerChaosError):
    """Raised when the memory pressure fault fails.

    Memory pressure allocates memory inside a container's cgroup
    until the memory.high threshold is reached.  Failures in
    allocation simulation or cgroup interaction trigger this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH10"
        self.context = {"reason": reason}


class ChaosDiskFillError(ContainerChaosError):
    """Raised when the disk fill fault fails.

    Disk fill writes data to the container's overlay writable layer.
    Failures in overlay filesystem interaction or write operations
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH11"
        self.context = {"reason": reason}


class ChaosImagePullFailureError(ContainerChaosError):
    """Raised when the image pull failure fault fails to intercept pulls.

    Image pull failure intercepts requests from FizzContainerd to
    FizzRegistry.  Failures in request interception or error
    response injection trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH12"
        self.context = {"reason": reason}


class ChaosDNSFailureError(ContainerChaosError):
    """Raised when the DNS failure fault fails to disrupt resolution.

    DNS failure intercepts queries from FizzCNI's ContainerDNS.
    Failures in query interception or failure mode injection
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH13"
        self.context = {"reason": reason}


class ChaosNetworkLatencyError(ContainerChaosError):
    """Raised when the network latency fault fails to inject delay.

    Network latency adds delay to packets on a container's veth
    interface.  Failures in packet queue configuration or delay
    injection trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH14"
        self.context = {"reason": reason}


class ChaosGameDayError(ContainerChaosError):
    """Raised when a game day orchestration encounters an error.

    Game day errors include experiment scheduling failures,
    blast radius calculation errors, and report generation
    failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH15"
        self.context = {"reason": reason}


class ChaosGameDayAbortError(ContainerChaosError):
    """Raised when a game day is aborted due to system-level conditions.

    System-level abort conditions apply across all experiments
    in a game day.  When triggered, all running experiments are
    halted and faults are removed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH16"
        self.context = {"reason": reason}


class ChaosBlastRadiusExceededError(ContainerChaosError):
    """Raised when a fault injection would exceed the blast radius limit.

    Blast radius limits prevent chaos experiments from affecting
    too many containers simultaneously, protecting the platform
    from total service disruption during testing.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH17"
        self.context = {"reason": reason}


class ChaosSteadyStateViolationError(ContainerChaosError):
    """Raised when steady-state metrics deviate beyond tolerance during injection.

    Steady-state violations indicate that the system is not
    behaving as hypothesized during fault injection.  The experiment
    may continue or abort depending on abort condition configuration.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH18"
        self.context = {"reason": reason}


class ChaosCognitiveLoadGateError(ContainerChaosError):
    """Raised when the operator's cognitive load exceeds the chaos threshold.

    FizzBob's NASA-TLX cognitive load model prevents chaos
    experiments from running when the operator lacks sufficient
    cognitive capacity to monitor and respond to injected faults.
    Emergency experiments bypass this gate.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH19"
        self.context = {"reason": reason}


class ChaosScheduleError(ContainerChaosError):
    """Raised when a chaos schedule encounters a configuration error.

    Schedule errors include invalid cron expressions, conflicting
    schedules, and scheduling conflicts with maintenance windows.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH20"
        self.context = {"reason": reason}


class ChaosReportGenerationError(ContainerChaosError):
    """Raised when experiment or game day report generation fails.

    Report generation requires steady-state metric data from
    before, during, and after fault injection.  Missing data or
    metric collection errors trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH21"
        self.context = {"reason": reason}


class ChaosTargetResolutionError(ContainerChaosError):
    """Raised when target container resolution fails.

    Target resolution uses label selectors or container IDs to
    identify containers for fault injection.  If no containers
    match or the selector is invalid, this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CCH22"
        self.context = {"reason": reason}


class ChaosContainerChaosMiddlewareError(ContainerChaosError):
    """Raised when the FizzContainerChaos middleware fails during evaluation.

    The middleware annotates FizzBuzz evaluation responses with
    active chaos experiment information.  If experiment registry
    access or context enrichment fails, this exception is raised.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Container chaos middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-CCH23"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number
```

---

## 7. EventType Entries (~15)

Add to `enterprise_fizzbuzz/domain/models.py` EventType enum:

```python
    # Container Chaos Engineering events
    CONTAINER_CHAOS_EXPERIMENT_CREATED = auto()
    CONTAINER_CHAOS_EXPERIMENT_STARTED = auto()
    CONTAINER_CHAOS_EXPERIMENT_COMPLETED = auto()
    CONTAINER_CHAOS_EXPERIMENT_ABORTED = auto()
    CONTAINER_CHAOS_EXPERIMENT_FAILED = auto()
    CONTAINER_CHAOS_FAULT_INJECTED = auto()
    CONTAINER_CHAOS_FAULT_REMOVED = auto()
    CONTAINER_CHAOS_STEADY_STATE_MEASURED = auto()
    CONTAINER_CHAOS_STEADY_STATE_VIOLATED = auto()
    CONTAINER_CHAOS_ABORT_CONDITION_TRIGGERED = auto()
    CONTAINER_CHAOS_BLAST_RADIUS_CHECKED = auto()
    CONTAINER_CHAOS_COGNITIVE_GATE_CHECKED = auto()
    CONTAINER_CHAOS_GAMEDAY_STARTED = auto()
    CONTAINER_CHAOS_GAMEDAY_COMPLETED = auto()
    CONTAINER_CHAOS_GAMEDAY_ABORTED = auto()
```

---

## 8. Class Inventory

### 8.1 TargetResolver

```python
class TargetResolver:
    """Resolves fault injection targets from label selectors or container IDs.

    Uses FizzContainerd's metadata service to look up containers
    matching a label selector or specific container IDs.  Returns
    the set of container IDs that a fault should be applied to,
    respecting the target_count limit.
    """

    def __init__(self) -> None: ...

    def resolve(
        self,
        fault_config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> List[str]:
        """Resolve target containers from the fault configuration.

        Args:
            fault_config: Fault configuration with target selectors.
            container_registry: Registry of active containers (id -> metadata).

        Returns:
            List of container IDs to target.

        Raises:
            ChaosTargetResolutionError: If no containers match.
        """
        ...

    def _match_labels(
        self,
        container_labels: Dict[str, str],
        selector: Dict[str, str],
    ) -> bool:
        """Check if container labels satisfy the selector."""
        ...
```

### 8.2 SteadyStateProbe

```python
class SteadyStateProbe:
    """Measures steady-state metrics before, during, and after fault injection.

    Collects metric values from simulated FizzSLI data and cgroup
    resource utilization.  Baseline measurements establish normal
    behavior.  During and recovery measurements are compared
    against the baseline with a configurable tolerance band.
    """

    def __init__(
        self,
        tolerance: float = DEFAULT_STEADY_STATE_TOLERANCE,
    ) -> None: ...

    def measure_baseline(
        self,
        metrics: List[SteadyStateMetric],
        container_ids: List[str],
    ) -> List[SteadyStateMetric]:
        """Measure baseline steady-state metrics.

        Records the current value of each metric and stores it
        as the baseline for later comparison.
        """
        ...

    def measure_during(
        self,
        metrics: List[SteadyStateMetric],
        container_ids: List[str],
    ) -> List[SteadyStateMetric]:
        """Measure steady-state metrics during fault injection."""
        ...

    def measure_recovery(
        self,
        metrics: List[SteadyStateMetric],
        container_ids: List[str],
    ) -> List[SteadyStateMetric]:
        """Measure steady-state metrics after fault removal."""
        ...

    def check_violations(
        self,
        metrics: List[SteadyStateMetric],
    ) -> List[SteadyStateMetric]:
        """Check for metrics violating their thresholds.

        Returns list of violated metrics.
        """
        ...

    def compare(
        self,
        metrics: List[SteadyStateMetric],
    ) -> List[Dict[str, Any]]:
        """Compare baseline, during, and recovery values.

        Returns comparison dictionaries for each metric.
        """
        ...
```

### 8.3 BlastRadiusCalculator

```python
class BlastRadiusCalculator:
    """Calculates and enforces blast radius limits.

    Blast radius is the fraction of containers affected by active
    chaos experiments.  The calculator tracks affected containers
    across all concurrent experiments and prevents new fault
    injections that would exceed the configured limit.
    """

    def __init__(
        self,
        limit: float = DEFAULT_BLAST_RADIUS_LIMIT,
        scope: BlastRadiusScope = BlastRadiusScope.GLOBAL,
    ) -> None: ...

    def check(
        self,
        new_targets: List[str],
        currently_affected: Set[str],
        total_containers: int,
    ) -> Tuple[bool, float]:
        """Check if adding new targets would exceed the blast radius limit.

        Returns:
            Tuple of (is_within_limit, resulting_blast_radius_percent).
        """
        ...

    def current_radius(
        self,
        affected: Set[str],
        total: int,
    ) -> float:
        """Calculate current blast radius as a percentage."""
        ...

    def add_affected(self, container_ids: List[str]) -> None:
        """Register containers as affected by an active experiment."""
        ...

    def remove_affected(self, container_ids: List[str]) -> None:
        """Deregister containers when a fault is removed."""
        ...

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary of current blast radius state."""
        ...
```

### 8.4 Fault Injector Classes (8 classes)

Each fault injector follows the same interface pattern with `inject()`, `remove()`, and `verify()` methods.

#### 8.4.1 ContainerKillFault

```python
class ContainerKillFault:
    """Kills containers by sending SIGKILL to init processes.

    Sends SIGKILL to the target container's init process via
    FizzContainerd's task service.  Verifies that the container
    enters a stopped state and, if managed by FizzKube, that the
    orchestrator detects the failure and schedules a restart
    according to the pod's restart policy.

    Attributes:
        kill_count: Number of containers killed.
        restart_verified: Number of containers verified as restarted.
    """

    def __init__(self) -> None: ...

    def inject(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Kill the target containers.

        Returns dict with kill results per container.
        """
        ...

    def remove(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> None:
        """Container kill has no removal -- containers are restarted by the orchestrator."""
        ...

    def verify(
        self,
        container_ids: List[str],
        container_registry: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Verify that killed containers have been restarted."""
        ...
```

#### 8.4.2 NetworkPartitionFault

```python
class NetworkPartitionFault:
    """Isolates containers by dropping network traffic.

    Adds drop rules to the FizzCNI bridge's packet filter for
    the target container's veth endpoint.  Supports directional
    partitioning (ingress-only, egress-only, or both) and
    selective peer partitioning.
    """

    def __init__(self) -> None: ...

    def inject(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> Dict[str, Any]: ...

    def remove(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> None:
        """Remove drop rules to restore network connectivity."""
        ...

    def verify(
        self,
        container_ids: List[str],
        container_registry: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Verify that partition detection (health check failure) occurred."""
        ...
```

#### 8.4.3 CPUStressFault

```python
class CPUStressFault:
    """Consumes CPU quota inside container cgroups.

    Runs a simulated busy-loop process inside the container's
    cgroup to compete for CPU bandwidth.  Monitors FizzCgroup's
    cpu.stat to verify that throttling activates (nr_throttled
    increases).
    """

    def __init__(self) -> None: ...

    def inject(self, container_ids, config, container_registry) -> Dict[str, Any]: ...
    def remove(self, container_ids, config, container_registry) -> None: ...
    def verify(self, container_ids, container_registry) -> Dict[str, bool]: ...
```

#### 8.4.4 MemoryPressureFault

```python
class MemoryPressureFault:
    """Allocates memory inside container cgroups to trigger pressure.

    Simulates memory allocation at a configurable rate until
    the memory.high threshold (triggering throttling) or
    memory.max (triggering OOM kill) is reached.  Verifies
    that the OOM killer targets the stress process, not the
    application.
    """

    def __init__(self) -> None: ...

    def inject(self, container_ids, config, container_registry) -> Dict[str, Any]: ...
    def remove(self, container_ids, config, container_registry) -> None: ...
    def verify(self, container_ids, container_registry) -> Dict[str, bool]: ...
```

#### 8.4.5 DiskFillFault

```python
class DiskFillFault:
    """Fills container overlay writable layers.

    Writes data to the container's overlay writable layer until
    a configurable percentage of the layer's capacity is consumed.
    Verifies that application write operations fail gracefully.
    """

    def __init__(self) -> None: ...

    def inject(self, container_ids, config, container_registry) -> Dict[str, Any]: ...
    def remove(self, container_ids, config, container_registry) -> None: ...
    def verify(self, container_ids, container_registry) -> Dict[str, bool]: ...
```

#### 8.4.6 ImagePullFailureFault

```python
class ImagePullFailureFault:
    """Intercepts image pulls and injects errors.

    Injects error responses (HTTP 500, timeout, invalid manifest,
    auth failure) into FizzContainerd-to-FizzRegistry image pull
    requests.  Verifies that pods enter ImagePullBackOff state.
    """

    def __init__(self) -> None: ...

    def inject(self, container_ids, config, container_registry) -> Dict[str, Any]: ...
    def remove(self, container_ids, config, container_registry) -> None: ...
    def verify(self, container_ids, container_registry) -> Dict[str, bool]: ...
```

#### 8.4.7 DNSFailureFault

```python
class DNSFailureFault:
    """Disrupts DNS resolution in container networks.

    Intercepts DNS queries from FizzCNI's ContainerDNS and
    returns SERVFAIL, NXDOMAIN, timeout, or delayed responses.
    Verifies that services handle resolution failures gracefully.
    """

    def __init__(self) -> None: ...

    def inject(self, container_ids, config, container_registry) -> Dict[str, Any]: ...
    def remove(self, container_ids, config, container_registry) -> None: ...
    def verify(self, container_ids, container_registry) -> Dict[str, bool]: ...
```

#### 8.4.8 NetworkLatencyFault

```python
class NetworkLatencyFault:
    """Adds configurable delay to container network traffic.

    Queues packets on the container's veth interface with a
    programmable delay before forwarding.  Supports jitter
    (random variation) and partial correlation (affecting a
    percentage of packets).
    """

    def __init__(self) -> None: ...

    def inject(self, container_ids, config, container_registry) -> Dict[str, Any]: ...
    def remove(self, container_ids, config, container_registry) -> None: ...
    def verify(self, container_ids, container_registry) -> Dict[str, bool]: ...
```

### 8.5 FaultRegistry

```python
class FaultRegistry:
    """Registry mapping fault types to their injector implementations.

    Provides a single lookup point for resolving fault type enums
    to their corresponding injector class instances.
    """

    def __init__(self) -> None:
        """Initialize with all eight fault injectors."""
        ...

    def get_injector(self, fault_type: FaultType) -> Any:
        """Return the injector for the given fault type."""
        ...

    def list_faults(self) -> List[Dict[str, Any]]:
        """Return metadata for all registered fault types.

        Each entry includes fault_type, description, and configurable
        parameters with their defaults.
        """
        ...
```

### 8.6 ChaosExecutor

```python
class ChaosExecutor:
    """Executes chaos experiments through a standardized seven-phase lifecycle.

    The executor manages the complete experiment lifecycle:
    1. Pre-check: verify targets exist, cognitive load permits, blast radius safe
    2. Steady-state measurement: record baseline metrics
    3. Fault injection: apply the fault to target containers
    4. Observation: monitor abort conditions at regular intervals
    5. Fault removal: remove the fault
    6. Post-measurement: record recovery metrics
    7. Report generation: produce the experiment report

    Attributes:
        experiments: Registry of all experiments (active and historical).
        active_experiments: Currently running experiment IDs.
        reports: Generated experiment reports.
    """

    def __init__(
        self,
        fault_registry: FaultRegistry,
        target_resolver: TargetResolver,
        steady_state_probe: SteadyStateProbe,
        blast_radius_calculator: BlastRadiusCalculator,
        cognitive_load_threshold: float = DEFAULT_COGNITIVE_LOAD_THRESHOLD,
        observation_interval: float = DEFAULT_OBSERVATION_INTERVAL,
        container_registry: Optional[Dict[str, Any]] = None,
        event_bus: Optional[Any] = None,
    ) -> None: ...

    def register_experiment(self, experiment: ChaosExperiment) -> str:
        """Register a new experiment and return its ID."""
        ...

    def run_experiment(self, experiment_id: str) -> ExperimentReport:
        """Execute the full seven-phase experiment lifecycle.

        Args:
            experiment_id: ID of the registered experiment.

        Returns:
            ExperimentReport with results.

        Raises:
            ChaosExperimentNotFoundError: Experiment not registered.
            ChaosExperimentAlreadyRunningError: Experiment already running.
            ChaosExperimentFailedStartError: Pre-check failed.
        """
        ...

    def abort_experiment(self, experiment_id: str, reason: AbortReason = AbortReason.MANUAL_ABORT) -> None:
        """Abort a running experiment.

        Immediately removes the injected fault and updates the
        experiment status to ABORTED.
        """
        ...

    def get_experiment(self, experiment_id: str) -> ChaosExperiment:
        """Return experiment by ID."""
        ...

    def get_report(self, experiment_id: str) -> Optional[ExperimentReport]:
        """Return experiment report by ID."""
        ...

    def list_active(self) -> List[ChaosExperiment]:
        """Return all currently running experiments."""
        ...

    def list_all(self) -> List[ChaosExperiment]:
        """Return all experiments (active and historical)."""
        ...

    def _pre_check(self, experiment: ChaosExperiment) -> None:
        """Phase 1: Verify targets, cognitive load, blast radius."""
        ...

    def _measure_baseline(self, experiment: ChaosExperiment) -> None:
        """Phase 2: Record baseline steady-state metrics."""
        ...

    def _inject_fault(self, experiment: ChaosExperiment) -> None:
        """Phase 3: Apply the fault to target containers."""
        ...

    def _observe(self, experiment: ChaosExperiment) -> bool:
        """Phase 4: Monitor abort conditions. Returns True if aborted."""
        ...

    def _remove_fault(self, experiment: ChaosExperiment) -> None:
        """Phase 5: Remove the fault."""
        ...

    def _measure_recovery(self, experiment: ChaosExperiment) -> None:
        """Phase 6: Record recovery metrics."""
        ...

    def _generate_report(self, experiment: ChaosExperiment) -> ExperimentReport:
        """Phase 7: Produce the experiment report."""
        ...

    def _check_cognitive_load(self) -> float:
        """Query FizzBob cognitive load model.

        Returns the current NASA-TLX score.
        """
        ...

    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        ...

    def _add_timeline(self, experiment: ChaosExperiment, description: str) -> None:
        """Add a timestamped entry to the experiment timeline."""
        ...
```

### 8.7 ChaosGate

```python
class ChaosGate:
    """FizzBob cognitive load gate for chaos experiments.

    Queries the operator's NASA-TLX cognitive load score and
    blocks chaos experiments when the score exceeds the chaos
    threshold.  Emergency experiments bypass the gate.

    The chaos threshold (default: 60) is lower than the deployment
    threshold (default: 70) because chaos experiments require more
    cognitive capacity to monitor and respond to than routine
    deployments.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_COGNITIVE_LOAD_THRESHOLD,
    ) -> None: ...

    def check(self, is_emergency: bool = False) -> Tuple[bool, float]:
        """Check if chaos experiments are permitted.

        Args:
            is_emergency: Emergency experiments bypass the gate.

        Returns:
            Tuple of (is_permitted, current_cognitive_load_score).

        Raises:
            ChaosCognitiveLoadGateError: If load exceeds threshold
                and experiment is not emergency.
        """
        ...

    def get_threshold(self) -> float:
        """Return the current cognitive load threshold."""
        ...

    def set_threshold(self, threshold: float) -> None:
        """Update the cognitive load threshold."""
        ...
```

### 8.8 GameDayOrchestrator

```python
class GameDayOrchestrator:
    """Orchestrates coordinated multi-experiment game day exercises.

    Schedules experiments according to the game day's plan
    (sequential, concurrent, or staggered), monitors blast
    radius limits across all experiments, and produces a
    comprehensive post-game-day report.
    """

    def __init__(
        self,
        executor: ChaosExecutor,
        blast_radius_calculator: BlastRadiusCalculator,
    ) -> None: ...

    def register_gameday(self, gameday: GameDay) -> str:
        """Register a game day and return its ID."""
        ...

    def run_gameday(self, gameday_id: str) -> GameDayReport:
        """Execute a game day through its complete lifecycle.

        1. Pre-flight: validate experiments, check cognitive load
        2. Execute: run experiments according to schedule mode
        3. Cooldown: wait for system stabilization
        4. Report: generate comprehensive game day report
        """
        ...

    def abort_gameday(self, gameday_id: str, reason: AbortReason = AbortReason.MANUAL_ABORT) -> None:
        """Abort all running experiments in a game day."""
        ...

    def get_gameday(self, gameday_id: str) -> GameDay:
        """Return game day by ID."""
        ...

    def get_report(self, gameday_id: str) -> Optional[GameDayReport]:
        """Return game day report by ID."""
        ...

    def _run_sequential(self, gameday: GameDay) -> List[ExperimentReport]: ...
    def _run_concurrent(self, gameday: GameDay) -> List[ExperimentReport]: ...
    def _run_staggered(self, gameday: GameDay) -> List[ExperimentReport]: ...
    def _check_system_abort(self, gameday: GameDay) -> bool: ...
    def _generate_report(self, gameday: GameDay, exp_reports: List[ExperimentReport]) -> GameDayReport: ...
```

### 8.9 PredefinedGameDays

```python
class PredefinedGameDays:
    """Factory for predefined game day scenarios.

    Provides four predefined game day templates that cover the
    most common container resilience scenarios.
    """

    @staticmethod
    def container_restart_resilience() -> GameDay:
        """Kill containers across all service groups, verify restart."""
        ...

    @staticmethod
    def network_partition_tolerance() -> GameDay:
        """Partition fizzbuzz-core from fizzbuzz-data, verify degradation."""
        ...

    @staticmethod
    def resource_exhaustion() -> GameDay:
        """Apply CPU and memory stress to all services simultaneously."""
        ...

    @staticmethod
    def full_outage_recovery() -> GameDay:
        """Kill all containers, verify full platform recovery."""
        ...
```

### 8.10 ContainerChaosDashboard

```python
class ContainerChaosDashboard:
    """ASCII dashboard for chaos experiment status and reporting.

    Renders experiment status, active faults, blast radius,
    game day progress, and experiment reports as formatted
    ASCII tables using box-drawing characters.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None: ...

    def render_status(self, executor: ChaosExecutor) -> str:
        """Render active experiments with status, targets, and duration."""
        ...

    def render_report(self, report: ExperimentReport) -> str:
        """Render an experiment report with metric comparisons."""
        ...

    def render_gameday_report(self, report: GameDayReport) -> str:
        """Render a game day report with timeline and gaps."""
        ...

    def render_blast_radius(self, calculator: BlastRadiusCalculator, total: int) -> str:
        """Render current blast radius as a visual gauge."""
        ...

    def render_fault_list(self, registry: FaultRegistry) -> str:
        """Render available fault types with parameters and defaults."""
        ...

    def _render_header(self, title: str) -> str: ...
    def _render_table(self, headers: List[str], rows: List[List[str]]) -> str: ...
    def _render_metric_comparison(self, comparisons: List[Dict[str, Any]]) -> str: ...
    def _render_timeline(self, timeline: List[Tuple[datetime, str]]) -> str: ...
```

### 8.11 FizzContainerChaosMiddleware

```python
class FizzContainerChaosMiddleware(IMiddleware):
    """Middleware integrating container chaos with the FizzBuzz pipeline.

    Annotates each FizzBuzz evaluation response with information
    about any active chaos experiments affecting the evaluation's
    container.  If the evaluation is running inside a container
    that is currently targeted by a fault injection, the response
    metadata includes the experiment ID, fault type, and injection
    start time.

    Priority: 117 (after FizzContainerd at 112, before higher-priority
    middleware).
    """

    def __init__(
        self,
        executor: ChaosExecutor,
        dashboard: ContainerChaosDashboard,
        enable_dashboard: bool = False,
    ) -> None: ...

    def get_name(self) -> str:
        """Return 'FizzContainerChaosMiddleware'."""
        ...

    def get_priority(self) -> int:
        """Return MIDDLEWARE_PRIORITY (117)."""
        ...

    @property
    def priority(self) -> int: ...

    @property
    def name(self) -> str: ...

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process evaluation, annotating with active chaos info.

        Checks if the evaluation's container is targeted by an
        active experiment.  If so, adds chaos metadata to the
        processing context.  Then delegates to the next handler.
        """
        ...

    def render_status(self) -> str:
        """Render active experiment status."""
        ...

    def render_report(self, experiment_id: str) -> str:
        """Render a specific experiment report."""
        ...

    def render_gameday_report(self, gameday_id: str) -> str:
        """Render a game day report."""
        ...

    def render_blast_radius(self) -> str:
        """Render current blast radius."""
        ...

    def render_fault_list(self) -> str:
        """Render available fault types."""
        ...

    def render_stats(self) -> str:
        """Render chaos subsystem statistics."""
        ...
```

---

## 9. Factory Function

```python
def create_fizzcontainerchaos_subsystem(
    cognitive_load_threshold: float = DEFAULT_COGNITIVE_LOAD_THRESHOLD,
    blast_radius_limit: float = DEFAULT_BLAST_RADIUS_LIMIT,
    blast_radius_scope: str = "global",
    observation_interval: float = DEFAULT_OBSERVATION_INTERVAL,
    steady_state_tolerance: float = DEFAULT_STEADY_STATE_TOLERANCE,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    container_registry: Optional[Dict[str, Any]] = None,
    event_bus: Optional[Any] = None,
) -> Tuple[ChaosExecutor, GameDayOrchestrator, FizzContainerChaosMiddleware]:
    """Create and wire the complete FizzContainerChaos subsystem.

    Factory function that instantiates the chaos executor with all
    fault injectors, the game day orchestrator, and the middleware,
    ready for integration into the FizzBuzz evaluation pipeline.

    Args:
        cognitive_load_threshold: NASA-TLX threshold for chaos gating.
        blast_radius_limit: Maximum fraction of containers affected.
        blast_radius_scope: Scope for blast radius calculation.
        observation_interval: Seconds between abort condition checks.
        steady_state_tolerance: Tolerance band for metric comparison.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable dashboard rendering.
        container_registry: Optional registry of active containers.
        event_bus: Optional event bus for chaos events.

    Returns:
        Tuple of (ChaosExecutor, GameDayOrchestrator, FizzContainerChaosMiddleware).
    """
    ...
```

---

## 10. Config Properties (~10)

Add to `enterprise_fizzbuzz/infrastructure/config.py`:

```python
    @property
    def fizzcontainerchaos_enabled(self) -> bool:
        """Whether container chaos engineering is enabled."""
        return self._raw_config.get("fizzcontainerchaos", {}).get("enabled", False)

    @property
    def fizzcontainerchaos_cognitive_load_threshold(self) -> float:
        """NASA-TLX threshold for chaos experiment gating."""
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("cognitive_load_threshold", 60.0))

    @property
    def fizzcontainerchaos_blast_radius_limit(self) -> float:
        """Maximum fraction of containers affected simultaneously."""
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("blast_radius_limit", 0.50))

    @property
    def fizzcontainerchaos_blast_radius_scope(self) -> str:
        """Scope for blast radius calculation."""
        return self._raw_config.get("fizzcontainerchaos", {}).get("blast_radius_scope", "global")

    @property
    def fizzcontainerchaos_observation_interval(self) -> float:
        """Seconds between abort condition checks."""
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("observation_interval", 5.0))

    @property
    def fizzcontainerchaos_steady_state_tolerance(self) -> float:
        """Tolerance band for steady-state metric comparison."""
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("steady_state_tolerance", 0.15))

    @property
    def fizzcontainerchaos_experiment_timeout(self) -> float:
        """Default experiment timeout in seconds."""
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("experiment_timeout", 300.0))

    @property
    def fizzcontainerchaos_gameday_timeout(self) -> float:
        """Default game day timeout in seconds."""
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("gameday_timeout", 1800.0))

    @property
    def fizzcontainerchaos_dashboard_width(self) -> int:
        """ASCII dashboard width."""
        return int(self._raw_config.get("fizzcontainerchaos", {}).get("dashboard", {}).get("width", 72))

    @property
    def fizzcontainerchaos_default_latency_ms(self) -> float:
        """Default network latency injection in milliseconds."""
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("default_latency_ms", 200.0))
```

---

## 11. YAML Config Section

Add to `config.yaml`:

```yaml
fizzcontainerchaos:
  enabled: false
  cognitive_load_threshold: 60.0
  blast_radius_limit: 0.50
  blast_radius_scope: "global"
  observation_interval: 5.0
  steady_state_tolerance: 0.15
  experiment_timeout: 300.0
  gameday_timeout: 1800.0
  default_latency_ms: 200.0
  dashboard:
    width: 72
```

---

## 12. CLI Flags (~8)

Add to `__main__.py` argparse section:

```python
    parser.add_argument(
        "--fizzcontainerchaos",
        action="store_true",
        help="Enable FizzContainerChaos: container-native chaos engineering with fault injection, game days, and cognitive load gating",
    )
    parser.add_argument(
        "--fizzcontainerchaos-run",
        type=str,
        default=None,
        metavar="EXPERIMENT",
        help="Run a chaos experiment (experiment name or YAML path)",
    )
    parser.add_argument(
        "--fizzcontainerchaos-gameday",
        type=str,
        default=None,
        metavar="GAMEDAY",
        help="Run a predefined game day (container_restart, network_partition, resource_exhaustion, full_outage)",
    )
    parser.add_argument(
        "--fizzcontainerchaos-status",
        action="store_true",
        help="Display active chaos experiments with status",
    )
    parser.add_argument(
        "--fizzcontainerchaos-abort",
        type=str,
        default=None,
        metavar="EXPERIMENT_ID",
        help="Abort a running chaos experiment by ID",
    )
    parser.add_argument(
        "--fizzcontainerchaos-report",
        type=str,
        default=None,
        metavar="EXPERIMENT_ID",
        help="Display chaos experiment report by ID",
    )
    parser.add_argument(
        "--fizzcontainerchaos-list-faults",
        action="store_true",
        help="List available fault types with configurable parameters",
    )
    parser.add_argument(
        "--fizzcontainerchaos-blast-radius",
        action="store_true",
        help="Show current blast radius across all active experiments",
    )
```

---

## 13. `__main__.py` Wiring

### 13.1 Import Block

```python
from enterprise_fizzbuzz.infrastructure.fizzcontainerchaos import (
    ChaosExecutor,
    GameDayOrchestrator,
    ContainerChaosDashboard,
    FizzContainerChaosMiddleware,
    PredefinedGameDays,
    create_fizzcontainerchaos_subsystem,
)
```

### 13.2 Initialization Block

```python
    # ----------------------------------------------------------------
    # FizzContainerChaos: Container-Native Chaos Engineering
    # ----------------------------------------------------------------
    chaos_executor_instance = None
    chaos_orchestrator_instance = None
    chaos_middleware_instance = None

    if (args.fizzcontainerchaos or args.fizzcontainerchaos_run or args.fizzcontainerchaos_gameday
            or args.fizzcontainerchaos_status or args.fizzcontainerchaos_abort
            or args.fizzcontainerchaos_report or args.fizzcontainerchaos_list_faults
            or args.fizzcontainerchaos_blast_radius):
        chaos_executor_instance, chaos_orchestrator_instance, chaos_middleware_instance = create_fizzcontainerchaos_subsystem(
            cognitive_load_threshold=config.fizzcontainerchaos_cognitive_load_threshold,
            blast_radius_limit=config.fizzcontainerchaos_blast_radius_limit,
            blast_radius_scope=config.fizzcontainerchaos_blast_radius_scope,
            observation_interval=config.fizzcontainerchaos_observation_interval,
            steady_state_tolerance=config.fizzcontainerchaos_steady_state_tolerance,
            dashboard_width=config.fizzcontainerchaos_dashboard_width,
            enable_dashboard=args.fizzcontainerchaos_status,
            event_bus=event_bus,
        )
        builder.with_middleware(chaos_middleware_instance)

        if not args.no_banner:
            print(
                "  +---------------------------------------------------------+\n"
                "  | FIZZCONTAINERCHAOS: CONTAINER-NATIVE CHAOS ENGINEERING  |\n"
                f"  | Blast Radius Limit: {config.fizzcontainerchaos_blast_radius_limit:<6.0%}  Cognitive Threshold: {config.fizzcontainerchaos_cognitive_load_threshold:<4.0f} |\n"
                "  | 8 fault types: kill, partition, CPU, memory, disk,      |\n"
                "  | image pull, DNS, latency | Game day orchestration       |\n"
                "  | Chaos Mesh v2.6 architecture                            |\n"
                "  +---------------------------------------------------------+"
            )
```

### 13.3 Post-Execution Rendering Block

```python
    # FizzContainerChaos Status (post-execution)
    if args.fizzcontainerchaos_status and chaos_middleware_instance is not None:
        print()
        print(chaos_middleware_instance.render_status())
    elif args.fizzcontainerchaos_status and chaos_middleware_instance is None:
        print("\n  FizzContainerChaos not enabled. Use --fizzcontainerchaos to enable.\n")

    # FizzContainerChaos List Faults (post-execution)
    if args.fizzcontainerchaos_list_faults and chaos_middleware_instance is not None:
        print()
        print(chaos_middleware_instance.render_fault_list())
    elif args.fizzcontainerchaos_list_faults and chaos_middleware_instance is None:
        print("\n  FizzContainerChaos not enabled. Use --fizzcontainerchaos to enable.\n")

    # FizzContainerChaos Blast Radius (post-execution)
    if args.fizzcontainerchaos_blast_radius and chaos_middleware_instance is not None:
        print()
        print(chaos_middleware_instance.render_blast_radius())
    elif args.fizzcontainerchaos_blast_radius and chaos_middleware_instance is None:
        print("\n  FizzContainerChaos not enabled. Use --fizzcontainerchaos to enable.\n")

    # FizzContainerChaos Report (post-execution)
    if args.fizzcontainerchaos_report and chaos_middleware_instance is not None:
        print()
        print(chaos_middleware_instance.render_report(args.fizzcontainerchaos_report))
    elif args.fizzcontainerchaos_report and chaos_middleware_instance is None:
        print("\n  FizzContainerChaos not enabled. Use --fizzcontainerchaos to enable.\n")

    # FizzContainerChaos Run Experiment (post-execution)
    if args.fizzcontainerchaos_run and chaos_executor_instance is not None:
        # Create and run experiment from the specified name/type
        from enterprise_fizzbuzz.infrastructure.fizzcontainerchaos import FaultType as CCFaultType
        fault_type_map = {ft.value: ft for ft in CCFaultType}
        if args.fizzcontainerchaos_run in fault_type_map:
            exp = ChaosExperiment(
                name=f"CLI {args.fizzcontainerchaos_run} experiment",
                fault_config=FaultConfig(fault_type=fault_type_map[args.fizzcontainerchaos_run]),
            )
            exp_id = chaos_executor_instance.register_experiment(exp)
            report = chaos_executor_instance.run_experiment(exp_id)
            print()
            print(chaos_middleware_instance.render_report(exp_id))

    # FizzContainerChaos Game Day (post-execution)
    if args.fizzcontainerchaos_gameday and chaos_orchestrator_instance is not None:
        gameday_map = {
            "container_restart": PredefinedGameDays.container_restart_resilience,
            "network_partition": PredefinedGameDays.network_partition_tolerance,
            "resource_exhaustion": PredefinedGameDays.resource_exhaustion,
            "full_outage": PredefinedGameDays.full_outage_recovery,
        }
        if args.fizzcontainerchaos_gameday in gameday_map:
            gameday = gameday_map[args.fizzcontainerchaos_gameday]()
            gd_id = chaos_orchestrator_instance.register_gameday(gameday)
            gd_report = chaos_orchestrator_instance.run_gameday(gd_id)
            print()
            print(chaos_middleware_instance.render_gameday_report(gd_id))

    # FizzContainerChaos Abort (post-execution)
    if args.fizzcontainerchaos_abort and chaos_executor_instance is not None:
        chaos_executor_instance.abort_experiment(args.fizzcontainerchaos_abort)
        print(f"\n  Experiment {args.fizzcontainerchaos_abort} aborted.\n")
```

---

## 14. Re-export Stub

Create `fizzcontainerchaos.py` at project root:

```python
"""Re-export stub for FizzContainerChaos.

Maintains backward compatibility by re-exporting the public API
from the canonical module location.
"""

from enterprise_fizzbuzz.infrastructure.fizzcontainerchaos import (  # noqa: F401
    AbortCondition,
    AbortReason,
    BlastRadiusCalculator,
    BlastRadiusScope,
    ChaosExperiment,
    ChaosExecutor,
    ChaosGate,
    ChaosSchedule,
    ContainerChaosDashboard,
    ContainerKillFault,
    CPUStressFault,
    DiskFillFault,
    DNSFailureFault,
    ExperimentReport,
    ExperimentStatus,
    FaultConfig,
    FaultRegistry,
    FaultType,
    FizzContainerChaosMiddleware,
    GameDay,
    GameDayOrchestrator,
    GameDayReport,
    GameDayStatus,
    ImagePullFailureFault,
    MemoryPressureFault,
    NetworkLatencyFault,
    NetworkPartitionFault,
    PredefinedGameDays,
    ScheduleMode,
    SteadyStateMetric,
    SteadyStateProbe,
    TargetResolver,
    create_fizzcontainerchaos_subsystem,
)
```

---

## 15. Test Classes

File: `tests/test_fizzcontainerchaos.py` (~400 lines, ~85 tests)

```python
class TestFaultType:
    """Test FaultType enum values and membership."""
    # ~3 tests

class TestExperimentStatus:
    """Test ExperimentStatus enum transitions."""
    # ~3 tests

class TestGameDayStatus:
    """Test GameDayStatus enum values."""
    # ~2 tests

class TestAbortReason:
    """Test AbortReason enum values."""
    # ~2 tests

class TestBlastRadiusScope:
    """Test BlastRadiusScope enum values."""
    # ~2 tests

class TestScheduleMode:
    """Test ScheduleMode enum values."""
    # ~2 tests

class TestFaultConfig:
    """Test FaultConfig dataclass defaults and construction."""
    # ~4 tests

class TestSteadyStateMetric:
    """Test SteadyStateMetric baseline/during/recovery values."""
    # ~3 tests

class TestAbortCondition:
    """Test AbortCondition operator evaluation."""
    # ~3 tests

class TestChaosExperiment:
    """Test ChaosExperiment lifecycle and timeline."""
    # ~4 tests

class TestExperimentReport:
    """Test ExperimentReport generation and hypothesis evaluation."""
    # ~3 tests

class TestGameDay:
    """Test GameDay composition and scheduling."""
    # ~3 tests

class TestGameDayReport:
    """Test GameDayReport aggregation."""
    # ~2 tests

class TestChaosSchedule:
    """Test ChaosSchedule cron expression handling."""
    # ~2 tests

class TestTargetResolver:
    """Test container target resolution from labels and IDs."""
    # ~5 tests (label matching, count limiting, no match error, specific ID, random selection)

class TestSteadyStateProbe:
    """Test steady-state measurement and violation detection."""
    # ~4 tests (baseline, during, recovery, violation check)

class TestBlastRadiusCalculator:
    """Test blast radius calculation and limit enforcement."""
    # ~5 tests (within limit, exceeded, add/remove affected, scope)

class TestContainerKillFault:
    """Test container kill injection and verification."""
    # ~3 tests

class TestNetworkPartitionFault:
    """Test network partition injection and removal."""
    # ~3 tests

class TestCPUStressFault:
    """Test CPU stress injection and throttle verification."""
    # ~3 tests

class TestMemoryPressureFault:
    """Test memory pressure injection and OOM verification."""
    # ~3 tests

class TestDiskFillFault:
    """Test disk fill injection and graceful failure."""
    # ~2 tests

class TestImagePullFailureFault:
    """Test image pull failure injection and backoff."""
    # ~2 tests

class TestDNSFailureFault:
    """Test DNS failure injection and retry behavior."""
    # ~2 tests

class TestNetworkLatencyFault:
    """Test network latency injection with jitter."""
    # ~2 tests

class TestFaultRegistry:
    """Test fault type to injector mapping."""
    # ~3 tests (lookup, list, all types registered)

class TestChaosExecutor:
    """Test the seven-phase experiment lifecycle."""
    # ~8 tests (register, run full lifecycle, abort, pre-check fail,
    #           cognitive load gate, blast radius check, report generation, list)

class TestChaosGate:
    """Test cognitive load gating."""
    # ~3 tests (permitted, blocked, emergency bypass)

class TestGameDayOrchestrator:
    """Test game day execution modes."""
    # ~5 tests (sequential, concurrent, staggered, abort, report)

class TestPredefinedGameDays:
    """Test predefined game day factory methods."""
    # ~4 tests (one per predefined scenario)

class TestContainerChaosDashboard:
    """Test ASCII dashboard rendering."""
    # ~4 tests (status, report, blast radius, fault list)

class TestFizzContainerChaosMiddleware:
    """Test middleware pipeline integration."""
    # ~4 tests (process with no active experiments, process with active experiment,
    #           priority, name)

class TestCreateFizzcontainerchaosSubsystem:
    """Test factory function wiring."""
    # ~2 tests (default config, custom config)
```

---

## 16. File Structure Summary

| File | Lines | Purpose |
|------|-------|---------|
| `enterprise_fizzbuzz/infrastructure/fizzcontainerchaos.py` | ~2,800 | Main module |
| `enterprise_fizzbuzz/domain/exceptions.py` | +~240 | 24 exception classes (EFP-CCH00 through EFP-CCH23) |
| `enterprise_fizzbuzz/domain/models.py` | +~16 | 15 EventType entries |
| `enterprise_fizzbuzz/infrastructure/config.py` | +~40 | 10 config properties |
| `enterprise_fizzbuzz/__main__.py` | +~80 | Import, argparse, init, rendering blocks |
| `config.yaml` | +~12 | YAML config section |
| `tests/test_fizzcontainerchaos.py` | ~400 | ~85 tests |
| `fizzcontainerchaos.py` (root) | ~40 | Re-export stub |

**Total new code**: ~3,600 lines (module + tests + integration)

---

## 17. Implementation Order

1. Exception classes in `exceptions.py`
2. EventType entries in `models.py`
3. Constants, enums, and dataclasses in `fizzcontainerchaos.py`
4. TargetResolver, SteadyStateProbe, BlastRadiusCalculator
5. Eight fault injector classes
6. FaultRegistry
7. ChaosGate
8. ChaosExecutor (seven-phase lifecycle)
9. GameDayOrchestrator + PredefinedGameDays
10. ContainerChaosDashboard
11. FizzContainerChaosMiddleware
12. Factory function
13. Config properties
14. CLI flags and `__main__.py` wiring
15. Re-export stub
16. Tests
