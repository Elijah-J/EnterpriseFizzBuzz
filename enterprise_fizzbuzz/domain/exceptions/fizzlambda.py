"""
Enterprise FizzBuzz Platform - FizzLambda Serverless Function Runtime Exceptions (EFP-LAM00 through EFP-LAM39)

The FizzLambda serverless function runtime requires a comprehensive exception
hierarchy to surface failures across function registration, version management,
invocation dispatch, execution environment lifecycle, warm pool operations,
cold start optimization, event trigger processing, dead letter queue management,
retry orchestration, layer composition, auto-scaling, traffic shifting, and
compliance validation.  Each exception carries a unique error code for
operational triage and structured context for downstream telemetry consumers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzLambdaError(FizzBuzzError):
    """Base exception for FizzLambda serverless function runtime errors.

    All exceptions originating from the FizzLambda subsystem inherit from
    this class.  The runtime manages the complete serverless function
    lifecycle: registration, versioning, alias routing, invocation dispatch,
    execution environment management, warm pool operations, cold start
    optimization, event triggers, dead letter queues, retry policies,
    layer composition, auto-scaling, traffic shifting, and compliance
    validation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM00"
        self.context = {"reason": reason}


class FunctionNotFoundError(FizzLambdaError):
    """Raised when a referenced function does not exist in the registry.

    The function registry is the authoritative store for all function
    definitions.  When an invocation, version operation, alias creation,
    or trigger binding references a function name that does not exist
    in the target namespace, this exception is raised to prevent
    phantom function references from propagating through the system.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM01"
        self.context = {"reason": reason}


class FunctionAlreadyExistsError(FizzLambdaError):
    """Raised when creating a function with a name that already exists in the namespace.

    Function names are unique within a namespace.  Duplicate creation
    attempts are rejected to prevent silent overwrites of existing
    function configurations, which could disrupt live invocation routing
    and invalidate published versions.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM02"
        self.context = {"reason": reason}


class FunctionRegistryError(FizzLambdaError):
    """Raised when the function registry encounters a persistence or consistency error.

    The registry enforces optimistic concurrency control on function
    definitions.  When a concurrent modification is detected, or the
    internal state becomes inconsistent, this exception prevents
    corrupted definitions from being served to invocation routers.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM03"
        self.context = {"reason": reason}


class FunctionVersionError(FizzLambdaError):
    """Raised when version operations fail (publish, resolve, or garbage collect).

    Version management creates immutable snapshots of function definitions.
    When the version counter overflows, the snapshot capture fails, or
    garbage collection encounters a referenced version, this exception
    halts the operation to preserve version integrity.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM04"
        self.context = {"reason": reason}


class FunctionVersionNotFoundError(FizzLambdaError):
    """Raised when a referenced version number does not exist for a function.

    Invocation routers and alias managers resolve version numbers to
    immutable definition snapshots.  When the requested version has
    not been published or has been garbage collected, this exception
    prevents execution against a nonexistent code artifact.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM05"
        self.context = {"reason": reason}


class AliasNotFoundError(FizzLambdaError):
    """Raised when a referenced alias does not exist for a function.

    Aliases provide stable invocation endpoints that can be redirected
    to different function versions without changing caller configuration.
    When the specified alias name has not been created or has been
    deleted, this exception signals that the routing path is broken.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM06"
        self.context = {"reason": reason}


class AliasAlreadyExistsError(FizzLambdaError):
    """Raised when creating an alias with a name that already exists.

    Alias names are unique per function.  Duplicate creation is rejected
    to prevent accidental routing changes.  Use the update operation to
    modify an existing alias's version target or traffic weight.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM07"
        self.context = {"reason": reason}


class InvocationError(FizzLambdaError):
    """Raised when a function invocation fails during dispatch or execution.

    Invocation failures may originate from payload validation, environment
    acquisition, handler execution, or response serialization.  This
    exception captures the failure context for retry classification and
    dead letter queue routing.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM08"
        self.context = {"reason": reason}


class InvocationTimeoutError(FizzLambdaError):
    """Raised when a function invocation exceeds its configured timeout.

    Each function defines a maximum execution duration between 1 and
    900 seconds.  When the handler does not return within this window,
    the execution environment is force-terminated and this exception
    is raised to trigger the retry policy evaluation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM09"
        self.context = {"reason": reason}


class InvocationThrottledError(FizzLambdaError):
    """Raised when an invocation is rejected due to concurrency limits.

    The auto-scaler enforces both function-level reserved concurrency
    and account-level concurrency caps.  When all available execution
    slots are occupied and burst scaling is exhausted, this exception
    rejects the invocation with a 429 status code equivalent.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM10"
        self.context = {"reason": reason}


class InvocationPayloadError(FizzLambdaError):
    """Raised when the invocation payload exceeds size limits or fails validation.

    Synchronous invocations are limited to 6 MB payloads; asynchronous
    invocations to 256 KB.  When the payload exceeds these limits or
    cannot be deserialized as valid JSON, this exception prevents
    oversized data from entering the execution pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM11"
        self.context = {"reason": reason}


class ExecutionEnvironmentError(FizzLambdaError):
    """Raised when execution environment creation, reuse, or destruction fails.

    Execution environments are the isolated sandboxes in which function
    code runs.  Failures during cgroup configuration, container creation,
    network namespace setup, or runtime bootstrap trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM12"
        self.context = {"reason": reason}


