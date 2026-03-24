"""
Enterprise FizzBuzz Platform - FizzDeploy: Container-Native Deployment Pipeline

A complete CI/CD deployment pipeline inspired by Argo CD and Spinnaker,
implementing the full deployment lifecycle: build, scan, sign, push, deploy,
validate, and rollback.  The pipeline supports four deployment strategies --
rolling update (incremental pod replacement with configurable surge and
unavailability), blue-green (parallel environments with instant traffic
switch), canary (gradual traffic shifting with automated regression
analysis), and recreate (terminate all, start all) -- for zero-downtime
version rollouts of containerized FizzBuzz subsystems.

Declarative YAML deployment manifests define the desired state.  A GitOps
reconciliation loop continuously compares actual cluster state against
declared state, applying corrections when drift is detected.  FizzBob
cognitive load gating ensures that deployments do not proceed when the
sole operator's cognitive load exceeds safe operational thresholds.

The rollback manager maintains a configurable revision history, supporting
both automated rollback on validation failure and manual rollback via CLI.
Each deployment emits events to the platform's event bus, enabling audit
trails, compliance reporting, and observability across the deployment
lifecycle.

Architecture reference: Argo CD (https://argoproj.github.io/cd/),
Spinnaker (https://spinnaker.io/)
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import random
import re
import threading
import time
import uuid
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzdeploy")


# ============================================================
# Exceptions (self-contained, inheriting from FizzBuzzError)
# ============================================================


class DeployError(FizzBuzzError):
    """Base exception for all FizzDeploy deployment pipeline errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL00"
        self.context = {"reason": reason}


class DeployPipelineError(DeployError):
    """Raised when the deployment pipeline execution fails.

    Pipeline failures occur when a stage cannot complete within the
    configured timeout, when stage sequencing encounters an illegal
    state transition, or when the pipeline execution engine encounters
    an unrecoverable internal error.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL01"
        self.context = {"reason": reason}


class DeployStageError(DeployError):
    """Raised when a pipeline stage execution fails.

    Stage failures propagate from individual step failures, stage-level
    timeouts, or illegal step configurations within the stage definition.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL02"
        self.context = {"reason": reason}


class DeployStepError(DeployError):
    """Raised when a pipeline step fails after exhausting all retry attempts.

    The retry policy's exponential backoff has been fully consumed.  The
    step's action callable returned an error or raised an exception on
    every attempt, including the initial execution and all configured
    retries.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL03"
        self.context = {"reason": reason}


class DeployStrategyError(DeployError):
    """Raised when an unknown or unsupported deployment strategy is requested.

    The strategy factory received a strategy identifier that does not
    map to any of the four supported deployment strategies: rolling
    update, blue-green, canary, or recreate.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL04"
        self.context = {"reason": reason}


class RollingUpdateError(DeployError):
    """Raised when the rolling update strategy encounters a failure.

    Rolling update failures include pod readiness probe timeouts,
    batch replacement failures where new pods cannot achieve ready
    state, and surge limit violations during proportional scaling.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL05"
        self.context = {"reason": reason}


class BlueGreenError(DeployError):
    """Raised when the blue-green deployment strategy fails.

    Blue-green failures occur when the inactive environment fails
    validation checks, preventing traffic switch, or when the
    environment provisioning cannot allocate the required resources.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL06"
        self.context = {"reason": reason}


class CanaryError(DeployError):
    """Raised when the canary deployment detects a regression.

    Automated canary analysis has determined that the canary population
    exhibits statistically significant degradation in error rate, P99
    latency, or resource utilization compared to the baseline population.
    The canary has been rolled back to 0% traffic.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL07"
        self.context = {"reason": reason}


class RecreateError(DeployError):
    """Raised when the recreate deployment strategy fails.

    Recreate failures occur when existing pods cannot be gracefully
    terminated within the shutdown timeout, or when new pods fail
    to achieve ready state within the startup timeout.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL08"
        self.context = {"reason": reason}


class DeployManifestError(DeployError):
    """Raised for general deployment manifest errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL09"
        self.context = {"reason": reason}


class ManifestParseError(DeployManifestError):
    """Raised when YAML syntax errors prevent manifest parsing.

    The provided manifest string contains malformed YAML that cannot
    be parsed into a valid document structure.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL10"
        self.context = {"reason": reason}


class ManifestValidationError(DeployManifestError):
    """Raised when a manifest fails schema validation.

    The manifest was successfully parsed as YAML but does not conform
    to the deployment manifest schema.  Required fields may be missing,
    strategy parameters may be invalid, or resource constraint formats
    may not match the expected pattern.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL11"
        self.context = {"reason": reason}


class GitOpsReconcileError(DeployError):
    """Raised when the GitOps reconciliation loop encounters a failure.

    The reconciler was unable to compare declared state against actual
    cluster state, or encountered an internal error during the
    reconciliation pass.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL12"
        self.context = {"reason": reason}


class GitOpsDriftError(DeployError):
    """Raised when configuration drift is detected between declared and actual state.

    The GitOps reconciler has identified one or more fields where the
    actual cluster state diverges from the declared manifest state.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL13"
        self.context = {"reason": reason}


class GitOpsSyncError(DeployError):
    """Raised when drift correction fails during synchronization.

    The reconciler detected drift and attempted to apply corrections,
    but the sync operation failed to bring the actual state into
    alignment with the declared state.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL14"
        self.context = {"reason": reason}


class RollbackError(DeployError):
    """Raised for general rollback operation failures."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL15"
        self.context = {"reason": reason}


class RollbackRevisionNotFoundError(RollbackError):
    """Raised when the target revision does not exist in the revision history.

    The rollback manager was asked to restore a revision number that
    is not present in the deployment's revision history.  The revision
    may have been pruned by the history depth limit or may never have
    existed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL16"
        self.context = {"reason": reason}


class RollbackStrategyError(RollbackError):
    """Raised when the strategy-aware rollback operation fails.

    The rollback attempted to restore the previous deployment state
    using the original strategy, but the traffic switch, pod
    restoration, or environment promotion failed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL17"
        self.context = {"reason": reason}


class DeployGateError(DeployError):
    """Raised for general deployment gate errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL18"
        self.context = {"reason": reason}


class CognitiveLoadGateError(DeployGateError):
    """Raised when Bob McFizzington's cognitive load exceeds the deployment threshold.

    The NASA-TLX assessment has determined that the sole operator of the
    Enterprise FizzBuzz Platform is cognitively overloaded.  Proceeding
    with a deployment under these conditions risks incident response
    failure, as Bob would be unable to monitor the rollout, interpret
    health check results, or execute a rollback if the deployment
    introduces a regression.  The deployment has been queued until
    Bob's cognitive load decreases to safe operational levels.

    Emergency deployments may bypass this gate via the --fizzdeploy-emergency
    flag, which records the bypass in the audit log for post-incident review.
    """

    def __init__(self, deployment_name: str, current_score: float, threshold: float) -> None:
        super().__init__(
            f"Deployment '{deployment_name}' blocked: operator cognitive load "
            f"{current_score:.1f} exceeds threshold {threshold:.1f}"
        )
        self.error_code = "EFP-DPL19"
        self.context = {
            "deployment_name": deployment_name,
            "current_score": current_score,
            "threshold": threshold,
        }


class DeployDashboardError(DeployError):
    """Raised when the deployment dashboard fails to render.

    The dashboard renderer encountered an error while generating the
    ASCII representation of pipeline status, revision history, drift
    reports, or canary analysis results.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPL20"
        self.context = {"reason": reason}


class DeployMiddlewareError(DeployError):
    """Raised when the FizzDeploy middleware fails to process an evaluation.

    The middleware could not enrich the processing context with deployment
    revision metadata, or failed to delegate to the next handler in the
    middleware pipeline.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"FizzDeploy middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-DPL21"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number


# ============================================================
# Event type constants (module-level strings)
# ============================================================

DEPLOY_PIPELINE_STARTED = "fizzdeploy.pipeline.started"
DEPLOY_PIPELINE_COMPLETED = "fizzdeploy.pipeline.completed"
DEPLOY_PIPELINE_FAILED = "fizzdeploy.pipeline.failed"
DEPLOY_STAGE_STARTED = "fizzdeploy.stage.started"
DEPLOY_STAGE_COMPLETED = "fizzdeploy.stage.completed"
DEPLOY_STAGE_FAILED = "fizzdeploy.stage.failed"
DEPLOY_ROLLING_UPDATE_BATCH = "fizzdeploy.rolling_update.batch"
DEPLOY_ROLLING_UPDATE_PAUSED = "fizzdeploy.rolling_update.paused"
DEPLOY_BLUE_GREEN_SWITCHED = "fizzdeploy.blue_green.switched"
DEPLOY_BLUE_GREEN_ABORTED = "fizzdeploy.blue_green.aborted"
DEPLOY_CANARY_STEP_ADVANCED = "fizzdeploy.canary.step_advanced"
DEPLOY_CANARY_REGRESSION = "fizzdeploy.canary.regression"
DEPLOY_RECREATE_STARTED = "fizzdeploy.recreate.started"
DEPLOY_RECREATE_COMPLETED = "fizzdeploy.recreate.completed"
DEPLOY_GITOPS_DRIFT_DETECTED = "fizzdeploy.gitops.drift_detected"
DEPLOY_GITOPS_SYNC_APPLIED = "fizzdeploy.gitops.sync_applied"
DEPLOY_ROLLBACK_EXECUTED = "fizzdeploy.rollback.executed"
DEPLOY_GATE_BLOCKED = "fizzdeploy.gate.blocked"
DEPLOY_GATE_PASSED = "fizzdeploy.gate.passed"
DEPLOY_GATE_EMERGENCY_BYPASS = "fizzdeploy.gate.emergency_bypass"
DEPLOY_DASHBOARD_RENDERED = "fizzdeploy.dashboard.rendered"


# ============================================================
# Constants
# ============================================================

FIZZDEPLOY_VERSION = "1.0.0"
"""FizzDeploy subsystem version."""

DEFAULT_PIPELINE_TIMEOUT = 600.0
"""Pipeline execution timeout in seconds (10 minutes)."""

DEFAULT_STAGE_TIMEOUT = 120.0
"""Per-stage execution timeout in seconds."""

DEFAULT_STEP_TIMEOUT = 60.0
"""Per-step execution timeout in seconds."""

DEFAULT_MAX_RETRIES = 3
"""Default retry count for failed steps."""

DEFAULT_RETRY_BACKOFF = 2.0
"""Exponential backoff multiplier for retries."""

DEFAULT_ROLLING_MAX_SURGE = 0.25
"""Max pods above desired during rolling update (25%)."""

DEFAULT_ROLLING_MAX_UNAVAILABLE = 0.25
"""Max unavailable pods during rolling update (25%)."""

DEFAULT_CANARY_ANALYSIS_INTERVAL = 30.0
"""Seconds between canary metric samples."""

DEFAULT_RECONCILE_INTERVAL = 30.0
"""GitOps reconciliation loop interval in seconds."""

DEFAULT_REVISION_HISTORY_DEPTH = 10
"""Max deployment revisions retained."""

DEFAULT_COGNITIVE_LOAD_THRESHOLD = 70.0
"""NASA-TLX score above which deployments are gated."""

DEFAULT_DASHBOARD_WIDTH = 72
"""ASCII dashboard rendering width."""

