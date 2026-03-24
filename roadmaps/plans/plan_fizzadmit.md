# Implementation Plan: FizzAdmit -- Admission Controllers & CRD Operator Framework

**Source:** Brainstorm Report, TeraSwarm Cycle, Idea 7
**Target File:** `enterprise_fizzbuzz/infrastructure/fizzadmit.py`
**Target Lines:** ~3,500
**Target Tests:** ~500 (in `tests/test_fizzadmit.py`)
**Middleware Priority:** 119
**Error Code Prefix:** EFP-ADM

---

## 1. Module Docstring

```python
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
```

---

## 3. Constants (~18)

| Constant | Value | Purpose |
|----------|-------|---------|
| `FIZZADMIT_VERSION` | `"1.0.0"` | FizzAdmit subsystem version |
| `ADMISSION_API_VERSION` | `"admission.fizzkube.io/v1"` | AdmissionReview API version |
| `CRD_API_VERSION` | `"apiextensions.fizzkube.io/v1"` | CRD API version |
| `DEFAULT_ADMISSION_TIMEOUT` | `10.0` | Default admission controller timeout in seconds |
| `MAX_WEBHOOK_TIMEOUT` | `30.0` | Maximum webhook timeout in seconds |
| `DEFAULT_FAILURE_POLICY` | `"FAIL"` | Default failure policy for unavailable controllers |
| `BUILTIN_PRIORITY_RANGE` | `(0, 999)` | Priority range reserved for built-in controllers |
| `WEBHOOK_PRIORITY_START` | `1000` | Minimum priority for webhook controllers |
| `DEFAULT_FINALIZER_TIMEOUT` | `300.0` | Seconds before a finalizer is considered stuck |
| `DEFAULT_RECONCILE_MAX_CONCURRENT` | `1` | Default max concurrent reconciliations |
| `DEFAULT_RECONCILE_BACKOFF_BASE` | `5.0` | Base reconcile retry backoff in seconds |
| `DEFAULT_RECONCILE_BACKOFF_CAP` | `300.0` | Maximum reconcile backoff (5 minutes) |
| `DEFAULT_RECONCILE_BACKOFF_MULTIPLIER` | `2.0` | Backoff multiplier per reconcile retry |
| `DEFAULT_MAX_WORK_QUEUE_DEPTH` | `1000` | Maximum work queue depth before backpressure |
| `DEFAULT_LEADER_ELECTION_LEASE` | `15.0` | Leader election lease duration in seconds |
| `DEFAULT_LEADER_ELECTION_RENEW` | `10.0` | Leader election renew interval in seconds |
| `DEFAULT_LEADER_ELECTION_RETRY` | `2.0` | Leader election retry interval in seconds |
| `MIDDLEWARE_PRIORITY` | `119` | Middleware pipeline priority for FizzAdmit |

---

## 4. Enums (~8)

### AdmissionPhase
```python
class AdmissionPhase(Enum):
    """Phase in the admission chain."""
    MUTATING = "MUTATING"
    VALIDATING = "VALIDATING"
```

### AdmissionOperation
```python
class AdmissionOperation(Enum):
    """API operations that admission controllers intercept."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CONNECT = "CONNECT"
```

### FailurePolicy
```python
class FailurePolicy(Enum):
    """Behavior when an admission controller is unavailable or errors."""
    FAIL = "FAIL"
    IGNORE = "IGNORE"
```

### SideEffects
```python
class SideEffects(Enum):
    """Whether an admission controller has side effects."""
    NONE = "NONE"
    SOME = "SOME"
```

### SecurityProfile
```python
class SecurityProfile(Enum):
    """Pod security admission profiles."""
    PRIVILEGED = "PRIVILEGED"
    BASELINE = "BASELINE"
    RESTRICTED = "RESTRICTED"
```

### EnforcementMode
```python
class EnforcementMode(Enum):
    """Pod security enforcement mode per namespace."""
    ENFORCE = "enforce"
    WARN = "warn"
    AUDIT = "audit"
```

### ImagePolicyAction
```python
class ImagePolicyAction(Enum):
    """Image policy rule action."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_SIGNATURE = "REQUIRE_SIGNATURE"
```

### PropagationPolicy
```python
class PropagationPolicy(Enum):
    """Cascading deletion policy."""
    BACKGROUND = "BACKGROUND"
    FOREGROUND = "FOREGROUND"
    ORPHAN = "ORPHAN"
```

---

## 5. Data Classes

### 5.1 Admission Review Protocol (~250 lines)

#### GroupVersionKind
```python
@dataclass
class GroupVersionKind:
    """Identifies a resource type by group, version, and kind."""
    group: str
    version: str
    kind: str
```

#### GroupVersionResource
```python
@dataclass
class GroupVersionResource:
    """Identifies a resource type by group, version, and resource name."""
    group: str
    version: str
    resource: str
```

#### UserInfo
```python
@dataclass
class UserInfo:
    """Authenticated user making the API request."""
    username: str
    groups: List[str] = field(default_factory=list)
    uid: str = ""
```

#### AdmissionStatus
```python
@dataclass
class AdmissionStatus:
    """Rejection status returned by a denying admission controller."""
    code: int                  # HTTP status code (e.g., 403)
    message: str               # Human-readable denial reason
    reason: str                # Machine-readable denial reason
```

#### JsonPatchOperation
```python
@dataclass
class JsonPatchOperation:
    """RFC 6902 JSON Patch operation."""
    op: str                    # add, remove, replace, move, copy
    path: str                  # JSON Pointer to target field
    value: Any = None          # Value for add/replace
    from_path: str = ""        # Source path for move/copy
```

Implement `apply_patches(obj: dict, patches: List[JsonPatchOperation]) -> dict` utility that:
- Applies each patch operation in order on a deep copy
- Supports `add`, `remove`, `replace`, `move`, `copy` per RFC 6902
- Handles `/` path separator, `~0` (`~`) and `~1` (`/`) escape sequences
- Raises `AdmissionChainError` on invalid paths or operations

#### AdmissionRequest
```python
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
```

#### AdmissionResponse
```python
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
```

#### AdmissionReview
```python
@dataclass
class AdmissionReview:
    """Envelope for admission request/response exchange."""
    api_version: str = ADMISSION_API_VERSION
    kind: str = "AdmissionReview"
    request: Optional[AdmissionRequest] = None
    response: Optional[AdmissionResponse] = None
```

### 5.2 Admission Controller Registration (~50 lines)

#### AdmissionControllerRegistration
```python
@dataclass
class AdmissionControllerRegistration:
    """Registration metadata for an admission controller."""
    name: str
    phase: AdmissionPhase
    priority: int
    controller: "AdmissionController"
    operations: List[AdmissionOperation] = field(default_factory=lambda: [AdmissionOperation.CREATE, AdmissionOperation.UPDATE])
    resources: List[GroupVersionResource] = field(default_factory=list)  # empty = all
    namespaces: List[str] = field(default_factory=lambda: ["*"])
    failure_policy: FailurePolicy = FailurePolicy.FAIL
    side_effects: SideEffects = SideEffects.NONE
    timeout_seconds: float = DEFAULT_ADMISSION_TIMEOUT
```

### 5.3 Webhook Configuration (~80 lines)

#### RuleWithOperations
```python
@dataclass
class RuleWithOperations:
    """Specifies which operations and resources trigger a webhook."""
    operations: List[AdmissionOperation]
    api_groups: List[str]
    api_versions: List[str]
    resources: List[str]
    scope: str = "*"  # CLUSTER, NAMESPACED, or *
```

