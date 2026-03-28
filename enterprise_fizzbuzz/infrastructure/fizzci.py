"""
Enterprise FizzBuzz Platform - FizzCI: Continuous Integration Pipeline Engine

Production-grade CI pipeline engine for the Enterprise FizzBuzz Platform.
Implements YAML pipeline definitions, directed acyclic graph (DAG) execution
of stages and jobs, parallel job execution within stages, artifact passing
between stages, conditional execution (branch filters, path filters, manual
gates), secret injection from FizzVault, container-based job isolation via
FizzOCI, build caching with content-addressable storage, webhook triggers
from FizzVCS, status reporting, retry policies, matrix builds (parameterized
job expansion), pipeline templates and reusable workflows, real-time log
streaming, and pipeline visualization (ASCII DAG rendering).

FizzCI fills the platform's quality assurance gap -- the Enterprise FizzBuzz
Platform has a version control system, a deployment pipeline, a container
runtime, an image registry, and 20,100+ tests, yet no automated mechanism
to validate correctness before release.  Every merge today is an act of
faith.  FizzCI ensures that acts of faith are replaced by evidence.

Architecture reference: GitHub Actions, GitLab CI/CD, Jenkins Pipeline, Tekton.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import logging
import math
import os
import random
import re
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizzci import (
    FizzCIError,
    FizzCIPipelineParseError,
    FizzCIPipelineSyntaxError,
    FizzCIDAGCycleError,
    FizzCIDAGError,
    FizzCIStageError,
    FizzCIStageNotFoundError,
    FizzCIJobError,
    FizzCIJobTimeoutError,
    FizzCIJobCancelledError,
    FizzCIStepError,
    FizzCIStepCommandError,
    FizzCIArtifactError,
    FizzCIArtifactNotFoundError,
    FizzCIArtifactUploadError,
    FizzCICacheError,
    FizzCICacheMissError,
    FizzCISecretError,
    FizzCISecretNotFoundError,
    FizzCIConditionError,
    FizzCIBranchFilterError,
    FizzCIPathFilterError,
    FizzCIMatrixError,
    FizzCIMatrixEmptyError,
    FizzCIRetryError,
    FizzCIRetryExhaustedError,
    FizzCIWebhookError,
    FizzCIWebhookPayloadError,
    FizzCITemplateError,
    FizzCITemplateNotFoundError,
    FizzCILogError,
    FizzCIStatusError,
    FizzCIHistoryError,
    FizzCIVisualizationError,
    FizzCIConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzci")


# ============================================================
# Event Type Registration
# ============================================================

EVENT_PIPELINE_STARTED = EventType.register("FIZZCI_PIPELINE_STARTED")
EVENT_PIPELINE_COMPLETED = EventType.register("FIZZCI_PIPELINE_COMPLETED")
EVENT_PIPELINE_FAILED = EventType.register("FIZZCI_PIPELINE_FAILED")
EVENT_STAGE_STARTED = EventType.register("FIZZCI_STAGE_STARTED")
EVENT_STAGE_COMPLETED = EventType.register("FIZZCI_STAGE_COMPLETED")
EVENT_JOB_STARTED = EventType.register("FIZZCI_JOB_STARTED")
EVENT_JOB_COMPLETED = EventType.register("FIZZCI_JOB_COMPLETED")
EVENT_JOB_FAILED = EventType.register("FIZZCI_JOB_FAILED")


# ============================================================
# Constants
# ============================================================

FIZZCI_VERSION = "1.0.0"
"""FizzCI continuous integration pipeline engine version."""

FIZZCI_SERVER_NAME = f"FizzCI/{FIZZCI_VERSION} (Enterprise FizzBuzz Platform)"
"""Engine identification string."""

DEFAULT_MAX_PARALLEL_JOBS = 8
DEFAULT_JOB_TIMEOUT = 3600.0          # 1 hour
DEFAULT_STEP_TIMEOUT = 600.0          # 10 minutes
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5.0             # seconds
DEFAULT_ARTIFACT_MAX_SIZE = 104857600  # 100 MB
DEFAULT_CACHE_MAX_SIZE = 1073741824   # 1 GB
DEFAULT_CACHE_TTL = 86400.0           # 24 hours
DEFAULT_LOG_BUFFER_SIZE = 10000       # lines
DEFAULT_HISTORY_MAX_RUNS = 100
DEFAULT_DASHBOARD_WIDTH = 72

MIDDLEWARE_PRIORITY = 122

DEFAULT_CONTAINER_IMAGE = "fizzbuzz/ci-runner:latest"
DEFAULT_PIPELINES_DIR = ".fizzci/"

WEBHOOK_EVENTS = frozenset({"push", "pull_request", "tag", "schedule", "manual"})

# Simulated step command execution times (ms)
SIMULATED_STEP_DURATIONS = {
    "checkout": 1200,
    "install": 3500,
    "lint": 2100,
    "test": 8500,
    "build": 5200,
    "package": 1800,
    "deploy": 2400,
    "publish": 1500,
    "notify": 500,
    "cleanup": 300,
}


# ============================================================
# Enums
# ============================================================


class PipelineStatus(Enum):
    """Pipeline execution status."""
    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
    SKIPPED = auto()


class StageStatus(Enum):
    """Stage execution status."""
    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
    SKIPPED = auto()


class JobStatus(Enum):
    """Job execution status."""
    PENDING = auto()
    QUEUED = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
    SKIPPED = auto()
    RETRYING = auto()


class StepStatus(Enum):
    """Step execution status."""
    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    SKIPPED = auto()


class RetryStrategy(Enum):
    """Job retry strategies."""
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    NONE = "none"


class TriggerType(Enum):
    """Pipeline trigger types."""
    PUSH = "push"
    PULL_REQUEST = "pull_request"
    TAG = "tag"
    SCHEDULE = "schedule"
    MANUAL = "manual"
    WEBHOOK = "webhook"


class ConditionType(Enum):
    """Conditional execution types."""
    BRANCH = "branch"
    PATH = "path"
    MANUAL = "manual"
    EXPRESSION = "expression"
    ALWAYS = "always"
    NEVER = "never"


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class FizzCIConfig:
    """Configuration for the FizzCI pipeline engine."""
    max_parallel_jobs: int = DEFAULT_MAX_PARALLEL_JOBS
    job_timeout: float = DEFAULT_JOB_TIMEOUT
    step_timeout: float = DEFAULT_STEP_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay: float = DEFAULT_RETRY_DELAY
    artifact_max_size: int = DEFAULT_ARTIFACT_MAX_SIZE
    cache_max_size: int = DEFAULT_CACHE_MAX_SIZE
    cache_ttl: float = DEFAULT_CACHE_TTL
    log_buffer_size: int = DEFAULT_LOG_BUFFER_SIZE
    history_max_runs: int = DEFAULT_HISTORY_MAX_RUNS
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
    default_image: str = DEFAULT_CONTAINER_IMAGE
    pipelines_dir: str = DEFAULT_PIPELINES_DIR
    webhook_secret: str = ""


@dataclass
class StepDefinition:
    """A single step within a job."""
    name: str = ""
    command: str = ""
    working_directory: str = ""
    environment: Dict[str, str] = field(default_factory=dict)
    timeout: float = DEFAULT_STEP_TIMEOUT
    continue_on_error: bool = False
    condition: str = ""


@dataclass
class RetryPolicy:
    """Job retry configuration."""
    max_attempts: int = DEFAULT_MAX_RETRIES
    strategy: RetryStrategy = RetryStrategy.FIXED
    delay: float = DEFAULT_RETRY_DELAY
    max_delay: float = 300.0


@dataclass
class ArtifactSpec:
    """Artifact upload/download specification."""
    name: str = ""
    paths: List[str] = field(default_factory=list)
    when: str = "on_success"  # on_success, on_failure, always
    expire_in: float = 86400.0  # seconds


@dataclass
class MatrixConfig:
    """Matrix build configuration for parameterized job expansion."""
    parameters: Dict[str, List[str]] = field(default_factory=dict)
    include: List[Dict[str, str]] = field(default_factory=list)
    exclude: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ConditionSpec:
    """Conditional execution specification."""
    condition_type: ConditionType = ConditionType.ALWAYS
    branches: List[str] = field(default_factory=list)
    paths: List[str] = field(default_factory=list)
    expression: str = ""


@dataclass
class JobDefinition:
    """A job within a stage, containing steps."""
    name: str = ""
    steps: List[StepDefinition] = field(default_factory=list)
    image: str = DEFAULT_CONTAINER_IMAGE
    services: List[str] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    secrets: List[str] = field(default_factory=list)
    artifacts: Optional[ArtifactSpec] = None
    cache_key: str = ""
    cache_paths: List[str] = field(default_factory=list)
    retry: Optional[RetryPolicy] = None
    timeout: float = DEFAULT_JOB_TIMEOUT
    condition: Optional[ConditionSpec] = None
    needs: List[str] = field(default_factory=list)
    matrix: Optional[MatrixConfig] = None
    allow_failure: bool = False


@dataclass
class StageDefinition:
    """A stage containing jobs that execute in parallel."""
    name: str = ""
    jobs: List[JobDefinition] = field(default_factory=list)
    condition: Optional[ConditionSpec] = None
    depends_on: List[str] = field(default_factory=list)


@dataclass
class PipelineDefinition:
    """Complete pipeline definition parsed from YAML."""
    name: str = ""
    stages: List[StageDefinition] = field(default_factory=list)
    triggers: List[TriggerType] = field(default_factory=list)
    variables: Dict[str, str] = field(default_factory=dict)
    timeout: float = DEFAULT_JOB_TIMEOUT
    version: str = "1.0"


@dataclass
class StepResult:
    """Result of executing a single step."""
    name: str = ""
    status: StepStatus = StepStatus.PENDING
    exit_code: int = 0
    output: str = ""
    duration_ms: float = 0.0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


@dataclass
class JobResult:
    """Result of executing a job."""
    name: str = ""
    status: JobStatus = JobStatus.PENDING
    step_results: List[StepResult] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    retry_count: int = 0
    matrix_values: Dict[str, str] = field(default_factory=dict)
    log_lines: List[str] = field(default_factory=list)


@dataclass
class StageResult:
    """Result of executing a stage."""
    name: str = ""
    status: StageStatus = StageStatus.PENDING
    job_results: List[JobResult] = field(default_factory=list)
    duration_ms: float = 0.0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


@dataclass
class PipelineRun:
    """A single execution of a pipeline."""
    run_id: str = ""
    pipeline_name: str = ""
    status: PipelineStatus = PipelineStatus.PENDING
    trigger: TriggerType = TriggerType.MANUAL
    trigger_ref: str = ""
    stage_results: List[StageResult] = field(default_factory=list)
    variables: Dict[str, str] = field(default_factory=dict)
    duration_ms: float = 0.0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    commit_sha: str = ""
    branch: str = "main"


@dataclass
class Artifact:
    """Stored build artifact."""
    name: str = ""
    pipeline_name: str = ""
    run_id: str = ""
    job_name: str = ""
    content_hash: str = ""
    size: int = 0
    paths: List[str] = field(default_factory=list)
    data: bytes = b""
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


@dataclass
class CacheEntry:
    """Build cache entry."""
    key: str = ""
    content_hash: str = ""
    size: int = 0
    data: bytes = b""
    created_at: float = 0.0
    last_accessed: float = 0.0
    hit_count: int = 0


@dataclass
class WebhookPayload:
    """Webhook trigger payload."""
    event: str = ""
    ref: str = ""
    branch: str = ""
    commit_sha: str = ""
    author: str = ""
    message: str = ""
    paths_changed: List[str] = field(default_factory=list)
    timestamp: float = 0.0
    signature: str = ""


@dataclass
class EngineMetrics:
    """Aggregate CI engine metrics."""
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    cancelled_runs: int = 0
    total_jobs: int = 0
    successful_jobs: int = 0
    failed_jobs: int = 0
    total_steps: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    artifacts_stored: int = 0
    artifacts_size_bytes: int = 0
    total_duration_ms: float = 0.0
    retries_performed: int = 0


# ============================================================
# Pipeline Parser
# ============================================================


class PipelineParser:
    """YAML pipeline definition parser.

    Parses pipeline definitions from dictionaries (representing parsed
    YAML) into PipelineDefinition objects.  Validates structure, resolves
    stage dependencies, and expands shorthand notations.
    """

    def parse(self, definition: Dict[str, Any]) -> PipelineDefinition:
        """Parse a pipeline definition dictionary into a PipelineDefinition."""
        pipeline = PipelineDefinition()
        pipeline.name = definition.get("name", "unnamed-pipeline")
        pipeline.version = definition.get("version", "1.0")
        pipeline.variables = definition.get("variables", {})
        pipeline.timeout = float(definition.get("timeout", DEFAULT_JOB_TIMEOUT))

        # Parse triggers
        triggers = definition.get("triggers", definition.get("on", ["manual"]))
        if isinstance(triggers, str):
            triggers = [triggers]
        for t in triggers:
            try:
                pipeline.triggers.append(TriggerType(t))
            except ValueError:
                pipeline.triggers.append(TriggerType.MANUAL)

        # Parse stages
        stages_def = definition.get("stages", [])
        if isinstance(stages_def, list):
            for stage_def in stages_def:
                if isinstance(stage_def, dict):
                    pipeline.stages.append(self._parse_stage(stage_def))
                elif isinstance(stage_def, str):
                    pipeline.stages.append(StageDefinition(name=stage_def))

        if not pipeline.stages:
            raise FizzCIPipelineSyntaxError(pipeline.name, "Pipeline must have at least one stage")

        return pipeline

    def _parse_stage(self, stage_def: Dict[str, Any]) -> StageDefinition:
        """Parse a stage definition."""
        stage = StageDefinition()
        stage.name = stage_def.get("name", "unnamed-stage")
        stage.depends_on = stage_def.get("depends_on", [])

        # Parse condition
        if "condition" in stage_def:
            stage.condition = self._parse_condition(stage_def["condition"])

        # Parse jobs
        jobs_def = stage_def.get("jobs", [])
        for job_def in jobs_def:
            if isinstance(job_def, dict):
                stage.jobs.append(self._parse_job(job_def))

        return stage

    def _parse_job(self, job_def: Dict[str, Any]) -> JobDefinition:
        """Parse a job definition."""
        job = JobDefinition()
        job.name = job_def.get("name", "unnamed-job")
        job.image = job_def.get("image", DEFAULT_CONTAINER_IMAGE)
        job.services = job_def.get("services", [])
        job.environment = job_def.get("environment", job_def.get("env", {}))
        job.secrets = job_def.get("secrets", [])
        job.cache_key = job_def.get("cache_key", "")
        job.cache_paths = job_def.get("cache_paths", [])
        job.timeout = float(job_def.get("timeout", DEFAULT_JOB_TIMEOUT))
        job.needs = job_def.get("needs", [])
        job.allow_failure = job_def.get("allow_failure", False)

        # Parse steps
        steps_def = job_def.get("steps", [])
        for step_def in steps_def:
            if isinstance(step_def, dict):
                job.steps.append(self._parse_step(step_def))
            elif isinstance(step_def, str):
                job.steps.append(StepDefinition(name=step_def, command=step_def))

        # Parse retry policy
        if "retry" in job_def:
            retry_def = job_def["retry"]
            if isinstance(retry_def, int):
                job.retry = RetryPolicy(max_attempts=retry_def)
            elif isinstance(retry_def, dict):
                job.retry = RetryPolicy(
                    max_attempts=retry_def.get("max_attempts", DEFAULT_MAX_RETRIES),
                    strategy=RetryStrategy(retry_def.get("strategy", "fixed")),
                    delay=float(retry_def.get("delay", DEFAULT_RETRY_DELAY)),
                )

        # Parse artifacts
        if "artifacts" in job_def:
            art_def = job_def["artifacts"]
            job.artifacts = ArtifactSpec(
                name=art_def.get("name", job.name),
                paths=art_def.get("paths", []),
                when=art_def.get("when", "on_success"),
                expire_in=float(art_def.get("expire_in", 86400.0)),
            )

        # Parse matrix
        if "matrix" in job_def:
            mat_def = job_def["matrix"]
            job.matrix = MatrixConfig(
                parameters=mat_def.get("parameters", {}),
                include=mat_def.get("include", []),
                exclude=mat_def.get("exclude", []),
            )

        # Parse condition
        if "condition" in job_def:
            job.condition = self._parse_condition(job_def["condition"])

        return job

    def _parse_step(self, step_def: Dict[str, Any]) -> StepDefinition:
        """Parse a step definition."""
        return StepDefinition(
            name=step_def.get("name", step_def.get("run", "unnamed-step")),
            command=step_def.get("run", step_def.get("command", "")),
            working_directory=step_def.get("working_directory", ""),
            environment=step_def.get("env", {}),
            timeout=float(step_def.get("timeout", DEFAULT_STEP_TIMEOUT)),
            continue_on_error=step_def.get("continue_on_error", False),
            condition=step_def.get("if", ""),
        )

    def _parse_condition(self, cond_def: Any) -> ConditionSpec:
        """Parse a condition specification."""
        if isinstance(cond_def, str):
            if cond_def == "always":
                return ConditionSpec(condition_type=ConditionType.ALWAYS)
            elif cond_def == "never":
                return ConditionSpec(condition_type=ConditionType.NEVER)
            elif cond_def == "manual":
                return ConditionSpec(condition_type=ConditionType.MANUAL)
            return ConditionSpec(condition_type=ConditionType.EXPRESSION, expression=cond_def)

        if isinstance(cond_def, dict):
            if "branches" in cond_def:
                return ConditionSpec(
                    condition_type=ConditionType.BRANCH,
                    branches=cond_def["branches"],
                )
            if "paths" in cond_def:
                return ConditionSpec(
                    condition_type=ConditionType.PATH,
                    paths=cond_def["paths"],
                )

        return ConditionSpec(condition_type=ConditionType.ALWAYS)


# ============================================================
# DAG Builder
# ============================================================


class DAGBuilder:
    """Directed Acyclic Graph builder for pipeline execution ordering.

    Constructs a topological ordering of stages using Kahn's algorithm,
    detecting cycles that would indicate an impossible execution order.
    """

    def build(self, stages: List[StageDefinition]) -> List[List[StageDefinition]]:
        """Build execution levels from stage dependencies.

        Returns a list of levels, where each level contains stages
        that can execute in parallel (all dependencies satisfied).
        """
        name_to_stage = {s.name: s for s in stages}
        in_degree: Dict[str, int] = {s.name: 0 for s in stages}
        adjacency: Dict[str, List[str]] = {s.name: [] for s in stages}

        for stage in stages:
            for dep in stage.depends_on:
                if dep not in name_to_stage:
                    raise FizzCIDAGError(f"Stage '{stage.name}' depends on unknown stage '{dep}'")
                adjacency[dep].append(stage.name)
                in_degree[stage.name] += 1

        # Kahn's algorithm
        queue = deque([name for name, deg in in_degree.items() if deg == 0])
        levels: List[List[StageDefinition]] = []
        processed = 0

        while queue:
            level_names = list(queue)
            queue.clear()
            level = [name_to_stage[n] for n in level_names]
            levels.append(level)
            processed += len(level)

            for name in level_names:
                for neighbor in adjacency[name]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        if processed != len(stages):
            cycle_nodes = [n for n, d in in_degree.items() if d > 0]
            raise FizzCIDAGCycleError(
                f"Cycle detected in stage dependencies involving: {', '.join(cycle_nodes)}"
            )

        return levels

    def validate(self, pipeline: PipelineDefinition) -> bool:
        """Validate that a pipeline's stage graph is a valid DAG."""
        try:
            self.build(pipeline.stages)
            return True
        except (FizzCIDAGCycleError, FizzCIDAGError):
            return False


