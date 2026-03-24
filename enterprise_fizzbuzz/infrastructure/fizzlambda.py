"""
FizzLambda -- Serverless Function Runtime
==========================================

FizzLambda is a serverless function execution runtime modeled after
AWS Lambda's architecture.  It provides the complete function lifecycle:
registration, immutable versioning, alias-based routing with weighted
traffic shifting, synchronous and asynchronous invocation dispatch,
execution environment management with warm pools, cold start optimization
through snapshot-and-restore and predictive pre-warming, event triggers
(HTTP, timer, queue, event bus), dead letter queues with replay,
retry management with exponential backoff, shared dependency layers,
auto-scaling with burst concurrency, and deployment gating through
cognitive load and compliance validation.

The runtime integrates with the platform's container infrastructure:
execution environments are backed by FizzOCI containers with cgroup v2
resource isolation, FizzCNI network namespaces, and FizzOverlay
filesystem layers.  Cold starts follow the AWS Lambda initialization
sequence: image resolution, sandbox creation, cgroup configuration,
container creation, and runtime bootstrap.

Evaluation routing between the container path and the serverless path
is controlled by the ``--fizzlambda-mode`` flag:

- **container** (default): Evaluations bypass FizzLambda entirely
- **serverless**: All evaluations are routed through FizzLambda functions
- **hybrid**: FizzLambda handles evaluations only when a matching
  function trigger fires

The runtime registers seven built-in functions that demonstrate the
full capabilities of the serverless model applied to FizzBuzz evaluation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import random
import struct
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
)

from enterprise_fizzbuzz.domain.events._registry import EventType
from enterprise_fizzbuzz.domain.exceptions.fizzlambda import (
    AliasAlreadyExistsError,
    AliasNotFoundError,
    AutoScalerError,
    ColdStartError,
    ColdStartOptimizerError,
    ConcurrencyLimitError,
    DeadLetterQueueError,
    ExecutionEnvironmentError,
    FizzLambdaCognitiveLoadError,
    FizzLambdaComplianceError,
    FizzLambdaMiddlewareError,
    FunctionAlreadyExistsError,
    FunctionNotFoundError,
    FunctionPackagingError,
    FunctionRegistryError,
    FunctionVersionError,
    FunctionVersionNotFoundError,
    HTTPTriggerError,
    InvocationError,
    InvocationPayloadError,
    InvocationThrottledError,
    InvocationTimeoutError,
    LayerError,
    LayerLimitExceededError,
    LayerNotFoundError,
    QueueFullError,
    QueueMessageNotFoundError,
    QueueTriggerError,
    ResourceAllocationError,
    RetryExhaustedError,
    SnapshotCaptureError,
    SnapshotRestoreError,
    TimerTriggerError,
    TrafficShiftError,
    TriggerError,
    TriggerNotFoundError,
    WarmPoolCapacityError,
    WarmPoolError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import FizzBuzzResult, ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIZZLAMBDA_VERSION = "1.0.0"

DEFAULT_MEMORY_MB = 256
MIN_MEMORY_MB = 128
MAX_MEMORY_MB = 10240
DEFAULT_TIMEOUT_SECONDS = 30
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 900
DEFAULT_EPHEMERAL_STORAGE_MB = 512
MAX_EPHEMERAL_STORAGE_MB = 10240

VCPU_MEMORY_RATIO = 1769
CPU_PERIOD_US = 100000

MAX_PAYLOAD_SYNC_BYTES = 6291456
MAX_PAYLOAD_ASYNC_BYTES = 262144

MAX_LAYERS = 5
MAX_LAYER_TOTAL_MB = 250

MAX_CONCURRENT_ENVIRONMENTS = 1000
MAX_BURST_CONCURRENCY = 500
DEFAULT_IDLE_TIMEOUT = 300.0

DEFAULT_MAX_RECEIVE_COUNT = 3
DEFAULT_VISIBILITY_TIMEOUT = 30.0
DEFAULT_MESSAGE_RETENTION = 1209600
DEFAULT_QUEUE_DEPTH = 100000

DEFAULT_MAX_ENVIRONMENTS = 1000
DEFAULT_MAX_PER_FUNCTION = 100
DEFAULT_RECYCLING_INVOCATIONS = 10000
DEFAULT_RECYCLING_LIFETIME = 14400.0

DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 118
LOG_TAIL_BYTES = 4096
MAX_EXEC_PID_LIMIT = 1024


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FunctionRuntime(Enum):
    """Execution runtime for serverless functions."""
    PYTHON_312 = "python3.12"
    FIZZBYTECODE = "fizzbytecode"
    FIZZLANG = "fizzlang"


class CodeSourceType(Enum):
    """Source type for function code."""
    INLINE = "inline"
    IMAGE = "image"
    LAYER_COMPOSITION = "layer_composition"


class InvocationType(Enum):
    """How the caller wants the invocation handled."""
    REQUEST_RESPONSE = "RequestResponse"
    EVENT = "Event"
    DRY_RUN = "DryRun"


class LogType(Enum):
    """Whether to return log output in the invocation response."""
    NONE = "None"
    TAIL = "Tail"


class EnvironmentState(Enum):
    """Lifecycle state of an execution environment."""
    CREATING = "creating"
    READY = "ready"
    BUSY = "busy"
    FROZEN = "frozen"
    DESTROYING = "destroying"


class TriggerType(Enum):
    """Type of event trigger."""
    HTTP = "http"
    TIMER = "timer"
    QUEUE = "queue"
    EVENT_BUS = "event_bus"


class AuthType(Enum):
    """Authentication type for HTTP triggers."""
    NONE = "none"
    IAM = "iam"
    API_KEY = "api_key"


class DeadLetterTargetType(Enum):
    """Target type for dead letter delivery."""
    QUEUE = "queue"
    EVENT_BUS = "event_bus"


class TrafficShiftStrategy(Enum):
    """Deployment strategy for alias traffic shifting."""
    LINEAR = "linear"
    CANARY = "canary"
    ALL_AT_ONCE = "all_at_once"


class RetryClassification(Enum):
    """Classification of invocation failures for retry decisions."""
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    AMBIGUOUS = "ambiguous"


class FunctionErrorType(Enum):
    """Type of function execution error."""
    HANDLED = "Handled"
    UNHANDLED = "Unhandled"
    TIMEOUT = "Timeout"
    OUT_OF_MEMORY = "OutOfMemory"


class QueueMessageState(Enum):
    """State of a message in a FizzLambda queue."""
    AVAILABLE = "available"
    IN_FLIGHT = "in_flight"
    DEAD = "dead"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CodeSource:
    """Source specification for function code."""
    source_type: CodeSourceType = CodeSourceType.INLINE
    inline_code: str = ""
    image_reference: str = ""
    layer_names: List[str] = field(default_factory=list)


@dataclass
class VPCConfig:
    """FizzCNI network configuration for function execution environments."""
    subnet_ids: List[str] = field(default_factory=list)
    security_group_ids: List[str] = field(default_factory=list)


@dataclass
class ConcurrencyConfig:
    """Concurrency limits for a function."""
    reserved_concurrency: Optional[int] = None
    provisioned_concurrency: int = 0


@dataclass
class DeadLetterConfig:
    """Dead letter queue configuration for failed invocations."""
    target_type: DeadLetterTargetType = DeadLetterTargetType.QUEUE
    target_arn: str = ""


@dataclass
class RetryPolicy:
    """Retry configuration for failed invocations from a trigger."""
    max_retries: int = 2
    retry_delay_seconds: int = 60


@dataclass
class FunctionDefinition:
    """Declarative specification of a serverless function."""
    function_id: str = ""
    name: str = ""
    namespace: str = "default"
    runtime: FunctionRuntime = FunctionRuntime.PYTHON_312
    handler: str = ""
    code_source: CodeSource = field(default_factory=CodeSource)
    memory_mb: int = DEFAULT_MEMORY_MB
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    ephemeral_storage_mb: int = DEFAULT_EPHEMERAL_STORAGE_MB
    environment_variables: Dict[str, str] = field(default_factory=dict)
    vpc_config: Optional[VPCConfig] = None
    concurrency: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)
    dead_letter_config: Optional[DeadLetterConfig] = None
    tags: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 0


@dataclass
class FunctionVersion:
    """Immutable snapshot of a function definition at publication time."""
    function_name: str = ""
    version_number: int = 0
    description: str = ""
    code_sha256: str = ""
    definition_snapshot: FunctionDefinition = field(default_factory=FunctionDefinition)
    published_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FunctionAlias:
    """Named pointer to one or two function versions for deployment routing."""
    alias_name: str = ""
    function_name: str = ""
    function_version: int = 0
    additional_version: Optional[int] = None
    additional_version_weight: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FunctionContext:
    """Runtime context object passed to every function invocation."""
    invocation_id: str = ""
    function_name: str = ""
    function_version: str = ""
    memory_limit_mb: int = DEFAULT_MEMORY_MB
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    start_time: float = field(default_factory=time.time)
    log_group: str = ""
    trace_id: str = ""
    client_context: Dict[str, Any] = field(default_factory=dict)
    identity: Dict[str, Any] = field(default_factory=dict)

    @property
    def timeout_remaining_ms(self) -> int:
        """Return the number of milliseconds remaining before timeout."""
        elapsed = time.time() - self.start_time
        remaining = max(0, self.timeout_seconds - elapsed)
        return int(remaining * 1000)


@dataclass
class InvocationRequest:
    """Wire format for invoking a function."""
    function_name: str = ""
    qualifier: str = "$LATEST"
    invocation_type: InvocationType = InvocationType.REQUEST_RESPONSE
    payload: bytes = b""
    client_context: Dict[str, Any] = field(default_factory=dict)
    log_type: LogType = LogType.NONE


@dataclass
class InvocationMetrics:
    """Metrics collected during a single invocation."""
    duration_ms: float = 0.0
    billed_duration_ms: float = 0.0
    memory_used_mb: float = 0.0
    memory_allocated_mb: float = 0.0
    cold_start: bool = False


@dataclass
class InvocationResponse:
    """Response from a function invocation."""
    status_code: int = 200
    payload: bytes = b""
    function_error: Optional[str] = None
    log_result: Optional[str] = None
    executed_version: str = ""
    metrics: InvocationMetrics = field(default_factory=InvocationMetrics)


@dataclass
class ExecutionEnvironment:
    """Running instance capable of executing function invocations."""
    environment_id: str = ""
    function_id: str = ""
    function_version: str = ""
    state: EnvironmentState = EnvironmentState.CREATING
    container_id: str = ""
    sandbox_id: str = ""
    cgroup_path: str = ""
    network_namespace: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_invocation_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    invocation_count: int = 0
    peak_memory_bytes: int = 0
    is_provisioned: bool = False


@dataclass
class TriggerDefinition:
    """Specification for an event trigger bound to a function."""
    trigger_id: str = ""
    function_name: str = ""
    qualifier: str = "$LATEST"
    trigger_type: TriggerType = TriggerType.HTTP
    trigger_config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    batch_size: int = 1
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class HTTPTriggerConfig:
    """Configuration for an HTTP event trigger."""
    route_path: str = "/api/fizzbuzz"
    http_methods: List[str] = field(default_factory=lambda: ["POST"])
    auth_type: AuthType = AuthType.NONE
    cors_config: Optional[Dict[str, Any]] = None


@dataclass
class TimerTriggerConfig:
    """Configuration for a timer/schedule event trigger."""
    schedule_expression: str = ""
    input_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueueTriggerConfig:
    """Configuration for a queue-based event trigger."""
    queue_name: str = ""
    batch_size: int = 1
    batch_window_seconds: int = 0
    max_concurrency: int = 2


@dataclass
class EventBusTriggerConfig:
    """Configuration for an event bus pattern-matching trigger."""
    event_pattern: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueueMessage:
    """Individual message in a FizzLambda queue."""
    message_id: str = ""
    body: bytes = b""
    attributes: Dict[str, Any] = field(default_factory=dict)
    receipt_handle: str = ""
    state: QueueMessageState = QueueMessageState.AVAILABLE
    receive_count: int = 0
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    first_received_at: Optional[datetime] = None
    visibility_deadline: Optional[datetime] = None


@dataclass
class FunctionLayer:
    """Versioned package of shared dependencies."""
    layer_name: str = ""
    layer_version: int = 1
    description: str = ""
    compatible_runtimes: List[FunctionRuntime] = field(default_factory=list)
    content_ref: str = ""
    content_sha256: str = ""
    size_bytes: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SnapshotRecord:
    """Record of a captured execution environment snapshot."""
    snapshot_id: str = ""
    function_id: str = ""
    function_version: str = ""
    code_hash: str = ""
    image_ref: str = ""
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ColdStartBreakdown:
    """Latency breakdown for a cold start sequence."""
    image_resolution_ms: float = 0.0
    sandbox_creation_ms: float = 0.0
    network_setup_ms: float = 0.0
    container_creation_ms: float = 0.0
    runtime_bootstrap_ms: float = 0.0
    total_ms: float = 0.0
    snapshot_restored: bool = False


@dataclass
class PreWarmPrediction:
    """Predictive pre-warming forecast for a function."""
    function_id: str = ""
    predicted_concurrency: int = 0
    confidence: float = 0.0
    trigger_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TrafficShiftState:
    """Current state of an in-progress traffic shift operation."""
    alias_name: str = ""
    function_name: str = ""
    strategy: TrafficShiftStrategy = TrafficShiftStrategy.LINEAR
    old_version: int = 0
    new_version: int = 0
    current_weight: float = 0.0
    target_weight: float = 1.0
    step_count: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# FunctionRegistry
# ---------------------------------------------------------------------------

class FunctionRegistry:
    """Authoritative store for function definitions.

    Provides CRUD operations with optimistic concurrency control,
    namespace isolation, definition validation, and event emission.
    Functions are identified by their name within a namespace.
    """

    def __init__(self, event_bus: Any = None) -> None:
        self._functions: Dict[str, FunctionDefinition] = {}
        self._event_bus = event_bus
        self._lock = threading.Lock()

    def create_function(self, definition: FunctionDefinition) -> FunctionDefinition:
        """Register a new function definition."""
        self._validate_definition(definition)
        key = f"{definition.namespace}:{definition.name}"
        with self._lock:
            if key in self._functions:
                raise FunctionAlreadyExistsError(
                    f"Function '{definition.name}' already exists in namespace '{definition.namespace}'"
                )
            if not definition.function_id:
                definition.function_id = str(uuid.uuid4())
            definition.created_at = datetime.now(timezone.utc)
            definition.updated_at = datetime.now(timezone.utc)
            definition.version = 1
            self._functions[key] = definition
        self._emit_event(EventType.LAM_FUNCTION_CREATED, {
            "function_name": definition.name,
            "namespace": definition.namespace,
            "runtime": definition.runtime.value,
        })
        logger.info("Function '%s' created in namespace '%s'", definition.name, definition.namespace)
        return definition

    def get_function(self, name: str, namespace: str = "default") -> FunctionDefinition:
        """Retrieve a function definition by name and namespace."""
        key = f"{namespace}:{name}"
        with self._lock:
            if key not in self._functions:
                raise FunctionNotFoundError(
                    f"Function '{name}' not found in namespace '{namespace}'"
                )
            return self._functions[key]

    def update_function(self, name: str, updates: Dict[str, Any],
                        namespace: str = "default") -> FunctionDefinition:
        """Update a function definition with optimistic concurrency control."""
        key = f"{namespace}:{name}"
        with self._lock:
            if key not in self._functions:
                raise FunctionNotFoundError(
                    f"Function '{name}' not found in namespace '{namespace}'"
                )
            definition = self._functions[key]
            expected_version = updates.pop("expected_version", None)
            if expected_version is not None and definition.version != expected_version:
                raise FunctionRegistryError(
                    f"Optimistic concurrency conflict for '{name}': "
                    f"expected version {expected_version}, found {definition.version}"
                )
            for attr, value in updates.items():
                if hasattr(definition, attr):
                    setattr(definition, attr, value)
            definition.version += 1
            definition.updated_at = datetime.now(timezone.utc)
            if "memory_mb" in updates or "timeout_seconds" in updates:
                self._validate_definition(definition)
        self._emit_event(EventType.LAM_FUNCTION_UPDATED, {
            "function_name": name,
            "namespace": namespace,
            "version": definition.version,
        })
        return definition

    def delete_function(self, name: str, namespace: str = "default") -> None:
        """Remove a function from the registry."""
        key = f"{namespace}:{name}"
        with self._lock:
            if key not in self._functions:
                raise FunctionNotFoundError(
                    f"Function '{name}' not found in namespace '{namespace}'"
                )
            del self._functions[key]
        self._emit_event(EventType.LAM_FUNCTION_DELETED, {
            "function_name": name,
            "namespace": namespace,
        })
        logger.info("Function '%s' deleted from namespace '%s'", name, namespace)

    def list_functions(self, namespace: Optional[str] = None) -> List[FunctionDefinition]:
        """List all functions, optionally filtered by namespace."""
        with self._lock:
            if namespace is not None:
                return [
                    f for f in self._functions.values()
                    if f.namespace == namespace
                ]
            return list(self._functions.values())

    def _validate_definition(self, definition: FunctionDefinition) -> None:
        """Validate function definition constraints."""
        if definition.memory_mb < MIN_MEMORY_MB or definition.memory_mb > MAX_MEMORY_MB:
            raise FunctionRegistryError(
                f"Memory {definition.memory_mb} MB is outside valid range "
                f"[{MIN_MEMORY_MB}, {MAX_MEMORY_MB}]"
            )
        if definition.timeout_seconds < MIN_TIMEOUT_SECONDS or definition.timeout_seconds > MAX_TIMEOUT_SECONDS:
            raise FunctionRegistryError(
                f"Timeout {definition.timeout_seconds}s is outside valid range "
                f"[{MIN_TIMEOUT_SECONDS}, {MAX_TIMEOUT_SECONDS}]"
            )
        if definition.ephemeral_storage_mb > MAX_EPHEMERAL_STORAGE_MB:
            raise FunctionRegistryError(
                f"Ephemeral storage {definition.ephemeral_storage_mb} MB exceeds "
                f"maximum {MAX_EPHEMERAL_STORAGE_MB} MB"
            )

    def _validate_concurrency_update(self, definition: FunctionDefinition,
                                      new_concurrency: ConcurrencyConfig) -> None:
        """Validate concurrency configuration changes."""
        if new_concurrency.reserved_concurrency is not None:
            if new_concurrency.reserved_concurrency < 0:
                raise FunctionRegistryError(
                    "Reserved concurrency cannot be negative"
                )
        if new_concurrency.provisioned_concurrency < 0:
            raise FunctionRegistryError(
                "Provisioned concurrency cannot be negative"
            )

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# FunctionVersionManager
# ---------------------------------------------------------------------------

class FunctionVersionManager:
    """Manages immutable version snapshots and version garbage collection.

    Each published version captures an immutable snapshot of the function
    definition at the time of publication, including a SHA-256 hash of
    the code source for integrity verification.
    """

    def __init__(self, registry: FunctionRegistry, event_bus: Any = None) -> None:
        self._registry = registry
        self._versions: Dict[str, List[FunctionVersion]] = defaultdict(list)
        self._event_bus = event_bus

    def publish_version(self, function_name: str, description: str = "",
                        namespace: str = "default") -> FunctionVersion:
        """Create an immutable version snapshot of the current function definition."""
        definition = self._registry.get_function(function_name, namespace)
        versions = self._versions[function_name]
        version_number = len(versions) + 1
        code_sha256 = self._compute_code_sha256(definition)

        version = FunctionVersion(
            function_name=function_name,
            version_number=version_number,
            description=description,
            code_sha256=code_sha256,
            definition_snapshot=copy.deepcopy(definition),
            published_at=datetime.now(timezone.utc),
        )
        versions.append(version)
        self._emit_event(EventType.LAM_VERSION_PUBLISHED, {
            "function_name": function_name,
            "version": version_number,
            "code_sha256": code_sha256,
        })
        logger.info("Published version %d of function '%s'", version_number, function_name)
        return version

    def get_version(self, function_name: str, version_number: int) -> FunctionVersion:
        """Retrieve a specific version by number."""
        versions = self._versions.get(function_name, [])
        for v in versions:
            if v.version_number == version_number:
                return v
        raise FunctionVersionNotFoundError(
            f"Version {version_number} not found for function '{function_name}'"
        )

    def get_latest_version(self, function_name: str) -> FunctionVersion:
        """Retrieve the most recently published version."""
        versions = self._versions.get(function_name, [])
        if not versions:
            raise FunctionVersionNotFoundError(
                f"No versions published for function '{function_name}'"
            )
        return versions[-1]

    def list_versions(self, function_name: str) -> List[FunctionVersion]:
        """List all versions for a function in publication order."""
        return list(self._versions.get(function_name, []))

    def delete_version(self, function_name: str, version_number: int) -> None:
        """Delete a specific version."""
        versions = self._versions.get(function_name, [])
        for i, v in enumerate(versions):
            if v.version_number == version_number:
                versions.pop(i)
                return
        raise FunctionVersionNotFoundError(
            f"Version {version_number} not found for function '{function_name}'"
        )

    def garbage_collect(self, retention_days: int = 30) -> List[str]:
        """Remove unreferenced versions older than the retention period."""
        cutoff = datetime.now(timezone.utc).timestamp() - (retention_days * 86400)
        collected = []
        for function_name, versions in self._versions.items():
            to_remove = []
            for v in versions:
                if v.published_at.timestamp() < cutoff:
                    to_remove.append(v)
            for v in to_remove:
                versions.remove(v)
                ref = f"{function_name}:v{v.version_number}"
                collected.append(ref)
                self._emit_event(EventType.LAM_VERSION_GARBAGE_COLLECTED, {
                    "function_name": function_name,
                    "version": v.version_number,
                })
        if collected:
            logger.info("Garbage collected %d versions: %s", len(collected), collected)
        return collected

    def _compute_code_sha256(self, definition: FunctionDefinition) -> str:
        """Compute SHA-256 hash of the function code source."""
        content = ""
        if definition.code_source.source_type == CodeSourceType.INLINE:
            content = definition.code_source.inline_code
        elif definition.code_source.source_type == CodeSourceType.IMAGE:
            content = definition.code_source.image_reference
        else:
            content = ",".join(definition.code_source.layer_names)
        return hashlib.sha256(content.encode()).hexdigest()

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# AliasManager
# ---------------------------------------------------------------------------

class AliasManager:
    """Manages mutable aliases with optional weighted routing.

    An alias is a named pointer to one or two function versions.
    When two versions are configured, the alias distributes invocations
    based on the configured weight, enabling canary and linear
    deployment strategies.
    """

    def __init__(self, version_manager: FunctionVersionManager,
                 event_bus: Any = None) -> None:
        self._version_manager = version_manager
        self._aliases: Dict[str, Dict[str, FunctionAlias]] = defaultdict(dict)
        self._event_bus = event_bus

    def create_alias(self, function_name: str, alias_name: str,
                     version: int) -> FunctionAlias:
        """Create a new alias pointing to a specific version."""
        self._version_manager.get_version(function_name, version)
        if alias_name in self._aliases.get(function_name, {}):
            raise AliasAlreadyExistsError(
                f"Alias '{alias_name}' already exists for function '{function_name}'"
            )
        alias = FunctionAlias(
            alias_name=alias_name,
            function_name=function_name,
            function_version=version,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._aliases[function_name][alias_name] = alias
        self._emit_event(EventType.LAM_ALIAS_CREATED, {
            "function_name": function_name,
            "alias_name": alias_name,
            "version": version,
        })
        return alias

    def update_alias(self, function_name: str, alias_name: str, version: int,
                     additional_version: Optional[int] = None,
                     additional_version_weight: float = 0.0) -> FunctionAlias:
        """Update an alias's target version and optional traffic split."""
        self._version_manager.get_version(function_name, version)
        if additional_version is not None:
            self._version_manager.get_version(function_name, additional_version)
        aliases = self._aliases.get(function_name, {})
        if alias_name not in aliases:
            raise AliasNotFoundError(
                f"Alias '{alias_name}' not found for function '{function_name}'"
            )
        alias = aliases[alias_name]
        alias.function_version = version
        alias.additional_version = additional_version
        alias.additional_version_weight = additional_version_weight
        alias.updated_at = datetime.now(timezone.utc)
        self._emit_event(EventType.LAM_ALIAS_UPDATED, {
            "function_name": function_name,
            "alias_name": alias_name,
            "version": version,
            "additional_version": additional_version,
            "weight": additional_version_weight,
        })
        return alias

    def get_alias(self, function_name: str, alias_name: str) -> FunctionAlias:
        """Retrieve an alias by name."""
        aliases = self._aliases.get(function_name, {})
        if alias_name not in aliases:
            raise AliasNotFoundError(
                f"Alias '{alias_name}' not found for function '{function_name}'"
            )
        return aliases[alias_name]

    def delete_alias(self, function_name: str, alias_name: str) -> None:
        """Delete an alias."""
        aliases = self._aliases.get(function_name, {})
        if alias_name not in aliases:
            raise AliasNotFoundError(
                f"Alias '{alias_name}' not found for function '{function_name}'"
            )
        del aliases[alias_name]
        self._emit_event(EventType.LAM_ALIAS_DELETED, {
            "function_name": function_name,
            "alias_name": alias_name,
        })

    def list_aliases(self, function_name: str) -> List[FunctionAlias]:
        """List all aliases for a function."""
        return list(self._aliases.get(function_name, {}).values())

    def resolve_version(self, alias: FunctionAlias) -> int:
        """Resolve which version to invoke based on alias weights.

        When only one version is configured, always returns that version.
        When two versions are configured, performs weighted random selection
        based on the additional_version_weight parameter.
        """
        if alias.additional_version is None or alias.additional_version_weight <= 0:
            return alias.function_version
        if random.random() < alias.additional_version_weight:
            return alias.additional_version
        return alias.function_version

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# TrafficShiftOrchestrator
# ---------------------------------------------------------------------------