#### WebhookClientConfig
```python
@dataclass
class WebhookClientConfig:
    """How to reach a webhook endpoint."""
    url: str = ""
    service_name: str = ""
    service_namespace: str = ""
    service_port: int = 443
    service_path: str = ""
    ca_bundle: str = ""
```

#### MutatingWebhookConfiguration
```python
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
```

#### ValidatingWebhookConfiguration
```python
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
```

### 5.4 Resource Quota & LimitRange Models (~80 lines)

#### ResourceQuota
```python
@dataclass
class ResourceQuota:
    """Namespace-level resource quota definition and tracking."""
    namespace: str
    hard: Dict[str, float] = field(default_factory=dict)
    # Keys: requests.cpu, requests.memory, limits.cpu, limits.memory,
    #        pods, services, configmaps, secrets, persistentvolumeclaims
    used: Dict[str, float] = field(default_factory=dict)
    scope_selector: Dict[str, str] = field(default_factory=dict)
```

#### LimitRange
```python
@dataclass
class LimitRange:
    """Namespace-level resource defaults and bounds."""
    namespace: str
    type: str = "Container"  # Container, Pod, or PersistentVolumeClaim
    default: Dict[str, str] = field(default_factory=dict)
    default_request: Dict[str, str] = field(default_factory=dict)
    min: Dict[str, str] = field(default_factory=dict)
    max: Dict[str, str] = field(default_factory=dict)
    max_limit_request_ratio: Dict[str, float] = field(default_factory=dict)
```

#### ImagePolicyRule
```python
@dataclass
class ImagePolicyRule:
    """Image policy enforcement rule."""
    name: str
    pattern: str
    action: ImagePolicyAction
    message: str = ""
```

### 5.5 CRD Model (~100 lines)

#### CRDNames
```python
@dataclass
class CRDNames:
    """Naming conventions for a custom resource type."""
    kind: str
    singular: str
    plural: str
    short_names: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
```

#### PrinterColumn
```python
@dataclass
class PrinterColumn:
    """Additional column for tabular CRD output."""
    name: str
    type: str          # string, integer, date
    json_path: str
    description: str = ""
    priority: int = 0
```

#### SubResources
```python
@dataclass
class SubResources:
    """Subresource configuration for a CRD version."""
    status: bool = False
    scale: Optional[Dict[str, str]] = None
    # scale keys: spec_replicas_path, status_replicas_path, label_selector_path
```

#### CRDVersion
```python
@dataclass
class CRDVersion:
    """A version definition within a CRD."""
    name: str
    served: bool = True
    storage: bool = False
    schema: Optional[Dict[str, Any]] = None  # OpenAPI v3 schema
    additional_printer_columns: List[PrinterColumn] = field(default_factory=list)
    subresources: Optional[SubResources] = None
```

#### CustomResourceDefinition
```python
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
```

### 5.6 Owner Reference & Finalizer (~40 lines)

#### OwnerReference
```python
@dataclass
class OwnerReference:
    """Parent-child relationship metadata."""
    api_version: str
    kind: str
    name: str
    uid: str
    controller: bool = False
    block_owner_deletion: bool = False
```

### 5.7 Operator SDK (~60 lines)

#### ReconcileRequest
```python
@dataclass
class ReconcileRequest:
    """Identifies the resource to reconcile."""
    name: str
    namespace: str = ""
```

#### ReconcileResult
```python
@dataclass
class ReconcileResult:
    """Result of a reconciliation cycle."""
    requeue: bool = False
    requeue_after: float = 0.0
    error: Optional[str] = None
```

#### OperatorMetrics
```python
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
```

### 5.8 Audit Record (~30 lines)

#### AdmissionAuditRecord
```python
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
```

---

## 6. Core Classes

### 6.1 AdmissionController (Abstract Base) (~30 lines)

```python
class AdmissionController:
    """Abstract base for admission controllers."""

    def admit(self, request: AdmissionRequest) -> AdmissionResponse:
        """Evaluate the request and return an admission decision."""
        raise NotImplementedError
```

### 6.2 AdmissionChain (~300 lines)

Central pipeline orchestrating all admission controllers.

**State:**
- `_mutating: List[AdmissionControllerRegistration]` -- sorted by priority
- `_validating: List[AdmissionControllerRegistration]` -- sorted by priority
- `_audit_log: List[AdmissionAuditRecord]` -- bounded deque (max 10,000)
- `_lock: threading.Lock`

**Methods:**
- `register(registration: AdmissionControllerRegistration)` -- Insert into correct phase list, maintaining priority sort order. Validates name uniqueness, priority range (built-in vs webhook).
- `unregister(name: str)` -- Remove a controller by name.
- `admit(request: AdmissionRequest) -> AdmissionResponse` -- Execute the full admission pipeline:
  1. Filter controllers matching the request's operation, resource, and namespace.
  2. Execute all matching MUTATING controllers in priority order. Each receives a deep copy of the current object. If a controller returns patches, apply them via `apply_patches()`. If a controller returns `allowed=False`, short-circuit and return denial. Skip controllers with `side_effects=SOME` if `dry_run=True`.
  3. Re-encode the mutated object.
  4. Execute all matching VALIDATING controllers in priority order on the mutated object. Controllers at the same priority level execute concurrently (thread pool). If any returns `allowed=False`, reject.
  5. Aggregate all patches, audit annotations, and warnings from all controllers.
  6. Record `AdmissionAuditRecord` for each controller invocation.
  7. Return final `AdmissionResponse`.
- `_matches(registration, request) -> bool` -- Check if a controller's operations, resources, and namespaces match the request.
- `_handle_controller_error(registration, error, request) -> AdmissionResponse` -- Apply failure policy: FAIL returns denial, IGNORE returns allow with warning.
- `get_chain_summary() -> List[Dict]` -- Return the ordered chain for `--fizzadmit-admission-chain` CLI output.
- `get_audit_log(limit: int = 100) -> List[AdmissionAuditRecord]` -- Return recent audit records.

### 6.3 ResourceQuotaAdmissionController (~300 lines)

Mutating + validating, priority 100.

**State:**
- `_quotas: Dict[str, ResourceQuota]` -- namespace -> quota
- `_lock: threading.Lock`

**Methods:**
- `set_quota(namespace: str, quota: ResourceQuota)` -- Configure or update a namespace quota.
- `get_quota(namespace: str) -> Optional[ResourceQuota]` -- Retrieve quota and usage.
- `admit(request: AdmissionRequest) -> AdmissionResponse`:
  - On CREATE: sum resources of the new pod's containers (parse `resources.requests` from each container spec). Add to namespace used counts. If any metric exceeds hard limit, deny with `ResourceQuotaExhausted` status. Increment pod/service/configmap/secret counts as appropriate. Also check scope selectors against pod labels.
  - On DELETE: decrement used counts by the deleted resource's contribution.
  - On UPDATE: compute delta between old and new resource requests, apply delta.
  - Update the ResourceQuota status sub-resource with current used values.
  - All mutations are idempotent: if the request is later denied by a downstream controller, the quota accounting is rolled back.
- `_parse_resource_value(value: str) -> float` -- Parse Kubernetes resource strings (`"500m"` = 0.5 CPU, `"256FB"` = 256 FizzBytes, `"1Gi"` = 1073741824).
- `_check_scope_selector(quota: ResourceQuota, labels: Dict[str, str]) -> bool` -- Check if the resource matches the quota's scope selector.
- `render_quota_status(namespace: str) -> str` -- Render quota utilization table for CLI.

