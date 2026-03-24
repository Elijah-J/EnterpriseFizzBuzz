# Implementation Plan: FizzDeploy -- Container-Native Deployment Pipeline

**Date:** 2026-03-24
**Module:** `enterprise_fizzbuzz/infrastructure/fizzdeploy.py`
**Target:** ~3,000 lines + ~400 tests
**Middleware Priority:** 114
**Error Code Prefix:** EFP-DPL
**Reference Architecture:** Argo CD, Spinnaker, Flux CD

---

## 1. Module Docstring

```python
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
```

---

## 2. Imports

```python
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

from enterprise_fizzbuzz.domain.exceptions import (
    DeployError,
    DeployPipelineError,
    DeployStageError,
    DeployStepError,
    DeployStrategyError,
    RollingUpdateError,
    BlueGreenError,
    CanaryError,
    RecreateError,
    DeployManifestError,
    ManifestParseError,
    ManifestValidationError,
    GitOpsReconcileError,
    GitOpsDriftError,
    GitOpsSyncError,
    RollbackError,
    RollbackRevisionNotFoundError,
    RollbackStrategyError,
    DeployGateError,
    CognitiveLoadGateError,
    DeployDashboardError,
    DeployMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)
```

---

## 3. Constants (~12)

| Constant | Value | Description |
|----------|-------|-------------|
| `FIZZDEPLOY_VERSION` | `"1.0.0"` | FizzDeploy subsystem version |
| `DEFAULT_PIPELINE_TIMEOUT` | `600.0` | Pipeline execution timeout in seconds (10 minutes) |
| `DEFAULT_STAGE_TIMEOUT` | `120.0` | Per-stage execution timeout in seconds |
| `DEFAULT_STEP_TIMEOUT` | `60.0` | Per-step execution timeout in seconds |
| `DEFAULT_MAX_RETRIES` | `3` | Default retry count for failed steps |
| `DEFAULT_RETRY_BACKOFF` | `2.0` | Exponential backoff multiplier for retries |
| `DEFAULT_ROLLING_MAX_SURGE` | `0.25` | Max pods above desired during rolling update (25%) |
| `DEFAULT_ROLLING_MAX_UNAVAILABLE` | `0.25` | Max unavailable pods during rolling update (25%) |
| `DEFAULT_CANARY_ANALYSIS_INTERVAL` | `30.0` | Seconds between canary metric samples |
| `DEFAULT_RECONCILE_INTERVAL` | `30.0` | GitOps reconciliation loop interval in seconds |
| `DEFAULT_REVISION_HISTORY_DEPTH` | `10` | Max deployment revisions retained |
| `DEFAULT_COGNITIVE_LOAD_THRESHOLD` | `70.0` | NASA-TLX score above which deployments are gated |
| `DEFAULT_DASHBOARD_WIDTH` | `72` | ASCII dashboard rendering width |
| `MIDDLEWARE_PRIORITY` | `114` | Middleware pipeline priority for FizzDeploy |

---

## 4. Enums (~7)

### 4.1 `PipelineStatus(Enum)`

Pipeline lifecycle states.

| Member | Value | Description |
|--------|-------|-------------|
| `PENDING` | `"pending"` | Pipeline created but not yet started |
| `RUNNING` | `"running"` | Pipeline is executing stages |
| `SUCCEEDED` | `"succeeded"` | All stages completed successfully |
| `FAILED` | `"failed"` | A stage or step failed and the pipeline was aborted |
| `ROLLED_BACK` | `"rolled_back"` | Pipeline failed and rollback was executed |
| `CANCELLED` | `"cancelled"` | Pipeline was explicitly cancelled |

### 4.2 `StageType(Enum)`

Standard pipeline stage types.

| Member | Value | Description |
|--------|-------|-------------|
| `BUILD` | `"build"` | Build container image via FizzImage |
| `SCAN` | `"scan"` | Vulnerability scan via FizzRegistry scanner |
| `SIGN` | `"sign"` | Image signing for provenance |
| `PUSH` | `"push"` | Push image to FizzRegistry |
| `DEPLOY` | `"deploy"` | Apply deployment strategy to cluster |
| `VALIDATE` | `"validate"` | Run health checks and smoke tests |
| `FINALIZE` | `"finalize"` | Mark deployment complete or trigger rollback |

### 4.3 `StageStatus(Enum)`

Individual stage execution states.

| Member | Value | Description |
|--------|-------|-------------|
| `PENDING` | `"pending"` | Stage not yet started |
| `RUNNING` | `"running"` | Stage is executing |
| `SUCCEEDED` | `"succeeded"` | Stage completed successfully |
| `FAILED` | `"failed"` | Stage failed |
| `SKIPPED` | `"skipped"` | Stage was skipped (on_failure=skip) |

### 4.4 `DeploymentStrategy(Enum)`

Deployment strategy types.

| Member | Value | Description |
|--------|-------|-------------|
| `ROLLING_UPDATE` | `"rolling_update"` | Incremental pod replacement |
| `BLUE_GREEN` | `"blue_green"` | Parallel environment traffic switch |
| `CANARY` | `"canary"` | Gradual traffic shifting with analysis |
| `RECREATE` | `"recreate"` | Terminate all, then start all |

### 4.5 `SyncStrategy(Enum)`

GitOps drift correction strategies.

| Member | Value | Description |
|--------|-------|-------------|
| `AUTO` | `"auto"` | Automatically apply corrections on drift |
| `MANUAL` | `"manual"` | Detect and report drift, require explicit approval |
| `DRY_RUN` | `"dry_run"` | Detect drift, show what would change, do not apply |

### 4.6 `RevisionStatus(Enum)`

Deployment revision lifecycle.