class TrafficShiftOrchestrator:
    """Orchestrates progressive deployment via alias weight updates.

    Supports three strategies:
    - Linear: Equal weight increments over N steps
    - Canary: Jump to target weight in one step
    - All-at-once: Immediate 100% shift
    """

    def __init__(self, alias_manager: AliasManager, event_bus: Any = None) -> None:
        self._alias_manager = alias_manager
        self._shifts: Dict[str, TrafficShiftState] = {}
        self._event_bus = event_bus

    def start_shift(self, function_name: str, alias_name: str, new_version: int,
                    strategy: TrafficShiftStrategy, steps: int = 10,
                    step_interval_seconds: float = 300.0) -> TrafficShiftState:
        """Begin a traffic shift operation."""
        alias = self._alias_manager.get_alias(function_name, alias_name)
        old_version = alias.function_version

        state = TrafficShiftState(
            alias_name=alias_name,
            function_name=function_name,
            strategy=strategy,
            old_version=old_version,
            new_version=new_version,
            current_weight=0.0,
            target_weight=1.0,
            step_count=steps,
            started_at=datetime.now(timezone.utc),
        )

        if strategy == TrafficShiftStrategy.ALL_AT_ONCE:
            self._alias_manager.update_alias(
                function_name, alias_name, new_version
            )
            state.current_weight = 1.0
        elif strategy == TrafficShiftStrategy.CANARY:
            weight = state.target_weight
            self._alias_manager.update_alias(
                function_name, alias_name, old_version,
                additional_version=new_version,
                additional_version_weight=weight,
            )
            state.current_weight = weight
        else:
            increment = 1.0 / max(steps, 1)
            state.current_weight = increment
            self._alias_manager.update_alias(
                function_name, alias_name, old_version,
                additional_version=new_version,
                additional_version_weight=increment,
            )

        key = f"{function_name}:{alias_name}"
        self._shifts[key] = state
        self._emit_event(EventType.LAM_TRAFFIC_SHIFT_STARTED, {
            "function_name": function_name,
            "alias_name": alias_name,
            "old_version": old_version,
            "new_version": new_version,
            "strategy": strategy.value,
        })
        return state

    def advance_shift(self, function_name: str, alias_name: str) -> TrafficShiftState:
        """Advance the traffic shift by one step."""
        key = f"{function_name}:{alias_name}"
        state = self._shifts.get(key)
        if state is None:
            raise TrafficShiftError(
                f"No active traffic shift for '{function_name}:{alias_name}'"
            )
        new_weight = self._compute_next_weight(state)
        state.current_weight = new_weight

        if new_weight >= state.target_weight:
            self._alias_manager.update_alias(
                function_name, alias_name, state.new_version
            )
            state.current_weight = 1.0
            del self._shifts[key]
            self._emit_event(EventType.LAM_TRAFFIC_SHIFT_COMPLETED, {
                "function_name": function_name,
                "alias_name": alias_name,
            })
        else:
            self._alias_manager.update_alias(
                function_name, alias_name, state.old_version,
                additional_version=state.new_version,
                additional_version_weight=new_weight,
            )
        return state

    def rollback_shift(self, function_name: str, alias_name: str) -> None:
        """Rollback an in-progress traffic shift to the original version."""
        key = f"{function_name}:{alias_name}"
        state = self._shifts.get(key)
        if state is None:
            raise TrafficShiftError(
                f"No active traffic shift for '{function_name}:{alias_name}'"
            )
        self._alias_manager.update_alias(
            function_name, alias_name, state.old_version
        )
        del self._shifts[key]
        self._emit_event(EventType.LAM_TRAFFIC_SHIFT_ROLLED_BACK, {
            "function_name": function_name,
            "alias_name": alias_name,
        })

    def get_shift_state(self, function_name: str,
                        alias_name: str) -> Optional[TrafficShiftState]:
        """Get the current state of a traffic shift operation."""
        key = f"{function_name}:{alias_name}"
        return self._shifts.get(key)

    def _compute_next_weight(self, state: TrafficShiftState) -> float:
        """Compute the next weight increment based on the strategy."""
        if state.strategy == TrafficShiftStrategy.LINEAR:
            increment = 1.0 / max(state.step_count, 1)
            return min(state.current_weight + increment, state.target_weight)
        elif state.strategy == TrafficShiftStrategy.CANARY:
            return state.target_weight
        else:
            return state.target_weight

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# InvocationRouter
# ---------------------------------------------------------------------------

class InvocationRouter:
    """Resolves function name + qualifier to a concrete definition and version.

    Handles three qualifier types:
    - ``$LATEST``: Resolves to the most recently published version
    - Numeric version: Resolves to a specific version number
    - Alias name: Resolves through the alias manager with weighted routing
    """

    def __init__(self, registry: FunctionRegistry,
                 version_manager: FunctionVersionManager,
                 alias_manager: AliasManager) -> None:
        self._registry = registry
        self._version_manager = version_manager
        self._alias_manager = alias_manager

    def resolve(self, function_name: str,
                qualifier: str = "$LATEST") -> Tuple[FunctionDefinition, FunctionVersion]:
        """Resolve a function name and qualifier to a definition and version."""
        definition = self._registry.get_function(function_name)
        if qualifier == "$LATEST":
            version = self._resolve_latest(function_name)
        elif qualifier.isdigit():
            version = self._resolve_version(function_name, qualifier)
        else:
            version = self._resolve_alias(function_name, qualifier)
        return definition, version

    def _resolve_alias(self, function_name: str, alias_name: str) -> FunctionVersion:
        """Resolve an alias to a function version."""
        alias = self._alias_manager.get_alias(function_name, alias_name)
        version_number = self._alias_manager.resolve_version(alias)
        return self._version_manager.get_version(function_name, version_number)

    def _resolve_version(self, function_name: str, version_str: str) -> FunctionVersion:
        """Resolve a numeric version string."""
        return self._version_manager.get_version(function_name, int(version_str))

    def _resolve_latest(self, function_name: str) -> FunctionVersion:
        """Resolve $LATEST to the most recently published version."""
        return self._version_manager.get_latest_version(function_name)


# ---------------------------------------------------------------------------
# ResourceAllocator
# ---------------------------------------------------------------------------