### 6.4 LimitRangerAdmissionController (~250 lines)

Mutating, priority 200.

**State:**
- `_ranges: Dict[str, LimitRange]` -- namespace -> limit range

**Methods:**
- `set_limit_range(namespace: str, limit_range: LimitRange)` -- Configure namespace limit range.
- `get_limit_range(namespace: str) -> Optional[LimitRange]` -- Retrieve limit range.
- `admit(request: AdmissionRequest) -> AdmissionResponse`:
  - Only acts on CREATE/UPDATE for pods.
  - For each container in `spec.containers`:
    - If `resources.requests` is missing, generate JSON Patch to add `default_request` values.
    - If `resources.limits` is missing, generate JSON Patch to add `default` values.
  - After mutation, validate that all resource values fall within `[min, max]`.
  - Validate that limit/request ratios do not exceed `max_limit_request_ratio`.
  - Return patches for defaults; return denial for range violations with detailed message identifying the container name, resource, and violated constraint.
- `render_limit_range(namespace: str) -> str` -- Render limit range config for CLI.

### 6.5 PodSecurityAdmissionController (~250 lines)

Validating, priority 300.

**State:**
- `_namespace_profiles: Dict[str, Tuple[SecurityProfile, EnforcementMode, str]]` -- namespace -> (profile, mode, version)

**Methods:**
- `set_namespace_policy(namespace: str, profile: SecurityProfile, mode: EnforcementMode, version: str = "v1.0")` -- Configure namespace security policy.
- `admit(request: AdmissionRequest) -> AdmissionResponse`:
  - Only acts on CREATE/UPDATE for pods.
  - Look up the namespace's profile and enforcement mode.
  - If profile is PRIVILEGED, allow unconditionally.
  - For BASELINE, check each container for: `privileged: true`, `hostNetwork/hostPID/hostIPC: true`, dangerous capabilities (`ALL`, `SYS_ADMIN`, `NET_ADMIN`, `SYS_PTRACE`), `allowPrivilegeEscalation: true`, writable `/proc` mounts.
  - For RESTRICTED, all BASELINE checks plus: `runAsNonRoot` must be true, `readOnlyRootFilesystem` must be true, only `NET_BIND_SERVICE` capability allowed (all others dropped), seccomp profile must be `RuntimeDefault` or `Localhost`, only `configMap`, `secret`, `emptyDir`, `persistentVolumeClaim` volume types allowed.
  - Enforcement: `ENFORCE` = deny, `WARN` = allow with warnings, `AUDIT` = allow with audit annotation.
- `_check_baseline_violations(pod_spec: Dict) -> List[str]` -- Return list of BASELINE violation descriptions.
- `_check_restricted_violations(pod_spec: Dict) -> List[str]` -- Return list of RESTRICTED violation descriptions (superset of BASELINE).
- `render_security_profile(namespace: str) -> str` -- Render namespace security profile for CLI.

### 6.6 ImagePolicyAdmissionController (~200 lines)

Validating, priority 400.

**State:**
- `_rules: List[ImagePolicyRule]` -- ordered policy rules
- `_image_digests: Dict[str, str]` -- tag -> digest cache (simulated resolution)
- `_signed_images: Set[str]` -- set of signed image digests

**Methods:**
- `add_rule(rule: ImagePolicyRule)` -- Add a policy rule.
- `set_default_rules()` -- Register the four default rules: deny `:latest`, deny non-`fizzbuzz-registry.local` registries, deny images failing vulnerability scan, require signatures in production namespaces.
- `register_signed_image(digest: str)` -- Mark an image digest as signed.
- `register_image_digest(tag: str, digest: str)` -- Cache tag-to-digest resolution.
- `admit(request: AdmissionRequest) -> AdmissionResponse`:
  - Extract all container image references from the pod spec.
  - For each image, resolve tag to digest (if cached).
  - Evaluate each image against policy rules in order. First matching rule determines the action.
  - ALLOW: continue. DENY: reject with rule message. REQUIRE_SIGNATURE: check signed set; deny if unsigned.
  - Return denial with all violation details if any image fails.
- `render_image_policy() -> str` -- Render policy rules table for CLI.

### 6.7 WebhookDispatcher (~250 lines)

Routes AdmissionReview requests to registered webhook endpoints.

**State:**
- `_mutating_webhooks: List[MutatingWebhookConfiguration]`
- `_validating_webhooks: List[ValidatingWebhookConfiguration]`
- `_webhook_handlers: Dict[str, Callable]` -- name -> handler function (simulated endpoint)

**Methods:**
- `register_mutating_webhook(config: MutatingWebhookConfiguration)` -- Register a mutating webhook.
- `register_validating_webhook(config: ValidatingWebhookConfiguration)` -- Register a validating webhook.
- `register_webhook_handler(name: str, handler: Callable)` -- Register a simulated webhook handler function.
- `dispatch_mutating(request: AdmissionRequest) -> List[AdmissionResponse]` -- Dispatch to all matching mutating webhooks. For each: construct AdmissionReview, call handler with timeout enforcement, apply failure policy on error. Support `reinvocation_policy: IF_NEEDED` by re-invoking if subsequent webhooks mutate the object.
- `dispatch_validating(request: AdmissionRequest) -> List[AdmissionResponse]` -- Dispatch to all matching validating webhooks. All must allow for the request to pass.
- `_matches_webhook(config, request) -> bool` -- Check rules, namespace_selector, and object_selector.
- `_call_webhook(name: str, review: AdmissionReview, timeout: float) -> AdmissionResponse` -- Call the registered handler with timeout enforcement.
- `get_webhook_summary() -> List[Dict]` -- Return webhook list for `--fizzadmit-webhooks` CLI.

### 6.8 OpenAPISchemaValidator (~150 lines)

Validates custom resource instances against OpenAPI v3 schemas.

**Methods:**
- `validate(instance: Dict[str, Any], schema: Dict[str, Any]) -> List[str]` -- Return list of validation errors. Supports: `type` (object, array, string, integer, number, boolean), `properties`, `required`, `enum`, `minimum`, `maximum`, `pattern`, `format`, `default`, `minLength`, `maxLength`, `minItems`, `maxItems`, nested objects, arrays with `items`.
- `apply_defaults(instance: Dict, schema: Dict) -> Dict` -- Apply default values from schema to missing fields.
- `prune_unknown_fields(instance: Dict, schema: Dict) -> Dict` -- Remove fields not defined in schema (structural schema enforcement).
- `is_structural(schema: Dict) -> bool` -- Verify that every field has an explicit type (structural schema requirement).

### 6.9 CRDRegistry (~350 lines)

Manages CustomResourceDefinition lifecycle.

**State:**
- `_crds: Dict[str, CustomResourceDefinition]` -- name -> CRD
- `_instances: Dict[str, Dict[str, Dict[str, Any]]]` -- `{group/plural: {ns/name: resource}}`
- `_validators: Dict[str, Callable]` -- CRD name -> compiled validator
- `_watchers: Dict[str, List[Callable]]` -- resource type -> list of watch callbacks
- `_lock: threading.Lock`