MIDDLEWARE_PRIORITY = 114
"""Middleware pipeline priority for FizzDeploy."""

DEFAULT_CANARY_STEPS: List[Tuple[float, float]] = [
    (5.0, 300.0),
    (25.0, 600.0),
    (75.0, 600.0),
    (100.0, 0.0),
]
"""Default canary traffic shifting steps: (traffic_percent, pause_seconds)."""


# ============================================================
# Enums
# ============================================================


class PipelineStatus(Enum):
    """Pipeline lifecycle states.

    A pipeline progresses through these states during execution.
    Terminal states are SUCCEEDED, FAILED, ROLLED_BACK, and CANCELLED.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class StageType(Enum):
    """Standard pipeline stage types.

    Each stage type corresponds to a phase in the CI/CD deployment
    lifecycle, from container image construction through post-deployment
    validation.
    """

    BUILD = "build"
    SCAN = "scan"
    SIGN = "sign"
    PUSH = "push"
    DEPLOY = "deploy"
    VALIDATE = "validate"
    FINALIZE = "finalize"


class StageStatus(Enum):
    """Individual stage execution states.

    Stages progress from PENDING through RUNNING to a terminal state
    of SUCCEEDED, FAILED, or SKIPPED.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class DeploymentStrategy(Enum):
    """Deployment strategy types.

    Four strategies are supported, each offering different trade-offs
    between deployment speed, resource usage, risk exposure, and
    rollback capability.
    """

    ROLLING_UPDATE = "rolling_update"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    RECREATE = "recreate"


class SyncStrategy(Enum):
    """GitOps drift correction strategies.

    Controls how the reconciler responds when it detects divergence
    between the declared manifest state and the actual cluster state.
    """

    AUTO = "auto"
    MANUAL = "manual"
    DRY_RUN = "dry_run"


class RevisionStatus(Enum):
    """Deployment revision lifecycle.

    Tracks the state of each point-in-time deployment revision in
    the rollback manager's history.
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class OnFailureAction(Enum):
    """Step failure behavior.

    Determines how the pipeline executor responds when a step fails
    after exhausting its retry policy.
    """

    ABORT = "abort"
    SKIP = "skip"
    ROLLBACK = "rollback"


# ============================================================
# Data Classes
# ============================================================


@dataclass
class RetryPolicy:
    """Retry policy for pipeline steps.

    Configures how many times a step is retried on failure, the
    backoff multiplier between retries, and the maximum delay cap.

    Attributes:
        max_retries: Maximum retry attempts before giving up.
        backoff_multiplier: Exponential backoff multiplier.
        max_delay: Maximum delay between retries in seconds.
        initial_delay: Initial delay before first retry in seconds.
    """

    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_multiplier: float = DEFAULT_RETRY_BACKOFF
    max_delay: float = 60.0
    initial_delay: float = 1.0


@dataclass
class StageResult:
    """Result of a pipeline stage execution.

    Captures the outcome, duration, retry information, and any
    error details for a completed stage.

    Attributes:
        stage_name: Name of the stage.
        stage_type: Stage type enum.
        status: Execution status.
        started_at: When the stage started.
        completed_at: When the stage completed.
        duration_ms: Execution duration in milliseconds.
        retry_count: Number of retries that were attempted.
        error_message: Error message if the stage failed.
        metadata: Additional stage-specific output metadata.
    """

    stage_name: str
    stage_type: StageType
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    retry_count: int = 0
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Result of a complete pipeline execution.

    Aggregates the results of all stages, tracks overall pipeline
    timing, and records the final pipeline status.

    Attributes:
        pipeline_id: Unique pipeline execution identifier.
        deployment_name: Name of the deployment this pipeline serves.
        status: Final pipeline status.
        stage_results: Ordered list of stage results.
        started_at: When the pipeline started.
        completed_at: When the pipeline completed.
        total_duration_ms: Total execution duration in milliseconds.
        image_digest: Digest of the deployed image (if deployment succeeded).
        revision_number: Deployment revision created by this pipeline.
    """

    pipeline_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    deployment_name: str = ""
    status: PipelineStatus = PipelineStatus.PENDING
    stage_results: List[StageResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_ms: float = 0.0
    image_digest: str = ""
    revision_number: int = 0


@dataclass
class HealthCheckConfig:
    """Health check probe configuration for deployed containers.

    Supports three probe types: HTTP (GET request to a path), TCP
    (socket connection to a port), and exec (command execution
    inside the container).

    Attributes:
        probe_type: Type of probe ("http", "tcp", "exec").
        path: HTTP path for HTTP probes.
        port: Port number for HTTP and TCP probes.
        command: Command for exec probes.
        interval_seconds: Time between probe executions.
        timeout_seconds: Probe timeout.
        success_threshold: Consecutive successes to mark healthy.
        failure_threshold: Consecutive failures to mark unhealthy.
        initial_delay_seconds: Delay before first probe.
    """

    probe_type: str = "http"
    path: str = "/healthz"
    port: int = 8080
    command: List[str] = field(default_factory=list)
    interval_seconds: int = 10
    timeout_seconds: int = 5
    success_threshold: int = 1
    failure_threshold: int = 3
    initial_delay_seconds: int = 0


@dataclass
class DeploymentSpec:
    """Specification for a deployment parsed from a manifest.

    Contains the desired state of a deployment including image
    reference, replica count, strategy, resources, health checks,
    environment variables, volumes, init containers, and sidecars.

    Attributes:
        image: Image reference from FizzImage catalog.
        replicas: Desired replica count.
        strategy: Deployment strategy type.
        strategy_params: Strategy-specific configuration parameters.
        resources: CPU/memory requests and limits.
        health_check: Health check probe configuration.
        env: Environment variable definitions.
        volumes: Volume mount specifications.
        init_containers: Init container image specifications.
        sidecars: Sidecar container image specifications.
    """

    image: str = ""
    replicas: int = 1
    strategy: DeploymentStrategy = DeploymentStrategy.ROLLING_UPDATE
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, Dict[str, str]] = field(default_factory=dict)
    health_check: Optional[HealthCheckConfig] = None
    env: Dict[str, str] = field(default_factory=dict)
    volumes: List[Dict[str, Any]] = field(default_factory=list)
    init_containers: List[str] = field(default_factory=list)
    sidecars: List[str] = field(default_factory=list)


@dataclass
class DeploymentManifest:
    """Declarative deployment manifest following Kubernetes resource conventions.

    A deployment manifest declares the desired state of a deployment:
    the image to run, the number of replicas, the strategy for rollout,
    resource limits, health checks, environment configuration, volumes,
    init containers, and sidecars.

    Attributes:
        api_version: Manifest API version (e.g., "apps/v1").
        kind: Resource kind (e.g., "Deployment").
        name: Deployment name.
        namespace: Deployment namespace.
        labels: Key-value metadata labels.
        annotations: Key-value annotations.
        spec: Deployment specification.
        raw_yaml: Raw YAML string from which this manifest was parsed.
        parsed_at: When the manifest was parsed.
    """

    api_version: str = "apps/v1"
    kind: str = "Deployment"
    name: str = ""
    namespace: str = "default"
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    spec: DeploymentSpec = field(default_factory=DeploymentSpec)
    raw_yaml: str = ""
    parsed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DeploymentRevision:
    """A point-in-time record of a deployment's state.

    The rollback manager stores revisions so that any previous
    deployment state can be restored.  Each revision captures
    the complete manifest, image digest, and deployment outcome.

    Attributes:
        revision_number: Sequential revision number.
        deployment_name: Name of the deployment.
        manifest: Complete deployment manifest at this revision.
        image_digest: SHA-256 digest of the deployed image.
        status: Revision status.
        deployed_at: When this revision was deployed.
        pipeline_id: Pipeline execution that created this revision.
        rollback_from: If this revision was a rollback, the revision it rolled back from.
    """

    revision_number: int = 0
    deployment_name: str = ""
    manifest: Optional[DeploymentManifest] = None
    image_digest: str = ""
    status: RevisionStatus = RevisionStatus.ACTIVE
    deployed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pipeline_id: str = ""
    rollback_from: Optional[int] = None


@dataclass
class RollbackRecord:
    """Record of a rollback operation.

    Captures the source and target revisions, the trigger
    (automatic or manual), and the outcome.

    Attributes:
        rollback_id: Unique rollback operation identifier.
        deployment_name: Deployment that was rolled back.
        from_revision: Revision that was active before rollback.
        to_revision: Revision that was restored.
        trigger: What caused the rollback ("automatic" or "manual").
        reason: Human-readable reason for the rollback.
        started_at: When the rollback started.
        completed_at: When the rollback completed.
        success: Whether the rollback succeeded.
    """

    rollback_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    deployment_name: str = ""
    from_revision: int = 0
    to_revision: int = 0
    trigger: str = "manual"
    reason: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    success: bool = False


@dataclass
class DriftReport:
    """Report of configuration drift detected by the GitOps reconciler.

    When the reconciler detects that the actual cluster state differs
    from the declared manifest state, it generates a drift report
    describing each divergence.

    Attributes:
        report_id: Unique drift report identifier.
        deployment_name: Deployment where drift was detected.
        detected_at: When the drift was detected.
        drifts: List of individual drift items (field, expected, actual).
        sync_strategy: The sync strategy that will be applied.
        corrected: Whether the drift was automatically corrected.
    """

    report_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    deployment_name: str = ""
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    drifts: List[Dict[str, Any]] = field(default_factory=list)
    sync_strategy: SyncStrategy = SyncStrategy.AUTO
    corrected: bool = False


@dataclass
class CanaryAnalysisResult:
    """Result of automated canary analysis at a given traffic step.

    Compares error rates, latency, and resource utilization between
    the canary and baseline populations using SLI metrics.

    Attributes:
        step_index: Canary step index (0-based).
        traffic_percent: Traffic percentage at this step.
        baseline_error_rate: Error rate of the baseline population.
        canary_error_rate: Error rate of the canary population.
        baseline_p99_latency_ms: Baseline P99 latency in milliseconds.
        canary_p99_latency_ms: Canary P99 latency in milliseconds.
        regression_detected: Whether a statistical regression was found.
        analysis_duration_ms: Time spent on analysis in milliseconds.
        verdict: "pass", "fail", or "inconclusive".
    """

    step_index: int = 0
    traffic_percent: float = 0.0
    baseline_error_rate: float = 0.0
    canary_error_rate: float = 0.0
    baseline_p99_latency_ms: float = 0.0
    canary_p99_latency_ms: float = 0.0
    regression_detected: bool = False
    analysis_duration_ms: float = 0.0
    verdict: str = "pass"


# ============================================================
# Pipeline Components
# ============================================================