class ColdStartError(FizzLambdaError):
    """Raised when cold start initialization fails (image resolution, sandbox, bootstrap).

    Cold starts involve a multi-phase initialization sequence: image
    resolution, sandbox creation, cgroup configuration, container
    creation, and runtime bootstrap.  Failure at any phase triggers
    this exception with a breakdown of which phase failed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM13"
        self.context = {"reason": reason}


class WarmPoolError(FizzLambdaError):
    """Raised when warm pool operations fail (acquire, return, eviction).

    The warm pool maintains pre-initialized execution environments
    for low-latency invocations.  When pool operations encounter
    capacity limits, stale environments, or consistency errors,
    this exception surfaces the failure for operational visibility.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM14"
        self.context = {"reason": reason}


class WarmPoolCapacityError(FizzLambdaError):
    """Raised when the warm pool exceeds its maximum environment capacity.

    The warm pool enforces both a global maximum (default: 1,000
    environments) and a per-function maximum (default: 100).  When
    a new environment cannot be added without exceeding these limits,
    this exception triggers LRU eviction or request throttling.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM15"
        self.context = {"reason": reason}


class ColdStartOptimizerError(FizzLambdaError):
    """Raised when cold start optimization operations fail (snapshot, pre-warm, cache).

    The cold start optimizer uses snapshot-and-restore, predictive
    pre-warming, and layer caching to reduce initialization latency.
    When these optimization paths encounter errors, this exception
    falls back to the standard cold start sequence.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM16"
        self.context = {"reason": reason}


class SnapshotCaptureError(FizzLambdaError):
    """Raised when execution environment snapshot capture fails.

    Snapshots freeze the initialized state of an execution environment
    for rapid restoration on subsequent invocations.  When the memory
    state cannot be serialized, the filesystem overlay cannot be
    captured, or the snapshot store is at capacity, this exception
    signals that the optimization path is unavailable.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM17"
        self.context = {"reason": reason}


class SnapshotRestoreError(FizzLambdaError):
    """Raised when execution environment snapshot restore fails.

    Snapshot restoration bypasses the full cold start sequence by
    loading a pre-initialized memory image.  When the snapshot is
    corrupted, the code hash has changed, or the runtime version
    is incompatible, this exception triggers a full cold start fallback.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM18"
        self.context = {"reason": reason}


class TriggerError(FizzLambdaError):
    """Raised when event trigger creation, update, or delivery fails.

    Event triggers bind external event sources to function invocations.
    When trigger configuration is invalid, the event source is
    unreachable, or the delivery pipeline encounters an error,
    this exception prevents misconfigured triggers from silently
    dropping events.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM19"
        self.context = {"reason": reason}


class TriggerNotFoundError(FizzLambdaError):
    """Raised when a referenced trigger does not exist.

    Trigger management operations (enable, disable, delete, fire)
    require a valid trigger ID.  When the specified trigger has not
    been created or has been deleted, this exception prevents
    operations against phantom triggers.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM20"
        self.context = {"reason": reason}


class HTTPTriggerError(FizzLambdaError):
    """Raised when HTTP trigger route registration or request mapping fails.

    HTTP triggers expose functions as HTTP endpoints with configurable
    routes, methods, authentication, and CORS policies.  When route
    registration conflicts with existing routes, or request mapping
    cannot produce a valid invocation event, this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM21"
        self.context = {"reason": reason}


class TimerTriggerError(FizzLambdaError):
    """Raised when timer trigger scheduling or cron expression parsing fails.

    Timer triggers invoke functions on a schedule defined by cron
    expressions or rate expressions.  When the expression cannot be
    parsed, the schedule is invalid, or the next fire time cannot be
    computed, this exception prevents misconfigured schedules from
    being persisted.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM22"
        self.context = {"reason": reason}


class QueueTriggerError(FizzLambdaError):
    """Raised when queue trigger polling, batching, or visibility timeout fails.

    Queue triggers poll message queues and batch messages into
    invocation events.  When polling encounters connectivity issues,
    batching exceeds configured limits, or visibility timeout
    operations fail, this exception surfaces the failure.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM23"
        self.context = {"reason": reason}


class EventBusTriggerError(FizzLambdaError):
    """Raised when event bus trigger pattern matching or delivery fails.

    Event bus triggers filter events using pattern matching rules
    and deliver matching events as function invocation payloads.
    When pattern compilation fails, or event delivery encounters
    serialization errors, this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM24"
        self.context = {"reason": reason}


class DeadLetterQueueError(FizzLambdaError):
    """Raised when DLQ operations fail (send, receive, replay, purge).

    The dead letter queue captures invocations that have exhausted
    all retry attempts.  When DLQ operations encounter capacity
    limits, message corruption, or replay failures, this exception
    provides the operational context for recovery.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM25"
        self.context = {"reason": reason}


class QueueFullError(FizzLambdaError):
    """Raised when a queue reaches its maximum depth and cannot accept new messages.

    Async invocation queues have a configurable depth limit (default:
    100,000 messages).  When the queue is full, new messages are
    rejected to prevent unbounded memory growth and provide
    backpressure to upstream callers.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM26"
        self.context = {"reason": reason}