**Methods:**
- `register_crd(crd: CustomResourceDefinition)` -- Validate CRD spec (structural schema, exactly one storage version, valid DNS names), compile schema into validator, store in registry. Emit `FIZZADMIT_CRD_REGISTERED` event.
- `unregister_crd(name: str)` -- Delete CRD and garbage-collect all instances. Instances with finalizers get a grace period. Emit `FIZZADMIT_CRD_DELETED` event.
- `get_crd(name: str) -> Optional[CustomResourceDefinition]` -- Look up a CRD.
- `list_crds() -> List[CustomResourceDefinition]` -- List all registered CRDs.
- `create_instance(crd_name: str, namespace: str, instance: Dict) -> Dict` -- Validate instance against CRD schema, apply defaults, prune unknown fields, assign UID and generation, store. Runs through admission chain if registered.
- `get_instance(crd_name: str, namespace: str, name: str) -> Optional[Dict]` -- Retrieve an instance.
- `list_instances(crd_name: str, namespace: str = "") -> List[Dict]` -- List instances, optionally filtered by namespace.
- `update_instance(crd_name: str, namespace: str, name: str, new_spec: Dict) -> Dict` -- Validate updated spec, increment generation, store.
- `update_instance_status(crd_name: str, namespace: str, name: str, status: Dict) -> Dict` -- Update status sub-resource without triggering main-resource admission.
- `delete_instance(crd_name: str, namespace: str, name: str, propagation: PropagationPolicy = PropagationPolicy.BACKGROUND)` -- Set deletion_timestamp, trigger finalizer processing. Actual removal occurs when all finalizers are cleared.
- `add_watch(resource_type: str, callback: Callable)` -- Register a watch callback for a resource type.
- `_notify_watchers(resource_type: str, event_type: str, obj: Dict)` -- Notify all registered watchers of a change.
- `render_crd_list() -> str` -- Table of CRDs for `--fizzadmit-crd-list`.
- `render_crd_describe(name: str) -> str` -- Detailed CRD view for `--fizzadmit-crd-describe`.
- `render_crd_instances(kind: str, namespace: str = "") -> str` -- Instance table using printer columns.

### 6.10 FinalizerManager (~200 lines)

**State:**
- `_finalizer_handlers: Dict[str, Callable]` -- finalizer string -> handler function
- `_stuck_timeout: float`

**Methods:**
- `register_finalizer(name: str, handler: Callable)` -- Register a finalizer handler.
- `add_finalizer(resource: Dict, finalizer_name: str) -> Dict` -- Add finalizer to resource's `metadata.finalizers` list.
- `process_finalizers(resource: Dict) -> Tuple[Dict, bool]` -- For a resource with `deletion_timestamp` set:
  - Iterate through `metadata.finalizers`.
  - For each, call the registered handler. If handler succeeds, remove the finalizer.
  - If handler raises an error, leave finalizer in place (will retry on next reconcile).
  - Return updated resource and whether all finalizers have been cleared.
- `check_stuck(resource: Dict) -> bool` -- Check if deletion_timestamp is older than `_stuck_timeout`. If so, emit alert and return True.
- `force_remove_all(resource: Dict) -> Dict` -- Emergency: remove all finalizers regardless of handler state. For `--fizzadmit-force-finalize`.

### 6.11 GarbageCollector (~200 lines)

Processes owner reference relationships for cascading deletion.

**State:**
- `_crd_registry: CRDRegistry` -- reference to CRD registry for resource access

**Methods:**
- `add_owner_reference(child: Dict, owner_ref: OwnerReference) -> Dict` -- Add owner reference to child's `metadata.owner_references`.
- `delete_with_propagation(resource: Dict, policy: PropagationPolicy)`:
  - BACKGROUND: delete parent immediately, queue async deletion of all children with matching owner references.
  - FOREGROUND: add `foreground-deletion` finalizer to parent. Delete all children first. Remove finalizer when children are gone. Parent is garbage collected only after all children.
  - ORPHAN: delete parent, remove owner references from children (they become independent).
- `find_children(parent_uid: str) -> List[Dict]` -- Scan all instances for owner references matching the parent UID.
- `_is_orphaned(resource: Dict) -> bool` -- Check if all owners in owner_references have been deleted.
- `collect_orphans()` -- Scan for resources whose owners no longer exist. Resources with all owners deleted are garbage collected. Resources with some owners remaining survive.

### 6.12 Reconciler (Abstract Base) (~20 lines)

```python
class Reconciler:
    """Interface for operator reconciliation logic."""

    def reconcile(self, request: ReconcileRequest) -> ReconcileResult:
        """Reconcile the desired and actual state of a custom resource."""
        raise NotImplementedError
```

### 6.13 ReconcileLoop (~200 lines)

**State:**
- `_reconciler: Reconciler`
- `_resource_type: str` -- primary resource GVK string
- `_work_queue: deque` -- rate-limited deduplicated work queue
- `_queued_keys: Set[str]` -- keys currently in the queue (for deduplication)
- `_metrics: OperatorMetrics`
- `_max_concurrent: int`
- `_backoff_base: float`
- `_backoff_cap: float`
- `_backoff_multiplier: float`
- `_error_counts: Dict[str, int]` -- key -> consecutive error count (for backoff)
- `_is_leader: bool`
- `_running: bool`

**Methods:**
- `enqueue(key: str)` -- Add a resource key (namespace/name) to the work queue if not already present. Deduplicate by key.
- `run()` -- Main loop: dequeue items, call `_process_item()`, handle results.
- `_process_item(key: str)`:
  1. Record start time.
  2. Call `reconciler.reconcile(ReconcileRequest(name, namespace))`.
  3. On success with `requeue=False`: clear error count, record success metric.
  4. On success with `requeue=True`: re-enqueue after `requeue_after` seconds.
  5. On error: increment error count, compute backoff (`base * multiplier^error_count`, capped at cap), re-enqueue after backoff.
  6. Record latency sample.
- `_compute_backoff(error_count: int) -> float` -- Exponential backoff with jitter.
- `acquire_leadership() -> bool` -- Simulated leader election using compare-and-swap on an etcd key. Only the leader processes the work queue.
- `renew_leadership() -> bool` -- Renew the leader lease.
- `get_metrics() -> OperatorMetrics` -- Return current metrics.

### 6.14 OperatorBuilder (~150 lines)

Fluent builder for constructing operator controllers.

**Methods:**
- `__init__(name: str)` -- Operator name.
- `for_resource(group: str, version: str, kind: str) -> OperatorBuilder` -- Set the primary resource.
- `with_reconciler(reconciler: Reconciler) -> OperatorBuilder` -- Set the reconciler.
- `with_finalizer(name: str) -> OperatorBuilder` -- Register a finalizer.
- `owns(group: str, version: str, kind: str) -> OperatorBuilder` -- Declare owned child resource type.
- `watches(group: str, version: str, kind: str, handler: Callable) -> OperatorBuilder` -- Watch additional resource type.
- `with_max_concurrent_reconciles(n: int) -> OperatorBuilder` -- Set max concurrency.
- `with_rate_limiter(max_delay: float, base_delay: float) -> OperatorBuilder` -- Configure rate limiter.
- `build() -> Operator` -- Validate configuration (reconciler required, primary resource required), construct ReconcileLoop, register watches with CRDRegistry, return Operator.

### 6.15 Operator (~80 lines)

Runtime wrapper around the reconcile loop and operator configuration.

**State:**
- `_name: str`
- `_loop: ReconcileLoop`
- `_primary_gvk: GroupVersionKind`
- `_owned_gvks: List[GroupVersionKind]`
- `_watched_gvks: List[Tuple[GroupVersionKind, Callable]]`
- `_finalizer_name: Optional[str]`
- `_crd_registry: CRDRegistry`