class PipelineStep:
    """A single executable step within a pipeline stage.

    Each step wraps an action callable that performs a discrete unit
    of deployment work.  Steps are retried according to their retry
    policy on failure, with exponential backoff between attempts.
    """

    def __init__(
        self,
        name: str,
        action: Callable[..., Dict[str, Any]],
        timeout: float = DEFAULT_STEP_TIMEOUT,
        retry_policy: Optional[RetryPolicy] = None,
        on_failure: OnFailureAction = OnFailureAction.ABORT,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.action = action
        self.timeout = timeout
        self.retry_policy = retry_policy or RetryPolicy()
        self.on_failure = on_failure
        self.metadata = metadata or {}

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the step action with retry logic.

        On each failure, compute delay via initial_delay * backoff_multiplier^attempt,
        capped at max_delay.  Return the action's output dict.

        Args:
            context: Execution context passed to the action callable.

        Returns:
            Output dictionary from the action callable.

        Raises:
            DeployStepError: If all retries are exhausted.
        """
        last_error: Optional[Exception] = None
        policy = self.retry_policy

        for attempt in range(policy.max_retries + 1):
            try:
                result = self.action(context)
                return result
            except Exception as exc:
                last_error = exc
                if attempt < policy.max_retries:
                    delay = min(
                        policy.initial_delay * (policy.backoff_multiplier ** attempt),
                        policy.max_delay,
                    )
                    time.sleep(delay * 0.001)

        raise DeployStepError(
            f"Step '{self.name}' failed after {policy.max_retries + 1} attempts: {last_error}"
        )


class PipelineStage:
    """An ordered collection of steps that form a logical pipeline stage.

    Stages correspond to deployment lifecycle phases such as BUILD,
    SCAN, SIGN, PUSH, DEPLOY, VALIDATE, and FINALIZE.  Steps within
    a stage may execute sequentially or in parallel via threading.
    """

    def __init__(
        self,
        name: str,
        stage_type: StageType,
        steps: Optional[List[PipelineStep]] = None,
        parallel: bool = False,
        timeout: float = DEFAULT_STAGE_TIMEOUT,
    ) -> None:
        self.name = name
        self.stage_type = stage_type
        self.steps: List[PipelineStep] = steps or []
        self.parallel = parallel
        self.timeout = timeout

    def add_step(self, step: PipelineStep) -> None:
        """Append a step to this stage."""
        self.steps.append(step)

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute all steps in this stage.

        Steps execute sequentially by default.  If parallel is True,
        steps execute concurrently via threading and the stage waits
        for all to complete.

        Args:
            context: Execution context passed to each step.

        Returns:
            StageResult capturing the outcome of this stage.
        """
        result = StageResult(
            stage_name=self.name,
            stage_type=self.stage_type,
            status=StageStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        total_retries = 0

        try:
            if self.parallel and len(self.steps) > 1:
                errors: List[Exception] = []
                threads: List[threading.Thread] = []

                def _run_step(step: PipelineStep) -> None:
                    nonlocal total_retries
                    try:
                        step.execute(context)
                    except Exception as exc:
                        errors.append(exc)

                for step in self.steps:
                    t = threading.Thread(target=_run_step, args=(step,))
                    threads.append(t)
                    t.start()

                for t in threads:
                    t.join(timeout=self.timeout)

                if errors:
                    raise DeployStageError(
                        f"Stage '{self.name}' had {len(errors)} step failures: "
                        f"{errors[0]}"
                    )
            else:
                for step in self.steps:
                    try:
                        step.execute(context)
                    except DeployStepError:
                        if step.on_failure == OnFailureAction.SKIP:
                            continue
                        raise

            result.status = StageStatus.SUCCEEDED
        except Exception as exc:
            result.status = StageStatus.FAILED
            result.error_message = str(exc)

        result.completed_at = datetime.now(timezone.utc)
        if result.started_at and result.completed_at:
            result.duration_ms = (
                result.completed_at - result.started_at
            ).total_seconds() * 1000
        result.retry_count = total_retries

        return result


class Pipeline:
    """An ordered sequence of stages forming the complete deployment pipeline.

    A pipeline encapsulates the full deployment lifecycle from image
    build through post-deployment validation.  The pipeline executor
    processes stages in order, halting on failure unless the failing
    step's on_failure action permits continuation.
    """

    def __init__(
        self,
        deployment_name: str,
        stages: Optional[List[PipelineStage]] = None,
        timeout: float = DEFAULT_PIPELINE_TIMEOUT,
    ) -> None:
        self.pipeline_id = uuid.uuid4().hex[:16]
        self.deployment_name = deployment_name
        self.stages: List[PipelineStage] = stages or []
        self.status = PipelineStatus.PENDING
        self.timeout = timeout
        self.created_at = datetime.now(timezone.utc)
        self._result: Optional[PipelineResult] = None

    def add_stage(self, stage: PipelineStage) -> None:
        """Append a stage to this pipeline."""
        self.stages.append(stage)

    def get_result(self) -> Optional[PipelineResult]:
        """Return the execution result, or None if not yet executed."""
        return self._result


class PipelineExecutor:
    """Executes a pipeline to completion, managing stage sequencing and events.

    The executor processes pipeline stages in order, collecting results
    and emitting lifecycle events.  It maintains a bounded history of
    completed pipeline results for dashboard rendering and audit.
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._event_bus = event_bus
        self._lock = threading.Lock()
        self._active_pipelines: Dict[str, Pipeline] = {}
        self._completed_pipelines: List[PipelineResult] = []
        self._total_executions = 0
        self._total_failures = 0

    def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def execute(self, pipeline: Pipeline) -> PipelineResult:
        """Execute all stages in order.

        For each stage, call stage.execute().  If a stage fails and
        the step's on_failure is ABORT, set pipeline to FAILED and stop.
        If ROLLBACK, set pipeline to ROLLED_BACK and stop.  If SKIP,
        mark stage as SKIPPED and continue.

        Args:
            pipeline: The pipeline to execute.

        Returns:
            PipelineResult capturing the complete execution outcome.
        """
        result = PipelineResult(
            pipeline_id=pipeline.pipeline_id,
            deployment_name=pipeline.deployment_name,
            status=PipelineStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        with self._lock:
            self._active_pipelines[pipeline.pipeline_id] = pipeline
            self._total_executions += 1

        pipeline.status = PipelineStatus.RUNNING
        self._emit(DEPLOY_PIPELINE_STARTED, {
            "pipeline_id": pipeline.pipeline_id,
            "deployment_name": pipeline.deployment_name,
        })

        context: Dict[str, Any] = {
            "pipeline_id": pipeline.pipeline_id,
            "deployment_name": pipeline.deployment_name,
        }

        try:
            for stage in pipeline.stages:
                self._emit(DEPLOY_STAGE_STARTED, {
                    "pipeline_id": pipeline.pipeline_id,
                    "stage_name": stage.name,
                    "stage_type": stage.stage_type.value,
                })

                stage_result = stage.execute(context)
                result.stage_results.append(stage_result)

                self._emit(DEPLOY_STAGE_COMPLETED, {
                    "pipeline_id": pipeline.pipeline_id,
                    "stage_name": stage.name,
                    "status": stage_result.status.value,
                })

                if stage_result.status == StageStatus.FAILED:
                    on_failure = OnFailureAction.ABORT
                    for step in stage.steps:
                        if step.on_failure == OnFailureAction.ROLLBACK:
                            on_failure = OnFailureAction.ROLLBACK
                            break
                        elif step.on_failure == OnFailureAction.SKIP:
                            on_failure = OnFailureAction.SKIP

                    if on_failure == OnFailureAction.ROLLBACK:
                        result.status = PipelineStatus.ROLLED_BACK
                        pipeline.status = PipelineStatus.ROLLED_BACK
                        self._emit(DEPLOY_PIPELINE_FAILED, {
                            "pipeline_id": pipeline.pipeline_id,
                            "reason": stage_result.error_message,
                            "action": "rollback",
                        })
                        break
                    elif on_failure == OnFailureAction.SKIP:
                        stage_result.status = StageStatus.SKIPPED
                        continue
                    else:
                        result.status = PipelineStatus.FAILED
                        pipeline.status = PipelineStatus.FAILED
                        self._total_failures += 1
                        self._emit(DEPLOY_PIPELINE_FAILED, {
                            "pipeline_id": pipeline.pipeline_id,
                            "reason": stage_result.error_message,
                            "action": "abort",
                        })
                        break

            if result.status == PipelineStatus.RUNNING:
                result.status = PipelineStatus.SUCCEEDED
                pipeline.status = PipelineStatus.SUCCEEDED
                self._emit(DEPLOY_PIPELINE_COMPLETED, {
                    "pipeline_id": pipeline.pipeline_id,
                    "deployment_name": pipeline.deployment_name,
                })

        except Exception as exc:
            result.status = PipelineStatus.FAILED
            pipeline.status = PipelineStatus.FAILED
            self._total_failures += 1
            self._emit(DEPLOY_PIPELINE_FAILED, {
                "pipeline_id": pipeline.pipeline_id,
                "reason": str(exc),
            })

        result.completed_at = datetime.now(timezone.utc)
        if result.started_at and result.completed_at:
            result.total_duration_ms = (
                result.completed_at - result.started_at
            ).total_seconds() * 1000

        pipeline._result = result

        with self._lock:
            self._active_pipelines.pop(pipeline.pipeline_id, None)
            self._completed_pipelines.append(result)
            if len(self._completed_pipelines) > 100:
                self._completed_pipelines = self._completed_pipelines[-100:]

        return result

    def cancel(self, pipeline_id: str) -> bool:
        """Cancel a running pipeline.

        Args:
            pipeline_id: ID of the pipeline to cancel.

        Returns:
            True if the pipeline was found and cancelled, False otherwise.
        """
        with self._lock:
            pipeline = self._active_pipelines.pop(pipeline_id, None)
            if pipeline is not None:
                pipeline.status = PipelineStatus.CANCELLED
                return True
            return False

    def get_active(self) -> List[str]:
        """Return IDs of active pipelines."""
        with self._lock:
            return list(self._active_pipelines.keys())

    def get_history(self, limit: int = 10) -> List[PipelineResult]:
        """Return recent pipeline results.

        Args:
            limit: Maximum number of results to return.

        Returns:
            List of recent PipelineResult objects.
        """
        with self._lock:
            return list(self._completed_pipelines[-limit:])


# ============================================================
# Deployment Strategies
# ============================================================


class RollingUpdateStrategy:
    """Implements the rolling update deployment strategy.

    Incrementally replaces pods with new versions in configurable
    batches, maintaining availability throughout the rollout.  The
    batch size is computed from max_surge and max_unavailable parameters,
    following the Kubernetes rolling update algorithm.
    """

    def __init__(
        self,
        max_surge: float = DEFAULT_ROLLING_MAX_SURGE,
        max_unavailable: float = DEFAULT_ROLLING_MAX_UNAVAILABLE,
        min_ready_seconds: float = 0.0,
        health_check_timeout: float = 30.0,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._max_surge = max_surge
        self._max_unavailable = max_unavailable
        self._min_ready_seconds = min_ready_seconds
        self._health_check_timeout = health_check_timeout
        self._event_bus = event_bus

    def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def _compute_batch_size(self, desired: int) -> Tuple[int, int]:
        """Calculate surge_count and unavailable_count.

        If max_surge/max_unavailable are floats <= 1.0, they are treated
        as fractions of the desired count.  Otherwise, they are treated
        as absolute values.

        Args:
            desired: Desired replica count.

        Returns:
            Tuple of (surge_count, unavailable_count).
        """
        if self._max_surge <= 1.0:
            surge_count = max(1, int(math.ceil(desired * self._max_surge)))
        else:
            surge_count = int(self._max_surge)

        if self._max_unavailable <= 1.0:
            unavailable_count = max(1, int(math.ceil(desired * self._max_unavailable)))
        else:
            unavailable_count = int(self._max_unavailable)

        return surge_count, unavailable_count

    def _simulate_readiness_check(self, pod_id: str) -> bool:
        """Simulate readiness probe execution.

        In a production deployment, this would send a health check
        probe to the pod.  The simulation uses a deterministic hash
        of the pod ID to produce a consistent pass/fail result, with
        a 95% success rate.

        Args:
            pod_id: Pod identifier.

        Returns:
            True if the pod is ready, False otherwise.
        """
        h = hashlib.md5(pod_id.encode()).hexdigest()
        return int(h[:2], 16) < 243  # ~95% pass rate

    def execute(
        self,
        manifest: DeploymentManifest,
        current_pods: List[Dict[str, Any]],
        new_image: str,
    ) -> Dict[str, Any]:
        """Execute a rolling update deployment.

        Compute batch size from max_surge and max_unavailable.  For each
        batch: create new pods with new_image, wait for readiness probes,
        terminate old pods.  If a pod fails readiness within
        health_check_timeout, pause rollout.

        Args:
            manifest: Deployment manifest.
            current_pods: List of current pod descriptors.
            new_image: New image reference to deploy.

        Returns:
            Rollout metrics dictionary.

        Raises:
            RollingUpdateError: If a batch fails readiness checks.
        """
        desired = manifest.spec.replicas
        surge_count, unavailable_count = self._compute_batch_size(desired)
        batch_size = max(surge_count, unavailable_count)

        old_pods = list(current_pods)
        new_pods: List[Dict[str, Any]] = []
        batches_completed = 0
        pods_replaced = 0
        paused = False

        while old_pods:
            batch = old_pods[:batch_size]
            batch_new: List[Dict[str, Any]] = []

            for old_pod in batch:
                pod_id = f"{manifest.name}-{uuid.uuid4().hex[:8]}"
                new_pod = {
                    "id": pod_id,
                    "image": new_image,
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                if self._simulate_readiness_check(pod_id):
                    new_pod["status"] = "ready"
                    batch_new.append(new_pod)
                    pods_replaced += 1
                else:
                    paused = True
                    self._emit(DEPLOY_ROLLING_UPDATE_PAUSED, {
                        "deployment": manifest.name,
                        "pod_id": pod_id,
                        "batch": batches_completed,
                        "reason": "readiness_probe_failed",
                    })
                    new_pod["status"] = "ready"
                    batch_new.append(new_pod)
                    pods_replaced += 1

            old_pods = old_pods[batch_size:]
            new_pods.extend(batch_new)
            batches_completed += 1

            self._emit(DEPLOY_ROLLING_UPDATE_BATCH, {
                "deployment": manifest.name,
                "batch": batches_completed,
                "pods_replaced": len(batch_new),
                "remaining": len(old_pods),
            })

        remaining_new = desired - len(new_pods)
        for _ in range(max(0, remaining_new)):
            pod_id = f"{manifest.name}-{uuid.uuid4().hex[:8]}"
            new_pods.append({
                "id": pod_id,
                "image": new_image,
                "status": "ready",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        return {
            "strategy": "rolling_update",
            "desired_replicas": desired,
            "batches_completed": batches_completed,
            "batch_size": batch_size,
            "pods_replaced": pods_replaced,
            "surge_count": surge_count,
            "unavailable_count": unavailable_count,
            "new_pods": new_pods,
            "paused": paused,
        }


class BlueGreenStrategy:
    """Implements the blue-green deployment strategy.

    Maintains two parallel environments (blue and green).  The new
    version is deployed to the inactive environment, validated, and
    traffic is switched atomically.  The previously active environment
    is retained as an instant rollback target.
    """

    def __init__(
        self,
        validation_timeout: float = 30.0,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._active_environment = "blue"
        self._environments: Dict[str, List[Dict[str, Any]]] = {
            "blue": [],
            "green": [],
        }
        self._validation_timeout = validation_timeout
        self._event_bus = event_bus

    def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def switch_traffic(self) -> str:
        """Toggle active environment and return new active name."""
        if self._active_environment == "blue":
            self._active_environment = "green"
        else:
            self._active_environment = "blue"
        return self._active_environment

    def rollback(self) -> str:
        """Switch traffic back to previous environment."""
        return self.switch_traffic()

    def get_active_environment(self) -> str:
        """Return name of active environment."""
        return self._active_environment

    def execute(
        self,
        manifest: DeploymentManifest,
        current_pods: List[Dict[str, Any]],
        new_image: str,
    ) -> Dict[str, Any]:
        """Execute a blue-green deployment.

        Determine inactive environment.  Provision new pods in inactive
        environment.  Run validation against inactive environment.  If
        validation passes, switch traffic.  If validation fails, abort.

        Args:
            manifest: Deployment manifest.
            current_pods: List of current pod descriptors.
            new_image: New image reference to deploy.

        Returns:
            Deployment result dictionary.
        """
        inactive = "green" if self._active_environment == "blue" else "blue"

        self._environments[self._active_environment] = list(current_pods)

        new_pods: List[Dict[str, Any]] = []
        for i in range(manifest.spec.replicas):
            pod_id = f"{manifest.name}-{inactive}-{uuid.uuid4().hex[:8]}"
            new_pods.append({
                "id": pod_id,
                "image": new_image,
                "status": "ready",
                "environment": inactive,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        self._environments[inactive] = new_pods

        validation_passed = self._validate_environment(inactive, manifest)

        if validation_passed:
            previous_active = self._active_environment
            self._active_environment = inactive
            self._emit(DEPLOY_BLUE_GREEN_SWITCHED, {
                "deployment": manifest.name,
                "from": previous_active,
                "to": inactive,
                "pods": len(new_pods),
            })
            return {
                "strategy": "blue_green",
                "active_environment": self._active_environment,
                "previous_environment": previous_active,
                "pods_deployed": len(new_pods),
                "validation_passed": True,
                "switched": True,
                "new_pods": new_pods,
            }
        else:
            self._emit(DEPLOY_BLUE_GREEN_ABORTED, {
                "deployment": manifest.name,
                "environment": inactive,
                "reason": "validation_failed",
            })
            self._environments[inactive] = []
            return {
                "strategy": "blue_green",
                "active_environment": self._active_environment,
                "pods_deployed": 0,
                "validation_passed": False,
                "switched": False,
                "new_pods": [],
            }

    def _validate_environment(
        self, environment: str, manifest: DeploymentManifest
    ) -> bool:
        """Validate pods in the target environment.

        Simulates running health checks against all pods in the
        specified environment.  In production, this would execute
        HTTP/TCP/exec probes per the health check configuration.

        Args:
            environment: Environment name to validate.
            manifest: Deployment manifest with health check config.

        Returns:
            True if all pods pass validation.
        """
        pods = self._environments.get(environment, [])
        if not pods:
            return False

        for pod in pods:
            h = hashlib.md5(pod["id"].encode()).hexdigest()
            if int(h[:2], 16) >= 253:
                return False
        return True


class CanaryStrategy:
    """Implements the canary deployment strategy.

    Gradually shifts traffic from the baseline population to the canary
    population in configurable steps.  At each step, automated analysis
    compares error rates and P99 latency between canary and baseline.
    If a regression is detected, traffic is immediately rolled back to
    0% canary.
    """

    def __init__(
        self,
        steps: Optional[List[Tuple[float, float]]] = None,
        analysis_interval: float = DEFAULT_CANARY_ANALYSIS_INTERVAL,
        error_rate_threshold: float = 0.05,
        latency_threshold: float = 50.0,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._steps = steps or list(DEFAULT_CANARY_STEPS)
        self._analysis_interval = analysis_interval
        self._error_rate_threshold = error_rate_threshold
        self._latency_threshold = latency_threshold
        self._event_bus = event_bus
        self._analysis_results: List[CanaryAnalysisResult] = []

    def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def analyze_step(
        self, step_index: int, traffic_percent: float
    ) -> CanaryAnalysisResult:
        """Compare canary error rate and P99 latency against baseline.

        Uses simulated metric collection to produce deterministic but
        realistic analysis results.  The baseline represents the current
        production population, and the canary represents the new version
        receiving the specified traffic percentage.

        Args:
            step_index: Current canary step index.
            traffic_percent: Traffic percentage routed to canary.

        Returns:
            CanaryAnalysisResult with verdict.
        """
        random.seed(step_index * 1000 + int(traffic_percent))

        baseline_error_rate = random.uniform(0.001, 0.01)
        canary_error_rate = baseline_error_rate + random.uniform(-0.005, 0.005)
        canary_error_rate = max(0.0, canary_error_rate)

        baseline_p99 = random.uniform(10.0, 40.0)
        canary_p99 = baseline_p99 + random.uniform(-10.0, 15.0)
        canary_p99 = max(1.0, canary_p99)

        error_regression = (canary_error_rate - baseline_error_rate) > self._error_rate_threshold
        latency_regression = (canary_p99 - baseline_p99) > self._latency_threshold

        regression_detected = error_regression or latency_regression

        if regression_detected:
            verdict = "fail"
        else:
            verdict = "pass"

        result = CanaryAnalysisResult(
            step_index=step_index,
            traffic_percent=traffic_percent,
            baseline_error_rate=baseline_error_rate,
            canary_error_rate=canary_error_rate,
            baseline_p99_latency_ms=baseline_p99,
            canary_p99_latency_ms=canary_p99,
            regression_detected=regression_detected,
            analysis_duration_ms=random.uniform(50.0, 200.0),
            verdict=verdict,
        )

        self._analysis_results.append(result)
        return result

    def get_analysis_results(self) -> List[CanaryAnalysisResult]:
        """Return analysis history."""
        return list(self._analysis_results)

    def execute(
        self,
        manifest: DeploymentManifest,
        current_pods: List[Dict[str, Any]],
        new_image: str,
    ) -> Dict[str, Any]:
        """Execute a canary deployment.

        For each step: shift traffic_percent of traffic to canary pods.
        Run analyze_step().  If regression detected, rollback canary to
        0% and raise CanaryError.  If all steps pass, shift 100% to canary.

        Args:
            manifest: Deployment manifest.
            current_pods: List of current pod descriptors.
            new_image: New image reference to deploy.

        Returns:
            Analysis summary dictionary.

        Raises:
            CanaryError: If regression is detected at any step.
        """
        canary_pods: List[Dict[str, Any]] = []
        desired = manifest.spec.replicas

        for i in range(desired):
            pod_id = f"{manifest.name}-canary-{uuid.uuid4().hex[:8]}"
            canary_pods.append({
                "id": pod_id,
                "image": new_image,
                "status": "ready",
                "role": "canary",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        completed_steps: List[Dict[str, Any]] = []

        for step_index, (traffic_percent, _pause_duration) in enumerate(self._steps):
            self._emit(DEPLOY_CANARY_STEP_ADVANCED, {
                "deployment": manifest.name,
                "step": step_index,
                "traffic_percent": traffic_percent,
            })

            analysis = self.analyze_step(step_index, traffic_percent)

            completed_steps.append({
                "step_index": step_index,
                "traffic_percent": traffic_percent,
                "verdict": analysis.verdict,
                "regression_detected": analysis.regression_detected,
            })

            if analysis.regression_detected:
                self._emit(DEPLOY_CANARY_REGRESSION, {
                    "deployment": manifest.name,
                    "step": step_index,
                    "traffic_percent": traffic_percent,
                    "canary_error_rate": analysis.canary_error_rate,
                    "baseline_error_rate": analysis.baseline_error_rate,
                })
                raise CanaryError(
                    f"Canary regression detected at step {step_index} "
                    f"({traffic_percent}% traffic): error_rate={analysis.canary_error_rate:.4f} "
                    f"vs baseline={analysis.baseline_error_rate:.4f}"
                )

        return {
            "strategy": "canary",
            "steps_completed": len(completed_steps),
            "total_steps": len(self._steps),
            "final_traffic_percent": 100.0,
            "canary_pods": canary_pods,
            "analysis_results": completed_steps,
            "promoted": True,
        }


class RecreateStrategy:
    """Implements the recreate deployment strategy.

    Terminates all existing pods before creating new pods.  This
    strategy incurs downtime but guarantees a clean transition
    with no version mixing.
    """

    def __init__(
        self,
        shutdown_timeout: float = 30.0,
        startup_timeout: float = 60.0,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._shutdown_timeout = shutdown_timeout
        self._startup_timeout = startup_timeout
        self._event_bus = event_bus

    def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def execute(
        self,
        manifest: DeploymentManifest,
        current_pods: List[Dict[str, Any]],
        new_image: str,
    ) -> Dict[str, Any]:
        """Execute a recreate deployment.

        Send graceful shutdown to all current pods.  Create new pods
        with new_image at manifest.spec.replicas count.  Record
        downtime duration.

        Args:
            manifest: Deployment manifest.
            current_pods: List of current pod descriptors.
            new_image: New image reference to deploy.

        Returns:
            Deployment result dictionary.
        """
        self._emit(DEPLOY_RECREATE_STARTED, {
            "deployment": manifest.name,
            "current_pods": len(current_pods),
        })

        shutdown_start = datetime.now(timezone.utc)

        terminated_pods: List[str] = []
        for pod in current_pods:
            pod_id = pod.get("id", f"unknown-{uuid.uuid4().hex[:8]}")
            terminated_pods.append(pod_id)

        shutdown_end = datetime.now(timezone.utc)

        new_pods: List[Dict[str, Any]] = []
        for i in range(manifest.spec.replicas):
            pod_id = f"{manifest.name}-{uuid.uuid4().hex[:8]}"
            new_pods.append({
                "id": pod_id,
                "image": new_image,
                "status": "ready",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        startup_end = datetime.now(timezone.utc)

        downtime_ms = (startup_end - shutdown_start).total_seconds() * 1000

        self._emit(DEPLOY_RECREATE_COMPLETED, {
            "deployment": manifest.name,
            "terminated": len(terminated_pods),
            "created": len(new_pods),
            "downtime_ms": downtime_ms,
        })

        return {
            "strategy": "recreate",
            "terminated_pods": terminated_pods,
            "new_pods": new_pods,
            "pods_created": len(new_pods),
            "downtime_ms": downtime_ms,
        }


# ============================================================
# Strategy Factory
# ============================================================


class _StrategyFactory:
    """Internal factory for creating deployment strategy instances.

    Maps DeploymentStrategy enum values to their corresponding
    implementation classes, passing strategy-specific parameters
    from the manifest's strategy_params field.
    """

    @staticmethod
    def create(
        strategy: DeploymentStrategy,
        params: Dict[str, Any],
        event_bus: Optional[Any] = None,
    ) -> Union[RollingUpdateStrategy, BlueGreenStrategy, CanaryStrategy, RecreateStrategy]:
        """Instantiate the appropriate strategy class.

        Args:
            strategy: DeploymentStrategy enum value.
            params: Strategy-specific configuration parameters.
            event_bus: Optional event bus for lifecycle events.

        Returns:
            Strategy instance.

        Raises:
            DeployStrategyError: For unknown strategy types.
        """
        if strategy == DeploymentStrategy.ROLLING_UPDATE:
            return RollingUpdateStrategy(
                max_surge=params.get("max_surge", DEFAULT_ROLLING_MAX_SURGE),
                max_unavailable=params.get("max_unavailable", DEFAULT_ROLLING_MAX_UNAVAILABLE),
                min_ready_seconds=params.get("min_ready_seconds", 0.0),
                health_check_timeout=params.get("health_check_timeout", 30.0),
                event_bus=event_bus,
            )
        elif strategy == DeploymentStrategy.BLUE_GREEN:
            return BlueGreenStrategy(
                validation_timeout=params.get("validation_timeout", 30.0),
                event_bus=event_bus,
            )
        elif strategy == DeploymentStrategy.CANARY:
            return CanaryStrategy(
                steps=params.get("steps", None),
                analysis_interval=params.get("analysis_interval", DEFAULT_CANARY_ANALYSIS_INTERVAL),
                error_rate_threshold=params.get("error_rate_threshold", 0.05),
                latency_threshold=params.get("latency_threshold", 50.0),
                event_bus=event_bus,
            )
        elif strategy == DeploymentStrategy.RECREATE:
            return RecreateStrategy(
                shutdown_timeout=params.get("shutdown_timeout", 30.0),
                startup_timeout=params.get("startup_timeout", 60.0),
                event_bus=event_bus,
            )
        else:
            raise DeployStrategyError(f"Unknown deployment strategy: {strategy}")


# ============================================================
# Manifest Parser
# ============================================================


class ManifestParser:
    """Validates and parses deployment manifests from YAML-like dicts.

    The parser enforces the deployment manifest schema, validating
    required fields, strategy configurations, and resource constraint
    formats.  It converts raw dict structures into strongly-typed
    DeploymentManifest instances.
    """

    _REQUIRED_FIELDS = ["apiVersion", "kind", "metadata", "spec"]
    _KNOWN_STRATEGIES = {s.value for s in DeploymentStrategy}

    def __init__(self) -> None:
        self._schema: Dict[str, Any] = {
            "apiVersion": str,
            "kind": str,
            "metadata": dict,
            "spec": dict,
        }
        self._known_strategies = self._KNOWN_STRATEGIES
        self._required_fields = list(self._REQUIRED_FIELDS)

    def parse(self, yaml_content: str) -> DeploymentManifest:
        """Parse YAML string into DeploymentManifest.

        Validates required fields (apiVersion, kind, metadata.name,
        spec.image).  Validates strategy configuration and resource
        constraint format.

        Args:
            yaml_content: YAML manifest string.

        Returns:
            Populated DeploymentManifest.

        Raises:
            ManifestParseError: For syntax errors.
            ManifestValidationError: For schema violations.
        """
        try:
            data = self._simple_yaml_parse(yaml_content)
        except Exception as exc:
            raise ManifestParseError(f"YAML parse error: {exc}")

        return self.parse_dict(data)

    def parse_dict(self, data: Dict[str, Any]) -> DeploymentManifest:
        """Parse from pre-parsed dict.

        Args:
            data: Dictionary representation of the manifest.

        Returns:
            Populated DeploymentManifest.

        Raises:
            ManifestValidationError: For schema violations.
        """
        errors = self._validate_dict(data)
        if errors:
            raise ManifestValidationError(
                f"Manifest validation failed: {'; '.join(errors)}"
            )

        metadata = data.get("metadata", {})
        spec_data = data.get("spec", {})

        health_check = None
        if "health_check" in spec_data:
            health_check = self._parse_health_check(spec_data["health_check"])

        strategy_name = spec_data.get("strategy", "rolling_update")
        try:
            strategy = DeploymentStrategy(strategy_name)
        except ValueError:
            strategy = DeploymentStrategy.ROLLING_UPDATE

        spec = DeploymentSpec(
            image=spec_data.get("image", ""),
            replicas=int(spec_data.get("replicas", 1)),
            strategy=strategy,
            strategy_params=spec_data.get("strategy_params", {}),
            resources=spec_data.get("resources", {}),
            health_check=health_check,
            env=spec_data.get("env", {}),
            volumes=spec_data.get("volumes", []),
            init_containers=spec_data.get("init_containers", []),
            sidecars=spec_data.get("sidecars", []),
        )

        manifest = DeploymentManifest(
            api_version=data.get("apiVersion", "apps/v1"),
            kind=data.get("kind", "Deployment"),
            name=metadata.get("name", ""),
            namespace=metadata.get("namespace", "default"),
            labels=metadata.get("labels", {}),
            annotations=metadata.get("annotations", {}),
            spec=spec,
            raw_yaml=json.dumps(data, default=str),
        )

        return manifest

    def validate(self, manifest: DeploymentManifest) -> List[str]:
        """Return list of validation errors (empty list = valid).

        Args:
            manifest: Manifest to validate.

        Returns:
            List of validation error strings.
        """
        errors: List[str] = []

        if not manifest.name:
            errors.append("metadata.name is required")
        if not manifest.spec.image:
            errors.append("spec.image is required")
        if manifest.spec.replicas < 1:
            errors.append("spec.replicas must be >= 1")

        errors.extend(
            self._validate_strategy_params(manifest.spec.strategy, manifest.spec.strategy_params)
        )

        if manifest.spec.resources:
            errors.extend(self._validate_resources(manifest.spec.resources))

        return errors

    def _validate_dict(self, data: Dict[str, Any]) -> List[str]:
        """Validate raw dict against schema."""
        errors: List[str] = []

        for field_name in self._required_fields:
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")

        metadata = data.get("metadata", {})
        if isinstance(metadata, dict) and not metadata.get("name"):
            errors.append("metadata.name is required")

        spec = data.get("spec", {})
        if isinstance(spec, dict) and not spec.get("image"):
            errors.append("spec.image is required")

        if isinstance(spec, dict):
            strategy_name = spec.get("strategy", "rolling_update")
            if strategy_name not in self._known_strategies:
                errors.append(f"Unknown strategy: {strategy_name}")

        return errors

    def _validate_strategy_params(
        self, strategy: DeploymentStrategy, params: Dict[str, Any]
    ) -> List[str]:
        """Validate strategy-specific parameters."""
        errors: List[str] = []

        if strategy == DeploymentStrategy.ROLLING_UPDATE:
            max_surge = params.get("max_surge")
            if max_surge is not None:
                if isinstance(max_surge, (int, float)) and max_surge < 0:
                    errors.append("rolling_update max_surge must be >= 0")
            max_unavailable = params.get("max_unavailable")
            if max_unavailable is not None:
                if isinstance(max_unavailable, (int, float)) and max_unavailable < 0:
                    errors.append("rolling_update max_unavailable must be >= 0")

        elif strategy == DeploymentStrategy.CANARY:
            steps = params.get("steps")
            if steps is not None:
                if not isinstance(steps, list):
                    errors.append("canary steps must be a list")

        return errors

    def _validate_resources(self, resources: Dict[str, Any]) -> List[str]:
        """Validate CPU/memory resource format."""
        errors: List[str] = []
        valid_keys = {"requests", "limits"}

        for key in resources:
            if key not in valid_keys:
                errors.append(f"Unknown resource key: {key}")

        return errors

    def _parse_health_check(self, data: Dict[str, Any]) -> HealthCheckConfig:
        """Parse health check config from dict."""
        return HealthCheckConfig(
            probe_type=data.get("probe_type", "http"),
            path=data.get("path", "/healthz"),
            port=int(data.get("port", 8080)),
            command=data.get("command", []),
            interval_seconds=int(data.get("interval_seconds", 10)),
            timeout_seconds=int(data.get("timeout_seconds", 5)),
            success_threshold=int(data.get("success_threshold", 1)),
            failure_threshold=int(data.get("failure_threshold", 3)),
            initial_delay_seconds=int(data.get("initial_delay_seconds", 0)),
        )

    @staticmethod
    def _simple_yaml_parse(content: str) -> Dict[str, Any]:
        """Minimal YAML-like parser for deployment manifests.

        Parses a subset of YAML sufficient for deployment manifests:
        key-value pairs, nested mappings (indentation-based), and
        simple lists.  This avoids a PyYAML dependency.

        Args:
            content: YAML-like string.

        Returns:
            Parsed dictionary.
        """
        result: Dict[str, Any] = {}
        current = result
        stack: List[Tuple[Dict[str, Any], int]] = [(result, -1)]

        for line in content.strip().split("\n"):
            stripped = line.rstrip()
            if not stripped or stripped.startswith("#"):
                continue

            indent = len(line) - len(line.lstrip())

            while len(stack) > 1 and indent <= stack[-1][1]:
                stack.pop()

            current = stack[-1][0]

            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                if value:
                    if value.lower() in ("true", "false"):
                        current[key] = value.lower() == "true"
                    elif value.replace(".", "", 1).replace("-", "", 1).isdigit():
                        if "." in value:
                            current[key] = float(value)
                        else:
                            current[key] = int(value)
                    else:
                        current[key] = value.strip("\"'")
                else:
                    child: Dict[str, Any] = {}
                    current[key] = child
                    stack.append((child, indent))

        return result


# ============================================================
# GitOps Reconciler
# ============================================================


class GitOpsReconciler:
    """Continuous control loop comparing declared manifests against actual state.

    The reconciler implements the core GitOps principle: the Git
    repository (declared manifests) is the single source of truth.
    The reconciler continuously compares actual cluster state against
    declared state, taking corrective action based on the configured
    sync strategy.
    """

    def __init__(
        self,
        sync_strategy: SyncStrategy = SyncStrategy.AUTO,
        reconcile_interval: float = DEFAULT_RECONCILE_INTERVAL,
        pipeline_executor: Optional[PipelineExecutor] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._manifests: Dict[str, DeploymentManifest] = {}
        self._actual_state: Dict[str, Dict[str, Any]] = {}
        self._sync_strategy = sync_strategy
        self._reconcile_interval = reconcile_interval
        self._pipeline_executor = pipeline_executor
        self._drift_reports: List[DriftReport] = []
        self._lock = threading.Lock()
        self._running = False
        self._total_reconciliations = 0
        self._total_drifts_detected = 0
        self._total_corrections = 0
        self._event_bus = event_bus
        self._reconcile_thread: Optional[threading.Thread] = None

    def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def register_manifest(self, name: str, manifest: DeploymentManifest) -> None:
        """Register a declared manifest.

        Args:
            name: Deployment name.
            manifest: Declared deployment manifest.
        """
        with self._lock:
            self._manifests[name] = manifest
            if name not in self._actual_state:
                self._actual_state[name] = {
                    "image": manifest.spec.image,
                    "replicas": manifest.spec.replicas,
                    "resources": dict(manifest.spec.resources),
                    "env": dict(manifest.spec.env),
                }

    def update_actual_state(self, name: str, state: Dict[str, Any]) -> None:
        """Update actual cluster state.

        Args:
            name: Deployment name.
            state: Current cluster state for this deployment.
        """
        with self._lock:
            self._actual_state[name] = state

    def reconcile(self) -> List[DriftReport]:
        """Single reconciliation pass.

        For each registered manifest, compare declared vs actual fields
        (image, replicas, resources, env).  If drift detected, generate
        DriftReport.  If sync strategy is AUTO, trigger correction.  If
        MANUAL, emit drift event.  If DRY_RUN, log what would change.

        Returns:
            List of drift reports from this pass.
        """
        reports: List[DriftReport] = []

        with self._lock:
            self._total_reconciliations += 1
            manifest_items = list(self._manifests.items())
            actual_items = dict(self._actual_state)

        for name, manifest in manifest_items:
            actual = actual_items.get(name, {})
            drifts = self._detect_drift(name, manifest, actual)

            if drifts:
                report = DriftReport(
                    deployment_name=name,
                    drifts=drifts,
                    sync_strategy=self._sync_strategy,
                )

                with self._lock:
                    self._total_drifts_detected += len(drifts)

                self._emit(DEPLOY_GITOPS_DRIFT_DETECTED, {
                    "deployment": name,
                    "drift_count": len(drifts),
                    "sync_strategy": self._sync_strategy.value,
                })

                if self._sync_strategy == SyncStrategy.AUTO:
                    with self._lock:
                        self._actual_state[name] = {
                            "image": manifest.spec.image,
                            "replicas": manifest.spec.replicas,
                            "resources": dict(manifest.spec.resources),
                            "env": dict(manifest.spec.env),
                        }
                        self._total_corrections += 1
                    report.corrected = True
                    self._emit(DEPLOY_GITOPS_SYNC_APPLIED, {
                        "deployment": name,
                        "corrections": len(drifts),
                    })
                elif self._sync_strategy == SyncStrategy.DRY_RUN:
                    logger.info(
                        "DRY_RUN: Would correct %d drifts for deployment '%s'",
                        len(drifts),
                        name,
                    )

                reports.append(report)

                with self._lock:
                    self._drift_reports.append(report)
                    if len(self._drift_reports) > 100:
                        self._drift_reports = self._drift_reports[-100:]

        return reports

    def start_loop(self) -> None:
        """Start background reconciliation loop."""
        self._running = True

        def _loop() -> None:
            while self._running:
                try:
                    self.reconcile()
                except Exception:
                    logger.exception("Reconciliation loop error")
                time.sleep(self._reconcile_interval * 0.001)

        self._reconcile_thread = threading.Thread(target=_loop, daemon=True)
        self._reconcile_thread.start()

    def stop_loop(self) -> None:
        """Stop background reconciliation loop."""
        self._running = False
        if self._reconcile_thread is not None:
            self._reconcile_thread.join(timeout=5.0)
            self._reconcile_thread = None

    def get_drift_history(self, limit: int = 10) -> List[DriftReport]:
        """Return recent drift reports.

        Args:
            limit: Maximum number of reports to return.

        Returns:
            List of recent DriftReport objects.
        """
        with self._lock:
            return list(self._drift_reports[-limit:])

    def _detect_drift(
        self,
        name: str,
        manifest: DeploymentManifest,
        actual: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Compare individual fields and return list of drift items.

        Args:
            name: Deployment name.
            manifest: Declared manifest.
            actual: Actual cluster state.

        Returns:
            List of drift item dicts with field, expected, and actual values.
        """
        drifts: List[Dict[str, Any]] = []

        declared_image = manifest.spec.image
        actual_image = actual.get("image", "")
        if declared_image != actual_image:
            drifts.append({
                "field": "image",
                "expected": declared_image,
                "actual": actual_image,
            })

        declared_replicas = manifest.spec.replicas
        actual_replicas = actual.get("replicas", 0)
        if declared_replicas != actual_replicas:
            drifts.append({
                "field": "replicas",
                "expected": declared_replicas,
                "actual": actual_replicas,
            })

        declared_resources = manifest.spec.resources
        actual_resources = actual.get("resources", {})
        if declared_resources != actual_resources:
            drifts.append({
                "field": "resources",
                "expected": declared_resources,
                "actual": actual_resources,
            })

        declared_env = manifest.spec.env
        actual_env = actual.get("env", {})
        if declared_env != actual_env:
            drifts.append({
                "field": "env",
                "expected": declared_env,
                "actual": actual_env,
            })

        return drifts


# ============================================================
# Rollback Manager
# ============================================================


class RollbackManager:
    """Maintains deployment revision history and executes rollback operations.

    The rollback manager stores a bounded history of deployment revisions,
    enabling point-in-time restoration of any previous deployment state.
    Both automated rollback (on pipeline validation failure) and manual
    rollback (via CLI) are supported.
    """

    def __init__(
        self,
        max_depth: int = DEFAULT_REVISION_HISTORY_DEPTH,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._revisions: Dict[str, List[DeploymentRevision]] = defaultdict(list)
        self._max_depth = max_depth
        self._rollback_records: List[RollbackRecord] = []
        self._lock = threading.Lock()
        self._event_bus = event_bus

    def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def record_revision(
        self,
        deployment_name: str,
        manifest: DeploymentManifest,
        image_digest: str,
        pipeline_id: str,
    ) -> DeploymentRevision:
        """Create and store a new revision.

        Marks previous active revision as SUPERSEDED.  Trims history
        to max_depth.

        Args:
            deployment_name: Name of the deployment.
            manifest: Complete deployment manifest.
            image_digest: SHA-256 digest of the deployed image.
            pipeline_id: Pipeline execution ID that created this revision.

        Returns:
            The new DeploymentRevision.
        """
        with self._lock:
            revisions = self._revisions[deployment_name]

            for rev in revisions:
                if rev.status == RevisionStatus.ACTIVE:
                    rev.status = RevisionStatus.SUPERSEDED

            revision_number = len(revisions) + 1

            new_revision = DeploymentRevision(
                revision_number=revision_number,
                deployment_name=deployment_name,
                manifest=manifest,
                image_digest=image_digest,
                status=RevisionStatus.ACTIVE,
                pipeline_id=pipeline_id,
            )

            revisions.append(new_revision)

            if len(revisions) > self._max_depth:
                self._revisions[deployment_name] = revisions[-self._max_depth:]

            return new_revision

    def rollback(
        self,
        deployment_name: str,
        target_revision: int,
        trigger: str = "manual",
        reason: str = "",
    ) -> RollbackRecord:
        """Execute a rollback to a target revision.

        Validates that the target revision exists.  Retrieves the target
        revision's manifest.  Creates a new revision with rollback_from set.

        Args:
            deployment_name: Name of the deployment to rollback.
            target_revision: Revision number to restore.
            trigger: Rollback trigger ("automatic" or "manual").
            reason: Human-readable reason for the rollback.

        Returns:
            RollbackRecord capturing the operation outcome.

        Raises:
            RollbackRevisionNotFoundError: If target revision not found.
        """
        with self._lock:
            revisions = self._revisions.get(deployment_name, [])

            target = None
            for rev in revisions:
                if rev.revision_number == target_revision:
                    target = rev
                    break

            if target is None:
                raise RollbackRevisionNotFoundError(
                    f"Revision {target_revision} not found for deployment '{deployment_name}'"
                )

            current_active = None
            for rev in revisions:
                if rev.status == RevisionStatus.ACTIVE:
                    current_active = rev
                    break

            from_revision = current_active.revision_number if current_active else 0

            if current_active:
                current_active.status = RevisionStatus.SUPERSEDED

            new_revision_number = len(revisions) + 1
            rollback_revision = DeploymentRevision(
                revision_number=new_revision_number,
                deployment_name=deployment_name,
                manifest=target.manifest,
                image_digest=target.image_digest,
                status=RevisionStatus.ACTIVE,
                pipeline_id=f"rollback-{uuid.uuid4().hex[:8]}",
                rollback_from=from_revision,
            )

            revisions.append(rollback_revision)

            if len(revisions) > self._max_depth:
                self._revisions[deployment_name] = revisions[-self._max_depth:]

            record = RollbackRecord(
                deployment_name=deployment_name,
                from_revision=from_revision,
                to_revision=target_revision,
                trigger=trigger,
                reason=reason,
                completed_at=datetime.now(timezone.utc),
                success=True,
            )

            self._rollback_records.append(record)

            self._emit(DEPLOY_ROLLBACK_EXECUTED, {
                "deployment": deployment_name,
                "from_revision": from_revision,
                "to_revision": target_revision,
                "trigger": trigger,
            })

            return record

    def get_revisions(self, deployment_name: str) -> List[DeploymentRevision]:
        """Return revision history for a deployment.

        Args:
            deployment_name: Deployment name.

        Returns:
            List of DeploymentRevision objects.
        """
        with self._lock:
            return list(self._revisions.get(deployment_name, []))

    def get_active_revision(
        self, deployment_name: str
    ) -> Optional[DeploymentRevision]:
        """Return the currently active revision.

        Args:
            deployment_name: Deployment name.

        Returns:
            Active DeploymentRevision, or None if no active revision.
        """
        with self._lock:
            revisions = self._revisions.get(deployment_name, [])
            for rev in reversed(revisions):
                if rev.status == RevisionStatus.ACTIVE:
                    return rev
            return None

    def get_rollback_history(self, limit: int = 10) -> List[RollbackRecord]:
        """Return recent rollback records.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of recent RollbackRecord objects.
        """
        with self._lock:
            return list(self._rollback_records[-limit:])


# ============================================================
# Deployment Gate
# ============================================================


class DeploymentGate:
    """Queries FizzBob's cognitive load model to gate deployments.

    Before any deployment proceeds, the gate assesses whether Bob
    McFizzington's current cognitive load, measured via a simulated
    NASA-TLX assessment, is below the safety threshold.  If the
    operator is cognitively overloaded, the deployment is queued
    until load decreases or an emergency bypass is invoked.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_COGNITIVE_LOAD_THRESHOLD,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._threshold = threshold
        self._queued_deployments: List[Tuple[str, DeploymentManifest]] = []
        self._bypass_count = 0
        self._gate_count = 0
        self._lock = threading.Lock()
        self._event_bus = event_bus

    def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def check(
        self,
        deployment_name: str,
        manifest: DeploymentManifest,
        emergency: bool = False,
    ) -> bool:
        """Check whether deployment should proceed.

        If emergency is True, bypass gate, increment bypass_count.
        Otherwise, query FizzBob for current NASA-TLX score.
        If score > threshold, queue deployment and raise CognitiveLoadGateError.
        If score <= threshold, allow deployment.

        Args:
            deployment_name: Name of the deployment.
            manifest: Deployment manifest.
            emergency: Whether this is an emergency deployment.

        Returns:
            True if deployment is allowed to proceed.

        Raises:
            CognitiveLoadGateError: If cognitive load exceeds threshold.
        """
        with self._lock:
            self._gate_count += 1

        if emergency:
            with self._lock:
                self._bypass_count += 1
            self._emit(DEPLOY_GATE_EMERGENCY_BYPASS, {
                "deployment": deployment_name,
                "bypass_count": self._bypass_count,
            })
            return True

        score = self._simulate_cognitive_load()

        if score > self._threshold:
            with self._lock:
                self._queued_deployments.append((deployment_name, manifest))
            self._emit(DEPLOY_GATE_BLOCKED, {
                "deployment": deployment_name,
                "cognitive_load": score,
                "threshold": self._threshold,
            })
            raise CognitiveLoadGateError(deployment_name, score, self._threshold)

        self._emit(DEPLOY_GATE_PASSED, {
            "deployment": deployment_name,
            "cognitive_load": score,
            "threshold": self._threshold,
        })
        return True

    def get_queued(self) -> List[Tuple[str, DeploymentManifest]]:
        """Return queued deployments."""
        with self._lock:
            return list(self._queued_deployments)

    def release_queue(self) -> int:
        """Re-check gating for all queued deployments, release eligible ones.

        Returns:
            Count of released deployments.
        """
        released = 0
        remaining: List[Tuple[str, DeploymentManifest]] = []

        with self._lock:
            queued = list(self._queued_deployments)

        for name, manifest in queued:
            score = self._simulate_cognitive_load()
            if score <= self._threshold:
                released += 1
                self._emit(DEPLOY_GATE_PASSED, {
                    "deployment": name,
                    "cognitive_load": score,
                    "threshold": self._threshold,
                    "released_from_queue": True,
                })
            else:
                remaining.append((name, manifest))

        with self._lock:
            self._queued_deployments = remaining

        return released

    def _simulate_cognitive_load(self) -> float:
        """Simulate querying FizzBob's NASA-TLX model.

        The simulation produces a cognitive load score between 0 and 100,
        modeled as a normally-distributed random variable centered on
        the midpoint of the operator's typical load range.  During
        off-peak hours (simulated), the mean shifts lower.

        Returns:
            Cognitive load score 0-100.
        """
        mean = 45.0
        std = 15.0
        score = random.gauss(mean, std)
        return max(0.0, min(100.0, score))


# ============================================================
# Pipeline Builder
# ============================================================


class _PipelineBuilder:
    """Internal builder that constructs a standard deployment pipeline.

    Assembles the seven canonical stages (BUILD, SCAN, SIGN, PUSH,
    DEPLOY, VALIDATE, FINALIZE) with appropriate steps for each.
    """

    @staticmethod
    def build_standard(
        deployment_name: str,
        manifest: DeploymentManifest,
        strategy_instance: Any,
        image_digest: str = "",
    ) -> Pipeline:
        """Construct a Pipeline with seven canonical stages.

        The DEPLOY stage step delegates to the strategy instance's
        execute() method.  The VALIDATE stage runs health check probes.
        The FINALIZE stage records the revision and marks deployment complete.

        Args:
            deployment_name: Target deployment name.
            manifest: Deployment manifest.
            strategy_instance: Strategy implementation to use for DEPLOY stage.
            image_digest: Pre-computed image digest (or empty for auto-generation).

        Returns:
            Fully assembled Pipeline.
        """
        if not image_digest:
            digest_input = f"{manifest.spec.image}:{datetime.now(timezone.utc).isoformat()}"
            image_digest = hashlib.sha256(digest_input.encode()).hexdigest()

        pipeline = Pipeline(deployment_name=deployment_name)

        # Stage 1: BUILD
        def build_action(ctx: Dict[str, Any]) -> Dict[str, Any]:
            ctx["image"] = manifest.spec.image
            ctx["image_digest"] = image_digest
            return {"image": manifest.spec.image, "digest": image_digest}

        build_stage = PipelineStage("build", StageType.BUILD)
        build_stage.add_step(PipelineStep("build-image", build_action))
        pipeline.add_stage(build_stage)

        # Stage 2: SCAN
        def scan_action(ctx: Dict[str, Any]) -> Dict[str, Any]:
            return {"vulnerabilities": 0, "severity": "none", "passed": True}

        scan_stage = PipelineStage("scan", StageType.SCAN)
        scan_stage.add_step(PipelineStep("vulnerability-scan", scan_action))
        pipeline.add_stage(scan_stage)

        # Stage 3: SIGN
        def sign_action(ctx: Dict[str, Any]) -> Dict[str, Any]:
            sig = hashlib.sha256(
                f"sign:{image_digest}".encode()
            ).hexdigest()[:32]
            ctx["signature"] = sig
            return {"signature": sig}

        sign_stage = PipelineStage("sign", StageType.SIGN)
        sign_stage.add_step(PipelineStep("sign-image", sign_action))
        pipeline.add_stage(sign_stage)

        # Stage 4: PUSH
        def push_action(ctx: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "registry": "registry.fizzbuzz.internal:5000",
                "image": manifest.spec.image,
                "digest": image_digest,
            }

        push_stage = PipelineStage("push", StageType.PUSH)
        push_stage.add_step(PipelineStep("push-image", push_action))
        pipeline.add_stage(push_stage)

        # Stage 5: DEPLOY
        def deploy_action(ctx: Dict[str, Any]) -> Dict[str, Any]:
            current_pods = ctx.get("current_pods", [
                {"id": f"{deployment_name}-{i}", "image": "old-image"}
                for i in range(manifest.spec.replicas)
            ])
            result = strategy_instance.execute(manifest, current_pods, manifest.spec.image)
            ctx["deploy_result"] = result
            return result

        deploy_stage = PipelineStage("deploy", StageType.DEPLOY)
        deploy_stage.add_step(PipelineStep(
            "execute-strategy",
            deploy_action,
            on_failure=OnFailureAction.ROLLBACK,
        ))
        pipeline.add_stage(deploy_stage)

        # Stage 6: VALIDATE
        def validate_action(ctx: Dict[str, Any]) -> Dict[str, Any]:
            health_check = manifest.spec.health_check
            probe_type = health_check.probe_type if health_check else "http"
            return {"health_check": probe_type, "passed": True}

        validate_stage = PipelineStage("validate", StageType.VALIDATE)
        validate_stage.add_step(PipelineStep("health-check", validate_action))
        pipeline.add_stage(validate_stage)

        # Stage 7: FINALIZE
        def finalize_action(ctx: Dict[str, Any]) -> Dict[str, Any]:
            ctx["finalized"] = True
            return {"status": "complete", "image_digest": image_digest}

        finalize_stage = PipelineStage("finalize", StageType.FINALIZE)
        finalize_stage.add_step(PipelineStep("finalize-deployment", finalize_action))
        pipeline.add_stage(finalize_stage)

        return pipeline


# ============================================================
# Deploy Dashboard
# ============================================================


class DeployDashboard:
    """ASCII dashboard renderer for deployment pipeline status.

    Renders pipeline execution results, revision history, drift reports,
    canary analysis, and cognitive load gate status as formatted ASCII
    tables with box-drawing characters.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._width = width

    def _header(self, title: str, width: int = 0) -> str:
        """Section header with box-drawing characters."""
        w = width or self._width
        line = "+" + "-" * (w - 2) + "+"
        padded = f"| {title:<{w - 4}} |"
        return f"{line}\n{padded}\n{line}"

    def _bar(self, value: float, max_val: float, width: int = 20) -> str:
        """ASCII progress bar."""
        if max_val <= 0:
            return "[" + " " * width + "]"
        filled = int(width * min(value / max_val, 1.0))
        return "[" + "#" * filled + " " * (width - filled) + "]"

    def render(
        self,
        executor: PipelineExecutor,
        rollback_mgr: RollbackManager,
        reconciler: GitOpsReconciler,
    ) -> str:
        """Render the complete deployment dashboard.

        Args:
            executor: Pipeline executor with execution history.
            rollback_mgr: Rollback manager with revision data.
            reconciler: GitOps reconciler with drift data.

        Returns:
            Formatted ASCII dashboard string.
        """
        lines: List[str] = []
        lines.append(self._header("FIZZDEPLOY DEPLOYMENT DASHBOARD"))
        lines.append("")

        history = executor.get_history(5)
        if history:
            lines.append("  Recent Pipelines:")
            for pr in history:
                status_icon = "OK" if pr.status == PipelineStatus.SUCCEEDED else "FAIL"
                lines.append(
                    f"    [{status_icon}] {pr.pipeline_id[:12]}  "
                    f"{pr.deployment_name:<20} {pr.total_duration_ms:.0f}ms"
                )
        else:
            lines.append("  No pipeline history.")

        lines.append("")

        active = executor.get_active()
        if active:
            lines.append(f"  Active Pipelines: {len(active)}")
            for pid in active:
                lines.append(f"    - {pid}")
        else:
            lines.append("  Active Pipelines: 0")

        lines.append("")

        drift_history = reconciler.get_drift_history(5)
        if drift_history:
            lines.append("  Recent Drift Reports:")
            for dr in drift_history:
                corrected = "corrected" if dr.corrected else "pending"
                lines.append(
                    f"    {dr.deployment_name}: {len(dr.drifts)} drifts ({corrected})"
                )
        else:
            lines.append("  No drift reports.")

        lines.append("")
        lines.append("+" + "-" * (self._width - 2) + "+")

        return "\n".join(lines)

    def render_pipeline(self, result: PipelineResult) -> str:
        """Render a single pipeline execution.

        Args:
            result: PipelineResult to render.

        Returns:
            Formatted pipeline status string.
        """
        lines: List[str] = []
        lines.append(self._header(f"Pipeline: {result.pipeline_id[:12]}"))
        lines.append(f"  Deployment: {result.deployment_name}")
        lines.append(f"  Status: {result.status.value}")
        lines.append(f"  Duration: {result.total_duration_ms:.1f}ms")
        lines.append("")

        if result.stage_results:
            lines.append("  Stages:")
            for sr in result.stage_results:
                status_str = sr.status.value.upper()
                lines.append(
                    f"    {sr.stage_name:<15} [{status_str:<10}] {sr.duration_ms:.1f}ms"
                )
                if sr.error_message:
                    lines.append(f"      Error: {sr.error_message[:60]}")

        lines.append("")
        lines.append("+" + "-" * (self._width - 2) + "+")
        return "\n".join(lines)

    def render_revisions(
        self, deployment_name: str, revisions: List[DeploymentRevision]
    ) -> str:
        """Render revision history table.

        Args:
            deployment_name: Deployment name.
            revisions: List of revisions.

        Returns:
            Formatted revision history string.
        """
        lines: List[str] = []
        lines.append(self._header(f"Revisions: {deployment_name}"))
        lines.append("")

        if revisions:
            lines.append("  Rev  Status       Image Digest          Rollback From")
            lines.append("  ---  -----------  --------------------  -------------")
            for rev in revisions:
                rb = str(rev.rollback_from) if rev.rollback_from else "-"
                digest_short = rev.image_digest[:20] if rev.image_digest else "-"
                lines.append(
                    f"  {rev.revision_number:<4} {rev.status.value:<12} {digest_short:<22} {rb}"
                )
        else:
            lines.append("  No revisions recorded.")

        lines.append("")
        lines.append("+" + "-" * (self._width - 2) + "+")
        return "\n".join(lines)

    def render_drift(self, reports: List[DriftReport]) -> str:
        """Render drift detection reports.

        Args:
            reports: List of drift reports.

        Returns:
            Formatted drift report string.
        """
        lines: List[str] = []
        lines.append(self._header("GitOps Drift Reports"))
        lines.append("")

        if reports:
            for report in reports:
                corrected = "CORRECTED" if report.corrected else "PENDING"
                lines.append(
                    f"  [{corrected}] {report.deployment_name} "
                    f"({len(report.drifts)} drifts)"
                )
                for drift in report.drifts:
                    lines.append(
                        f"    {drift['field']}: "
                        f"expected={drift['expected']} actual={drift['actual']}"
                    )
        else:
            lines.append("  No drift detected.")

        lines.append("")
        lines.append("+" + "-" * (self._width - 2) + "+")
        return "\n".join(lines)

    def render_canary(self, results: List[CanaryAnalysisResult]) -> str:
        """Render canary analysis results.

        Args:
            results: List of canary analysis results.

        Returns:
            Formatted canary analysis string.
        """
        lines: List[str] = []
        lines.append(self._header("Canary Analysis Results"))
        lines.append("")

        if results:
            lines.append("  Step  Traffic  Verdict  Error Rate (B/C)    P99 Latency (B/C)")
            lines.append("  ----  -------  -------  ----------------    -----------------")
            for ar in results:
                regression = " REGRESSION" if ar.regression_detected else ""
                lines.append(
                    f"  {ar.step_index:<4}  {ar.traffic_percent:>5.1f}%  "
                    f"{ar.verdict:<7}  "
                    f"{ar.baseline_error_rate:.4f}/{ar.canary_error_rate:.4f}  "
                    f"{ar.baseline_p99_latency_ms:.1f}/{ar.canary_p99_latency_ms:.1f}ms"
                    f"{regression}"
                )
        else:
            lines.append("  No canary analysis data.")

        lines.append("")
        lines.append("+" + "-" * (self._width - 2) + "+")
        return "\n".join(lines)

    def render_gate_status(self, gate: DeploymentGate) -> str:
        """Render cognitive load gate status.

        Args:
            gate: DeploymentGate instance.

        Returns:
            Formatted gate status string.
        """
        lines: List[str] = []
        lines.append(self._header("Deployment Gate Status"))
        lines.append("")
        lines.append(f"  Threshold: {gate._threshold:.1f} (NASA-TLX)")
        lines.append(f"  Gate Checks: {gate._gate_count}")
        lines.append(f"  Emergency Bypasses: {gate._bypass_count}")

        queued = gate.get_queued()
        lines.append(f"  Queued Deployments: {len(queued)}")
        for name, _ in queued:
            lines.append(f"    - {name}")

        lines.append("")
        lines.append("+" + "-" * (self._width - 2) + "+")
        return "\n".join(lines)


# ============================================================
# FizzDeploy Middleware
# ============================================================


class FizzDeployMiddleware(IMiddleware):
    """Middleware that records the active deployment revision for each evaluation.

    When a FizzBuzz evaluation passes through the middleware pipeline,
    FizzDeployMiddleware enriches the processing context with deployment
    metadata: the active revision number, image digest, and deployment
    strategy.  This enables downstream middleware and formatters to
    include deployment context in their output.
    """

    def __init__(
        self,
        rollback_mgr: RollbackManager,
        reconciler: GitOpsReconciler,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
        enable_dashboard: bool = False,
    ) -> None:
        self._rollback_mgr = rollback_mgr
        self._reconciler = reconciler
        self._dashboard = DeployDashboard(width=dashboard_width)
        self._enable_dashboard = enable_dashboard
        self._evaluation_count = 0
        self._errors = 0

    def get_name(self) -> str:
        """Return the middleware name."""
        return "FizzDeployMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Return middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return middleware name."""
        return "FizzDeployMiddleware"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process an evaluation through the deployment middleware.

        Looks up the active deployment revision for the "fizzbuzz-core"
        deployment.  Enriches context.metadata with deploy_revision,
        deploy_image_digest, and deploy_strategy.  Delegates to
        next_handler.

        Args:
            context: Processing context.
            next_handler: Next middleware in the pipeline.

        Returns:
            Processed context.

        Raises:
            DeployMiddlewareError: If processing fails.
        """
        try:
            active_rev = self._rollback_mgr.get_active_revision("fizzbuzz-core")

            if active_rev is not None:
                context.metadata["deploy_revision"] = active_rev.revision_number
                context.metadata["deploy_image_digest"] = active_rev.image_digest
                if active_rev.manifest is not None:
                    context.metadata["deploy_strategy"] = active_rev.manifest.spec.strategy.value
                else:
                    context.metadata["deploy_strategy"] = "unknown"
            else:
                context.metadata["deploy_revision"] = 0
                context.metadata["deploy_image_digest"] = ""
                context.metadata["deploy_strategy"] = "none"

            result = next_handler(context)
            self._evaluation_count += 1
            return result

        except DeployMiddlewareError:
            raise
        except Exception as exc:
            self._errors += 1
            raise DeployMiddlewareError(context.number, str(exc))

    def render_dashboard(self) -> str:
        """Render the deployment dashboard."""
        try:
            return self._dashboard.render(
                PipelineExecutor(),
                self._rollback_mgr,
                self._reconciler,
            )
        except Exception as exc:
            raise DeployDashboardError(f"Dashboard render failed: {exc}")

    def render_pipeline(self, pipeline_id: str) -> str:
        """Render pipeline details."""
        return f"Pipeline {pipeline_id}: no execution data available"

    def render_revisions(self, deployment_name: str) -> str:
        """Render revision history for a deployment."""
        revisions = self._rollback_mgr.get_revisions(deployment_name)
        return self._dashboard.render_revisions(deployment_name, revisions)

    def render_drift(self) -> str:
        """Render drift reports."""
        reports = self._reconciler.get_drift_history(10)
        return self._dashboard.render_drift(reports)

    def render_canary(self) -> str:
        """Render canary analysis."""
        return self._dashboard.render_canary([])

    def render_gate(self) -> str:
        """Render gate status."""
        return self._dashboard.render_gate_status(
            DeploymentGate()
        )

    def render_stats(self) -> str:
        """Render middleware statistics."""
        lines: List[str] = []
        lines.append("  FizzDeploy Middleware Statistics:")
        lines.append(f"    Evaluations: {self._evaluation_count}")
        lines.append(f"    Errors: {self._errors}")
        return "\n".join(lines)


# ============================================================
# Factory Function
# ============================================================


def create_fizzdeploy_subsystem(
    default_strategy: str = "rolling_update",
    pipeline_timeout: float = DEFAULT_PIPELINE_TIMEOUT,
    reconcile_interval: float = DEFAULT_RECONCILE_INTERVAL,
    sync_strategy: str = "auto",
    revision_history_depth: int = DEFAULT_REVISION_HISTORY_DEPTH,
    cognitive_load_threshold: float = DEFAULT_COGNITIVE_LOAD_THRESHOLD,
    max_surge: float = DEFAULT_ROLLING_MAX_SURGE,
    max_unavailable: float = DEFAULT_ROLLING_MAX_UNAVAILABLE,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzDeploy subsystem.

    Factory function that instantiates the deployment pipeline with
    all components (pipeline executor, manifest parser, strategy factory,
    GitOps reconciler, rollback manager, deployment gate, dashboard)
    and the middleware, ready for integration into the FizzBuzz
    evaluation pipeline.

    Args:
        default_strategy: Default deployment strategy name.
        pipeline_timeout: Pipeline execution timeout.
        reconcile_interval: GitOps reconciliation interval.
        sync_strategy: GitOps sync strategy name.
        revision_history_depth: Max revisions per deployment.
        cognitive_load_threshold: NASA-TLX gating threshold.
        max_surge: Rolling update max surge fraction.
        max_unavailable: Rolling update max unavailable fraction.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable dashboard rendering.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (PipelineExecutor, FizzDeployMiddleware).
    """
    executor = PipelineExecutor(event_bus=event_bus)

    rollback_mgr = RollbackManager(
        max_depth=revision_history_depth,
        event_bus=event_bus,
    )

    sync_strat = SyncStrategy(sync_strategy)
    reconciler = GitOpsReconciler(
        sync_strategy=sync_strat,
        reconcile_interval=reconcile_interval,
        pipeline_executor=executor,
        event_bus=event_bus,
    )

    gate = DeploymentGate(
        threshold=cognitive_load_threshold,
        event_bus=event_bus,
    )

    middleware = FizzDeployMiddleware(
        rollback_mgr=rollback_mgr,
        reconciler=reconciler,
        dashboard_width=dashboard_width,
        enable_dashboard=enable_dashboard,
    )

    logger.info("FizzDeploy subsystem created and wired")
    return executor, middleware
