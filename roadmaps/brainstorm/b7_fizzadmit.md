# FizzAdmit -- Kubernetes-Style Admission Controllers & CRD Operator Framework

**Date:** 2026-03-24
**Status:** PROPOSED
**Estimated Scale:** ~3,500 lines of implementation + ~500 lines of tests

> *"FizzKube accepts every resource request unconditionally. A pod requesting 10 terabytes of FizzBytes memory is admitted. A deployment targeting a namespace that does not exist is admitted. A container image referencing a registry that has never existed is admitted. A pod spec with a negative replica count is admitted. The API server receives the request, stores it in etcd, and lets the scheduler discover -- at scheduling time -- that the request is impossible to fulfill. This is the equivalent of an airport that issues every passenger a boarding pass and then lets the gate agent figure out that the plane doesn't exist. Kubernetes solved this in 2015 with admission controllers: a chain of validation and mutation plugins that intercept every API request before it reaches the persistent store. Nine years later, FizzKube has no admission chain. Every request is admitted. Every invalid resource reaches etcd. Every impossible pod reaches the scheduler. FizzAdmit builds the checkpoint between the API server and etcd."*

---

## The Problem

The Enterprise FizzBuzz Platform's container orchestrator, FizzKube, implements a faithful Kubernetes-style control plane: an API server processes resource requests, etcd stores cluster state, the scheduler assigns pods to nodes, the controller manager reconciles desired and actual state, and the kubelet (upgraded in FizzKubeV2) manages pod lifecycle through CRI. FizzKube handles the core resource types -- Pods, Deployments, ReplicaSets, Services, Namespaces, ConfigMaps, and HPAs. It does not handle custom resource types. It does not validate resource requests before persisting them. It does not mutate resource requests to inject defaults or enforce policies. It does not support extending the API server with new resource types defined at runtime. It does not implement the operator pattern for managing complex application lifecycle through custom controllers.