**Methods:**
- `start()` -- Start the reconcile loop. Register watch callbacks with CRD registry.
- `stop()` -- Stop the reconcile loop.
- `handle_event(event_type: str, obj: Dict)` -- Called by CRD registry watchers. Map the event to a reconcile request key and enqueue.
- `get_status() -> Dict` -- Return operator status (name, primary resource, queue depth, error count, is_leader, metrics).

### 6.16 Built-in CRD: FizzBuzzClusterOperator (~80 lines)

Implements `Reconciler` for the `FizzBuzzCluster` CRD.

- `reconcile(request)`:
  1. Fetch `FizzBuzzCluster` instance from CRD registry.
  2. If deleted (has deletion_timestamp) and finalizer present: clean up owned resources (simulated Deployment, Service, ConfigMap deletion), remove finalizer, return.
  3. Ensure finalizer is added.
  4. Read `spec.replicas`, `spec.rules`, `spec.cache_enabled`, etc.
  5. Reconcile owned Deployment: check if it exists with correct replica count and configuration. Create or update as needed, with owner reference.
  6. Reconcile owned Service: create if missing, with owner reference.
  7. Reconcile owned ConfigMap: create or update with rule configuration.
  8. Update status: `phase` (`Provisioning`, `Running`, `Degraded`, `Failed`), `ready_replicas`, `current_rules`, `conditions`, `observed_generation`.
  9. Return `ReconcileResult(requeue=False)` if all good, `requeue=True` with delay if still provisioning.

### 6.17 Built-in CRD: FizzBuzzBackupOperator (~70 lines)

Implements `Reconciler` for the `FizzBuzzBackup` CRD.

- `reconcile(request)`:
  1. Fetch `FizzBuzzBackup` instance.
  2. If deleted and finalizer present: wait for in-progress backups, optionally retain or delete completed backups based on `spec.delete_backups_on_remove`, remove finalizer.
  3. Ensure finalizer is added.
  4. Parse `spec.schedule` (cron expression), compute next scheduled backup time.
  5. If backup is due: create backup job (simulated), update `status.last_backup_time`, `status.last_backup_status`.
  6. Enforce retention: delete backups beyond `spec.retention_count`.
  7. Update status: `status.backup_count`, `status.next_scheduled_backup`.

### 6.18 FizzAdmitMiddleware (~150 lines)

Integrates with the FizzBuzz evaluation middleware pipeline.

**Implements:** `IMiddleware`

**State:**
- `_admission_chain: AdmissionChain`
- `_crd_registry: CRDRegistry`
- `_webhook_dispatcher: WebhookDispatcher`
- `_finalizer_manager: FinalizerManager`
- `_garbage_collector: GarbageCollector`
- `_operators: Dict[str, Operator]`
- `_cluster_operator: FizzBuzzClusterOperator`
- `_backup_operator: FizzBuzzBackupOperator`

**Methods:**
- `process(context: ProcessingContext, next_handler: Callable) -> FizzBuzzResult`:
  - Construct a lightweight AdmissionRequest from the evaluation context (namespace, resource requests, evaluation parameters).
  - Run through admission chain.
  - If denied, annotate context with denial reason and raise or skip based on configuration.
  - If admitted, annotate context with admission metadata (admitted_by, admission_latency_ms, mutations_applied).
  - Call `next_handler(context)`.
- `render_admission_chain() -> str` -- Table of registered controllers.
- `render_quota_status(namespace: str) -> str` -- Delegate to ResourceQuotaAdmissionController.
- `render_limit_range(namespace: str) -> str` -- Delegate to LimitRangerAdmissionController.
- `render_security_profile(namespace: str) -> str` -- Delegate to PodSecurityAdmissionController.
- `render_image_policy() -> str` -- Delegate to ImagePolicyAdmissionController.
- `render_webhooks() -> str` -- Delegate to WebhookDispatcher.
- `render_crd_list() -> str` -- Delegate to CRDRegistry.
- `render_crd_describe(name: str) -> str` -- Delegate to CRDRegistry.
- `render_crd_instances(kind: str, namespace: str) -> str` -- Delegate to CRDRegistry.
- `render_operators() -> str` -- Table of operator status.
- `render_dashboard() -> str` -- Summary dashboard with admission chain, active CRDs, operator health.

---

## 7. Factory Function (~60 lines)

```python
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
) -> Tuple["FizzAdmitSubsystem", "FizzAdmitMiddleware"]:
```

1. Create `CRDRegistry`, `FinalizerManager`, `GarbageCollector(crd_registry)`.
2. Create `AdmissionChain`.
3. Create and register built-in controllers: `ResourceQuotaAdmissionController` (priority 100), `LimitRangerAdmissionController` (priority 200), `PodSecurityAdmissionController` (priority 300), `ImagePolicyAdmissionController` (priority 400).
4. If `enable_default_image_rules`, call `image_policy.set_default_rules()`.
5. Create `WebhookDispatcher`.
6. Register built-in CRDs: `FizzBuzzCluster`, `FizzBuzzBackup`.
7. Create operators: `FizzBuzzClusterOperator`, `FizzBuzzBackupOperator`. Build via `OperatorBuilder`.
8. Create `FizzAdmitMiddleware` with all components.
9. Return subsystem handle and middleware.

---

## 8. File Inventory

### File 1: `enterprise_fizzbuzz/domain/exceptions/fizzadmit.py` (~120 lines)

Exception hierarchy with EFP-ADM prefix:

| Class | Code | Trigger |
|-------|------|---------|
| `FizzAdmitError` | `EFP-ADM00` | Base exception for all FizzAdmit errors |
| `AdmissionChainError` | `EFP-ADM01` | Admission chain configuration or execution failure |
| `AdmissionControllerError` | `EFP-ADM02` | Generic admission controller internal error |
| `AdmissionDeniedError` | `EFP-ADM03` | Request explicitly denied by an admission controller |
| `AdmissionTimeoutError` | `EFP-ADM04` | Admission controller exceeded its timeout |
| `AdmissionWebhookError` | `EFP-ADM05` | Webhook dispatch or response parsing failure |
| `AdmissionWebhookUnreachableError` | `EFP-ADM06` | Webhook endpoint is unreachable |
| `ResourceQuotaExhaustedError` | `EFP-ADM07` | Namespace resource quota would be exceeded |
| `LimitRangeViolationError` | `EFP-ADM08` | Resource value outside configured LimitRange bounds |
| `PodSecurityViolationError` | `EFP-ADM09` | Pod spec violates the namespace security profile |
| `ImagePolicyViolationError` | `EFP-ADM10` | Container image fails organizational policy check |
| `CRDError` | `EFP-ADM11` | Base CRD framework error |
| `CRDSchemaValidationError` | `EFP-ADM12` | CRD schema is not structural or contains invalid types |
| `CRDRegistrationError` | `EFP-ADM13` | CRD registration failed (duplicate name, invalid spec) |
| `CRDInstanceValidationError` | `EFP-ADM14` | Custom resource instance fails schema validation |
| `CRDNotFoundError` | `EFP-ADM15` | Referenced CRD does not exist in the registry |
| `CRDDeletionError` | `EFP-ADM16` | CRD deletion failed (stuck instances, finalizer issues) |
| `OperatorError` | `EFP-ADM17` | Base operator framework error |
| `OperatorReconcileError` | `EFP-ADM18` | Reconciliation loop encountered an unrecoverable error |
| `OperatorLeaderElectionError` | `EFP-ADM19` | Leader election failed or lease expired |
| `OperatorWorkQueueError` | `EFP-ADM20` | Work queue overflow or corruption |
| `FinalizerError` | `EFP-ADM21` | Base finalizer error |
| `FinalizerStuckError` | `EFP-ADM22` | Finalizer not removed within timeout |
| `FinalizerRemovalError` | `EFP-ADM23` | Finalizer handler failed during removal |
| `OwnerReferenceError` | `EFP-ADM24` | Invalid or cyclic owner reference |
| `GarbageCollectionError` | `EFP-ADM25` | Garbage collection of orphaned resources failed |
| `CascadingDeletionError` | `EFP-ADM26` | Cascading deletion failed during child cleanup |
| `FizzAdmitMiddlewareError` | `EFP-ADM27` | Middleware pipeline integration error |