| Member | Value | Description |
|--------|-------|-------------|
| `ACTIVE` | `"active"` | Currently serving traffic |
| `SUPERSEDED` | `"superseded"` | Replaced by a newer revision |
| `ROLLED_BACK` | `"rolled_back"` | Reverted to by a rollback operation |
| `FAILED` | `"failed"` | Deployment of this revision failed |

### 4.7 `OnFailureAction(Enum)`

Step failure behavior.

| Member | Value | Description |
|--------|-------|-------------|
| `ABORT` | `"abort"` | Abort the entire pipeline |
| `SKIP` | `"skip"` | Skip this step and continue |
| `ROLLBACK` | `"rollback"` | Trigger immediate rollback |

---

## 5. Data Classes (~10)

### 5.1 `RetryPolicy`

```python
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
```

### 5.2 `StageResult`

```python
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
```

### 5.3 `PipelineResult`

```python
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
```

### 5.4 `DeploymentSpec`

```python
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
```

### 5.5 `HealthCheckConfig`

```python
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
```

### 5.6 `DeploymentManifest`

```python
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
```

### 5.7 `DeploymentRevision`

```python
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
```

### 5.8 `RollbackRecord`

```python
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
```

### 5.9 `DriftReport`

```python
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
```

### 5.10 `CanaryAnalysisResult`

```python
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
```

---

## 6. Class Inventory (16 classes)

### 6.1 `PipelineStep` (~60 lines)

A single executable step within a pipeline stage.

**Attributes:**
- `name: str` -- Step identifier
- `action: Callable[..., Dict[str, Any]]` -- Step action callable
- `timeout: float` -- Step execution timeout (default: `DEFAULT_STEP_TIMEOUT`)
- `retry_policy: RetryPolicy` -- Retry configuration
- `on_failure: OnFailureAction` -- Failure behavior (default: `ABORT`)
- `metadata: Dict[str, Any]` -- Step-specific metadata

**Methods:**
- `execute(context: Dict[str, Any]) -> Dict[str, Any]` -- Execute the step action with retry logic. On each failure, compute delay via `initial_delay * backoff_multiplier^attempt`, capped at `max_delay`. Return the action's output dict. Raise `DeployStepError` if all retries exhausted.

### 6.2 `PipelineStage` (~80 lines)

An ordered collection of steps that form a logical pipeline stage (e.g., BUILD, DEPLOY).

**Attributes:**
- `name: str` -- Stage name
- `stage_type: StageType` -- Stage type enum
- `steps: List[PipelineStep]` -- Steps in this stage
- `parallel: bool` -- Whether steps execute in parallel (default: `False`)
- `timeout: float` -- Stage-level timeout

**Methods:**
- `add_step(step: PipelineStep) -> None` -- Append a step.
- `execute(context: Dict[str, Any]) -> StageResult` -- Execute all steps (sequentially or in parallel via threading). Return `StageResult` with aggregated timing and status. Emit `DEPLOY_STAGE_STARTED` and `DEPLOY_STAGE_COMPLETED` events.

### 6.3 `Pipeline` (~120 lines)

An ordered sequence of stages forming the complete deployment pipeline.

**Attributes:**
- `pipeline_id: str` -- Unique pipeline identifier (UUID hex prefix)
- `deployment_name: str` -- Name of the target deployment
- `stages: List[PipelineStage]` -- Ordered pipeline stages
- `status: PipelineStatus` -- Current pipeline status
- `timeout: float` -- Pipeline-level timeout
- `created_at: datetime` -- Pipeline creation timestamp
- `_result: Optional[PipelineResult]` -- Pipeline execution result

**Methods:**
- `add_stage(stage: PipelineStage) -> None` -- Append a stage.
- `get_result() -> Optional[PipelineResult]` -- Return the execution result.

### 6.4 `PipelineExecutor` (~250 lines)

Executes a pipeline to completion, managing stage sequencing, timeout enforcement, and event emission.

**Attributes:**
- `_event_bus: Optional[Any]` -- Event bus for lifecycle events
- `_lock: threading.Lock` -- Thread safety lock
- `_active_pipelines: Dict[str, Pipeline]` -- Currently executing pipelines
- `_completed_pipelines: List[PipelineResult]` -- Historical results (bounded ring buffer, last 100)
- `_total_executions: int` -- Total pipeline executions
- `_total_failures: int` -- Total failed pipelines

**Methods:**
- `execute(pipeline: Pipeline) -> PipelineResult` -- Execute all stages in order. For each stage, call `stage.execute()`. If a stage fails and the step's `on_failure` is `ABORT`, set pipeline to `FAILED` and stop. If `ROLLBACK`, set pipeline to `ROLLED_BACK` and stop. If `SKIP`, mark stage as `SKIPPED` and continue. Record timing metrics. Emit `DEPLOY_PIPELINE_STARTED`, `DEPLOY_PIPELINE_COMPLETED`, `DEPLOY_PIPELINE_FAILED` events.
- `cancel(pipeline_id: str) -> bool` -- Cancel a running pipeline.
- `get_active() -> List[str]` -- Return IDs of active pipelines.
- `get_history(limit: int = 10) -> List[PipelineResult]` -- Return recent pipeline results.

### 6.5 `RollingUpdateStrategy` (~180 lines)

Implements the rolling update deployment strategy: incremental pod replacement with configurable surge and unavailability.

**Attributes:**
- `_max_surge: float` -- Max pods above desired count (0.0-1.0 as fraction, or int for absolute)
- `_max_unavailable: float` -- Max pods unavailable (0.0-1.0 or int)
- `_min_ready_seconds: float` -- Min seconds a pod must be ready
- `_health_check_timeout: float` -- Health check timeout per pod
- `_event_bus: Optional[Any]` -- Event bus

