"""
Enterprise FizzBuzz Platform - FizzCI Pipeline Engine Errors (EFP-CI00 .. EFP-CI34)

Exception hierarchy for the FizzCI continuous integration pipeline engine.
Covers YAML pipeline parsing, DAG construction and cycle detection, stage
and job execution, step command processing, artifact storage, build caching,
secret injection, conditional evaluation, branch and path filtering, matrix
expansion, retry policies, webhook triggers, pipeline templates, log
streaming, status reporting, pipeline history, and DAG visualization.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzCIError(FizzBuzzError):
    """Base exception for all FizzCI pipeline engine errors.

    FizzCI is the platform's continuous integration engine that parses
    declarative YAML pipeline definitions, constructs a directed acyclic
    graph of stages, jobs, and steps, and orchestrates their execution
    with full artifact, caching, and secret management.  All CI-specific
    failures inherit from this class to enable categorical error handling
    in the middleware pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzCI error: {reason}",
            error_code="EFP-CI00",
            context={"reason": reason},
        )


class FizzCIPipelineParseError(FizzCIError):
    """Raised when YAML pipeline parsing fails.

    Covers malformed YAML syntax, invalid encoding, and deserialization
    errors encountered while loading pipeline definition files.
    """

    def __init__(self, file: str, reason: str) -> None:
        super().__init__(f"Pipeline parse error in '{file}': {reason}")
        self.error_code = "EFP-CI01"
        self.context = {"file": file, "reason": reason}


class FizzCIPipelineSyntaxError(FizzCIError):
    """Raised when a pipeline definition has invalid structure.

    Covers missing required fields, invalid field types, unrecognized
    keys, and schema validation failures in the pipeline definition.
    """

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"Pipeline syntax error at '{field}': {reason}")
        self.error_code = "EFP-CI02"
        self.context = {"field": field, "reason": reason}


class FizzCIDAGCycleError(FizzCIError):
    """Raised when a cycle is detected in the stage/job dependency graph.

    The pipeline DAG must be acyclic to guarantee a valid topological
    execution order.  This exception is raised when Kahn's algorithm
    or depth-first traversal detects a back edge in the dependency graph.
    """

    def __init__(self, cycle_path: str) -> None:
        super().__init__(f"Cycle detected in pipeline DAG: {cycle_path}")
        self.error_code = "EFP-CI03"
        self.context = {"cycle_path": cycle_path}