Pattern: each class inherits from `FizzAdmitError` (which inherits `FizzBuzzError` via `._base`). Constructor takes a `message: str` plus relevant context fields (namespace, controller_name, resource_name, etc.) and passes `error_code` and `context` dict to super.

### File 2: `enterprise_fizzbuzz/domain/events/fizzadmit.py` (~40 lines)

Register event types via `EventType.register()`:

```python
"""FizzAdmit admission controller and CRD operator events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("FIZZADMIT_REQUEST_ADMITTED")
EventType.register("FIZZADMIT_REQUEST_DENIED")
EventType.register("FIZZADMIT_REQUEST_MUTATED")
EventType.register("FIZZADMIT_CHAIN_EXECUTED")
EventType.register("FIZZADMIT_QUOTA_EXCEEDED")
EventType.register("FIZZADMIT_QUOTA_UPDATED")
EventType.register("FIZZADMIT_LIMIT_DEFAULTED")
EventType.register("FIZZADMIT_LIMIT_VIOLATED")
EventType.register("FIZZADMIT_SECURITY_VIOLATION")
EventType.register("FIZZADMIT_IMAGE_DENIED")
EventType.register("FIZZADMIT_WEBHOOK_CALLED")
EventType.register("FIZZADMIT_WEBHOOK_FAILED")
EventType.register("FIZZADMIT_CRD_REGISTERED")
EventType.register("FIZZADMIT_CRD_DELETED")
EventType.register("FIZZADMIT_CRD_INSTANCE_CREATED")
EventType.register("FIZZADMIT_CRD_INSTANCE_UPDATED")
EventType.register("FIZZADMIT_CRD_INSTANCE_DELETED")
EventType.register("FIZZADMIT_OPERATOR_RECONCILE")
EventType.register("FIZZADMIT_OPERATOR_RECONCILE_ERROR")
EventType.register("FIZZADMIT_OPERATOR_LEADER_ELECTED")
EventType.register("FIZZADMIT_FINALIZER_ADDED")
EventType.register("FIZZADMIT_FINALIZER_REMOVED")
EventType.register("FIZZADMIT_FINALIZER_STUCK")
EventType.register("FIZZADMIT_GC_COLLECTED")
EventType.register("FIZZADMIT_CASCADE_DELETE")
EventType.register("FIZZADMIT_EVALUATION_PROCESSED")
EventType.register("FIZZADMIT_DASHBOARD_RENDERED")
```

### File 3: `enterprise_fizzbuzz/infrastructure/config/mixins/fizzadmit.py` (~80 lines)

```python
"""FizzAdmit configuration properties."""

from __future__ import annotations

from typing import Any


class FizzadmitConfigMixin:
    """Configuration properties for the FizzAdmit subsystem."""

    @property
    def fizzadmit_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzadmit", {}).get("enabled", False)

    @property
    def fizzadmit_admission_timeout(self) -> float:
        self._ensure_loaded()
        return float(self._raw_config.get("fizzadmit", {}).get("admission_timeout", 10.0))

    @property
    def fizzadmit_finalizer_timeout(self) -> float:
        self._ensure_loaded()
        return float(self._raw_config.get("fizzadmit", {}).get("finalizer_timeout", 300.0))

    @property
    def fizzadmit_reconcile_max_concurrent(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzadmit", {}).get("reconcile_max_concurrent", 1))

    @property
    def fizzadmit_reconcile_backoff_base(self) -> float:
        self._ensure_loaded()
        return float(self._raw_config.get("fizzadmit", {}).get("reconcile_backoff_base", 5.0))

    @property
    def fizzadmit_reconcile_backoff_cap(self) -> float:
        self._ensure_loaded()
        return float(self._raw_config.get("fizzadmit", {}).get("reconcile_backoff_cap", 300.0))

    @property
    def fizzadmit_leader_election_lease(self) -> float:
        self._ensure_loaded()
        return float(self._raw_config.get("fizzadmit", {}).get("leader_election_lease", 15.0))

    @property
    def fizzadmit_enable_default_image_rules(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzadmit", {}).get("enable_default_image_rules", True)

    @property
    def fizzadmit_default_security_profile(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzadmit", {}).get("default_security_profile", "BASELINE")

    @property
    def fizzadmit_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzadmit", {}).get("dashboard_width", 80))

    @property
    def fizzadmit_max_audit_records(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzadmit", {}).get("max_audit_records", 10000))

    @property
    def fizzadmit_work_queue_max_depth(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzadmit", {}).get("work_queue_max_depth", 1000))
```

### File 4: `enterprise_fizzbuzz/infrastructure/features/fizzadmit_feature.py` (~70 lines)

```python
"""Feature descriptor for FizzAdmit admission controllers and CRD operator framework."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzAdmitFeature(FeatureDescriptor):
    name = "fizzadmit"
    description = "Kubernetes-style admission controllers and CRD operator framework for FizzKube"
    middleware_priority = 119
    cli_flags = [
        ("--fizzadmit", {"action": "store_true", "default": False,
                         "help": "Enable FizzAdmit: admission controllers and CRD operator framework"}),
        ("--fizzadmit-admission-chain", {"action": "store_true", "default": False,
                                          "help": "Display the registered admission chain"}),
        ("--fizzadmit-dry-run", {"type": str, "default": None, "metavar": "RESOURCE_YAML",
                                  "help": "Submit a resource through admission in dry-run mode"}),
        ("--fizzadmit-quota-status", {"type": str, "default": None, "metavar": "NAMESPACE",
                                       "help": "Display resource quota utilization for a namespace"}),
        ("--fizzadmit-limit-range", {"type": str, "default": None, "metavar": "NAMESPACE",
                                      "help": "Display LimitRange configuration for a namespace"}),
        ("--fizzadmit-security-profile", {"type": str, "default": None, "metavar": "NAMESPACE",
                                           "help": "Display pod security profile for a namespace"}),
        ("--fizzadmit-image-policy", {"action": "store_true", "default": False,
                                       "help": "Display configured image policy rules"}),
        ("--fizzadmit-webhooks", {"action": "store_true", "default": False,
                                   "help": "List registered webhook configurations"}),
        ("--fizzadmit-crd-list", {"action": "store_true", "default": False,
                                   "help": "List all registered CustomResourceDefinitions"}),
        ("--fizzadmit-crd-describe", {"type": str, "default": None, "metavar": "NAME",
                                       "help": "Describe a CRD schema, versions, and subresources"}),
        ("--fizzadmit-crd-instances", {"type": str, "default": None, "metavar": "KIND",
                                        "help": "List instances of a custom resource type"}),
        ("--fizzadmit-operators", {"action": "store_true", "default": False,
                                    "help": "List operators with reconciliation status"}),
        ("--fizzadmit-force-finalize", {"type": str, "default": None, "metavar": "RESOURCE",
                                         "help": "Forcibly remove all finalizers from a stuck resource"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzadmit", False),
            getattr(args, "fizzadmit_admission_chain", False),
            getattr(args, "fizzadmit_crd_list", False),
            getattr(args, "fizzadmit_operators", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzadmit import (
            FizzAdmitMiddleware,
            create_fizzadmit_subsystem,
        )

        subsystem, middleware = create_fizzadmit_subsystem(
            admission_timeout=config.fizzadmit_admission_timeout,
            finalizer_timeout=config.fizzadmit_finalizer_timeout,
            reconcile_max_concurrent=config.fizzadmit_reconcile_max_concurrent,
            reconcile_backoff_base=config.fizzadmit_reconcile_backoff_base,
            reconcile_backoff_cap=config.fizzadmit_reconcile_backoff_cap,
            leader_election_lease=config.fizzadmit_leader_election_lease,
            enable_default_image_rules=config.fizzadmit_enable_default_image_rules,
            default_security_profile=config.fizzadmit_default_security_profile,
            dashboard_width=config.fizzadmit_dashboard_width,
        )

        return subsystem, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzadmit_admission_chain", False):
            parts.append(middleware.render_admission_chain())
        if getattr(args, "fizzadmit_image_policy", False):
            parts.append(middleware.render_image_policy())
        if getattr(args, "fizzadmit_webhooks", False):
            parts.append(middleware.render_webhooks())
        if getattr(args, "fizzadmit_crd_list", False):
            parts.append(middleware.render_crd_list())
        if getattr(args, "fizzadmit_crd_describe", None) is not None:
            parts.append(middleware.render_crd_describe(args.fizzadmit_crd_describe))
        if getattr(args, "fizzadmit_operators", False):
            parts.append(middleware.render_operators())
        if getattr(args, "fizzadmit", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
```