# ============================================================
# Matrix Expander
# ============================================================


class MatrixExpander:
    """Matrix build parameter expander.

    Expands a matrix configuration into concrete job instances by
    computing the Cartesian product of parameter lists, applying
    include/exclude rules.
    """

    def expand(self, job: JobDefinition) -> List[JobDefinition]:
        """Expand a job with matrix configuration into concrete jobs."""
        if job.matrix is None or not job.matrix.parameters:
            return [job]

        combinations = self._cartesian_product(job.matrix.parameters)

        # Apply excludes
        if job.matrix.exclude:
            combinations = [
                c for c in combinations
                if not any(self._matches(c, ex) for ex in job.matrix.exclude)
            ]

        # Apply includes
        for inc in job.matrix.include:
            if inc not in combinations:
                combinations.append(inc)

        if not combinations:
            raise FizzCIMatrixEmptyError(job.name)

        expanded = []
        for combo in combinations:
            expanded_job = copy.deepcopy(job)
            suffix = "-".join(f"{v}" for v in combo.values())
            expanded_job.name = f"{job.name} ({suffix})"
            expanded_job.matrix = None  # Clear matrix on expanded jobs

            # Merge matrix values into environment
            for key, value in combo.items():
                expanded_job.environment[f"MATRIX_{key.upper()}"] = value

            expanded.append(expanded_job)

        return expanded

    def _cartesian_product(self, params: Dict[str, List[str]]) -> List[Dict[str, str]]:
        """Compute Cartesian product of parameter lists."""
        keys = list(params.keys())
        if not keys:
            return [{}]

        result = [{}]
        for key in keys:
            new_result = []
            for combo in result:
                for value in params[key]:
                    new_combo = dict(combo)
                    new_combo[key] = value
                    new_result.append(new_combo)
            result = new_result

        return result

    def _matches(self, combo: Dict[str, str], pattern: Dict[str, str]) -> bool:
        """Check if a combination matches an exclude pattern."""
        return all(combo.get(k) == v for k, v in pattern.items())

    def preview(self, job: JobDefinition) -> List[Dict[str, str]]:
        """Preview matrix expansion without creating jobs."""
        if job.matrix is None:
            return [{}]
        combos = self._cartesian_product(job.matrix.parameters)
        if job.matrix.exclude:
            combos = [c for c in combos if not any(self._matches(c, ex) for ex in job.matrix.exclude)]
        for inc in job.matrix.include:
            if inc not in combos:
                combos.append(inc)
        return combos


