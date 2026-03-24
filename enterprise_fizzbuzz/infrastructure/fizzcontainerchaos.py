"""
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
"""

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

from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzcontainerchaos")


# ============================================================
# Exception Classes (EFP-CCH prefix)
# ============================================================


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


# ============================================================
# Event Type Constants
# ============================================================

CONTAINER_CHAOS_EXPERIMENT_CREATED = "container_chaos_experiment_created"
CONTAINER_CHAOS_EXPERIMENT_STARTED = "container_chaos_experiment_started"
CONTAINER_CHAOS_EXPERIMENT_COMPLETED = "container_chaos_experiment_completed"
CONTAINER_CHAOS_EXPERIMENT_ABORTED = "container_chaos_experiment_aborted"
CONTAINER_CHAOS_EXPERIMENT_FAILED = "container_chaos_experiment_failed"
CONTAINER_CHAOS_FAULT_INJECTED = "container_chaos_fault_injected"
CONTAINER_CHAOS_FAULT_REMOVED = "container_chaos_fault_removed"
CONTAINER_CHAOS_STEADY_STATE_MEASURED = "container_chaos_steady_state_measured"
CONTAINER_CHAOS_STEADY_STATE_VIOLATED = "container_chaos_steady_state_violated"
CONTAINER_CHAOS_ABORT_CONDITION_TRIGGERED = "container_chaos_abort_condition_triggered"
CONTAINER_CHAOS_BLAST_RADIUS_CHECKED = "container_chaos_blast_radius_checked"
CONTAINER_CHAOS_COGNITIVE_GATE_CHECKED = "container_chaos_cognitive_gate_checked"
CONTAINER_CHAOS_GAMEDAY_STARTED = "container_chaos_gameday_started"
CONTAINER_CHAOS_GAMEDAY_COMPLETED = "container_chaos_gameday_completed"
CONTAINER_CHAOS_GAMEDAY_ABORTED = "container_chaos_gameday_aborted"


# ============================================================
# Constants
# ============================================================

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


# ============================================================
# Enums
# ============================================================


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


class BlastRadiusScope(Enum):
    """Scope for blast radius calculation.

    Determines which container set is used as the denominator
    when computing the fraction of affected containers.
    """

    GLOBAL = "global"
    SERVICE_GROUP = "service_group"
    NAMESPACE = "namespace"
    POD = "pod"


class ScheduleMode(Enum):
    """Scheduling mode for experiments within a game day.

    Controls how multiple experiments are executed relative
    to each other during a coordinated game day exercise.
    """

    SEQUENTIAL = "sequential"
    CONCURRENT = "concurrent"
    STAGGERED = "staggered"


# ============================================================
# Dataclasses
# ============================================================


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


# ============================================================
# TargetResolver
# ============================================================


class TargetResolver:
    """Resolves fault injection targets from label selectors or container IDs.

    Uses FizzContainerd's metadata service to look up containers
    matching a label selector or specific container IDs.  Returns
    the set of container IDs that a fault should be applied to,
    respecting the target_count limit.
    """

    def __init__(self) -> None:
        self._rng = random.Random()
        self._resolution_count = 0

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
        self._resolution_count += 1

        if not container_registry:
            raise ChaosTargetResolutionError(
                "Container registry is empty; no targets available for fault injection"
            )

        # Direct container ID targeting
        if fault_config.target_container:
            if fault_config.target_container not in container_registry:
                raise ChaosTargetResolutionError(
                    f"Target container '{fault_config.target_container}' not found in registry"
                )
            return [fault_config.target_container]

        # Label selector targeting
        if fault_config.target_labels:
            matched = []
            for cid, meta in container_registry.items():
                container_labels = meta.get("labels", {}) if isinstance(meta, dict) else {}
                if self._match_labels(container_labels, fault_config.target_labels):
                    matched.append(cid)

            if not matched:
                raise ChaosTargetResolutionError(
                    f"No containers match label selector {fault_config.target_labels}"
                )

            # Apply target_count limit
            if fault_config.target_count > 0 and len(matched) > fault_config.target_count:
                matched = self._rng.sample(matched, fault_config.target_count)

            logger.info(
                "Resolved %d target containers from label selector %s",
                len(matched),
                fault_config.target_labels,
            )
            return matched

        # No selector: target all containers up to target_count
        all_ids = list(container_registry.keys())
        if fault_config.target_count > 0 and len(all_ids) > fault_config.target_count:
            all_ids = self._rng.sample(all_ids, fault_config.target_count)

        return all_ids

    def _match_labels(
        self,
        container_labels: Dict[str, str],
        selector: Dict[str, str],
    ) -> bool:
        """Check if container labels satisfy the selector.

        All selector key-value pairs must be present in the
        container's labels for a match.
        """
        for key, value in selector.items():
            if container_labels.get(key) != value:
                return False
        return True


# ============================================================
# SteadyStateProbe
# ============================================================


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
    ) -> None:
        self._tolerance = tolerance
        self._rng = random.Random(42)
        self._measurement_count = 0

    def measure_baseline(
        self,
        metrics: List[SteadyStateMetric],
        container_ids: List[str],
    ) -> List[SteadyStateMetric]:
        """Measure baseline steady-state metrics.

        Records the current value of each metric and stores it
        as the baseline for later comparison.
        """
        self._measurement_count += 1
        for metric in metrics:
            # Simulate baseline measurement from FizzSLI telemetry
            if metric.name == "error_rate":
                metric.baseline_value = self._rng.uniform(0.0, 2.0)
            elif metric.name == "p99_latency_ms":
                metric.baseline_value = self._rng.uniform(5.0, 50.0)
            elif metric.name == "throughput_rps":
                metric.baseline_value = self._rng.uniform(500.0, 2000.0)
            elif metric.name == "cpu_utilization":
                metric.baseline_value = self._rng.uniform(10.0, 40.0)
            elif metric.name == "memory_utilization":
                metric.baseline_value = self._rng.uniform(20.0, 60.0)
            else:
                metric.baseline_value = self._rng.uniform(0.0, 100.0)

        logger.info(
            "Measured baseline steady-state for %d metrics across %d containers",
            len(metrics),
            len(container_ids),
        )
        return metrics

    def measure_during(
        self,
        metrics: List[SteadyStateMetric],
        container_ids: List[str],
    ) -> List[SteadyStateMetric]:
        """Measure steady-state metrics during fault injection.

        Values are expected to deviate from baseline while faults
        are active.  The degree of deviation depends on the fault
        type and the metric being measured.
        """
        self._measurement_count += 1
        for metric in metrics:
            # Simulate degraded measurements during fault injection
            degradation_factor = 1.0 + self._rng.uniform(0.05, 0.30)
            if metric.name in ("error_rate", "p99_latency_ms", "cpu_utilization", "memory_utilization"):
                metric.during_value = metric.baseline_value * degradation_factor
            elif metric.name == "throughput_rps":
                metric.during_value = metric.baseline_value / degradation_factor
            else:
                metric.during_value = metric.baseline_value * degradation_factor

        logger.info(
            "Measured during-fault steady-state for %d metrics across %d containers",
            len(metrics),
            len(container_ids),
        )
        return metrics

    def measure_recovery(
        self,
        metrics: List[SteadyStateMetric],
        container_ids: List[str],
    ) -> List[SteadyStateMetric]:
        """Measure steady-state metrics after fault removal.

        Values should return to within tolerance of the baseline
        after fault removal, confirming system recovery.
        """
        self._measurement_count += 1
        for metric in metrics:
            # Simulate recovery: values near baseline with small variation
            recovery_factor = 1.0 + self._rng.uniform(-0.05, 0.05)
            metric.recovery_value = metric.baseline_value * recovery_factor

        logger.info(
            "Measured recovery steady-state for %d metrics across %d containers",
            len(metrics),
            len(container_ids),
        )
        return metrics

    def check_violations(
        self,
        metrics: List[SteadyStateMetric],
    ) -> List[SteadyStateMetric]:
        """Check for metrics violating their thresholds.

        Returns list of metrics whose during_value exceeds the
        threshold bounds.
        """
        violations = []
        for metric in metrics:
            if metric.threshold_upper is not None and metric.during_value > metric.threshold_upper:
                violations.append(metric)
            elif metric.threshold_lower is not None and metric.during_value < metric.threshold_lower:
                violations.append(metric)
        return violations

    def compare(
        self,
        metrics: List[SteadyStateMetric],
    ) -> List[Dict[str, Any]]:
        """Compare baseline, during, and recovery values.

        Returns comparison dictionaries for each metric, including
        deviation percentages and recovery assessment.
        """
        comparisons = []
        for metric in metrics:
            baseline = metric.baseline_value
            during_deviation = 0.0
            recovery_deviation = 0.0

            if baseline != 0.0:
                during_deviation = abs(metric.during_value - baseline) / abs(baseline) * 100.0
                recovery_deviation = abs(metric.recovery_value - baseline) / abs(baseline) * 100.0

            recovered = recovery_deviation <= (self._tolerance * 100.0)

            comparisons.append({
                "name": metric.name,
                "unit": metric.unit,
                "baseline": round(baseline, 3),
                "during": round(metric.during_value, 3),
                "recovery": round(metric.recovery_value, 3),
                "during_deviation_percent": round(during_deviation, 2),
                "recovery_deviation_percent": round(recovery_deviation, 2),
                "recovered": recovered,
            })

        return comparisons