class FizzCIDAGError(FizzCIError):
    """Raised on general DAG construction errors.

    Covers invalid dependency references, disconnected subgraphs,
    and topological sort failures not attributable to cycles.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"DAG construction error: {reason}")
        self.error_code = "EFP-CI04"
        self.context = {"reason": reason}


class FizzCIStageError(FizzCIError):
    """Raised on stage execution failures.

    Covers failures in stage lifecycle management including
    initialization, execution, and teardown phases.
    """

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"Stage '{stage}' failed: {reason}")
        self.error_code = "EFP-CI05"
        self.context = {"stage": stage, "reason": reason}


class FizzCIStageNotFoundError(FizzCIError):
    """Raised when a referenced stage does not exist.

    Stage dependencies and conditional triggers may reference stages
    by name.  This exception is raised when the referenced stage
    is not defined in the pipeline.
    """

    def __init__(self, stage: str) -> None:
        super().__init__(f"Stage not found: '{stage}'")
        self.error_code = "EFP-CI06"
        self.context = {"stage": stage}


class FizzCIJobError(FizzCIError):
    """Raised on job execution failures.

    Covers failures in job lifecycle management including environment
    provisioning, step execution, and resource cleanup.
    """

    def __init__(self, job: str, reason: str) -> None:
        super().__init__(f"Job '{job}' failed: {reason}")
        self.error_code = "EFP-CI07"
        self.context = {"job": job, "reason": reason}


class FizzCIJobTimeoutError(FizzCIError):
    """Raised when a job exceeds its configured timeout.

    Each job has a maximum execution duration.  When the wallclock
    time exceeds this limit, the job is forcibly terminated and
    this exception is raised.
    """

    def __init__(self, job: str, timeout_seconds: int) -> None:
        super().__init__(f"Job '{job}' exceeded timeout of {timeout_seconds}s")
        self.error_code = "EFP-CI08"
        self.context = {"job": job, "timeout_seconds": timeout_seconds}


class FizzCIJobCancelledError(FizzCIError):
    """Raised when a job is cancelled by user action or policy.

    Covers manual cancellation, automatic cancellation due to
    superseding pipeline runs, and cancellation triggered by
    failure policies in dependent jobs.
    """

    def __init__(self, job: str, reason: str) -> None:
        super().__init__(f"Job '{job}' was cancelled: {reason}")
        self.error_code = "EFP-CI09"
        self.context = {"job": job, "reason": reason}


class FizzCIStepError(FizzCIError):
    """Raised on step execution failures.

    Covers failures in individual step execution within a job,
    including environment variable resolution, working directory
    setup, and shell invocation errors.
    """

    def __init__(self, step: str, reason: str) -> None:
        super().__init__(f"Step '{step}' failed: {reason}")
        self.error_code = "EFP-CI10"
        self.context = {"step": step, "reason": reason}


class FizzCIStepCommandError(FizzCIError):
    """Raised when a step command returns a non-zero exit code.

    The CI engine executes each step command in a subprocess and
    monitors its exit code.  A non-zero exit code indicates command
    failure and halts the job unless continue-on-error is enabled.
    """

    def __init__(self, step: str, command: str, exit_code: int) -> None:
        super().__init__(f"Step '{step}' command failed with exit code {exit_code}: {command}")
        self.error_code = "EFP-CI11"
        self.context = {"step": step, "command": command, "exit_code": exit_code}


class FizzCIArtifactError(FizzCIError):
    """Raised on artifact storage or retrieval failures.

    Covers failures in the artifact subsystem including path
    resolution, compression, and backend storage operations.
    """

    def __init__(self, artifact: str, reason: str) -> None:
        super().__init__(f"Artifact error for '{artifact}': {reason}")
        self.error_code = "EFP-CI12"
        self.context = {"artifact": artifact, "reason": reason}


class FizzCIArtifactNotFoundError(FizzCIError):
    """Raised when a referenced artifact does not exist.

    Jobs may declare dependencies on artifacts produced by upstream
    jobs.  This exception is raised when the expected artifact is
    not found in the artifact store.
    """

    def __init__(self, artifact: str) -> None:
        super().__init__(f"Artifact not found: '{artifact}'")
        self.error_code = "EFP-CI13"
        self.context = {"artifact": artifact}


class FizzCIArtifactUploadError(FizzCIError):
    """Raised when artifact upload to the storage backend fails.

    Covers network errors, authentication failures, and storage
    quota violations during artifact upload operations.
    """

    def __init__(self, artifact: str, reason: str) -> None:
        super().__init__(f"Artifact upload failed for '{artifact}': {reason}")
        self.error_code = "EFP-CI14"
        self.context = {"artifact": artifact, "reason": reason}


class FizzCICacheError(FizzCIError):
    """Raised on build cache operation failures.

    Covers failures in the build cache subsystem including key
    computation, cache storage, and cache restoration operations.
    """

    def __init__(self, key: str, reason: str) -> None:
        super().__init__(f"Cache error for key '{key}': {reason}")
        self.error_code = "EFP-CI15"
        self.context = {"key": key, "reason": reason}


class FizzCICacheMissError(FizzCIError):
    """Raised when a cache key is not found in the build cache.

    The build cache uses content-addressable keys derived from
    dependency lock files and configuration hashes.  A cache miss
    requires a full rebuild of the cached artifact.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"Cache miss for key '{key}'")
        self.error_code = "EFP-CI16"
        self.context = {"key": key}


class FizzCISecretError(FizzCIError):
    """Raised on secret injection failures.

    Covers failures in retrieving secrets from the vault, decryption
    errors, and environment variable injection failures.
    """

    def __init__(self, secret: str, reason: str) -> None:
        super().__init__(f"Secret injection error for '{secret}': {reason}")
        self.error_code = "EFP-CI17"
        self.context = {"secret": secret, "reason": reason}


class FizzCISecretNotFoundError(FizzCIError):
    """Raised when a referenced secret does not exist in the vault.

    Pipeline steps may reference secrets by name for injection into
    the execution environment.  This exception is raised when the
    named secret is not found in the secrets vault.
    """

    def __init__(self, secret: str) -> None:
        super().__init__(f"Secret not found: '{secret}'")
        self.error_code = "EFP-CI18"
        self.context = {"secret": secret}


class FizzCIConditionError(FizzCIError):
    """Raised when conditional expression evaluation fails.

    Covers syntax errors in condition expressions, undefined variable
    references, and type coercion failures during evaluation.
    """

    def __init__(self, condition: str, reason: str) -> None:
        super().__init__(f"Condition evaluation failed for '{condition}': {reason}")
        self.error_code = "EFP-CI19"
        self.context = {"condition": condition, "reason": reason}


class FizzCIBranchFilterError(FizzCIError):
    """Raised when branch filter evaluation fails.

    Covers invalid glob patterns, regex compilation errors, and
    failures in matching the current branch against include/exclude
    filter rules.
    """

    def __init__(self, pattern: str, reason: str) -> None:
        super().__init__(f"Branch filter error for pattern '{pattern}': {reason}")
        self.error_code = "EFP-CI20"
        self.context = {"pattern": pattern, "reason": reason}


class FizzCIPathFilterError(FizzCIError):
    """Raised when path filter evaluation fails.

    Covers invalid path glob patterns, file system traversal errors,
    and failures in matching changed file paths against include/exclude
    filter rules.
    """

    def __init__(self, pattern: str, reason: str) -> None:
        super().__init__(f"Path filter error for pattern '{pattern}': {reason}")
        self.error_code = "EFP-CI21"
        self.context = {"pattern": pattern, "reason": reason}