**Methods:**
- `execute(manifest: DeploymentManifest, current_pods: List[Dict], new_image: str) -> Dict[str, Any]` -- Compute batch size from `max_surge` and `max_unavailable`. For each batch: create new pods with `new_image`, wait for readiness probes, terminate old pods. If a pod fails readiness within `health_check_timeout`, pause rollout and emit `DEPLOY_ROLLING_UPDATE_PAUSED`. Return rollout metrics dict.
- `_compute_batch_size(desired: int) -> Tuple[int, int]` -- Calculate `surge_count` and `unavailable_count` from fractional/absolute parameters.
- `_simulate_readiness_check(pod_id: str) -> bool` -- Simulate readiness probe execution.

### 6.6 `BlueGreenStrategy` (~160 lines)

Implements the blue-green deployment strategy: parallel environments with instant traffic switch.

**Attributes:**
- `_active_environment: str` -- Currently active environment ("blue" or "green")
- `_environments: Dict[str, List[Dict]]` -- Pod sets per environment
- `_validation_timeout: float` -- Validation timeout for inactive environment
- `_event_bus: Optional[Any]` -- Event bus

**Methods:**
- `execute(manifest: DeploymentManifest, current_pods: List[Dict], new_image: str) -> Dict[str, Any]` -- Determine inactive environment. Provision new pods in inactive environment. Run validation against inactive environment. If validation passes, switch traffic by updating service endpoint. If validation fails, abort and leave traffic on active environment. Emit `DEPLOY_BLUE_GREEN_SWITCHED` or `DEPLOY_BLUE_GREEN_ABORTED`.
- `switch_traffic() -> str` -- Toggle active environment and return new active name.
- `rollback() -> str` -- Switch traffic back to previous environment.
- `get_active_environment() -> str` -- Return name of active environment.

### 6.7 `CanaryStrategy` (~200 lines)

Implements the canary deployment strategy: gradual traffic shifting with automated analysis.

**Attributes:**
- `_steps: List[Tuple[float, float]]` -- List of `(traffic_percent, pause_duration_seconds)` tuples
- `_analysis_interval: float` -- Seconds between metric samples
- `_error_rate_threshold: float` -- Error rate regression threshold (default: 0.05)
- `_latency_threshold: float` -- P99 latency regression threshold in ms (default: 50.0)
- `_event_bus: Optional[Any]` -- Event bus
- `_analysis_results: List[CanaryAnalysisResult]` -- Analysis history

**Methods:**
- `execute(manifest: DeploymentManifest, current_pods: List[Dict], new_image: str) -> Dict[str, Any]` -- For each step: shift `traffic_percent` of traffic to canary pods. Wait `pause_duration` while collecting metrics at `analysis_interval`. Run `analyze_step()`. If regression detected, rollback canary to 0% and raise `CanaryError`. If all steps pass, shift 100% to canary. Return analysis summary dict.
- `analyze_step(step_index: int, traffic_percent: float) -> CanaryAnalysisResult` -- Compare canary error rate and P99 latency against baseline. Return analysis result with verdict.
- `get_analysis_results() -> List[CanaryAnalysisResult]` -- Return analysis history.

**Default canary steps:**
```python
DEFAULT_CANARY_STEPS = [
    (5.0, 300.0),    # 5% for 5 minutes
    (25.0, 600.0),   # 25% for 10 minutes
    (75.0, 600.0),   # 75% for 10 minutes
    (100.0, 0.0),    # 100% -- final promotion
]
```

### 6.8 `RecreateStrategy` (~100 lines)

Implements the recreate deployment strategy: terminate all existing pods, then create all new pods.

**Attributes:**
- `_shutdown_timeout: float` -- Timeout for graceful shutdown of old pods
- `_startup_timeout: float` -- Timeout for new pods to become ready
- `_event_bus: Optional[Any]` -- Event bus

**Methods:**
- `execute(manifest: DeploymentManifest, current_pods: List[Dict], new_image: str) -> Dict[str, Any]` -- Send graceful shutdown to all current pods. Wait `shutdown_timeout` for all to terminate. Create new pods with `new_image` at `manifest.spec.replicas` count. Wait `startup_timeout` for all to become ready. Record downtime duration. Emit `DEPLOY_RECREATE_STARTED`, `DEPLOY_RECREATE_COMPLETED`.

### 6.9 `ManifestParser` (~200 lines)

Validates and parses deployment manifests from YAML strings or dicts.

**Attributes:**
- `_schema: Dict[str, Any]` -- JSON schema for manifest validation
- `_known_strategies: Set[str]` -- Valid strategy names
- `_required_fields: List[str]` -- Required top-level fields

**Methods:**
- `parse(yaml_content: str) -> DeploymentManifest` -- Parse YAML string into `DeploymentManifest`. Validate required fields (`apiVersion`, `kind`, `metadata.name`, `spec.image`). Validate strategy configuration. Validate resource constraint format. Raise `ManifestParseError` for syntax errors, `ManifestValidationError` for schema violations. Return populated `DeploymentManifest`.
- `parse_dict(data: Dict[str, Any]) -> DeploymentManifest` -- Parse from pre-parsed dict.
- `validate(manifest: DeploymentManifest) -> List[str]` -- Return list of validation errors (empty list = valid).
- `_validate_strategy_params(strategy: DeploymentStrategy, params: Dict) -> List[str]` -- Validate strategy-specific parameters.
- `_validate_resources(resources: Dict) -> List[str]` -- Validate CPU/memory format.
- `_parse_health_check(data: Dict) -> HealthCheckConfig` -- Parse health check config.

### 6.10 `GitOpsReconciler` (~250 lines)

Continuous control loop comparing declared deployment manifests against actual cluster state.