class ResourceAllocator:
    """Maps function resource configurations to cgroup controller settings.

    Implements the proportional CPU allocation model used by AWS Lambda:
    1,769 MB of memory equals one full vCPU (100,000 microseconds of
    CPU time per period).  Functions with less memory receive proportionally
    less CPU time; functions with more memory receive proportionally more.
    """

    def __init__(self) -> None:
        self._simulated_stats: Dict[str, Dict[str, float]] = {}

    def compute_cpu_quota(self, memory_mb: int) -> int:
        """Compute the cpu.max quota value for a given memory allocation.

        Returns the number of microseconds of CPU time per period
        that the function is entitled to.
        """
        vcpus = memory_mb / VCPU_MEMORY_RATIO
        quota = int(vcpus * CPU_PERIOD_US)
        return max(quota, 1000)

    def compute_memory_max(self, memory_mb: int) -> int:
        """Compute memory.max in bytes."""
        return memory_mb * 1024 * 1024

    def compute_memory_high(self, memory_mb: int) -> int:
        """Compute memory.high (90% of memory.max) for soft limits."""
        return int(self.compute_memory_max(memory_mb) * 0.9)

    def compute_pids_max(self) -> int:
        """Return the maximum process count for execution environments."""
        return MAX_EXEC_PID_LIMIT

    def compute_io_max(self, ephemeral_storage_mb: int) -> int:
        """Compute proportional I/O bandwidth based on ephemeral storage."""
        base_iops = 3000
        additional = ephemeral_storage_mb // 512
        return base_iops + (additional * 500)

    def create_cgroup_config(self, definition: FunctionDefinition) -> Dict[str, Any]:
        """Generate the complete cgroup v2 configuration for a function."""
        return {
            "cpu.max": f"{self.compute_cpu_quota(definition.memory_mb)} {CPU_PERIOD_US}",
            "memory.max": str(self.compute_memory_max(definition.memory_mb)),
            "memory.high": str(self.compute_memory_high(definition.memory_mb)),
            "pids.max": str(self.compute_pids_max()),
            "io.max": str(self.compute_io_max(definition.ephemeral_storage_mb)),
        }

    def get_cgroup_path(self, function_name: str, environment_id: str) -> str:
        """Generate the cgroup hierarchy path for an execution environment."""
        return f"/sys/fs/cgroup/fizzlambda/{function_name}/{environment_id}"

    def read_peak_memory(self, cgroup_path: str) -> int:
        """Read simulated peak memory usage from a cgroup path."""
        stats = self._simulated_stats.get(cgroup_path, {})
        return int(stats.get("memory_peak", random.randint(10 * 1024 * 1024, 100 * 1024 * 1024)))

    def read_cpu_stats(self, cgroup_path: str) -> Dict[str, float]:
        """Read simulated CPU statistics from a cgroup path."""
        stats = self._simulated_stats.get(cgroup_path, {})
        return {
            "usage_usec": stats.get("cpu_usage", random.uniform(1000, 50000)),
            "user_usec": stats.get("cpu_user", random.uniform(800, 40000)),
            "system_usec": stats.get("cpu_system", random.uniform(200, 10000)),
            "nr_periods": stats.get("nr_periods", random.randint(1, 100)),
            "nr_throttled": stats.get("nr_throttled", random.randint(0, 10)),
            "throttled_usec": stats.get("throttled_usec", random.uniform(0, 5000)),
        }


# ---------------------------------------------------------------------------
# ExecutionEnvironmentManager
# ---------------------------------------------------------------------------

class ExecutionEnvironmentManager:
    """Creates, manages, and destroys isolated execution environments.

    Each execution environment represents an initialized sandbox capable
    of executing function invocations.  The cold start sequence follows
    the AWS Lambda initialization model: image resolution, sandbox
    creation, cgroup configuration, container creation, and runtime
    bootstrap.
    """

    def __init__(self, resource_allocator: ResourceAllocator,
                 event_bus: Any = None) -> None:
        self._resource_allocator = resource_allocator
        self._event_bus = event_bus
        self._environments: Dict[str, ExecutionEnvironment] = {}
        self._logs: Dict[str, List[str]] = defaultdict(list)
        self._max_recycling_invocations = DEFAULT_RECYCLING_INVOCATIONS
        self._max_recycling_lifetime = DEFAULT_RECYCLING_LIFETIME

    def create_environment(self, definition: FunctionDefinition,
                           version: FunctionVersion) -> ExecutionEnvironment:
        """Create a new execution environment via the cold start sequence."""
        env_id = str(uuid.uuid4())[:12]
        self._emit_event(EventType.LAM_ENVIRONMENT_CREATING, {
            "environment_id": env_id,
            "function_name": definition.name,
        })

        breakdown = self._cold_start_sequence(definition, version)

        cgroup_path = self._resource_allocator.get_cgroup_path(definition.name, env_id)
        env = ExecutionEnvironment(
            environment_id=env_id,
            function_id=definition.function_id,
            function_version=str(version.version_number),
            state=EnvironmentState.READY,
            container_id=f"fizz-{env_id}",
            sandbox_id=f"sandbox-{env_id}",
            cgroup_path=cgroup_path,
            network_namespace=f"ns-{env_id}",
            created_at=datetime.now(timezone.utc),
            last_invocation_at=datetime.now(timezone.utc),
        )
        self._environments[env_id] = env
        self._emit_event(EventType.LAM_ENVIRONMENT_READY, {
            "environment_id": env_id,
            "cold_start_ms": breakdown.total_ms,
        })
        self._emit_event(EventType.LAM_COLD_START_COMPLETED, {
            "environment_id": env_id,
            "breakdown": {
                "image_resolution_ms": breakdown.image_resolution_ms,
                "sandbox_creation_ms": breakdown.sandbox_creation_ms,
                "network_setup_ms": breakdown.network_setup_ms,
                "container_creation_ms": breakdown.container_creation_ms,
                "runtime_bootstrap_ms": breakdown.runtime_bootstrap_ms,
                "total_ms": breakdown.total_ms,
            },
        })
        logger.debug("Environment %s created for %s (cold start: %.1fms)",
                      env_id, definition.name, breakdown.total_ms)
        return env

    def destroy_environment(self, environment: ExecutionEnvironment) -> None:
        """Destroy an execution environment and release all resources."""
        environment.state = EnvironmentState.DESTROYING
        self._emit_event(EventType.LAM_ENVIRONMENT_DESTROYING, {
            "environment_id": environment.environment_id,
        })
        self._cleanup_sandbox(environment.sandbox_id)
        self._cleanup_cgroup(environment.cgroup_path)
        if environment.environment_id in self._environments:
            del self._environments[environment.environment_id]
        environment.state = EnvironmentState.DESTROYING
        self._emit_event(EventType.LAM_ENVIRONMENT_DESTROYED, {
            "environment_id": environment.environment_id,
        })

    def execute_invocation(self, environment: ExecutionEnvironment,
                           request: InvocationRequest,
                           context: FunctionContext,
                           handler: Optional[Callable] = None) -> InvocationResponse:
        """Execute a function invocation in the given environment."""
        environment.state = EnvironmentState.BUSY
        self._emit_event(EventType.LAM_ENVIRONMENT_BUSY, {
            "environment_id": environment.environment_id,
        })

        start = time.time()
        try:
            if context.timeout_remaining_ms <= 0:
                self._handle_timeout(environment)
                return InvocationResponse(
                    status_code=408,
                    function_error=FunctionErrorType.TIMEOUT.value,
                    executed_version=environment.function_version,
                    metrics=InvocationMetrics(cold_start=False),
                )

            if handler is not None:
                try:
                    event = json.loads(request.payload) if request.payload else {}
                except (json.JSONDecodeError, UnicodeDecodeError):
                    event = {}
                result = handler(event, context)
                response_payload = json.dumps(result).encode() if result else b""
            else:
                response_payload = self._inject_event(environment, request.payload)

            elapsed = time.time() - start
            duration_ms = elapsed * 1000
            billed_ms = max(math.ceil(duration_ms), 1)

            peak_memory = self._resource_allocator.read_peak_memory(environment.cgroup_path)
            memory_used_mb = peak_memory / (1024 * 1024)

            environment.invocation_count += 1
            environment.last_invocation_at = datetime.now(timezone.utc)
            environment.peak_memory_bytes = max(environment.peak_memory_bytes, peak_memory)
            environment.state = EnvironmentState.READY

            log_entry = (
                f"[{datetime.now(timezone.utc).isoformat()}] "
                f"INV {context.invocation_id} {context.function_name} "
                f"v{context.function_version} {duration_ms:.1f}ms "
                f"{memory_used_mb:.1f}MB"
            )
            self._logs[context.function_name].append(log_entry)
            if len(self._logs[context.function_name]) > 1000:
                self._logs[context.function_name] = self._logs[context.function_name][-1000:]

            log_result = None
            if request.log_type == LogType.TAIL:
                log_result = log_entry[:LOG_TAIL_BYTES]

            return InvocationResponse(
                status_code=200,
                payload=response_payload,
                executed_version=environment.function_version,
                log_result=log_result,
                metrics=InvocationMetrics(
                    duration_ms=duration_ms,
                    billed_duration_ms=float(billed_ms),
                    memory_used_mb=memory_used_mb,
                    memory_allocated_mb=float(context.memory_limit_mb),
                    cold_start=False,
                ),
            )
        except Exception as exc:
            elapsed = time.time() - start
            environment.state = EnvironmentState.READY
            return InvocationResponse(
                status_code=500,
                function_error=FunctionErrorType.UNHANDLED.value,
                payload=json.dumps({"errorMessage": str(exc)}).encode(),
                executed_version=environment.function_version,
                metrics=InvocationMetrics(
                    duration_ms=elapsed * 1000,
                    billed_duration_ms=float(max(math.ceil(elapsed * 1000), 1)),
                    memory_allocated_mb=float(context.memory_limit_mb),
                ),
            )

    def should_recycle(self, environment: ExecutionEnvironment) -> bool:
        """Check if an environment should be recycled based on age or invocation count."""
        if environment.invocation_count >= self._max_recycling_invocations:
            return True
        age = (datetime.now(timezone.utc) - environment.created_at).total_seconds()
        if age >= self._max_recycling_lifetime:
            return True
        return False

    def get_logs(self, function_name: str, tail: int = 20) -> List[str]:
        """Retrieve recent invocation logs for a function."""
        logs = self._logs.get(function_name, [])
        return logs[-tail:]

    def _cold_start_sequence(self, definition: FunctionDefinition,
                             version: FunctionVersion) -> ColdStartBreakdown:
        """Execute the cold start initialization sequence."""
        self._emit_event(EventType.LAM_COLD_START_INITIATED, {
            "function_name": definition.name,
            "version": version.version_number,
        })

        image_ms = random.uniform(5, 50)
        sandbox_ms = random.uniform(2, 20)
        network_ms = random.uniform(1, 10)
        container_ms = random.uniform(10, 80)
        bootstrap_ms = random.uniform(5, 100)

        return ColdStartBreakdown(
            image_resolution_ms=image_ms,
            sandbox_creation_ms=sandbox_ms,
            network_setup_ms=network_ms,
            container_creation_ms=container_ms,
            runtime_bootstrap_ms=bootstrap_ms,
            total_ms=image_ms + sandbox_ms + network_ms + container_ms + bootstrap_ms,
            snapshot_restored=False,
        )

    def _resolve_image(self, definition: FunctionDefinition) -> str:
        """Resolve the container image for a function."""
        if definition.code_source.source_type == CodeSourceType.IMAGE:
            return definition.code_source.image_reference
        return f"fizzlambda/{definition.runtime.value}:latest"

    def _create_sandbox(self, definition: FunctionDefinition) -> str:
        """Create a sandbox for function execution."""
        return f"sandbox-{uuid.uuid4().hex[:8]}"

    def _configure_cgroup(self, definition: FunctionDefinition, env_id: str) -> str:
        """Configure cgroup v2 resource limits for the environment."""
        return self._resource_allocator.get_cgroup_path(definition.name, env_id)

    def _create_container(self, sandbox_id: str, image_ref: str,
                          definition: FunctionDefinition) -> str:
        """Create a container within the sandbox."""
        return f"fizz-{uuid.uuid4().hex[:8]}"

    def _await_readiness(self, container_id: str, timeout: float) -> None:
        """Wait for the container to reach ready state."""
        pass

    def _inject_event(self, environment: ExecutionEnvironment,
                      payload: bytes) -> bytes:
        """Inject an event payload into the execution environment."""
        try:
            event = json.loads(payload) if payload else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            event = {}

        number = event.get("number", 0)
        if isinstance(number, int) and number > 0:
            result = str(number)
            if number % 15 == 0:
                result = "FizzBuzz"
            elif number % 3 == 0:
                result = "Fizz"
            elif number % 5 == 0:
                result = "Buzz"
            return json.dumps({"result": result, "number": number}).encode()
        return json.dumps({"result": "processed", "input": event}).encode()

    def _handle_timeout(self, environment: ExecutionEnvironment) -> None:
        """Handle a function execution timeout."""
        self._emit_event(EventType.LAM_INVOCATION_TIMED_OUT, {
            "environment_id": environment.environment_id,
        })
        environment.state = EnvironmentState.READY

    def _handle_oom(self, environment: ExecutionEnvironment) -> None:
        """Handle an out-of-memory condition."""
        self._emit_event(EventType.LAM_INVOCATION_OOM_KILLED, {
            "environment_id": environment.environment_id,
        })
        environment.state = EnvironmentState.DESTROYING

    def _cleanup_sandbox(self, sandbox_id: str) -> None:
        """Clean up sandbox resources."""
        logger.debug("Cleaned up sandbox %s", sandbox_id)

    def _cleanup_cgroup(self, cgroup_path: str) -> None:
        """Clean up cgroup hierarchy."""
        logger.debug("Cleaned up cgroup %s", cgroup_path)

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# WarmPoolManager
# ---------------------------------------------------------------------------