# ============================================================
# Conditional Evaluator
# ============================================================


class ConditionalEvaluator:
    """Evaluates conditional execution rules.

    Determines whether a stage or job should execute based on
    branch filters, path filters, manual gates, and expressions.
    """

    def evaluate(self, condition: Optional[ConditionSpec],
                 context: Dict[str, Any]) -> bool:
        """Evaluate a condition against the current execution context.

        Returns True if the stage/job should execute.
        """
        if condition is None:
            return True

        if condition.condition_type == ConditionType.ALWAYS:
            return True
        elif condition.condition_type == ConditionType.NEVER:
            return False
        elif condition.condition_type == ConditionType.MANUAL:
            return context.get("manual_approval", False)
        elif condition.condition_type == ConditionType.BRANCH:
            return self._evaluate_branch(condition.branches, context)
        elif condition.condition_type == ConditionType.PATH:
            return self._evaluate_path(condition.paths, context)
        elif condition.condition_type == ConditionType.EXPRESSION:
            return self._evaluate_expression(condition.expression, context)

        return True

    def _evaluate_branch(self, branches: List[str], context: Dict[str, Any]) -> bool:
        """Evaluate branch filter conditions."""
        current_branch = context.get("branch", "main")
        for pattern in branches:
            if pattern == current_branch:
                return True
            if pattern.endswith("*") and current_branch.startswith(pattern[:-1]):
                return True
        return False

    def _evaluate_path(self, paths: List[str], context: Dict[str, Any]) -> bool:
        """Evaluate path filter conditions."""
        changed_paths = context.get("paths_changed", [])
        for pattern in paths:
            for changed in changed_paths:
                if pattern == changed:
                    return True
                if pattern.endswith("*") and changed.startswith(pattern[:-1]):
                    return True
                if pattern.endswith("/**") and changed.startswith(pattern[:-3]):
                    return True
        return False

    def _evaluate_expression(self, expression: str, context: Dict[str, Any]) -> bool:
        """Evaluate a simple expression condition."""
        # Support simple expressions
        expression = expression.strip()
        if expression == "true":
            return True
        if expression == "false":
            return False
        # Support equality checks: var == value
        if "==" in expression:
            parts = expression.split("==", 1)
            left = parts[0].strip().lstrip("$")
            right = parts[1].strip().strip("'\"")
            return str(context.get(left, "")) == right
        return True


# ============================================================
# Artifact Manager
# ============================================================


class ArtifactManager:
    """Content-addressable artifact storage and retrieval.

    Stores build artifacts keyed by SHA-256 content hash for
    deduplication.  Artifacts are associated with pipeline runs
    and jobs for traceability.
    """

    def __init__(self, config: FizzCIConfig) -> None:
        self._config = config
        self._artifacts: Dict[str, Artifact] = {}
        self._by_name: Dict[str, List[str]] = defaultdict(list)

    def store(self, name: str, data: bytes, pipeline_name: str,
              run_id: str, job_name: str,
              paths: Optional[List[str]] = None) -> Artifact:
        """Store an artifact and return its metadata."""
        if len(data) > self._config.artifact_max_size:
            raise FizzCIArtifactUploadError(
                name, f"Artifact exceeds size limit ({len(data)} > {self._config.artifact_max_size})"
            )

        content_hash = hashlib.sha256(data).hexdigest()
        artifact_id = f"{run_id}/{job_name}/{name}"
        now = datetime.now(timezone.utc)

        artifact = Artifact(
            name=name,
            pipeline_name=pipeline_name,
            run_id=run_id,
            job_name=job_name,
            content_hash=content_hash,
            size=len(data),
            paths=paths or [],
            data=data,
            created_at=now,
            expires_at=now + timedelta(seconds=86400.0),
        )

        self._artifacts[artifact_id] = artifact
        self._by_name[name].append(artifact_id)

        logger.debug("Artifact stored: %s (%d bytes, hash=%s)", artifact_id, len(data), content_hash[:12])
        return artifact

    def retrieve(self, name: str, run_id: str = "",
                 job_name: str = "") -> Optional[Artifact]:
        """Retrieve an artifact by name, optionally scoped to run/job."""
        if run_id and job_name:
            artifact_id = f"{run_id}/{job_name}/{name}"
            return self._artifacts.get(artifact_id)

        # Find most recent by name
        ids = self._by_name.get(name, [])
        if ids:
            return self._artifacts.get(ids[-1])

        return None

    def list_all(self) -> List[Artifact]:
        """List all stored artifacts."""
        return list(self._artifacts.values())

    def delete(self, artifact_id: str) -> bool:
        """Delete an artifact by ID."""
        if artifact_id in self._artifacts:
            art = self._artifacts.pop(artifact_id)
            if art.name in self._by_name:
                self._by_name[art.name] = [
                    aid for aid in self._by_name[art.name] if aid != artifact_id
                ]
            return True
        return False

    def cleanup_expired(self) -> int:
        """Remove expired artifacts. Returns count removed."""
        now = datetime.now(timezone.utc)
        expired = [aid for aid, a in self._artifacts.items()
                   if a.expires_at and a.expires_at < now]
        for aid in expired:
            self.delete(aid)
        return len(expired)

    @property
    def total_size(self) -> int:
        """Total size of all stored artifacts in bytes."""
        return sum(a.size for a in self._artifacts.values())

    @property
    def count(self) -> int:
        """Number of stored artifacts."""
        return len(self._artifacts)


# ============================================================
# Build Cache
# ============================================================