**Attributes:**
- `_manifests: Dict[str, DeploymentManifest]` -- Declared manifests by deployment name
- `_actual_state: Dict[str, Dict[str, Any]]` -- Actual cluster state per deployment
- `_sync_strategy: SyncStrategy` -- Default sync strategy
- `_reconcile_interval: float` -- Loop interval in seconds
- `_pipeline_executor: PipelineExecutor` -- Pipeline executor for corrections
- `_drift_reports: List[DriftReport]` -- Drift detection history (bounded)
- `_lock: threading.Lock` -- Thread safety
- `_running: bool` -- Whether the reconcile loop is active
- `_total_reconciliations: int` -- Total reconciliation passes
- `_total_drifts_detected: int` -- Total drifts found
- `_total_corrections: int` -- Total auto-corrections applied
- `_event_bus: Optional[Any]` -- Event bus

**Methods:**
- `register_manifest(name: str, manifest: DeploymentManifest) -> None` -- Register a declared manifest.
- `update_actual_state(name: str, state: Dict[str, Any]) -> None` -- Update actual cluster state.
- `reconcile() -> List[DriftReport]` -- Single reconciliation pass. For each registered manifest, compare declared vs actual fields (`image`, `replicas`, `resources`, `env`). If drift detected, generate `DriftReport`. If sync strategy is `AUTO`, trigger correction pipeline. If `MANUAL`, emit drift event and return report. If `DRY_RUN`, log what would change. Return list of drift reports.
- `start_loop() -> None` -- Start background reconciliation loop (runs `reconcile()` every `reconcile_interval` seconds).
- `stop_loop() -> None` -- Stop background reconciliation loop.
- `get_drift_history(limit: int = 10) -> List[DriftReport]` -- Return recent drift reports.
- `_detect_drift(name: str, manifest: DeploymentManifest, actual: Dict) -> List[Dict[str, Any]]` -- Compare individual fields and return list of drift items.

### 6.11 `RollbackManager` (~180 lines)

Maintains deployment revision history and executes rollback operations.

**Attributes:**
- `_revisions: Dict[str, List[DeploymentRevision]]` -- Revision history per deployment (bounded by `_max_depth`)
- `_max_depth: int` -- Maximum revisions retained per deployment
- `_rollback_records: List[RollbackRecord]` -- Rollback operation log
- `_lock: threading.Lock` -- Thread safety
- `_event_bus: Optional[Any]` -- Event bus

**Methods:**
- `record_revision(deployment_name: str, manifest: DeploymentManifest, image_digest: str, pipeline_id: str) -> DeploymentRevision` -- Create and store a new revision. Mark previous active revision as `SUPERSEDED`. Trim history to `max_depth`. Return the new revision.
- `rollback(deployment_name: str, target_revision: int) -> RollbackRecord` -- Validate that target revision exists. Retrieve the target revision's manifest. Create a new revision with `rollback_from` set. Execute rollback deployment using the original strategy. Return `RollbackRecord`. Raise `RollbackRevisionNotFoundError` if target not found.
- `get_revisions(deployment_name: str) -> List[DeploymentRevision]` -- Return revision history.
- `get_active_revision(deployment_name: str) -> Optional[DeploymentRevision]` -- Return the currently active revision.
- `get_rollback_history(limit: int = 10) -> List[RollbackRecord]` -- Return recent rollback records.

### 6.12 `DeploymentGate` (~120 lines)

Queries FizzBob's cognitive load model to gate deployments on operator readiness.

**Attributes:**
- `_threshold: float` -- NASA-TLX score threshold (default: 70.0)
- `_queued_deployments: List[Tuple[str, DeploymentManifest]]` -- Deployments waiting for cognitive load to decrease
- `_bypass_count: int` -- Emergency bypasses
- `_gate_count: int` -- Total gating decisions
- `_lock: threading.Lock` -- Thread safety
- `_event_bus: Optional[Any]` -- Event bus

**Methods:**
- `check(deployment_name: str, manifest: DeploymentManifest, emergency: bool = False) -> bool` -- If `emergency` is True, bypass gate, increment `_bypass_count`, emit `DEPLOY_GATE_EMERGENCY_BYPASS`, return True. Otherwise, query FizzBob for current NASA-TLX score. If score > `_threshold`, queue deployment, emit `DEPLOY_GATE_BLOCKED`, raise `CognitiveLoadGateError`. If score <= threshold, emit `DEPLOY_GATE_PASSED`, return True.
- `get_queued() -> List[Tuple[str, DeploymentManifest]]` -- Return queued deployments.
- `release_queue() -> int` -- Re-check gating for all queued deployments, release eligible ones. Return count of released deployments.
- `_simulate_cognitive_load() -> float` -- Simulate querying FizzBob's NASA-TLX model. Return a score 0-100.

### 6.13 `DeployDashboard` (~200 lines)

ASCII dashboard renderer for deployment pipeline status, revision history, drift reports, and canary analysis.

**Methods:**
- `render(executor: PipelineExecutor, rollback_mgr: RollbackManager, reconciler: GitOpsReconciler) -> str` -- Render the complete deployment dashboard including pipeline status, active deployments, and reconciler state.
- `render_pipeline(result: PipelineResult) -> str` -- Render a single pipeline execution with stage-by-stage status, duration, and retry counts.
- `render_revisions(deployment_name: str, revisions: List[DeploymentRevision]) -> str` -- Render revision history table.
- `render_drift(reports: List[DriftReport]) -> str` -- Render drift detection reports.
- `render_canary(results: List[CanaryAnalysisResult]) -> str` -- Render canary analysis results with traffic steps and regression indicators.
- `render_gate_status(gate: DeploymentGate) -> str` -- Render cognitive load gate status.
- `_bar(value: float, max_val: float, width: int = 20) -> str` -- ASCII progress bar helper.
- `_header(title: str, width: int) -> str` -- Section header with box-drawing characters.

### 6.14 `FizzDeployMiddleware(IMiddleware)` (~120 lines)

Middleware that records the active deployment revision for each FizzBuzz evaluation request.