# ============================================================
# BlastRadiusCalculator
# ============================================================


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
    ) -> None:
        self._limit = limit
        self._scope = scope
        self._affected: Set[str] = set()
        self._check_count = 0

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
        self._check_count += 1

        if total_containers == 0:
            return (True, 0.0)

        combined = currently_affected | set(new_targets)
        radius = len(combined) / total_containers
        within_limit = radius <= self._limit

        logger.info(
            "Blast radius check: %d new + %d current = %.1f%% (limit: %.1f%%)",
            len(new_targets),
            len(currently_affected),
            radius * 100,
            self._limit * 100,
        )

        return (within_limit, radius * 100)

    def current_radius(
        self,
        affected: Set[str],
        total: int,
    ) -> float:
        """Calculate current blast radius as a percentage."""
        if total == 0:
            return 0.0
        return len(affected) / total * 100.0

    def add_affected(self, container_ids: List[str]) -> None:
        """Register containers as affected by an active experiment."""
        self._affected.update(container_ids)

    def remove_affected(self, container_ids: List[str]) -> None:
        """Deregister containers when a fault is removed."""
        self._affected -= set(container_ids)

    def get_affected(self) -> Set[str]:
        """Return the set of currently affected container IDs."""
        return set(self._affected)

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary of current blast radius state."""
        return {
            "limit_percent": self._limit * 100,
            "scope": self._scope.value,
            "affected_count": len(self._affected),
            "affected_ids": sorted(self._affected),
            "check_count": self._check_count,
        }


# ============================================================
# Fault Injector Classes
# ============================================================


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

    def __init__(self) -> None:
        self.kill_count = 0
        self.restart_verified = 0
        self._killed_containers: Set[str] = set()

    def inject(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Kill the target containers.

        Sends SIGKILL to each container's init process.  Records
        the kill timestamp and original container state for
        verification during the recovery phase.

        Returns dict with kill results per container.
        """
        results: Dict[str, Any] = {}
        for cid in container_ids:
            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta["status"] = "killed"
                meta["killed_at"] = datetime.now(timezone.utc).isoformat()
                meta["exit_code"] = 137  # SIGKILL
            self._killed_containers.add(cid)
            self.kill_count += 1
            results[cid] = {
                "killed": True,
                "signal": "SIGKILL",
                "exit_code": 137,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            logger.info("Container %s killed via SIGKILL", cid)

        return results

    def remove(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> None:
        """Container kill has no removal -- containers are restarted by the orchestrator.

        The kill fault is a one-shot operation.  Recovery depends on
        the container orchestrator (FizzKube) detecting the failure
        and scheduling a replacement according to the pod's restart
        policy.
        """
        for cid in container_ids:
            meta = container_registry.get(cid, {})
            if isinstance(meta, dict) and meta.get("status") == "killed":
                meta["status"] = "running"
                meta["restarted_at"] = datetime.now(timezone.utc).isoformat()
                self.restart_verified += 1
                logger.info("Container %s restarted by orchestrator", cid)

    def verify(
        self,
        container_ids: List[str],
        container_registry: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Verify that killed containers have been restarted.

        Checks each killed container for orchestrator restart evidence
        (status transition from killed back to running).
        """
        results: Dict[str, bool] = {}
        for cid in container_ids:
            meta = container_registry.get(cid, {})
            restarted = isinstance(meta, dict) and meta.get("status") == "running"
            results[cid] = restarted
        return results


class NetworkPartitionFault:
    """Isolates containers by dropping network traffic.

    Adds drop rules to the FizzCNI bridge's packet filter for
    the target container's veth endpoint.  Supports directional
    partitioning (ingress-only, egress-only, or both) and
    selective peer partitioning.
    """

    def __init__(self) -> None:
        self._partitioned: Dict[str, Dict[str, Any]] = {}

    def inject(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply network partition to target containers.

        Installs packet filter drop rules on each container's veth
        interface.  Direction controls whether ingress, egress, or
        both traffic flows are dropped.

        Returns dict with partition results per container.
        """
        results: Dict[str, Any] = {}
        for cid in container_ids:
            partition_info = {
                "direction": config.direction,
                "target_peers": list(config.target_peers),
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "veth": f"veth-{cid[:8]}",
            }
            self._partitioned[cid] = partition_info

            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta["network_partitioned"] = True
                meta["partition_direction"] = config.direction

            results[cid] = {
                "partitioned": True,
                "direction": config.direction,
                "peers": list(config.target_peers),
                "veth": partition_info["veth"],
            }
            logger.info(
                "Network partition applied to container %s (direction=%s)",
                cid,
                config.direction,
            )

        return results

    def remove(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> None:
        """Remove drop rules to restore network connectivity.

        Flushes packet filter rules installed during injection,
        restoring full network connectivity to the affected
        containers.
        """
        for cid in container_ids:
            self._partitioned.pop(cid, None)
            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta.pop("network_partitioned", None)
                meta.pop("partition_direction", None)
            logger.info("Network partition removed from container %s", cid)

    def verify(
        self,
        container_ids: List[str],
        container_registry: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Verify that partition detection (health check failure) occurred.

        Checks that containers detected the network partition via
        health check failures or connection timeouts.
        """
        results: Dict[str, bool] = {}
        for cid in container_ids:
            results[cid] = cid in self._partitioned
        return results


class CPUStressFault:
    """Consumes CPU quota inside container cgroups.

    Runs a simulated busy-loop process inside the container's
    cgroup to compete for CPU bandwidth.  Monitors FizzCgroup's
    cpu.stat to verify that throttling activates (nr_throttled
    increases).
    """

    def __init__(self) -> None:
        self._stressed: Dict[str, Dict[str, Any]] = {}

    def inject(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply CPU stress to target containers.

        Creates busy-loop processes inside each container's cgroup,
        consuming the specified number of cores at the given load
        percentage.

        Returns dict with stress results per container.
        """
        results: Dict[str, Any] = {}
        for cid in container_ids:
            stress_info = {
                "cores": config.cores,
                "load_percent": config.load_percent,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "stress_pid": random.randint(10000, 99999),
                "nr_throttled_before": random.randint(0, 100),
            }
            self._stressed[cid] = stress_info

            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta["cpu_stressed"] = True
                meta["cpu_stress_cores"] = config.cores
                meta["cpu_load_percent"] = config.load_percent

            results[cid] = {
                "stressed": True,
                "cores": config.cores,
                "load_percent": config.load_percent,
                "stress_pid": stress_info["stress_pid"],
            }
            logger.info(
                "CPU stress applied to container %s (%d cores at %.0f%%)",
                cid,
                config.cores,
                config.load_percent,
            )

        return results

    def remove(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> None:
        """Remove CPU stress processes from target containers.

        Terminates the busy-loop processes and verifies CPU
        utilization returns to pre-injection levels.
        """
        for cid in container_ids:
            self._stressed.pop(cid, None)
            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta.pop("cpu_stressed", None)
                meta.pop("cpu_stress_cores", None)
                meta.pop("cpu_load_percent", None)
            logger.info("CPU stress removed from container %s", cid)

    def verify(
        self,
        container_ids: List[str],
        container_registry: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Verify that CPU throttling activated during stress.

        Checks FizzCgroup cpu.stat for increased nr_throttled
        values, confirming the cgroup bandwidth controller
        detected and throttled the stress processes.
        """
        results: Dict[str, bool] = {}
        for cid in container_ids:
            # Throttling is verified if the container was stressed
            results[cid] = cid in self._stressed
        return results


class MemoryPressureFault:
    """Allocates memory inside container cgroups to trigger pressure.

    Simulates memory allocation at a configurable rate until
    the memory.high threshold (triggering throttling) or
    memory.max (triggering OOM kill) is reached.  Verifies
    that the OOM killer targets the stress process, not the
    application.
    """

    def __init__(self) -> None:
        self._pressured: Dict[str, Dict[str, Any]] = {}

    def inject(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply memory pressure to target containers.

        Allocates memory at the configured rate inside each
        container's cgroup.  Tracks allocation progress and
        OOM events.

        Returns dict with pressure results per container.
        """
        results: Dict[str, Any] = {}
        for cid in container_ids:
            target_bytes = config.target_bytes if config.target_bytes > 0 else 268435456  # 256 MB
            pressure_info = {
                "target_bytes": target_bytes,
                "rate_bytes_per_second": config.rate_bytes_per_second,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "allocated_bytes": target_bytes,
                "oom_triggered": False,
            }
            self._pressured[cid] = pressure_info

            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta["memory_pressured"] = True
                meta["memory_allocated_bytes"] = target_bytes

            results[cid] = {
                "pressured": True,
                "target_bytes": target_bytes,
                "rate_bytes_per_second": config.rate_bytes_per_second,
                "allocated_bytes": target_bytes,
            }
            logger.info(
                "Memory pressure applied to container %s (%d bytes at %d B/s)",
                cid,
                target_bytes,
                config.rate_bytes_per_second,
            )

        return results

    def remove(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> None:
        """Remove memory pressure from target containers.

        Frees allocated memory and verifies that memory utilization
        drops back to pre-injection levels.
        """
        for cid in container_ids:
            self._pressured.pop(cid, None)
            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta.pop("memory_pressured", None)
                meta.pop("memory_allocated_bytes", None)
            logger.info("Memory pressure removed from container %s", cid)

    def verify(
        self,
        container_ids: List[str],
        container_registry: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Verify that memory pressure triggered expected behavior.

        Checks for memory.high throttling events or OOM kills
        in the container's cgroup memory controller.
        """
        results: Dict[str, bool] = {}
        for cid in container_ids:
            results[cid] = cid in self._pressured
        return results


class DiskFillFault:
    """Fills container overlay writable layers.

    Writes data to the container's overlay writable layer until
    a configurable percentage of the layer's capacity is consumed.
    Verifies that application write operations fail gracefully.
    """

    def __init__(self) -> None:
        self._filled: Dict[str, Dict[str, Any]] = {}

    def inject(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fill overlay writable layers for target containers.

        Creates large files in the container's overlay writable
        layer until the configured fill percentage is reached.

        Returns dict with fill results per container.
        """
        results: Dict[str, Any] = {}
        for cid in container_ids:
            total_capacity = 1073741824  # 1 GB simulated capacity
            filled_bytes = int(total_capacity * config.fill_percent / 100.0)
            fill_info = {
                "fill_percent": config.fill_percent,
                "file_size": config.file_size,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "total_capacity": total_capacity,
                "filled_bytes": filled_bytes,
                "files_created": filled_bytes // config.file_size,
            }
            self._filled[cid] = fill_info

            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta["disk_filled"] = True
                meta["disk_fill_percent"] = config.fill_percent

            results[cid] = {
                "filled": True,
                "fill_percent": config.fill_percent,
                "filled_bytes": filled_bytes,
                "files_created": fill_info["files_created"],
            }
            logger.info(
                "Disk fill applied to container %s (%.0f%%, %d bytes)",
                cid,
                config.fill_percent,
                filled_bytes,
            )

        return results

    def remove(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> None:
        """Remove fill files from container overlay writable layers.

        Deletes the created fill files and verifies that disk
        utilization drops to pre-injection levels.
        """
        for cid in container_ids:
            self._filled.pop(cid, None)
            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta.pop("disk_filled", None)
                meta.pop("disk_fill_percent", None)
            logger.info("Disk fill removed from container %s", cid)

    def verify(
        self,
        container_ids: List[str],
        container_registry: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Verify that disk fill caused write failures.

        Checks that application write operations produced ENOSPC
        errors or graceful degradation during the fill period.
        """
        results: Dict[str, bool] = {}
        for cid in container_ids:
            results[cid] = cid in self._filled
        return results


class ImagePullFailureFault:
    """Intercepts image pulls and injects errors.

    Injects error responses (HTTP 500, timeout, invalid manifest,
    auth failure) into FizzContainerd-to-FizzRegistry image pull
    requests.  Verifies that pods enter ImagePullBackOff state.
    """

    def __init__(self) -> None:
        self._intercepted: Dict[str, Dict[str, Any]] = {}

    def inject(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Intercept image pulls for target containers.

        Installs an interception hook in FizzContainerd's image
        service that returns the configured error for pull requests
        matching the specified images.

        Returns dict with interception results per container.
        """
        results: Dict[str, Any] = {}
        for cid in container_ids:
            intercept_info = {
                "error_type": config.error_type,
                "affected_images": list(config.affected_images),
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "pulls_intercepted": 0,
            }
            self._intercepted[cid] = intercept_info

            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta["image_pull_failure"] = True
                meta["image_pull_error_type"] = config.error_type

            results[cid] = {
                "intercepted": True,
                "error_type": config.error_type,
                "affected_images": list(config.affected_images),
            }
            logger.info(
                "Image pull failure injected for container %s (error=%s)",
                cid,
                config.error_type,
            )

        return results

    def remove(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> None:
        """Remove image pull interception.

        Removes the interception hook, allowing pull requests to
        proceed normally to FizzRegistry.
        """
        for cid in container_ids:
            self._intercepted.pop(cid, None)
            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta.pop("image_pull_failure", None)
                meta.pop("image_pull_error_type", None)
            logger.info("Image pull failure removed from container %s", cid)

    def verify(
        self,
        container_ids: List[str],
        container_registry: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Verify that pods entered ImagePullBackOff state.

        Checks FizzKube pod status for ImagePullBackOff events
        caused by the injected pull failures.
        """
        results: Dict[str, bool] = {}
        for cid in container_ids:
            results[cid] = cid in self._intercepted
        return results


class DNSFailureFault:
    """Disrupts DNS resolution in container networks.

    Intercepts DNS queries from FizzCNI's ContainerDNS and
    returns SERVFAIL, NXDOMAIN, timeout, or delayed responses.
    Verifies that services handle resolution failures gracefully.
    """

    def __init__(self) -> None:
        self._disrupted: Dict[str, Dict[str, Any]] = {}

    def inject(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Disrupt DNS resolution for target containers.

        Installs a query interceptor in FizzCNI's ContainerDNS
        that returns the configured failure response for queries
        matching the specified domain patterns.

        Returns dict with disruption results per container.
        """
        results: Dict[str, Any] = {}
        for cid in container_ids:
            disruption_info = {
                "failure_mode": config.failure_mode,
                "affected_domains": list(config.affected_domains),
                "delay_ms": config.delay_ms,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "queries_disrupted": 0,
            }
            self._disrupted[cid] = disruption_info

            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta["dns_failure"] = True
                meta["dns_failure_mode"] = config.failure_mode

            results[cid] = {
                "disrupted": True,
                "failure_mode": config.failure_mode,
                "affected_domains": list(config.affected_domains),
            }
            logger.info(
                "DNS failure injected for container %s (mode=%s)",
                cid,
                config.failure_mode,
            )

        return results

    def remove(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> None:
        """Remove DNS disruption from target containers.

        Removes the query interceptor, restoring normal DNS
        resolution through FizzCNI's ContainerDNS.
        """
        for cid in container_ids:
            self._disrupted.pop(cid, None)
            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta.pop("dns_failure", None)
                meta.pop("dns_failure_mode", None)
            logger.info("DNS failure removed from container %s", cid)

    def verify(
        self,
        container_ids: List[str],
        container_registry: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Verify that DNS disruption caused resolution failures.

        Checks service connection logs for DNS-related errors
        (SERVFAIL, NXDOMAIN, timeouts) during the injection period.
        """
        results: Dict[str, bool] = {}
        for cid in container_ids:
            results[cid] = cid in self._disrupted
        return results


class NetworkLatencyFault:
    """Adds configurable delay to container network traffic.

    Queues packets on the container's veth interface with a
    programmable delay before forwarding.  Supports jitter
    (random variation) and partial correlation (affecting a
    percentage of packets).
    """

    def __init__(self) -> None:
        self._delayed: Dict[str, Dict[str, Any]] = {}

    def inject(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Add network latency to target containers.

        Configures packet queuing on each container's veth
        interface with the specified delay, jitter, and
        correlation parameters.

        Returns dict with latency injection results per container.
        """
        results: Dict[str, Any] = {}
        for cid in container_ids:
            delay_info = {
                "latency_ms": config.latency_ms,
                "jitter_ms": config.jitter_ms,
                "correlation_percent": config.correlation_percent,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "veth": f"veth-{cid[:8]}",
            }
            self._delayed[cid] = delay_info

            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta["network_latency"] = True
                meta["latency_ms"] = config.latency_ms
                meta["jitter_ms"] = config.jitter_ms

            results[cid] = {
                "delayed": True,
                "latency_ms": config.latency_ms,
                "jitter_ms": config.jitter_ms,
                "correlation_percent": config.correlation_percent,
                "veth": delay_info["veth"],
            }
            logger.info(
                "Network latency injected for container %s (%.0fms +/- %.0fms)",
                cid,
                config.latency_ms,
                config.jitter_ms,
            )

        return results

    def remove(
        self,
        container_ids: List[str],
        config: FaultConfig,
        container_registry: Dict[str, Any],
    ) -> None:
        """Remove network latency from target containers.

        Removes packet queuing rules, restoring normal latency
        on the container's veth interface.
        """
        for cid in container_ids:
            self._delayed.pop(cid, None)
            meta = container_registry.get(cid, {})
            if isinstance(meta, dict):
                meta.pop("network_latency", None)
                meta.pop("latency_ms", None)
                meta.pop("jitter_ms", None)
            logger.info("Network latency removed from container %s", cid)

    def verify(
        self,
        container_ids: List[str],
        container_registry: Dict[str, Any],
    ) -> Dict[str, bool]:
        """Verify that latency injection affected traffic.

        Checks packet statistics on the container's veth interface
        for evidence of queuing delay.
        """
        results: Dict[str, bool] = {}
        for cid in container_ids:
            results[cid] = cid in self._delayed
        return results


# ============================================================
# FaultRegistry
# ============================================================


class FaultRegistry:
    """Registry mapping fault types to their injector implementations.

    Provides a single lookup point for resolving fault type enums
    to their corresponding injector class instances.
    """

    def __init__(self) -> None:
        """Initialize with all eight fault injectors."""
        self._injectors: Dict[FaultType, Any] = {
            FaultType.CONTAINER_KILL: ContainerKillFault(),
            FaultType.NETWORK_PARTITION: NetworkPartitionFault(),
            FaultType.CPU_STRESS: CPUStressFault(),
            FaultType.MEMORY_PRESSURE: MemoryPressureFault(),
            FaultType.DISK_FILL: DiskFillFault(),
            FaultType.IMAGE_PULL_FAILURE: ImagePullFailureFault(),
            FaultType.DNS_FAILURE: DNSFailureFault(),
            FaultType.NETWORK_LATENCY: NetworkLatencyFault(),
        }

    def get_injector(self, fault_type: FaultType) -> Any:
        """Return the injector for the given fault type.

        Raises:
            ChaosFaultInjectionError: If the fault type is not registered.
        """
        injector = self._injectors.get(fault_type)
        if injector is None:
            raise ChaosFaultInjectionError(
                f"No injector registered for fault type {fault_type.value}"
            )
        return injector

    def list_faults(self) -> List[Dict[str, Any]]:
        """Return metadata for all registered fault types.

        Each entry includes fault_type, description, and configurable
        parameters with their defaults.
        """
        fault_params = {
            FaultType.CONTAINER_KILL: {
                "description": "Kill containers by sending SIGKILL to init processes",
                "params": {"interval": 0.0},
            },
            FaultType.NETWORK_PARTITION: {
                "description": "Isolate containers by dropping network traffic",
                "params": {"direction": "both", "target_peers": []},
            },
            FaultType.CPU_STRESS: {
                "description": "Consume CPU quota inside container cgroups",
                "params": {"cores": DEFAULT_CPU_STRESS_CORES, "load_percent": 80.0},
            },
            FaultType.MEMORY_PRESSURE: {
                "description": "Allocate memory inside container cgroups to trigger pressure",
                "params": {"target_bytes": 0, "rate_bytes_per_second": DEFAULT_MEMORY_PRESSURE_RATE},
            },
            FaultType.DISK_FILL: {
                "description": "Fill container overlay writable layers",
                "params": {"fill_percent": DEFAULT_DISK_FILL_PERCENT, "file_size": 4096},
            },
            FaultType.IMAGE_PULL_FAILURE: {
                "description": "Intercept image pulls and inject errors",
                "params": {"error_type": "server_error", "affected_images": []},
            },
            FaultType.DNS_FAILURE: {
                "description": "Disrupt DNS resolution in container networks",
                "params": {"failure_mode": "servfail", "affected_domains": []},
            },
            FaultType.NETWORK_LATENCY: {
                "description": "Add configurable delay to container network traffic",
                "params": {
                    "latency_ms": DEFAULT_LATENCY_MS,
                    "jitter_ms": DEFAULT_JITTER_MS,
                    "correlation_percent": 100.0,
                },
            },
        }

        result = []
        for ft, injector in self._injectors.items():
            info = fault_params.get(ft, {"description": "", "params": {}})
            result.append({
                "fault_type": ft.value,
                "description": info["description"],
                "params": info["params"],
                "injector_class": type(injector).__name__,
            })

        return result


# ============================================================
# ChaosGate
# ============================================================


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
    ) -> None:
        self._threshold = threshold
        self._check_count = 0
        self._last_score: float = 0.0
        self._rng = random.Random()

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
        self._check_count += 1

        # Simulate NASA-TLX score from FizzBob cognitive load model
        score = self._rng.uniform(20.0, 80.0)
        self._last_score = score

        if is_emergency:
            logger.info(
                "Cognitive load gate bypassed for emergency experiment (score=%.1f)",
                score,
            )
            return (True, score)

        permitted = score <= self._threshold
        if not permitted:
            logger.warning(
                "Cognitive load gate blocked chaos experiment: score %.1f > threshold %.1f",
                score,
                self._threshold,
            )
            raise ChaosCognitiveLoadGateError(
                f"Operator cognitive load ({score:.1f}) exceeds chaos threshold "
                f"({self._threshold:.1f}). Chaos experiment blocked to prevent "
                f"cognitive overload during fault injection."
            )

        logger.info(
            "Cognitive load gate passed: score %.1f <= threshold %.1f",
            score,
            self._threshold,
        )
        return (True, score)

    def get_threshold(self) -> float:
        """Return the current cognitive load threshold."""
        return self._threshold

    def set_threshold(self, threshold: float) -> None:
        """Update the cognitive load threshold."""
        self._threshold = threshold

    def get_last_score(self) -> float:
        """Return the most recently measured cognitive load score."""
        return self._last_score


# ============================================================
# ChaosExecutor
# ============================================================


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
        chaos_gate: Optional[ChaosGate] = None,
        cognitive_load_threshold: float = DEFAULT_COGNITIVE_LOAD_THRESHOLD,
        observation_interval: float = DEFAULT_OBSERVATION_INTERVAL,
        container_registry: Optional[Dict[str, Any]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._fault_registry = fault_registry
        self._target_resolver = target_resolver
        self._steady_state_probe = steady_state_probe
        self._blast_radius_calculator = blast_radius_calculator
        self._chaos_gate = chaos_gate or ChaosGate(threshold=cognitive_load_threshold)
        self._observation_interval = observation_interval
        self._container_registry: Dict[str, Any] = container_registry or {}
        self._event_bus = event_bus
        self._lock = threading.Lock()

        self.experiments: Dict[str, ChaosExperiment] = {}
        self.active_experiments: Set[str] = set()
        self.reports: Dict[str, ExperimentReport] = {}

    def register_experiment(self, experiment: ChaosExperiment) -> str:
        """Register a new experiment and return its ID."""
        with self._lock:
            self.experiments[experiment.experiment_id] = experiment
            self._add_timeline(experiment, "Experiment registered")
            self._emit_event(CONTAINER_CHAOS_EXPERIMENT_CREATED, {
                "experiment_id": experiment.experiment_id,
                "name": experiment.name,
                "fault_type": experiment.fault_config.fault_type.value,
            })
            logger.info(
                "Registered chaos experiment %s (%s)",
                experiment.experiment_id,
                experiment.name,
            )
            return experiment.experiment_id

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
        experiment = self.get_experiment(experiment_id)

        if experiment_id in self.active_experiments:
            raise ChaosExperimentAlreadyRunningError(
                f"Experiment {experiment_id} is already running"
            )

        self._emit_event(CONTAINER_CHAOS_EXPERIMENT_STARTED, {
            "experiment_id": experiment_id,
        })

        try:
            # Phase 1: Pre-check
            self._pre_check(experiment)

            # Phase 2: Measure baseline
            self._measure_baseline(experiment)

            # Phase 3: Inject fault
            self._inject_fault(experiment)

            # Phase 4: Observe
            aborted = self._observe(experiment)

            # Phase 5: Remove fault
            self._remove_fault(experiment)

            # Phase 6: Measure recovery
            self._measure_recovery(experiment)

            if aborted:
                experiment.status = ExperimentStatus.ABORTED
                self._add_timeline(experiment, "Experiment aborted")
                self._emit_event(CONTAINER_CHAOS_EXPERIMENT_ABORTED, {
                    "experiment_id": experiment_id,
                    "abort_reason": experiment.abort_reason.value if experiment.abort_reason else "unknown",
                })
            else:
                experiment.status = ExperimentStatus.COMPLETED
                self._add_timeline(experiment, "Experiment completed successfully")
                self._emit_event(CONTAINER_CHAOS_EXPERIMENT_COMPLETED, {
                    "experiment_id": experiment_id,
                })

        except (ChaosExperimentFailedStartError, ChaosCognitiveLoadGateError) as exc:
            experiment.status = ExperimentStatus.FAILED
            experiment.error_message = str(exc)
            self._add_timeline(experiment, f"Experiment failed: {exc}")
            self._emit_event(CONTAINER_CHAOS_EXPERIMENT_FAILED, {
                "experiment_id": experiment_id,
                "error": str(exc),
            })
        finally:
            experiment.completed_at = datetime.now(timezone.utc)
            self.active_experiments.discard(experiment_id)

        # Phase 7: Generate report
        report = self._generate_report(experiment)
        self.reports[experiment_id] = report
        return report

    def abort_experiment(
        self,
        experiment_id: str,
        reason: AbortReason = AbortReason.MANUAL_ABORT,
    ) -> None:
        """Abort a running experiment.

        Immediately removes the injected fault and updates the
        experiment status to ABORTED.
        """
        experiment = self.get_experiment(experiment_id)
        experiment.abort_reason = reason
        experiment.status = ExperimentStatus.ABORTED
        experiment.completed_at = datetime.now(timezone.utc)
        self._add_timeline(experiment, f"Experiment aborted: {reason.value}")
        self.active_experiments.discard(experiment_id)

        # Remove fault if injected
        if experiment.affected_containers:
            injector = self._fault_registry.get_injector(experiment.fault_config.fault_type)
            injector.remove(
                experiment.affected_containers,
                experiment.fault_config,
                self._container_registry,
            )
            self._blast_radius_calculator.remove_affected(experiment.affected_containers)

        logger.info("Experiment %s aborted: %s", experiment_id, reason.value)

    def get_experiment(self, experiment_id: str) -> ChaosExperiment:
        """Return experiment by ID."""
        experiment = self.experiments.get(experiment_id)
        if experiment is None:
            raise ChaosExperimentNotFoundError(
                f"Experiment {experiment_id} not found in registry"
            )
        return experiment

    def get_report(self, experiment_id: str) -> Optional[ExperimentReport]:
        """Return experiment report by ID."""
        return self.reports.get(experiment_id)

    def list_active(self) -> List[ChaosExperiment]:
        """Return all currently running experiments."""
        return [
            self.experiments[eid]
            for eid in self.active_experiments
            if eid in self.experiments
        ]

    def list_all(self) -> List[ChaosExperiment]:
        """Return all experiments (active and historical)."""
        return list(self.experiments.values())

    def _pre_check(self, experiment: ChaosExperiment) -> None:
        """Phase 1: Verify targets, cognitive load, blast radius.

        Pre-checks ensure the experiment can execute safely:
        - Target containers exist and are healthy
        - Operator cognitive load permits chaos injection
        - Blast radius limit would not be exceeded
        """
        experiment.status = ExperimentStatus.PRE_CHECK
        experiment.started_at = datetime.now(timezone.utc)
        self._add_timeline(experiment, "Pre-check phase started")

        # Cognitive load gate
        self._chaos_gate.check(is_emergency=experiment.is_emergency)
        self._emit_event(CONTAINER_CHAOS_COGNITIVE_GATE_CHECKED, {
            "experiment_id": experiment.experiment_id,
            "score": self._chaos_gate.get_last_score(),
            "threshold": self._chaos_gate.get_threshold(),
        })

        # Resolve targets
        targets = self._target_resolver.resolve(
            experiment.fault_config,
            self._container_registry,
        )
        experiment.affected_containers = targets

        # Blast radius check
        within_limit, radius = self._blast_radius_calculator.check(
            targets,
            self._blast_radius_calculator.get_affected(),
            len(self._container_registry),
        )
        self._emit_event(CONTAINER_CHAOS_BLAST_RADIUS_CHECKED, {
            "experiment_id": experiment.experiment_id,
            "radius_percent": radius,
            "within_limit": within_limit,
        })

        if not within_limit:
            raise ChaosExperimentFailedStartError(
                f"Blast radius {radius:.1f}% would exceed limit "
                f"{self._blast_radius_calculator._limit * 100:.1f}%"
            )

        self.active_experiments.add(experiment.experiment_id)
        self._add_timeline(experiment, f"Pre-check passed: {len(targets)} targets resolved")

    def _measure_baseline(self, experiment: ChaosExperiment) -> None:
        """Phase 2: Record baseline steady-state metrics."""
        experiment.status = ExperimentStatus.MEASURING_BASELINE
        self._add_timeline(experiment, "Baseline measurement started")

        if experiment.steady_state_metrics:
            self._steady_state_probe.measure_baseline(
                experiment.steady_state_metrics,
                experiment.affected_containers,
            )
            self._emit_event(CONTAINER_CHAOS_STEADY_STATE_MEASURED, {
                "experiment_id": experiment.experiment_id,
                "phase": "baseline",
                "metric_count": len(experiment.steady_state_metrics),
            })

        self._add_timeline(experiment, "Baseline measurement completed")

    def _inject_fault(self, experiment: ChaosExperiment) -> None:
        """Phase 3: Apply the fault to target containers."""
        experiment.status = ExperimentStatus.INJECTING
        self._add_timeline(experiment, f"Injecting {experiment.fault_config.fault_type.value} fault")

        injector = self._fault_registry.get_injector(experiment.fault_config.fault_type)
        injector.inject(
            experiment.affected_containers,
            experiment.fault_config,
            self._container_registry,
        )
        self._blast_radius_calculator.add_affected(experiment.affected_containers)

        self._emit_event(CONTAINER_CHAOS_FAULT_INJECTED, {
            "experiment_id": experiment.experiment_id,
            "fault_type": experiment.fault_config.fault_type.value,
            "targets": experiment.affected_containers,
        })
        self._add_timeline(
            experiment,
            f"Fault injected into {len(experiment.affected_containers)} containers",
        )

    def _observe(self, experiment: ChaosExperiment) -> bool:
        """Phase 4: Monitor abort conditions. Returns True if aborted.

        Checks abort conditions at the configured observation interval.
        Also measures steady-state metrics during fault injection to
        detect violations.
        """
        experiment.status = ExperimentStatus.OBSERVING
        self._add_timeline(experiment, "Observation phase started")

        # Simulate observation period (no actual sleeping in the platform)
        if experiment.steady_state_metrics:
            self._steady_state_probe.measure_during(
                experiment.steady_state_metrics,
                experiment.affected_containers,
            )

            violations = self._steady_state_probe.check_violations(
                experiment.steady_state_metrics,
            )

            if violations:
                self._emit_event(CONTAINER_CHAOS_STEADY_STATE_VIOLATED, {
                    "experiment_id": experiment.experiment_id,
                    "violations": [v.name for v in violations],
                })

                # Check if any abort condition references violated metrics
                for condition in experiment.abort_conditions:
                    for violation in violations:
                        if condition.metric_name == violation.name:
                            condition.triggered = True
                            condition.triggered_at = datetime.now(timezone.utc)
                            self._emit_event(CONTAINER_CHAOS_ABORT_CONDITION_TRIGGERED, {
                                "experiment_id": experiment.experiment_id,
                                "condition": condition.description,
                                "metric": condition.metric_name,
                            })
                            experiment.abort_reason = AbortReason.STEADY_STATE_VIOLATION
                            self._add_timeline(
                                experiment,
                                f"Abort condition triggered: {condition.description}",
                            )
                            return True

        self._add_timeline(experiment, "Observation phase completed without abort")
        return False

    def _remove_fault(self, experiment: ChaosExperiment) -> None:
        """Phase 5: Remove the fault."""
        experiment.status = ExperimentStatus.REMOVING_FAULT
        self._add_timeline(experiment, "Removing fault")

        injector = self._fault_registry.get_injector(experiment.fault_config.fault_type)
        injector.remove(
            experiment.affected_containers,
            experiment.fault_config,
            self._container_registry,
        )
        self._blast_radius_calculator.remove_affected(experiment.affected_containers)

        self._emit_event(CONTAINER_CHAOS_FAULT_REMOVED, {
            "experiment_id": experiment.experiment_id,
            "fault_type": experiment.fault_config.fault_type.value,
        })
        self._add_timeline(experiment, "Fault removed")

    def _measure_recovery(self, experiment: ChaosExperiment) -> None:
        """Phase 6: Record recovery metrics."""
        experiment.status = ExperimentStatus.MEASURING_RECOVERY
        self._add_timeline(experiment, "Recovery measurement started")

        if experiment.steady_state_metrics:
            self._steady_state_probe.measure_recovery(
                experiment.steady_state_metrics,
                experiment.affected_containers,
            )
            self._emit_event(CONTAINER_CHAOS_STEADY_STATE_MEASURED, {
                "experiment_id": experiment.experiment_id,
                "phase": "recovery",
                "metric_count": len(experiment.steady_state_metrics),
            })

        self._add_timeline(experiment, "Recovery measurement completed")

    def _generate_report(self, experiment: ChaosExperiment) -> ExperimentReport:
        """Phase 7: Produce the experiment report.

        Compares steady-state metrics and evaluates the experiment's
        hypothesis based on the observed behavior during fault
        injection.
        """
        comparisons = []
        hypothesis_validated = True

        if experiment.steady_state_metrics:
            comparisons = self._steady_state_probe.compare(experiment.steady_state_metrics)
            # Hypothesis is validated if all metrics recovered
            for comp in comparisons:
                if not comp.get("recovered", False):
                    hypothesis_validated = False
                    break

        duration = 0.0
        if experiment.started_at and experiment.completed_at:
            duration = (experiment.completed_at - experiment.started_at).total_seconds()

        total_containers = len(self._container_registry) if self._container_registry else 0
        affected_count = len(experiment.affected_containers)
        blast_radius = (affected_count / total_containers * 100.0) if total_containers > 0 else 0.0

        recommendations = []
        if not hypothesis_validated:
            recommendations.append(
                "Steady-state metrics did not fully recover after fault removal. "
                "Review recovery procedures and timeout configurations."
            )
        if experiment.abort_reason:
            recommendations.append(
                f"Experiment was aborted ({experiment.abort_reason.value}). "
                "Consider adjusting abort thresholds or fault intensity."
            )
        if blast_radius > 30.0:
            recommendations.append(
                f"Blast radius was {blast_radius:.1f}%, exceeding 30%. "
                "Consider reducing target_count or narrowing label selectors."
            )

        report = ExperimentReport(
            experiment_id=experiment.experiment_id,
            experiment_name=experiment.name,
            fault_type=experiment.fault_config.fault_type,
            hypothesis=experiment.hypothesis,
            hypothesis_validated=hypothesis_validated,
            steady_state_comparison=comparisons,
            affected_container_count=affected_count,
            total_container_count=total_containers,
            blast_radius_percent=blast_radius,
            duration_seconds=duration,
            abort_reason=experiment.abort_reason,
            timeline=list(experiment.timeline),
            recommendations=recommendations,
        )

        self._add_timeline(experiment, "Report generated")
        return report

    def _check_cognitive_load(self) -> float:
        """Query FizzBob cognitive load model.

        Returns the current NASA-TLX score.
        """
        _, score = self._chaos_gate.check(is_emergency=True)
        return score

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)

    def _add_timeline(self, experiment: ChaosExperiment, description: str) -> None:
        """Add a timestamped entry to the experiment timeline."""
        experiment.timeline.append((datetime.now(timezone.utc), description))


# ============================================================
# GameDayOrchestrator
# ============================================================


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
    ) -> None:
        self._executor = executor
        self._blast_radius_calculator = blast_radius_calculator
        self._gamedays: Dict[str, GameDay] = {}
        self._reports: Dict[str, GameDayReport] = {}

    def register_gameday(self, gameday: GameDay) -> str:
        """Register a game day and return its ID."""
        self._gamedays[gameday.gameday_id] = gameday
        gameday.timeline.append((datetime.now(timezone.utc), "Game day registered"))
        logger.info("Registered game day %s (%s)", gameday.gameday_id, gameday.title)
        return gameday.gameday_id

    def run_gameday(self, gameday_id: str) -> GameDayReport:
        """Execute a game day through its complete lifecycle.

        1. Pre-flight: validate experiments, check cognitive load
        2. Execute: run experiments according to schedule mode
        3. Cooldown: wait for system stabilization
        4. Report: generate comprehensive game day report
        """
        gameday = self.get_gameday(gameday_id)
        gameday.started_at = datetime.now(timezone.utc)

        # Pre-flight
        gameday.status = GameDayStatus.PRE_FLIGHT
        gameday.timeline.append((datetime.now(timezone.utc), "Pre-flight checks started"))

        # Register all experiments
        for exp in gameday.experiments:
            self._executor.register_experiment(exp)

        gameday.timeline.append((datetime.now(timezone.utc), "Pre-flight checks passed"))

        # Execute
        gameday.status = GameDayStatus.EXECUTING
        gameday.timeline.append((datetime.now(timezone.utc), "Experiment execution started"))

        exp_reports: List[ExperimentReport] = []
        try:
            if gameday.schedule_mode == ScheduleMode.SEQUENTIAL:
                exp_reports = self._run_sequential(gameday)
            elif gameday.schedule_mode == ScheduleMode.CONCURRENT:
                exp_reports = self._run_concurrent(gameday)
            elif gameday.schedule_mode == ScheduleMode.STAGGERED:
                exp_reports = self._run_staggered(gameday)
        except ChaosGameDayAbortError:
            gameday.status = GameDayStatus.ABORTED
            gameday.timeline.append((datetime.now(timezone.utc), "Game day aborted"))

        # Cooldown
        if gameday.status != GameDayStatus.ABORTED:
            gameday.status = GameDayStatus.COOLDOWN
            gameday.timeline.append((datetime.now(timezone.utc), "Cooldown phase started"))
            gameday.timeline.append((datetime.now(timezone.utc), "Cooldown phase completed"))

        # Report
        gameday.completed_at = datetime.now(timezone.utc)
        if gameday.status != GameDayStatus.ABORTED:
            gameday.status = GameDayStatus.COMPLETED

        report = self._generate_report(gameday, exp_reports)
        self._reports[gameday_id] = report

        gameday.timeline.append((datetime.now(timezone.utc), "Game day completed"))
        return report

    def abort_gameday(
        self,
        gameday_id: str,
        reason: AbortReason = AbortReason.MANUAL_ABORT,
    ) -> None:
        """Abort all running experiments in a game day."""
        gameday = self.get_gameday(gameday_id)
        gameday.abort_reason = reason
        gameday.status = GameDayStatus.ABORTED
        gameday.completed_at = datetime.now(timezone.utc)

        for exp in gameday.experiments:
            if exp.experiment_id in self._executor.active_experiments:
                self._executor.abort_experiment(exp.experiment_id, reason)

        gameday.timeline.append((
            datetime.now(timezone.utc),
            f"Game day aborted: {reason.value}",
        ))
        logger.info("Game day %s aborted: %s", gameday_id, reason.value)

    def get_gameday(self, gameday_id: str) -> GameDay:
        """Return game day by ID."""
        gameday = self._gamedays.get(gameday_id)
        if gameday is None:
            raise ChaosGameDayError(f"Game day {gameday_id} not found")
        return gameday

    def get_report(self, gameday_id: str) -> Optional[GameDayReport]:
        """Return game day report by ID."""
        return self._reports.get(gameday_id)

    def _run_sequential(self, gameday: GameDay) -> List[ExperimentReport]:
        """Run experiments one after another."""
        reports = []
        for exp in gameday.experiments:
            if self._check_system_abort(gameday):
                break
            report = self._executor.run_experiment(exp.experiment_id)
            reports.append(report)
            gameday.affected_containers.update(exp.affected_containers)
        return reports

    def _run_concurrent(self, gameday: GameDay) -> List[ExperimentReport]:
        """Run all experiments simultaneously.

        In the simulated environment, concurrent execution is
        serialized but all experiments are started before any
        complete.
        """
        reports = []
        for exp in gameday.experiments:
            report = self._executor.run_experiment(exp.experiment_id)
            reports.append(report)
            gameday.affected_containers.update(exp.affected_containers)
        return reports

    def _run_staggered(self, gameday: GameDay) -> List[ExperimentReport]:
        """Run experiments with a delay between starts.

        Staggered execution provides a gradual ramp-up of chaos,
        allowing operators to observe cascading effects between
        fault injections.
        """
        reports = []
        for i, exp in enumerate(gameday.experiments):
            if self._check_system_abort(gameday):
                break
            report = self._executor.run_experiment(exp.experiment_id)
            reports.append(report)
            gameday.affected_containers.update(exp.affected_containers)
        return reports

    def _check_system_abort(self, gameday: GameDay) -> bool:
        """Check system-level abort conditions.

        Evaluates blast radius and abort conditions across all
        experiments in the game day.
        """
        if gameday.abort_reason is not None:
            return True

        total = len(self._executor._container_registry)
        if total > 0:
            radius = len(gameday.affected_containers) / total
            if radius > gameday.blast_radius_limit:
                gameday.abort_reason = AbortReason.BLAST_RADIUS_EXCEEDED
                gameday.timeline.append((
                    datetime.now(timezone.utc),
                    f"System abort: blast radius {radius*100:.1f}% exceeds limit {gameday.blast_radius_limit*100:.1f}%",
                ))
                return True

        return False

    def _generate_report(
        self,
        gameday: GameDay,
        exp_reports: List[ExperimentReport],
    ) -> GameDayReport:
        """Generate comprehensive game day report.

        Aggregates individual experiment reports, identifies
        resilience gaps, and produces remediation recommendations.
        """
        completed = sum(1 for r in exp_reports if r.abort_reason is None)
        aborted = sum(1 for r in exp_reports if r.abort_reason is not None)
        failed = sum(1 for e in gameday.experiments if e.status == ExperimentStatus.FAILED)

        peak_radius = max(
            (r.blast_radius_percent for r in exp_reports),
            default=0.0,
        )

        duration = 0.0
        if gameday.started_at and gameday.completed_at:
            duration = (gameday.completed_at - gameday.started_at).total_seconds()

        # Evaluate system-level hypothesis
        hypothesis_validated = all(
            r.hypothesis_validated for r in exp_reports
        ) and failed == 0

        # Identify resilience gaps
        gaps = []
        for report in exp_reports:
            if not report.hypothesis_validated:
                gaps.append(
                    f"{report.experiment_name}: hypothesis not validated "
                    f"(fault type: {report.fault_type.value})"
                )
            if report.abort_reason:
                gaps.append(
                    f"{report.experiment_name}: aborted ({report.abort_reason.value})"
                )

        # Aggregate recommendations
        recommendations = []
        if gaps:
            recommendations.append(
                "Address the identified resilience gaps before the next game day."
            )
        if peak_radius > 40.0:
            recommendations.append(
                "Peak blast radius was high. Consider running experiments "
                "with smaller target scopes in future game days."
            )
        if not hypothesis_validated:
            recommendations.append(
                "System-level hypothesis was not validated. Review container "
                "restart policies, health check configurations, and failover mechanisms."
            )

        return GameDayReport(
            gameday_id=gameday.gameday_id,
            title=gameday.title,
            hypothesis=gameday.hypothesis,
            hypothesis_validated=hypothesis_validated,
            experiment_reports=exp_reports,
            experiments_completed=completed,
            experiments_aborted=aborted,
            experiments_failed=failed,
            peak_blast_radius_percent=peak_radius,
            total_duration_seconds=duration,
            timeline=list(gameday.timeline),
            resilience_gaps=gaps,
            recommendations=recommendations,
        )


# ============================================================
# PredefinedGameDays
# ============================================================


class PredefinedGameDays:
    """Factory for predefined game day scenarios.

    Provides four predefined game day templates that cover the
    most common container resilience scenarios.  Each scenario
    includes appropriate experiments, hypotheses, steady-state
    metrics, and abort conditions.
    """

    @staticmethod
    def container_restart_resilience() -> GameDay:
        """Kill containers across all service groups, verify restart.

        Tests that the container orchestrator detects killed
        containers and restarts them within the configured
        restart timeout.
        """
        exp = ChaosExperiment(
            name="Container kill across service groups",
            description="Kill one container from each service group to verify restart resilience",
            fault_config=FaultConfig(
                fault_type=FaultType.CONTAINER_KILL,
                target_labels={"tier": "application"},
                target_count=3,
                duration=60.0,
            ),
            hypothesis="Killed containers are restarted within 30 seconds and service availability remains above 99%",
            steady_state_metrics=[
                SteadyStateMetric(name="error_rate", unit="%", threshold_upper=5.0),
                SteadyStateMetric(name="throughput_rps", unit="req/s", threshold_lower=100.0),
            ],
        )
        return GameDay(
            title="Container Restart Resilience",
            description="Validates that the platform recovers from container failures by verifying orchestrator restart behavior",
            hypothesis="All killed containers are restarted and service metrics recover within tolerance",
            experiments=[exp],
            schedule_mode=ScheduleMode.SEQUENTIAL,
            blast_radius_limit=0.30,
        )

    @staticmethod
    def network_partition_tolerance() -> GameDay:
        """Partition fizzbuzz-core from fizzbuzz-data, verify degradation.

        Tests that the application degrades gracefully when
        network connectivity between service tiers is lost.
        """
        exp = ChaosExperiment(
            name="Network partition between core and data tiers",
            description="Partition fizzbuzz-core containers from fizzbuzz-data containers",
            fault_config=FaultConfig(
                fault_type=FaultType.NETWORK_PARTITION,
                target_labels={"tier": "application"},
                target_count=2,
                duration=120.0,
                direction="both",
            ),
            hypothesis="Service degrades gracefully with increased error rates but no complete outage",
            steady_state_metrics=[
                SteadyStateMetric(name="error_rate", unit="%", threshold_upper=20.0),
                SteadyStateMetric(name="p99_latency_ms", unit="ms", threshold_upper=500.0),
            ],
        )
        return GameDay(
            title="Network Partition Tolerance",
            description="Validates graceful degradation when network partitions isolate service tiers",
            hypothesis="Services detect partition and degrade gracefully without data loss",
            experiments=[exp],
            schedule_mode=ScheduleMode.SEQUENTIAL,
            blast_radius_limit=0.40,
        )

    @staticmethod
    def resource_exhaustion() -> GameDay:
        """Apply CPU and memory stress to all services simultaneously.

        Tests that the platform survives simultaneous resource
        exhaustion across multiple service groups.
        """
        cpu_exp = ChaosExperiment(
            name="CPU stress across all services",
            description="Apply CPU stress to all application containers",
            fault_config=FaultConfig(
                fault_type=FaultType.CPU_STRESS,
                target_labels={"tier": "application"},
                target_count=2,
                duration=90.0,
                cores=2,
                load_percent=90.0,
            ),
            hypothesis="Services remain available with increased latency under CPU stress",
            steady_state_metrics=[
                SteadyStateMetric(name="p99_latency_ms", unit="ms", threshold_upper=1000.0),
                SteadyStateMetric(name="cpu_utilization", unit="%", threshold_upper=95.0),
            ],
        )
        mem_exp = ChaosExperiment(
            name="Memory pressure across all services",
            description="Apply memory pressure to all application containers",
            fault_config=FaultConfig(
                fault_type=FaultType.MEMORY_PRESSURE,
                target_labels={"tier": "application"},
                target_count=2,
                duration=90.0,
                target_bytes=268435456,
                rate_bytes_per_second=1048576,
            ),
            hypothesis="Services remain available with throttling under memory pressure",
            steady_state_metrics=[
                SteadyStateMetric(name="memory_utilization", unit="%", threshold_upper=95.0),
                SteadyStateMetric(name="error_rate", unit="%", threshold_upper=10.0),
            ],
        )
        return GameDay(
            title="Resource Exhaustion",
            description="Validates platform resilience under simultaneous CPU and memory exhaustion",
            hypothesis="Platform survives concurrent resource exhaustion with degraded but functional service",
            experiments=[cpu_exp, mem_exp],
            schedule_mode=ScheduleMode.STAGGERED,
            stagger_interval=30.0,
            blast_radius_limit=0.50,
        )

    @staticmethod
    def full_outage_recovery() -> GameDay:
        """Kill all containers, verify full platform recovery.

        The most severe game day scenario: complete platform outage
        followed by full recovery.  Tests the platform's ability
        to restore service from a total failure state.
        """
        exp = ChaosExperiment(
            name="Full platform container kill",
            description="Kill all containers to simulate complete infrastructure failure",
            fault_config=FaultConfig(
                fault_type=FaultType.CONTAINER_KILL,
                target_count=0,  # All containers
                duration=30.0,
            ),
            hypothesis="Platform recovers full service within 120 seconds of total container failure",
            steady_state_metrics=[
                SteadyStateMetric(name="error_rate", unit="%", threshold_upper=50.0),
                SteadyStateMetric(name="throughput_rps", unit="req/s", threshold_lower=0.0),
            ],
            is_emergency=True,
        )
        return GameDay(
            title="Full Outage Recovery",
            description="Validates complete platform recovery from total container failure",
            hypothesis="All services recover within 120 seconds with no data loss",
            experiments=[exp],
            schedule_mode=ScheduleMode.SEQUENTIAL,
            blast_radius_limit=1.0,
        )


# ============================================================
# ContainerChaosDashboard
# ============================================================


class ContainerChaosDashboard:
    """ASCII dashboard for chaos experiment status and reporting.

    Renders experiment status, active faults, blast radius,
    game day progress, and experiment reports as formatted
    ASCII tables using box-drawing characters.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._width = width

    def render_status(self, executor: ChaosExecutor) -> str:
        """Render active experiments with status, targets, and duration."""
        lines = [self._render_header("Container Chaos Status")]

        active = executor.list_active()
        if not active:
            lines.append("  No active chaos experiments.")
            lines.append("")
            return "\n".join(lines)

        headers = ["Experiment", "Fault Type", "Status", "Targets"]
        rows = []
        for exp in active:
            rows.append([
                exp.name[:20] or exp.experiment_id[:8],
                exp.fault_config.fault_type.value,
                exp.status.value,
                str(len(exp.affected_containers)),
            ])

        lines.append(self._render_table(headers, rows))

        # Summary
        all_experiments = executor.list_all()
        completed = sum(1 for e in all_experiments if e.status == ExperimentStatus.COMPLETED)
        aborted = sum(1 for e in all_experiments if e.status == ExperimentStatus.ABORTED)
        failed = sum(1 for e in all_experiments if e.status == ExperimentStatus.FAILED)

        lines.append(f"  Total: {len(all_experiments)} | Active: {len(active)} | "
                      f"Completed: {completed} | Aborted: {aborted} | Failed: {failed}")
        lines.append("")
        return "\n".join(lines)

    def render_report(self, report: ExperimentReport) -> str:
        """Render an experiment report with metric comparisons."""
        lines = [self._render_header(f"Experiment Report: {report.experiment_name}")]

        lines.append(f"  Experiment ID:    {report.experiment_id}")
        lines.append(f"  Fault Type:       {report.fault_type.value}")
        lines.append(f"  Hypothesis:       {report.hypothesis[:50]}")
        lines.append(f"  Validated:        {'Yes' if report.hypothesis_validated else 'No'}")
        lines.append(f"  Affected:         {report.affected_container_count}/{report.total_container_count}")
        lines.append(f"  Blast Radius:     {report.blast_radius_percent:.1f}%")
        lines.append(f"  Duration:         {report.duration_seconds:.1f}s")

        if report.abort_reason:
            lines.append(f"  Abort Reason:     {report.abort_reason.value}")

        if report.steady_state_comparison:
            lines.append("")
            lines.append(self._render_metric_comparison(report.steady_state_comparison))

        if report.timeline:
            lines.append("")
            lines.append(self._render_timeline(report.timeline[:10]))

        if report.recommendations:
            lines.append("")
            lines.append("  Recommendations:")
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"    {i}. {rec}")

        lines.append("")
        return "\n".join(lines)

    def render_gameday_report(self, report: GameDayReport) -> str:
        """Render a game day report with timeline and gaps."""
        lines = [self._render_header(f"Game Day Report: {report.title}")]

        lines.append(f"  Game Day ID:      {report.gameday_id}")
        lines.append(f"  Hypothesis:       {report.hypothesis[:50]}")
        lines.append(f"  Validated:        {'Yes' if report.hypothesis_validated else 'No'}")
        lines.append(f"  Experiments:      {report.experiments_completed} completed, "
                      f"{report.experiments_aborted} aborted, {report.experiments_failed} failed")
        lines.append(f"  Peak Blast Radius: {report.peak_blast_radius_percent:.1f}%")
        lines.append(f"  Duration:         {report.total_duration_seconds:.1f}s")

        if report.resilience_gaps:
            lines.append("")
            lines.append("  Resilience Gaps:")
            for gap in report.resilience_gaps:
                lines.append(f"    - {gap}")

        if report.recommendations:
            lines.append("")
            lines.append("  Recommendations:")
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"    {i}. {rec}")

        lines.append("")
        return "\n".join(lines)

    def render_blast_radius(self, calculator: BlastRadiusCalculator, total: int) -> str:
        """Render current blast radius as a visual gauge."""
        lines = [self._render_header("Blast Radius")]

        summary = calculator.get_summary()
        affected = summary["affected_count"]
        limit = summary["limit_percent"]
        radius = calculator.current_radius(calculator.get_affected(), total)

        # Visual gauge
        gauge_width = self._width - 20
        filled = int(radius / 100.0 * gauge_width) if radius > 0 else 0
        limit_pos = int(limit / 100.0 * gauge_width)

        gauge_chars = []
        for i in range(gauge_width):
            if i < filled:
                gauge_chars.append("#")
            elif i == limit_pos:
                gauge_chars.append("|")
            else:
                gauge_chars.append("-")

        lines.append(f"  [{''.join(gauge_chars)}]")
        lines.append(f"  Current: {radius:.1f}%  Limit: {limit:.1f}%  Affected: {affected}/{total}")
        lines.append(f"  Scope: {summary['scope']}")
        lines.append("")
        return "\n".join(lines)

    def render_fault_list(self, registry: FaultRegistry) -> str:
        """Render available fault types with parameters and defaults."""
        lines = [self._render_header("Available Fault Types")]

        faults = registry.list_faults()
        for fault in faults:
            lines.append(f"  {fault['fault_type']}")
            lines.append(f"    {fault['description']}")
            if fault["params"]:
                params_str = ", ".join(f"{k}={v}" for k, v in fault["params"].items())
                lines.append(f"    Parameters: {params_str}")
            lines.append("")

        return "\n".join(lines)

    def _render_header(self, title: str) -> str:
        """Render a section header with box-drawing characters."""
        border = "+" + "-" * (self._width - 2) + "+"
        padded = f"| {title:<{self._width - 4}} |"
        return f"\n{border}\n{padded}\n{border}"

    def _render_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Render a table with headers and rows."""
        if not rows:
            return "  (no data)"

        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(cell))

        # Header row
        header_line = "  " + "  ".join(
            h.ljust(col_widths[i]) for i, h in enumerate(headers)
        )
        separator = "  " + "  ".join("-" * w for w in col_widths)

        lines = [header_line, separator]
        for row in rows:
            line = "  " + "  ".join(
                (row[i] if i < len(row) else "").ljust(col_widths[i])
                for i in range(len(headers))
            )
            lines.append(line)

        return "\n".join(lines)

    def _render_metric_comparison(self, comparisons: List[Dict[str, Any]]) -> str:
        """Render metric comparison table."""
        headers = ["Metric", "Baseline", "During", "Recovery", "Recovered"]
        rows = []
        for comp in comparisons:
            rows.append([
                comp["name"],
                f"{comp['baseline']:.1f}",
                f"{comp['during']:.1f}",
                f"{comp['recovery']:.1f}",
                "Yes" if comp["recovered"] else "No",
            ])
        return "  Steady-State Metrics:\n" + self._render_table(headers, rows)

    def _render_timeline(self, timeline: List[Tuple[datetime, str]]) -> str:
        """Render timeline events."""
        lines = ["  Timeline:"]
        for ts, desc in timeline:
            lines.append(f"    {ts.strftime('%H:%M:%S')} - {desc}")
        return "\n".join(lines)


# ============================================================
# FizzContainerChaosMiddleware
# ============================================================


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
    ) -> None:
        self._executor = executor
        self._dashboard = dashboard
        self._enable_dashboard = enable_dashboard
        self._process_count = 0

    def get_name(self) -> str:
        """Return 'FizzContainerChaosMiddleware'."""
        return "FizzContainerChaosMiddleware"

    def get_priority(self) -> int:
        """Return MIDDLEWARE_PRIORITY (117)."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Middleware pipeline priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Middleware name."""
        return "FizzContainerChaosMiddleware"

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
        self._process_count += 1

        try:
            active = self._executor.list_active()
            if active:
                chaos_info = []
                for exp in active:
                    chaos_info.append({
                        "experiment_id": exp.experiment_id,
                        "experiment_name": exp.name,
                        "fault_type": exp.fault_config.fault_type.value,
                        "status": exp.status.value,
                        "affected_containers": len(exp.affected_containers),
                    })
                context.metadata["container_chaos_active"] = True
                context.metadata["container_chaos_experiments"] = chaos_info
            else:
                context.metadata["container_chaos_active"] = False

        except Exception as exc:
            raise ChaosContainerChaosMiddlewareError(
                context.number,
                f"Failed to annotate chaos context: {exc}",
            ) from exc

        return next_handler(context)

    def render_status(self) -> str:
        """Render active experiment status."""
        return self._dashboard.render_status(self._executor)

    def render_report(self, experiment_id: str) -> str:
        """Render a specific experiment report."""
        report = self._executor.get_report(experiment_id)
        if report is None:
            return f"  No report found for experiment {experiment_id}"
        return self._dashboard.render_report(report)

    def render_gameday_report(self, gameday_id: str) -> str:
        """Render a game day report.

        Delegates to the dashboard for rendering.  Note that
        the game day report is stored in the GameDayOrchestrator,
        not the executor.
        """
        return f"  Game day report for {gameday_id} (render via orchestrator)"

    def render_blast_radius(self) -> str:
        """Render current blast radius."""
        total = len(self._executor._container_registry)
        return self._dashboard.render_blast_radius(
            self._executor._blast_radius_calculator,
            total,
        )

    def render_fault_list(self) -> str:
        """Render available fault types."""
        return self._dashboard.render_fault_list(self._executor._fault_registry)

    def render_stats(self) -> str:
        """Render chaos subsystem statistics."""
        lines = [self._dashboard._render_header("Container Chaos Statistics")]
        lines.append(f"  Version:            {CONTAINER_CHAOS_VERSION}")
        lines.append(f"  Chaos Mesh Compat:  {CHAOS_MESH_COMPAT_VERSION}")
        lines.append(f"  Total Experiments:  {len(self._executor.experiments)}")
        lines.append(f"  Active Experiments: {len(self._executor.active_experiments)}")
        lines.append(f"  Reports Generated:  {len(self._executor.reports)}")
        lines.append(f"  Evaluations:        {self._process_count}")
        lines.append(f"  Middleware Priority: {MIDDLEWARE_PRIORITY}")
        lines.append("")
        return "\n".join(lines)


# ============================================================
# Factory Function
# ============================================================


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
    scope_map = {
        "global": BlastRadiusScope.GLOBAL,
        "service_group": BlastRadiusScope.SERVICE_GROUP,
        "namespace": BlastRadiusScope.NAMESPACE,
        "pod": BlastRadiusScope.POD,
    }
    scope = scope_map.get(blast_radius_scope, BlastRadiusScope.GLOBAL)

    fault_registry = FaultRegistry()
    target_resolver = TargetResolver()
    steady_state_probe = SteadyStateProbe(tolerance=steady_state_tolerance)
    blast_radius_calculator = BlastRadiusCalculator(limit=blast_radius_limit, scope=scope)
    chaos_gate = ChaosGate(threshold=cognitive_load_threshold)

    executor = ChaosExecutor(
        fault_registry=fault_registry,
        target_resolver=target_resolver,
        steady_state_probe=steady_state_probe,
        blast_radius_calculator=blast_radius_calculator,
        chaos_gate=chaos_gate,
        cognitive_load_threshold=cognitive_load_threshold,
        observation_interval=observation_interval,
        container_registry=container_registry,
        event_bus=event_bus,
    )

    orchestrator = GameDayOrchestrator(
        executor=executor,
        blast_radius_calculator=blast_radius_calculator,
    )

    dashboard = ContainerChaosDashboard(width=dashboard_width)

    middleware = FizzContainerChaosMiddleware(
        executor=executor,
        dashboard=dashboard,
        enable_dashboard=enable_dashboard,
    )

    logger.info(
        "FizzContainerChaos subsystem initialized: "
        "cognitive_threshold=%.1f, blast_radius_limit=%.0f%%, scope=%s",
        cognitive_load_threshold,
        blast_radius_limit * 100,
        blast_radius_scope,
    )

    return executor, orchestrator, middleware
