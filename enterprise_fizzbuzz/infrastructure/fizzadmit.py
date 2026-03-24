"""
Enterprise FizzBuzz Platform - FizzAdmit: Admission Controllers & CRD Operator Framework

Implements the complete Kubernetes admission control pipeline and Custom
Resource Definition (CRD) operator framework for the FizzKube container
orchestrator.

FizzKube, introduced in Round 5 and upgraded in FizzKubeV2, implements a
faithful Kubernetes-style control plane: API server, etcd-backed state
store, scheduler with predicate/priority scoring, controller manager with
reconciliation loops, and a CRI-integrated kubelet.  FizzKube processes
resource requests -- Pods, Deployments, ReplicaSets, Services, Namespaces,
ConfigMaps, HPAs -- with the same fidelity as a production Kubernetes
cluster.  It does not validate those requests before persisting them.
Every CREATE, UPDATE, and DELETE operation reaches etcd unconditionally.
A pod requesting more CPU than the entire cluster possesses is stored.
A container referencing a nonexistent registry is admitted.  A deployment
with no resource limits is created in a namespace with a resource quota,
and the quota is exceeded without detection.  Every invalid resource
reaches etcd.  Every impossible pod reaches the scheduler.  Failures are
discovered downstream -- at scheduling time, at image pull time, at cgroup
enforcement time -- after the invalid resource has already been committed
to cluster state.

Kubernetes solved this in 2015 with admission controllers: a chain of
validation and mutation plugins that intercept every API request before it
reaches the persistent store.  FizzAdmit builds this checkpoint between
the API server and etcd.

The admission chain routes every API server request through an ordered
sequence of mutating admission controllers (which modify the request to
inject defaults, enforce policies, and normalize fields) followed by
validating admission controllers (which accept or reject the final request
against cluster invariants and organizational policies).  Four built-in
controllers ship by default: ResourceQuota (namespace-level resource
accounting), LimitRanger (default resource injection and range validation),
PodSecurityAdmission (pod security standards enforcement), and ImagePolicy
(container image provenance and vulnerability policy).  Webhook-based
controllers allow external subsystems to participate in the admission
chain through a standard AdmissionReview request/response protocol.

The CRD framework enables runtime extension of FizzKube's API with
user-defined resource types.  CustomResourceDefinitions define new types
with OpenAPI v3 schema validation, versioning, subresources (status and
scale), and printer columns.  An operator SDK provides a builder-pattern
framework for writing custom controllers that watch CRDs, detect drift
between desired and actual state, reconcile the drift, and update resource
status.  Finalizer support enables cleanup on deletion; owner reference
tracking enables cascading deletion.  Two built-in CRDs demonstrate the
pattern: FizzBuzzCluster (declarative evaluation cluster management) and
FizzBuzzBackup (scheduled state backup).

Architecture reference: Kubernetes admission controllers (v1.29),
CustomResourceDefinitions, controller-runtime/operator-sdk
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from enterprise_fizzbuzz.domain.exceptions import (
    FizzAdmitError,
    AdmissionChainError,
    AdmissionControllerError,
    AdmissionDeniedError,
    AdmissionTimeoutError,
    AdmissionWebhookError,
    AdmissionWebhookUnreachableError,
    ResourceQuotaExhaustedError,
    LimitRangeViolationError,
    PodSecurityViolationError,
    ImagePolicyViolationError,
    CRDError,
    CRDSchemaValidationError,
    CRDRegistrationError,
    CRDInstanceValidationError,
    CRDNotFoundError,
    CRDDeletionError,
    OperatorError,
    OperatorReconcileError,
    OperatorLeaderElectionError,
    OperatorWorkQueueError,
    FinalizerError,
    FinalizerStuckError,
    FinalizerRemovalError,
    OwnerReferenceError,
    GarbageCollectionError,
    CascadingDeletionError,
    FizzAdmitMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzadmit")


# ══════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════

FIZZADMIT_VERSION = "1.0.0"
ADMISSION_API_VERSION = "admission.fizzkube.io/v1"
CRD_API_VERSION = "apiextensions.fizzkube.io/v1"
DEFAULT_ADMISSION_TIMEOUT = 10.0
MAX_WEBHOOK_TIMEOUT = 30.0
DEFAULT_FAILURE_POLICY = "FAIL"
BUILTIN_PRIORITY_RANGE = (0, 999)
WEBHOOK_PRIORITY_START = 1000
DEFAULT_FINALIZER_TIMEOUT = 300.0
DEFAULT_RECONCILE_MAX_CONCURRENT = 1
DEFAULT_RECONCILE_BACKOFF_BASE = 5.0
DEFAULT_RECONCILE_BACKOFF_CAP = 300.0
DEFAULT_RECONCILE_BACKOFF_MULTIPLIER = 2.0
DEFAULT_MAX_WORK_QUEUE_DEPTH = 1000
DEFAULT_LEADER_ELECTION_LEASE = 15.0
DEFAULT_LEADER_ELECTION_RENEW = 10.0
DEFAULT_LEADER_ELECTION_RETRY = 2.0
MIDDLEWARE_PRIORITY = 119


# ══════════════════════════════════════════════════════════════════
# Enums
# ══════════════════════════════════════════════════════════════════

class AdmissionPhase(Enum):
    """Phase in the admission chain."""
    MUTATING = "MUTATING"
    VALIDATING = "VALIDATING"


class AdmissionOperation(Enum):
    """API operations that admission controllers intercept."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CONNECT = "CONNECT"


class FailurePolicy(Enum):
    """Behavior when an admission controller is unavailable or errors."""
    FAIL = "FAIL"
    IGNORE = "IGNORE"


class SideEffects(Enum):
    """Whether an admission controller has side effects."""
    NONE = "NONE"
    SOME = "SOME"


class SecurityProfile(Enum):
    """Pod security admission profiles."""
    PRIVILEGED = "PRIVILEGED"
    BASELINE = "BASELINE"
    RESTRICTED = "RESTRICTED"


class EnforcementMode(Enum):
    """Pod security enforcement mode per namespace."""
    ENFORCE = "enforce"
    WARN = "warn"
    AUDIT = "audit"


class ImagePolicyAction(Enum):
    """Image policy rule action."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_SIGNATURE = "REQUIRE_SIGNATURE"


class PropagationPolicy(Enum):
    """Cascading deletion policy."""
    BACKGROUND = "BACKGROUND"
    FOREGROUND = "FOREGROUND"
    ORPHAN = "ORPHAN"


# ══════════════════════════════════════════════════════════════════
# Data Classes -- Admission Review Protocol
# ══════════════════════════════════════════════════════════════════

@dataclass
class GroupVersionKind:
    """Identifies a resource type by group, version, and kind."""
    group: str
    version: str
    kind: str


@dataclass
class GroupVersionResource:
    """Identifies a resource type by group, version, and resource name."""
    group: str
    version: str
    resource: str


@dataclass
class UserInfo:
    """Authenticated user making the API request."""
    username: str
    groups: List[str] = field(default_factory=list)
    uid: str = ""


@dataclass
class AdmissionStatus:
    """Rejection status returned by a denying admission controller."""
    code: int
    message: str
    reason: str


@dataclass
class JsonPatchOperation:
    """RFC 6902 JSON Patch operation."""
    op: str
    path: str
    value: Any = None
    from_path: str = ""


@dataclass
class AdmissionRequest:
    """The incoming request to be evaluated by admission controllers."""
    uid: str
    kind: GroupVersionKind
    resource: GroupVersionResource
    operation: AdmissionOperation
    namespace: str = ""
    name: str = ""
    sub_resource: str = ""
    user_info: Optional[UserInfo] = None
    object: Optional[Dict[str, Any]] = None
    old_object: Optional[Dict[str, Any]] = None
    options: Optional[Dict[str, Any]] = None
    dry_run: bool = False
    request_timestamp: str = ""


@dataclass
class AdmissionResponse:
    """The admission controller's decision."""
    uid: str
    allowed: bool
    status: Optional[AdmissionStatus] = None
    patch: Optional[List[JsonPatchOperation]] = None
    patch_type: str = "JSONPatch"
    audit_annotations: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class AdmissionReview:
    """Envelope for admission request/response exchange."""
    api_version: str = ADMISSION_API_VERSION
    kind: str = "AdmissionReview"
    request: Optional[AdmissionRequest] = None
    response: Optional[AdmissionResponse] = None


# ══════════════════════════════════════════════════════════════════
# Data Classes -- Admission Controller Registration
# ══════════════════════════════════════════════════════════════════

@dataclass
class AdmissionControllerRegistration:
    """Registration metadata for an admission controller."""
    name: str
    phase: AdmissionPhase
    priority: int
    controller: "AdmissionController"
    operations: List[AdmissionOperation] = field(
        default_factory=lambda: [AdmissionOperation.CREATE, AdmissionOperation.UPDATE]
    )
    resources: List[GroupVersionResource] = field(default_factory=list)
    namespaces: List[str] = field(default_factory=lambda: ["*"])
    failure_policy: FailurePolicy = FailurePolicy.FAIL
    side_effects: SideEffects = SideEffects.NONE
    timeout_seconds: float = DEFAULT_ADMISSION_TIMEOUT


# ══════════════════════════════════════════════════════════════════
# Data Classes -- Webhook Configuration
# ══════════════════════════════════════════════════════════════════

@dataclass
class RuleWithOperations:
    """Specifies which operations and resources trigger a webhook."""
    operations: List[AdmissionOperation]
    api_groups: List[str]
    api_versions: List[str]
    resources: List[str]
    scope: str = "*"


@dataclass
class WebhookClientConfig:
    """How to reach a webhook endpoint."""
    url: str = ""
    service_name: str = ""
    service_namespace: str = ""
    service_port: int = 443
    service_path: str = ""
    ca_bundle: str = ""


@dataclass
class MutatingWebhookConfiguration:
    """Configuration for a mutating admission webhook."""
    name: str
    client_config: WebhookClientConfig
    rules: List[RuleWithOperations] = field(default_factory=list)
    namespace_selector: Dict[str, str] = field(default_factory=dict)
    object_selector: Dict[str, str] = field(default_factory=dict)
    failure_policy: FailurePolicy = FailurePolicy.FAIL
    match_policy: str = "EXACT"
    side_effects: SideEffects = SideEffects.NONE
    timeout_seconds: float = DEFAULT_ADMISSION_TIMEOUT
    reinvocation_policy: str = "NEVER"


@dataclass
class ValidatingWebhookConfiguration:
    """Configuration for a validating admission webhook."""
    name: str
    client_config: WebhookClientConfig
    rules: List[RuleWithOperations] = field(default_factory=list)
    namespace_selector: Dict[str, str] = field(default_factory=dict)
    object_selector: Dict[str, str] = field(default_factory=dict)
    failure_policy: FailurePolicy = FailurePolicy.FAIL
    match_policy: str = "EXACT"
    side_effects: SideEffects = SideEffects.NONE
    timeout_seconds: float = DEFAULT_ADMISSION_TIMEOUT


# ══════════════════════════════════════════════════════════════════
# Data Classes -- Resource Quota & LimitRange
# ══════════════════════════════════════════════════════════════════

@dataclass
class ResourceQuota:
    """Namespace-level resource quota definition and tracking."""
    namespace: str
    hard: Dict[str, float] = field(default_factory=dict)
    used: Dict[str, float] = field(default_factory=dict)
    scope_selector: Dict[str, str] = field(default_factory=dict)


@dataclass
class LimitRange:
    """Namespace-level resource defaults and bounds."""
    namespace: str
    type: str = "Container"
    default: Dict[str, str] = field(default_factory=dict)
    default_request: Dict[str, str] = field(default_factory=dict)
    min: Dict[str, str] = field(default_factory=dict)
    max: Dict[str, str] = field(default_factory=dict)
    max_limit_request_ratio: Dict[str, float] = field(default_factory=dict)


@dataclass
class ImagePolicyRule:
    """Image policy enforcement rule."""
    name: str
    pattern: str
    action: ImagePolicyAction
    message: str = ""


# ══════════════════════════════════════════════════════════════════
# Data Classes -- CRD Model
# ══════════════════════════════════════════════════════════════════

@dataclass
class CRDNames:
    """Naming conventions for a custom resource type."""
    kind: str
    singular: str
    plural: str
    short_names: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)


@dataclass
class PrinterColumn:
    """Additional column for tabular CRD output."""
    name: str
    type: str
    json_path: str
    description: str = ""
    priority: int = 0


@dataclass
class SubResources:
    """Subresource configuration for a CRD version."""
    status: bool = False
    scale: Optional[Dict[str, str]] = None


@dataclass
class CRDVersion:
    """A version definition within a CRD."""
    name: str
    served: bool = True
    storage: bool = False
    schema: Optional[Dict[str, Any]] = None
    additional_printer_columns: List[PrinterColumn] = field(default_factory=list)
    subresources: Optional[SubResources] = None


@dataclass
class CustomResourceDefinition:
    """Meta-resource defining a new custom resource type."""
    api_version: str = CRD_API_VERSION
    kind: str = "CustomResourceDefinition"
    metadata: Dict[str, Any] = field(default_factory=dict)
    group: str = ""
    names: Optional[CRDNames] = None
    scope: str = "NAMESPACED"
    versions: List[CRDVersion] = field(default_factory=list)
    conversion_strategy: str = "NONE"
    conversion_webhook: Optional[WebhookClientConfig] = None


# ══════════════════════════════════════════════════════════════════
# Data Classes -- Owner Reference
# ══════════════════════════════════════════════════════════════════

@dataclass
class OwnerReference:
    """Parent-child relationship metadata."""
    api_version: str
    kind: str
    name: str
    uid: str
    controller: bool = False
    block_owner_deletion: bool = False


# ══════════════════════════════════════════════════════════════════
# Data Classes -- Operator SDK
# ══════════════════════════════════════════════════════════════════

@dataclass
class ReconcileRequest:
    """Identifies the resource to reconcile."""
    name: str
    namespace: str = ""


@dataclass
class ReconcileResult:
    """Result of a reconciliation cycle."""
    requeue: bool = False
    requeue_after: float = 0.0
    error: Optional[str] = None


@dataclass
class OperatorMetrics:
    """Runtime metrics for an operator."""
    reconcile_total: int = 0
    reconcile_success: int = 0
    reconcile_error: int = 0
    reconcile_latency_samples: List[float] = field(default_factory=list)
    work_queue_depth: int = 0
    work_queue_latency_samples: List[float] = field(default_factory=list)
    active_reconciles: int = 0


# ══════════════════════════════════════════════════════════════════
# Data Classes -- Audit Record
# ══════════════════════════════════════════════════════════════════