**Attributes:**
- `_rollback_mgr: RollbackManager` -- Rollback manager for revision lookup
- `_reconciler: GitOpsReconciler` -- GitOps reconciler
- `_dashboard: DeployDashboard` -- Dashboard renderer
- `_enable_dashboard: bool` -- Whether dashboard rendering is enabled
- `_evaluation_count: int` -- Total evaluations processed
- `_errors: int` -- Total middleware errors

**Methods (IMiddleware):**
- `get_name() -> str` -- Return `"FizzDeployMiddleware"`.
- `get_priority() -> int` -- Return `MIDDLEWARE_PRIORITY` (114).
- `process(context: ProcessingContext, next_handler: Callable) -> ProcessingContext` -- Look up the active deployment revision for the "fizzbuzz-core" deployment. Enrich `context.metadata` with `deploy_revision`, `deploy_image_digest`, `deploy_strategy`. Delegate to `next_handler`. Increment `_evaluation_count`. On failure, increment `_errors` and raise `DeployMiddlewareError`.

**Properties:**
- `priority -> int` -- Return 114.
- `name -> str` -- Return `"FizzDeployMiddleware"`.

**Render methods** (delegate to `DeployDashboard`):
- `render_dashboard() -> str`
- `render_pipeline(pipeline_id: str) -> str`
- `render_revisions(deployment_name: str) -> str`
- `render_drift() -> str`
- `render_canary() -> str`
- `render_gate() -> str`
- `render_stats() -> str`

### 6.15 `_StrategyFactory` (~50 lines)

Internal factory for creating deployment strategy instances.

**Methods (static):**
- `create(strategy: DeploymentStrategy, params: Dict[str, Any], event_bus: Optional[Any] = None) -> Union[RollingUpdateStrategy, BlueGreenStrategy, CanaryStrategy, RecreateStrategy]` -- Instantiate the appropriate strategy class based on the enum, passing strategy-specific parameters. Raise `DeployStrategyError` for unknown strategies.

### 6.16 `_PipelineBuilder` (~100 lines)

Internal builder that constructs a standard deployment pipeline with the seven canonical stages.

**Methods:**
- `build_standard(deployment_name: str, manifest: DeploymentManifest, strategy_instance, image_digest: str = "") -> Pipeline` -- Construct a `Pipeline` with seven stages (`BUILD`, `SCAN`, `SIGN`, `PUSH`, `DEPLOY`, `VALIDATE`, `FINALIZE`), each containing appropriate steps. The `DEPLOY` stage step delegates to the strategy instance's `execute()` method. The `VALIDATE` stage runs health check probes. The `FINALIZE` stage records the revision and marks the deployment complete.

---

## 7. Exception Classes (~20, EFP-DPL01 through EFP-DPL20)

Base exception: `DeployError(FizzBuzzError)` with `error_code="EFP-DPL00"`.

All exceptions follow the established pattern:
```python
class ExceptionName(DeployError):
    """Docstring explaining the failure mode."""
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-DPLxx"
        self.context = {"reason": reason}
```

| # | Class | Code | Trigger |
|---|-------|------|---------|
| 00 | `DeployError` | EFP-DPL00 | Base exception for all FizzDeploy errors |
| 01 | `DeployPipelineError` | EFP-DPL01 | Pipeline execution failure (timeout, stage sequencing) |
| 02 | `DeployStageError` | EFP-DPL02 | Stage execution failure (step failure, stage timeout) |
| 03 | `DeployStepError` | EFP-DPL03 | Step execution failure after all retries exhausted |
| 04 | `DeployStrategyError` | EFP-DPL04 | Unknown or unsupported deployment strategy |
| 05 | `RollingUpdateError` | EFP-DPL05 | Rolling update failure (pod readiness timeout, batch failure) |
| 06 | `BlueGreenError` | EFP-DPL06 | Blue-green failure (validation failure on inactive environment) |
| 07 | `CanaryError` | EFP-DPL07 | Canary failure (regression detected during analysis) |
| 08 | `RecreateError` | EFP-DPL08 | Recreate strategy failure (shutdown timeout, startup failure) |
| 09 | `DeployManifestError` | EFP-DPL09 | General deployment manifest error |
| 10 | `ManifestParseError` | EFP-DPL10 | YAML syntax error during manifest parsing |
| 11 | `ManifestValidationError` | EFP-DPL11 | Manifest schema validation failure (missing required fields, invalid strategy params) |
| 12 | `GitOpsReconcileError` | EFP-DPL12 | Reconciliation loop failure (state comparison error) |
| 13 | `GitOpsDriftError` | EFP-DPL13 | Drift detection found divergence between declared and actual state |
| 14 | `GitOpsSyncError` | EFP-DPL14 | Drift correction failed during sync |
| 15 | `RollbackError` | EFP-DPL15 | General rollback failure |
| 16 | `RollbackRevisionNotFoundError` | EFP-DPL16 | Target revision does not exist in revision history |
| 17 | `RollbackStrategyError` | EFP-DPL17 | Strategy-aware rollback failed (traffic switch failure, pod restoration failure) |
| 18 | `DeployGateError` | EFP-DPL18 | General deployment gate error |
| 19 | `CognitiveLoadGateError` | EFP-DPL19 | Deployment blocked by FizzBob cognitive load threshold |
| 20 | `DeployDashboardError` | EFP-DPL20 | Dashboard rendering failure |
| 21 | `DeployMiddlewareError` | EFP-DPL21 | Middleware failed to process evaluation through deploy subsystem |

### Exception Docstring Style

Each exception gets a deadpan, technically earnest docstring. Example:

```python
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
```

---

## 8. EventType Entries (~15)

Add to `enterprise_fizzbuzz/domain/models.py` in the `EventType` enum:

```python
    # FizzDeploy — Container-Native Deployment Pipeline events
    DEPLOY_PIPELINE_STARTED = auto()
    DEPLOY_PIPELINE_COMPLETED = auto()
    DEPLOY_PIPELINE_FAILED = auto()
    DEPLOY_STAGE_STARTED = auto()
    DEPLOY_STAGE_COMPLETED = auto()
    DEPLOY_STAGE_FAILED = auto()
    DEPLOY_ROLLING_UPDATE_BATCH = auto()
    DEPLOY_ROLLING_UPDATE_PAUSED = auto()
    DEPLOY_BLUE_GREEN_SWITCHED = auto()
    DEPLOY_BLUE_GREEN_ABORTED = auto()
    DEPLOY_CANARY_STEP_ADVANCED = auto()
    DEPLOY_CANARY_REGRESSION = auto()
    DEPLOY_RECREATE_COMPLETED = auto()
    DEPLOY_GITOPS_DRIFT_DETECTED = auto()
    DEPLOY_GITOPS_SYNC_APPLIED = auto()
    DEPLOY_ROLLBACK_EXECUTED = auto()
    DEPLOY_GATE_BLOCKED = auto()
    DEPLOY_GATE_PASSED = auto()
    DEPLOY_GATE_EMERGENCY_BYPASS = auto()
    DEPLOY_DASHBOARD_RENDERED = auto()
```

---

## 9. Config Properties (~10)

Add to `enterprise_fizzbuzz/infrastructure/config.py` (`ConfigurationManager` class):

```python
    @property
    def fizzdeploy_enabled(self) -> bool:
        """Whether the FizzDeploy deployment pipeline is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdeploy", {}).get("enabled", False)

    @property
    def fizzdeploy_default_strategy(self) -> str:
        """Default deployment strategy."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdeploy", {}).get("default_strategy", "rolling_update")

    @property
    def fizzdeploy_pipeline_timeout(self) -> float:
        """Pipeline execution timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzdeploy", {}).get("pipeline_timeout", 600.0))

    @property
    def fizzdeploy_reconcile_interval(self) -> float:
        """GitOps reconciliation loop interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzdeploy", {}).get("reconcile_interval", 30.0))

    @property
    def fizzdeploy_sync_strategy(self) -> str:
        """Default GitOps sync strategy."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdeploy", {}).get("sync_strategy", "auto")

    @property
    def fizzdeploy_revision_history_depth(self) -> int:
        """Maximum deployment revisions retained per deployment."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzdeploy", {}).get("revision_history_depth", 10))

    @property
    def fizzdeploy_cognitive_load_threshold(self) -> float:
        """NASA-TLX cognitive load threshold for deployment gating."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzdeploy", {}).get("cognitive_load_threshold", 70.0))

    @property
    def fizzdeploy_max_surge(self) -> float:
        """Default max surge for rolling update strategy (fraction 0.0-1.0)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzdeploy", {}).get("rolling_update", {}).get("max_surge", 0.25))

    @property
    def fizzdeploy_max_unavailable(self) -> float:
        """Default max unavailable for rolling update strategy (fraction 0.0-1.0)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzdeploy", {}).get("rolling_update", {}).get("max_unavailable", 0.25))

    @property
    def fizzdeploy_dashboard_width(self) -> int:
        """Width of the FizzDeploy ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzdeploy", {}).get("dashboard", {}).get("width", 72))
```

---

## 10. YAML Config Section

Add to `config.yaml`:

```yaml
fizzdeploy:
  enabled: false                              # Master switch — opt-in via --fizzdeploy
  default_strategy: rolling_update            # Default deployment strategy
  pipeline_timeout: 600.0                     # Pipeline execution timeout (seconds)
  reconcile_interval: 30.0                    # GitOps reconciliation loop interval (seconds)
  sync_strategy: auto                         # GitOps sync strategy: auto, manual, dry_run
  revision_history_depth: 10                  # Max deployment revisions retained
  cognitive_load_threshold: 70.0              # NASA-TLX threshold for deployment gating
  rolling_update:
    max_surge: 0.25                           # Max pods above desired during update
    max_unavailable: 0.25                     # Max pods unavailable during update
  canary:
    analysis_interval: 30.0                   # Seconds between canary metric samples
    error_rate_threshold: 0.05                # Canary error rate regression threshold
    latency_threshold: 50.0                   # Canary P99 latency regression threshold (ms)
  dashboard:
    width: 72                                 # ASCII dashboard width
```

---

## 11. CLI Flags (9 flags)

Add to `__main__.py` argparse section:

```python
    parser.add_argument(
        "--fizzdeploy",
        action="store_true",
        help="Enable FizzDeploy: container-native deployment pipeline with four strategies, GitOps reconciliation, and cognitive load gating",
    )
    parser.add_argument(
        "--fizzdeploy-apply",
        type=str,
        default=None,
        metavar="MANIFEST",
        help="Apply a deployment manifest (YAML file path or inline YAML)",
    )
    parser.add_argument(
        "--fizzdeploy-status",
        type=str,
        default=None,
        metavar="DEPLOYMENT",
        help="Display deployment status and revision history",
    )
    parser.add_argument(
        "--fizzdeploy-rollback",
        nargs=2,
        default=None,
        metavar=("DEPLOYMENT", "REVISION"),
        help="Rollback a deployment to a specific revision number",
    )
    parser.add_argument(
        "--fizzdeploy-pipeline",
        type=str,
        default=None,
        metavar="DEPLOYMENT",
        help="Display pipeline execution details for a deployment",
    )
    parser.add_argument(
        "--fizzdeploy-strategy",
        type=str,
        default=None,
        choices=["rolling", "bluegreen", "canary", "recreate"],
        help="Override the default deployment strategy",
    )
    parser.add_argument(
        "--fizzdeploy-gitops-sync",
        action="store_true",
        help="Trigger a manual GitOps reconciliation pass",
    )
    parser.add_argument(
        "--fizzdeploy-emergency",
        action="store_true",
        help="Bypass cognitive load gating for emergency deployments",
    )
    parser.add_argument(
        "--fizzdeploy-dry-run",
        action="store_true",
        help="Show what a deployment would change without applying",
    )
```