class WarmPoolManager:
    """Two-level pool structure for pre-initialized execution environments.

    The warm pool is organized as::

        function_id -> version -> [ExecutionEnvironment, ...]

    Environments are acquired with MRU (most recently used) ordering to
    maximize cache locality.  Idle eviction sweeps release environments
    that exceed the configured timeout.  Provisioned concurrency
    environments are exempt from idle eviction.
    """

    def __init__(self, env_manager: ExecutionEnvironmentManager,
                 max_total: int = DEFAULT_MAX_ENVIRONMENTS,
                 max_per_function: int = DEFAULT_MAX_PER_FUNCTION,
                 idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
                 event_bus: Any = None) -> None:
        self._env_manager = env_manager
        self._max_total = max_total
        self._max_per_function = max_per_function
        self._idle_timeout = idle_timeout
        self._event_bus = event_bus
        self._pool: Dict[str, Dict[str, List[ExecutionEnvironment]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def acquire(self, function_id: str, version: str) -> Optional[ExecutionEnvironment]:
        """Acquire a warm execution environment (MRU ordering)."""
        with self._lock:
            envs = self._pool.get(function_id, {}).get(version, [])
            for i in range(len(envs) - 1, -1, -1):
                env = envs[i]
                if env.state == EnvironmentState.READY:
                    envs.pop(i)
                    self._hits += 1
                    self._emit_event(EventType.LAM_WARM_POOL_HIT, {
                        "function_id": function_id,
                        "environment_id": env.environment_id,
                    })
                    return env
        self._misses += 1
        self._emit_event(EventType.LAM_WARM_POOL_MISS, {
            "function_id": function_id,
            "version": version,
        })
        return None

    def release(self, environment: ExecutionEnvironment) -> None:
        """Return an execution environment to the warm pool."""
        with self._lock:
            function_envs = self._pool[environment.function_id][environment.function_version]
            total = self.get_pool_size()
            if total >= self._max_total:
                self._evict_lru(environment.function_id, environment.function_version)
            if len(function_envs) >= self._max_per_function:
                self._evict_lru(environment.function_id, environment.function_version)
            environment.state = EnvironmentState.FROZEN
            self._emit_event(EventType.LAM_ENVIRONMENT_FROZEN, {
                "environment_id": environment.environment_id,
            })
            function_envs.append(environment)

    def evict_idle(self) -> int:
        """Sweep and evict environments that exceed the idle timeout."""
        now = datetime.now(timezone.utc)
        evicted = 0
        with self._lock:
            for function_id, versions in self._pool.items():
                for version, envs in versions.items():
                    to_remove = []
                    for env in envs:
                        if env.is_provisioned:
                            continue
                        idle_seconds = (now - env.last_invocation_at).total_seconds()
                        if idle_seconds > self._idle_timeout:
                            to_remove.append(env)
                    for env in to_remove:
                        envs.remove(env)
                        self._env_manager.destroy_environment(env)
                        evicted += 1
                        self._emit_event(EventType.LAM_WARM_POOL_EVICTION, {
                            "environment_id": env.environment_id,
                            "idle_seconds": (now - env.last_invocation_at).total_seconds(),
                        })
        return evicted

    def provision(self, function_id: str, version: str,
                  definition: FunctionDefinition, count: int,
                  func_version: Optional[FunctionVersion] = None) -> List[ExecutionEnvironment]:
        """Pre-initialize warm environments for provisioned concurrency."""
        environments = []
        if func_version is None:
            func_version = FunctionVersion(
                function_name=definition.name,
                version_number=int(version) if version.isdigit() else 1,
            )
        for _ in range(count):
            env = self._env_manager.create_environment(definition, func_version)
            env.is_provisioned = True
            env.state = EnvironmentState.FROZEN
            with self._lock:
                self._pool[function_id][version].append(env)
            environments.append(env)
            self._emit_event(EventType.LAM_WARM_POOL_PROVISIONED, {
                "function_id": function_id,
                "environment_id": env.environment_id,
            })
        return environments

    def deprovision(self, function_id: str) -> int:
        """Remove all provisioned environments for a function."""
        removed = 0
        with self._lock:
            versions = self._pool.get(function_id, {})
            for version, envs in versions.items():
                to_remove = [e for e in envs if e.is_provisioned]
                for env in to_remove:
                    envs.remove(env)
                    self._env_manager.destroy_environment(env)
                    removed += 1
        return removed

    def get_pool_size(self, function_id: Optional[str] = None) -> int:
        """Get the current pool size, optionally filtered by function."""
        total = 0
        for fid, versions in self._pool.items():
            if function_id is not None and fid != function_id:
                continue
            for envs in versions.values():
                total += len(envs)
        return total

    def get_hit_rate(self, function_id: Optional[str] = None) -> float:
        """Compute the warm pool hit rate."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive warm pool statistics."""
        return {
            "total_environments": self.get_pool_size(),
            "max_total": self._max_total,
            "max_per_function": self._max_per_function,
            "idle_timeout": self._idle_timeout,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.get_hit_rate(),
            "functions": len(self._pool),
        }

    def _evict_lru(self, function_id: str, version: str) -> None:
        """Evict the least recently used environment from the pool."""
        envs = self._pool.get(function_id, {}).get(version, [])
        non_provisioned = [e for e in envs if not e.is_provisioned]
        if non_provisioned:
            lru = min(non_provisioned, key=lambda e: e.last_invocation_at)
            envs.remove(lru)
            self._env_manager.destroy_environment(lru)

    def _is_provisioned(self, environment: ExecutionEnvironment) -> bool:
        """Check if an environment is part of provisioned concurrency."""
        return environment.is_provisioned

    def _replace_provisioned(self, environment: ExecutionEnvironment) -> None:
        """Replace a recycled provisioned environment with a new one."""
        pass

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# ColdStartOptimizer
# ---------------------------------------------------------------------------

class ColdStartOptimizer:
    """Reduces cold start latency through snapshot-and-restore, predictive
    pre-warming, and layer caching.

    The optimizer maintains three subsystems:

    1. **Snapshot store**: Captures initialized environment state for
       rapid restoration on subsequent invocations.
    2. **Predictive pre-warmer**: Analyzes invocation history time series
       to forecast demand and pre-warm environments ahead of traffic spikes.
    3. **Layer cache**: Caches extracted layer contents to avoid repeated
       decompression during cold starts.
    """

    def __init__(self, env_manager: ExecutionEnvironmentManager,
                 warm_pool: WarmPoolManager,
                 snapshot_enabled: bool = True,
                 predictive_enabled: bool = True,
                 layer_cache_size_mb: int = 10240,
                 event_bus: Any = None) -> None:
        self._env_manager = env_manager
        self._warm_pool = warm_pool
        self._snapshot_enabled = snapshot_enabled
        self._predictive_enabled = predictive_enabled
        self._layer_cache_size_mb = layer_cache_size_mb
        self._event_bus = event_bus

        self._snapshots: Dict[str, SnapshotRecord] = {}
        self._invocation_history: Dict[str, List[float]] = defaultdict(list)
        self._layer_cache: OrderedDict = OrderedDict()
        self._layer_cache_bytes = 0
        self._snapshot_hits = 0
        self._snapshot_misses = 0
        self._cold_start_latencies: List[float] = []

    def capture_snapshot(self, environment: ExecutionEnvironment,
                         definition: FunctionDefinition) -> SnapshotRecord:
        """Capture the initialized state of an execution environment."""
        if not self._snapshot_enabled:
            raise ColdStartOptimizerError("Snapshot capture is disabled")

        snapshot = SnapshotRecord(
            snapshot_id=str(uuid.uuid4())[:12],
            function_id=definition.function_id,
            function_version=environment.function_version,
            code_hash=hashlib.sha256(
                definition.code_source.inline_code.encode()
            ).hexdigest(),
            image_ref=f"snapshot://{environment.environment_id}",
            captured_at=datetime.now(timezone.utc),
        )
        key = f"{definition.function_id}:{environment.function_version}"
        self._snapshots[key] = snapshot
        self._emit_event(EventType.LAM_SNAPSHOT_CAPTURED, {
            "snapshot_id": snapshot.snapshot_id,
            "function_id": definition.function_id,
        })
        return snapshot

    def restore_snapshot(self, function_id: str,
                         version: str) -> Optional[ExecutionEnvironment]:
        """Attempt to restore an environment from a snapshot."""
        key = f"{function_id}:{version}"
        snapshot = self._snapshots.get(key)
        if snapshot is None:
            self._snapshot_misses += 1
            return None

        env_id = str(uuid.uuid4())[:12]
        env = ExecutionEnvironment(
            environment_id=env_id,
            function_id=function_id,
            function_version=version,
            state=EnvironmentState.READY,
            container_id=f"fizz-snap-{env_id}",
            sandbox_id=f"sandbox-snap-{env_id}",
            cgroup_path=f"/sys/fs/cgroup/fizzlambda/snap/{env_id}",
            network_namespace=f"ns-snap-{env_id}",
        )
        self._snapshot_hits += 1
        self._emit_event(EventType.LAM_SNAPSHOT_RESTORED, {
            "snapshot_id": snapshot.snapshot_id,
            "environment_id": env_id,
        })
        return env

    def get_snapshot(self, function_id: str, version: str) -> Optional[SnapshotRecord]:
        """Retrieve a snapshot record for a function version."""
        key = f"{function_id}:{version}"
        return self._snapshots.get(key)

    def invalidate_snapshot(self, function_id: str, version: str) -> None:
        """Invalidate a snapshot when the underlying code changes."""
        key = f"{function_id}:{version}"
        if key in self._snapshots:
            del self._snapshots[key]

    def record_invocation(self, function_id: str, timestamp: float) -> None:
        """Record an invocation timestamp for demand prediction."""
        history = self._invocation_history[function_id]
        history.append(timestamp)
        if len(history) > 10000:
            self._invocation_history[function_id] = history[-10000:]

    def predict_demand(self, function_id: str) -> Optional[PreWarmPrediction]:
        """Predict future invocation demand using time-series analysis."""
        if not self._predictive_enabled:
            return None
        history = self._invocation_history.get(function_id, [])
        if len(history) < 10:
            return None

        pattern = self._compute_seasonal_pattern(history)
        next_peak = self._forecast_next_peak(pattern)
        if next_peak is None:
            return None

        recent_rate = len(history[-100:]) / max(
            (history[-1] - history[-100]) if len(history) >= 100 else 1, 0.001
        )
        predicted = max(1, int(recent_rate * 1.5))

        return PreWarmPrediction(
            function_id=function_id,
            predicted_concurrency=predicted,
            confidence=min(0.95, len(history) / 1000),
            trigger_time=datetime.now(timezone.utc),
        )

    def pre_warm(self, function_id: str, definition: FunctionDefinition,
                 version: FunctionVersion) -> int:
        """Pre-warm environments based on demand prediction."""
        prediction = self.predict_demand(function_id)
        if prediction is None:
            return 0
        current = self._warm_pool.get_pool_size(function_id)
        needed = max(0, prediction.predicted_concurrency - current)
        if needed > 0:
            self._warm_pool.provision(
                function_id, str(version.version_number),
                definition, needed, version
            )
            self._emit_event(EventType.LAM_PRE_WARM_TRIGGERED, {
                "function_id": function_id,
                "count": needed,
                "confidence": prediction.confidence,
            })
        return needed

    def cache_layer(self, layer: FunctionLayer) -> None:
        """Cache extracted layer contents for rapid cold starts."""
        key = f"{layer.layer_name}:{layer.layer_version}"
        if key in self._layer_cache:
            self._layer_cache.move_to_end(key)
            return
        content = layer.content_ref.encode() if layer.content_ref else b""
        size = len(content)
        while (self._layer_cache_bytes + size) > (self._layer_cache_size_mb * 1024 * 1024):
            if not self._layer_cache:
                break
            evicted_key, evicted_content = self._layer_cache.popitem(last=False)
            self._layer_cache_bytes -= len(evicted_content)
        self._layer_cache[key] = content
        self._layer_cache_bytes += size

    def get_cached_layer(self, layer_name: str, version: int) -> Optional[bytes]:
        """Retrieve a cached layer by name and version."""
        key = f"{layer_name}:{version}"
        if key in self._layer_cache:
            self._layer_cache.move_to_end(key)
            return self._layer_cache[key]
        return None

    def evict_layer_cache(self) -> int:
        """Evict all entries from the layer cache."""
        count = len(self._layer_cache)
        self._layer_cache.clear()
        self._layer_cache_bytes = 0
        return count

    def get_cold_start_stats(self) -> Dict[str, Any]:
        """Get cold start optimization statistics."""
        total_snapshots = self._snapshot_hits + self._snapshot_misses
        return {
            "snapshot_enabled": self._snapshot_enabled,
            "predictive_enabled": self._predictive_enabled,
            "snapshots_stored": len(self._snapshots),
            "snapshot_hits": self._snapshot_hits,
            "snapshot_misses": self._snapshot_misses,
            "snapshot_hit_rate": (
                self._snapshot_hits / total_snapshots if total_snapshots > 0 else 0.0
            ),
            "layer_cache_entries": len(self._layer_cache),
            "layer_cache_bytes": self._layer_cache_bytes,
            "layer_cache_capacity_mb": self._layer_cache_size_mb,
            "cold_start_count": len(self._cold_start_latencies),
            "avg_cold_start_ms": (
                sum(self._cold_start_latencies) / len(self._cold_start_latencies)
                if self._cold_start_latencies else 0.0
            ),
        }

    def _compute_seasonal_pattern(self, timestamps: List[float]) -> List[float]:
        """Compute hourly seasonal pattern from invocation timestamps."""
        hourly_counts: List[float] = [0.0] * 24
        for ts in timestamps:
            hour = int((ts % 86400) / 3600)
            hourly_counts[hour] += 1
        total = sum(hourly_counts) or 1
        return [c / total for c in hourly_counts]

    def _forecast_next_peak(self, pattern: List[float]) -> Optional[float]:
        """Forecast the next peak hour from the seasonal pattern."""
        if not pattern:
            return None
        peak_hour = pattern.index(max(pattern))
        now_hour = int((time.time() % 86400) / 3600)
        hours_until = (peak_hour - now_hour) % 24
        return time.time() + (hours_until * 3600)

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# EventTriggerManager
# ---------------------------------------------------------------------------

class EventTriggerManager:
    """Manages trigger registrations and event delivery.

    Supports four trigger types:
    - HTTP: Maps HTTP requests to function invocations
    - Timer: Invokes functions on a schedule (cron or rate)
    - Queue: Polls message queues and batches messages
    - Event Bus: Filters events by pattern matching
    """

    def __init__(self, event_bus: Any = None) -> None:
        self._triggers: Dict[str, TriggerDefinition] = {}
        self._event_bus = event_bus

    def create_trigger(self, trigger: TriggerDefinition) -> TriggerDefinition:
        """Register a new event trigger."""
        if not trigger.trigger_id:
            trigger.trigger_id = str(uuid.uuid4())[:12]
        if trigger.trigger_id in self._triggers:
            raise TriggerError(
                f"Trigger '{trigger.trigger_id}' already exists"
            )
        trigger.created_at = datetime.now(timezone.utc)
        self._triggers[trigger.trigger_id] = trigger
        self._emit_event(EventType.LAM_TRIGGER_CREATED, {
            "trigger_id": trigger.trigger_id,
            "function_name": trigger.function_name,
            "trigger_type": trigger.trigger_type.value,
        })
        return trigger

    def get_trigger(self, trigger_id: str) -> TriggerDefinition:
        """Retrieve a trigger by ID."""
        if trigger_id not in self._triggers:
            raise TriggerNotFoundError(
                f"Trigger '{trigger_id}' not found"
            )
        return self._triggers[trigger_id]

    def delete_trigger(self, trigger_id: str) -> None:
        """Delete a trigger."""
        if trigger_id not in self._triggers:
            raise TriggerNotFoundError(
                f"Trigger '{trigger_id}' not found"
            )
        del self._triggers[trigger_id]

    def enable_trigger(self, trigger_id: str) -> None:
        """Enable a trigger for event delivery."""
        trigger = self.get_trigger(trigger_id)
        trigger.enabled = True
        self._emit_event(EventType.LAM_TRIGGER_ENABLED, {
            "trigger_id": trigger_id,
        })

    def disable_trigger(self, trigger_id: str) -> None:
        """Disable a trigger to stop event delivery."""
        trigger = self.get_trigger(trigger_id)
        trigger.enabled = False
        self._emit_event(EventType.LAM_TRIGGER_DISABLED, {
            "trigger_id": trigger_id,
        })

    def list_triggers(self, function_name: Optional[str] = None) -> List[TriggerDefinition]:
        """List triggers, optionally filtered by function name."""
        if function_name is not None:
            return [
                t for t in self._triggers.values()
                if t.function_name == function_name
            ]
        return list(self._triggers.values())

    def fire_trigger(self, trigger: TriggerDefinition,
                     event_payload: Dict[str, Any]) -> InvocationRequest:
        """Create an invocation request from a trigger event."""
        if not trigger.enabled:
            raise TriggerError(
                f"Trigger '{trigger.trigger_id}' is disabled"
            )
        self._emit_event(EventType.LAM_TRIGGER_FIRED, {
            "trigger_id": trigger.trigger_id,
            "function_name": trigger.function_name,
        })
        return InvocationRequest(
            function_name=trigger.function_name,
            qualifier=trigger.qualifier,
            invocation_type=InvocationType.REQUEST_RESPONSE,
            payload=json.dumps(event_payload).encode(),
        )

    def _map_http_event(self, config: HTTPTriggerConfig,
                        raw_request: Dict[str, Any]) -> Dict[str, Any]:
        """Map an HTTP request to an invocation event."""
        return {
            "httpMethod": raw_request.get("method", "POST"),
            "path": config.route_path,
            "headers": raw_request.get("headers", {}),
            "body": raw_request.get("body", ""),
            "queryStringParameters": raw_request.get("query", {}),
            "isBase64Encoded": False,
        }

    def _map_http_response(self, response_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Map an invocation response to an HTTP response."""
        return {
            "statusCode": response_payload.get("statusCode", 200),
            "headers": response_payload.get("headers", {}),
            "body": response_payload.get("body", ""),
        }

    def _evaluate_timer(self, config: TimerTriggerConfig) -> Optional[float]:
        """Evaluate a timer trigger's next fire time."""
        if config.schedule_expression.startswith("cron("):
            parsed = self._parse_cron(config.schedule_expression)
            return parsed.get("next_fire", None)
        elif config.schedule_expression.startswith("rate("):
            interval = self._parse_rate(config.schedule_expression)
            return time.time() + interval
        return None

    def _parse_cron(self, expression: str) -> Dict[str, Any]:
        """Parse a cron expression into its components."""
        inner = expression.strip("cron()")
        parts = inner.split()
        if len(parts) < 5:
            raise TimerTriggerError(
                f"Invalid cron expression: '{expression}' requires at least 5 fields"
            )
        return {
            "minute": parts[0],
            "hour": parts[1],
            "day_of_month": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
            "year": parts[5] if len(parts) > 5 else "*",
            "next_fire": time.time() + 60,
        }

    def _parse_rate(self, expression: str) -> float:
        """Parse a rate expression to seconds."""
        inner = expression.strip("rate()")
        parts = inner.strip().split()
        if len(parts) != 2:
            raise TimerTriggerError(
                f"Invalid rate expression: '{expression}'"
            )
        value = int(parts[0])
        unit = parts[1].lower().rstrip("s")
        multipliers = {"minute": 60, "hour": 3600, "day": 86400}
        if unit not in multipliers:
            raise TimerTriggerError(
                f"Unknown rate unit '{unit}' in expression '{expression}'"
            )
        return value * multipliers[unit]

    def _poll_queue(self, config: QueueTriggerConfig) -> List[QueueMessage]:
        """Poll messages from a queue trigger source."""
        return []

    def _match_event_pattern(self, pattern: Dict[str, Any],
                             event: Dict[str, Any]) -> bool:
        """Match an event against a trigger pattern.

        Pattern matching follows the EventBridge-style rules:
        - String values must match exactly
        - List values match if the event value is in the list
        - Nested objects are matched recursively
        """
        for key, expected in pattern.items():
            actual = event.get(key)
            if actual is None:
                return False
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif isinstance(expected, dict):
                if not isinstance(actual, dict):
                    return False
                if not self._match_event_pattern(expected, actual):
                    return False
            else:
                if actual != expected:
                    return False
        return True

    def _batch_messages(self, messages: List[QueueMessage],
                        batch_size: int) -> List[List[QueueMessage]]:
        """Batch messages into groups for invocation."""
        batches = []
        for i in range(0, len(messages), batch_size):
            batches.append(messages[i:i + batch_size])
        return batches

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# AutoScaler
# ---------------------------------------------------------------------------

class AutoScaler:
    """Reactive scaling engine for execution environments.

    Tracks concurrent invocations per function, manages burst scaling
    (up to max_burst simultaneous cold starts), enforces account-level
    concurrency limits, and handles throttling when capacity is exhausted.
    """

    def __init__(self, warm_pool: WarmPoolManager,
                 env_manager: ExecutionEnvironmentManager,
                 max_burst: int = MAX_BURST_CONCURRENCY,
                 account_limit: int = MAX_CONCURRENT_ENVIRONMENTS,
                 event_bus: Any = None) -> None:
        self._warm_pool = warm_pool
        self._env_manager = env_manager
        self._max_burst = max_burst
        self._account_limit = account_limit
        self._event_bus = event_bus
        self._active: Dict[str, int] = defaultdict(int)
        self._throttle_counts: Dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def on_invocation_start(self, function_id: str) -> None:
        """Record the start of an invocation."""
        with self._lock:
            self._active[function_id] += 1

    def on_invocation_end(self, function_id: str) -> None:
        """Record the end of an invocation."""
        with self._lock:
            self._active[function_id] = max(0, self._active[function_id] - 1)

    def get_active_count(self, function_id: Optional[str] = None) -> int:
        """Get the current active invocation count."""
        with self._lock:
            if function_id is not None:
                return self._active.get(function_id, 0)
            return sum(self._active.values())

    def check_concurrency(self, function_id: str,
                          reserved: Optional[int]) -> bool:
        """Check if a new invocation is allowed under concurrency limits."""
        with self._lock:
            if not self._check_account_limit():
                self._record_throttle(function_id)
                return False
            if reserved is not None:
                if self._active.get(function_id, 0) >= reserved:
                    self._record_throttle(function_id)
                    return False
            return True

    def scale_up(self, function_id: str, count: int,
                 definition: FunctionDefinition,
                 version: FunctionVersion) -> int:
        """Scale up by creating new execution environments."""
        actual = min(count, self._max_burst)
        created = 0
        for _ in range(actual):
            if not self._check_account_limit():
                break
            env = self._env_manager.create_environment(definition, version)
            self._warm_pool.release(env)
            created += 1
        if created > 0:
            self._emit_event(EventType.LAM_SCALE_UP, {
                "function_id": function_id,
                "count": created,
            })
        return created

    def get_throttle_count(self, function_id: Optional[str] = None) -> int:
        """Get the number of throttled invocations."""
        with self._lock:
            if function_id is not None:
                return self._throttle_counts.get(function_id, 0)
            return sum(self._throttle_counts.values())

    def get_stats(self) -> Dict[str, Any]:
        """Get auto-scaler statistics."""
        with self._lock:
            return {
                "total_active": sum(self._active.values()),
                "account_limit": self._account_limit,
                "max_burst": self._max_burst,
                "total_throttled": sum(self._throttle_counts.values()),
                "per_function_active": dict(self._active),
                "per_function_throttled": dict(self._throttle_counts),
            }

    def _check_account_limit(self) -> bool:
        """Check if the account-level concurrency limit is reached."""
        total = sum(self._active.values())
        return total < self._account_limit

    def _record_throttle(self, function_id: str) -> None:
        """Record a throttle event."""
        self._throttle_counts[function_id] += 1
        self._emit_event(EventType.LAM_INVOCATION_THROTTLED, {
            "function_id": function_id,
        })

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# DeadLetterQueueManager
# ---------------------------------------------------------------------------

class DeadLetterQueueManager:
    """FIFO queue implementation with visibility timeout, DLQ routing,
    replay, and monitoring.

    Each queue supports:
    - Configurable visibility timeout for in-flight messages
    - Maximum receive count before routing to dead letter state
    - Message retention with automatic expiration
    - Replay of dead-letter messages for reprocessing
    - Queue depth monitoring with alert thresholds
    """

    def __init__(self, event_bus: Any = None) -> None:
        self._queues: Dict[str, Dict[str, Any]] = {}
        self._messages: Dict[str, List[QueueMessage]] = defaultdict(list)
        self._event_bus = event_bus

    def create_queue(self, queue_name: str,
                     visibility_timeout: float = DEFAULT_VISIBILITY_TIMEOUT,
                     message_retention: int = DEFAULT_MESSAGE_RETENTION,
                     max_receive_count: int = DEFAULT_MAX_RECEIVE_COUNT) -> None:
        """Create a new queue."""
        self._queues[queue_name] = {
            "visibility_timeout": visibility_timeout,
            "message_retention": message_retention,
            "max_receive_count": max_receive_count,
            "created_at": datetime.now(timezone.utc),
        }

    def delete_queue(self, queue_name: str) -> None:
        """Delete a queue and all its messages."""
        self._queues.pop(queue_name, None)
        self._messages.pop(queue_name, None)

    def send_message(self, queue_name: str, body: bytes,
                     attributes: Optional[Dict[str, Any]] = None) -> QueueMessage:
        """Send a message to a queue."""
        if queue_name not in self._queues:
            self.create_queue(queue_name)
        messages = self._messages[queue_name]
        if len(messages) >= DEFAULT_QUEUE_DEPTH:
            raise QueueFullError(
                f"Queue '{queue_name}' is at maximum depth ({DEFAULT_QUEUE_DEPTH})"
            )
        msg = QueueMessage(
            message_id=str(uuid.uuid4())[:12],
            body=body,
            attributes=attributes or {},
            receipt_handle=str(uuid.uuid4()),
            state=QueueMessageState.AVAILABLE,
            sent_at=datetime.now(timezone.utc),
        )
        messages.append(msg)
        self._emit_event(EventType.LAM_DLQ_MESSAGE_SENT, {
            "queue_name": queue_name,
            "message_id": msg.message_id,
        })
        return msg

    def receive_messages(self, queue_name: str,
                         max_messages: int = 1) -> List[QueueMessage]:
        """Receive messages from a queue with visibility timeout."""
        self._restore_visibility(queue_name)
        self._expire_messages(queue_name)

        messages = self._messages.get(queue_name, [])
        config = self._queues.get(queue_name, {})
        visibility_timeout = config.get("visibility_timeout", DEFAULT_VISIBILITY_TIMEOUT)
        max_receive_count = config.get("max_receive_count", DEFAULT_MAX_RECEIVE_COUNT)

        result = []
        for msg in messages:
            if len(result) >= max_messages:
                break
            if msg.state == QueueMessageState.AVAILABLE:
                msg.state = QueueMessageState.IN_FLIGHT
                msg.receive_count += 1
                msg.receipt_handle = str(uuid.uuid4())
                if msg.first_received_at is None:
                    msg.first_received_at = datetime.now(timezone.utc)
                msg.visibility_deadline = datetime.now(timezone.utc)

                if msg.receive_count >= max_receive_count:
                    msg.state = QueueMessageState.DEAD
                else:
                    result.append(msg)

        for msg in result:
            self._emit_event(EventType.LAM_DLQ_MESSAGE_RECEIVED, {
                "queue_name": queue_name,
                "message_id": msg.message_id,
            })
        return result

    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        """Delete a message by its receipt handle."""
        messages = self._messages.get(queue_name, [])
        for i, msg in enumerate(messages):
            if msg.receipt_handle == receipt_handle:
                messages.pop(i)
                return
        raise QueueMessageNotFoundError(
            f"Message with receipt handle '{receipt_handle}' not found in queue '{queue_name}'"
        )

    def change_visibility(self, queue_name: str, receipt_handle: str,
                          timeout: float) -> None:
        """Change the visibility timeout of an in-flight message."""
        messages = self._messages.get(queue_name, [])
        for msg in messages:
            if msg.receipt_handle == receipt_handle:
                msg.visibility_deadline = datetime.now(timezone.utc)
                return
        raise QueueMessageNotFoundError(
            f"Message with receipt handle '{receipt_handle}' not found"
        )

    def purge_queue(self, queue_name: str) -> int:
        """Purge all messages from a queue."""
        messages = self._messages.get(queue_name, [])
        count = len(messages)
        messages.clear()
        self._emit_event(EventType.LAM_DLQ_PURGED, {
            "queue_name": queue_name,
            "count": count,
        })
        return count

    def replay_message(self, queue_name: str, message_id: str,
                       runtime: Any = None) -> InvocationResponse:
        """Replay a dead-letter message by re-invoking the original function."""
        messages = self._messages.get(queue_name, [])
        target_msg = None
        for msg in messages:
            if msg.message_id == message_id:
                target_msg = msg
                break
        if target_msg is None:
            raise QueueMessageNotFoundError(
                f"Message '{message_id}' not found in queue '{queue_name}'"
            )

        self._emit_event(EventType.LAM_DLQ_MESSAGE_REPLAYED, {
            "queue_name": queue_name,
            "message_id": message_id,
        })

        if runtime is not None:
            function_name = target_msg.attributes.get("function_name", "")
            request = InvocationRequest(
                function_name=function_name,
                payload=target_msg.body,
            )
            response = runtime.invoke(request)
            if response.status_code == 200:
                messages.remove(target_msg)
            return response

        return InvocationResponse(
            status_code=200,
            payload=target_msg.body,
            executed_version="replay",
        )

    def get_queue_stats(self, queue_name: str) -> Dict[str, Any]:
        """Get statistics for a queue."""
        messages = self._messages.get(queue_name, [])
        available = sum(1 for m in messages if m.state == QueueMessageState.AVAILABLE)
        in_flight = sum(1 for m in messages if m.state == QueueMessageState.IN_FLIGHT)
        dead = sum(1 for m in messages if m.state == QueueMessageState.DEAD)

        oldest_age = 0.0
        for msg in messages:
            age = (datetime.now(timezone.utc) - msg.sent_at).total_seconds()
            oldest_age = max(oldest_age, age)

        return {
            "total_messages": len(messages),
            "available": available,
            "in_flight": in_flight,
            "dead": dead,
            "oldest_age_seconds": oldest_age,
        }

    def list_queues(self) -> List[str]:
        """List all queue names."""
        return list(self._queues.keys())

    def _expire_messages(self, queue_name: str) -> int:
        """Remove messages that exceed the retention period."""
        config = self._queues.get(queue_name, {})
        retention = config.get("message_retention", DEFAULT_MESSAGE_RETENTION)
        messages = self._messages.get(queue_name, [])
        cutoff = datetime.now(timezone.utc).timestamp() - retention
        to_remove = [m for m in messages if m.sent_at.timestamp() < cutoff]
        for msg in to_remove:
            messages.remove(msg)
        return len(to_remove)

    def _restore_visibility(self, queue_name: str) -> int:
        """Restore messages whose visibility timeout has expired."""
        config = self._queues.get(queue_name, {})
        visibility_timeout = config.get("visibility_timeout", DEFAULT_VISIBILITY_TIMEOUT)
        messages = self._messages.get(queue_name, [])
        restored = 0
        now = datetime.now(timezone.utc)
        for msg in messages:
            if msg.state == QueueMessageState.IN_FLIGHT:
                if msg.visibility_deadline is not None:
                    elapsed = (now - msg.visibility_deadline).total_seconds()
                    if elapsed >= visibility_timeout:
                        msg.state = QueueMessageState.AVAILABLE
                        msg.visibility_deadline = None
                        restored += 1
        return restored

    def _check_alerts(self, queue_name: str) -> List[str]:
        """Check for queue alert conditions."""
        alerts = []
        stats = self.get_queue_stats(queue_name)
        if stats["total_messages"] > 100:
            alerts.append(f"Queue '{queue_name}' depth exceeds alert threshold")
        if stats["oldest_age_seconds"] > 86400:
            alerts.append(f"Queue '{queue_name}' has messages older than 24 hours")
        return alerts

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# RetryManager
# ---------------------------------------------------------------------------

class RetryManager:
    """Classifies failures, manages exponential backoff retries, and
    routes exhausted invocations to the dead letter queue.

    Failure classification determines the retry strategy:
    - Retryable: Timeout, throttle, transient errors
    - Non-retryable: Code errors, unhandled exceptions
    - Ambiguous: Unknown error types (treated as retryable)
    """

    def __init__(self, dlq_manager: DeadLetterQueueManager,
                 event_bus: Any = None) -> None:
        self._dlq_manager = dlq_manager
        self._event_bus = event_bus
        self._retry_counts: Dict[str, int] = defaultdict(int)
        self._success_count = 0
        self._exhaustion_count = 0

    def handle_failure(self, request: InvocationRequest,
                       response: InvocationResponse,
                       trigger: Optional[TriggerDefinition],
                       function_def: FunctionDefinition) -> Optional[InvocationRequest]:
        """Handle a failed invocation with retry logic."""
        classification = self.classify_failure(response)
        max_retries = trigger.retry_policy.max_retries if trigger else 2
        base_delay = trigger.retry_policy.retry_delay_seconds if trigger else 60

        key = f"{request.function_name}:{request.qualifier}"
        attempt = self._retry_counts.get(key, 0)

        if self.should_retry(attempt, max_retries, classification):
            self._retry_counts[key] = attempt + 1
            self._emit_event(EventType.LAM_RETRY_ATTEMPTED, {
                "function_name": request.function_name,
                "attempt": attempt + 1,
                "classification": classification.value,
            })
            return request

        self.route_to_dlq(request, response, function_def)
        self._retry_counts.pop(key, None)
        return None

    def classify_failure(self, response: InvocationResponse) -> RetryClassification:
        """Classify a failure for retry decisions."""
        if response.function_error == FunctionErrorType.TIMEOUT.value:
            return RetryClassification.RETRYABLE
        if response.function_error == FunctionErrorType.OUT_OF_MEMORY.value:
            return RetryClassification.RETRYABLE
        if response.function_error == FunctionErrorType.UNHANDLED.value:
            return RetryClassification.NON_RETRYABLE
        if response.status_code == 429:
            return RetryClassification.RETRYABLE
        if response.status_code >= 500:
            return RetryClassification.RETRYABLE
        return RetryClassification.AMBIGUOUS

    def compute_delay(self, attempt: int, base_delay: int = 60) -> float:
        """Compute exponential backoff delay with jitter."""
        delay = base_delay * (2 ** attempt)
        jitter = random.uniform(0, delay * 0.1)
        return delay + jitter

    def should_retry(self, attempt: int, max_retries: int,
                     classification: RetryClassification) -> bool:
        """Determine whether a retry should be attempted."""
        if classification == RetryClassification.NON_RETRYABLE:
            return False
        return attempt < max_retries

    def route_to_dlq(self, request: InvocationRequest,
                     response: InvocationResponse,
                     function_def: FunctionDefinition) -> None:
        """Route a failed invocation to the dead letter queue."""
        queue_name = f"dlq-{request.function_name}"
        self._dlq_manager.send_message(
            queue_name,
            request.payload,
            attributes={
                "function_name": request.function_name,
                "qualifier": request.qualifier,
                "error": response.function_error or "unknown",
                "status_code": response.status_code,
            },
        )
        self._exhaustion_count += 1
        self._emit_event(EventType.LAM_RETRY_EXHAUSTED, {
            "function_name": request.function_name,
            "error": response.function_error,
        })

    def record_success(self, request: InvocationRequest) -> None:
        """Record a successful retry."""
        key = f"{request.function_name}:{request.qualifier}"
        if key in self._retry_counts:
            del self._retry_counts[key]
            self._success_count += 1
            self._emit_event(EventType.LAM_RETRY_SUCCEEDED, {
                "function_name": request.function_name,
            })

    def get_stats(self) -> Dict[str, Any]:
        """Get retry statistics."""
        return {
            "pending_retries": len(self._retry_counts),
            "successful_retries": self._success_count,
            "exhausted_retries": self._exhaustion_count,
        }

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# LayerManager
# ---------------------------------------------------------------------------

class LayerManager:
    """Layer lifecycle, composition, and caching integration.

    Layers are versioned packages of shared dependencies that can be
    attached to multiple functions.  Each function may use up to 5 layers
    with a combined uncompressed size of 250 MB.  Layers are composed
    using overlay semantics where later layers take precedence.
    """

    def __init__(self, event_bus: Any = None) -> None:
        self._layers: Dict[str, List[FunctionLayer]] = defaultdict(list)
        self._event_bus = event_bus

    def create_layer(self, name: str, description: str,
                     compatible_runtimes: List[FunctionRuntime],
                     content: bytes) -> FunctionLayer:
        """Create a new layer."""
        layer = FunctionLayer(
            layer_name=name,
            layer_version=1,
            description=description,
            compatible_runtimes=compatible_runtimes,
            content_ref=f"layer://{name}/1",
            content_sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            created_at=datetime.now(timezone.utc),
        )
        self._layers[name].append(layer)
        self._emit_event(EventType.LAM_LAYER_CREATED, {
            "layer_name": name,
            "version": 1,
            "size_bytes": len(content),
        })
        return layer

    def publish_layer(self, layer_name: str) -> FunctionLayer:
        """Publish a new version of an existing layer."""
        versions = self._layers.get(layer_name, [])
        if not versions:
            raise LayerNotFoundError(
                f"Layer '{layer_name}' not found"
            )
        latest = versions[-1]
        new_version = latest.layer_version + 1
        new_layer = FunctionLayer(
            layer_name=layer_name,
            layer_version=new_version,
            description=latest.description,
            compatible_runtimes=latest.compatible_runtimes,
            content_ref=f"layer://{layer_name}/{new_version}",
            content_sha256=latest.content_sha256,
            size_bytes=latest.size_bytes,
            created_at=datetime.now(timezone.utc),
        )
        versions.append(new_layer)
        self._emit_event(EventType.LAM_LAYER_PUBLISHED, {
            "layer_name": layer_name,
            "version": new_version,
        })
        return new_layer

    def get_layer(self, layer_name: str, version: int) -> FunctionLayer:
        """Retrieve a specific layer version."""
        versions = self._layers.get(layer_name, [])
        for layer in versions:
            if layer.layer_version == version:
                return layer
        raise LayerNotFoundError(
            f"Layer '{layer_name}' version {version} not found"
        )

    def get_latest_layer(self, layer_name: str) -> FunctionLayer:
        """Retrieve the latest version of a layer."""
        versions = self._layers.get(layer_name, [])
        if not versions:
            raise LayerNotFoundError(
                f"Layer '{layer_name}' not found"
            )
        return versions[-1]

    def list_layers(self) -> List[FunctionLayer]:
        """List the latest version of all layers."""
        result = []
        for versions in self._layers.values():
            if versions:
                result.append(versions[-1])
        return result

    def delete_layer_version(self, layer_name: str, version: int) -> None:
        """Delete a specific layer version."""
        versions = self._layers.get(layer_name, [])
        for i, layer in enumerate(versions):
            if layer.layer_version == version:
                versions.pop(i)
                return
        raise LayerNotFoundError(
            f"Layer '{layer_name}' version {version} not found"
        )

    def compose_layers(self, layer_refs: List[str]) -> Dict[str, bytes]:
        """Compose multiple layers using overlay semantics."""
        self.validate_layer_limits(layer_refs)
        composed: Dict[str, bytes] = {}
        for ref in layer_refs:
            parts = ref.split(":")
            name = parts[0]
            version = int(parts[1]) if len(parts) > 1 else None
            if version is not None:
                layer = self.get_layer(name, version)
            else:
                layer = self.get_latest_layer(name)
            extracted = self._extract_layer(layer)
            composed = self._merge_layers([composed, extracted])
        return composed

    def validate_layer_limits(self, layer_refs: List[str]) -> None:
        """Validate that layer count and total size are within limits."""
        if len(layer_refs) > MAX_LAYERS:
            raise LayerLimitExceededError(
                f"Function uses {len(layer_refs)} layers, maximum is {MAX_LAYERS}"
            )
        total_size = 0
        for ref in layer_refs:
            parts = ref.split(":")
            name = parts[0]
            version = int(parts[1]) if len(parts) > 1 else None
            try:
                layer = self.get_layer(name, version) if version else self.get_latest_layer(name)
                total_size += layer.size_bytes
            except LayerNotFoundError:
                pass
        if total_size > MAX_LAYER_TOTAL_MB * 1024 * 1024:
            raise LayerLimitExceededError(
                f"Total layer size {total_size} bytes exceeds maximum "
                f"{MAX_LAYER_TOTAL_MB} MB"
            )

    def _compute_content_hash(self, content: bytes) -> str:
        """Compute SHA-256 hash of layer content."""
        return hashlib.sha256(content).hexdigest()

    def _extract_layer(self, layer: FunctionLayer) -> Dict[str, bytes]:
        """Extract a layer into a file map."""
        return {
            f"/opt/{layer.layer_name}/lib": layer.content_ref.encode(),
            f"/opt/{layer.layer_name}/manifest.json": json.dumps({
                "name": layer.layer_name,
                "version": layer.layer_version,
            }).encode(),
        }

    def _merge_layers(self, layers: List[Dict[str, bytes]]) -> Dict[str, bytes]:
        """Merge multiple file maps with later layers taking precedence."""
        merged: Dict[str, bytes] = {}
        for layer_files in layers:
            merged.update(layer_files)
        return merged

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# FunctionPackager
# ---------------------------------------------------------------------------

class FunctionPackager:
    """Integrates function code with the FizzImage build system.

    Generates FizzFile templates, handles inline code packaging, image
    reference resolution, and layer composition for multi-layer functions.
    """

    def __init__(self, layer_manager: LayerManager) -> None:
        self._layer_manager = layer_manager

    def package_function(self, definition: FunctionDefinition) -> str:
        """Package a function for deployment."""
        if definition.code_source.source_type == CodeSourceType.INLINE:
            return self._package_inline(definition.code_source.inline_code)
        elif definition.code_source.source_type == CodeSourceType.IMAGE:
            return self._package_image(definition.code_source.image_reference)
        else:
            return self._package_layers(definition)

    def generate_fizzfile(self, definition: FunctionDefinition) -> str:
        """Generate a FizzFile template for the function."""
        base = self.get_base_image()
        lines = [
            f"FROM {base}",
            f"LABEL runtime={definition.runtime.value}",
            f"LABEL handler={definition.handler}",
            f"ENV FIZZ_MEMORY_MB={definition.memory_mb}",
            f"ENV FIZZ_TIMEOUT={definition.timeout_seconds}",
        ]
        for key, value in definition.environment_variables.items():
            lines.append(f"ENV {key}={value}")
        if definition.code_source.source_type == CodeSourceType.INLINE:
            lines.append(f"COPY handler.py /var/task/handler.py")
        lines.append(f'CMD ["{definition.handler}"]')
        return "\n".join(lines)

    def build_image(self, definition: FunctionDefinition,
                    version: FunctionVersion) -> str:
        """Build a container image for a function version."""
        return f"fizzlambda/{definition.name}:v{version.version_number}"

    def get_base_image(self) -> str:
        """Return the base image for FizzLambda functions."""
        return "fizzregistry.local/fizzlambda-base:latest"

    def _package_inline(self, code: str) -> str:
        """Package inline code into a deployment artifact."""
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:12]
        return f"inline://{code_hash}"

    def _package_image(self, image_ref: str) -> str:
        """Validate and return an image reference."""
        return image_ref

    def _package_layers(self, definition: FunctionDefinition) -> str:
        """Package a layer-composition function."""
        layers = definition.code_source.layer_names
        self._layer_manager.validate_layer_limits(layers)
        return f"layers://{','.join(layers)}"


# ---------------------------------------------------------------------------
# InvocationDispatcher
# ---------------------------------------------------------------------------

class InvocationDispatcher:
    """Central invocation routing engine.

    Validates requests, checks concurrency limits, acquires warm
    execution environments (or triggers cold starts), manages the
    synchronous and asynchronous invocation paths, and records
    metrics for observability.
    """

    def __init__(self, router: InvocationRouter,
                 warm_pool: WarmPoolManager,
                 env_manager: ExecutionEnvironmentManager,
                 auto_scaler: AutoScaler,
                 retry_manager: RetryManager,
                 event_bus: Any = None) -> None:
        self._router = router
        self._warm_pool = warm_pool
        self._env_manager = env_manager
        self._auto_scaler = auto_scaler
        self._retry_manager = retry_manager
        self._event_bus = event_bus
        self._async_queues: Dict[str, deque] = defaultdict(deque)
        self._metrics: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def dispatch(self, request: InvocationRequest) -> InvocationResponse:
        """Dispatch a synchronous invocation."""
        self._validate_request(request)

        if request.invocation_type == InvocationType.DRY_RUN:
            return InvocationResponse(
                status_code=204,
                executed_version="dry_run",
            )

        if request.invocation_type == InvocationType.EVENT:
            return self.dispatch_async(request)

        definition, version = self._router.resolve(
            request.function_name, request.qualifier
        )

        if not self._auto_scaler.check_concurrency(
            definition.function_id,
            definition.concurrency.reserved_concurrency,
        ):
            raise InvocationThrottledError(
                f"Concurrency limit reached for '{request.function_name}'"
            )

        self._auto_scaler.on_invocation_start(definition.function_id)
        self._emit_event(EventType.LAM_INVOCATION_STARTED, {
            "function_name": request.function_name,
            "qualifier": request.qualifier,
        })

        try:
            environment = self._acquire_environment(definition, version)
            response = self._execute(environment, request, definition, version)

            cold_start = environment.invocation_count <= 1
            self._record_metrics(request, response, cold_start)

            if response.status_code == 200:
                self._warm_pool.release(environment)
                self._emit_event(EventType.LAM_INVOCATION_COMPLETED, {
                    "function_name": request.function_name,
                    "duration_ms": response.metrics.duration_ms,
                })
            else:
                self._emit_event(EventType.LAM_INVOCATION_FAILED, {
                    "function_name": request.function_name,
                    "error": response.function_error,
                })

            return response
        finally:
            self._auto_scaler.on_invocation_end(definition.function_id)

    def dispatch_async(self, request: InvocationRequest) -> InvocationResponse:
        """Dispatch an asynchronous invocation."""
        self._validate_request(request, async_mode=True)
        self._enqueue_async(request)
        return InvocationResponse(
            status_code=202,
            payload=json.dumps({"status": "queued"}).encode(),
        )

    def _validate_request(self, request: InvocationRequest,
                          async_mode: bool = False) -> None:
        """Validate an invocation request."""
        if not request.function_name:
            raise InvocationPayloadError("Function name is required")
        max_size = MAX_PAYLOAD_ASYNC_BYTES if async_mode else MAX_PAYLOAD_SYNC_BYTES
        if len(request.payload) > max_size:
            raise InvocationPayloadError(
                f"Payload size {len(request.payload)} exceeds maximum {max_size} bytes"
            )

    def _acquire_environment(self, definition: FunctionDefinition,
                             version: FunctionVersion) -> ExecutionEnvironment:
        """Acquire an execution environment from the warm pool or cold start."""
        env = self._warm_pool.acquire(
            definition.function_id,
            str(version.version_number),
        )
        if env is not None:
            env.state = EnvironmentState.READY
            return env
        return self._env_manager.create_environment(definition, version)

    def _execute(self, environment: ExecutionEnvironment,
                 request: InvocationRequest,
                 definition: FunctionDefinition,
                 version: FunctionVersion) -> InvocationResponse:
        """Execute the invocation in the given environment."""
        context = self._build_context(request, definition, version)
        return self._env_manager.execute_invocation(
            environment, request, context
        )

    def _build_context(self, request: InvocationRequest,
                       definition: FunctionDefinition,
                       version: FunctionVersion) -> FunctionContext:
        """Build the function context for an invocation."""
        return FunctionContext(
            invocation_id=str(uuid.uuid4()),
            function_name=request.function_name,
            function_version=str(version.version_number),
            memory_limit_mb=definition.memory_mb,
            timeout_seconds=definition.timeout_seconds,
            start_time=time.time(),
            log_group=f"/fizzlambda/{request.function_name}",
            trace_id=str(uuid.uuid4()),
            client_context=request.client_context,
        )

    def _record_metrics(self, request: InvocationRequest,
                        response: InvocationResponse,
                        cold_start: bool) -> None:
        """Record invocation metrics."""
        metric = {
            "function_name": request.function_name,
            "status_code": response.status_code,
            "duration_ms": response.metrics.duration_ms,
            "billed_duration_ms": response.metrics.billed_duration_ms,
            "memory_used_mb": response.metrics.memory_used_mb,
            "cold_start": cold_start,
            "timestamp": time.time(),
        }
        self._metrics[request.function_name].append(metric)
        if len(self._metrics[request.function_name]) > 10000:
            self._metrics[request.function_name] = \
                self._metrics[request.function_name][-10000:]

    def _enqueue_async(self, request: InvocationRequest) -> None:
        """Enqueue an async invocation request."""
        queue = self._async_queues[request.function_name]
        if len(queue) >= DEFAULT_QUEUE_DEPTH:
            raise QueueFullError(
                f"Async queue for '{request.function_name}' is at capacity"
            )
        queue.append(request)

    def _drain_queue(self, function_id: str) -> None:
        """Drain the async invocation queue for a function."""
        queue = self._async_queues.get(function_id, deque())
        while queue:
            request = queue.popleft()
            try:
                self.dispatch(request)
            except Exception:
                logger.debug("Async invocation failed for %s", function_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get dispatcher statistics."""
        return {
            "total_invocations": sum(
                len(m) for m in self._metrics.values()
            ),
            "async_queue_depth": sum(
                len(q) for q in self._async_queues.values()
            ),
            "functions_invoked": len(self._metrics),
        }

    def get_function_metrics(self, function_name: str) -> Dict[str, Any]:
        """Get metrics for a specific function."""
        metrics = self._metrics.get(function_name, [])
        if not metrics:
            return {
                "invocation_count": 0,
                "error_count": 0,
                "avg_duration_ms": 0.0,
                "cold_start_count": 0,
            }
        errors = sum(1 for m in metrics if m["status_code"] != 200)
        durations = [m["duration_ms"] for m in metrics]
        cold_starts = sum(1 for m in metrics if m.get("cold_start", False))
        return {
            "invocation_count": len(metrics),
            "error_count": errors,
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0.0,
            "p50_duration_ms": sorted(durations)[len(durations) // 2] if durations else 0.0,
            "p99_duration_ms": sorted(durations)[int(len(durations) * 0.99)] if durations else 0.0,
            "cold_start_count": cold_starts,
            "cold_start_rate": cold_starts / len(metrics) if metrics else 0.0,
        }

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.emit(event_type, data)
            except Exception:
                logger.debug("Failed to emit event %s", event_type)


# ---------------------------------------------------------------------------
# BuiltinFunctions
# ---------------------------------------------------------------------------

class BuiltinFunctions:
    """Pre-built serverless functions for FizzBuzz evaluation.

    These seven functions demonstrate the full capabilities of the
    FizzLambda runtime applied to the FizzBuzz evaluation domain:

    1. standard-eval: Canonical modulo-based FizzBuzz evaluation
    2. configurable-eval: User-defined divisor/label pairs
    3. ml-eval: Machine learning-based FizzBuzz classification
    4. batch-eval: Batch processing of number ranges
    5. scheduled-report: Periodic FizzBuzz summary generation
    6. cache-invalidation: Cache coherence management
    7. audit-log: Compliance audit trail generation
    """

    @staticmethod
    def standard_evaluation_handler(event: dict, context: FunctionContext) -> dict:
        """Standard FizzBuzz evaluation using the modulo algorithm."""
        number = event.get("number", 0)
        if not isinstance(number, int) or number <= 0:
            return {"error": "Invalid number", "number": number}
        result = str(number)
        if number % 15 == 0:
            result = "FizzBuzz"
        elif number % 3 == 0:
            result = "Fizz"
        elif number % 5 == 0:
            result = "Buzz"
        return {
            "number": number,
            "result": result,
            "function": "standard-eval",
            "version": context.function_version,
            "remaining_ms": context.timeout_remaining_ms,
        }

    @staticmethod
    def configurable_evaluation_handler(event: dict, context: FunctionContext) -> dict:
        """Configurable FizzBuzz evaluation with user-defined rules."""
        number = event.get("number", 0)
        rules = event.get("rules", [{"divisor": 3, "label": "Fizz"}, {"divisor": 5, "label": "Buzz"}])
        if not isinstance(number, int) or number <= 0:
            return {"error": "Invalid number", "number": number}
        labels = []
        for rule in rules:
            if number % rule["divisor"] == 0:
                labels.append(rule["label"])
        result = "".join(labels) if labels else str(number)
        return {"number": number, "result": result, "rules_matched": len(labels)}

    @staticmethod
    def ml_evaluation_handler(event: dict, context: FunctionContext) -> dict:
        """ML-based FizzBuzz classification using simulated inference."""
        number = event.get("number", 0)
        if not isinstance(number, int) or number <= 0:
            return {"error": "Invalid number", "number": number}
        features = [number % 3, number % 5, number % 15]
        if features[2] == 0:
            prediction = "FizzBuzz"
            confidence = 0.99
        elif features[0] == 0:
            prediction = "Fizz"
            confidence = 0.97
        elif features[1] == 0:
            prediction = "Buzz"
            confidence = 0.98
        else:
            prediction = str(number)
            confidence = 0.95
        return {
            "number": number,
            "prediction": prediction,
            "confidence": confidence,
            "model": "fizz-nn-v3",
        }

    @staticmethod
    def batch_evaluation_handler(event: dict, context: FunctionContext) -> dict:
        """Batch FizzBuzz evaluation for number ranges."""
        start = event.get("start", 1)
        end = event.get("end", 100)
        results = []
        for n in range(start, end + 1):
            if n % 15 == 0:
                results.append({"number": n, "result": "FizzBuzz"})
            elif n % 3 == 0:
                results.append({"number": n, "result": "Fizz"})
            elif n % 5 == 0:
                results.append({"number": n, "result": "Buzz"})
            else:
                results.append({"number": n, "result": str(n)})
        return {"count": len(results), "results": results}

    @staticmethod
    def scheduled_report_handler(event: dict, context: FunctionContext) -> dict:
        """Generate a periodic FizzBuzz evaluation summary."""
        range_size = event.get("range_size", 1000)
        fizz_count = sum(1 for n in range(1, range_size + 1) if n % 3 == 0 and n % 5 != 0)
        buzz_count = sum(1 for n in range(1, range_size + 1) if n % 5 == 0 and n % 3 != 0)
        fizzbuzz_count = sum(1 for n in range(1, range_size + 1) if n % 15 == 0)
        plain_count = range_size - fizz_count - buzz_count - fizzbuzz_count
        return {
            "range": f"1-{range_size}",
            "fizz": fizz_count,
            "buzz": buzz_count,
            "fizzbuzz": fizzbuzz_count,
            "plain": plain_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def cache_invalidation_handler(event: dict, context: FunctionContext) -> dict:
        """Handle cache invalidation events."""
        keys = event.get("keys", [])
        return {
            "invalidated": len(keys),
            "keys": keys,
            "action": "cache_invalidation",
        }

    @staticmethod
    def audit_log_handler(event: dict, context: FunctionContext) -> dict:
        """Generate compliance audit log entries."""
        operation = event.get("operation", "evaluation")
        return {
            "audit_id": str(uuid.uuid4()),
            "operation": operation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "function_name": context.function_name,
            "function_version": context.function_version,
            "compliance_status": "compliant",
        }

    @classmethod
    def get_definitions(cls) -> List[FunctionDefinition]:
        """Return definitions for all built-in functions."""
        return [
            FunctionDefinition(
                name="standard-eval",
                handler="builtins.standard_evaluation_handler",
                code_source=CodeSource(source_type=CodeSourceType.INLINE,
                                       inline_code="standard_eval"),
                tags={"builtin": "true", "category": "evaluation"},
            ),
            FunctionDefinition(
                name="configurable-eval",
                handler="builtins.configurable_evaluation_handler",
                code_source=CodeSource(source_type=CodeSourceType.INLINE,
                                       inline_code="configurable_eval"),
                tags={"builtin": "true", "category": "evaluation"},
            ),
            FunctionDefinition(
                name="ml-eval",
                handler="builtins.ml_evaluation_handler",
                memory_mb=512,
                code_source=CodeSource(source_type=CodeSourceType.INLINE,
                                       inline_code="ml_eval"),
                tags={"builtin": "true", "category": "ml"},
            ),
            FunctionDefinition(
                name="batch-eval",
                handler="builtins.batch_evaluation_handler",
                memory_mb=512,
                timeout_seconds=60,
                code_source=CodeSource(source_type=CodeSourceType.INLINE,
                                       inline_code="batch_eval"),
                tags={"builtin": "true", "category": "batch"},
            ),
            FunctionDefinition(
                name="scheduled-report",
                handler="builtins.scheduled_report_handler",
                timeout_seconds=120,
                code_source=CodeSource(source_type=CodeSourceType.INLINE,
                                       inline_code="scheduled_report"),
                tags={"builtin": "true", "category": "reporting"},
            ),
            FunctionDefinition(
                name="cache-invalidation",
                handler="builtins.cache_invalidation_handler",
                code_source=CodeSource(source_type=CodeSourceType.INLINE,
                                       inline_code="cache_invalidation"),
                tags={"builtin": "true", "category": "maintenance"},
            ),
            FunctionDefinition(
                name="audit-log",
                handler="builtins.audit_log_handler",
                code_source=CodeSource(source_type=CodeSourceType.INLINE,
                                       inline_code="audit_log"),
                tags={"builtin": "true", "category": "compliance"},
            ),
        ]

    @classmethod
    def get_triggers(cls) -> List[TriggerDefinition]:
        """Return trigger definitions for built-in functions."""
        return [
            TriggerDefinition(
                function_name="standard-eval",
                trigger_type=TriggerType.HTTP,
                trigger_config={
                    "route_path": "/api/fizzbuzz/evaluate",
                    "http_methods": ["POST"],
                    "auth_type": "none",
                },
            ),
            TriggerDefinition(
                function_name="batch-eval",
                trigger_type=TriggerType.QUEUE,
                trigger_config={
                    "queue_name": "fizzbuzz-batch-queue",
                    "batch_size": 10,
                },
            ),
            TriggerDefinition(
                function_name="scheduled-report",
                trigger_type=TriggerType.TIMER,
                trigger_config={
                    "schedule_expression": "rate(1 hour)",
                },
            ),
            TriggerDefinition(
                function_name="cache-invalidation",
                trigger_type=TriggerType.EVENT_BUS,
                trigger_config={
                    "event_pattern": {"source": ["fizzbuzz.cache"], "detail-type": ["CacheInvalidation"]},
                },
            ),
        ]

    @classmethod
    def get_layers(cls) -> List[FunctionLayer]:
        """Return layer definitions for built-in functions."""
        return [
            FunctionLayer(
                layer_name="fizzbuzz-commons",
                description="Shared FizzBuzz evaluation utilities and helpers",
                compatible_runtimes=[FunctionRuntime.PYTHON_312, FunctionRuntime.FIZZLANG],
                content_ref="layer://fizzbuzz-commons/1",
                size_bytes=1024 * 100,
            ),
            FunctionLayer(
                layer_name="fizzbuzz-ml-deps",
                description="Machine learning model weights and inference runtime",
                compatible_runtimes=[FunctionRuntime.PYTHON_312],
                content_ref="layer://fizzbuzz-ml-deps/1",
                size_bytes=1024 * 1024 * 50,
            ),
        ]


# ---------------------------------------------------------------------------
# FizzLambdaRuntime
# ---------------------------------------------------------------------------

class FizzLambdaRuntime:
    """Top-level runtime engine for the FizzLambda serverless platform.

    Wires all components together and manages the complete function
    lifecycle from registration through invocation, scaling, and teardown.
    Provides a unified API surface for the middleware and CLI layers.
    """

    def __init__(self,
                 max_total_environments: int = DEFAULT_MAX_ENVIRONMENTS,
                 max_per_function: int = DEFAULT_MAX_PER_FUNCTION,
                 idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
                 max_burst: int = MAX_BURST_CONCURRENCY,
                 account_limit: int = MAX_CONCURRENT_ENVIRONMENTS,
                 snapshot_enabled: bool = True,
                 predictive_enabled: bool = True,
                 layer_cache_size_mb: int = 10240,
                 event_bus: Any = None) -> None:
        self._event_bus = event_bus
        self._started = False

        self._resource_allocator = ResourceAllocator()
        self._registry = FunctionRegistry(event_bus=event_bus)
        self._version_manager = FunctionVersionManager(
            self._registry, event_bus=event_bus
        )
        self._alias_manager = AliasManager(
            self._version_manager, event_bus=event_bus
        )
        self._traffic_shift = TrafficShiftOrchestrator(
            self._alias_manager, event_bus=event_bus
        )
        self._env_manager = ExecutionEnvironmentManager(
            self._resource_allocator, event_bus=event_bus
        )
        self._warm_pool = WarmPoolManager(
            self._env_manager,
            max_total=max_total_environments,
            max_per_function=max_per_function,
            idle_timeout=idle_timeout,
            event_bus=event_bus,
        )
        self._cold_start_optimizer = ColdStartOptimizer(
            self._env_manager, self._warm_pool,
            snapshot_enabled=snapshot_enabled,
            predictive_enabled=predictive_enabled,
            layer_cache_size_mb=layer_cache_size_mb,
            event_bus=event_bus,
        )
        self._router = InvocationRouter(
            self._registry, self._version_manager, self._alias_manager
        )
        self._dlq_manager = DeadLetterQueueManager(event_bus=event_bus)
        self._retry_manager = RetryManager(self._dlq_manager, event_bus=event_bus)
        self._auto_scaler = AutoScaler(
            self._warm_pool, self._env_manager,
            max_burst=max_burst,
            account_limit=account_limit,
            event_bus=event_bus,
        )
        self._trigger_manager = EventTriggerManager(event_bus=event_bus)
        self._layer_manager = LayerManager(event_bus=event_bus)
        self._packager = FunctionPackager(self._layer_manager)
        self._dispatcher = InvocationDispatcher(
            self._router, self._warm_pool, self._env_manager,
            self._auto_scaler, self._retry_manager, event_bus=event_bus,
        )
        self._builtin_handlers: Dict[str, Callable] = {}

    # -- Function lifecycle --

    def create_function(self, definition: FunctionDefinition) -> FunctionDefinition:
        """Create a new serverless function."""
        return self._registry.create_function(definition)

    def update_function(self, name: str, updates: Dict[str, Any]) -> FunctionDefinition:
        """Update a function's configuration."""
        return self._registry.update_function(name, updates)

    def delete_function(self, name: str) -> None:
        """Delete a function and clean up associated resources."""
        self._registry.delete_function(name)

    def get_function(self, name: str) -> FunctionDefinition:
        """Retrieve a function definition."""
        return self._registry.get_function(name)

    def list_functions(self) -> List[FunctionDefinition]:
        """List all registered functions."""
        return self._registry.list_functions()

    def publish_version(self, name: str, description: str = "") -> FunctionVersion:
        """Publish a new immutable version of a function."""
        return self._version_manager.publish_version(name, description)

    def list_versions(self, name: str) -> List[FunctionVersion]:
        """List all versions of a function."""
        return self._version_manager.list_versions(name)

    # -- Alias management --

    def create_alias(self, function_name: str, alias_name: str,
                     version: int) -> FunctionAlias:
        """Create a new alias for a function."""
        return self._alias_manager.create_alias(function_name, alias_name, version)

    def update_alias(self, function_name: str, alias_name: str, version: int,
                     additional_version: Optional[int] = None,
                     weight: float = 0.0) -> FunctionAlias:
        """Update an alias's target version."""
        return self._alias_manager.update_alias(
            function_name, alias_name, version,
            additional_version=additional_version,
            additional_version_weight=weight,
        )

    def list_aliases(self, function_name: str) -> List[FunctionAlias]:
        """List all aliases for a function."""
        return self._alias_manager.list_aliases(function_name)

    # -- Invocation --

    def invoke(self, request: InvocationRequest) -> InvocationResponse:
        """Invoke a function synchronously."""
        return self._dispatcher.dispatch(request)

    def invoke_async(self, request: InvocationRequest) -> InvocationResponse:
        """Invoke a function asynchronously."""
        request.invocation_type = InvocationType.EVENT
        return self._dispatcher.dispatch_async(request)

    # -- Triggers --

    def create_trigger(self, trigger: TriggerDefinition) -> TriggerDefinition:
        """Register an event trigger."""
        return self._trigger_manager.create_trigger(trigger)

    def list_triggers(self, function_name: str) -> List[TriggerDefinition]:
        """List triggers for a function."""
        return self._trigger_manager.list_triggers(function_name)

    def enable_trigger(self, trigger_id: str) -> None:
        """Enable an event trigger."""
        self._trigger_manager.enable_trigger(trigger_id)

    def disable_trigger(self, trigger_id: str) -> None:
        """Disable an event trigger."""
        self._trigger_manager.disable_trigger(trigger_id)

    # -- Layers --

    def create_layer(self, name: str, description: str,
                     runtimes: List[FunctionRuntime], content: bytes) -> FunctionLayer:
        """Create a new dependency layer."""
        return self._layer_manager.create_layer(name, description, runtimes, content)

    def publish_layer(self, name: str) -> FunctionLayer:
        """Publish a new version of a layer."""
        return self._layer_manager.publish_layer(name)

    def list_layers(self) -> List[FunctionLayer]:
        """List all layers."""
        return self._layer_manager.list_layers()

    # -- Queues / DLQ --

    def list_queues(self) -> List[str]:
        """List all dead letter queues."""
        return self._dlq_manager.list_queues()

    def receive_queue_messages(self, queue_name: str,
                                max_messages: int = 1) -> List[QueueMessage]:
        """Receive messages from a queue."""
        return self._dlq_manager.receive_messages(queue_name, max_messages)

    def replay_queue_message(self, queue_name: str,
                              message_id: str) -> InvocationResponse:
        """Replay a dead-letter message."""
        return self._dlq_manager.replay_message(queue_name, message_id, self)

    def purge_queue(self, queue_name: str) -> int:
        """Purge all messages from a queue."""
        return self._dlq_manager.purge_queue(queue_name)

    # -- Observability --

    def get_warm_pool_stats(self) -> Dict[str, Any]:
        """Get warm pool statistics."""
        return self._warm_pool.get_stats()

    def get_concurrency_stats(self) -> Dict[str, Any]:
        """Get concurrency and scaling statistics."""
        return self._auto_scaler.get_stats()

    def get_cold_start_stats(self) -> Dict[str, Any]:
        """Get cold start optimization statistics."""
        return self._cold_start_optimizer.get_cold_start_stats()

    def get_function_metrics(self, name: str) -> Dict[str, Any]:
        """Get invocation metrics for a function."""
        return self._dispatcher.get_function_metrics(name)

    def get_function_logs(self, name: str, tail: int = 20) -> List[str]:
        """Get recent invocation logs for a function."""
        return self._env_manager.get_logs(name, tail)

    # -- Lifecycle --

    def register_builtins(self) -> None:
        """Register all built-in functions, triggers, and layers."""
        builtins = BuiltinFunctions()

        handler_map = {
            "standard-eval": builtins.standard_evaluation_handler,
            "configurable-eval": builtins.configurable_evaluation_handler,
            "ml-eval": builtins.ml_evaluation_handler,
            "batch-eval": builtins.batch_evaluation_handler,
            "scheduled-report": builtins.scheduled_report_handler,
            "cache-invalidation": builtins.cache_invalidation_handler,
            "audit-log": builtins.audit_log_handler,
        }

        for defn in builtins.get_definitions():
            self.create_function(defn)
            self.publish_version(defn.name, f"Built-in {defn.name} v1")
            if defn.name in handler_map:
                self._builtin_handlers[defn.name] = handler_map[defn.name]

        for trigger in builtins.get_triggers():
            self.create_trigger(trigger)

        for layer in builtins.get_layers():
            self._layer_manager.create_layer(
                layer.layer_name,
                layer.description,
                layer.compatible_runtimes,
                layer.content_ref.encode(),
            )

        logger.info("Registered %d built-in functions", len(builtins.get_definitions()))

    def start(self) -> None:
        """Initialize the runtime and register built-in functions."""
        if self._started:
            return
        self.register_builtins()
        self._started = True
        logger.info("FizzLambda runtime v%s started", FIZZLAMBDA_VERSION)

    def stop(self) -> None:
        """Shut down the runtime and clean up resources."""
        self._warm_pool.evict_idle()
        self._started = False
        logger.info("FizzLambda runtime stopped")


# ---------------------------------------------------------------------------
# FizzLambdaCognitiveLoadGate
# ---------------------------------------------------------------------------

class FizzLambdaCognitiveLoadGate:
    """Deployment gating based on operator cognitive load.

    Integrates with FizzBob's NASA-TLX cognitive load assessment model
    to prevent deployments when the operator's cognitive load exceeds
    the configured threshold.  Emergency deployments may bypass this
    gate when operational necessity outweighs the risk of operator error.
    """

    def __init__(self, max_tlx_score: float = 65.0) -> None:
        self._max_tlx_score = max_tlx_score
        self._bypassed = False
        self._current_score = random.uniform(30.0, 55.0)

    def check_deployment(self, operation: str) -> bool:
        """Check if a deployment operation is allowed."""
        if self._bypassed:
            return True
        if self._current_score > self._max_tlx_score:
            raise FizzLambdaCognitiveLoadError(
                f"Deployment blocked: operator cognitive load ({self._current_score:.1f}) "
                f"exceeds threshold ({self._max_tlx_score:.1f}) for operation '{operation}'"
            )
        return True

    def bypass_emergency(self) -> None:
        """Enable emergency bypass for critical deployments."""
        self._bypassed = True
        logger.warning("Cognitive load gate bypassed for emergency deployment")


# ---------------------------------------------------------------------------
# FizzLambdaComplianceEngine
# ---------------------------------------------------------------------------

class FizzLambdaComplianceEngine:
    """Extends SOX/GDPR/HIPAA compliance to serverless operations.

    Ensures that all serverless function deployments, invocations, and
    data processing operations comply with regulatory requirements.
    Maintains an audit trail and validates data classification and
    network isolation requirements.
    """

    def __init__(self) -> None:
        self._audit_trail: List[Dict[str, Any]] = []

    def log_deployment(self, function_name: str, version: int,
                       operator: str) -> None:
        """Record a deployment operation in the compliance audit trail."""
        self._audit_trail.append({
            "event": "deployment",
            "function_name": function_name,
            "version": version,
            "operator": operator,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sox_compliant": True,
        })

    def check_data_classification(self, definition: FunctionDefinition) -> bool:
        """Verify that functions handling classified data have proper controls."""
        classification = definition.tags.get("data_classification", "public")
        if classification in ("confidential", "restricted"):
            if definition.vpc_config is None:
                raise FizzLambdaComplianceError(
                    f"Function '{definition.name}' processes {classification} data "
                    f"but does not have VPC isolation configured"
                )
        return True

    def validate_vpc_requirement(self, definition: FunctionDefinition) -> bool:
        """Validate VPC configuration for compliance-sensitive functions."""
        if definition.tags.get("hipaa", "false") == "true":
            if definition.vpc_config is None:
                raise FizzLambdaComplianceError(
                    f"HIPAA-tagged function '{definition.name}' requires VPC isolation"
                )
        return True


# ---------------------------------------------------------------------------
# FizzLambdaDashboard
# ---------------------------------------------------------------------------

class FizzLambdaDashboard:
    """ASCII dashboard rendering for FizzLambda operational visibility.

    Renders warm pool status, concurrency utilization, cold start metrics,
    function inventory, queue status, alias routing, trigger configuration,
    and layer information as structured ASCII tables.
    """

    def __init__(self, runtime: FizzLambdaRuntime,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._runtime = runtime
        self._width = width

    def render_functions(self) -> str:
        """Render the function inventory table."""
        functions = self._runtime.list_functions()
        headers = ["Name", "Runtime", "Memory", "Timeout", "Versions"]
        rows = []
        for f in functions:
            versions = self._runtime.list_versions(f.name)
            rows.append([
                f.name,
                f.runtime.value,
                f"{f.memory_mb} MB",
                f"{f.timeout_seconds}s",
                str(len(versions)),
            ])
        return self._render_section(
            "FizzLambda Functions",
            self._render_table(headers, rows) if rows else "(no functions registered)"
        )

    def render_warm_pool(self) -> str:
        """Render warm pool status."""
        stats = self._runtime.get_warm_pool_stats()
        content = "\n".join([
            f"  Total Environments : {stats['total_environments']} / {stats['max_total']}",
            f"  Hit Rate           : {stats['hit_rate']:.1%}",
            f"  Hits / Misses      : {stats['hits']} / {stats['misses']}",
            f"  Functions Tracked  : {stats['functions']}",
            f"  Idle Timeout       : {stats['idle_timeout']:.0f}s",
            "",
            f"  Utilization: {self._render_bar(stats['total_environments'], stats['max_total'], 30)}",
        ])
        return self._render_section("Warm Pool Status", content)

    def render_concurrency(self) -> str:
        """Render concurrency utilization."""
        stats = self._runtime.get_concurrency_stats()
        content = "\n".join([
            f"  Active Executions  : {stats['total_active']} / {stats['account_limit']}",
            f"  Max Burst          : {stats['max_burst']}",
            f"  Total Throttled    : {stats['total_throttled']}",
            "",
            f"  Utilization: {self._render_bar(stats['total_active'], stats['account_limit'], 30)}",
        ])
        return self._render_section("Concurrency Utilization", content)

    def render_cold_starts(self) -> str:
        """Render cold start optimization metrics."""
        stats = self._runtime.get_cold_start_stats()
        content = "\n".join([
            f"  Snapshot Enabled   : {stats['snapshot_enabled']}",
            f"  Predictive Enabled : {stats['predictive_enabled']}",
            f"  Snapshots Stored   : {stats['snapshots_stored']}",
            f"  Snapshot Hit Rate  : {stats['snapshot_hit_rate']:.1%}",
            f"  Layer Cache Entries : {stats['layer_cache_entries']}",
            f"  Layer Cache Usage  : {stats['layer_cache_bytes'] / (1024*1024):.1f} MB / {stats['layer_cache_capacity_mb']} MB",
            f"  Avg Cold Start     : {stats['avg_cold_start_ms']:.1f} ms",
        ])
        return self._render_section("Cold Start Optimization", content)

    def render_metrics(self, function_name: str) -> str:
        """Render invocation metrics for a function."""
        metrics = self._runtime.get_function_metrics(function_name)
        content = "\n".join([
            f"  Function           : {function_name}",
            f"  Invocation Count   : {metrics['invocation_count']}",
            f"  Error Count        : {metrics['error_count']}",
            f"  Avg Duration       : {metrics['avg_duration_ms']:.1f} ms",
            f"  Cold Start Count   : {metrics['cold_start_count']}",
        ])
        return self._render_section(f"Metrics: {function_name}", content)

    def render_logs(self, function_name: str) -> str:
        """Render recent invocation logs for a function."""
        logs = self._runtime.get_function_logs(function_name)
        if not logs:
            content = "  (no logs available)"
        else:
            content = "\n".join(f"  {line}" for line in logs)
        return self._render_section(f"Logs: {function_name}", content)

    def render_queues(self) -> str:
        """Render queue status."""
        queues = self._runtime.list_queues()
        if not queues:
            return self._render_section("Queues", "  (no queues)")
        headers = ["Queue", "Total", "Available", "In-Flight", "Dead"]
        rows = []
        for q in queues:
            stats = self._runtime._dlq_manager.get_queue_stats(q)
            rows.append([
                q,
                str(stats["total_messages"]),
                str(stats["available"]),
                str(stats["in_flight"]),
                str(stats["dead"]),
            ])
        return self._render_section("Queues", self._render_table(headers, rows))

    def render_aliases(self, function_name: str) -> str:
        """Render alias routing for a function."""
        aliases = self._runtime.list_aliases(function_name)
        if not aliases:
            return self._render_section(
                f"Aliases: {function_name}", "  (no aliases)"
            )
        headers = ["Alias", "Version", "Additional", "Weight"]
        rows = []
        for a in aliases:
            rows.append([
                a.alias_name,
                str(a.function_version),
                str(a.additional_version or "-"),
                f"{a.additional_version_weight:.0%}" if a.additional_version else "-",
            ])
        return self._render_section(
            f"Aliases: {function_name}",
            self._render_table(headers, rows),
        )

    def render_triggers(self, function_name: str) -> str:
        """Render trigger configuration for a function."""
        triggers = self._runtime.list_triggers(function_name)
        if not triggers:
            return self._render_section(
                f"Triggers: {function_name}", "  (no triggers)"
            )
        headers = ["ID", "Type", "Enabled", "Qualifier"]
        rows = []
        for t in triggers:
            rows.append([
                t.trigger_id[:12],
                t.trigger_type.value,
                "Y" if t.enabled else "N",
                t.qualifier,
            ])
        return self._render_section(
            f"Triggers: {function_name}",
            self._render_table(headers, rows),
        )

    def render_layers(self) -> str:
        """Render layer inventory."""
        layers = self._runtime.list_layers()
        if not layers:
            return self._render_section("Layers", "  (no layers)")
        headers = ["Name", "Version", "Size", "Runtimes"]
        rows = []
        for layer in layers:
            runtimes = ", ".join(r.value for r in layer.compatible_runtimes)
            size_str = f"{layer.size_bytes / 1024:.0f} KB" if layer.size_bytes < 1024 * 1024 else f"{layer.size_bytes / (1024*1024):.1f} MB"
            rows.append([
                layer.layer_name,
                str(layer.layer_version),
                size_str,
                runtimes,
            ])
        return self._render_section("Layers", self._render_table(headers, rows))

    def render_dashboard(self) -> str:
        """Render the complete FizzLambda dashboard."""
        parts = [
            self._render_section(
                "FizzLambda Serverless Runtime v" + FIZZLAMBDA_VERSION,
                f"  Status: {'RUNNING' if self._runtime._started else 'STOPPED'}"
            ),
            self.render_functions(),
            self.render_warm_pool(),
            self.render_concurrency(),
            self.render_cold_starts(),
        ]
        return "\n".join(parts)

    def _render_bar(self, value: float, max_value: float, width: int) -> str:
        """Render a horizontal bar chart."""
        if max_value <= 0:
            return "[" + " " * width + "]"
        ratio = min(value / max_value, 1.0)
        filled = int(ratio * width)
        return "[" + "#" * filled + " " * (width - filled) + f"] {ratio:.0%}"

    def _render_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Render a formatted ASCII table."""
        if not rows:
            return "(empty)"
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(cell))
        header_line = "  " + " | ".join(
            h.ljust(col_widths[i]) for i, h in enumerate(headers)
        )
        sep_line = "  " + "-+-".join("-" * w for w in col_widths)
        row_lines = []
        for row in rows:
            cells = []
            for i, cell in enumerate(row):
                w = col_widths[i] if i < len(col_widths) else len(cell)
                cells.append(cell.ljust(w))
            row_lines.append("  " + " | ".join(cells))
        return "\n".join([header_line, sep_line] + row_lines)

    def _render_section(self, title: str, content: str) -> str:
        """Render a dashboard section with a title border."""
        border = "=" * self._width
        return f"\n{border}\n  {title}\n{border}\n{content}\n"


# ---------------------------------------------------------------------------
# FizzLambdaMiddleware
# ---------------------------------------------------------------------------

class FizzLambdaMiddleware(IMiddleware):
    """FizzLambda middleware for the evaluation pipeline.

    Integrates the FizzLambda serverless function runtime with the
    platform's middleware pipeline.  Annotates evaluation responses
    with serverless metadata headers and routes evaluations between
    the container path and the serverless path based on the configured
    mode.
    """

    def __init__(self, runtime: FizzLambdaRuntime,
                 dashboard: FizzLambdaDashboard,
                 mode: str = "container") -> None:
        self._runtime = runtime
        self._dashboard = dashboard
        self._mode = mode
        self._evaluation_count = 0

    def get_name(self) -> str:
        """Return the middleware name."""
        return "FizzLambdaMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    def process(self, context: ProcessingContext,
                next_handler: Callable[[ProcessingContext], ProcessingContext]) -> ProcessingContext:
        """Process the context through the serverless evaluation path."""
        self._evaluation_count += 1

        if self._should_use_serverless(context):
            request = InvocationRequest(
                function_name="standard-eval",
                payload=json.dumps({"number": context.number}).encode(),
            )
            try:
                response = self._runtime.invoke(request)
                if context.results:
                    self._annotate_response(context.results[-1], response)
                self._emit_event(EventType.LAM_EVALUATION_PROCESSED, {
                    "number": context.number,
                    "mode": "serverless",
                })
            except Exception:
                logger.debug("Serverless evaluation failed, falling back to container path")
                context = next_handler(context)
        else:
            context = next_handler(context)

        context.metadata["fizzlambda_mode"] = self._mode
        context.metadata["fizzlambda_version"] = FIZZLAMBDA_VERSION
        return context

    def render_dashboard(self) -> str:
        """Render the FizzLambda dashboard."""
        return self._dashboard.render_dashboard()

    def render_functions(self) -> str:
        """Render the function list."""
        return self._dashboard.render_functions()

    def render_warm_pool(self) -> str:
        """Render warm pool status."""
        return self._dashboard.render_warm_pool()

    def render_concurrency(self) -> str:
        """Render concurrency utilization."""
        return self._dashboard.render_concurrency()

    def render_cold_starts(self) -> str:
        """Render cold start metrics."""
        return self._dashboard.render_cold_starts()

    def render_metrics(self, function_name: str) -> str:
        """Render function metrics."""
        return self._dashboard.render_metrics(function_name)

    def render_logs(self, function_name: str) -> str:
        """Render function logs."""
        return self._dashboard.render_logs(function_name)

    def render_queues(self) -> str:
        """Render queue status."""
        return self._dashboard.render_queues()

    def render_aliases(self, function_name: str) -> str:
        """Render alias routing."""
        return self._dashboard.render_aliases(function_name)

    def render_triggers(self, function_name: str) -> str:
        """Render trigger configuration."""
        return self._dashboard.render_triggers(function_name)

    def render_layers(self) -> str:
        """Render layer inventory."""
        return self._dashboard.render_layers()

    def _annotate_response(self, result: FizzBuzzResult,
                           response: InvocationResponse) -> None:
        """Annotate a FizzBuzz result with serverless metadata headers."""
        result.metadata["X-FizzLambda-Version"] = FIZZLAMBDA_VERSION
        result.metadata["X-FizzLambda-Executed-Version"] = response.executed_version
        result.metadata["X-FizzLambda-Duration-Ms"] = str(response.metrics.duration_ms)
        result.metadata["X-FizzLambda-Billed-Ms"] = str(response.metrics.billed_duration_ms)
        result.metadata["X-FizzLambda-Memory-Used-MB"] = str(response.metrics.memory_used_mb)
        result.metadata["X-FizzLambda-Cold-Start"] = str(response.metrics.cold_start)

    def _should_use_serverless(self, context: ProcessingContext) -> bool:
        """Determine whether to route this evaluation through FizzLambda."""
        if self._mode == "serverless":
            return True
        if self._mode == "hybrid":
            return context.metadata.get("fizzlambda_trigger", False)
        return False

    def _emit_event(self, event_type: Any, data: Dict[str, Any]) -> None:
        """Emit an event through the event bus if available."""
        if self._runtime._event_bus is not None:
            try:
                self._runtime._event_bus.emit(event_type, data)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Factory Function
# ---------------------------------------------------------------------------

def create_fizzlambda_subsystem(
    max_total_environments: int = DEFAULT_MAX_ENVIRONMENTS,
    max_per_function: int = DEFAULT_MAX_PER_FUNCTION,
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
    max_burst: int = MAX_BURST_CONCURRENCY,
    account_limit: int = MAX_CONCURRENT_ENVIRONMENTS,
    snapshot_enabled: bool = True,
    predictive_enabled: bool = True,
    layer_cache_size_mb: int = 10240,
    mode: str = "container",
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    event_bus: Any = None,
) -> Tuple[FizzLambdaRuntime, FizzLambdaDashboard, FizzLambdaMiddleware]:
    """Create and wire the complete FizzLambda subsystem.

    Returns:
        A tuple of (runtime, dashboard, middleware) ready for integration
        with the platform's evaluation pipeline.
    """
    runtime = FizzLambdaRuntime(
        max_total_environments=max_total_environments,
        max_per_function=max_per_function,
        idle_timeout=idle_timeout,
        max_burst=max_burst,
        account_limit=account_limit,
        snapshot_enabled=snapshot_enabled,
        predictive_enabled=predictive_enabled,
        layer_cache_size_mb=layer_cache_size_mb,
        event_bus=event_bus,
    )
    runtime.start()

    dashboard = FizzLambdaDashboard(runtime, width=dashboard_width)
    middleware = FizzLambdaMiddleware(runtime, dashboard, mode=mode)

    return runtime, dashboard, middleware