In Kubernetes, admission controllers are the gatekeepers between the API server and persistent storage. Every CREATE, UPDATE, and DELETE request passes through a chain of admission controllers before the resource is written to etcd. Admission controllers come in two varieties: **validating** controllers that accept or reject a request based on policy (e.g., ResourceQuota enforces that the namespace's aggregate resource usage does not exceed the quota; PodSecurityAdmission enforces that pod specs conform to security standards; ImagePolicyWebhook enforces that container images meet organizational requirements), and **mutating** controllers that modify the request before validation (e.g., LimitRanger injects default resource requests and limits into pod specs that omit them; ServiceAccount injects the default service account token; AlwaysPullImages overrides the image pull policy to Always for security). Admission controllers execute in a defined order: mutating controllers run first (to set defaults and enforce policies that modify the request), then validating controllers run (to reject requests that violate invariants on the final, mutated request).

Beyond admission control, Kubernetes provides a CustomResourceDefinition (CRD) mechanism that allows operators to define new resource types with their own schemas, validation rules, and lifecycle semantics. CRDs transform Kubernetes from a container orchestrator into an extensible platform API. Combined with custom controllers (the operator pattern), CRDs enable declarative management of complex application stacks: a database operator watches DatabaseCluster CRDs and reconciles the actual database topology to match the declared specification; a certificate operator watches Certificate CRDs and provisions TLS certificates from Let's Encrypt; a backup operator watches BackupSchedule CRDs and executes periodic backups. The operator pattern -- watch for changes, detect drift between desired and actual state, reconcile the drift, update status -- is the fundamental extension mechanism of the Kubernetes ecosystem.

FizzKube has none of this. Its API server accepts all requests without validation. It supports a fixed set of built-in resource types with no mechanism for extension. It has no admission chain, no webhooks, no CRDs, no operator framework, no finalizers, and no owner references. The platform's 116 infrastructure modules cannot define custom resources. Complex subsystem lifecycle cannot be managed declaratively. Resource requests cannot be validated against policy before they consume cluster capacity. FizzKube is a competent orchestrator for the resource types it knows about; it cannot learn new ones.

## The Vision

A comprehensive admission control and custom resource framework for FizzKube, implementing the complete Kubernetes admission pipeline and CRD operator pattern. The admission chain intercepts every API server request, routing it through an ordered sequence of mutating admission controllers (which modify the request to inject defaults, enforce policies, and normalize fields) followed by validating admission controllers (which accept or reject the final request against cluster invariants and organizational policies). Both built-in and webhook-based admission controllers are supported: built-in controllers implement core cluster policies (resource quota enforcement, default resource limit injection, pod security admission, image policy enforcement), while webhook controllers allow external subsystems to participate in the admission chain through a standard AdmissionReview request/response protocol. The CRD framework enables runtime definition of custom resource types with OpenAPI v3 schema validation, versioning, subresources (status and scale), and printer columns. An operator SDK provides a builder-pattern framework for writing custom controllers that watch CRDs, detect drift between desired and actual state, reconcile the drift, and update resource status -- with finalizer support for cleanup on deletion and owner reference tracking for cascading deletion.

## Key Components

- **`fizzadmit.py`** (~3,500 lines): FizzAdmit Admission Controllers & CRD Operator Framework

### Admission Review Protocol

The foundation of the admission chain is a standardized request/response protocol that every admission controller -- built-in or webhook -- uses to communicate with the API server.

- **`AdmissionReview`**: the envelope for admission requests and responses. Contains:
  - `api_version`: protocol version (e.g., `"admission.fizzkube.io/v1"`)
  - `kind`: always `"AdmissionReview"`
  - `request`: an `AdmissionRequest` containing the details of the API operation being admitted
  - `response`: an `AdmissionResponse` populated by the admission controller after evaluation
- **`AdmissionRequest`**: the incoming request to be evaluated:
  - `uid`: unique identifier for this admission request, used to correlate request and response
  - `kind`: the `GroupVersionKind` of the resource being created/updated/deleted (e.g., `{"group": "", "version": "v1", "kind": "Pod"}`)
  - `resource`: the `GroupVersionResource` (e.g., `{"group": "", "version": "v1", "resource": "pods"}`)
  - `sub_resource`: the sub-resource being accessed, if any (e.g., `"status"`, `"scale"`)
  - `name`: the name of the resource being operated on (empty for CREATE)
  - `namespace`: the namespace of the resource
  - `operation`: one of `CREATE`, `UPDATE`, `DELETE`, `CONNECT`
  - `user_info`: the authenticated user making the request (username, groups, UID), sourced from FizzCap's capability tokens or RBAC session
  - `object`: the resource object from the incoming request (the new version for CREATE/UPDATE, None for DELETE)
  - `old_object`: the existing resource object (None for CREATE, the current version for UPDATE/DELETE)
  - `options`: operation-specific options (e.g., `CreateOptions`, `UpdateOptions`)
  - `dry_run`: boolean indicating whether this is a dry-run request (admission must not have side effects)
  - `request_timestamp`: ISO 8601 timestamp when the API server received the request
- **`AdmissionResponse`**: the admission controller's decision:
  - `uid`: must match the request UID
  - `allowed`: boolean -- `True` to admit the request, `False` to reject
  - `status`: on rejection, an `AdmissionStatus` containing `code` (HTTP status code, e.g., 403), `message` (human-readable denial reason), and `reason` (machine-readable denial reason, e.g., `"ResourceQuotaExceeded"`, `"SecurityPolicyViolation"`)
  - `patch`: for mutating controllers, a list of JSON Patch operations (RFC 6902) to apply to the request object. Each patch operation specifies `op` (`add`, `remove`, `replace`, `move`, `copy`), `path` (JSON Pointer to the target field), and `value` (for `add`/`replace`)
  - `patch_type`: the patch format, always `"JSONPatch"` in the current implementation
  - `audit_annotations`: key-value pairs to include in the audit log entry for this request, enabling admission controllers to record their reasoning
  - `warnings`: list of human-readable warning messages to return to the client (e.g., `"Deprecated API version v1beta1 -- migrate to v1"`)

### Admission Chain

The admission chain orchestrates the execution of admission controllers in a defined priority order, separating mutating and validating phases.

- **`AdmissionChain`**: the central admission pipeline that every API server request passes through:
  - **Registration**: admission controllers register with the chain, specifying:
    - `name`: unique controller name (e.g., `"resource-quota"`, `"limit-ranger"`, `"pod-security"`)
    - `phase`: `MUTATING` or `VALIDATING`
    - `priority`: integer priority within the phase (lower numbers execute first). Built-in controllers use priorities 0-999; webhook controllers use priorities 1000+
    - `operations`: which operations to intercept (`CREATE`, `UPDATE`, `DELETE`, `CONNECT`, or `*` for all)
    - `resources`: which resource types to intercept (e.g., `[{"group": "", "resource": "pods"}]`, or `*` for all)
    - `namespaces`: which namespaces to intercept (list of namespace names, `*` for all, or empty to match only cluster-scoped resources)
    - `failure_policy`: `FAIL` (reject the request if the controller is unavailable or errors) or `IGNORE` (skip the controller if it is unavailable or errors)
    - `side_effects`: `NONE` (the controller has no side effects) or `SOME` (the controller may have side effects -- dry-run requests skip controllers with side effects)
    - `timeout_seconds`: maximum time the controller has to respond (default: 10 seconds)
  - **Execution order**:
    1. All `MUTATING` controllers execute in priority order. Each controller receives the current request object and may return JSON Patch mutations. Mutations are applied sequentially -- each mutating controller sees the result of all prior mutations
    2. After all mutating controllers have executed, the API server re-encodes the mutated object
    3. All `VALIDATING` controllers execute in priority order on the mutated object. Each controller returns `allowed: True` or `allowed: False`. If any validating controller rejects the request, the entire request is rejected with the denying controller's status message. Validating controllers execute in parallel when they have no ordering dependency (same priority level)
  - **Short-circuit behavior**: if a mutating controller rejects the request (returns `allowed: False`), the chain stops immediately without executing subsequent controllers. This allows mutating controllers to enforce hard policy constraints
  - **Dry-run mode**: when `dry_run` is True, the chain skips controllers with `side_effects: SOME` and ensures no state mutations occur. All other controllers execute normally, enabling API clients to preview whether a request would be admitted without actually persisting it
  - **Audit logging**: every admission decision is recorded in the audit log with the controller name, decision (allow/deny), latency, any patches applied, and any warnings generated. The audit log integrates with FizzOTel for distributed tracing of admission decisions

### Built-in Admission Controllers

FizzAdmit ships with four built-in admission controllers that enforce core cluster policies. These controllers are automatically registered with the admission chain at startup.

- **`ResourceQuotaAdmissionController`** (mutating + validating, priority 100):
  - **Purpose**: enforces namespace-level resource quotas. When a pod is created, the controller sums the resource requests (CPU, memory) of all existing pods in the namespace and adds the new pod's requests. If the total would exceed the namespace's quota, the request is rejected with a `ResourceQuotaExceeded` status
  - **Quota model**: each namespace has a `ResourceQuota` object stored in etcd containing `hard` limits: `requests.cpu` (total CPU requests across all pods), `requests.memory` (total memory requests), `limits.cpu` (total CPU limits), `limits.memory` (total memory limits), `pods` (maximum number of pods), `services` (maximum number of services), `configmaps` (maximum number of ConfigMaps), `secrets` (maximum number of secrets), `persistentvolumeclaims` (maximum number of PVCs)
  - **Quota tracking**: the controller maintains a `used` counter for each quota metric, updated on every CREATE and DELETE. On UPDATE, the delta between old and new resource requests is applied. The `used` counters are persisted in etcd alongside the quota definition
  - **Scope selectors**: quotas can target specific resource subsets using label selectors (e.g., a quota that applies only to pods with label `priority: high`), enabling tiered resource allocation within a namespace
  - **Status**: the controller updates the ResourceQuota's `status` sub-resource with current `used` values after every admission decision, enabling operators to query quota utilization via `--fizzadmit-quota-status`

- **`LimitRangerAdmissionController`** (mutating, priority 200):
  - **Purpose**: injects default resource requests and limits into pod containers that omit them, and validates that specified resources fall within configured ranges. Without LimitRanger, a pod can be created with no resource limits, consuming unbounded resources from the node's cgroup budget
  - **LimitRange model**: each namespace has a `LimitRange` object containing per-type defaults and bounds:
    - `type`: `Container`, `Pod`, or `PersistentVolumeClaim`
    - `default`: default resource limits applied when the container spec omits limits (e.g., `{"cpu": "500m", "memory": "256FB"}`)
    - `default_request`: default resource requests applied when the container spec omits requests (e.g., `{"cpu": "100m", "memory": "128FB"}`)
    - `min`: minimum allowed resource values (requests below min are rejected)
    - `max`: maximum allowed resource values (limits above max are rejected)
    - `max_limit_request_ratio`: maximum ratio between limit and request for each resource (prevents overcommitting, e.g., a ratio of 2 means a container's CPU limit cannot be more than 2x its request)
  - **Mutation behavior**: for each container in the pod spec, the controller checks whether `resources.requests` and `resources.limits` are specified. Missing requests are filled from `default_request`. Missing limits are filled from `default`. The mutations are returned as JSON Patch operations
  - **Validation behavior**: after mutation, the controller validates that all resource values fall within `[min, max]` and that the limit/request ratio does not exceed `max_limit_request_ratio`. Violations result in rejection with a detailed message identifying the offending container, resource, and constraint

- **`PodSecurityAdmissionController`** (validating, priority 300):
  - **Purpose**: enforces pod security standards by validating pod specs against a configurable security profile. Prevents the creation of pods with known-insecure configurations: privileged containers, host namespace sharing, dangerous capabilities, unconfined seccomp/AppArmor profiles, and writable root filesystems
  - **Security profiles**: three built-in profiles modeled on the Kubernetes Pod Security Standards:
    - `PRIVILEGED`: unrestricted -- no validation. Intended for system-level infrastructure pods (e.g., CNI plugins, cgroup managers)
    - `BASELINE`: prevents known privilege escalation vectors. Rejects pods with: `privileged: true`, `hostNetwork: true`, `hostPID: true`, `hostIPC: true`, dangerous capabilities (`ALL`, `SYS_ADMIN`, `NET_ADMIN`, `SYS_PTRACE`), `allowPrivilegeEscalation: true` (unless the image entrypoint requires setuid), writable `/proc` mounts
    - `RESTRICTED`: maximally restrictive. Includes all BASELINE restrictions plus: requires `runAsNonRoot: true`, requires `readOnlyRootFilesystem: true`, drops ALL capabilities (only allows `NET_BIND_SERVICE`), requires seccomp profile `RuntimeDefault` or `Localhost`, disallows volume types other than `configMap`, `secret`, `emptyDir`, and `persistentVolumeClaim`
  - **Namespace-level enforcement**: each namespace is labeled with a profile and enforcement mode:
    - `enforce`: violations cause request rejection
    - `warn`: violations generate warnings in the AdmissionResponse but the request is admitted
    - `audit`: violations are recorded in the audit log but neither rejected nor warned
  - **Version pinning**: profiles are pinned to a version (e.g., `restricted:v1.0`) so that policy updates do not retroactively invalidate existing pods

- **`ImagePolicyAdmissionController`** (validating, priority 400):
  - **Purpose**: enforces organizational policies on container images referenced in pod specs. Prevents the use of unauthorized registries, untagged images, images with known vulnerabilities, and images lacking required signatures
  - **Policy rules**: a configurable list of image policy rules, each specifying:
    - `name`: rule identifier
    - `pattern`: image reference pattern to match (glob syntax, e.g., `"fizzbuzz-registry.local/*"`, `"*:latest"`)
    - `action`: `ALLOW`, `DENY`, or `REQUIRE_SIGNATURE`
    - `message`: human-readable explanation of the policy (included in rejection messages)
  - **Default policy rules**:
    - DENY images with tag `:latest` (require immutable semantic version or digest references)
    - DENY images from registries other than `fizzbuzz-registry.local` (enforce supply chain provenance)
    - DENY images that failed vulnerability scanning in FizzImage's catalog scanner (enforce security baseline)
    - REQUIRE_SIGNATURE for images deployed to production namespaces (enforce provenance verification via FizzRegistry's image signing)
  - **Image resolution**: the controller resolves image tags to digests via FizzRegistry's manifest API, ensuring that the exact image content (not just the tag) is evaluated against policy. This prevents tag mutation attacks where a `:v1.0.0` tag is re-pointed to a different image after policy evaluation

### Webhook Admission Controllers

External subsystems participate in the admission chain through webhook-based controllers that receive AdmissionReview requests and return AdmissionResponse decisions.

- **`MutatingWebhookConfiguration`**: defines a mutating admission webhook:
  - `name`: webhook name (e.g., `"sidecar-injector.fizzkube.io"`)
  - `client_config`: how to reach the webhook endpoint:
    - `url`: direct URL (e.g., `"https://sidecar-injector.fizzbuzz-system:443/mutate"`)
    - `service`: alternatively, a reference to a FizzKube Service (`name`, `namespace`, `port`, `path`) resolved through the service registry
    - `ca_bundle`: CA certificate for TLS verification
  - `rules`: list of `RuleWithOperations` specifying which resources and operations trigger the webhook:
    - `operations`: list of `CREATE`, `UPDATE`, `DELETE`, `CONNECT`
    - `api_groups`: list of API groups (e.g., `[""]` for core, `["apps"]` for deployments)
    - `api_versions`: list of API versions (e.g., `["v1"]`)
    - `resources`: list of resource types (e.g., `["pods"]`)
    - `scope`: `CLUSTER`, `NAMESPACED`, or `*`
  - `namespace_selector`: label selector to match namespaces where the webhook applies
  - `object_selector`: label selector to match objects the webhook applies to
  - `failure_policy`: `FAIL` or `IGNORE` (behavior when webhook is unreachable)
  - `match_policy`: `EXACT` (only match the exact resource specified) or `EQUIVALENT` (match equivalent resources -- e.g., a rule matching `deployments` also matches `deployments/scale`)
  - `side_effects`: `NONE` or `SOME`
  - `timeout_seconds`: webhook call timeout (default: 10, max: 30)
  - `reinvocation_policy`: `NEVER` (call the webhook once) or `IF_NEEDED` (re-invoke the webhook if subsequent mutating webhooks modify the object, to ensure this webhook's mutations are preserved)

- **`ValidatingWebhookConfiguration`**: defines a validating admission webhook. Same fields as `MutatingWebhookConfiguration` except: no `reinvocation_policy` (validating webhooks always see the final mutated object), and no JSON Patch in responses (validating webhooks can only allow or deny).

- **`WebhookDispatcher`**: routes AdmissionReview requests to registered webhook endpoints:
  - Matches the incoming request against all registered webhook configurations using `rules`, `namespace_selector`, and `object_selector`
  - Constructs an `AdmissionReview` request with the current (possibly mutated) object
  - Dispatches the review to the webhook endpoint via the service mesh or direct URL
  - Applies `timeout_seconds` enforcement -- if the webhook does not respond within the timeout, applies the `failure_policy`
  - For mutating webhooks, applies returned JSON Patch operations to the request object
  - For validating webhooks, aggregates allow/deny decisions (all must allow for the request to pass)
  - Records webhook call latency, outcome, and any errors in the admission audit log

### CustomResourceDefinition (CRD) Framework

The CRD framework enables runtime extension of FizzKube's API with user-defined resource types.

- **`CustomResourceDefinition`**: the meta-resource that defines a new resource type:
  - `api_version`: `"apiextensions.fizzkube.io/v1"`
  - `kind`: `"CustomResourceDefinition"`
  - `metadata`: standard resource metadata (`name`, `labels`, `annotations`)
  - `spec`:
    - `group`: the API group for the custom resource (e.g., `"fizzbuzz.io"`, `"databases.fizzkube.io"`)
    - `names`: naming conventions:
      - `kind`: the CamelCase kind name (e.g., `"FizzBuzzCluster"`)
      - `singular`: singular form (e.g., `"fizzbuzzcluster"`)
      - `plural`: plural form used in API paths (e.g., `"fizzbuzzclusters"`)
      - `short_names`: list of abbreviated aliases (e.g., `["fbc"]`)
      - `categories`: grouping categories (e.g., `["all"]` to include in `kubectl get all`)
    - `scope`: `NAMESPACED` or `CLUSTER` (whether instances are namespace-scoped or cluster-wide)
    - `versions`: list of version definitions, each containing:
      - `name`: version string (e.g., `"v1"`, `"v1beta1"`)
      - `served`: boolean -- whether this version is served by the API server
      - `storage`: boolean -- whether this version is the storage version (exactly one version must be the storage version)
      - `schema`: OpenAPI v3 schema definition for the custom resource:
        - `open_api_v3_schema`: a JSON Schema object with `type`, `properties`, `required`, `enum`, `minimum`, `maximum`, `pattern`, `format`, `description`, `default`, and nested object/array schemas. The schema validates every CREATE and UPDATE request for this custom resource type
        - **Structural schema requirement**: the schema must be "structural" -- every field must have an explicit `type`, no `additionalProperties: true` at the root, no arbitrary JSON blobs. This enables server-side validation, defaulting, and pruning of unknown fields
      - `additional_printer_columns`: columns displayed in tabular output (e.g., `--fizzadmit-crd-list`):
        - `name`: column header
        - `type`: data type (`string`, `integer`, `date`)
        - `json_path`: JSON path expression extracting the value from the custom resource (e.g., `".spec.replicas"`, `".status.phase"`)
        - `description`: column description
        - `priority`: display priority (0 = always shown, higher = shown with verbose output)
      - `subresources`:
        - `status`: if present, enables the `/status` sub-resource endpoint. Status is isolated from the spec -- updates to status do not trigger admission webhooks that watch the main resource, and vice versa. This prevents reconciliation loops where a controller's status update triggers its own watch
        - `scale`: if present, enables the `/scale` sub-resource for HPA integration:
          - `spec_replicas_path`: JSON path to the replica count in the spec (e.g., `".spec.replicas"`)
          - `status_replicas_path`: JSON path to the actual replica count in the status (e.g., `".status.readyReplicas"`)
          - `label_selector_path`: JSON path to the label selector for HPA pod counting (e.g., `".spec.selector"`)
    - `conversion`: strategy for converting between versions:
      - `strategy`: `NONE` (no conversion -- all versions have identical schemas) or `WEBHOOK` (use a webhook to convert between versions)
      - `webhook`: if strategy is WEBHOOK, the webhook configuration for version conversion

- **`CRDRegistry`**: manages the lifecycle of CustomResourceDefinitions:
  - **Registration**: when a CRD is created, the registry:
    1. Validates the CRD spec (structural schema compliance, at most one storage version, names are valid DNS subdomains)
    2. Compiles the OpenAPI v3 schema into a validator function
    3. Registers new API endpoints in FizzKube's API server for CRUD operations on the custom resource (`GET`, `LIST`, `CREATE`, `UPDATE`, `DELETE`, `WATCH`)
    4. Stores the CRD definition in etcd at `/apiextensions/crds/{name}`
    5. Updates the API discovery endpoint to include the new resource type
  - **Instance storage**: custom resource instances are stored in etcd at `/{group}/{version}/{plural}/{namespace}/{name}` (namespaced) or `/{group}/{version}/{plural}/{name}` (cluster-scoped)
  - **Validation**: every CREATE and UPDATE for a custom resource instance is validated against the CRD's OpenAPI v3 schema. Unknown fields are pruned (removed from the stored object) unless the schema explicitly allows them. Default values from the schema are applied to missing fields
  - **Deletion**: when a CRD is deleted, all instances of that custom resource are garbage collected. Instances with finalizers are given a grace period to complete their finalization before forced deletion

### Operator SDK

The operator SDK provides a builder-pattern framework for writing custom controllers that manage the lifecycle of custom resources through the operator pattern: watch, detect drift, reconcile, update status.

- **`OperatorBuilder`**: fluent builder for constructing operator controllers:
  ```
  operator = (OperatorBuilder("fizzbuzz-cluster-operator")
      .for_resource(group="fizzbuzz.io", version="v1", kind="FizzBuzzCluster")
      .with_reconciler(FizzBuzzClusterReconciler())
      .with_finalizer("cleanup.fizzbuzz.io/cluster")
      .owns(group="", version="v1", kind="Pod")
      .owns(group="", version="v1", kind="Service")
      .watches(group="", version="v1", kind="ConfigMap", handler=config_change_handler)
      .with_max_concurrent_reconciles(3)
      .with_rate_limiter(RateLimiter(max_delay=300, base_delay=5))
      .build())
  ```
  - `for_resource(group, version, kind)`: the primary resource this operator manages. Changes to this resource trigger reconciliation
  - `with_reconciler(reconciler)`: the `Reconciler` implementation containing the reconciliation logic
  - `with_finalizer(name)`: register a finalizer that runs before resource deletion completes
  - `owns(group, version, kind)`: declare that this operator creates and owns resources of the specified type. Changes to owned resources trigger reconciliation of the owner. Owner references are automatically injected into created resources
  - `watches(group, version, kind, handler)`: watch additional resource types for changes. The handler function maps the changed resource to the reconciliation key (typically the owning custom resource's name/namespace)
  - `with_max_concurrent_reconciles(n)`: maximum number of concurrent reconciliation goroutines (default: 1)
  - `with_rate_limiter(limiter)`: rate limiter for reconciliation re-queues, preventing hot loops on repeatedly failing resources

- **`Reconciler`**: the interface that operator controllers implement:
  - `reconcile(request: ReconcileRequest) -> ReconcileResult`: the core reconciliation function
    - `ReconcileRequest`: contains `name` and `namespace` of the resource to reconcile
    - `ReconcileResult`: contains `requeue` (boolean -- requeue for another reconciliation), `requeue_after` (duration to wait before re-queuing), and `error` (if reconciliation failed)
  - **Reconciliation lifecycle**:
    1. **Fetch**: retrieve the custom resource from etcd. If it does not exist (deleted while queued), return success
    2. **Check finalizers**: if the resource is marked for deletion (has a `deletion_timestamp`) and the operator's finalizer is present, run the finalizer logic, then remove the finalizer from the resource. When all finalizers are removed, the resource is garbage collected
    3. **Detect drift**: compare the desired state (`.spec`) against the actual state (`.status` and owned resources). Identify what needs to change
    4. **Reconcile**: create, update, or delete owned resources to bring actual state in line with desired state. Each owned resource is created with an `owner_reference` pointing back to the custom resource
    5. **Update status**: write the reconciliation result to the custom resource's `.status` sub-resource: `phase` (e.g., `"Provisioning"`, `"Running"`, `"Failed"`), `conditions` (list of typed conditions with status, reason, message, and last transition time), `observed_generation` (the `.metadata.generation` that was last reconciled)
    6. **Return result**: if reconciliation succeeded, return `ReconcileResult(requeue=False)`. If the resource is not yet ready (e.g., waiting for a pod to become healthy), return `ReconcileResult(requeue=True, requeue_after=30)`. If reconciliation failed, return an error for retry with exponential backoff

- **`ReconcileLoop`**: the control loop that drives operator reconciliation:
  - **Watch**: subscribes to etcd watch events for the primary resource type and all owned/watched resource types
  - **Work queue**: incoming events are deduplicated by resource key (namespace/name) and placed in a rate-limited work queue. If the same resource triggers multiple events before its reconciliation completes, only one reconciliation runs, and it sees the latest state
  - **Execution**: dequeues items from the work queue and calls the `Reconciler.reconcile()` method. Handles errors by re-queuing with exponential backoff (base: 5 seconds, max: 300 seconds, multiplier: 2.0)
  - **Leader election**: in multi-replica deployments of the operator, a leader election mechanism (using etcd compare-and-swap) ensures that only one replica actively reconciles at a time. Standby replicas maintain watches but do not process the work queue
  - **Metrics**: exposes operator metrics: reconciliation count (total, success, error), reconciliation latency (p50, p95, p99), work queue depth, work queue latency, and active reconciliation count

### Finalizers

Finalizers provide a mechanism for operators to run cleanup logic before a resource is permanently deleted.

- **`FinalizerManager`**: manages finalizer lifecycle for custom resources:
  - **Adding finalizers**: when an operator creates a custom resource, it adds its finalizer string (e.g., `"cleanup.fizzbuzz.io/cluster"`) to the resource's `metadata.finalizers` list. The resource cannot be garbage collected while any finalizer remains
  - **Finalization on deletion**: when a resource is deleted (DELETE API call), the API server sets `metadata.deletion_timestamp` but does not remove the resource from etcd. The operator's reconcile loop detects the deletion timestamp, runs cleanup logic (e.g., deleting external resources, draining connections, archiving data), and then removes its finalizer from the list. When the finalizer list is empty, the API server garbage collects the resource
  - **Stuck finalizer handling**: if a finalizer is not removed within a configurable timeout (default: 300 seconds), the resource enters `FinalizerStuck` status and an alert is sent via FizzPager. An emergency CLI flag (`--fizzadmit-force-finalize`) allows operators to remove stuck finalizers manually
  - **Pre-delete validation**: finalizer logic can abort deletion by returning an error. The resource remains alive with its deletion timestamp set but is not garbage collected until the finalizer succeeds. This enables "delete protection" for critical resources

### Owner References & Cascading Deletion

Owner references establish parent-child relationships between resources, enabling automatic garbage collection of dependent resources when the parent is deleted.

- **`OwnerReference`**: metadata attached to a child resource pointing to its parent:
  - `api_version`: parent's API version
  - `kind`: parent's kind
  - `name`: parent's name
  - `uid`: parent's UID (ensures the reference is to the specific parent instance, not a recreated resource with the same name)
  - `controller`: boolean -- whether this owner is the managing controller (a resource can have multiple owners but at most one controller)
  - `block_owner_deletion`: boolean -- if true, the owner cannot be deleted until this child is garbage collected first (foreground cascading deletion)

- **`GarbageCollector`**: processes owner reference relationships for cascading deletion:
  - **Background cascading deletion** (default): when a parent is deleted, the garbage collector asynchronously deletes all children with owner references pointing to the parent. The parent is removed from etcd immediately; children are cleaned up in the background
  - **Foreground cascading deletion**: when a parent is deleted with `propagation_policy: Foreground`, the parent's `metadata.finalizers` receives a `foreground-deletion` finalizer. The garbage collector deletes all children first, and only removes the finalizer (allowing the parent to be garbage collected) after all children are gone
  - **Orphan deletion policy**: when a parent is deleted with `propagation_policy: Orphan`, children are not deleted. Their owner references are removed, and they become independent resources
  - **Multi-owner handling**: a resource with multiple owners is only garbage collected when all owners are deleted. This enables shared ownership of common resources (e.g., a ConfigMap owned by multiple operators)

### Built-in CRD Examples

FizzAdmit ships with two built-in CRDs that demonstrate the operator pattern and serve practical purposes within the platform.

- **`FizzBuzzCluster` CRD** (`fizzbuzz.io/v1`):
  - **Purpose**: declarative management of a complete FizzBuzz evaluation cluster. Instead of manually creating deployments, services, and config maps, an operator creates a single `FizzBuzzCluster` resource specifying the desired evaluation configuration, and the `FizzBuzzClusterOperator` reconciles the underlying infrastructure
  - **Schema**: `spec.replicas` (evaluation pod count), `spec.rules` (list of FizzBuzz rules with divisor and label), `spec.cache_enabled` (boolean), `spec.cache_coherence` (MESI protocol mode), `spec.formatter` (output format), `spec.middleware` (list of enabled middleware), `spec.resources` (CPU/memory requests and limits per evaluation pod)
  - **Operator behavior**: creates a Deployment with the specified replica count, a Service for evaluation requests, a ConfigMap with the rule configuration, and optionally a cache sidecar. Reconciles drift: if the Deployment is manually scaled, the operator corrects it to match `spec.replicas`. Updates status with `phase` (`Provisioning`, `Running`, `Degraded`, `Failed`), `ready_replicas`, `current_rules`, and `conditions`

- **`FizzBuzzBackup` CRD** (`fizzbuzz.io/v1`):
  - **Purpose**: declarative backup scheduling for FizzBuzz evaluation state, event sourcing journals, and configuration snapshots
  - **Schema**: `spec.schedule` (cron expression), `spec.retention_count` (number of backups to retain), `spec.target` (what to back up: `"state"`, `"journal"`, `"config"`, `"all"`), `spec.storage_class` (where to store backups: `"filesystem"`, `"overlay"`)
  - **Operator behavior**: the `FizzBuzzBackupOperator` creates backup jobs on the specified schedule, manages retention (deleting backups beyond the retention count, oldest first), and updates status with `last_backup_time`, `last_backup_status`, `backup_count`, and `next_scheduled_backup`
  - **Finalizer**: on deletion, the operator's finalizer ensures that in-progress backups complete before the CRD instance is removed. Completed backups are optionally retained or garbage collected based on a `spec.delete_backups_on_remove` flag

### FizzAdmit Middleware

- **`FizzAdmitMiddleware`**: integrates with the FizzBuzz evaluation middleware pipeline. Intercepts evaluation requests and runs them through a lightweight admission check: verifies that the requesting namespace has sufficient quota for one more evaluation, checks that the evaluation parameters (range, format, rules) conform to the namespace's admission policy, and annotates the evaluation context with admission metadata (admitted_by, admission_latency_ms, mutations_applied)

### CLI Flags

- `--fizzadmit`: enable the FizzAdmit admission controller and CRD framework
- `--fizzadmit-admission-chain`: display the registered admission chain (controller name, phase, priority, resources, failure policy)
- `--fizzadmit-dry-run <resource.yaml>`: submit a resource through the admission chain in dry-run mode, showing whether it would be admitted and what mutations would be applied
- `--fizzadmit-quota-status <namespace>`: display resource quota utilization for a namespace
- `--fizzadmit-limit-range <namespace>`: display the LimitRange configuration for a namespace
- `--fizzadmit-security-profile <namespace>`: display the pod security admission profile and enforcement mode for a namespace
- `--fizzadmit-image-policy`: display the configured image policy rules
- `--fizzadmit-webhooks`: list registered webhook configurations (mutating and validating)
- `--fizzadmit-crd-list`: list all registered CustomResourceDefinitions with their versions and scope
- `--fizzadmit-crd-describe <name>`: display a CRD's schema, versions, printer columns, and subresources
- `--fizzadmit-crd-instances <kind> [--namespace <ns>]`: list instances of a custom resource type
- `--fizzadmit-operators`: list registered operators with their reconciliation status, work queue depth, and error count
- `--fizzadmit-force-finalize <resource>`: forcibly remove all finalizers from a stuck resource (emergency use)

## Why This Is Necessary

Because an API server without admission control is an API server without policy enforcement. FizzKube processes resource requests with the same indiscriminate acceptance that a rubber stamp processes documents. A pod requesting more CPU than the entire cluster possesses is persisted to etcd. A container referencing an image from an untrusted registry is scheduled without question. A deployment with no resource limits is created in a namespace with a resource quota, and the quota is exceeded without notice because no admission controller checks it. The scheduler discovers the impossibility at scheduling time; the kubelet discovers the image problem at pull time; the cgroup discovers the resource violation at enforcement time. Every failure is discovered downstream, after the invalid resource has already been committed to cluster state, after controllers have begun reconciling it, after events have been emitted and audit logs written. Admission controllers catch these failures at the API boundary, before a single byte reaches etcd.

The CRD and operator framework is equally essential. FizzKube supports a fixed set of built-in resource types. The platform has 116 infrastructure modules, each with its own lifecycle, configuration schema, and operational semantics. Without CRDs, managing these modules through FizzKube requires mapping every module's configuration onto Deployments, ConfigMaps, and annotation gymnastics. CRDs provide first-class API types: a `FizzBuzzCluster` resource is as native to the API server as a Pod. The operator pattern provides declarative lifecycle management: instead of imperative scripts that create, update, and tear down resources in sequence, operators continuously reconcile the declared state against reality. This is the same pattern that manages PostgreSQL clusters, Kafka topics, Prometheus monitors, and certificate provisioning in production Kubernetes clusters. The operator ecosystem is what transformed Kubernetes from a container orchestrator into a universal control plane. FizzAdmit gives FizzKube the same extensibility.

## Estimated Scale

~3,500 lines of admission control and operator framework:
- ~250 lines of AdmissionReview protocol (AdmissionRequest, AdmissionResponse, AdmissionStatus, JSON Patch model)
- ~300 lines of admission chain (AdmissionChain, registration, phase ordering, short-circuit, dry-run, audit integration)
- ~300 lines of ResourceQuota admission controller (quota model, usage tracking, scope selectors, status updates)
- ~250 lines of LimitRanger admission controller (LimitRange model, default injection, range validation, JSON Patch generation)
- ~250 lines of PodSecurityAdmission controller (security profiles, namespace enforcement, version pinning)
- ~200 lines of ImagePolicy admission controller (policy rules, image resolution, signature verification)
- ~250 lines of webhook admission controllers (MutatingWebhookConfiguration, ValidatingWebhookConfiguration, WebhookDispatcher, timeout/failure handling)
- ~350 lines of CRD framework (CustomResourceDefinition model, OpenAPI v3 schema validation, CRDRegistry, instance storage, field pruning, defaulting)
- ~350 lines of operator SDK (OperatorBuilder, Reconciler interface, ReconcileLoop, work queue, rate limiter, leader election, metrics)
- ~200 lines of finalizer management (FinalizerManager, finalization lifecycle, stuck handling, pre-delete validation)
- ~200 lines of owner references and garbage collector (OwnerReference, cascading deletion policies, multi-owner handling)
- ~150 lines of built-in CRDs (FizzBuzzCluster, FizzBuzzBackup, operator implementations)
- ~150 lines of middleware and CLI integration
- ~500 lines of tests (admission chain ordering, quota enforcement, limit range mutation, security profile validation, image policy, CRD schema validation, operator reconciliation, finalizer lifecycle, cascading deletion, webhook dispatch)

Total: ~4,000 lines (implementation + tests).