---

## 12. `__main__.py` Wiring

### Import block

```python
from enterprise_fizzbuzz.infrastructure.fizzdeploy import (
    PipelineExecutor,
    GitOpsReconciler,
    RollbackManager,
    DeploymentGate,
    ManifestParser,
    DeployDashboard,
    FizzDeployMiddleware,
    create_fizzdeploy_subsystem,
)
```

### Initialization block (in subsystem wiring section, after containerd)

```python
    deploy_middleware_instance = None
    deploy_executor_instance = None

    if args.fizzdeploy or args.fizzdeploy_apply or args.fizzdeploy_status or args.fizzdeploy_rollback or args.fizzdeploy_pipeline or args.fizzdeploy_gitops_sync or args.fizzdeploy_dry_run:
        deploy_executor_instance, deploy_middleware_instance = create_fizzdeploy_subsystem(
            default_strategy=config.fizzdeploy_default_strategy,
            pipeline_timeout=config.fizzdeploy_pipeline_timeout,
            reconcile_interval=config.fizzdeploy_reconcile_interval,
            sync_strategy=config.fizzdeploy_sync_strategy,
            revision_history_depth=config.fizzdeploy_revision_history_depth,
            cognitive_load_threshold=config.fizzdeploy_cognitive_load_threshold,
            max_surge=config.fizzdeploy_max_surge,
            max_unavailable=config.fizzdeploy_max_unavailable,
            dashboard_width=config.fizzdeploy_dashboard_width,
            enable_dashboard=args.fizzdeploy_status is not None,
            event_bus=event_bus,
        )
        builder.with_middleware(deploy_middleware_instance)

        if not args.no_banner:
            print(
                "  +---------------------------------------------------------+\n"
                "  | FIZZDEPLOY: CONTAINER-NATIVE DEPLOYMENT PIPELINE        |\n"
                f"  | Strategy: {config.fizzdeploy_default_strategy:<46}|\n"
                f"  | Reconcile: {config.fizzdeploy_reconcile_interval:.0f}s{' ':>4} Revisions: {config.fizzdeploy_revision_history_depth:<16}|\n"
                "  | Rolling update, blue-green, canary, recreate            |\n"
                "  | GitOps reconciliation, cognitive load gating             |\n"
                "  | Argo CD / Spinnaker architecture                        |\n"
                "  +---------------------------------------------------------+"
            )
```

### Post-execution rendering block

```python
    # FizzDeploy Status (post-execution)
    if args.fizzdeploy_status and deploy_middleware_instance is not None:
        print()
        print(deploy_middleware_instance.render_revisions(args.fizzdeploy_status))
    elif args.fizzdeploy_status and deploy_middleware_instance is None:
        print("\n  FizzDeploy not enabled. Use --fizzdeploy to enable.\n")

    # FizzDeploy Pipeline (post-execution)
    if args.fizzdeploy_pipeline and deploy_middleware_instance is not None:
        print()
        print(deploy_middleware_instance.render_pipeline(args.fizzdeploy_pipeline))
    elif args.fizzdeploy_pipeline and deploy_middleware_instance is None:
        print("\n  FizzDeploy not enabled. Use --fizzdeploy to enable.\n")

    # FizzDeploy GitOps Sync (post-execution)
    if args.fizzdeploy_gitops_sync and deploy_middleware_instance is not None:
        print()
        print(deploy_middleware_instance.render_drift())
    elif args.fizzdeploy_gitops_sync and deploy_middleware_instance is None:
        print("\n  FizzDeploy not enabled. Use --fizzdeploy to enable.\n")
```

---

## 13. Factory Function

```python
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
```

---

## 14. Re-export Stub

Create `fizzdeploy.py` at repository root:

```python
"""Backward-compatible re-export stub for fizzdeploy."""
from enterprise_fizzbuzz.infrastructure.fizzdeploy import *  # noqa: F401,F403
```

---

## 15. Test Plan

### Test file: `tests/test_fizzdeploy.py` (~400 tests)

### Test Classes and Counts

| Test Class | Count | Scope |
|------------|-------|-------|
| `TestRetryPolicy` | 8 | RetryPolicy defaults, backoff calculation, max delay cap |
| `TestPipelineStep` | 15 | Step execution, timeout, retry logic, on_failure actions |
| `TestPipelineStage` | 18 | Stage execution (sequential/parallel), timeout, step aggregation |
| `TestPipeline` | 12 | Pipeline construction, stage ordering, status transitions |
| `TestPipelineExecutor` | 25 | End-to-end pipeline execution, cancel, abort, rollback path, history |
| `TestPipelineStatus` | 6 | Pipeline status enum values and transitions |
| `TestStageType` | 7 | Stage type enum values |
| `TestStageStatus` | 5 | Stage status enum values |
| `TestDeploymentStrategy` | 4 | Deployment strategy enum values |
| `TestSyncStrategy` | 3 | Sync strategy enum values |
| `TestRevisionStatus` | 4 | Revision status enum values |
| `TestOnFailureAction` | 3 | On-failure action enum values |
| `TestRollingUpdateStrategy` | 25 | Batch size computation, pod replacement, readiness checks, pause on failure |
| `TestBlueGreenStrategy` | 20 | Environment provisioning, traffic switch, validation failure abort, rollback |
| `TestCanaryStrategy` | 22 | Traffic shifting, analysis at each step, regression detection, rollback to 0% |
| `TestRecreateStrategy` | 15 | Graceful shutdown, new pod creation, downtime recording |
| `TestDeploymentManifest` | 10 | Manifest dataclass construction, defaults |
| `TestDeploymentSpec` | 8 | Spec construction, health check embedding |
| `TestHealthCheckConfig` | 8 | HTTP/TCP/exec probe configs, defaults |
| `TestManifestParser` | 20 | YAML parsing, required field validation, strategy param validation, error reporting |
| `TestGitOpsReconciler` | 25 | Manifest registration, drift detection, auto-sync, manual sync, dry-run, loop start/stop |
| `TestDriftReport` | 8 | Drift report construction, drift item format |
| `TestRollbackManager` | 20 | Revision recording, rollback execution, revision not found, history depth trim |
| `TestDeploymentRevision` | 8 | Revision construction, status transitions, rollback_from tracking |
| `TestRollbackRecord` | 6 | Record construction, success/failure |
| `TestDeploymentGate` | 15 | Threshold check, queueing, emergency bypass, queue release |
| `TestCanaryAnalysisResult` | 8 | Analysis result construction, regression flags, verdicts |
| `TestStrategyFactory` | 6 | Factory creates correct strategy type, unknown strategy error |
| `TestPipelineBuilder` | 10 | Standard pipeline construction, seven stages present, step ordering |
| `TestDeployDashboard` | 18 | Dashboard rendering (pipeline, revisions, drift, canary, gate, stats) |
| `TestFizzDeployMiddleware` | 20 | Middleware name, priority, process flow, context enrichment, error handling |
| `TestCreateFizzDeploySubsystem` | 10 | Factory function wiring, component types, defaults |
| `TestDeployExceptions` | 22 | All 22 exception classes: error codes, context, inheritance |
| `TestDeployIntegration` | 15 | End-to-end: manifest parse -> gate check -> pipeline execute -> revision record |