### File 5: `config.d/fizzadmit.yaml`

```yaml

fizzadmit:
  enabled: false
  admission_timeout: 10.0
  finalizer_timeout: 300.0
  reconcile_max_concurrent: 1
  reconcile_backoff_base: 5.0
  reconcile_backoff_cap: 300.0
  leader_election_lease: 15.0
  enable_default_image_rules: true
  default_security_profile: "BASELINE"
  dashboard_width: 80
  max_audit_records: 10000
  work_queue_max_depth: 1000
```

### File 6: `fizzadmit.py` (root-level re-export stub)

```python
"""Backward-compatible re-export stub for fizzadmit."""
from enterprise_fizzbuzz.infrastructure.fizzadmit import *  # noqa: F401,F403
```

### File 7: `enterprise_fizzbuzz/infrastructure/fizzadmit.py` (~3,500 lines)

The main implementation file containing all classes described in sections 2-7.

### File 8: `tests/test_fizzadmit.py` (~500 lines, ~100 tests)

Test structure organized by subsystem:

---

## 9. Test Plan

### 9.1 AdmissionReview Protocol (~15 tests)

- `test_admission_request_defaults` -- verify default field values
- `test_admission_response_allowed` -- construct allowed response, verify fields
- `test_admission_response_denied` -- construct denied response with status
- `test_admission_review_envelope` -- request/response correlation by UID
- `test_json_patch_add` -- apply add operation
- `test_json_patch_remove` -- apply remove operation
- `test_json_patch_replace` -- apply replace operation
- `test_json_patch_move` -- apply move operation
- `test_json_patch_copy` -- apply copy operation
- `test_json_patch_nested_path` -- apply patch to deeply nested path
- `test_json_patch_escape_sequences` -- `~0` and `~1` in paths
- `test_json_patch_invalid_path` -- raises AdmissionChainError
- `test_json_patch_multiple_operations` -- sequential application
- `test_user_info_serialization` -- UserInfo fields populated from context
- `test_dry_run_flag_propagation` -- dry_run flag reaches controllers

### 9.2 Admission Chain (~20 tests)

- `test_empty_chain_admits_all` -- no controllers registered, request admitted
- `test_mutating_before_validating` -- mutating controllers execute before validating
- `test_priority_ordering_within_phase` -- lower priority executes first
- `test_mutating_patches_applied` -- patches from mutating controller applied to object
- `test_mutating_sequential_patches` -- each controller sees result of prior mutations
- `test_validating_reject_stops_chain` -- single validation rejection denies request
- `test_mutating_reject_short_circuits` -- mutating controller denial stops chain
- `test_operation_filtering` -- controller only invoked for matching operations
- `test_resource_filtering` -- controller only invoked for matching resource types
- `test_namespace_filtering` -- controller only invoked for matching namespaces
- `test_wildcard_matching` -- `*` matches all operations/resources/namespaces
- `test_dry_run_skips_side_effects` -- controllers with `side_effects=SOME` skipped in dry run
- `test_failure_policy_fail` -- controller error with FAIL policy denies request
- `test_failure_policy_ignore` -- controller error with IGNORE policy admits with warning
- `test_audit_log_recorded` -- every admission decision creates an audit record
- `test_audit_log_bounded` -- audit log does not exceed maximum size
- `test_chain_summary_rendering` -- `--fizzadmit-admission-chain` output format
- `test_register_duplicate_name` -- raises error on duplicate controller name
- `test_unregister_controller` -- controller removed from chain
- `test_concurrent_validating_same_priority` -- same-priority validators execute concurrently

### 9.3 ResourceQuota Controller (~15 tests)

- `test_quota_admits_within_limits` -- pod within quota is admitted
- `test_quota_denies_exceeding_cpu` -- pod exceeding CPU quota is denied
- `test_quota_denies_exceeding_memory` -- pod exceeding memory quota is denied
- `test_quota_denies_exceeding_pod_count` -- namespace at max pod count
- `test_quota_tracks_used_on_create` -- used counters increment on CREATE
- `test_quota_tracks_used_on_delete` -- used counters decrement on DELETE
- `test_quota_delta_on_update` -- UPDATE computes delta between old and new
- `test_quota_scope_selector` -- quota with label selector only applies to matching pods
- `test_quota_status_rendering` -- `--fizzadmit-quota-status` output format
- `test_parse_cpu_millicores` -- `"500m"` = 0.5
- `test_parse_memory_fizzbytes` -- `"256FB"` = 256
- `test_parse_memory_gi` -- `"1Gi"` = 1073741824
- `test_quota_rollback_on_downstream_denial` -- quota accounting rolled back if later controller denies
- `test_multiple_quotas_per_namespace` -- not supported, latest wins
- `test_quota_zero_used_initial` -- fresh quota has all used = 0

### 9.4 LimitRanger Controller (~12 tests)

- `test_default_limits_injected` -- missing limits filled from LimitRange defaults
- `test_default_requests_injected` -- missing requests filled from LimitRange defaults
- `test_both_defaults_injected` -- both missing limits and requests filled
- `test_existing_values_preserved` -- specified values not overwritten
- `test_min_violation_denied` -- value below min is rejected
- `test_max_violation_denied` -- value above max is rejected
- `test_ratio_violation_denied` -- limit/request ratio exceeds max
- `test_multiple_containers` -- defaults injected into each container
- `test_patch_format` -- JSON patches generated correctly
- `test_limit_range_rendering` -- `--fizzadmit-limit-range` output format
- `test_no_limit_range_passthrough` -- namespace without LimitRange passes through
- `test_limit_range_per_pod_type` -- different ranges for Container vs Pod types