class QueueMessageNotFoundError(FizzLambdaError):
    """Raised when a referenced queue message does not exist or has expired.

    Queue message operations (delete, change visibility, replay)
    require a valid message ID or receipt handle.  When the message
    has been deleted, has expired, or the receipt handle is stale,
    this exception prevents operations against phantom messages.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM27"
        self.context = {"reason": reason}


class RetryExhaustedError(FizzLambdaError):
    """Raised when all retry attempts for a failed invocation are exhausted.

    The retry manager classifies failures and applies exponential
    backoff retries.  When the maximum retry count is reached and
    the invocation has not succeeded, this exception triggers dead
    letter queue routing for manual investigation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM28"
        self.context = {"reason": reason}


class LayerError(FizzLambdaError):
    """Raised when layer creation, composition, or caching operations fail.

    Layers provide shared dependency packages that can be attached
    to multiple functions.  When layer content is corrupted, composition
    encounters conflicting files, or caching operations fail, this
    exception prevents malformed layers from being used.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM29"
        self.context = {"reason": reason}


class LayerNotFoundError(FizzLambdaError):
    """Raised when a referenced layer does not exist in the layer registry.

    Functions reference layers by name and version.  When the specified
    layer has not been created or the requested version has been deleted,
    this exception prevents function deployment with missing dependencies.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM30"
        self.context = {"reason": reason}


class LayerLimitExceededError(FizzLambdaError):
    """Raised when a function exceeds the maximum number of layers (5) or total size (250 MB).

    Functions may attach up to 5 layers with a combined uncompressed
    size of 250 MB.  These limits ensure that cold start times remain
    bounded and execution environment resource consumption is predictable.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM31"
        self.context = {"reason": reason}


class ResourceAllocationError(FizzLambdaError):
    """Raised when cgroup resource mapping fails for an execution environment.

    The resource allocator translates function memory and CPU
    configurations into cgroup controller settings.  When the
    mapping produces invalid cgroup parameters or the cgroup
    hierarchy cannot be created, this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM32"
        self.context = {"reason": reason}


class FunctionPackagingError(FizzLambdaError):
    """Raised when function image build, FizzFile generation, or layer integration fails.

    The function packager integrates code sources with the FizzImage
    build system.  When inline code exceeds size limits, image
    references are unresolvable, or layer composition produces
    invalid artifacts, this exception prevents deployment of
    broken function packages.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM33"
        self.context = {"reason": reason}


class AutoScalerError(FizzLambdaError):
    """Raised when auto-scaling operations fail (scale-up, throttle, concurrency tracking).

    The auto-scaler manages reactive scaling of execution environments
    based on invocation demand.  When burst scaling exceeds capacity,
    concurrency tracking becomes inconsistent, or environment creation
    fails during scale-up, this exception surfaces the scaling failure.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM34"
        self.context = {"reason": reason}


class TrafficShiftError(FizzLambdaError):
    """Raised when traffic shifting operations fail during alias-based canary or linear deployment.

    Traffic shifting progressively moves invocation traffic from one
    function version to another.  When weight calculations produce
    invalid values, the alias state becomes inconsistent, or the
    rollback path fails, this exception halts the shift operation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM35"
        self.context = {"reason": reason}


class ConcurrencyLimitError(FizzLambdaError):
    """Raised when account-level or function-level concurrency limits are exceeded.

    The platform enforces a hard account-wide concurrency limit
    (default: 1,000 concurrent executions) and optional per-function
    reserved concurrency.  When these limits are reached and no
    burst capacity remains, this exception rejects new invocations.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM36"
        self.context = {"reason": reason}


class FizzLambdaMiddlewareError(FizzLambdaError):
    """Raised when FizzLambda middleware pipeline integration encounters an error.

    The FizzLambda middleware sits in the evaluation pipeline and
    routes evaluations between container and serverless execution
    paths.  When the routing decision fails, response annotation
    encounters an error, or dashboard rendering fails, this exception
    is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM37"
        self.context = {"reason": reason}


class FizzLambdaCognitiveLoadError(FizzLambdaError):
    """Raised when a deployment is blocked by Bob McFizzington's cognitive load threshold.

    The cognitive load gate integrates with FizzBob's NASA-TLX
    assessment model.  When the operator's cognitive load score
    exceeds the configured threshold (default: 65.0), deployments
    are blocked to prevent operator error during high-stress periods.
    Emergency deployments may bypass this gate.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM38"
        self.context = {"reason": reason}


class FizzLambdaComplianceError(FizzLambdaError):
    """Raised when serverless operations violate SOX/GDPR/HIPAA compliance requirements.

    The compliance engine extends the platform's regulatory framework
    to serverless operations.  Deployments without proper audit trails,
    functions processing classified data without VPC isolation, and
    operations by unauthorized personnel trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-LAM39"
        self.context = {"reason": reason}