class BuildCache:
    """Content-addressable build cache with LRU eviction.

    Caches build outputs keyed by a hash of inputs (source files,
    dependencies, environment) to avoid redundant work.
    """

    def __init__(self, config: FizzCIConfig) -> None:
        self._config = config
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._total_size = 0
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[bytes]:
        """Retrieve a cache entry by key. Returns None on miss."""
        entry = self._entries.get(key)
        if entry is None:
            self._misses += 1
            return None

        now = time.time()
        if now - entry.created_at > self._config.cache_ttl:
            self._evict(key)
            self._misses += 1
            return None

        entry.last_accessed = now
        entry.hit_count += 1
        self._entries.move_to_end(key)
        self._hits += 1

        return entry.data

    def put(self, key: str, data: bytes) -> None:
        """Store a cache entry, evicting LRU entries if necessary."""
        content_hash = hashlib.sha256(data).hexdigest()
        size = len(data)

        # Evict until we have room
        while self._total_size + size > self._config.cache_max_size and self._entries:
            self._evict_lru()

        now = time.time()
        self._entries[key] = CacheEntry(
            key=key,
            content_hash=content_hash,
            size=size,
            data=data,
            created_at=now,
            last_accessed=now,
            hit_count=0,
        )
        self._total_size += size

    def invalidate(self, key: str) -> bool:
        """Invalidate a specific cache entry."""
        return self._evict(key)

    def clear(self) -> int:
        """Clear all cache entries. Returns count cleared."""
        count = len(self._entries)
        self._entries.clear()
        self._total_size = 0
        return count

    def _evict(self, key: str) -> bool:
        """Evict a specific cache entry."""
        entry = self._entries.pop(key, None)
        if entry:
            self._total_size -= entry.size
            return True
        return False

    def _evict_lru(self) -> None:
        """Evict the least recently used entry."""
        if self._entries:
            key, entry = self._entries.popitem(last=False)
            self._total_size -= entry.size

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a percentage."""
        total = self._hits + self._misses
        return (self._hits / total * 100) if total > 0 else 0.0

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        return {
            "entries": len(self._entries),
            "total_size": self._total_size,
            "max_size": self._config.cache_max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self.hit_rate:.1f}%",
        }


# ============================================================
# Secret Injector
# ============================================================


class SecretInjector:
    """Injects secrets from the platform's vault into job environments.

    Resolves secret references in job definitions to actual values,
    masking them in log output.
    """

    # Simulated vault secrets
    _VAULT: Dict[str, str] = {
        "DEPLOY_TOKEN": "fzbz-deploy-xxxxxxxx",
        "REGISTRY_PASSWORD": "fzbz-registry-yyyyyyyy",
        "SONAR_TOKEN": "fzbz-sonar-zzzzzzzz",
        "SLACK_WEBHOOK": "https://hooks.fizzbuzz.local/services/XXXXXXXXX",
        "NPM_TOKEN": "npm_fizzbuzz_aaaaaa",
        "DATABASE_URL": "postgresql://fizzbuzz:fizzbuzz@localhost:5432/fizzbuzz",
        "AWS_ACCESS_KEY_ID": "AKIAFIZZBUZZ000000",
        "AWS_SECRET_ACCESS_KEY": "fzbz+secret+bbbbbbbb",
    }

    def inject(self, job: JobDefinition) -> Dict[str, str]:
        """Resolve secret references and return environment with injected secrets."""
        env = dict(job.environment)

        for secret_name in job.secrets:
            value = self._VAULT.get(secret_name)
            if value is None:
                raise FizzCISecretNotFoundError(secret_name)
            env[secret_name] = value

        return env

    def mask_secrets(self, text: str, secrets: List[str]) -> str:
        """Replace secret values in text with masked placeholders."""
        for secret_name in secrets:
            value = self._VAULT.get(secret_name, "")
            if value and value in text:
                text = text.replace(value, f"***{secret_name}***")
        return text

    def list_available(self) -> List[str]:
        """List available secret names (not values)."""
        return sorted(self._VAULT.keys())


# ============================================================
# Log Streamer
# ============================================================


class LogStreamer:
    """Real-time buffered log output per job.

    Captures step output and provides streaming access for
    dashboard display and post-execution review.
    """

    def __init__(self, config: FizzCIConfig) -> None:
        self._config = config
        self._buffers: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def create_buffer(self, job_id: str) -> None:
        """Create a log buffer for a job."""
        with self._lock:
            self._buffers[job_id] = deque(maxlen=self._config.log_buffer_size)

    def append(self, job_id: str, line: str) -> None:
        """Append a log line to a job's buffer."""
        buf = self._buffers.get(job_id)
        if buf is not None:
            timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
            buf.append(f"[{timestamp}] {line}")

    def get_lines(self, job_id: str, last_n: int = 0) -> List[str]:
        """Retrieve log lines for a job."""
        buf = self._buffers.get(job_id)
        if buf is None:
            return []
        lines = list(buf)
        if last_n > 0:
            return lines[-last_n:]
        return lines

    def clear(self, job_id: str) -> None:
        """Clear a job's log buffer."""
        with self._lock:
            self._buffers.pop(job_id, None)


# ============================================================
# Step Executor
# ============================================================