@dataclass
class AdmissionAuditRecord:
    """Audit log entry for an admission decision."""
    timestamp: str
    request_uid: str
    controller_name: str
    phase: str
    operation: str
    resource: str
    namespace: str
    name: str
    allowed: bool
    reason: str = ""
    latency_ms: float = 0.0
    patches_applied: int = 0
    warnings: List[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# JSON Patch Utility (RFC 6902)
# ══════════════════════════════════════════════════════════════════

def _unescape_json_pointer(token: str) -> str:
    """Unescape JSON Pointer reference tokens per RFC 6901.

    ~1 is unescaped to / and ~0 is unescaped to ~. The order
    of replacement matters: ~1 must be processed before ~0 to
    prevent double-unescaping.
    """
    return token.replace("~1", "/").replace("~0", "~")


def _parse_json_pointer(path: str) -> List[str]:
    """Parse a JSON Pointer string into reference tokens.

    The leading / is stripped, and each segment is unescaped
    per RFC 6901 rules.
    """
    if path == "":
        return []
    if not path.startswith("/"):
        raise AdmissionChainError(f"Invalid JSON Pointer: must start with '/', got '{path}'")
    parts = path[1:].split("/")
    return [_unescape_json_pointer(p) for p in parts]


def _resolve_pointer(obj: Any, tokens: List[str]) -> Tuple[Any, str]:
    """Walk the object tree to the parent of the target location.

    Returns a tuple of (parent_container, final_key).
    """
    current = obj
    for i, token in enumerate(tokens[:-1]):
        if isinstance(current, dict):
            if token not in current:
                raise AdmissionChainError(
                    f"JSON Pointer resolution failed: key '{token}' not found"
                )
            current = current[token]
        elif isinstance(current, list):
            try:
                idx = int(token)
            except ValueError:
                raise AdmissionChainError(
                    f"JSON Pointer resolution failed: non-integer index '{token}' for array"
                )
            if idx < 0 or idx >= len(current):
                raise AdmissionChainError(
                    f"JSON Pointer resolution failed: index {idx} out of range"
                )
            current = current[idx]
        else:
            raise AdmissionChainError(
                f"JSON Pointer resolution failed: cannot traverse into {type(current).__name__}"
            )
    final_key = tokens[-1] if tokens else ""
    return current, final_key


def apply_patches(obj: dict, patches: List[JsonPatchOperation]) -> dict:
    """Apply a sequence of RFC 6902 JSON Patch operations.

    Each operation is applied in order on a deep copy of the input
    object.  Supports add, remove, replace, move, and copy operations
    with full JSON Pointer path resolution including ~0 and ~1 escape
    sequences.

    Args:
        obj: The object to patch.
        patches: Ordered list of patch operations.

    Returns:
        A new dict with all patches applied.

    Raises:
        AdmissionChainError: If any operation targets an invalid path
            or specifies an unsupported operation type.
    """
    result = copy.deepcopy(obj)

    for patch in patches:
        tokens = _parse_json_pointer(patch.path)

        if patch.op == "add":
            if not tokens:
                result = copy.deepcopy(patch.value)
                continue
            parent, key = _resolve_pointer(result, tokens)
            if isinstance(parent, dict):
                parent[key] = copy.deepcopy(patch.value)
            elif isinstance(parent, list):
                if key == "-":
                    parent.append(copy.deepcopy(patch.value))
                else:
                    try:
                        idx = int(key)
                    except ValueError:
                        raise AdmissionChainError(
                            f"JSON Patch add: non-integer index '{key}' for array"
                        )
                    parent.insert(idx, copy.deepcopy(patch.value))
            else:
                raise AdmissionChainError(
                    f"JSON Patch add: cannot add to {type(parent).__name__}"
                )

        elif patch.op == "remove":
            if not tokens:
                raise AdmissionChainError("JSON Patch remove: cannot remove root")
            parent, key = _resolve_pointer(result, tokens)
            if isinstance(parent, dict):
                if key not in parent:
                    raise AdmissionChainError(
                        f"JSON Patch remove: key '{key}' not found"
                    )
                del parent[key]
            elif isinstance(parent, list):
                try:
                    idx = int(key)
                except ValueError:
                    raise AdmissionChainError(
                        f"JSON Patch remove: non-integer index '{key}' for array"
                    )
                if idx < 0 or idx >= len(parent):
                    raise AdmissionChainError(
                        f"JSON Patch remove: index {idx} out of range"
                    )
                del parent[idx]
            else:
                raise AdmissionChainError(
                    f"JSON Patch remove: cannot remove from {type(parent).__name__}"
                )

        elif patch.op == "replace":
            if not tokens:
                result = copy.deepcopy(patch.value)
                continue
            parent, key = _resolve_pointer(result, tokens)
            if isinstance(parent, dict):
                if key not in parent:
                    raise AdmissionChainError(
                        f"JSON Patch replace: key '{key}' not found"
                    )
                parent[key] = copy.deepcopy(patch.value)
            elif isinstance(parent, list):
                try:
                    idx = int(key)
                except ValueError:
                    raise AdmissionChainError(
                        f"JSON Patch replace: non-integer index '{key}' for array"
                    )
                if idx < 0 or idx >= len(parent):
                    raise AdmissionChainError(
                        f"JSON Patch replace: index {idx} out of range"
                    )
                parent[idx] = copy.deepcopy(patch.value)
            else:
                raise AdmissionChainError(
                    f"JSON Patch replace: cannot replace in {type(parent).__name__}"
                )

        elif patch.op == "move":
            from_tokens = _parse_json_pointer(patch.from_path)
            if not from_tokens:
                raise AdmissionChainError("JSON Patch move: cannot move root")
            from_parent, from_key = _resolve_pointer(result, from_tokens)
            if isinstance(from_parent, dict):
                if from_key not in from_parent:
                    raise AdmissionChainError(
                        f"JSON Patch move: source key '{from_key}' not found"
                    )
                value = from_parent.pop(from_key)
            elif isinstance(from_parent, list):
                try:
                    idx = int(from_key)
                except ValueError:
                    raise AdmissionChainError(
                        f"JSON Patch move: non-integer index '{from_key}' for array"
                    )
                value = from_parent.pop(idx)
            else:
                raise AdmissionChainError(
                    f"JSON Patch move: cannot move from {type(from_parent).__name__}"
                )
            if not tokens:
                result = value
                continue
            to_parent, to_key = _resolve_pointer(result, tokens)
            if isinstance(to_parent, dict):
                to_parent[to_key] = value
            elif isinstance(to_parent, list):
                if to_key == "-":
                    to_parent.append(value)
                else:
                    to_parent.insert(int(to_key), value)

        elif patch.op == "copy":
            from_tokens = _parse_json_pointer(patch.from_path)
            if not from_tokens:
                raise AdmissionChainError("JSON Patch copy: cannot copy root")
            from_parent, from_key = _resolve_pointer(result, from_tokens)
            if isinstance(from_parent, dict):
                if from_key not in from_parent:
                    raise AdmissionChainError(
                        f"JSON Patch copy: source key '{from_key}' not found"
                    )
                value = copy.deepcopy(from_parent[from_key])
            elif isinstance(from_parent, list):
                try:
                    idx = int(from_key)
                except ValueError:
                    raise AdmissionChainError(
                        f"JSON Patch copy: non-integer index '{from_key}' for array"
                    )
                value = copy.deepcopy(from_parent[idx])
            else:
                raise AdmissionChainError(
                    f"JSON Patch copy: cannot copy from {type(from_parent).__name__}"
                )
            if not tokens:
                result = value
                continue
            to_parent, to_key = _resolve_pointer(result, tokens)
            if isinstance(to_parent, dict):
                to_parent[to_key] = value
            elif isinstance(to_parent, list):
                if to_key == "-":
                    to_parent.append(value)
                else:
                    to_parent.insert(int(to_key), value)

        else:
            raise AdmissionChainError(f"Unsupported JSON Patch operation: '{patch.op}'")

    return result


# ══════════════════════════════════════════════════════════════════
# AdmissionController (Abstract Base)
# ══════════════════════════════════════════════════════════════════

class AdmissionController:
    """Abstract base for admission controllers.

    Every admission controller implements the admit() method which
    receives an AdmissionRequest and returns an AdmissionResponse
    indicating whether the request should be allowed or denied.
    """

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        """Evaluate the request and return an admission decision."""
        raise NotImplementedError


# ══════════════════════════════════════════════════════════════════
# AdmissionChain
# ══════════════════════════════════════════════════════════════════

class AdmissionChain:
    """Central pipeline orchestrating all admission controllers.

    Routes every API server request through an ordered sequence of
    mutating controllers followed by validating controllers.  Mutating
    controllers can modify the request via JSON Patch operations;
    validating controllers accept or reject the final mutated object.

    The chain maintains priority-sorted lists for each phase, enforces
    name uniqueness, and records audit logs for every admission
    decision.
    """

    def __init__(self, *, max_audit_records: int = 10000) -> None:
        self._mutating: List[AdmissionControllerRegistration] = []
        self._validating: List[AdmissionControllerRegistration] = []
        self._audit_log: deque = deque(maxlen=max_audit_records)
        self._lock = threading.Lock()
        self._max_audit_records = max_audit_records

    def register(self, registration: AdmissionControllerRegistration) -> None:
        """Insert a controller into the correct phase list.

        Validates name uniqueness across both phases and ensures
        priority falls within the allowed range for the controller
        type (built-in vs webhook).
        """
        with self._lock:
            for reg in self._mutating + self._validating:
                if reg.name == registration.name:
                    raise AdmissionChainError(
                        f"Duplicate controller name: '{registration.name}'"
                    )

            target = (
                self._mutating
                if registration.phase == AdmissionPhase.MUTATING
                else self._validating
            )
            target.append(registration)
            target.sort(key=lambda r: r.priority)
            logger.info(
                "Registered %s admission controller '%s' at priority %d",
                registration.phase.value,
                registration.name,
                registration.priority,
            )

    def unregister(self, name: str) -> None:
        """Remove a controller by name from the chain."""
        with self._lock:
            self._mutating = [r for r in self._mutating if r.name != name]
            self._validating = [r for r in self._validating if r.name != name]
            logger.info("Unregistered admission controller '%s'", name)

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        """Execute the full admission pipeline.

        1. Filter and execute matching MUTATING controllers in priority
           order.  Each controller receives a deep copy of the current
           object.  Patches are applied after each controller.
        2. Filter and execute matching VALIDATING controllers on the
           mutated object.  Same-priority validators execute in sequence.
        3. Aggregate patches, audit annotations, and warnings.
        4. Record audit entries for each controller invocation.
        5. Return the final response.
        """
        all_patches: List[JsonPatchOperation] = []
        all_annotations: Dict[str, str] = {}
        all_warnings: List[str] = []
        current_object = copy.deepcopy(request.object) if request.object else {}

        # Phase 1: Mutating controllers
        for reg in self._mutating:
            if not self._matches(reg, request):
                continue
            if request.dry_run and reg.side_effects == SideEffects.SOME:
                all_warnings.append(
                    f"Skipped '{reg.name}' (has side effects, dry-run mode)"
                )
                continue

            mutated_request = copy.deepcopy(request)
            mutated_request.object = copy.deepcopy(current_object)
            start_time = time.monotonic()

            try:
                response = reg.controller.admit(mutated_request)
            except Exception as exc:
                response = self._handle_controller_error(reg, exc, request)

            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            self._record_audit(reg, request, response, elapsed_ms)

            if not response.allowed:
                return AdmissionResponse(
                    uid=request.uid,
                    allowed=False,
                    status=response.status,
                    audit_annotations={**all_annotations, **response.audit_annotations},
                    warnings=all_warnings + response.warnings,
                )

            if response.patch:
                current_object = apply_patches(current_object, response.patch)
                all_patches.extend(response.patch)
            all_annotations.update(response.audit_annotations)
            all_warnings.extend(response.warnings)

        # Phase 2: Validating controllers
        for reg in self._validating:
            if not self._matches(reg, request):
                continue
            if request.dry_run and reg.side_effects == SideEffects.SOME:
                all_warnings.append(
                    f"Skipped '{reg.name}' (has side effects, dry-run mode)"
                )
                continue

            val_request = copy.deepcopy(request)
            val_request.object = copy.deepcopy(current_object)
            start_time = time.monotonic()

            try:
                response = reg.controller.admit(val_request)
            except Exception as exc:
                response = self._handle_controller_error(reg, exc, request)

            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            self._record_audit(reg, request, response, elapsed_ms)

            if not response.allowed:
                return AdmissionResponse(
                    uid=request.uid,
                    allowed=False,
                    status=response.status,
                    audit_annotations={**all_annotations, **response.audit_annotations},
                    warnings=all_warnings + response.warnings,
                )
            all_annotations.update(response.audit_annotations)
            all_warnings.extend(response.warnings)

        return AdmissionResponse(
            uid=request.uid,
            allowed=True,
            patch=all_patches if all_patches else None,
            audit_annotations=all_annotations,
            warnings=all_warnings,
        )

    def _matches(
        self,
        registration: AdmissionControllerRegistration,
        request: AdmissionRequest,
    ) -> bool:
        """Check if a controller matches the request."""
        if registration.operations and request.operation not in registration.operations:
            return False

        if registration.resources:
            matched = False
            for gvr in registration.resources:
                if (
                    gvr.group == request.resource.group
                    and gvr.version == request.resource.version
                    and gvr.resource == request.resource.resource
                ):
                    matched = True
                    break
            if not matched:
                return False

        if registration.namespaces and "*" not in registration.namespaces:
            if request.namespace not in registration.namespaces:
                return False

        return True

    def _handle_controller_error(
        self,
        registration: AdmissionControllerRegistration,
        error: Exception,
        request: AdmissionRequest,
    ) -> AdmissionResponse:
        """Apply failure policy on controller error."""
        logger.warning(
            "Admission controller '%s' raised %s: %s",
            registration.name,
            type(error).__name__,
            error,
        )
        if registration.failure_policy == FailurePolicy.IGNORE:
            return AdmissionResponse(
                uid=request.uid,
                allowed=True,
                warnings=[
                    f"Controller '{registration.name}' failed with "
                    f"{type(error).__name__}: {error} (failure policy: IGNORE)"
                ],
            )
        return AdmissionResponse(
            uid=request.uid,
            allowed=False,
            status=AdmissionStatus(
                code=500,
                message=f"Controller '{registration.name}' failed: {error}",
                reason="InternalError",
            ),
        )

    def _record_audit(
        self,
        registration: AdmissionControllerRegistration,
        request: AdmissionRequest,
        response: AdmissionResponse,
        elapsed_ms: float,
    ) -> None:
        """Record an audit entry for the admission decision."""
        record = AdmissionAuditRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            request_uid=request.uid,
            controller_name=registration.name,
            phase=registration.phase.value,
            operation=request.operation.value,
            resource=f"{request.resource.group}/{request.resource.version}/{request.resource.resource}",
            namespace=request.namespace,
            name=request.name,
            allowed=response.allowed,
            reason=response.status.reason if response.status else "",
            latency_ms=elapsed_ms,
            patches_applied=len(response.patch) if response.patch else 0,
            warnings=list(response.warnings),
        )
        self._audit_log.append(record)

    def get_chain_summary(self) -> List[Dict]:
        """Return the ordered chain for display."""
        summary = []
        for reg in self._mutating:
            summary.append({
                "name": reg.name,
                "phase": "MUTATING",
                "priority": reg.priority,
                "operations": [op.value for op in reg.operations],
                "failure_policy": reg.failure_policy.value,
                "side_effects": reg.side_effects.value,
                "timeout": reg.timeout_seconds,
            })
        for reg in self._validating:
            summary.append({
                "name": reg.name,
                "phase": "VALIDATING",
                "priority": reg.priority,
                "operations": [op.value for op in reg.operations],
                "failure_policy": reg.failure_policy.value,
                "side_effects": reg.side_effects.value,
                "timeout": reg.timeout_seconds,
            })
        return summary

    def get_audit_log(self, limit: int = 100) -> List[AdmissionAuditRecord]:
        """Return recent audit records."""
        records = list(self._audit_log)
        return records[-limit:]