class FizzCIMatrixError(FizzCIError):
    """Raised on matrix expansion errors.

    Covers invalid matrix dimension definitions, cross-product
    computation failures, and matrix include/exclude rule violations.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Matrix expansion error: {reason}")
        self.error_code = "EFP-CI22"
        self.context = {"reason": reason}


class FizzCIMatrixEmptyError(FizzCIError):
    """Raised when matrix expansion produces zero combinations.

    After applying include and exclude rules, the resulting matrix
    must contain at least one combination.  An empty matrix indicates
    an overly restrictive exclude rule or misconfigured dimensions.
    """

    def __init__(self, matrix_name: str) -> None:
        super().__init__(f"Matrix '{matrix_name}' produced zero combinations")
        self.error_code = "EFP-CI23"
        self.context = {"matrix_name": matrix_name}


class FizzCIRetryError(FizzCIError):
    """Raised on retry policy errors.

    Covers invalid retry configuration, backoff computation failures,
    and errors in the retry decision logic.
    """

    def __init__(self, job: str, reason: str) -> None:
        super().__init__(f"Retry policy error for job '{job}': {reason}")
        self.error_code = "EFP-CI24"
        self.context = {"job": job, "reason": reason}


class FizzCIRetryExhaustedError(FizzCIError):
    """Raised when a job exceeds its maximum retry count.

    After the configured number of retry attempts with the specified
    backoff strategy, the job is declared permanently failed and
    downstream dependents are cancelled.
    """

    def __init__(self, job: str, attempts: int) -> None:
        super().__init__(f"Retry exhausted for job '{job}' after {attempts} attempts")
        self.error_code = "EFP-CI25"
        self.context = {"job": job, "attempts": attempts}


class FizzCIWebhookError(FizzCIError):
    """Raised on webhook trigger errors.

    Covers failures in processing inbound webhook events that
    trigger pipeline executions, including authentication and
    event type validation.
    """

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"Webhook error from '{source}': {reason}")
        self.error_code = "EFP-CI26"
        self.context = {"source": source, "reason": reason}


class FizzCIWebhookPayloadError(FizzCIError):
    """Raised when a webhook payload fails validation.

    Covers missing required fields, invalid JSON structure, and
    HMAC signature verification failures in webhook payloads.
    """

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"Invalid webhook payload from '{source}': {reason}")
        self.error_code = "EFP-CI27"
        self.context = {"source": source, "reason": reason}


class FizzCITemplateError(FizzCIError):
    """Raised on pipeline template errors.

    Covers template parameter resolution failures, recursive template
    inclusion, and template schema validation errors.
    """

    def __init__(self, template: str, reason: str) -> None:
        super().__init__(f"Template error for '{template}': {reason}")
        self.error_code = "EFP-CI28"
        self.context = {"template": template, "reason": reason}


class FizzCITemplateNotFoundError(FizzCIError):
    """Raised when a referenced pipeline template does not exist.

    Pipelines may extend or include reusable templates by name.
    This exception is raised when the referenced template is not
    found in the template registry.
    """

    def __init__(self, template: str) -> None:
        super().__init__(f"Template not found: '{template}'")
        self.error_code = "EFP-CI29"
        self.context = {"template": template}


class FizzCILogError(FizzCIError):
    """Raised on log streaming errors.

    Covers failures in real-time log capture, log storage backend
    errors, and log retrieval failures during and after job execution.
    """

    def __init__(self, job: str, reason: str) -> None:
        super().__init__(f"Log error for job '{job}': {reason}")
        self.error_code = "EFP-CI30"
        self.context = {"job": job, "reason": reason}


class FizzCIStatusError(FizzCIError):
    """Raised on pipeline status reporting errors.

    Covers failures in updating pipeline, stage, and job status
    records, and errors in commit status notification delivery.
    """

    def __init__(self, pipeline_id: str, reason: str) -> None:
        super().__init__(f"Status error for pipeline '{pipeline_id}': {reason}")
        self.error_code = "EFP-CI31"
        self.context = {"pipeline_id": pipeline_id, "reason": reason}


class FizzCIHistoryError(FizzCIError):
    """Raised on pipeline history errors.

    Covers failures in querying, storing, and pruning historical
    pipeline execution records.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Pipeline history error: {reason}")
        self.error_code = "EFP-CI32"
        self.context = {"reason": reason}


class FizzCIVisualizationError(FizzCIError):
    """Raised on DAG visualization errors.

    Covers failures in rendering the pipeline DAG to graphical
    formats, layout computation errors, and output serialization
    failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"DAG visualization error: {reason}")
        self.error_code = "EFP-CI33"
        self.context = {"reason": reason}


class FizzCIConfigError(FizzCIError):
    """Raised on FizzCI configuration errors.

    Covers invalid runner configurations, missing required parameters,
    and conflicting configuration options in the CI engine settings.
    """

    def __init__(self, parameter: str, reason: str) -> None:
        super().__init__(f"Configuration error for '{parameter}': {reason}")
        self.error_code = "EFP-CI34"
        self.context = {"parameter": parameter, "reason": reason}