class StepExecutor:
    """Executes individual pipeline steps.

    Simulates command execution with realistic timing and output,
    consistent with the platform's simulation pattern.
    """

    def __init__(self, config: FizzCIConfig, secret_injector: SecretInjector,
                 log_streamer: LogStreamer) -> None:
        self._config = config
        self._secrets = secret_injector
        self._log = log_streamer

    def execute(self, step: StepDefinition, job_id: str,
                environment: Dict[str, str]) -> StepResult:
        """Execute a single step and return the result."""
        result = StepResult(
            name=step.name,
            status=StepStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        self._log.append(job_id, f"Step: {step.name}")
        if step.command:
            self._log.append(job_id, f"  $ {step.command}")

        # Simulate execution
        cmd_base = step.command.split()[0] if step.command else "run"
        duration = SIMULATED_STEP_DURATIONS.get(cmd_base, 1000 + random.randint(100, 2000))
        # Scale down for simulation (don't actually wait)
        result.duration_ms = float(duration)

        # Simulate output
        output_lines = self._generate_output(step, environment)
        for line in output_lines:
            masked = self._secrets.mask_secrets(line, list(environment.keys()))
            self._log.append(job_id, f"  {masked}")

        # Simulate success/failure (5% random failure rate for realism)
        if random.random() < 0.05 and not step.continue_on_error:
            result.status = StepStatus.FAILED
            result.exit_code = 1
            result.output = f"Error: {step.command} exited with code 1"
            self._log.append(job_id, f"  EXIT CODE: 1")
        else:
            result.status = StepStatus.SUCCESS
            result.exit_code = 0
            result.output = "\n".join(output_lines)
            self._log.append(job_id, f"  EXIT CODE: 0")

        result.finished_at = datetime.now(timezone.utc)

        if result.status == StepStatus.FAILED and step.continue_on_error:
            result.status = StepStatus.SUCCESS
            self._log.append(job_id, f"  (continue_on_error: ignoring failure)")

        return result

    def _generate_output(self, step: StepDefinition,
                         environment: Dict[str, str]) -> List[str]:
        """Generate simulated step output."""
        cmd = step.command.lower() if step.command else ""
        lines = []

        if "checkout" in cmd:
            lines = [
                "Cloning repository...",
                "HEAD is now at abc1234 feat(fizzbuzz): latest commit",
                "Submodule 'enterprise_fizzbuzz' registered",
            ]
        elif "install" in cmd or "pip" in cmd:
            lines = [
                "Installing dependencies...",
                "Collecting pytest>=7.0",
                "Collecting pyyaml>=6.0",
                "Successfully installed 12 packages",
            ]
        elif "lint" in cmd:
            lines = [
                "Running linter...",
                "Checking 843 files...",
                "All checks passed. 0 errors, 0 warnings.",
            ]
        elif "test" in cmd or "pytest" in cmd:
            lines = [
                "Running test suite...",
                "collected 20100 items",
                "tests/ .........................................",
                "20100 passed in 287.43s",
            ]
        elif "build" in cmd:
            lines = [
                "Building artifacts...",
                "Compiling enterprise_fizzbuzz package...",
                "Build complete: dist/enterprise_fizzbuzz-1.0.0.tar.gz",
            ]
        elif "deploy" in cmd:
            lines = [
                "Deploying to production...",
                f"Image: {environment.get('CI_IMAGE', DEFAULT_CONTAINER_IMAGE)}",
                "Deployment successful.",
            ]
        else:
            lines = [
                f"Executing: {step.command}",
                "Done.",
            ]

        return lines


# ============================================================
# Job Runner
# ============================================================


class JobRunner:
    """Executes pipeline jobs.

    Runs all steps in a job sequentially, manages retries,
    collects artifacts, and reports results.
    """

    def __init__(self, config: FizzCIConfig, step_executor: StepExecutor,
                 artifact_manager: ArtifactManager, build_cache: BuildCache,
                 log_streamer: LogStreamer) -> None:
        self._config = config
        self._step_executor = step_executor
        self._artifacts = artifact_manager
        self._cache = build_cache
        self._log = log_streamer

    def run(self, job: JobDefinition, pipeline_name: str,
            run_id: str, environment: Dict[str, str]) -> JobResult:
        """Execute a job and return the result."""
        job_id = f"{run_id}/{job.name}"
        self._log.create_buffer(job_id)

        result = JobResult(
            name=job.name,
            status=JobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        self._log.append(job_id, f"Job started: {job.name}")
        self._log.append(job_id, f"Image: {job.image}")

        # Merge job environment
        merged_env = dict(environment)
        merged_env.update(job.environment)
        merged_env["CI_JOB_NAME"] = job.name
        merged_env["CI_IMAGE"] = job.image

        # Check build cache
        if job.cache_key:
            cached = self._cache.get(job.cache_key)
            if cached is not None:
                self._log.append(job_id, f"Cache hit: {job.cache_key}")
            else:
                self._log.append(job_id, f"Cache miss: {job.cache_key}")

        # Execute steps
        all_success = True
        for step in job.steps:
            step_result = self._step_executor.execute(step, job_id, merged_env)
            result.step_results.append(step_result)
            result.duration_ms += step_result.duration_ms

            if step_result.status == StepStatus.FAILED:
                all_success = False
                break

        # Handle retry
        retry_policy = job.retry or RetryPolicy(max_attempts=0)
        if not all_success and retry_policy.max_attempts > 0:
            for attempt in range(1, retry_policy.max_attempts + 1):
                result.retry_count = attempt
                self._log.append(job_id, f"Retrying (attempt {attempt}/{retry_policy.max_attempts})...")

                # Re-run failed steps
                all_success = True
                result.step_results.clear()
                for step in job.steps:
                    step_result = self._step_executor.execute(step, job_id, merged_env)
                    result.step_results.append(step_result)
                    result.duration_ms += step_result.duration_ms
                    if step_result.status == StepStatus.FAILED:
                        all_success = False
                        break

                if all_success:
                    break

        # Set final status
        if all_success:
            result.status = JobStatus.SUCCESS
        elif job.allow_failure:
            result.status = JobStatus.SUCCESS
            self._log.append(job_id, "Job failed but allow_failure=true")
        else:
            result.status = JobStatus.FAILED

        # Store artifacts
        if job.artifacts and (
            (job.artifacts.when == "on_success" and result.status == JobStatus.SUCCESS) or
            (job.artifacts.when == "on_failure" and result.status == JobStatus.FAILED) or
            job.artifacts.when == "always"
        ):
            artifact_data = json.dumps({
                "job": job.name,
                "paths": job.artifacts.paths,
                "status": result.status.name,
            }).encode("utf-8")
            try:
                art = self._artifacts.store(
                    job.artifacts.name, artifact_data,
                    pipeline_name, run_id, job.name, job.artifacts.paths
                )
                result.artifacts[job.artifacts.name] = art.content_hash
                self._log.append(job_id, f"Artifact stored: {job.artifacts.name}")
            except FizzCIArtifactError as e:
                self._log.append(job_id, f"Artifact upload failed: {e}")

        # Update build cache
        if job.cache_key and all_success:
            cache_data = json.dumps({"job": job.name, "cached": True}).encode("utf-8")
            self._cache.put(job.cache_key, cache_data)
            self._log.append(job_id, f"Cache updated: {job.cache_key}")

        result.finished_at = datetime.now(timezone.utc)
        result.log_lines = self._log.get_lines(job_id)

        self._log.append(job_id, f"Job finished: {result.status.name} ({result.duration_ms:.0f}ms)")
        return result


# ============================================================
# Pipeline Executor
# ============================================================


class PipelineExecutor:
    """Top-level pipeline execution orchestrator.

    Parses the pipeline definition, builds the DAG, expands matrices,
    evaluates conditions, and executes stages in dependency order with
    parallel job execution within each stage.
    """

    def __init__(self, config: FizzCIConfig,
                 job_runner: JobRunner,
                 dag_builder: DAGBuilder,
                 matrix_expander: MatrixExpander,
                 conditional_evaluator: ConditionalEvaluator,
                 secret_injector: SecretInjector,
                 log_streamer: LogStreamer) -> None:
        self._config = config
        self._job_runner = job_runner
        self._dag = dag_builder
        self._matrix = matrix_expander
        self._conditional = conditional_evaluator
        self._secrets = secret_injector
        self._log = log_streamer

    def execute(self, pipeline: PipelineDefinition,
                trigger: TriggerType = TriggerType.MANUAL,
                context: Optional[Dict[str, Any]] = None) -> PipelineRun:
        """Execute a pipeline and return the run result."""
        if context is None:
            context = {}

        run = PipelineRun(
            run_id=uuid.uuid4().hex[:12],
            pipeline_name=pipeline.name,
            status=PipelineStatus.RUNNING,
            trigger=trigger,
            trigger_ref=context.get("ref", ""),
            variables=dict(pipeline.variables),
            started_at=datetime.now(timezone.utc),
            commit_sha=context.get("commit_sha", uuid.uuid4().hex[:8]),
            branch=context.get("branch", "main"),
        )

        # Build global environment
        global_env = {
            "CI": "true",
            "CI_PIPELINE_NAME": pipeline.name,
            "CI_RUN_ID": run.run_id,
            "CI_BRANCH": run.branch,
            "CI_COMMIT_SHA": run.commit_sha,
            "CI_TRIGGER": trigger.value,
        }
        global_env.update(pipeline.variables)

        # Build execution DAG
        levels = self._dag.build(pipeline.stages)

        # Execute levels in order
        pipeline_success = True
        for level in levels:
            level_results = []
            for stage in level:
                stage_result = self._execute_stage(stage, pipeline, run, global_env, context)
                level_results.append(stage_result)
                run.stage_results.append(stage_result)

                if stage_result.status == StageStatus.FAILED:
                    pipeline_success = False

            if not pipeline_success:
                # Cancel remaining stages
                break

        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = sum(sr.duration_ms for sr in run.stage_results)

        if pipeline_success:
            run.status = PipelineStatus.SUCCESS
        else:
            run.status = PipelineStatus.FAILED

        return run

    def _execute_stage(self, stage: StageDefinition, pipeline: PipelineDefinition,
                       run: PipelineRun, global_env: Dict[str, str],
                       context: Dict[str, Any]) -> StageResult:
        """Execute a single stage."""
        result = StageResult(
            name=stage.name,
            status=StageStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        # Check condition
        if not self._conditional.evaluate(stage.condition, context):
            result.status = StageStatus.SKIPPED
            result.finished_at = datetime.now(timezone.utc)
            return result

        # Expand matrix jobs
        expanded_jobs = []
        for job in stage.jobs:
            if not self._conditional.evaluate(job.condition, context):
                continue
            expanded = self._matrix.expand(job)
            expanded_jobs.extend(expanded)

        # Inject secrets and execute jobs (simulated parallel)
        all_success = True
        for job in expanded_jobs:
            try:
                env = self._secrets.inject(job)
            except FizzCISecretNotFoundError:
                env = dict(job.environment)

            merged_env = dict(global_env)
            merged_env.update(env)
            merged_env["CI_STAGE_NAME"] = stage.name

            job_result = self._job_runner.run(job, pipeline.name, run.run_id, merged_env)
            result.job_results.append(job_result)
            result.duration_ms += job_result.duration_ms

            if job_result.status == JobStatus.FAILED:
                all_success = False

        result.status = StageStatus.SUCCESS if all_success else StageStatus.FAILED
        result.finished_at = datetime.now(timezone.utc)
        return result


# ============================================================
# Webhook Trigger Handler
# ============================================================


class WebhookTriggerHandler:
    """Handles webhook-triggered pipeline executions.

    Validates webhook payloads, matches events to pipeline triggers,
    and initiates pipeline runs.
    """

    def __init__(self, config: FizzCIConfig) -> None:
        self._config = config

    def validate_payload(self, payload: WebhookPayload) -> bool:
        """Validate a webhook payload."""
        if not payload.event:
            raise FizzCIWebhookPayloadError("Missing event type")
        if payload.event not in WEBHOOK_EVENTS:
            raise FizzCIWebhookPayloadError(f"Unknown event type: {payload.event}")

        # Verify signature if webhook secret is configured
        if self._config.webhook_secret and payload.signature:
            expected = hmac.new(
                self._config.webhook_secret.encode(),
                json.dumps({"event": payload.event, "ref": payload.ref}).encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, payload.signature):
                raise FizzCIWebhookError("Invalid webhook signature")

        return True

    def should_trigger(self, pipeline: PipelineDefinition,
                       payload: WebhookPayload) -> bool:
        """Determine if a pipeline should be triggered by this event."""
        try:
            trigger_type = TriggerType(payload.event)
        except ValueError:
            return False
        return trigger_type in pipeline.triggers

    def build_context(self, payload: WebhookPayload) -> Dict[str, Any]:
        """Build execution context from a webhook payload."""
        return {
            "event": payload.event,
            "ref": payload.ref,
            "branch": payload.branch or "main",
            "commit_sha": payload.commit_sha or uuid.uuid4().hex[:8],
            "author": payload.author,
            "message": payload.message,
            "paths_changed": payload.paths_changed,
        }


# ============================================================
# Status Reporter
# ============================================================


class StatusReporter:
    """Tracks and reports pipeline execution status.

    Provides status summaries for pipelines, stages, and jobs
    with duration tracking and outcome classification.
    """

    def format_run_status(self, run: PipelineRun) -> str:
        """Format a pipeline run status summary."""
        status_icon = {
            PipelineStatus.SUCCESS: "PASS",
            PipelineStatus.FAILED: "FAIL",
            PipelineStatus.RUNNING: "RUNNING",
            PipelineStatus.PENDING: "PENDING",
            PipelineStatus.CANCELLED: "CANCELLED",
            PipelineStatus.SKIPPED: "SKIPPED",
        }
        icon = status_icon.get(run.status, "?")

        lines = [
            f"Pipeline: {run.pipeline_name} [{icon}]",
            f"  Run ID:    {run.run_id}",
            f"  Branch:    {run.branch}",
            f"  Commit:    {run.commit_sha}",
            f"  Trigger:   {run.trigger.value}",
            f"  Duration:  {run.duration_ms:.0f}ms",
            f"  Started:   {run.started_at.strftime('%Y-%m-%d %H:%M:%S') if run.started_at else 'N/A'}",
        ]

        for sr in run.stage_results:
            stage_icon = "PASS" if sr.status == StageStatus.SUCCESS else "FAIL" if sr.status == StageStatus.FAILED else sr.status.name
            lines.append(f"  Stage: {sr.name} [{stage_icon}] ({sr.duration_ms:.0f}ms)")
            for jr in sr.job_results:
                job_icon = "PASS" if jr.status == JobStatus.SUCCESS else "FAIL" if jr.status == JobStatus.FAILED else jr.status.name
                retry_info = f" (retries: {jr.retry_count})" if jr.retry_count > 0 else ""
                lines.append(f"    Job: {jr.name} [{job_icon}] ({jr.duration_ms:.0f}ms){retry_info}")

        return "\n".join(lines)

    def format_summary(self, runs: List[PipelineRun]) -> str:
        """Format a summary of multiple pipeline runs."""
        total = len(runs)
        success = sum(1 for r in runs if r.status == PipelineStatus.SUCCESS)
        failed = sum(1 for r in runs if r.status == PipelineStatus.FAILED)
        lines = [
            f"Pipeline History: {total} runs ({success} passed, {failed} failed)",
        ]
        for run in runs[-10:]:  # Show last 10
            icon = "PASS" if run.status == PipelineStatus.SUCCESS else "FAIL"
            lines.append(
                f"  {run.run_id} | {run.pipeline_name:<20} | {icon:<4} | {run.duration_ms:.0f}ms | {run.branch}"
            )
        return "\n".join(lines)


# ============================================================
# Pipeline History
# ============================================================


class PipelineHistory:
    """In-memory pipeline execution history store."""

    def __init__(self, config: FizzCIConfig) -> None:
        self._config = config
        self._runs: OrderedDict[str, PipelineRun] = OrderedDict()

    def record(self, run: PipelineRun) -> None:
        """Record a pipeline run."""
        self._runs[run.run_id] = run
        # Trim to max
        while len(self._runs) > self._config.history_max_runs:
            self._runs.popitem(last=False)

    def get_run(self, run_id: str) -> Optional[PipelineRun]:
        """Retrieve a run by ID."""
        return self._runs.get(run_id)

    def get_all(self) -> List[PipelineRun]:
        """Retrieve all recorded runs."""
        return list(self._runs.values())

    def get_by_pipeline(self, pipeline_name: str) -> List[PipelineRun]:
        """Retrieve runs for a specific pipeline."""
        return [r for r in self._runs.values() if r.pipeline_name == pipeline_name]

    def get_latest(self, pipeline_name: str = "") -> Optional[PipelineRun]:
        """Get the most recent run, optionally filtered by pipeline."""
        runs = self.get_by_pipeline(pipeline_name) if pipeline_name else self.get_all()
        return runs[-1] if runs else None

    @property
    def count(self) -> int:
        """Number of recorded runs."""
        return len(self._runs)


# ============================================================
# Pipeline Template Engine
# ============================================================


class PipelineTemplateEngine:
    """Reusable pipeline workflow templates.

    Templates define common pipeline patterns that can be referenced
    and customized in pipeline definitions.
    """

    def __init__(self) -> None:
        self._templates: Dict[str, Dict[str, Any]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in pipeline templates."""
        self._templates["python-ci"] = {
            "name": "Python CI Template",
            "description": "Standard Python CI pipeline with lint, test, and build stages",
            "stages": [
                {
                    "name": "lint",
                    "jobs": [{"name": "pylint", "steps": [
                        {"name": "checkout", "run": "checkout"},
                        {"name": "install", "run": "pip install -r requirements.txt"},
                        {"name": "lint", "run": "lint src/"},
                    ]}],
                },
                {
                    "name": "test",
                    "depends_on": ["lint"],
                    "jobs": [{"name": "pytest", "steps": [
                        {"name": "checkout", "run": "checkout"},
                        {"name": "install", "run": "pip install -r requirements.txt"},
                        {"name": "test", "run": "pytest tests/ -v"},
                    ], "artifacts": {"name": "test-results", "paths": ["test-results/"]}}],
                },
                {
                    "name": "build",
                    "depends_on": ["test"],
                    "jobs": [{"name": "package", "steps": [
                        {"name": "checkout", "run": "checkout"},
                        {"name": "build", "run": "build dist/"},
                    ], "artifacts": {"name": "dist", "paths": ["dist/"]}}],
                },
            ],
        }

        self._templates["docker-build"] = {
            "name": "Docker Build Template",
            "description": "Build and push container images",
            "stages": [
                {
                    "name": "build",
                    "jobs": [{"name": "docker-build", "steps": [
                        {"name": "checkout", "run": "checkout"},
                        {"name": "build", "run": "build -t fizzbuzz/app:latest ."},
                    ]}],
                },
                {
                    "name": "push",
                    "depends_on": ["build"],
                    "jobs": [{"name": "docker-push", "steps": [
                        {"name": "publish", "run": "publish fizzbuzz/app:latest"},
                    ], "secrets": ["REGISTRY_PASSWORD"]}],
                },
            ],
        }

        self._templates["deploy"] = {
            "name": "Deployment Template",
            "description": "Deploy to staging and production with manual gate",
            "stages": [
                {
                    "name": "staging",
                    "jobs": [{"name": "deploy-staging", "steps": [
                        {"name": "deploy", "run": "deploy --env staging"},
                        {"name": "test", "run": "test --smoke --env staging"},
                    ]}],
                },
                {
                    "name": "production",
                    "depends_on": ["staging"],
                    "condition": "manual",
                    "jobs": [{"name": "deploy-prod", "steps": [
                        {"name": "deploy", "run": "deploy --env production"},
                        {"name": "notify", "run": "notify --channel ops"},
                    ], "secrets": ["DEPLOY_TOKEN", "SLACK_WEBHOOK"]}],
                },
            ],
        }

    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a template by name."""
        return self._templates.get(name)

    def list_templates(self) -> List[str]:
        """List available template names."""
        return sorted(self._templates.keys())

    def apply_template(self, template_name: str,
                       overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Apply a template with optional overrides to create a pipeline definition."""
        template = self._templates.get(template_name)
        if template is None:
            raise FizzCITemplateNotFoundError(template_name)

        definition = copy.deepcopy(template)
        if overrides:
            definition.update(overrides)

        return definition


# ============================================================
# Pipeline Visualizer
# ============================================================


class PipelineVisualizer:
    """ASCII DAG rendering for pipeline visualization.

    Renders pipeline stage dependencies as a text-based directed
    graph for terminal display.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._width = width

    def render_dag(self, pipeline: PipelineDefinition) -> str:
        """Render a pipeline's stage DAG as ASCII art."""
        if not pipeline.stages:
            return "  (empty pipeline)"

        dag = DAGBuilder()
        levels = dag.build(pipeline.stages)

        lines = [
            f"  Pipeline: {pipeline.name}",
            f"  {'=' * (self._width - 4)}",
        ]

        for level_idx, level in enumerate(levels):
            stage_names = [s.name for s in level]
            stage_str = "  |  ".join(f"[{n}]" for n in stage_names)
            lines.append(f"  {stage_str}")

            if level_idx < len(levels) - 1:
                # Draw connection arrows
                next_names = [s.name for s in levels[level_idx + 1]]
                arrow = "  " + "  |  " * len(stage_names)
                lines.append(arrow.rstrip())
                lines.append("  " + "  v  " * min(len(stage_names), len(next_names)))

        lines.append(f"  {'=' * (self._width - 4)}")
        return "\n".join(lines)

    def render_run_dag(self, run: PipelineRun) -> str:
        """Render a pipeline run's DAG with status indicators."""
        if not run.stage_results:
            return "  (no stages executed)"

        lines = [
            f"  Run: {run.run_id} ({run.status.name})",
            f"  {'─' * (self._width - 4)}",
        ]

        for sr in run.stage_results:
            icon = self._status_icon(sr.status)
            jobs_str = ", ".join(
                f"{jr.name}:{self._job_status_icon(jr.status)}"
                for jr in sr.job_results
            )
            lines.append(f"  {icon} {sr.name}: {jobs_str}")

        return "\n".join(lines)

    def _status_icon(self, status: StageStatus) -> str:
        """Get status icon for a stage."""
        return {
            StageStatus.SUCCESS: "[PASS]",
            StageStatus.FAILED: "[FAIL]",
            StageStatus.RUNNING: "[....]",
            StageStatus.PENDING: "[    ]",
            StageStatus.SKIPPED: "[SKIP]",
            StageStatus.CANCELLED: "[CNCL]",
        }.get(status, "[????]")

    def _job_status_icon(self, status: JobStatus) -> str:
        """Get status icon for a job."""
        return {
            JobStatus.SUCCESS: "OK",
            JobStatus.FAILED: "FAIL",
            JobStatus.RUNNING: "...",
            JobStatus.PENDING: "---",
            JobStatus.SKIPPED: "SKIP",
        }.get(status, "?")


# ============================================================
# Pipeline Engine (Top-Level Coordinator)
# ============================================================


class PipelineEngine:
    """Top-level CI pipeline engine coordinator.

    Manages pipeline definitions, template resolution, webhook
    handling, and execution orchestration.
    """

    def __init__(self, config: FizzCIConfig,
                 executor: PipelineExecutor,
                 parser: PipelineParser,
                 webhook_handler: WebhookTriggerHandler,
                 template_engine: PipelineTemplateEngine,
                 history: PipelineHistory,
                 visualizer: PipelineVisualizer,
                 metrics: EngineMetrics) -> None:
        self._config = config
        self._executor = executor
        self._parser = parser
        self._webhook = webhook_handler
        self._templates = template_engine
        self._history = history
        self._visualizer = visualizer
        self._metrics = metrics
        self._pipelines: Dict[str, PipelineDefinition] = {}
        self._started = False
        self._start_time = 0.0

    def start(self) -> None:
        """Start the pipeline engine."""
        self._started = True
        self._start_time = time.time()
        logger.info("FizzCI pipeline engine started")

    def register_pipeline(self, definition: Dict[str, Any]) -> PipelineDefinition:
        """Register a pipeline definition."""
        pipeline = self._parser.parse(definition)
        self._pipelines[pipeline.name] = pipeline
        logger.info("Pipeline registered: %s (%d stages)", pipeline.name, len(pipeline.stages))
        return pipeline

    def run_pipeline(self, name: str,
                     trigger: TriggerType = TriggerType.MANUAL,
                     context: Optional[Dict[str, Any]] = None) -> PipelineRun:
        """Execute a registered pipeline."""
        pipeline = self._pipelines.get(name)
        if pipeline is None:
            raise FizzCIError(f"Pipeline not found: {name}")

        run = self._executor.execute(pipeline, trigger, context)
        self._history.record(run)
        self._update_metrics(run)

        return run

    def trigger_webhook(self, payload: WebhookPayload) -> List[PipelineRun]:
        """Process a webhook and trigger matching pipelines."""
        self._webhook.validate_payload(payload)
        context = self._webhook.build_context(payload)
        runs = []

        for pipeline in self._pipelines.values():
            if self._webhook.should_trigger(pipeline, payload):
                run = self._executor.execute(
                    pipeline, TriggerType(payload.event), context
                )
                self._history.record(run)
                self._update_metrics(run)
                runs.append(run)

        return runs

    def get_pipeline(self, name: str) -> Optional[PipelineDefinition]:
        """Retrieve a registered pipeline definition."""
        return self._pipelines.get(name)

    def list_pipelines(self) -> List[str]:
        """List registered pipeline names."""
        return sorted(self._pipelines.keys())

    def _update_metrics(self, run: PipelineRun) -> None:
        """Update engine metrics from a pipeline run."""
        self._metrics.total_runs += 1
        self._metrics.total_duration_ms += run.duration_ms
        if run.status == PipelineStatus.SUCCESS:
            self._metrics.successful_runs += 1
        elif run.status == PipelineStatus.FAILED:
            self._metrics.failed_runs += 1

        for sr in run.stage_results:
            for jr in sr.job_results:
                self._metrics.total_jobs += 1
                if jr.status == JobStatus.SUCCESS:
                    self._metrics.successful_jobs += 1
                elif jr.status == JobStatus.FAILED:
                    self._metrics.failed_jobs += 1
                self._metrics.total_steps += len(jr.step_results)
                self._metrics.retries_performed += jr.retry_count

    def get_metrics(self) -> EngineMetrics:
        """Return current engine metrics."""
        return copy.copy(self._metrics)

    @property
    def uptime(self) -> float:
        """Engine uptime in seconds."""
        return time.time() - self._start_time if self._started else 0.0

    @property
    def is_running(self) -> bool:
        """Whether the engine is running."""
        return self._started


# ============================================================
# Dashboard
# ============================================================


class FizzCIDashboard:
    """ASCII dashboard for FizzCI pipeline engine status display."""

    def __init__(self, engine: PipelineEngine, artifact_manager: ArtifactManager,
                 build_cache: BuildCache, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._artifacts = artifact_manager
        self._cache = build_cache
        self._width = width

    def render(self) -> str:
        """Render the complete FizzCI dashboard."""
        sections = [
            self._render_header(),
            self._render_engine_status(),
            self._render_pipelines(),
            self._render_cache_status(),
            self._render_artifact_status(),
            self._render_recent_runs(),
        ]
        return "\n".join(sections)

    def _render_header(self) -> str:
        line = "=" * self._width
        title = "FizzCI Pipeline Engine Dashboard".center(self._width)
        return f"{line}\n{title}\n{line}"

    def _render_engine_status(self) -> str:
        m = self._engine.get_metrics()
        return "\n".join([
            f"  Engine ({FIZZCI_VERSION})",
            f"  {'─' * (self._width - 4)}",
            f"  Status:        {'RUNNING' if self._engine.is_running else 'STOPPED'}",
            f"  Uptime:        {self._engine.uptime:.1f}s",
            f"  Total Runs:    {m.total_runs}",
            f"  Successful:    {m.successful_runs}",
            f"  Failed:        {m.failed_runs}",
            f"  Total Jobs:    {m.total_jobs}",
            f"  Total Steps:   {m.total_steps}",
            f"  Retries:       {m.retries_performed}",
        ])

    def _render_pipelines(self) -> str:
        names = self._engine.list_pipelines()
        lines = [
            f"  Registered Pipelines ({len(names)})",
            f"  {'─' * (self._width - 4)}",
        ]
        for name in names:
            pipeline = self._engine.get_pipeline(name)
            if pipeline:
                triggers = ", ".join(t.value for t in pipeline.triggers)
                stages = len(pipeline.stages)
                lines.append(f"  {name:<30} {stages} stages  triggers: {triggers}")
        return "\n".join(lines)

    def _render_cache_status(self) -> str:
        stats = self._cache.get_stats()
        return "\n".join([
            f"  Build Cache",
            f"  {'─' * (self._width - 4)}",
            f"  Entries:       {stats['entries']}",
            f"  Size:          {stats['total_size']} / {stats['max_size']} bytes",
            f"  Hit Rate:      {stats['hit_rate']}",
        ])

    def _render_artifact_status(self) -> str:
        return "\n".join([
            f"  Artifacts",
            f"  {'─' * (self._width - 4)}",
            f"  Stored:        {self._artifacts.count}",
            f"  Total Size:    {self._artifacts.total_size} bytes",
        ])

    def _render_recent_runs(self) -> str:
        runs = self._engine._history.get_all()[-5:]
        lines = [
            f"  Recent Runs",
            f"  {'─' * (self._width - 4)}",
        ]
        if not runs:
            lines.append("  (no runs recorded)")
        for run in reversed(runs):
            icon = "PASS" if run.status == PipelineStatus.SUCCESS else "FAIL"
            lines.append(
                f"  {run.run_id} {run.pipeline_name:<20} {icon:<4} {run.duration_ms:.0f}ms"
            )
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================


class FizzCIMiddleware(IMiddleware):
    """Middleware integration for the FizzCI pipeline engine."""

    def __init__(self, engine: PipelineEngine, dashboard: FizzCIDashboard,
                 artifact_manager: ArtifactManager, build_cache: BuildCache,
                 config: FizzCIConfig) -> None:
        self._engine = engine
        self._dashboard = dashboard
        self._artifacts = artifact_manager
        self._cache = build_cache
        self._config = config

    def get_name(self) -> str:
        return "fizzci"

    def process(self, context: ProcessingContext, next_handler: Any) -> ProcessingContext:
        m = self._engine.get_metrics()
        context.metadata["fizzci_version"] = FIZZCI_VERSION
        context.metadata["fizzci_running"] = self._engine.is_running
        context.metadata["fizzci_total_runs"] = m.total_runs
        context.metadata["fizzci_successful_runs"] = m.successful_runs
        context.metadata["fizzci_failed_runs"] = m.failed_runs
        context.metadata["fizzci_total_jobs"] = m.total_jobs

        if next_handler is not None:
            return next_handler(context)
        return context

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def render_dashboard(self) -> str:
        return self._dashboard.render()

    def render_status(self) -> str:
        m = self._engine.get_metrics()
        latest = self._engine._history.get_latest()
        latest_str = f"Last: {latest.pipeline_name} [{latest.status.name}]" if latest else "No runs"
        return (
            f"FizzCI {FIZZCI_VERSION} | "
            f"{'UP' if self._engine.is_running else 'DOWN'} | "
            f"Runs: {m.total_runs} ({m.successful_runs} OK, {m.failed_runs} FAIL) | "
            f"{latest_str}"
        )

    def render_pipelines(self) -> str:
        names = self._engine.list_pipelines()
        lines = [
            "=" * self._config.dashboard_width,
            "FizzCI Registered Pipelines".center(self._config.dashboard_width),
            "=" * self._config.dashboard_width,
        ]
        visualizer = PipelineVisualizer(self._config.dashboard_width)
        for name in names:
            pipeline = self._engine.get_pipeline(name)
            if pipeline:
                lines.append(f"\n{visualizer.render_dag(pipeline)}")
        return "\n".join(lines)

    def render_run_result(self, pipeline_name: str) -> str:
        try:
            run = self._engine.run_pipeline(pipeline_name)
            reporter = StatusReporter()
            return reporter.format_run_status(run)
        except FizzCIError as e:
            return f"Error: {e}"

    def render_trigger_result(self, event: str) -> str:
        payload = WebhookPayload(
            event=event,
            ref=f"refs/heads/main",
            branch="main",
            commit_sha=uuid.uuid4().hex[:8],
            author="fizzbuzz-ci",
            message="Triggered by CLI",
            timestamp=time.time(),
        )
        try:
            runs = self._engine.trigger_webhook(payload)
            if not runs:
                return f"No pipelines matched trigger event: {event}"
            reporter = StatusReporter()
            return "\n\n".join(reporter.format_run_status(r) for r in runs)
        except FizzCIError as e:
            return f"Error: {e}"

    def render_logs(self, spec: str) -> str:
        parts = spec.split("/", 1)
        run_id = parts[0]
        run = self._engine._history.get_run(run_id)
        if run is None:
            return f"Run not found: {run_id}"
        lines = [f"Logs for run {run_id}:"]
        for sr in run.stage_results:
            for jr in sr.job_results:
                if len(parts) > 1 and parts[1] != jr.name:
                    continue
                lines.append(f"\n--- {jr.name} ---")
                lines.extend(jr.log_lines)
        return "\n".join(lines)

    def render_artifacts(self) -> str:
        artifacts = self._artifacts.list_all()
        lines = [
            "=" * self._config.dashboard_width,
            "FizzCI Artifacts".center(self._config.dashboard_width),
            "=" * self._config.dashboard_width,
        ]
        if not artifacts:
            lines.append("  (no artifacts stored)")
        for art in artifacts:
            lines.append(
                f"  {art.name:<25} {art.size:>8} bytes  {art.pipeline_name}/{art.run_id}/{art.job_name}"
            )
        lines.append(f"\n  Total: {self._artifacts.count} artifacts, {self._artifacts.total_size} bytes")
        return "\n".join(lines)

    def render_history(self) -> str:
        runs = self._engine._history.get_all()
        reporter = StatusReporter()
        return reporter.format_summary(runs)

    def render_cache_clear(self) -> str:
        count = self._cache.clear()
        return f"Build cache cleared: {count} entries removed"

    def render_matrix_preview(self, pipeline_name: str) -> str:
        pipeline = self._engine.get_pipeline(pipeline_name)
        if pipeline is None:
            return f"Pipeline not found: {pipeline_name}"
        expander = MatrixExpander()
        lines = [f"Matrix preview for {pipeline_name}:"]
        for stage in pipeline.stages:
            for job in stage.jobs:
                if job.matrix:
                    combos = expander.preview(job)
                    lines.append(f"\n  Job: {job.name} ({len(combos)} combinations)")
                    for combo in combos:
                        lines.append(f"    {combo}")
        return "\n".join(lines)

    def render_dry_run(self, pipeline_name: str) -> str:
        pipeline = self._engine.get_pipeline(pipeline_name)
        if pipeline is None:
            return f"Pipeline not found: {pipeline_name}"
        visualizer = PipelineVisualizer(self._config.dashboard_width)
        lines = [
            f"Dry run: {pipeline_name}",
            visualizer.render_dag(pipeline),
            f"\nStages: {len(pipeline.stages)}",
        ]
        total_jobs = sum(len(s.jobs) for s in pipeline.stages)
        lines.append(f"Jobs: {total_jobs}")
        total_steps = sum(len(j.steps) for s in pipeline.stages for j in s.jobs)
        lines.append(f"Steps: {total_steps}")
        return "\n".join(lines)

    def render_template(self, template_name: str) -> str:
        template = self._engine._templates.get_template(template_name)
        if template is None:
            return f"Template not found: {template_name}\nAvailable: {', '.join(self._engine._templates.list_templates())}"
        return json.dumps(template, indent=2)


# ============================================================
# Factory Function
# ============================================================


def create_fizzci_subsystem(
    max_parallel_jobs: int = DEFAULT_MAX_PARALLEL_JOBS,
    job_timeout: float = DEFAULT_JOB_TIMEOUT,
    step_timeout: float = DEFAULT_STEP_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    artifact_max_size: int = DEFAULT_ARTIFACT_MAX_SIZE,
    cache_max_size: int = DEFAULT_CACHE_MAX_SIZE,
    log_buffer_size: int = DEFAULT_LOG_BUFFER_SIZE,
    history_max_runs: int = DEFAULT_HISTORY_MAX_RUNS,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[PipelineEngine, FizzCIDashboard, FizzCIMiddleware]:
    """Factory function for creating the FizzCI subsystem.

    Constructs a fully wired pipeline engine with parser, DAG builder,
    matrix expander, conditional evaluator, secret injector, artifact
    manager, build cache, log streamer, webhook handler, template engine,
    and pipeline history.  Registers default pipelines for the Enterprise
    FizzBuzz Platform.
    """
    config = FizzCIConfig(
        max_parallel_jobs=max_parallel_jobs,
        job_timeout=job_timeout,
        step_timeout=step_timeout,
        max_retries=max_retries,
        artifact_max_size=artifact_max_size,
        cache_max_size=cache_max_size,
        log_buffer_size=log_buffer_size,
        history_max_runs=history_max_runs,
        dashboard_width=dashboard_width,
    )

    # Core components
    artifact_manager = ArtifactManager(config)
    build_cache = BuildCache(config)
    secret_injector = SecretInjector()
    log_streamer = LogStreamer(config)

    # Execution components
    step_executor = StepExecutor(config, secret_injector, log_streamer)
    job_runner = JobRunner(config, step_executor, artifact_manager, build_cache, log_streamer)
    dag_builder = DAGBuilder()
    matrix_expander = MatrixExpander()
    conditional_evaluator = ConditionalEvaluator()

    pipeline_executor = PipelineExecutor(
        config, job_runner, dag_builder, matrix_expander,
        conditional_evaluator, secret_injector, log_streamer,
    )

    # Management components
    parser = PipelineParser()
    webhook_handler = WebhookTriggerHandler(config)
    template_engine = PipelineTemplateEngine()
    history = PipelineHistory(config)
    visualizer = PipelineVisualizer(dashboard_width)
    metrics = EngineMetrics()

    # Engine
    engine = PipelineEngine(
        config, pipeline_executor, parser, webhook_handler,
        template_engine, history, visualizer, metrics,
    )

    # Dashboard and middleware
    dashboard = FizzCIDashboard(engine, artifact_manager, build_cache, dashboard_width)
    middleware = FizzCIMiddleware(engine, dashboard, artifact_manager, build_cache, config)

    # Start engine
    engine.start()

    # Register default pipelines
    engine.register_pipeline({
        "name": "fizzbuzz-ci",
        "on": ["push", "pull_request"],
        "variables": {"PYTHON_VERSION": "3.13", "PROJECT": "enterprise-fizzbuzz"},
        "stages": [
            {
                "name": "lint",
                "jobs": [{
                    "name": "lint",
                    "image": "fizzbuzz/ci-runner:latest",
                    "steps": [
                        {"name": "checkout", "run": "checkout"},
                        {"name": "install-deps", "run": "pip install -r requirements.txt"},
                        {"name": "lint", "run": "lint enterprise_fizzbuzz/"},
                    ],
                    "cache_key": "pip-deps-v1",
                    "cache_paths": [".pip-cache/"],
                }],
            },
            {
                "name": "test",
                "depends_on": ["lint"],
                "jobs": [{
                    "name": "pytest",
                    "steps": [
                        {"name": "checkout", "run": "checkout"},
                        {"name": "install-deps", "run": "pip install -r requirements.txt"},
                        {"name": "run-tests", "run": "pytest tests/ -v --tb=short"},
                    ],
                    "artifacts": {"name": "test-results", "paths": ["test-results/", "coverage/"]},
                    "retry": {"max_attempts": 2, "strategy": "fixed", "delay": 5.0},
                    "matrix": {
                        "parameters": {
                            "python": ["3.11", "3.12", "3.13"],
                        },
                    },
                }],
            },
            {
                "name": "build",
                "depends_on": ["test"],
                "jobs": [{
                    "name": "package",
                    "steps": [
                        {"name": "checkout", "run": "checkout"},
                        {"name": "build", "run": "build dist/enterprise_fizzbuzz-1.0.0.tar.gz"},
                        {"name": "package", "run": "package --format wheel"},
                    ],
                    "artifacts": {"name": "dist", "paths": ["dist/"]},
                }],
            },
        ],
    })

    engine.register_pipeline({
        "name": "fizzbuzz-deploy",
        "on": ["manual", "tag"],
        "variables": {"DEPLOY_ENV": "production"},
        "stages": [
            {
                "name": "validate",
                "jobs": [{
                    "name": "validate-artifacts",
                    "steps": [
                        {"name": "checkout", "run": "checkout"},
                        {"name": "test", "run": "pytest tests/ --smoke"},
                    ],
                }],
            },
            {
                "name": "deploy",
                "depends_on": ["validate"],
                "jobs": [{
                    "name": "deploy-production",
                    "steps": [
                        {"name": "deploy", "run": "deploy --env production"},
                        {"name": "notify", "run": "notify --channel ops --message 'Deployment complete'"},
                    ],
                    "secrets": ["DEPLOY_TOKEN", "SLACK_WEBHOOK"],
                }],
            },
        ],
    })

    engine.register_pipeline({
        "name": "fizzbuzz-nightly",
        "on": ["schedule"],
        "stages": [
            {
                "name": "full-suite",
                "jobs": [{
                    "name": "nightly-tests",
                    "steps": [
                        {"name": "checkout", "run": "checkout"},
                        {"name": "install", "run": "pip install -r requirements.txt"},
                        {"name": "test", "run": "pytest tests/ -v --all"},
                    ],
                    "timeout": 7200.0,
                }],
            },
        ],
    })

    logger.info(
        "FizzCI subsystem initialized: %d pipelines, %d templates",
        len(engine.list_pipelines()), len(template_engine.list_templates()),
    )

    return engine, dashboard, middleware