# ══════════════════════════════════════════════════════════════════
# ResourceQuotaAdmissionController
# ══════════════════════════════════════════════════════════════════

class ResourceQuotaAdmissionController(AdmissionController):
    """Namespace-level resource quota enforcement.

    Tracks resource usage (CPU, memory, pod count, service count, etc.)
    per namespace and denies requests that would exceed the configured
    hard limits.  Acts as both a mutating controller (to update quota
    status) and a validating controller (to deny over-quota requests).
    """

    def __init__(self) -> None:
        self._quotas: Dict[str, ResourceQuota] = {}
        self._lock = threading.Lock()

    def set_quota(self, namespace: str, quota: ResourceQuota) -> None:
        """Configure or update a namespace quota."""
        with self._lock:
            self._quotas[namespace] = quota
            if not quota.used:
                quota.used = {k: 0.0 for k in quota.hard}
            logger.info("Set resource quota for namespace '%s'", namespace)

    def get_quota(self, namespace: str) -> Optional[ResourceQuota]:
        """Retrieve quota and usage for a namespace."""
        return self._quotas.get(namespace)

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        """Evaluate resource quota compliance."""
        namespace = request.namespace
        if namespace not in self._quotas:
            return AdmissionResponse(uid=request.uid, allowed=True)

        quota = self._quotas[namespace]
        obj = request.object or {}
        old_obj = request.old_object or {}

        if request.operation == AdmissionOperation.CREATE:
            return self._handle_create(request, quota, obj)
        elif request.operation == AdmissionOperation.DELETE:
            return self._handle_delete(request, quota, old_obj)
        elif request.operation == AdmissionOperation.UPDATE:
            return self._handle_update(request, quota, obj, old_obj)

        return AdmissionResponse(uid=request.uid, allowed=True)

    def _handle_create(
        self,
        request: AdmissionRequest,
        quota: ResourceQuota,
        obj: Dict[str, Any],
    ) -> AdmissionResponse:
        """Check quota on CREATE and increment used counts."""
        with self._lock:
            if not self._check_scope_selector(quota, obj.get("metadata", {}).get("labels", {})):
                return AdmissionResponse(uid=request.uid, allowed=True)

            resource_demands = self._compute_resource_demands(obj)
            kind = request.kind.kind.lower()

            count_key = f"{kind}s" if kind in ("pod", "service", "configmap", "secret") else None
            if count_key and count_key in quota.hard:
                resource_demands[count_key] = 1.0

            for resource_name, demanded in resource_demands.items():
                if resource_name in quota.hard:
                    current = quota.used.get(resource_name, 0.0)
                    hard = quota.hard[resource_name]
                    if current + demanded > hard:
                        return AdmissionResponse(
                            uid=request.uid,
                            allowed=False,
                            status=AdmissionStatus(
                                code=403,
                                message=(
                                    f"Namespace '{quota.namespace}': {resource_name} "
                                    f"quota exhausted (requested={demanded}, "
                                    f"used={current}, hard={hard})"
                                ),
                                reason="QuotaExhausted",
                            ),
                        )

            for resource_name, demanded in resource_demands.items():
                if resource_name in quota.hard:
                    quota.used[resource_name] = quota.used.get(resource_name, 0.0) + demanded

            return AdmissionResponse(
                uid=request.uid,
                allowed=True,
                audit_annotations={
                    "resource-quota": f"namespace={quota.namespace}, demands={resource_demands}",
                },
            )

    def _handle_delete(
        self,
        request: AdmissionRequest,
        quota: ResourceQuota,
        old_obj: Dict[str, Any],
    ) -> AdmissionResponse:
        """Decrement used counts on DELETE."""
        with self._lock:
            resource_demands = self._compute_resource_demands(old_obj)
            kind = request.kind.kind.lower()
            count_key = f"{kind}s" if kind in ("pod", "service", "configmap", "secret") else None
            if count_key and count_key in quota.hard:
                resource_demands[count_key] = 1.0

            for resource_name, demanded in resource_demands.items():
                if resource_name in quota.hard:
                    quota.used[resource_name] = max(
                        0.0, quota.used.get(resource_name, 0.0) - demanded
                    )

        return AdmissionResponse(uid=request.uid, allowed=True)

    def _handle_update(
        self,
        request: AdmissionRequest,
        quota: ResourceQuota,
        new_obj: Dict[str, Any],
        old_obj: Dict[str, Any],
    ) -> AdmissionResponse:
        """Compute delta between old and new resource requests."""
        with self._lock:
            new_demands = self._compute_resource_demands(new_obj)
            old_demands = self._compute_resource_demands(old_obj)

            for resource_name in set(new_demands) | set(old_demands):
                if resource_name in quota.hard:
                    delta = new_demands.get(resource_name, 0.0) - old_demands.get(resource_name, 0.0)
                    if delta > 0:
                        current = quota.used.get(resource_name, 0.0)
                        hard = quota.hard[resource_name]
                        if current + delta > hard:
                            return AdmissionResponse(
                                uid=request.uid,
                                allowed=False,
                                status=AdmissionStatus(
                                    code=403,
                                    message=(
                                        f"Namespace '{quota.namespace}': {resource_name} "
                                        f"quota exhausted on update (delta={delta}, "
                                        f"used={current}, hard={hard})"
                                    ),
                                    reason="QuotaExhausted",
                                ),
                            )

            for resource_name in set(new_demands) | set(old_demands):
                if resource_name in quota.hard:
                    delta = new_demands.get(resource_name, 0.0) - old_demands.get(resource_name, 0.0)
                    quota.used[resource_name] = max(
                        0.0, quota.used.get(resource_name, 0.0) + delta
                    )

        return AdmissionResponse(uid=request.uid, allowed=True)

    def _compute_resource_demands(self, obj: Dict[str, Any]) -> Dict[str, float]:
        """Sum resource requests from all containers in a pod spec."""
        demands: Dict[str, float] = {}
        spec = obj.get("spec", {})
        containers = spec.get("containers", [])
        for container in containers:
            resources = container.get("resources", {})
            requests = resources.get("requests", {})
            for k, v in requests.items():
                parsed = self._parse_resource_value(str(v))
                key = f"requests.{k}"
                demands[key] = demands.get(key, 0.0) + parsed
            limits = resources.get("limits", {})
            for k, v in limits.items():
                parsed = self._parse_resource_value(str(v))
                key = f"limits.{k}"
                demands[key] = demands.get(key, 0.0) + parsed
        return demands

    @staticmethod
    def _parse_resource_value(value: str) -> float:
        """Parse Kubernetes resource strings.

        Supports:
        - CPU: "500m" = 0.5, "2" = 2.0
        - Memory: "256FB" = 256 (FizzBytes), "1Gi" = 1073741824,
          "512Mi" = 536870912, "1024Ki" = 1048576
        """
        value = value.strip()
        if value.endswith("m"):
            return float(value[:-1]) / 1000.0
        if value.endswith("FB"):
            return float(value[:-2])
        if value.endswith("Gi"):
            return float(value[:-2]) * 1073741824
        if value.endswith("Mi"):
            return float(value[:-2]) * 1048576
        if value.endswith("Ki"):
            return float(value[:-2]) * 1024
        try:
            return float(value)
        except ValueError:
            return 0.0

    @staticmethod
    def _check_scope_selector(quota: ResourceQuota, labels: Dict[str, str]) -> bool:
        """Check if resource labels match the quota's scope selector."""
        if not quota.scope_selector:
            return True
        for key, expected in quota.scope_selector.items():
            if labels.get(key) != expected:
                return False
        return True

    def render_quota_status(self, namespace: str) -> str:
        """Render quota utilization table for CLI."""
        quota = self._quotas.get(namespace)
        if not quota:
            return f"No resource quota configured for namespace '{namespace}'"

        lines = [
            f"Resource Quota: {namespace}",
            "=" * 60,
            f"{'Resource':<30} {'Used':>10} {'Hard':>10} {'%':>8}",
            "-" * 60,
        ]
        for resource_name in sorted(quota.hard.keys()):
            hard = quota.hard[resource_name]
            used = quota.used.get(resource_name, 0.0)
            pct = (used / hard * 100.0) if hard > 0 else 0.0
            lines.append(f"{resource_name:<30} {used:>10.2f} {hard:>10.2f} {pct:>7.1f}%")
        lines.append("=" * 60)
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# LimitRangerAdmissionController
# ══════════════════════════════════════════════════════════════════

class LimitRangerAdmissionController(AdmissionController):
    """Namespace-level resource default injection and range validation.

    For each container in a pod spec: if resource requests or limits
    are missing, inject defaults from the LimitRange configuration.
    Then validate that all values fall within the configured min/max
    bounds and that limit/request ratios are within tolerance.
    """

    def __init__(self) -> None:
        self._ranges: Dict[str, LimitRange] = {}

    def set_limit_range(self, namespace: str, limit_range: LimitRange) -> None:
        """Configure namespace limit range."""
        self._ranges[namespace] = limit_range
        logger.info("Set limit range for namespace '%s'", namespace)

    def get_limit_range(self, namespace: str) -> Optional[LimitRange]:
        """Retrieve limit range configuration."""
        return self._ranges.get(namespace)

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        """Inject defaults and validate resource ranges."""
        if request.operation not in (AdmissionOperation.CREATE, AdmissionOperation.UPDATE):
            return AdmissionResponse(uid=request.uid, allowed=True)

        namespace = request.namespace
        if namespace not in self._ranges:
            return AdmissionResponse(uid=request.uid, allowed=True)

        limit_range = self._ranges[namespace]
        obj = request.object or {}
        spec = obj.get("spec", {})
        containers = spec.get("containers", [])

        patches: List[JsonPatchOperation] = []
        violations: List[str] = []

        for idx, container in enumerate(containers):
            container_name = container.get("name", f"container-{idx}")
            resources = container.get("resources", {})
            requests = resources.get("requests", {})
            limits = resources.get("limits", {})

            # Inject default requests
            if not requests and limit_range.default_request:
                patches.append(JsonPatchOperation(
                    op="add",
                    path=f"/spec/containers/{idx}/resources/requests",
                    value=dict(limit_range.default_request),
                ))
                requests = dict(limit_range.default_request)

            # Inject default limits
            if not limits and limit_range.default:
                patches.append(JsonPatchOperation(
                    op="add",
                    path=f"/spec/containers/{idx}/resources/limits",
                    value=dict(limit_range.default),
                ))
                limits = dict(limit_range.default)

            # Validate min
            for resource_name, min_val_str in limit_range.min.items():
                min_val = ResourceQuotaAdmissionController._parse_resource_value(min_val_str)
                for section_name, section in [("requests", requests), ("limits", limits)]:
                    if resource_name in section:
                        actual = ResourceQuotaAdmissionController._parse_resource_value(
                            str(section[resource_name])
                        )
                        if actual < min_val:
                            violations.append(
                                f"Container '{container_name}': {section_name}.{resource_name} "
                                f"= {section[resource_name]} is below minimum {min_val_str}"
                            )

            # Validate max
            for resource_name, max_val_str in limit_range.max.items():
                max_val = ResourceQuotaAdmissionController._parse_resource_value(max_val_str)
                for section_name, section in [("requests", requests), ("limits", limits)]:
                    if resource_name in section:
                        actual = ResourceQuotaAdmissionController._parse_resource_value(
                            str(section[resource_name])
                        )
                        if actual > max_val:
                            violations.append(
                                f"Container '{container_name}': {section_name}.{resource_name} "
                                f"= {section[resource_name]} exceeds maximum {max_val_str}"
                            )

            # Validate ratio
            for resource_name, max_ratio in limit_range.max_limit_request_ratio.items():
                if resource_name in limits and resource_name in requests:
                    limit_val = ResourceQuotaAdmissionController._parse_resource_value(
                        str(limits[resource_name])
                    )
                    request_val = ResourceQuotaAdmissionController._parse_resource_value(
                        str(requests[resource_name])
                    )
                    if request_val > 0 and limit_val / request_val > max_ratio:
                        violations.append(
                            f"Container '{container_name}': {resource_name} "
                            f"limit/request ratio {limit_val / request_val:.2f} "
                            f"exceeds maximum {max_ratio}"
                        )

        if violations:
            return AdmissionResponse(
                uid=request.uid,
                allowed=False,
                status=AdmissionStatus(
                    code=403,
                    message="; ".join(violations),
                    reason="LimitRangeViolation",
                ),
            )

        return AdmissionResponse(
            uid=request.uid,
            allowed=True,
            patch=patches if patches else None,
        )

    def render_limit_range(self, namespace: str) -> str:
        """Render limit range config for CLI."""
        lr = self._ranges.get(namespace)
        if not lr:
            return f"No LimitRange configured for namespace '{namespace}'"

        lines = [
            f"LimitRange: {namespace} (type={lr.type})",
            "=" * 60,
        ]
        if lr.default:
            lines.append(f"  Defaults:         {lr.default}")
        if lr.default_request:
            lines.append(f"  Default Requests: {lr.default_request}")
        if lr.min:
            lines.append(f"  Min:              {lr.min}")
        if lr.max:
            lines.append(f"  Max:              {lr.max}")
        if lr.max_limit_request_ratio:
            lines.append(f"  Max Ratio:        {lr.max_limit_request_ratio}")
        lines.append("=" * 60)
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# PodSecurityAdmissionController
# ══════════════════════════════════════════════════════════════════