**Total: ~400 tests**

### Test Fixtures

```python
@pytest.fixture
def event_bus():
    """Provide a mock event bus."""
    class MockEventBus:
        def __init__(self):
            self.events = []
        def publish(self, event_type, data=None):
            self.events.append((event_type, data))
    return MockEventBus()

@pytest.fixture
def sample_manifest():
    """Provide a sample deployment manifest."""
    return DeploymentManifest(
        name="fizzbuzz-core",
        namespace="production",
        labels={"app": "fizzbuzz", "tier": "core"},
        spec=DeploymentSpec(
            image="fizzbuzz-eval:1.0.0",
            replicas=3,
            strategy=DeploymentStrategy.ROLLING_UPDATE,
            health_check=HealthCheckConfig(probe_type="http", path="/healthz", port=8080),
        ),
    )

@pytest.fixture
def pipeline_executor(event_bus):
    """Provide a PipelineExecutor instance."""
    return PipelineExecutor(event_bus=event_bus)

@pytest.fixture
def rollback_manager(event_bus):
    """Provide a RollbackManager instance."""
    return RollbackManager(max_depth=10, event_bus=event_bus)

@pytest.fixture
def reconciler(pipeline_executor, event_bus):
    """Provide a GitOpsReconciler instance."""
    return GitOpsReconciler(
        sync_strategy=SyncStrategy.AUTO,
        reconcile_interval=30.0,
        pipeline_executor=pipeline_executor,
        event_bus=event_bus,
    )

@pytest.fixture
def deployment_gate(event_bus):
    """Provide a DeploymentGate instance."""
    return DeploymentGate(threshold=70.0, event_bus=event_bus)
```

---

## 16. Implementation Order

1. Constants and enums
2. Data classes (RetryPolicy, StageResult, PipelineResult, DeploymentSpec, HealthCheckConfig, DeploymentManifest, DeploymentRevision, RollbackRecord, DriftReport, CanaryAnalysisResult)
3. PipelineStep, PipelineStage, Pipeline
4. PipelineExecutor
5. RollingUpdateStrategy
6. BlueGreenStrategy
7. CanaryStrategy
8. RecreateStrategy
9. _StrategyFactory
10. ManifestParser
11. GitOpsReconciler
12. RollbackManager
13. DeploymentGate
14. _PipelineBuilder
15. DeployDashboard
16. FizzDeployMiddleware
17. create_fizzdeploy_subsystem factory function

---

## 17. Line Budget Estimate

| Section | Lines |
|---------|-------|
| Module docstring + imports | 50 |
| Constants | 40 |
| Enums (7) | 120 |
| Data classes (10) | 280 |
| PipelineStep | 60 |
| PipelineStage | 80 |
| Pipeline | 120 |
| PipelineExecutor | 250 |
| RollingUpdateStrategy | 180 |
| BlueGreenStrategy | 160 |
| CanaryStrategy | 200 |
| RecreateStrategy | 100 |
| _StrategyFactory | 50 |
| ManifestParser | 200 |
| GitOpsReconciler | 250 |
| RollbackManager | 180 |
| DeploymentGate | 120 |
| _PipelineBuilder | 100 |
| DeployDashboard | 200 |
| FizzDeployMiddleware | 120 |
| Factory function | 60 |
| **Total** | **~3,000** |

---

## 18. Cross-Subsystem Integration Points

| Subsystem | Integration |
|-----------|-------------|
| **FizzImage** | BUILD stage invokes FizzImage catalog builder |
| **FizzRegistry** | SCAN stage invokes vulnerability scanner; PUSH stage pushes to registry |
| **FizzKube** | DEPLOY stage queries/updates pod state via FizzKube API |
| **FizzContainerd** | Strategy implementations create/delete containers via containerd daemon |
| **FizzBob** | DeploymentGate queries cognitive load model before deployment |
| **FizzPager** | Rolling update pause and drift detection trigger FizzPager alerts |
| **FizzApproval** | MANUAL sync strategy integrates with FizzApproval for drift correction approval |
| **FizzVCS** | GitOps reconciler reads declared manifests from FizzVCS |
| **FizzSLI** | Canary analysis queries SLI metrics for error rate and latency comparison |
| **FizzOTel** | Pipeline stages emit OpenTelemetry spans for execution tracing |
| **Event Bus** | All lifecycle events published to the platform event bus |