### 9.5 PodSecurityAdmission Controller (~12 tests)

- `test_privileged_profile_allows_all` -- PRIVILEGED profile admits everything
- `test_baseline_denies_privileged_container` -- `privileged: true` denied
- `test_baseline_denies_host_network` -- `hostNetwork: true` denied
- `test_baseline_denies_dangerous_caps` -- `SYS_ADMIN` capability denied
- `test_baseline_allows_safe_pod` -- conforming pod admitted
- `test_restricted_denies_root` -- `runAsNonRoot: false` denied
- `test_restricted_denies_writable_rootfs` -- `readOnlyRootFilesystem: false` denied
- `test_restricted_denies_extra_caps` -- capabilities other than NET_BIND_SERVICE denied
- `test_restricted_requires_seccomp` -- missing seccomp profile denied
- `test_warn_mode_admits_with_warning` -- WARN mode allows but adds warnings
- `test_audit_mode_admits_silently` -- AUDIT mode allows with audit annotation only
- `test_security_profile_rendering` -- `--fizzadmit-security-profile` output format

### 9.6 ImagePolicy Controller (~8 tests)

- `test_deny_latest_tag` -- `:latest` tag denied
- `test_deny_untrusted_registry` -- non-`fizzbuzz-registry.local` denied
- `test_allow_trusted_image` -- trusted registry with version tag allowed
- `test_require_signature_signed` -- signed image in production namespace allowed
- `test_require_signature_unsigned` -- unsigned image in production namespace denied
- `test_tag_to_digest_resolution` -- tags resolved to digests before evaluation
- `test_custom_policy_rules` -- user-defined rules evaluated in order
- `test_image_policy_rendering` -- `--fizzadmit-image-policy` output format

### 9.7 Webhook Dispatch (~8 tests)

- `test_mutating_webhook_called` -- matching webhook receives AdmissionReview
- `test_mutating_webhook_patches_applied` -- webhook patches applied to object
- `test_validating_webhook_denies` -- validating webhook rejection propagated
- `test_webhook_timeout_fail_policy` -- timeout with FAIL policy denies
- `test_webhook_timeout_ignore_policy` -- timeout with IGNORE policy admits
- `test_reinvocation_policy` -- IF_NEEDED reinvokes webhook after subsequent mutations
- `test_namespace_selector_filtering` -- webhook only called for matching namespaces
- `test_webhook_summary_rendering` -- `--fizzadmit-webhooks` output format

### 9.8 CRD Framework (~15 tests)

- `test_register_crd` -- CRD registered and retrievable
- `test_register_crd_invalid_schema` -- non-structural schema rejected
- `test_register_crd_multiple_storage_versions` -- rejected: only one storage version allowed
- `test_create_instance_validates_schema` -- instance validated against CRD schema
- `test_create_instance_applies_defaults` -- default values from schema applied
- `test_create_instance_prunes_unknown` -- unknown fields removed
- `test_update_instance_increments_generation` -- generation counter incremented
- `test_update_status_subresource` -- status update does not trigger main admission
- `test_delete_crd_cascades_instances` -- deleting CRD removes all instances
- `test_list_instances_by_namespace` -- filtered listing works
- `test_crd_list_rendering` -- `--fizzadmit-crd-list` output format
- `test_crd_describe_rendering` -- `--fizzadmit-crd-describe` output format
- `test_crd_instances_rendering` -- `--fizzadmit-crd-instances` output format
- `test_crd_watch_notifications` -- watchers notified on create/update/delete
- `test_openapi_validation_types` -- all JSON Schema types validated correctly

### 9.9 Operator Framework (~10 tests)

- `test_operator_builder_basic` -- build an operator with required fields
- `test_operator_builder_validates` -- missing reconciler raises error
- `test_reconcile_success` -- successful reconciliation clears error count
- `test_reconcile_requeue` -- requeue result re-enqueues after delay
- `test_reconcile_error_backoff` -- error triggers exponential backoff
- `test_work_queue_deduplication` -- same key only queued once
- `test_leader_election` -- only leader processes work queue
- `test_operator_metrics` -- reconciliation metrics collected
- `test_cluster_operator_reconcile` -- FizzBuzzCluster creates owned resources
- `test_backup_operator_reconcile` -- FizzBuzzBackup manages backup lifecycle

### 9.10 Finalizers & GC (~10 tests)

- `test_add_finalizer` -- finalizer added to resource metadata
- `test_process_finalizer_success` -- handler called, finalizer removed
- `test_process_finalizer_error` -- handler error leaves finalizer in place
- `test_stuck_finalizer_detection` -- timeout triggers stuck alert
- `test_force_remove_finalizers` -- emergency removal clears all finalizers
- `test_background_cascading_deletion` -- parent deleted, children cleaned async
- `test_foreground_cascading_deletion` -- children deleted before parent
- `test_orphan_deletion_policy` -- children survive with owner refs removed
- `test_multi_owner_survival` -- resource with multiple owners survives partial deletion
- `test_orphan_collection` -- orphaned resources (all owners deleted) are collected

---

## 10. Integration Points

### 10.1 Domain Exceptions Registration

Add to `enterprise_fizzbuzz/domain/exceptions/__init__.py`:
```python
from enterprise_fizzbuzz.domain.exceptions.fizzadmit import *  # noqa: F401,F403
```

Add all exception class names to `__all__`.

### 10.2 Domain Events Registration

Add to `enterprise_fizzbuzz/domain/events/__init__.py`:
```python
import enterprise_fizzbuzz.domain.events.fizzadmit  # noqa: F401
```

Note: the events file uses `fizzadmit` not `_fizzadmit` per brainstorm spec. If the convention requires underscore prefix, use `_fizzadmit.py` instead and adjust the import.

### 10.3 Config Mixin Registration

Add `FizzadmitConfigMixin` to the `ConfigurationManager` class's mixin inheritance chain in `enterprise_fizzbuzz/infrastructure/config/configuration_manager.py`.

### 10.4 Feature Registration

The feature descriptor auto-registers via the `_registry.py` discovery mechanism. No manual registration needed beyond creating the file.

---

## 11. Line Budget

| Component | Lines |
|-----------|-------|
| Module docstring | 50 |
| Imports | 40 |
| Constants | 25 |
| Enums (8) | 60 |
| Data classes (§5.1-5.8) | 350 |
| AdmissionController base | 15 |
| AdmissionChain | 300 |
| ResourceQuotaAdmissionController | 300 |
| LimitRangerAdmissionController | 250 |
| PodSecurityAdmissionController | 250 |
| ImagePolicyAdmissionController | 200 |
| WebhookDispatcher | 250 |
| OpenAPISchemaValidator | 150 |
| CRDRegistry | 350 |
| FinalizerManager | 200 |
| GarbageCollector | 200 |
| Reconciler base | 15 |
| ReconcileLoop | 200 |
| OperatorBuilder | 120 |
| Operator | 80 |
| FizzBuzzClusterOperator | 80 |
| FizzBuzzBackupOperator | 70 |
| FizzAdmitMiddleware | 150 |
| Factory function | 60 |
| JSON Patch utility (apply_patches) | 80 |
| **Total (fizzadmit.py)** | **~3,495** |
| Exceptions (fizzadmit.py) | ~120 |
| Events (fizzadmit.py) | ~40 |
| Config mixin | ~80 |
| Feature descriptor | ~70 |
| config.d YAML | ~15 |
| Root stub | ~3 |
| Tests | ~500 |
| **Grand Total** | **~4,323** |