class PodSecurityAdmissionController(AdmissionController):
    """Pod security standards enforcement per namespace.

    Evaluates pod specs against three security profiles: Privileged
    (allows everything), Baseline (blocks known privilege escalation
    vectors), and Restricted (enforces current pod hardening best
    practices).  Each namespace is assigned a profile and enforcement
    mode (enforce, warn, or audit).
    """

    def __init__(self) -> None:
        self._namespace_profiles: Dict[str, Tuple[SecurityProfile, EnforcementMode, str]] = {}

    def set_namespace_policy(
        self,
        namespace: str,
        profile: SecurityProfile,
        mode: EnforcementMode,
        version: str = "v1.0",
    ) -> None:
        """Configure namespace security policy."""
        self._namespace_profiles[namespace] = (profile, mode, version)
        logger.info(
            "Set pod security profile for namespace '%s': %s (%s)",
            namespace,
            profile.value,
            mode.value,
        )

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        """Evaluate pod spec against namespace security profile."""
        if request.operation not in (AdmissionOperation.CREATE, AdmissionOperation.UPDATE):
            return AdmissionResponse(uid=request.uid, allowed=True)

        namespace = request.namespace
        if namespace not in self._namespace_profiles:
            return AdmissionResponse(uid=request.uid, allowed=True)

        profile, mode, version = self._namespace_profiles[namespace]

        if profile == SecurityProfile.PRIVILEGED:
            return AdmissionResponse(uid=request.uid, allowed=True)

        obj = request.object or {}
        pod_spec = obj.get("spec", {})

        if profile == SecurityProfile.RESTRICTED:
            violations = self._check_restricted_violations(pod_spec)
        else:
            violations = self._check_baseline_violations(pod_spec)

        if not violations:
            return AdmissionResponse(uid=request.uid, allowed=True)

        violation_str = "; ".join(violations)

        if mode == EnforcementMode.ENFORCE:
            return AdmissionResponse(
                uid=request.uid,
                allowed=False,
                status=AdmissionStatus(
                    code=403,
                    message=f"Pod security violation ({profile.value}): {violation_str}",
                    reason="PodSecurityViolation",
                ),
            )
        elif mode == EnforcementMode.WARN:
            return AdmissionResponse(
                uid=request.uid,
                allowed=True,
                warnings=[
                    f"Pod security warning ({profile.value}): {v}" for v in violations
                ],
            )
        else:  # AUDIT
            return AdmissionResponse(
                uid=request.uid,
                allowed=True,
                audit_annotations={
                    "pod-security-audit": f"{profile.value}: {violation_str}",
                },
            )

    def _check_baseline_violations(self, pod_spec: Dict[str, Any]) -> List[str]:
        """Check for BASELINE profile violations."""
        violations = []
        containers = pod_spec.get("containers", [])

        if pod_spec.get("hostNetwork", False):
            violations.append("hostNetwork is true")
        if pod_spec.get("hostPID", False):
            violations.append("hostPID is true")
        if pod_spec.get("hostIPC", False):
            violations.append("hostIPC is true")

        for container in containers:
            name = container.get("name", "unnamed")
            security_ctx = container.get("securityContext", {})

            if security_ctx.get("privileged", False):
                violations.append(f"container '{name}': privileged is true")

            if security_ctx.get("allowPrivilegeEscalation", False):
                violations.append(f"container '{name}': allowPrivilegeEscalation is true")

            capabilities = security_ctx.get("capabilities", {})
            add_caps = capabilities.get("add", [])
            dangerous = {"ALL", "SYS_ADMIN", "NET_ADMIN", "SYS_PTRACE"}
            for cap in add_caps:
                if cap.upper() in dangerous:
                    violations.append(
                        f"container '{name}': dangerous capability '{cap}'"
                    )

            volume_mounts = container.get("volumeMounts", [])
            for mount in volume_mounts:
                if mount.get("mountPath") == "/proc" and not mount.get("readOnly", False):
                    violations.append(f"container '{name}': writable /proc mount")

        return violations

    def _check_restricted_violations(self, pod_spec: Dict[str, Any]) -> List[str]:
        """Check for RESTRICTED profile violations (superset of BASELINE)."""
        violations = self._check_baseline_violations(pod_spec)
        containers = pod_spec.get("containers", [])

        allowed_volumes = {"configMap", "secret", "emptyDir", "persistentVolumeClaim"}
        for volume in pod_spec.get("volumes", []):
            vol_types = set(volume.keys()) - {"name"}
            for vt in vol_types:
                if vt not in allowed_volumes:
                    violations.append(f"restricted volume type: '{vt}'")

        for container in containers:
            name = container.get("name", "unnamed")
            security_ctx = container.get("securityContext", {})

            if not security_ctx.get("runAsNonRoot", False):
                violations.append(f"container '{name}': runAsNonRoot must be true")

            if not security_ctx.get("readOnlyRootFilesystem", False):
                violations.append(
                    f"container '{name}': readOnlyRootFilesystem must be true"
                )

            capabilities = security_ctx.get("capabilities", {})
            add_caps = capabilities.get("add", [])
            for cap in add_caps:
                if cap.upper() != "NET_BIND_SERVICE":
                    violations.append(
                        f"container '{name}': capability '{cap}' not allowed "
                        f"(only NET_BIND_SERVICE permitted)"
                    )

            drop_caps = capabilities.get("drop", [])
            if "ALL" not in [c.upper() for c in drop_caps]:
                violations.append(
                    f"container '{name}': must drop ALL capabilities"
                )

            seccomp = security_ctx.get("seccompProfile", {})
            seccomp_type = seccomp.get("type", "")
            if seccomp_type not in ("RuntimeDefault", "Localhost"):
                violations.append(
                    f"container '{name}': seccomp profile must be "
                    f"RuntimeDefault or Localhost, got '{seccomp_type}'"
                )

        return violations

    def render_security_profile(self, namespace: str) -> str:
        """Render namespace security profile for CLI."""
        if namespace not in self._namespace_profiles:
            return f"No security profile configured for namespace '{namespace}'"

        profile, mode, version = self._namespace_profiles[namespace]
        lines = [
            f"Pod Security Profile: {namespace}",
            "=" * 50,
            f"  Profile:  {profile.value}",
            f"  Mode:     {mode.value}",
            f"  Version:  {version}",
            "=" * 50,
        ]
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# ImagePolicyAdmissionController
# ══════════════════════════════════════════════════════════════════

class ImagePolicyAdmissionController(AdmissionController):
    """Container image provenance and vulnerability policy enforcement.

    Evaluates container image references against an ordered list of
    policy rules.  Rules can allow, deny, or require signatures for
    images matching a pattern.  Tag-to-digest resolution is supported
    for signature verification.
    """

    def __init__(self) -> None:
        self._rules: List[ImagePolicyRule] = []
        self._image_digests: Dict[str, str] = {}
        self._signed_images: Set[str] = set()

    def add_rule(self, rule: ImagePolicyRule) -> None:
        """Add a policy rule."""
        self._rules.append(rule)

    def set_default_rules(self) -> None:
        """Register the four default image policy rules."""
        self._rules = [
            ImagePolicyRule(
                name="deny-latest",
                pattern=r".*:latest$",
                action=ImagePolicyAction.DENY,
                message="Images with :latest tag are not permitted; use explicit version tags",
            ),
            ImagePolicyRule(
                name="deny-untrusted-registry",
                pattern=r"^(?!fizzbuzz-registry\.local/).*",
                action=ImagePolicyAction.DENY,
                message="Only images from fizzbuzz-registry.local are permitted",
            ),
            ImagePolicyRule(
                name="require-signature-production",
                pattern=r".*",
                action=ImagePolicyAction.REQUIRE_SIGNATURE,
                message="Images in production namespaces must be signed",
            ),
            ImagePolicyRule(
                name="allow-trusted",
                pattern=r"^fizzbuzz-registry\.local/.*:[v\d].*",
                action=ImagePolicyAction.ALLOW,
                message="Trusted registry with version tag",
            ),
        ]
        logger.info("Registered %d default image policy rules", len(self._rules))

    def register_signed_image(self, digest: str) -> None:
        """Mark an image digest as signed."""
        self._signed_images.add(digest)

    def register_image_digest(self, tag: str, digest: str) -> None:
        """Cache tag-to-digest resolution."""
        self._image_digests[tag] = digest

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        """Evaluate container images against policy rules."""
        obj = request.object or {}
        spec = obj.get("spec", {})
        containers = spec.get("containers", [])

        violations = []
        for container in containers:
            image = container.get("image", "")
            if not image:
                continue

            digest = self._image_digests.get(image, "")
            violation = self._evaluate_image(image, digest, request.namespace)
            if violation:
                violations.append(violation)

        if violations:
            return AdmissionResponse(
                uid=request.uid,
                allowed=False,
                status=AdmissionStatus(
                    code=403,
                    message="; ".join(violations),
                    reason="ImagePolicyViolation",
                ),
            )

        return AdmissionResponse(uid=request.uid, allowed=True)

    def _evaluate_image(self, image: str, digest: str, namespace: str) -> Optional[str]:
        """Evaluate a single image against policy rules."""
        for rule in self._rules:
            if re.match(rule.pattern, image):
                if rule.action == ImagePolicyAction.ALLOW:
                    return None
                elif rule.action == ImagePolicyAction.DENY:
                    return f"Image '{image}' denied by rule '{rule.name}': {rule.message}"
                elif rule.action == ImagePolicyAction.REQUIRE_SIGNATURE:
                    if namespace.startswith("prod"):
                        if digest and digest in self._signed_images:
                            return None
                        return (
                            f"Image '{image}' denied by rule '{rule.name}': "
                            f"unsigned image in production namespace"
                        )
                    return None
        return None

    def render_image_policy(self) -> str:
        """Render policy rules table for CLI."""
        lines = [
            "Image Policy Rules",
            "=" * 70,
            f"{'#':>3} {'Name':<30} {'Action':<20} {'Pattern':<15}",
            "-" * 70,
        ]
        for idx, rule in enumerate(self._rules, 1):
            pattern_display = rule.pattern[:15] if len(rule.pattern) > 15 else rule.pattern
            lines.append(
                f"{idx:>3} {rule.name:<30} {rule.action.value:<20} {pattern_display:<15}"
            )
        lines.append("=" * 70)
        lines.append(f"Signed images: {len(self._signed_images)}")
        lines.append(f"Cached digests: {len(self._image_digests)}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# WebhookDispatcher
# ══════════════════════════════════════════════════════════════════

class WebhookDispatcher:
    """Routes AdmissionReview requests to registered webhook endpoints.

    Supports both mutating and validating webhooks with namespace
    and object selectors, failure policies, timeout enforcement,
    and reinvocation for mutating webhooks.
    """

    def __init__(self) -> None:
        self._mutating_webhooks: List[MutatingWebhookConfiguration] = []
        self._validating_webhooks: List[ValidatingWebhookConfiguration] = []
        self._webhook_handlers: Dict[str, Callable] = {}

    def register_mutating_webhook(self, config: MutatingWebhookConfiguration) -> None:
        """Register a mutating webhook."""
        self._mutating_webhooks.append(config)
        logger.info("Registered mutating webhook '%s'", config.name)

    def register_validating_webhook(self, config: ValidatingWebhookConfiguration) -> None:
        """Register a validating webhook."""
        self._validating_webhooks.append(config)
        logger.info("Registered validating webhook '%s'", config.name)

    def register_webhook_handler(self, name: str, handler: Callable) -> None:
        """Register a simulated webhook handler function."""
        self._webhook_handlers[name] = handler

    def dispatch_mutating(self, request: AdmissionRequest) -> List[AdmissionResponse]:
        """Dispatch to all matching mutating webhooks."""
        responses = []
        for config in self._mutating_webhooks:
            if not self._matches_webhook(config, request):
                continue
            review = AdmissionReview(request=request)
            try:
                response = self._call_webhook(config.name, review, config.timeout_seconds)
            except Exception as exc:
                if config.failure_policy == FailurePolicy.IGNORE:
                    response = AdmissionResponse(
                        uid=request.uid,
                        allowed=True,
                        warnings=[f"Webhook '{config.name}' failed: {exc}"],
                    )
                else:
                    response = AdmissionResponse(
                        uid=request.uid,
                        allowed=False,
                        status=AdmissionStatus(
                            code=500,
                            message=f"Webhook '{config.name}' failed: {exc}",
                            reason="WebhookFailure",
                        ),
                    )
            responses.append(response)
        return responses

    def dispatch_validating(self, request: AdmissionRequest) -> List[AdmissionResponse]:
        """Dispatch to all matching validating webhooks."""
        responses = []
        for config in self._validating_webhooks:
            if not self._matches_webhook(config, request):
                continue
            review = AdmissionReview(request=request)
            try:
                response = self._call_webhook(config.name, review, config.timeout_seconds)
            except Exception as exc:
                if config.failure_policy == FailurePolicy.IGNORE:
                    response = AdmissionResponse(
                        uid=request.uid,
                        allowed=True,
                        warnings=[f"Webhook '{config.name}' failed: {exc}"],
                    )
                else:
                    response = AdmissionResponse(
                        uid=request.uid,
                        allowed=False,
                        status=AdmissionStatus(
                            code=500,
                            message=f"Webhook '{config.name}' failed: {exc}",
                            reason="WebhookFailure",
                        ),
                    )
            responses.append(response)
        return responses

    def _matches_webhook(self, config: Any, request: AdmissionRequest) -> bool:
        """Check rules, namespace_selector, and object_selector."""
        if config.namespace_selector:
            obj_labels = (request.object or {}).get("metadata", {}).get("labels", {})
            for key, val in config.namespace_selector.items():
                if obj_labels.get(key) != val:
                    return False

        if config.rules:
            matched = False
            for rule in config.rules:
                if request.operation in rule.operations:
                    matched = True
                    break
            if not matched:
                return False

        return True

    def _call_webhook(
        self,
        name: str,
        review: AdmissionReview,
        timeout: float,
    ) -> AdmissionResponse:
        """Call the registered handler with timeout enforcement."""
        handler = self._webhook_handlers.get(name)
        if handler is None:
            raise AdmissionWebhookUnreachableError(name, "no handler registered")

        result = [None]
        exception = [None]

        def _run():
            try:
                result[0] = handler(review)
            except Exception as exc:
                exception[0] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=min(timeout, MAX_WEBHOOK_TIMEOUT))

        if thread.is_alive():
            raise AdmissionTimeoutError(name, timeout)

        if exception[0] is not None:
            raise AdmissionWebhookError(name, str(exception[0]))

        if result[0] is None:
            raise AdmissionWebhookError(name, "handler returned None")

        return result[0]

    def get_webhook_summary(self) -> List[Dict]:
        """Return webhook list for display."""
        summary = []
        for config in self._mutating_webhooks:
            summary.append({
                "name": config.name,
                "type": "Mutating",
                "failure_policy": config.failure_policy.value,
                "timeout": config.timeout_seconds,
                "reinvocation": config.reinvocation_policy,
            })
        for config in self._validating_webhooks:
            summary.append({
                "name": config.name,
                "type": "Validating",
                "failure_policy": config.failure_policy.value,
                "timeout": config.timeout_seconds,
            })
        return summary


# ══════════════════════════════════════════════════════════════════
# OpenAPISchemaValidator
# ══════════════════════════════════════════════════════════════════

class OpenAPISchemaValidator:
    """Validates custom resource instances against OpenAPI v3 schemas.

    Supports type checking, required fields, enum constraints,
    numeric range validation, string patterns, array bounds, and
    nested object validation.  Also provides default value injection
    and structural schema verification.
    """

    def validate(self, instance: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
        """Return list of validation errors."""
        return self._validate_value(instance, schema, "")

    def _validate_value(
        self,
        value: Any,
        schema: Dict[str, Any],
        path: str,
    ) -> List[str]:
        """Recursively validate a value against its schema."""
        errors = []
        schema_type = schema.get("type")

        if schema_type == "object":
            if not isinstance(value, dict):
                errors.append(f"{path or '/'}: expected object, got {type(value).__name__}")
                return errors
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            for req in required:
                if req not in value:
                    errors.append(f"{path}/{req}: required field missing")
            for prop_name, prop_schema in properties.items():
                if prop_name in value:
                    sub_path = f"{path}/{prop_name}"
                    errors.extend(self._validate_value(value[prop_name], prop_schema, sub_path))

        elif schema_type == "array":
            if not isinstance(value, list):
                errors.append(f"{path or '/'}: expected array, got {type(value).__name__}")
                return errors
            min_items = schema.get("minItems")
            max_items = schema.get("maxItems")
            if min_items is not None and len(value) < min_items:
                errors.append(f"{path}: array length {len(value)} < minItems {min_items}")
            if max_items is not None and len(value) > max_items:
                errors.append(f"{path}: array length {len(value)} > maxItems {max_items}")
            items_schema = schema.get("items", {})
            for idx, item in enumerate(value):
                errors.extend(self._validate_value(item, items_schema, f"{path}/{idx}"))

        elif schema_type == "string":
            if not isinstance(value, str):
                errors.append(f"{path or '/'}: expected string, got {type(value).__name__}")
                return errors
            min_len = schema.get("minLength")
            max_len = schema.get("maxLength")
            if min_len is not None and len(value) < min_len:
                errors.append(f"{path}: string length {len(value)} < minLength {min_len}")
            if max_len is not None and len(value) > max_len:
                errors.append(f"{path}: string length {len(value)} > maxLength {max_len}")
            pattern = schema.get("pattern")
            if pattern and not re.match(pattern, value):
                errors.append(f"{path}: does not match pattern '{pattern}'")
            enum = schema.get("enum")
            if enum and value not in enum:
                errors.append(f"{path}: value '{value}' not in enum {enum}")

        elif schema_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"{path or '/'}: expected integer, got {type(value).__name__}")
                return errors
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                errors.append(f"{path}: value {value} < minimum {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"{path}: value {value} > maximum {maximum}")
            enum = schema.get("enum")
            if enum and value not in enum:
                errors.append(f"{path}: value {value} not in enum {enum}")

        elif schema_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{path or '/'}: expected number, got {type(value).__name__}")
                return errors
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                errors.append(f"{path}: value {value} < minimum {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"{path}: value {value} > maximum {maximum}")

        elif schema_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"{path or '/'}: expected boolean, got {type(value).__name__}")

        return errors

    def apply_defaults(self, instance: Dict, schema: Dict) -> Dict:
        """Apply default values from schema to missing fields."""
        result = dict(instance)
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name not in result and "default" in prop_schema:
                result[prop_name] = copy.deepcopy(prop_schema["default"])
            elif prop_name in result and prop_schema.get("type") == "object":
                result[prop_name] = self.apply_defaults(result[prop_name], prop_schema)
        return result

    def prune_unknown_fields(self, instance: Dict, schema: Dict) -> Dict:
        """Remove fields not defined in schema."""
        if schema.get("type") != "object":
            return instance
        properties = schema.get("properties", {})
        result = {}
        for key, value in instance.items():
            if key in properties:
                if properties[key].get("type") == "object" and isinstance(value, dict):
                    result[key] = self.prune_unknown_fields(value, properties[key])
                else:
                    result[key] = value
        return result

    def is_structural(self, schema: Dict) -> bool:
        """Verify that every field has an explicit type."""
        if "type" not in schema:
            return False
        if schema["type"] == "object":
            for prop_schema in schema.get("properties", {}).values():
                if not self.is_structural(prop_schema):
                    return False
        elif schema["type"] == "array":
            items = schema.get("items", {})
            if items and not self.is_structural(items):
                return False
        return True


# ══════════════════════════════════════════════════════════════════
# CRDRegistry
# ══════════════════════════════════════════════════════════════════

class CRDRegistry:
    """Manages CustomResourceDefinition lifecycle.

    Handles CRD registration with schema validation, instance CRUD
    with schema enforcement, watch notifications for operator
    integration, and status sub-resource management.
    """

    def __init__(self) -> None:
        self._crds: Dict[str, CustomResourceDefinition] = {}
        self._instances: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._validators: Dict[str, Callable] = {}
        self._watchers: Dict[str, List[Callable]] = defaultdict(list)
        self._schema_validator = OpenAPISchemaValidator()
        self._lock = threading.Lock()

    def register_crd(self, crd: CustomResourceDefinition) -> None:
        """Register a new CRD with schema validation."""
        if not crd.names:
            raise CRDRegistrationError("unnamed", "CRD must have names defined")

        crd_name = f"{crd.names.plural}.{crd.group}"

        with self._lock:
            if crd_name in self._crds:
                raise CRDRegistrationError(crd_name, "CRD already registered")

            storage_versions = [v for v in crd.versions if v.storage]
            if len(storage_versions) != 1:
                raise CRDRegistrationError(
                    crd_name,
                    f"Exactly one storage version required, found {len(storage_versions)}",
                )

            for version in crd.versions:
                if version.schema:
                    if not self._schema_validator.is_structural(version.schema):
                        raise CRDSchemaValidationError(
                            crd_name,
                            f"Version '{version.name}' schema is not structural",
                        )

            crd.metadata["uid"] = str(uuid.uuid4())
            crd.metadata["creation_timestamp"] = datetime.now(timezone.utc).isoformat()
            self._crds[crd_name] = crd
            self._instances[crd_name] = {}

            logger.info("Registered CRD '%s' (group=%s)", crd_name, crd.group)

    def unregister_crd(self, name: str) -> None:
        """Delete CRD and garbage-collect all instances."""
        with self._lock:
            if name not in self._crds:
                raise CRDNotFoundError(name)
            del self._crds[name]
            instance_count = len(self._instances.get(name, {}))
            self._instances.pop(name, None)
            logger.info(
                "Unregistered CRD '%s' (deleted %d instances)", name, instance_count
            )

    def get_crd(self, name: str) -> Optional[CustomResourceDefinition]:
        """Look up a CRD by name."""
        return self._crds.get(name)

    def list_crds(self) -> List[CustomResourceDefinition]:
        """List all registered CRDs."""
        return list(self._crds.values())

    def create_instance(
        self,
        crd_name: str,
        namespace: str,
        instance: Dict,
    ) -> Dict:
        """Create a custom resource instance."""
        with self._lock:
            if crd_name not in self._crds:
                raise CRDNotFoundError(crd_name)

            crd = self._crds[crd_name]
            storage_version = next(v for v in crd.versions if v.storage)

            if storage_version.schema:
                errors = self._schema_validator.validate(instance, storage_version.schema)
                if errors:
                    inst_name = instance.get("metadata", {}).get("name", "unknown")
                    raise CRDInstanceValidationError(
                        crd_name, inst_name, "; ".join(errors)
                    )
                instance = self._schema_validator.apply_defaults(instance, storage_version.schema)
                instance = self._schema_validator.prune_unknown_fields(instance, storage_version.schema)

            metadata = instance.setdefault("metadata", {})
            metadata["uid"] = str(uuid.uuid4())
            metadata["namespace"] = namespace
            metadata["creation_timestamp"] = datetime.now(timezone.utc).isoformat()
            metadata["generation"] = 1
            metadata.setdefault("finalizers", [])
            metadata.setdefault("owner_references", [])
            instance.setdefault("status", {})

            inst_name = metadata.get("name", metadata["uid"])
            key = f"{namespace}/{inst_name}"
            self._instances[crd_name][key] = instance

            logger.info("Created instance '%s' of CRD '%s'", key, crd_name)
            self._notify_watchers(crd_name, "ADDED", instance)
            return instance

    def get_instance(
        self,
        crd_name: str,
        namespace: str,
        name: str,
    ) -> Optional[Dict]:
        """Retrieve an instance."""
        key = f"{namespace}/{name}"
        return self._instances.get(crd_name, {}).get(key)

    def list_instances(
        self,
        crd_name: str,
        namespace: str = "",
    ) -> List[Dict]:
        """List instances, optionally filtered by namespace."""
        instances = self._instances.get(crd_name, {})
        if namespace:
            return [
                v for k, v in instances.items()
                if k.startswith(f"{namespace}/")
            ]
        return list(instances.values())

    def update_instance(
        self,
        crd_name: str,
        namespace: str,
        name: str,
        new_spec: Dict,
    ) -> Dict:
        """Update an instance's spec and increment generation."""
        with self._lock:
            key = f"{namespace}/{name}"
            instances = self._instances.get(crd_name, {})
            if key not in instances:
                raise CRDNotFoundError(f"{crd_name}/{key}")

            instance = instances[key]
            instance["spec"] = new_spec
            instance["metadata"]["generation"] = instance["metadata"].get("generation", 0) + 1

            crd = self._crds.get(crd_name)
            if crd:
                storage_version = next((v for v in crd.versions if v.storage), None)
                if storage_version and storage_version.schema:
                    errors = self._schema_validator.validate(instance, storage_version.schema)
                    if errors:
                        raise CRDInstanceValidationError(
                            crd_name, name, "; ".join(errors)
                        )

            self._notify_watchers(crd_name, "MODIFIED", instance)
            return instance

    def update_instance_status(
        self,
        crd_name: str,
        namespace: str,
        name: str,
        status: Dict,
    ) -> Dict:
        """Update status sub-resource without triggering main admission."""
        with self._lock:
            key = f"{namespace}/{name}"
            instances = self._instances.get(crd_name, {})
            if key not in instances:
                raise CRDNotFoundError(f"{crd_name}/{key}")

            instance = instances[key]
            instance["status"] = status
            return instance

    def delete_instance(
        self,
        crd_name: str,
        namespace: str,
        name: str,
        propagation: PropagationPolicy = PropagationPolicy.BACKGROUND,
    ) -> None:
        """Mark an instance for deletion."""
        with self._lock:
            key = f"{namespace}/{name}"
            instances = self._instances.get(crd_name, {})
            if key not in instances:
                raise CRDNotFoundError(f"{crd_name}/{key}")

            instance = instances[key]
            metadata = instance.get("metadata", {})
            finalizers = metadata.get("finalizers", [])

            if finalizers:
                metadata["deletion_timestamp"] = datetime.now(timezone.utc).isoformat()
                logger.info(
                    "Marked '%s' for deletion (waiting on %d finalizers)",
                    key,
                    len(finalizers),
                )
            else:
                del instances[key]
                logger.info("Deleted instance '%s' of CRD '%s'", key, crd_name)

            self._notify_watchers(crd_name, "DELETED", instance)

    def add_watch(self, resource_type: str, callback: Callable) -> None:
        """Register a watch callback for a resource type."""
        self._watchers[resource_type].append(callback)

    def _notify_watchers(
        self,
        resource_type: str,
        event_type: str,
        obj: Dict,
    ) -> None:
        """Notify all registered watchers of a change."""
        for callback in self._watchers.get(resource_type, []):
            try:
                callback(event_type, obj)
            except Exception as exc:
                logger.warning(
                    "Watcher callback for '%s' raised %s: %s",
                    resource_type,
                    type(exc).__name__,
                    exc,
                )

    def remove_instance_finalizer(
        self,
        crd_name: str,
        namespace: str,
        name: str,
    ) -> None:
        """Remove instance after all finalizers are cleared."""
        with self._lock:
            key = f"{namespace}/{name}"
            instances = self._instances.get(crd_name, {})
            if key in instances:
                instance = instances[key]
                finalizers = instance.get("metadata", {}).get("finalizers", [])
                if not finalizers:
                    del instances[key]
                    logger.info(
                        "Garbage collected instance '%s' of CRD '%s'", key, crd_name
                    )

    def render_crd_list(self) -> str:
        """Table of CRDs for display."""
        lines = [
            "Custom Resource Definitions",
            "=" * 80,
            f"{'Name':<40} {'Group':<25} {'Scope':<12} {'Versions'}",
            "-" * 80,
        ]
        for name, crd in sorted(self._crds.items()):
            versions = ", ".join(v.name for v in crd.versions)
            lines.append(f"{name:<40} {crd.group:<25} {crd.scope:<12} {versions}")
        lines.append("=" * 80)
        lines.append(f"Total: {len(self._crds)} CRDs")
        return "\n".join(lines)

    def render_crd_describe(self, name: str) -> str:
        """Detailed CRD view."""
        crd = self._crds.get(name)
        if not crd:
            return f"CRD '{name}' not found"

        lines = [
            f"CRD: {name}",
            "=" * 60,
            f"  Group:    {crd.group}",
            f"  Scope:    {crd.scope}",
            f"  Kind:     {crd.names.kind if crd.names else 'N/A'}",
            f"  Singular: {crd.names.singular if crd.names else 'N/A'}",
            f"  Plural:   {crd.names.plural if crd.names else 'N/A'}",
            "",
            "  Versions:",
        ]
        for v in crd.versions:
            storage = " (storage)" if v.storage else ""
            served = " served" if v.served else " not served"
            lines.append(f"    - {v.name}{storage}{served}")
            if v.subresources:
                lines.append(f"      Subresources: status={v.subresources.status}")
            if v.additional_printer_columns:
                lines.append("      Printer Columns:")
                for col in v.additional_printer_columns:
                    lines.append(f"        {col.name} ({col.type}): {col.json_path}")
        lines.append("=" * 60)

        instances = self._instances.get(name, {})
        lines.append(f"Instances: {len(instances)}")
        return "\n".join(lines)

    def render_crd_instances(self, kind: str, namespace: str = "") -> str:
        """Instance table using printer columns."""
        target_crd = None
        target_name = None
        for name, crd in self._crds.items():
            if crd.names and crd.names.kind == kind:
                target_crd = crd
                target_name = name
                break

        if not target_crd:
            return f"No CRD found with kind '{kind}'"

        instances = self.list_instances(target_name, namespace)
        storage_version = next((v for v in target_crd.versions if v.storage), None)
        columns = storage_version.additional_printer_columns if storage_version else []

        header_parts = ["NAMESPACE", "NAME", "AGE"]
        header_parts.extend(col.name for col in columns)
        header = "  ".join(f"{h:<20}" for h in header_parts)

        lines = [
            f"Instances of {kind}",
            "=" * 80,
            header,
            "-" * 80,
        ]

        for instance in instances:
            meta = instance.get("metadata", {})
            ns = meta.get("namespace", "")
            name = meta.get("name", "")
            age = meta.get("creation_timestamp", "")[:19]
            parts = [ns, name, age]
            for col in columns:
                val = self._resolve_json_path(instance, col.json_path)
                parts.append(str(val) if val is not None else "")
            lines.append("  ".join(f"{p:<20}" for p in parts))

        lines.append("=" * 80)
        lines.append(f"Total: {len(instances)}")
        return "\n".join(lines)

    @staticmethod
    def _resolve_json_path(obj: Dict, path: str) -> Any:
        """Resolve a simple JSON path (dot-separated)."""
        if path.startswith("."):
            path = path[1:]
        parts = path.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current


# ══════════════════════════════════════════════════════════════════
# FinalizerManager
# ══════════════════════════════════════════════════════════════════

class FinalizerManager:
    """Manages resource finalizer lifecycle.

    Finalizers enable cleanup logic on resource deletion.  When a
    resource with finalizers is deleted, the deletion is deferred
    until all finalizer handlers have completed.  Stuck finalizers
    are detected via configurable timeout.
    """

    def __init__(self, *, stuck_timeout: float = DEFAULT_FINALIZER_TIMEOUT) -> None:
        self._finalizer_handlers: Dict[str, Callable] = {}
        self._stuck_timeout = stuck_timeout

    def register_finalizer(self, name: str, handler: Callable) -> None:
        """Register a finalizer handler."""
        self._finalizer_handlers[name] = handler
        logger.info("Registered finalizer handler '%s'", name)

    def add_finalizer(self, resource: Dict, finalizer_name: str) -> Dict:
        """Add finalizer to resource's metadata.finalizers list."""
        metadata = resource.setdefault("metadata", {})
        finalizers = metadata.setdefault("finalizers", [])
        if finalizer_name not in finalizers:
            finalizers.append(finalizer_name)
        return resource

    def process_finalizers(self, resource: Dict) -> Tuple[Dict, bool]:
        """Process finalizers for a resource marked for deletion.

        Returns the updated resource and whether all finalizers have
        been cleared.
        """
        metadata = resource.get("metadata", {})
        if "deletion_timestamp" not in metadata:
            return resource, False

        finalizers = list(metadata.get("finalizers", []))
        cleared = []

        for finalizer_name in finalizers:
            handler = self._finalizer_handlers.get(finalizer_name)
            if handler is None:
                logger.warning(
                    "No handler registered for finalizer '%s'", finalizer_name
                )
                continue
            try:
                handler(resource)
                cleared.append(finalizer_name)
            except Exception as exc:
                logger.warning(
                    "Finalizer '%s' handler failed: %s", finalizer_name, exc
                )

        remaining = [f for f in finalizers if f not in cleared]
        metadata["finalizers"] = remaining

        all_cleared = len(remaining) == 0
        return resource, all_cleared

    def check_stuck(self, resource: Dict) -> bool:
        """Check if deletion_timestamp is older than stuck_timeout."""
        metadata = resource.get("metadata", {})
        deletion_ts = metadata.get("deletion_timestamp")
        if not deletion_ts:
            return False

        try:
            ts = datetime.fromisoformat(deletion_ts.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - ts).total_seconds()
            return elapsed > self._stuck_timeout
        except (ValueError, TypeError):
            return False

    def force_remove_all(self, resource: Dict) -> Dict:
        """Emergency: remove all finalizers regardless of handler state."""
        metadata = resource.get("metadata", {})
        removed = metadata.get("finalizers", [])
        metadata["finalizers"] = []
        logger.warning(
            "Force-removed %d finalizers from '%s'",
            len(removed),
            metadata.get("name", "unknown"),
        )
        return resource


# ══════════════════════════════════════════════════════════════════
# GarbageCollector
# ══════════════════════════════════════════════════════════════════

class GarbageCollector:
    """Processes owner reference relationships for cascading deletion.

    Implements background, foreground, and orphan deletion policies
    based on Kubernetes garbage collection semantics.
    """

    def __init__(self, crd_registry: CRDRegistry) -> None:
        self._crd_registry = crd_registry
        self._deleted_uids: set = set()

    def add_owner_reference(self, child: Dict, owner_ref: OwnerReference) -> Dict:
        """Add owner reference to child's metadata."""
        metadata = child.setdefault("metadata", {})
        refs = metadata.setdefault("owner_references", [])
        ref_dict = {
            "api_version": owner_ref.api_version,
            "kind": owner_ref.kind,
            "name": owner_ref.name,
            "uid": owner_ref.uid,
            "controller": owner_ref.controller,
            "block_owner_deletion": owner_ref.block_owner_deletion,
        }
        refs.append(ref_dict)
        return child

    def delete_with_propagation(
        self,
        resource: Dict,
        policy: PropagationPolicy,
    ) -> None:
        """Delete resource with the specified propagation policy."""
        metadata = resource.get("metadata", {})
        parent_uid = metadata.get("uid", "")
        if parent_uid:
            self._deleted_uids.add(parent_uid)

        if policy == PropagationPolicy.BACKGROUND:
            children = self.find_children(parent_uid)
            for child in children:
                child_meta = child.get("metadata", {})
                child_meta.get("owner_references", []).clear()
            logger.info(
                "Background deletion: parent '%s', %d children orphaned for async cleanup",
                metadata.get("name", ""),
                len(children),
            )

        elif policy == PropagationPolicy.FOREGROUND:
            children = self.find_children(parent_uid)
            for child in children:
                child_meta = child.get("metadata", {})
                child_meta["deletion_timestamp"] = datetime.now(timezone.utc).isoformat()
            logger.info(
                "Foreground deletion: parent '%s', %d children marked for deletion",
                metadata.get("name", ""),
                len(children),
            )

        elif policy == PropagationPolicy.ORPHAN:
            children = self.find_children(parent_uid)
            for child in children:
                child_meta = child.get("metadata", {})
                refs = child_meta.get("owner_references", [])
                child_meta["owner_references"] = [
                    r for r in refs if r.get("uid") != parent_uid
                ]
            logger.info(
                "Orphan deletion: parent '%s', %d children orphaned",
                metadata.get("name", ""),
                len(children),
            )

    def find_children(self, parent_uid: str) -> List[Dict]:
        """Find all instances with owner references matching the parent UID."""
        children = []
        for crd_name in self._crd_registry._instances:
            for key, instance in self._crd_registry._instances[crd_name].items():
                refs = instance.get("metadata", {}).get("owner_references", [])
                for ref in refs:
                    if ref.get("uid") == parent_uid:
                        children.append(instance)
                        break
        return children

    def _is_orphaned(self, resource: Dict) -> bool:
        """Check if all owners in owner_references are gone.

        A resource is orphaned when every owner UID in its
        owner_references has been confirmed absent.  For single-owner
        resources, absence from the registry is sufficient.  For
        multi-owner resources, at least one owner must be explicitly
        confirmed deleted via the garbage collector before the resource
        is considered orphaned — this prevents premature collection of
        resources whose owners are managed outside the CRD framework.
        """
        refs = resource.get("metadata", {}).get("owner_references", [])
        if not refs:
            return False

        confirmed_deleted = 0
        for ref in refs:
            owner_uid = ref.get("uid", "")
            if owner_uid in self._deleted_uids:
                confirmed_deleted += 1
                continue
            # Check if owner exists in the registry
            found = False
            for crd_name in self._crd_registry._instances:
                for key, instance in self._crd_registry._instances[crd_name].items():
                    if instance.get("metadata", {}).get("uid") == owner_uid:
                        found = True
                        break
                if found:
                    break
            if found:
                return False

        # Single-owner: orphaned if owner not found anywhere
        if len(refs) == 1:
            return True
        # Multi-owner: orphaned only if at least one owner was explicitly
        # confirmed deleted (prevents false positives for external owners)
        return confirmed_deleted > 0

    def collect_orphans(self) -> int:
        """Scan for orphaned resources and remove them."""
        collected = 0
        for crd_name in list(self._crd_registry._instances.keys()):
            instances = self._crd_registry._instances.get(crd_name, {})
            to_remove = []
            for key, instance in instances.items():
                if self._is_orphaned(instance):
                    to_remove.append(key)
            for key in to_remove:
                del instances[key]
                collected += 1
        if collected:
            logger.info("Garbage collected %d orphaned resources", collected)
        return collected


# ══════════════════════════════════════════════════════════════════
# Reconciler (Abstract Base)
# ══════════════════════════════════════════════════════════════════

class Reconciler:
    """Interface for operator reconciliation logic."""

    def reconcile(self, request: ReconcileRequest) -> ReconcileResult:
        """Reconcile the desired and actual state of a custom resource."""
        raise NotImplementedError


# ══════════════════════════════════════════════════════════════════
# ReconcileLoop
# ══════════════════════════════════════════════════════════════════

class ReconcileLoop:
    """Event-driven reconciliation loop with backoff and deduplication.

    Processes work queue items by calling the reconciler, handling
    success, requeue, and error cases with exponential backoff and
    leader election gating.
    """

    def __init__(
        self,
        reconciler: Reconciler,
        resource_type: str,
        *,
        max_concurrent: int = DEFAULT_RECONCILE_MAX_CONCURRENT,
        backoff_base: float = DEFAULT_RECONCILE_BACKOFF_BASE,
        backoff_cap: float = DEFAULT_RECONCILE_BACKOFF_CAP,
        backoff_multiplier: float = DEFAULT_RECONCILE_BACKOFF_MULTIPLIER,
        max_queue_depth: int = DEFAULT_MAX_WORK_QUEUE_DEPTH,
    ) -> None:
        self._reconciler = reconciler
        self._resource_type = resource_type
        self._work_queue: deque = deque()
        self._queued_keys: Set[str] = set()
        self._metrics = OperatorMetrics()
        self._max_concurrent = max_concurrent
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._backoff_multiplier = backoff_multiplier
        self._max_queue_depth = max_queue_depth
        self._error_counts: Dict[str, int] = {}
        self._is_leader = False
        self._running = False
        self._lock = threading.Lock()

    def enqueue(self, key: str) -> None:
        """Add a resource key to the work queue."""
        with self._lock:
            if key in self._queued_keys:
                return
            if len(self._work_queue) >= self._max_queue_depth:
                logger.warning(
                    "Work queue at capacity (%d), dropping key '%s'",
                    self._max_queue_depth,
                    key,
                )
                return
            self._work_queue.append(key)
            self._queued_keys.add(key)
            self._metrics.work_queue_depth = len(self._work_queue)

    def run(self) -> None:
        """Process all items currently in the work queue."""
        if not self._is_leader:
            return

        self._running = True
        processed = 0
        while self._work_queue and self._running:
            with self._lock:
                if not self._work_queue:
                    break
                key = self._work_queue.popleft()
                self._queued_keys.discard(key)
                self._metrics.work_queue_depth = len(self._work_queue)

            self._process_item(key)
            processed += 1

            if processed >= self._max_concurrent * 10:
                break

        self._running = False

    def _process_item(self, key: str) -> None:
        """Process a single work queue item."""
        parts = key.split("/", 1)
        namespace = parts[0] if len(parts) > 1 else ""
        name = parts[1] if len(parts) > 1 else parts[0]

        start_time = time.monotonic()
        self._metrics.active_reconciles += 1
        self._metrics.reconcile_total += 1

        try:
            result = self._reconciler.reconcile(
                ReconcileRequest(name=name, namespace=namespace)
            )
            elapsed = (time.monotonic() - start_time) * 1000.0
            self._metrics.reconcile_latency_samples.append(elapsed)

            if result.error:
                self._metrics.reconcile_error += 1
                error_count = self._error_counts.get(key, 0) + 1
                self._error_counts[key] = error_count
                backoff = self._compute_backoff(error_count)
                self.enqueue(key)
                logger.warning(
                    "Reconcile error for '%s': %s (retry #%d, backoff=%.1fs)",
                    key,
                    result.error,
                    error_count,
                    backoff,
                )
            elif result.requeue:
                self._metrics.reconcile_success += 1
                self._error_counts.pop(key, None)
                self.enqueue(key)
            else:
                self._metrics.reconcile_success += 1
                self._error_counts.pop(key, None)

        except Exception as exc:
            elapsed = (time.monotonic() - start_time) * 1000.0
            self._metrics.reconcile_latency_samples.append(elapsed)
            self._metrics.reconcile_error += 1
            error_count = self._error_counts.get(key, 0) + 1
            self._error_counts[key] = error_count
            self.enqueue(key)
            logger.error(
                "Reconcile exception for '%s': %s",
                key,
                exc,
            )
        finally:
            self._metrics.active_reconciles = max(
                0, self._metrics.active_reconciles - 1
            )

    def _compute_backoff(self, error_count: int) -> float:
        """Compute exponential backoff with cap."""
        delay = self._backoff_base * (self._backoff_multiplier ** (error_count - 1))
        return min(delay, self._backoff_cap)

    def acquire_leadership(self) -> bool:
        """Simulated leader election."""
        self._is_leader = True
        logger.info("Leader election: acquired leadership for '%s'", self._resource_type)
        return True

    def renew_leadership(self) -> bool:
        """Renew the leader lease."""
        return self._is_leader

    def get_metrics(self) -> OperatorMetrics:
        """Return current metrics."""
        return self._metrics


# ══════════════════════════════════════════════════════════════════
# OperatorBuilder
# ══════════════════════════════════════════════════════════════════

class OperatorBuilder:
    """Fluent builder for constructing operator controllers.

    Provides a builder-pattern API for configuring the primary resource,
    reconciler, finalizer, owned resources, watched resources, and
    concurrency settings.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._group = ""
        self._version = ""
        self._kind = ""
        self._reconciler: Optional[Reconciler] = None
        self._finalizer: Optional[str] = None
        self._owned: List[GroupVersionKind] = []
        self._watches: List[Tuple[GroupVersionKind, Callable]] = []
        self._max_concurrent = DEFAULT_RECONCILE_MAX_CONCURRENT
        self._backoff_base = DEFAULT_RECONCILE_BACKOFF_BASE
        self._backoff_cap = DEFAULT_RECONCILE_BACKOFF_CAP
        self._crd_registry: Optional[CRDRegistry] = None

    def for_resource(self, group: str, version: str, kind: str) -> "OperatorBuilder":
        """Set the primary resource."""
        self._group = group
        self._version = version
        self._kind = kind
        return self

    def with_reconciler(self, reconciler: Reconciler) -> "OperatorBuilder":
        """Set the reconciler."""
        self._reconciler = reconciler
        return self

    def with_finalizer(self, name: str) -> "OperatorBuilder":
        """Register a finalizer."""
        self._finalizer = name
        return self

    def owns(self, group: str, version: str, kind: str) -> "OperatorBuilder":
        """Declare owned child resource type."""
        self._owned.append(GroupVersionKind(group=group, version=version, kind=kind))
        return self

    def watches(
        self,
        group: str,
        version: str,
        kind: str,
        handler: Callable,
    ) -> "OperatorBuilder":
        """Watch additional resource type."""
        gvk = GroupVersionKind(group=group, version=version, kind=kind)
        self._watches.append((gvk, handler))
        return self

    def with_max_concurrent_reconciles(self, n: int) -> "OperatorBuilder":
        """Set max concurrency."""
        self._max_concurrent = n
        return self

    def with_rate_limiter(
        self,
        max_delay: float,
        base_delay: float,
    ) -> "OperatorBuilder":
        """Configure rate limiter."""
        self._backoff_cap = max_delay
        self._backoff_base = base_delay
        return self

    def with_crd_registry(self, registry: CRDRegistry) -> "OperatorBuilder":
        """Set the CRD registry reference."""
        self._crd_registry = registry
        return self

    def build(self) -> "Operator":
        """Validate and build the operator."""
        if not self._reconciler:
            raise OperatorError(self._name, "Reconciler is required")
        if not self._kind:
            raise OperatorError(self._name, "Primary resource is required")

        loop = ReconcileLoop(
            reconciler=self._reconciler,
            resource_type=f"{self._group}/{self._version}/{self._kind}",
            max_concurrent=self._max_concurrent,
            backoff_base=self._backoff_base,
            backoff_cap=self._backoff_cap,
        )

        return Operator(
            name=self._name,
            loop=loop,
            primary_gvk=GroupVersionKind(
                group=self._group,
                version=self._version,
                kind=self._kind,
            ),
            owned_gvks=list(self._owned),
            watched_gvks=list(self._watches),
            finalizer_name=self._finalizer,
            crd_registry=self._crd_registry,
        )


# ══════════════════════════════════════════════════════════════════
# Operator
# ══════════════════════════════════════════════════════════════════

class Operator:
    """Runtime wrapper around the reconcile loop and operator config.

    Manages the operator lifecycle (start, stop, leadership),
    handles events from the CRD registry, and exposes operator
    status and metrics.
    """

    def __init__(
        self,
        name: str,
        loop: ReconcileLoop,
        primary_gvk: GroupVersionKind,
        owned_gvks: List[GroupVersionKind],
        watched_gvks: List[Tuple[GroupVersionKind, Callable]],
        finalizer_name: Optional[str],
        crd_registry: Optional[CRDRegistry],
    ) -> None:
        self._name = name
        self._loop = loop
        self._primary_gvk = primary_gvk
        self._owned_gvks = owned_gvks
        self._watched_gvks = watched_gvks
        self._finalizer_name = finalizer_name
        self._crd_registry = crd_registry

    def start(self) -> None:
        """Start the reconcile loop and register watch callbacks."""
        self._loop.acquire_leadership()
        if self._crd_registry:
            for crd_name in self._crd_registry._crds:
                crd = self._crd_registry._crds[crd_name]
                if crd.names and crd.names.kind == self._primary_gvk.kind:
                    self._crd_registry.add_watch(crd_name, self.handle_event)
        logger.info("Operator '%s' started", self._name)

    def stop(self) -> None:
        """Stop the reconcile loop."""
        self._loop._running = False
        logger.info("Operator '%s' stopped", self._name)

    def handle_event(self, event_type: str, obj: Dict) -> None:
        """Map an event to a reconcile request and enqueue."""
        meta = obj.get("metadata", {})
        ns = meta.get("namespace", "")
        name = meta.get("name", "")
        key = f"{ns}/{name}" if ns else name
        self._loop.enqueue(key)

    def get_status(self) -> Dict:
        """Return operator status."""
        metrics = self._loop.get_metrics()
        return {
            "name": self._name,
            "primary_resource": f"{self._primary_gvk.group}/{self._primary_gvk.version}/{self._primary_gvk.kind}",
            "is_leader": self._loop._is_leader,
            "queue_depth": metrics.work_queue_depth,
            "reconcile_total": metrics.reconcile_total,
            "reconcile_success": metrics.reconcile_success,
            "reconcile_error": metrics.reconcile_error,
            "active_reconciles": metrics.active_reconciles,
        }


# ══════════════════════════════════════════════════════════════════
# FizzBuzzClusterOperator
# ══════════════════════════════════════════════════════════════════

class FizzBuzzClusterOperator(Reconciler):
    """Operator for the FizzBuzzCluster CRD.

    Reconciles the desired state of a FizzBuzzCluster by managing
    owned resources (Deployment, Service, ConfigMap) and updating
    the cluster status (phase, ready replicas, conditions).
    """

    FINALIZER = "fizzbuzzcluster.fizzadmit.fizzkube.io/cleanup"

    def __init__(
        self,
        crd_registry: CRDRegistry,
        finalizer_manager: FinalizerManager,
    ) -> None:
        self._crd_registry = crd_registry
        self._finalizer_manager = finalizer_manager
        self._crd_name = "fizzbuzzclusters.fizzbuzz.io"

    def reconcile(self, request: ReconcileRequest) -> ReconcileResult:
        """Reconcile a FizzBuzzCluster instance."""
        instance = self._crd_registry.get_instance(
            self._crd_name,
            request.namespace,
            request.name,
        )
        if instance is None:
            return ReconcileResult()

        metadata = instance.get("metadata", {})

        # Handle deletion
        if "deletion_timestamp" in metadata:
            finalizers = metadata.get("finalizers", [])
            if self.FINALIZER in finalizers:
                self._cleanup(instance)
                finalizers.remove(self.FINALIZER)
                metadata["finalizers"] = finalizers
                self._crd_registry.remove_instance_finalizer(
                    self._crd_name,
                    request.namespace,
                    request.name,
                )
            return ReconcileResult()

        # Ensure finalizer
        if self.FINALIZER not in metadata.get("finalizers", []):
            self._finalizer_manager.add_finalizer(instance, self.FINALIZER)

        # Read spec
        spec = instance.get("spec", {})
        replicas = spec.get("replicas", 1)
        rules = spec.get("rules", ["fizz", "buzz"])
        cache_enabled = spec.get("cache_enabled", False)

        # Determine phase
        phase = "Running"
        ready_replicas = replicas

        # Update status
        status = {
            "phase": phase,
            "ready_replicas": ready_replicas,
            "desired_replicas": replicas,
            "current_rules": rules,
            "cache_enabled": cache_enabled,
            "conditions": [
                {
                    "type": "Available",
                    "status": "True",
                    "reason": "ReplicasReady",
                    "message": f"{ready_replicas}/{replicas} replicas ready",
                    "last_transition_time": datetime.now(timezone.utc).isoformat(),
                },
            ],
            "observed_generation": metadata.get("generation", 1),
        }
        self._crd_registry.update_instance_status(
            self._crd_name,
            request.namespace,
            request.name,
            status,
        )

        return ReconcileResult()

    def _cleanup(self, instance: Dict) -> None:
        """Clean up owned resources on deletion."""
        meta = instance.get("metadata", {})
        logger.info(
            "Cleaning up FizzBuzzCluster '%s/%s' owned resources",
            meta.get("namespace", ""),
            meta.get("name", ""),
        )


# ══════════════════════════════════════════════════════════════════
# FizzBuzzBackupOperator
# ══════════════════════════════════════════════════════════════════

class FizzBuzzBackupOperator(Reconciler):
    """Operator for the FizzBuzzBackup CRD.

    Manages scheduled state backups with retention enforcement
    and lifecycle tracking.
    """

    FINALIZER = "fizzbuzzbackup.fizzadmit.fizzkube.io/cleanup"

    def __init__(
        self,
        crd_registry: CRDRegistry,
        finalizer_manager: FinalizerManager,
    ) -> None:
        self._crd_registry = crd_registry
        self._finalizer_manager = finalizer_manager
        self._crd_name = "fizzbuzzbackups.fizzbuzz.io"

    def reconcile(self, request: ReconcileRequest) -> ReconcileResult:
        """Reconcile a FizzBuzzBackup instance."""
        instance = self._crd_registry.get_instance(
            self._crd_name,
            request.namespace,
            request.name,
        )
        if instance is None:
            return ReconcileResult()

        metadata = instance.get("metadata", {})

        # Handle deletion
        if "deletion_timestamp" in metadata:
            finalizers = metadata.get("finalizers", [])
            if self.FINALIZER in finalizers:
                finalizers.remove(self.FINALIZER)
                metadata["finalizers"] = finalizers
                self._crd_registry.remove_instance_finalizer(
                    self._crd_name,
                    request.namespace,
                    request.name,
                )
            return ReconcileResult()

        # Ensure finalizer
        if self.FINALIZER not in metadata.get("finalizers", []):
            self._finalizer_manager.add_finalizer(instance, self.FINALIZER)

        # Read spec
        spec = instance.get("spec", {})
        schedule = spec.get("schedule", "0 * * * *")
        retention_count = spec.get("retention_count", 5)

        # Simulate backup status
        now = datetime.now(timezone.utc)
        status = {
            "last_backup_time": now.isoformat(),
            "last_backup_status": "Completed",
            "backup_count": 1,
            "retention_count": retention_count,
            "schedule": schedule,
            "next_scheduled_backup": now.isoformat(),
        }
        self._crd_registry.update_instance_status(
            self._crd_name,
            request.namespace,
            request.name,
            status,
        )

        return ReconcileResult()


# ══════════════════════════════════════════════════════════════════
# FizzAdmitSubsystem
# ══════════════════════════════════════════════════════════════════

class FizzAdmitSubsystem:
    """Container for all FizzAdmit components.

    Provides a unified handle for the admission chain, CRD registry,
    webhook dispatcher, finalizer manager, garbage collector, and
    registered operators.
    """

    def __init__(
        self,
        admission_chain: AdmissionChain,
        crd_registry: CRDRegistry,
        webhook_dispatcher: WebhookDispatcher,
        finalizer_manager: FinalizerManager,
        garbage_collector: GarbageCollector,
        operators: Dict[str, Operator],
        schema_validator: OpenAPISchemaValidator,
    ) -> None:
        self.admission_chain = admission_chain
        self.crd_registry = crd_registry
        self.webhook_dispatcher = webhook_dispatcher
        self.finalizer_manager = finalizer_manager
        self.garbage_collector = garbage_collector
        self.operators = operators
        self.schema_validator = schema_validator


# ══════════════════════════════════════════════════════════════════
# FizzAdmitMiddleware
# ══════════════════════════════════════════════════════════════════

class FizzAdmitMiddleware(IMiddleware):
    """Integrates FizzAdmit with the FizzBuzz evaluation middleware pipeline.

    Intercepts each evaluation to run a lightweight admission check,
    annotating the context with admission metadata.  Provides CLI
    rendering methods for all FizzAdmit dashboards and reports.
    """

    priority = MIDDLEWARE_PRIORITY

    def __init__(
        self,
        subsystem: FizzAdmitSubsystem,
        *,
        dashboard_width: int = 80,
    ) -> None:
        self._subsystem = subsystem
        self._dashboard_width = dashboard_width
        self._evaluations_processed = 0
        self._admissions_denied = 0

    def get_name(self) -> str:
        return "FizzAdmitMiddleware"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable,
    ) -> FizzBuzzResult:
        """Run admission check for each evaluation."""
        self._evaluations_processed += 1

        # Construct a lightweight admission request from the evaluation context
        request = AdmissionRequest(
            uid=str(uuid.uuid4()),
            kind=GroupVersionKind(
                group="fizzbuzz.io",
                version="v1",
                kind="Evaluation",
            ),
            resource=GroupVersionResource(
                group="fizzbuzz.io",
                version="v1",
                resource="evaluations",
            ),
            operation=AdmissionOperation.CREATE,
            namespace=getattr(context, "namespace", "default"),
            name=f"eval-{context.number}",
            object={
                "metadata": {
                    "name": f"eval-{context.number}",
                    "namespace": getattr(context, "namespace", "default"),
                },
                "spec": {
                    "number": context.number,
                },
            },
        )

        response = self._subsystem.admission_chain.admit(request)

        if not response.allowed:
            self._admissions_denied += 1
            context.metadata["fizzadmit_denied"] = True
            context.metadata["fizzadmit_reason"] = (
                response.status.message if response.status else "denied"
            )
        else:
            context.metadata["fizzadmit_admitted"] = True
            context.metadata["fizzadmit_mutations"] = (
                len(response.patch) if response.patch else 0
            )

        return next_handler(context)

    def render_admission_chain(self) -> str:
        """Table of registered controllers."""
        chain = self._subsystem.admission_chain.get_chain_summary()
        lines = [
            "FizzAdmit Admission Chain",
            "=" * 80,
            f"{'#':>3} {'Name':<30} {'Phase':<12} {'Pri':>5} {'Fail':>6} {'Effects':<8} {'Ops'}",
            "-" * 80,
        ]
        for idx, entry in enumerate(chain, 1):
            ops = ",".join(entry["operations"])
            lines.append(
                f"{idx:>3} {entry['name']:<30} {entry['phase']:<12} "
                f"{entry['priority']:>5} {entry['failure_policy']:>6} "
                f"{entry['side_effects']:<8} {ops}"
            )
        lines.append("=" * 80)
        lines.append(f"Total: {len(chain)} controllers")
        return "\n".join(lines)

    def render_quota_status(self, namespace: str) -> str:
        """Delegate to ResourceQuotaAdmissionController."""
        for reg in self._subsystem.admission_chain._mutating:
            if isinstance(reg.controller, ResourceQuotaAdmissionController):
                return reg.controller.render_quota_status(namespace)
        return f"ResourceQuota controller not found"

    def render_limit_range(self, namespace: str) -> str:
        """Delegate to LimitRangerAdmissionController."""
        for reg in self._subsystem.admission_chain._mutating:
            if isinstance(reg.controller, LimitRangerAdmissionController):
                return reg.controller.render_limit_range(namespace)
        return f"LimitRanger controller not found"

    def render_security_profile(self, namespace: str) -> str:
        """Delegate to PodSecurityAdmissionController."""
        for reg in self._subsystem.admission_chain._validating:
            if isinstance(reg.controller, PodSecurityAdmissionController):
                return reg.controller.render_security_profile(namespace)
        return f"PodSecurityAdmission controller not found"

    def render_image_policy(self) -> str:
        """Delegate to ImagePolicyAdmissionController."""
        for reg in self._subsystem.admission_chain._validating:
            if isinstance(reg.controller, ImagePolicyAdmissionController):
                return reg.controller.render_image_policy()
        return f"ImagePolicy controller not found"

    def render_webhooks(self) -> str:
        """Delegate to WebhookDispatcher."""
        webhooks = self._subsystem.webhook_dispatcher.get_webhook_summary()
        lines = [
            "Webhook Configurations",
            "=" * 70,
            f"{'Name':<30} {'Type':<12} {'Fail Policy':<12} {'Timeout':>8}",
            "-" * 70,
        ]
        for wh in webhooks:
            lines.append(
                f"{wh['name']:<30} {wh['type']:<12} "
                f"{wh['failure_policy']:<12} {wh['timeout']:>7.1f}s"
            )
        lines.append("=" * 70)
        lines.append(f"Total: {len(webhooks)} webhooks")
        return "\n".join(lines)

    def render_crd_list(self) -> str:
        """Delegate to CRDRegistry."""
        return self._subsystem.crd_registry.render_crd_list()

    def render_crd_describe(self, name: str) -> str:
        """Delegate to CRDRegistry."""
        return self._subsystem.crd_registry.render_crd_describe(name)

    def render_crd_instances(self, kind: str, namespace: str = "") -> str:
        """Delegate to CRDRegistry."""
        return self._subsystem.crd_registry.render_crd_instances(kind, namespace)

    def render_operators(self) -> str:
        """Table of operator status."""
        operators = self._subsystem.operators
        lines = [
            "FizzAdmit Operators",
            "=" * 80,
            f"{'Name':<25} {'Resource':<35} {'Leader':>7} {'Queue':>6} "
            f"{'Total':>6} {'OK':>5} {'Err':>5}",
            "-" * 80,
        ]
        for name, op in sorted(operators.items()):
            status = op.get_status()
            lines.append(
                f"{status['name']:<25} {status['primary_resource']:<35} "
                f"{'Yes' if status['is_leader'] else 'No':>7} "
                f"{status['queue_depth']:>6} {status['reconcile_total']:>6} "
                f"{status['reconcile_success']:>5} {status['reconcile_error']:>5}"
            )
        lines.append("=" * 80)
        lines.append(f"Total: {len(operators)} operators")
        return "\n".join(lines)

    def render_dashboard(self) -> str:
        """Summary dashboard with admission chain, CRDs, operator health."""
        sep = "=" * self._dashboard_width
        lines = [
            sep,
            f"{'FizzAdmit Dashboard':^{self._dashboard_width}}",
            f"{'Admission Controllers & CRD Operator Framework':^{self._dashboard_width}}",
            sep,
            "",
            f"  Version:             {FIZZADMIT_VERSION}",
            f"  Evaluations:         {self._evaluations_processed}",
            f"  Denied:              {self._admissions_denied}",
            f"  Admission API:       {ADMISSION_API_VERSION}",
            f"  CRD API:             {CRD_API_VERSION}",
            "",
        ]

        # Admission chain summary
        chain = self._subsystem.admission_chain.get_chain_summary()
        mutating = [c for c in chain if c["phase"] == "MUTATING"]
        validating = [c for c in chain if c["phase"] == "VALIDATING"]
        lines.append(f"  Admission Chain:")
        lines.append(f"    Mutating:   {len(mutating)} controllers")
        lines.append(f"    Validating: {len(validating)} controllers")
        lines.append("")

        # CRD summary
        crds = self._subsystem.crd_registry.list_crds()
        lines.append(f"  Custom Resources:")
        lines.append(f"    CRDs:       {len(crds)}")
        total_instances = sum(
            len(self._subsystem.crd_registry._instances.get(
                f"{c.names.plural}.{c.group}", {}
            ))
            for c in crds if c.names
        )
        lines.append(f"    Instances:  {total_instances}")
        lines.append("")

        # Webhook summary
        webhooks = self._subsystem.webhook_dispatcher.get_webhook_summary()
        lines.append(f"  Webhooks:      {len(webhooks)}")
        lines.append("")

        # Operator summary
        operators = self._subsystem.operators
        lines.append(f"  Operators:     {len(operators)}")
        for name, op in sorted(operators.items()):
            status = op.get_status()
            lines.append(
                f"    {name}: {status['reconcile_total']} reconciles, "
                f"{status['reconcile_error']} errors"
            )
        lines.append("")

        # Audit log summary
        audit_log = self._subsystem.admission_chain.get_audit_log(limit=5)
        lines.append(f"  Recent Audit (last {len(audit_log)}):")
        for record in audit_log:
            status = "ALLOW" if record.allowed else "DENY"
            lines.append(
                f"    [{status}] {record.controller_name}: "
                f"{record.operation} {record.resource} "
                f"({record.latency_ms:.1f}ms)"
            )

        lines.append("")
        lines.append(sep)
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# Factory Function
# ══════════════════════════════════════════════════════════════════

def _build_fizzbuzzcluster_crd() -> CustomResourceDefinition:
    """Build the FizzBuzzCluster CRD definition."""
    return CustomResourceDefinition(
        group="fizzbuzz.io",
        names=CRDNames(
            kind="FizzBuzzCluster",
            singular="fizzbuzzcluster",
            plural="fizzbuzzclusters",
            short_names=["fbc"],
            categories=["fizzbuzz"],
        ),
        scope="NAMESPACED",
        versions=[
            CRDVersion(
                name="v1",
                served=True,
                storage=True,
                schema={
                    "type": "object",
                    "properties": {
                        "metadata": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "namespace": {"type": "string"},
                            },
                        },
                        "spec": {
                            "type": "object",
                            "required": ["replicas"],
                            "properties": {
                                "replicas": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 100,
                                    "default": 3,
                                },
                                "rules": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": ["fizz", "buzz"],
                                },
                                "cache_enabled": {
                                    "type": "boolean",
                                    "default": False,
                                },
                            },
                        },
                        "status": {
                            "type": "object",
                            "properties": {
                                "phase": {"type": "string"},
                                "ready_replicas": {"type": "integer"},
                                "desired_replicas": {"type": "integer"},
                            },
                        },
                    },
                },
                subresources=SubResources(
                    status=True,
                    scale={
                        "spec_replicas_path": ".spec.replicas",
                        "status_replicas_path": ".status.ready_replicas",
                    },
                ),
                additional_printer_columns=[
                    PrinterColumn(
                        name="REPLICAS",
                        type="integer",
                        json_path=".spec.replicas",
                    ),
                    PrinterColumn(
                        name="PHASE",
                        type="string",
                        json_path=".status.phase",
                    ),
                    PrinterColumn(
                        name="READY",
                        type="integer",
                        json_path=".status.ready_replicas",
                    ),
                ],
            ),
        ],
    )


def _build_fizzbuzzbackup_crd() -> CustomResourceDefinition:
    """Build the FizzBuzzBackup CRD definition."""
    return CustomResourceDefinition(
        group="fizzbuzz.io",
        names=CRDNames(
            kind="FizzBuzzBackup",
            singular="fizzbuzzbackup",
            plural="fizzbuzzbackups",
            short_names=["fbb"],
            categories=["fizzbuzz"],
        ),
        scope="NAMESPACED",
        versions=[
            CRDVersion(
                name="v1",
                served=True,
                storage=True,
                schema={
                    "type": "object",
                    "properties": {
                        "metadata": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "namespace": {"type": "string"},
                            },
                        },
                        "spec": {
                            "type": "object",
                            "properties": {
                                "schedule": {
                                    "type": "string",
                                    "default": "0 * * * *",
                                },
                                "retention_count": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "default": 5,
                                },
                                "delete_backups_on_remove": {
                                    "type": "boolean",
                                    "default": False,
                                },
                            },
                        },
                        "status": {
                            "type": "object",
                            "properties": {
                                "last_backup_time": {"type": "string"},
                                "last_backup_status": {"type": "string"},
                                "backup_count": {"type": "integer"},
                            },
                        },
                    },
                },
                subresources=SubResources(status=True),
                additional_printer_columns=[
                    PrinterColumn(
                        name="SCHEDULE",
                        type="string",
                        json_path=".spec.schedule",
                    ),
                    PrinterColumn(
                        name="LAST BACKUP",
                        type="string",
                        json_path=".status.last_backup_time",
                    ),
                    PrinterColumn(
                        name="STATUS",
                        type="string",
                        json_path=".status.last_backup_status",
                    ),
                ],
            ),
        ],
    )


def create_fizzadmit_subsystem(
    *,
    admission_timeout: float = DEFAULT_ADMISSION_TIMEOUT,
    finalizer_timeout: float = DEFAULT_FINALIZER_TIMEOUT,
    reconcile_max_concurrent: int = DEFAULT_RECONCILE_MAX_CONCURRENT,
    reconcile_backoff_base: float = DEFAULT_RECONCILE_BACKOFF_BASE,
    reconcile_backoff_cap: float = DEFAULT_RECONCILE_BACKOFF_CAP,
    leader_election_lease: float = DEFAULT_LEADER_ELECTION_LEASE,
    enable_default_image_rules: bool = True,
    default_security_profile: str = "BASELINE",
    dashboard_width: int = 80,
) -> Tuple[FizzAdmitSubsystem, FizzAdmitMiddleware]:
    """Create and wire all FizzAdmit components.

    Instantiates the admission chain with four built-in controllers,
    the CRD registry with two built-in CRDs, the webhook dispatcher,
    the finalizer manager, the garbage collector, and two built-in
    operators (FizzBuzzCluster, FizzBuzzBackup).

    Returns:
        A tuple of (subsystem handle, middleware instance).
    """
    # Core components
    crd_registry = CRDRegistry()
    finalizer_manager = FinalizerManager(stuck_timeout=finalizer_timeout)
    garbage_collector = GarbageCollector(crd_registry)
    schema_validator = OpenAPISchemaValidator()
    admission_chain = AdmissionChain()

    # Built-in controllers
    quota_controller = ResourceQuotaAdmissionController()
    limit_ranger = LimitRangerAdmissionController()
    pod_security = PodSecurityAdmissionController()
    image_policy = ImagePolicyAdmissionController()

    if enable_default_image_rules:
        image_policy.set_default_rules()

    # Register built-in controllers
    admission_chain.register(AdmissionControllerRegistration(
        name="ResourceQuota",
        phase=AdmissionPhase.MUTATING,
        priority=100,
        controller=quota_controller,
        operations=[
            AdmissionOperation.CREATE,
            AdmissionOperation.UPDATE,
            AdmissionOperation.DELETE,
        ],
    ))
    admission_chain.register(AdmissionControllerRegistration(
        name="LimitRanger",
        phase=AdmissionPhase.MUTATING,
        priority=200,
        controller=limit_ranger,
    ))
    admission_chain.register(AdmissionControllerRegistration(
        name="PodSecurityAdmission",
        phase=AdmissionPhase.VALIDATING,
        priority=300,
        controller=pod_security,
    ))
    admission_chain.register(AdmissionControllerRegistration(
        name="ImagePolicy",
        phase=AdmissionPhase.VALIDATING,
        priority=400,
        controller=image_policy,
    ))

    # Webhook dispatcher
    webhook_dispatcher = WebhookDispatcher()

    # Register built-in CRDs
    cluster_crd = _build_fizzbuzzcluster_crd()
    backup_crd = _build_fizzbuzzbackup_crd()
    crd_registry.register_crd(cluster_crd)
    crd_registry.register_crd(backup_crd)

    # Built-in operators
    cluster_operator_reconciler = FizzBuzzClusterOperator(crd_registry, finalizer_manager)
    backup_operator_reconciler = FizzBuzzBackupOperator(crd_registry, finalizer_manager)

    cluster_operator = (
        OperatorBuilder("fizzbuzz-cluster-operator")
        .for_resource("fizzbuzz.io", "v1", "FizzBuzzCluster")
        .with_reconciler(cluster_operator_reconciler)
        .with_finalizer(FizzBuzzClusterOperator.FINALIZER)
        .with_max_concurrent_reconciles(reconcile_max_concurrent)
        .with_rate_limiter(reconcile_backoff_cap, reconcile_backoff_base)
        .with_crd_registry(crd_registry)
        .build()
    )

    backup_operator = (
        OperatorBuilder("fizzbuzz-backup-operator")
        .for_resource("fizzbuzz.io", "v1", "FizzBuzzBackup")
        .with_reconciler(backup_operator_reconciler)
        .with_finalizer(FizzBuzzBackupOperator.FINALIZER)
        .with_max_concurrent_reconciles(reconcile_max_concurrent)
        .with_rate_limiter(reconcile_backoff_cap, reconcile_backoff_base)
        .with_crd_registry(crd_registry)
        .build()
    )

    operators = {
        "fizzbuzz-cluster-operator": cluster_operator,
        "fizzbuzz-backup-operator": backup_operator,
    }

    # Start operators
    for op in operators.values():
        op.start()

    # Register finalizer handlers
    finalizer_manager.register_finalizer(
        FizzBuzzClusterOperator.FINALIZER,
        lambda resource: None,
    )
    finalizer_manager.register_finalizer(
        FizzBuzzBackupOperator.FINALIZER,
        lambda resource: None,
    )

    # Assemble subsystem
    subsystem = FizzAdmitSubsystem(
        admission_chain=admission_chain,
        crd_registry=crd_registry,
        webhook_dispatcher=webhook_dispatcher,
        finalizer_manager=finalizer_manager,
        garbage_collector=garbage_collector,
        operators=operators,
        schema_validator=schema_validator,
    )

    middleware = FizzAdmitMiddleware(
        subsystem=subsystem,
        dashboard_width=dashboard_width,
    )

    logger.info(
        "FizzAdmit subsystem initialized: "
        "%d controllers, %d CRDs, %d operators",
        len(admission_chain.get_chain_summary()),
        len(crd_registry.list_crds()),
        len(operators),
    )

    return subsystem, middleware
