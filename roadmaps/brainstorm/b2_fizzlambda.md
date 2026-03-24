# FizzLambda -- Serverless Function Runtime

## Idea: FizzLambda -- Serverless Function Runtime

### The Problem

The Enterprise FizzBuzz Platform has containers. It has container orchestration. It has a deployment pipeline, a compose system, a chaos engineering framework, and a complete observability stack for containerized workloads. Every FizzBuzz evaluation runs inside a container managed by FizzContainerd, scheduled by FizzKubeV2, deployed by FizzDeploy, composed by FizzCompose, tested by FizzContainerChaos, and observed by FizzContainerOps. The containerization supercycle containerized the platform. The containers are running.

The containers are always running.

When no one is evaluating FizzBuzz -- and no one is evaluating FizzBuzz most of the time -- the containers sit idle. FizzKubeV2 reports 12 service groups healthy, 47 pods running, 94 containers alive. CPU utilization across the fleet: 0.3%. Memory allocated but unused: 94.7%. The containers are provisioned for peak load. Peak load is one request: a single evaluation of FizzBuzz for numbers 1 through 100. The containers wait. The cgroups account for resources that no computation consumes. The namespaces isolate processes that do nothing. The overlay filesystems maintain writable layers that no process writes to. The network interfaces carry only health check probes confirming that containers capable of evaluating FizzBuzz remain capable of evaluating FizzBuzz.

This is the fundamental limitation of container-based deployment: containers are infrastructure-as-a-server. They require provisioning decisions -- how many replicas, how much CPU, how much memory -- before any workload arrives. These decisions are made by capacity planning, not by demand. When demand is zero, the provisioned capacity is waste. When demand exceeds the provisioned capacity, the platform must scale -- but scaling containers takes seconds to minutes (image pull, container creation, namespace setup, cgroup configuration, health check convergence). During the scaling window, requests queue or fail.

Serverless computing eliminates the provisioning decision. In a serverless model, the unit of deployment is a function, not a container. Functions are invoked by events. When an event arrives, the runtime allocates an execution environment, loads the function code, executes the function, returns the result, and reclaims the environment. When no events arrive, no resources are consumed. Scaling is automatic and instantaneous: each concurrent invocation gets its own execution environment. There is no capacity planning. There is no idle waste. There is no scaling lag.

AWS Lambda launched in 2014 and processed 1 trillion invocations per month by 2020. Google Cloud Functions, Azure Functions, Cloudflare Workers, Vercel Edge Functions, and Deno Deploy followed. The serverless model is not a replacement for containers -- it is a complement. Containers serve long-running stateful workloads. Functions serve short-lived event-driven workloads. The FizzBuzz evaluation is the archetypal short-lived event-driven workload: it receives a request (evaluate these numbers), performs computation (apply rules, format output), and returns a result. No state persists between evaluations. No long-running process is required. Each evaluation is independent, idempotent, and ephemeral.

The Enterprise FizzBuzz Platform has a container runtime (FizzContainerd), a container orchestrator (FizzKubeV2), namespace isolation (FizzNS), resource accounting (FizzCgroup), image packaging (FizzImage), and container networking (FizzCNI). It does not have a serverless function runtime. Every evaluation, regardless of how brief or independent, requires a pre-provisioned, continuously running container. The platform has the engine for containers. It has no engine for functions.

### The Vision

A complete serverless Functions-as-a-Service runtime for the Enterprise FizzBuzz Platform, enabling each FizzBuzz evaluation to execute as an isolated, auto-scaling, event-driven function invocation. FizzLambda introduces the function as a first-class deployment primitive alongside the container: a self-contained unit of computation that is packaged via FizzImage, isolated via FizzNS, resource-limited via FizzCgroup, networked via FizzCNI, and managed by a purpose-built function runtime that handles cold start optimization, warm pool management, concurrent execution, event routing, automatic scaling (including scale-to-zero), function versioning with aliases, dead letter queues for failed invocations, and a layer system for shared dependency management.

The runtime is built on the platform's existing container infrastructure. Each function execution environment is a lightweight container: a minimal FizzImage with the function code and its dependencies, a FizzNS namespace group providing PID, NET, MNT, and USER isolation, a FizzCgroup node enforcing CPU, memory, and execution time limits, and a FizzCNI network interface for event delivery and response return. The critical differentiator from plain containers is lifecycle management: the function runtime creates execution environments on demand, reuses them across invocations (warm pool), reclaims them when idle (scale-to-zero), and scales them elastically to match concurrent demand.

FizzLambda integrates with the platform's event infrastructure to support four trigger types: HTTP invocations (via FizzProxy), timer-based scheduled invocations (via a cron engine), queue-based invocations (via the event sourcing journal), and event bus invocations (via the platform's IEventBus). Each trigger type provides at-least-once delivery semantics. Failed invocations are retried according to a configurable retry policy and, upon exhaustion, routed to a dead letter queue for manual inspection and replay.

### Key Components

- **`fizzlambda.py`** (~4,200 lines): FizzLambda Serverless Function Runtime

#### Function Model

The foundational abstraction for serverless computation in the Enterprise FizzBuzz Platform. A function is a named, versioned, deployable unit of computation with a defined interface, resource profile, and lifecycle.

- **`FunctionDefinition`**: the declarative specification of a serverless function:
  - `function_id` (UUID): globally unique identifier, assigned at creation time, immutable for the lifetime of the function
  - `name` (string): human-readable function name, unique within a namespace. Follows the platform's naming convention: `fizz-<domain>-<operation>`, e.g., `fizz-eval-standard`, `fizz-format-json`, `fizz-cache-invalidate`
  - `namespace` (string): logical grouping for functions, corresponding to the 12 service groups from FizzCompose. Functions within a namespace share network policies and IAM bindings
  - `runtime` (enum): the execution runtime -- `PYTHON_312` (CPython 3.12), `FIZZBYTECODE` (the platform's bytecode VM), `FIZZLANG` (the platform's DSL interpreter). Each runtime provides a language-specific handler invocation mechanism
  - `handler` (string): the entry point for function invocation, specified as `module.function_name`. The runtime loads the module, resolves the function, and invokes it with the event payload and a context object. The handler signature is `def handler(event: dict, context: FunctionContext) -> dict`
  - `code_source` (union): the source of the function code:
    - `InlineCode`: function code embedded directly in the definition (for functions under 4KB). Stored in the function registry's metadata
    - `ImageReference`: a reference to a FizzImage in FizzRegistry containing the function code and dependencies. The image must be built from a function-compatible base image (`fizzbuzz-lambda-base`)
    - `LayerComposition`: a list of FizzLambda layers (shared dependency packages) plus an inline or image-referenced code payload. Layers are merged at execution environment creation time
  - `memory_mb` (int): the memory allocation for the function, in megabytes. Range: 128 to 10,240 (10 GB). The memory allocation directly determines the CPU allocation: 1,769 MB equals one full vCPU (matching AWS Lambda's proportional allocation model). This mapping is enforced by FizzCgroup: a function with 3,538 MB memory receives `cpu.max 200000 100000` (two full CPUs), while a function with 128 MB receives `cpu.max 7234 100000` (approximately 7.2% of one CPU)
  - `timeout_seconds` (int): the maximum execution duration for a single invocation. Range: 1 to 900 (15 minutes). If a function exceeds its timeout, the runtime sends SIGTERM, waits 2 seconds, sends SIGKILL, and records an invocation failure with reason `TIMEOUT`. The timeout is enforced by a watchdog timer in the function runtime, not by the cgroup CPU controller -- CPU accounting measures compute time consumed, while timeout measures wall-clock elapsed
  - `ephemeral_storage_mb` (int): the writable overlay layer capacity for the execution environment. Range: 512 to 10,240. The overlay layer is mounted at `/tmp` in the function's namespace and persists between invocations of the same warm execution environment (but not across cold starts). Enforced by FizzOverlay's layer capacity limit
  - `environment_variables` (dict): key-value pairs injected into the execution environment's process environment. Supports references to the secrets vault: `${fizzvault:secret_name}` is resolved at environment creation time by the secrets injector
  - `vpc_config` (optional): FizzCNI network configuration for the function's execution environment:
    - `subnet_ids` (list): the FizzCNI subnets to attach the function's network interface to
    - `security_group_ids` (list): FizzCNI network policy groups controlling ingress and egress
    - If `vpc_config` is not specified, the function runs in a default network namespace with egress-only connectivity (the function can make outbound network calls but is not reachable from other containers except through the invocation API)
  - `concurrency` (object): concurrency control for the function:
    - `reserved_concurrency` (int): the maximum number of concurrent execution environments for this function. Provides an upper bound to prevent a single function from consuming all available capacity. Range: 0 (disabled, function cannot be invoked) to 1,000. Default: none (shares the account-level concurrency pool)
    - `provisioned_concurrency` (int): the number of pre-initialized execution environments maintained in the warm pool regardless of current demand. These environments are created at function deployment time and kept warm, eliminating cold starts for the first N concurrent invocations. Range: 0 to `reserved_concurrency`. Cost: provisioned environments consume resources even when idle. This is the explicit tradeoff between cold start latency and resource efficiency
  - `dead_letter_config` (optional): configuration for handling invocations that fail after all retries are exhausted:
    - `target_type` (enum): `QUEUE` (send the failed event to a FizzLambda dead letter queue) or `EVENT_BUS` (publish the failure event to the platform's IEventBus)
    - `target_arn` (string): the identifier of the dead letter target (queue name or event bus topic)
  - `tags` (dict): key-value metadata for function categorization, cost allocation, and access control. Standard tags include `fizzbuzz.io/service-group`, `fizzbuzz.io/criticality`, `fizzbuzz.io/owner` (Bob McFizzington for all functions)
  - `created_at` (datetime): creation timestamp
  - `updated_at` (datetime): last modification timestamp

- **`FunctionContext`**: the runtime context object passed to every function invocation:
  - `invocation_id` (UUID): unique identifier for this specific invocation, used for tracing, logging, and idempotency
  - `function_name` (string): the name of the invoked function
  - `function_version` (string): the version or alias that was invoked
  - `memory_limit_mb` (int): the memory allocation for this invocation
  - `timeout_remaining_ms` (property): the remaining wall-clock time before the timeout fires, computed as `timeout_seconds * 1000 - elapsed_ms`. Functions should check this property before starting long-running operations to avoid being killed mid-computation
  - `log_group` (string): the log destination for this invocation's structured log output
  - `trace_id` (string): the FizzOTel trace ID for this invocation, propagated from the trigger source for end-to-end distributed tracing
  - `client_context` (dict): opaque context data passed by the invoker (e.g., correlation IDs, tenant identifiers)
  - `identity` (object): the RBAC identity that triggered the invocation, resolved from the trigger's authentication context

- **`FunctionRegistry`**: the authoritative store for function definitions:
  - In-memory registry backed by a persistent store (the platform's SQLite persistence backend). Supports CRUD operations on function definitions with optimistic concurrency control (version field on each definition prevents lost-update conflicts)
  - Namespace isolation: functions in different namespaces are invisible to each other. Cross-namespace invocation requires explicit IAM grant via FizzCap
  - Dependency validation: when a function is registered or updated, the registry validates that its image reference exists in FizzRegistry, its layers are available, its handler is resolvable (by inspecting the image or inline code), and its VPC configuration references valid FizzCNI subnets and security groups
  - Event emission: function creation, update, deletion, and version publication emit events to the platform's IEventBus for audit logging and GitOps reconciliation

#### Function Runtime

The execution engine that manages the lifecycle of function invocation -- from event receipt to response delivery, including execution environment management, cold start optimization, and warm pool recycling.

- **`FunctionRuntime`**: the core runtime engine:
  - **Invocation lifecycle**: when an invocation request arrives:
    1. **Route**: the `InvocationRouter` resolves the function name and version/alias to a specific `FunctionDefinition` and `FunctionVersion`
    2. **Acquire environment**: the `ExecutionEnvironmentManager` either allocates a warm environment from the pool or creates a new one (cold start)
    3. **Inject event**: the event payload is serialized and written to the environment's stdin pipe (for inline runtimes) or passed via a local Unix domain socket (for image-based runtimes)
    4. **Execute**: the handler function is invoked with the event and context. The runtime monitors execution time against the configured timeout
    5. **Collect result**: the handler's return value is read from stdout (inline) or the response socket (image-based). If the handler raises an exception, the error is captured as an invocation failure
    6. **Return environment**: if the invocation succeeded, the environment is returned to the warm pool for reuse. If it failed, the environment's state may be contaminated; the runtime destroys it and creates a fresh one for the next invocation
    7. **Record metrics**: invocation duration, billed duration (rounded up to the nearest millisecond), memory used (peak RSS from cgroup `memory.peak`), and cold start flag are recorded in the metrics subsystem

  - **`InvocationRequest`**: the wire format for invoking a function:
    - `function_name` (string): the target function
    - `qualifier` (string): the version number or alias name (default: `$LATEST`)
    - `invocation_type` (enum): `REQUEST_RESPONSE` (synchronous -- caller blocks until the function returns), `EVENT` (asynchronous -- the function is invoked, and the caller receives an acknowledgment immediately; the result is discarded or delivered to a callback), `DRY_RUN` (validate the invocation without executing the function)
    - `payload` (bytes): the event payload, up to 6 MB for synchronous invocations and 256 KB for asynchronous invocations
    - `client_context` (dict): opaque context passed to the function via `FunctionContext.client_context`
    - `log_type` (enum): `NONE` (do not return logs) or `TAIL` (return the last 4 KB of function log output in the response)

  - **`InvocationResponse`**: the response from a function invocation:
    - `status_code` (int): 200 for success, 4xx for invocation errors (invalid payload, function not found, concurrency exceeded), 5xx for function errors (unhandled exception, timeout, OOM)
    - `payload` (bytes): the function's return value, serialized as JSON
    - `function_error` (optional string): the error type if the function failed (`Handled` for caught exceptions returned as errors, `Unhandled` for uncaught exceptions, `Timeout` for timeout, `OutOfMemory` for OOM kill)
    - `log_result` (optional string): the last 4 KB of log output (if `log_type` was `TAIL`)
    - `executed_version` (string): the actual version that was executed (useful when invoking via alias, to identify which version the alias resolved to)
    - `metrics` (object): `duration_ms`, `billed_duration_ms`, `memory_used_mb`, `memory_allocated_mb`, `cold_start` (boolean)

  - **`InvocationRouter`**: resolves invocation targets:
    - Version resolution: if `qualifier` is a version number (e.g., `3`), the router retrieves that specific version from the function registry. If `qualifier` is an alias (e.g., `prod`), the router resolves the alias to its target version (or weighted version set for traffic-shifted aliases). If `qualifier` is `$LATEST`, the router retrieves the most recently published version
    - Weighted routing: aliases can point to two versions with a weight distribution (e.g., version 5 at 90% and version 6 at 10%) for canary deployments. The router performs weighted random selection on each invocation
    - Concurrency check: before routing, the router checks the function's current concurrency (number of active execution environments) against its `reserved_concurrency` limit. If the limit would be exceeded, the invocation is throttled (429 Too Many Requests) or queued (for asynchronous invocations)

#### Execution Environment Manager

The component responsible for creating, pooling, reusing, and destroying the isolated execution environments in which functions run. Each execution environment is a lightweight container built on the platform's existing container infrastructure.

- **`ExecutionEnvironmentManager`**: lifecycle management for execution environments:

  - **`ExecutionEnvironment`**: a running instance capable of executing function invocations:
    - `environment_id` (UUID): unique identifier
    - `function_id` (UUID): the function this environment is configured to execute
    - `function_version` (string): the specific version loaded in this environment
    - `state` (enum): `CREATING` (being initialized), `READY` (idle, waiting for an invocation), `BUSY` (executing an invocation), `FROZEN` (suspended, awaiting eviction or reuse), `DESTROYING` (being torn down)
    - `container_id` (string): the FizzContainerd container backing this environment
    - `sandbox_id` (string): the FizzContainerd pod sandbox providing shared namespaces
    - `cgroup_path` (string): the FizzCgroup node path for this environment's resource limits
    - `network_namespace` (string): the FizzNS network namespace for this environment
    - `created_at` (datetime): when the environment was created
    - `last_invocation_at` (datetime): when the environment last processed an invocation (used for idle eviction)
    - `invocation_count` (int): total invocations processed by this environment (used for environment recycling -- environments are destroyed after a configurable number of invocations to prevent state accumulation)
    - `peak_memory_bytes` (int): maximum memory observed from `memory.peak` in this environment's cgroup

  - **Cold start sequence**: creating a new execution environment from scratch:
    1. **Image resolution**: resolve the function's `code_source` to a FizzImage. For `LayerComposition`, merge the layer images and the code image into a composite image using FizzOverlay's multi-layer mount
    2. **Sandbox creation**: create a pod sandbox via FizzContainerd's CRI service (`RunPodSandbox`). The sandbox provides the shared namespace group -- PID namespace (the function's processes are isolated from other functions), NET namespace (with a FizzCNI interface configured per the function's `vpc_config`), MNT namespace (with the composite image mounted read-only and an ephemeral overlay writable layer at `/tmp`), USER namespace (the function runs as a non-root user)
    3. **Cgroup configuration**: create a FizzCgroup node under the FizzLambda controller hierarchy. Configure `memory.max` to `memory_mb * 1024 * 1024`, `memory.high` to 90% of `memory.max` (triggering throttling before OOM), `cpu.max` to the proportional CPU allocation, and `pids.max` to 1,024 (preventing fork bombs)
    4. **Container creation**: create and start the function container via CRI (`CreateContainer`, `StartContainer`). The container entrypoint is the FizzLambda runtime bootstrap -- a lightweight process that initializes the language runtime (Python interpreter, bytecode VM, or FizzLang interpreter), loads the function handler module, and signals readiness by writing to a Unix domain socket
    5. **Runtime initialization**: the bootstrap process loads the function handler. For Python functions, this means importing the handler module and resolving the handler function. For bytecode functions, this means loading the compiled bytecode into the VM. Module-level initialization code (global variable initialization, database connections, library imports) executes during this phase. This is typically the most time-consuming part of the cold start because it includes Python module import overhead, dependency initialization, and any one-time setup the function performs at import time
    6. **Readiness signal**: the bootstrap writes `READY\n` to the control socket. The environment transitions from `CREATING` to `READY`. Cold start latency is measured from the start of step 1 to the receipt of this signal

  - **Cold start latency breakdown**: understanding where cold start time is spent:
    - Image resolution: ~10ms (FizzRegistry content-addressable lookup and FizzOverlay mount)
    - Sandbox creation: ~15ms (namespace creation via FizzNS, cgroup node creation via FizzCgroup)
    - Network setup: ~20ms (FizzCNI interface creation, IP allocation, bridge attachment, route configuration)
    - Container creation: ~10ms (FizzContainerd container and task creation)
    - Runtime bootstrap: ~50-500ms (Python interpreter startup, module imports, handler resolution -- dominated by the size and complexity of the function's dependency tree)
    - Total cold start: ~105-555ms (compared to AWS Lambda's typical 100-500ms for Python runtimes)
    - Cold start optimization strategies are described in the Cold Start Optimizer section below

  - **Warm invocation**: reusing an existing execution environment:
    1. The manager selects a `READY` environment from the warm pool for the matching function/version
    2. The environment transitions from `READY` to `BUSY`
    3. The event payload is injected via the control socket
    4. The handler executes. The `/tmp` writable overlay layer retains state from previous invocations (cached data, temp files, initialized connections). This is the warm start advantage: the Python interpreter is already running, modules are already imported, global state is initialized
    5. The handler returns. The environment transitions from `BUSY` to `READY` and is returned to the warm pool
    6. Warm invocation latency: ~1-5ms overhead (event injection, socket round-trip, response collection)

  - **Environment recycling**: to prevent unbounded state accumulation (memory leaks, growing temp files, stale connections), execution environments are recycled after a configurable maximum invocation count (default: 10,000 invocations) or maximum lifetime (default: 4 hours). Recycling destroys the current environment and allows the next invocation to cold-start a fresh one. Recycling is transparent to the invoker -- the increased latency of one cold start per 10,000 invocations is negligible

  - **Environment destruction**: tearing down an execution environment:
    1. Send SIGTERM to the container's init process via FizzContainerd's task service
    2. Wait 5 seconds for graceful shutdown (allowing the function to flush logs, close connections, release locks)
    3. Send SIGKILL if the process has not exited
    4. Remove the container and pod sandbox via CRI (`RemoveContainer`, `StopPodSandbox`, `RemovePodSandbox`)
    5. Reclaim the cgroup node and network namespace
    6. Delete the ephemeral overlay writable layer

#### Warm Pool Manager

The subsystem responsible for maintaining a pool of pre-initialized execution environments to minimize cold start latency for subsequent invocations.

- **`WarmPoolManager`**: warm pool lifecycle:

  - **Pool structure**: the warm pool is organized as a two-level map: `function_id -> version -> list[ExecutionEnvironment]`. Each entry is a list of `READY` environments, ordered by `last_invocation_at` (most recently used first, implementing MRU eviction -- the most recently used environment is the most likely to have warm caches and fresh connections)

  - **Acquisition**: when the runtime needs an environment:
    1. Check the warm pool for a `READY` environment matching the function ID and version
    2. If found: remove from pool, transition to `BUSY`, return (warm start)
    3. If not found: check if the function has provisioned concurrency environments. If so, and if any are `READY`, use one
    4. If still not found: request a cold start from `ExecutionEnvironmentManager` (cold start)

  - **Return**: when an invocation completes:
    1. If the environment has exceeded its recycling limits: destroy it
    2. If the warm pool for this function/version is at capacity: destroy the least recently used environment in the pool to make room
    3. Otherwise: transition to `READY`, update `last_invocation_at`, add to pool

  - **Idle eviction**: a background sweep runs every 30 seconds (configurable), scanning the warm pool for environments whose `last_invocation_at` exceeds the idle timeout (default: 5 minutes for on-demand environments, never for provisioned concurrency environments). Idle environments are destroyed, freeing their namespace, cgroup, and overlay resources. This is the scale-to-zero mechanism: when a function receives no invocations for 5 minutes, all its warm environments are evicted, and the function consumes zero resources until its next invocation

  - **Provisioned concurrency maintenance**: for functions with `provisioned_concurrency > 0`, the warm pool manager maintains a standing pool of pre-initialized environments:
    - At function deployment time, the manager creates `provisioned_concurrency` environments via cold start
    - These environments are never idle-evicted (they persist regardless of invocation frequency)
    - When a provisioned environment is destroyed (recycling, error), the manager immediately replaces it with a new cold-started environment
    - Provisioned environments are preferred over on-demand environments when serving invocations (they were created for exactly this purpose)
    - The cost: provisioned environments consume cgroup resources even when idle. A function with 10 provisioned environments at 512 MB each consumes 5 GB of memory allocation at all times. This is the explicit tradeoff between latency and resource efficiency, documented in the function's cost allocation dashboard

  - **Pool capacity limits**: the total warm pool capacity across all functions is bounded by the FizzLambda runtime's global configuration:
    - `max_total_environments` (default: 1,000): the maximum number of warm environments across all functions. Prevents the warm pool from consuming unbounded resources on the host
    - `max_environments_per_function` (default: 100): the maximum number of warm environments for a single function (excluding provisioned concurrency)
    - When pool capacity is exceeded, the manager evicts environments using a weighted LRU policy that considers both recency and function priority (functions tagged with `fizzbuzz.io/criticality: high` have higher eviction resistance)

  - **Warm pool metrics**: the warm pool manager emits metrics to the platform's metrics subsystem:
    - `fizzlambda.warm_pool.size` (gauge): current number of warm environments, by function and version
    - `fizzlambda.warm_pool.hits` (counter): invocations served from the warm pool (warm starts)
    - `fizzlambda.warm_pool.misses` (counter): invocations that required a cold start
    - `fizzlambda.warm_pool.evictions` (counter): environments evicted due to idle timeout or capacity pressure
    - `fizzlambda.warm_pool.hit_rate` (gauge): `hits / (hits + misses)` -- the warm start percentage. A low hit rate indicates that the function's invocation pattern does not align with its warm pool retention (invocations are too infrequent, or the idle timeout is too aggressive)

#### Cold Start Optimizer

The subsystem responsible for reducing cold start latency through pre-initialization, caching, and speculative techniques.

- **`ColdStartOptimizer`**: strategies for minimizing cold start impact:

  - **Snapshot and restore**: the most impactful cold start optimization. After a function's execution environment completes its first cold start (all the way through runtime initialization and handler loading), the optimizer captures a snapshot of the environment's memory state, filesystem state, and process state. Subsequent cold starts for the same function/version restore the snapshot instead of repeating the full initialization sequence:
    - **Snapshot capture**: after the bootstrap reports `READY`, the optimizer:
      1. Freezes the container's processes via FizzContainerd's checkpoint API (SIGSTOP)
      2. Captures the process memory pages via `/proc/<pid>/mem` (implemented within FizzNS's proc filesystem emulation)
      3. Captures the overlay filesystem's writable layer state
      4. Captures the cgroup configuration and accounting state
      5. Stores the snapshot as a FizzImage layer in FizzRegistry, tagged with the function ID and version
    - **Snapshot restore**: when a cold start is needed for a function with an existing snapshot:
      1. Create a new pod sandbox and cgroup (same as normal cold start steps 2-3)
      2. Instead of creating a fresh container, mount the snapshot layer as the container's initial state
      3. Restore process memory from the snapshot
      4. Resume execution (SIGCONT)
      5. The bootstrap process is already past the `READY` point -- no module imports, no handler resolution, no runtime initialization
    - **Restore latency**: ~25-40ms (sandbox creation + snapshot mount + memory restore), compared to ~105-555ms for a full cold start. This reduces cold start latency by 70-95%
    - **Snapshot invalidation**: snapshots are invalidated when the function's code, layers, or runtime version changes. The optimizer maintains a content hash of the function's deployment package and compares it on each cold start. Stale snapshots are garbage-collected by the warm pool manager's sweep

  - **Predictive pre-warming**: the optimizer analyzes invocation history to predict future demand and pre-warm execution environments before invocations arrive:
    - **Time-series analysis**: the optimizer maintains a sliding window of invocation timestamps (last 24 hours) per function. It computes an invocation rate time series with 1-minute granularity and fits a simple seasonal decomposition model (identifying daily and hourly patterns)
    - **Pre-warm trigger**: 5 minutes before a predicted demand increase (based on the seasonal pattern), the optimizer pre-creates execution environments up to the predicted concurrency level. These environments enter the warm pool as on-demand environments (subject to idle eviction, unlike provisioned concurrency)
    - **Accuracy feedback loop**: the optimizer compares its predictions to actual invocations and adjusts its model. If pre-warmed environments are consistently evicted without serving invocations, the optimizer reduces its pre-warming aggressiveness. If cold starts occur during predicted demand periods, the optimizer increases its pre-warming lead time

  - **Layer caching**: function code is packaged as FizzImage layers. The optimizer caches the extracted and prepared layer content locally (not just the compressed image layers in FizzRegistry) so that image resolution during cold start does not require decompression:
    - **Extracted layer cache**: a local LRU cache of extracted FizzImage layers, keyed by content digest. When a cold start requires an image, the optimizer checks the local cache before pulling from FizzRegistry
    - **Dependency layer pre-extraction**: common dependency layers (e.g., `fizzbuzz-lambda-base`, popular FizzLambda layers) are extracted and cached permanently (not subject to LRU eviction) based on usage frequency
    - **Cache size limit**: configurable maximum cache size (default: 10 GB). When the cache is full, the least recently used layers are evicted

  - **Runtime pre-initialization**: for the Python runtime, the optimizer pre-creates a "warm interpreter" -- a Python process that has completed interpreter initialization (bytecode compilation of builtins, stdlib import, site-packages enumeration) but has not loaded any function-specific code:
    - The warm interpreter is a single process maintained by the optimizer. When a cold start occurs, instead of starting a new Python process from scratch, the optimizer forks the warm interpreter process (via `os.fork()` semantics implemented by FizzNS) and loads the function-specific handler in the forked process
    - Fork latency: ~5ms (compared to ~50ms for full interpreter startup)
    - The warm interpreter is refreshed periodically (every hour) to pick up any runtime updates
    - This technique is modeled on AWS Lambda's "SnapStart" and Firecracker's microVM snapshot approach

#### Event Trigger System

The subsystem that connects external event sources to function invocations. Each trigger type implements an event source adapter that polls or listens for events and submits invocation requests to the function runtime.

- **`EventTriggerManager`**: manages trigger registrations and event delivery:

  - **`TriggerDefinition`**: the specification for an event trigger:
    - `trigger_id` (UUID): unique identifier
    - `function_name` (string): the target function to invoke when the trigger fires
    - `qualifier` (string): the version or alias to invoke (default: `$LATEST`)
    - `trigger_type` (enum): `HTTP`, `TIMER`, `QUEUE`, `EVENT_BUS`
    - `trigger_config` (union): type-specific configuration (see below)
    - `enabled` (bool): whether the trigger is active
    - `batch_size` (int): for queue triggers, the number of events to batch into a single invocation (default: 1, max: 10,000)
    - `retry_policy` (object): retry configuration for failed invocations:
      - `max_retries` (int): maximum number of retry attempts (default: 2)
      - `retry_delay_seconds` (int): delay between retries, with exponential backoff (default: 60 seconds, doubling each retry)
    - `created_at` (datetime): creation timestamp

  - **HTTP Trigger** (`HTTPTriggerConfig`): exposes a function as an HTTP endpoint via FizzProxy:
    - `route_path` (string): the URL path that triggers the function, e.g., `/api/fizzbuzz/evaluate`. The path is registered with FizzProxy's reverse proxy as a route
    - `http_methods` (list): which HTTP methods trigger the function (default: `["POST"]`)
    - `auth_type` (enum): `NONE` (open access), `IAM` (FizzCap capability check), `API_KEY` (API key validated against the billing monetization's key registry)
    - `cors_config` (optional): CORS headers for browser-based invocations
    - Event mapping: the HTTP request is transformed into a function invocation event:
      - `event.httpMethod` = request method
      - `event.path` = request path
      - `event.headers` = request headers (dict)
      - `event.queryStringParameters` = URL query parameters (dict)
      - `event.body` = request body (string, base64-encoded for binary)
      - `event.isBase64Encoded` = whether the body is base64-encoded
    - Response mapping: the function's response dict is transformed into an HTTP response:
      - `response["statusCode"]` -> HTTP status code
      - `response["headers"]` -> response headers
      - `response["body"]` -> response body
      - `response["isBase64Encoded"]` -> whether to decode body from base64
    - If the function fails (exception, timeout, OOM), FizzProxy returns a 502 Bad Gateway with an error message body

  - **Timer Trigger** (`TimerTriggerConfig`): invokes a function on a schedule:
    - `schedule_expression` (string): supports two formats:
      - Cron expression: standard 5-field cron (`minute hour day_of_month month day_of_week`), e.g., `0 */6 * * *` (every 6 hours). Evaluated in UTC
      - Rate expression: `rate(value unit)` where unit is `minute`, `minutes`, `hour`, `hours`, `day`, `days`, e.g., `rate(5 minutes)` (every 5 minutes)
    - `input` (dict): a static event payload passed to the function on each scheduled invocation. Used to parameterize scheduled evaluations: `{"range_start": 1, "range_end": 1000000, "format": "json"}`
    - The timer engine maintains a priority queue of next-fire-times for all active timer triggers. A scheduler thread wakes at the earliest next-fire-time, submits the invocation, and recomputes the next fire time. Clock accuracy is bounded by FizzClock's synchronization precision (NTP/PTP)
    - Missed invocations: if the scheduler thread is delayed (e.g., during garbage collection or host CPU contention), missed invocations are not replayed. The trigger simply fires at its next scheduled time. This is a deliberate design decision matching AWS EventBridge Scheduler's behavior -- scheduled invocations are best-effort, not exactly-once

  - **Queue Trigger** (`QueueTriggerConfig`): invokes a function for each message (or batch of messages) in a queue:
    - `queue_name` (string): the FizzLambda queue to poll (see Dead Letter Queue section)
    - `batch_size` (int): number of messages to dequeue per invocation (default: 1, max: 10,000). Messages are passed as a list in `event.Records`
    - `batch_window_seconds` (int): the maximum time to wait for a full batch before invoking with a partial batch (default: 0 -- invoke immediately with whatever is available)
    - `max_concurrency` (int): maximum number of concurrent invocations from this queue (default: 2, max: 1,000). Prevents a burst of queued messages from overwhelming the function's concurrency limit
    - Visibility timeout: when messages are dequeued for processing, they become invisible to other consumers for a configurable duration (default: 6 times the function's timeout). If the function succeeds, the messages are deleted from the queue. If the function fails, the messages become visible again after the visibility timeout expires, enabling retry. After a configurable maximum receive count (default: 3), failed messages are moved to the queue's dead letter queue
    - The queue poller uses long-polling: it waits up to 20 seconds for messages to arrive, then returns with whatever is available (or empty). This minimizes the number of empty polls while maintaining responsiveness to new messages

  - **Event Bus Trigger** (`EventBusTriggerConfig`): invokes a function when a matching event is published to the platform's IEventBus:
    - `event_pattern` (dict): a pattern that events must match to trigger the function. The pattern supports exact-match on event attributes:
      - `source` (list of strings): the event source must be one of these values, e.g., `["fizzbuzz.evaluation", "fizzbuzz.cache"]`
      - `detail_type` (list of strings): the event detail type must be one of these values, e.g., `["EvaluationCompleted", "CacheInvalidated"]`
      - `detail` (dict): nested attribute matching on the event's detail payload, supporting prefix, numeric range, and exists/not-exists filters
    - Event delivery: when an event matching the pattern is published to IEventBus, the trigger manager creates an invocation request with the full event as the payload. Multiple functions can be triggered by the same event (fan-out). The event bus provides at-least-once delivery -- the same event may trigger the same function more than once if delivery acknowledgment is lost. Functions triggered by event bus should be idempotent
    - Delivery ordering: events from the same source are delivered in order (FIFO within a source partition). Events from different sources have no ordering guarantee

  - **Event delivery guarantees**:
    - All trigger types provide at-least-once delivery. This means a function may be invoked more than once for the same event (due to retry on failure, acknowledgment timeout, or event redelivery). Functions must be idempotent or use the invocation ID for deduplication
    - At-most-once delivery is not supported (it would require suppressing retries, which is incompatible with reliable event processing)
    - Exactly-once processing can be achieved by the function itself using the invocation ID as an idempotency key with the persistence backend

#### Auto-Scaling Engine

The subsystem responsible for dynamically adjusting the number of execution environments to match current demand, from zero to the function's concurrency limit.

- **`AutoScaler`**: reactive scaling based on concurrent invocation demand:

  - **Scale-to-zero**: when a function has no active invocations and no warm pool environments, it consumes zero resources. The function definition exists in the registry but has no corresponding containers, namespaces, cgroups, or network interfaces. The first invocation after scale-to-zero triggers a cold start. This is the default behavior for all functions without provisioned concurrency

  - **Scale-up policy**: when invocation demand exceeds available warm environments:
    - The auto-scaler monitors the ratio of queued invocations to available environments
    - When queued invocations exceed zero (all warm environments are `BUSY`), the auto-scaler initiates concurrent cold starts for new environments
    - Burst scaling: up to 500 environments can be created simultaneously (matching AWS Lambda's burst concurrency). After the initial burst, scaling continues at a rate of 500 additional environments per minute
    - Scaling is bounded by the function's `reserved_concurrency` (if set) and the global `max_total_environments`
    - Scaling events are logged and emitted to the metrics subsystem

  - **Scale-down policy**: when invocation demand decreases:
    - Scale-down is handled by the warm pool manager's idle eviction, not by the auto-scaler directly
    - Environments that have been idle for longer than the idle timeout (5 minutes) are evicted
    - Scale-down is gradual: environments are evicted one by one as they exceed the idle timeout, not all at once. This prevents premature eviction of environments that might serve a subsequent invocation burst
    - Provisioned concurrency environments are never scaled down by the auto-scaler

  - **Concurrency tracking**: the auto-scaler maintains a real-time counter of active invocations per function:
    - `active_invocations[function_id]` is incremented when an environment transitions from `READY` to `BUSY`
    - `active_invocations[function_id]` is decremented when an environment transitions from `BUSY` to `READY` or `DESTROYING`
    - This counter is used for both scaling decisions and concurrency limit enforcement

  - **Throttling**: when a function's active invocations reach its `reserved_concurrency` limit:
    - Synchronous invocations (`REQUEST_RESPONSE`) receive an immediate 429 Too Many Requests response with a `Retry-After` header
    - Asynchronous invocations (`EVENT`) are queued in the function's internal event queue and processed when concurrency becomes available. The queue has a depth limit (default: 100,000 events). If the queue is full, the invocation is rejected with a 429 response
    - Throttled invocations are recorded in the metrics subsystem for capacity planning

  - **Auto-scaler metrics**:
    - `fizzlambda.autoscaler.concurrent_executions` (gauge): current active invocations per function
    - `fizzlambda.autoscaler.scale_up_events` (counter): number of cold starts triggered by scaling
    - `fizzlambda.autoscaler.throttled_invocations` (counter): invocations rejected due to concurrency limits
    - `fizzlambda.autoscaler.queue_depth` (gauge): number of queued asynchronous invocations per function

#### Function Versioning and Aliases

The subsystem that manages immutable function versions and mutable aliases that point to specific versions, enabling safe deployments and traffic shifting.

- **`FunctionVersionManager`**: version lifecycle management:

  - **Publishing a version**: when a function's code, configuration, or layers are finalized, the developer publishes a version:
    - A version is an immutable snapshot of the function definition at a point in time
    - Versions are numbered sequentially: 1, 2, 3, etc. Version numbers are never reused
    - `$LATEST` is a mutable pseudo-version that always points to the function's current (unpublished) state. Changes to the function definition update `$LATEST`. Publishing captures `$LATEST` as a numbered version
    - Published versions cannot be modified. To change a function's code, modify `$LATEST` and publish a new version
    - Each version stores: the complete function definition, the code source (image digest or inline code content hash), and the configuration (memory, timeout, environment variables)
    - Version metadata: `version_number`, `description` (optional developer note), `code_sha256` (content hash for integrity verification), `published_at`

  - **`FunctionAlias`**: a named pointer to one or two function versions:
    - `alias_name` (string): human-readable name, e.g., `prod`, `staging`, `canary`, `rollback`
    - `function_name` (string): the function this alias belongs to
    - `function_version` (string): the primary version this alias points to
    - `routing_config` (optional): weighted routing configuration for traffic shifting:
      - `additional_version` (string): a second version to route traffic to
      - `additional_version_weight` (float): the percentage of traffic (0.0 to 1.0) to route to the additional version. The primary version receives `1.0 - additional_version_weight`
    - Aliases are mutable: updating an alias to point to a new version is an instant, atomic operation. This is the primary deployment mechanism: publish a new version, update the `prod` alias to point to it. Rollback: update the `prod` alias to point to the previous version
    - Alias invocation: when a function is invoked via alias (e.g., `fizz-eval-standard` with qualifier `prod`), the invocation router resolves the alias to its target version(s) and routes accordingly

  - **Traffic shifting with aliases**: progressive deployment using weighted aliases:
    - **Linear traffic shift**: gradually increase traffic to the new version by updating the alias weight at fixed intervals. Example: start at 10% new / 90% old, increase by 10% every 5 minutes until reaching 100% new / 0% old. Rollback if error rate exceeds threshold at any step
    - **Canary traffic shift**: send a small percentage of traffic to the new version (e.g., 5%), monitor for a fixed duration (e.g., 30 minutes), then either shift 100% or rollback. No intermediate steps
    - **All-at-once**: update the alias to 100% new version immediately. Fastest deployment, highest risk
    - Traffic shift orchestration is managed by the `TrafficShiftOrchestrator`, which updates alias weights on a schedule and monitors FizzSLI metrics for anomalies

  - **Version cleanup**: old versions accumulate over time. A garbage collection policy removes versions that are:
    - Not referenced by any alias
    - Not the `$LATEST` version
    - Older than the configured retention period (default: 30 days)
    - The GC is conservative: it never removes a version that is actively serving invocations (has warm pool environments)

#### Dead Letter Queue System

The subsystem for handling function invocations that fail after all retries are exhausted. Dead letter queues provide a safety net that prevents event loss and enables manual inspection, debugging, and replay of failed invocations.

- **`DeadLetterQueueManager`**: DLQ lifecycle and operations:

  - **`FizzLambdaQueue`**: a FIFO message queue used for both DLQ and general-purpose queue triggers:
    - `queue_name` (string): unique identifier
    - `messages` (deque): ordered list of messages
    - `visibility_timeout_seconds` (int): how long a dequeued message is invisible to other consumers (default: 30)
    - `message_retention_seconds` (int): how long a message is retained in the queue before automatic deletion (default: 1,209,600 = 14 days)
    - `max_message_size_bytes` (int): maximum message payload size (default: 262,144 = 256 KB)
    - `max_receive_count` (int): for DLQs, the maximum number of times a message can be received before it is considered permanently failed. After this count, the message is marked as `DEAD` and no longer delivered
    - `redrive_policy` (optional): configuration for moving messages from a source queue to this DLQ after `maxReceiveCount` failures in the source queue

  - **`QueueMessage`**: an individual message in a queue:
    - `message_id` (UUID): unique identifier
    - `body` (bytes): the message payload (the original event that triggered the failed invocation)
    - `attributes` (dict): system attributes:
      - `SentTimestamp` (int): when the message was enqueued (epoch milliseconds)
      - `ApproximateReceiveCount` (int): how many times this message has been received
      - `ApproximateFirstReceiveTimestamp` (int): when this message was first received
      - `SourceFunction` (string): the function that failed to process this message
      - `SourceTrigger` (string): the trigger that generated the original invocation
      - `ErrorType` (string): the type of error that caused the failure (Unhandled, Timeout, OutOfMemory)
      - `ErrorMessage` (string): the error message from the failed invocation
      - `LastRetryTimestamp` (int): when the last retry was attempted
    - `receipt_handle` (string): an opaque token used to delete or extend the visibility of a received message

  - **DLQ operations**:
    - **Send** (`send_message`): enqueue a failed invocation event. Called by the retry manager when all retries are exhausted. The message body is the original event payload. Attributes capture the failure context (which function, which trigger, what error, how many retries were attempted)
    - **Receive** (`receive_messages`): dequeue one or more messages for inspection or replay. Received messages become invisible for `visibility_timeout_seconds`. If the receiver does not delete the message within the visibility timeout, it becomes visible again (enabling retry). The `max_number_of_messages` parameter controls batch size (default: 1, max: 10)
    - **Delete** (`delete_message`): permanently remove a message from the queue. Called after successful replay or manual resolution
    - **Purge** (`purge_queue`): remove all messages from the queue. Destructive operation requiring FizzApproval multi-party approval
    - **Replay** (`replay_message`): re-invoke the original function with the failed event payload. The message remains in the DLQ until the replay succeeds, at which point it is automatically deleted. If the replay fails, the message's receive count is incremented

  - **DLQ per function**: each function with a `dead_letter_config` has a dedicated DLQ. The DLQ name follows the convention `{function_name}-dlq`. Functions without `dead_letter_config` drop failed events after retries (events are lost). The platform's compliance engine (SOX/GDPR/HIPAA) requires DLQ configuration for all functions processing regulated data

  - **DLQ monitoring**: the DLQ manager emits metrics:
    - `fizzlambda.dlq.message_count` (gauge): number of messages in each DLQ
    - `fizzlambda.dlq.oldest_message_age_seconds` (gauge): age of the oldest message (indicates how long failures have been unresolved)
    - `fizzlambda.dlq.messages_received` (counter): total messages received from DLQ for inspection/replay
    - `fizzlambda.dlq.messages_replayed` (counter): total messages successfully replayed
    - Alert threshold: if `message_count` exceeds a configurable threshold (default: 100) or `oldest_message_age_seconds` exceeds 86,400 (24 hours), FizzPager is notified

#### Layer System

The subsystem for managing shared dependency packages that multiple functions can reference, eliminating the need to bundle common libraries into every function's deployment package.

- **`LayerManager`**: layer lifecycle and composition:

  - **`FunctionLayer`**: a versioned package of shared dependencies:
    - `layer_name` (string): unique identifier, e.g., `fizzbuzz-domain`, `fizzbuzz-ml-deps`, `fizzbuzz-crypto`
    - `layer_version` (int): sequential version number (like function versions, immutable once published)
    - `description` (string): human-readable description of the layer's contents
    - `compatible_runtimes` (list): which runtimes can use this layer (`PYTHON_312`, `FIZZBYTECODE`, `FIZZLANG`)
    - `content` (FizzImage reference): the layer's content is stored as a FizzImage layer in FizzRegistry. The image contains the dependency files installed in a well-known directory structure:
      - `/opt/python/` for Python packages (added to `PYTHONPATH` at runtime)
      - `/opt/fizzbytecode/` for bytecode VM modules (added to the VM's module search path)
      - `/opt/fizzlang/` for FizzLang libraries (added to the FizzLang import path)
      - `/opt/bin/` for executables (added to `PATH`)
      - `/opt/lib/` for shared libraries (added to `LD_LIBRARY_PATH`)
    - `content_sha256` (string): content hash for integrity verification
    - `size_bytes` (int): compressed size of the layer content
    - `created_at` (datetime): creation timestamp

  - **Layer composition**: a function can reference up to 5 layers. At execution environment creation time, the layers are merged with the function's code using FizzOverlay's multi-layer mount:
    - Layer order matters: layers are mounted in the order specified in the function definition. If two layers provide the same file path, the later layer wins (overlay semantics)
    - The function's own code is mounted on top of all layers, ensuring that function-specific files always take precedence over layer-provided files
    - Total uncompressed layer size limit: 250 MB (matching AWS Lambda's layer size limit). The limit is enforced at function deployment time, not at invocation time

  - **Standard platform layers**: the FizzLambda runtime provides pre-built layers for common platform dependencies:
    - **`fizzbuzz-domain-layer`**: the platform's domain layer (models, enums, exceptions, interfaces). Every function that interacts with FizzBuzz domain objects needs this layer
    - **`fizzbuzz-application-layer`**: the application layer (FizzBuzzServiceBuilder, rule factories, strategy ports). Functions that orchestrate FizzBuzz evaluation need this layer
    - **`fizzbuzz-ml-layer`**: the neural network engine, genetic algorithm, and federated learning dependencies. Functions that perform ML-based evaluation need this layer
    - **`fizzbuzz-crypto-layer`**: HMAC tokens, capability security, blockchain, and smart contract dependencies. Functions that perform authenticated or signed operations need this layer
    - **`fizzbuzz-data-layer`**: SQLite, filesystem, and in-memory persistence dependencies. Functions that read or write persistent state need this layer
    - **`fizzbuzz-observability-layer`**: OpenTelemetry, flame graph, and metrics dependencies. Functions that emit traces or metrics need this layer (recommended for all production functions)

  - **Layer versioning and lifecycle**:
    - Layers follow the same immutable versioning scheme as functions: publishing creates an immutable version snapshot
    - Layer versions are referenced by `layer_name:version_number` in function definitions
    - Layer updates do not automatically propagate to functions. Each function pins a specific layer version. To use a new layer version, the function definition must be updated and a new function version published
    - This explicit pinning prevents "dependency hell" where a shared library update silently breaks multiple functions. Each function's dependency set is fully deterministic

  - **Layer caching**: layers are cached by the cold start optimizer at multiple levels:
    - **Registry level**: compressed layer content in FizzRegistry (content-addressable, deduplicated)
    - **Local level**: extracted layer content on the runtime host (LRU cache managed by the cold start optimizer)
    - **Snapshot level**: layer content is included in execution environment snapshots, so snapshot-restored environments do not need to re-extract layers

#### Invocation Retry Manager

The subsystem responsible for retrying failed invocations according to the trigger's retry policy before routing events to the dead letter queue.

- **`RetryManager`**: retry orchestration:

  - **Retry eligibility**: not all failures are retryable. The retry manager classifies failures as:
    - **Retryable**: function timeout (may succeed with a different execution environment), transient errors (network issues, temporary dependency unavailability), runtime errors that may be caused by execution environment state (memory fragmentation, stale connections in warm environments)
    - **Non-retryable**: function code errors (syntax errors, import failures), configuration errors (invalid handler, missing environment variables), payload validation errors (invalid event format). Non-retryable failures are sent directly to the DLQ without retry
    - **Ambiguous**: unhandled exceptions from the function code. These are retried by default (the exception may be caused by a transient dependency issue), but functions can signal non-retryability by returning an error response with `"retry": false`

  - **Retry execution**:
    1. The retry manager receives a failed invocation event from the function runtime
    2. It classifies the failure as retryable or non-retryable
    3. For retryable failures, it checks the trigger's retry policy: if the current attempt is less than `max_retries`, it schedules a retry after `retry_delay_seconds * 2^(attempt - 1)` (exponential backoff)
    4. The retry is submitted as a new invocation request to the function runtime. The invocation uses a fresh execution environment (the previous environment may have been in a bad state)
    5. If the retry succeeds, the event is considered processed. If the retry fails, the manager increments the attempt counter and repeats from step 2
    6. When all retries are exhausted, the event is routed to the function's DLQ (if configured) or discarded (if no DLQ is configured)

  - **Retry metrics**:
    - `fizzlambda.retry.attempts` (counter): total retry attempts per function and failure type
    - `fizzlambda.retry.successes` (counter): retries that succeeded (recovered from transient failure)
    - `fizzlambda.retry.exhaustions` (counter): events that exhausted all retries and were sent to DLQ

#### Resource Allocation and Cgroup Integration

The subsystem that maps function resource configurations to FizzCgroup controllers, enforcing memory limits, CPU proportional allocation, PID limits, and execution timeout via the platform's existing cgroup infrastructure.

- **`ResourceAllocator`**: function-to-cgroup mapping:

  - **Cgroup hierarchy**: FizzLambda creates a dedicated cgroup subtree under the platform's root cgroup:
    ```
    /fizzbuzz/fizzlambda/
      ├── functions/
      │   ├── fizz-eval-standard/
      │   │   ├── env-{uuid-1}/    # execution environment 1
      │   │   ├── env-{uuid-2}/    # execution environment 2
      │   │   └── env-{uuid-3}/    # execution environment 3
      │   ├── fizz-format-json/
      │   │   └── env-{uuid-4}/
      │   └── fizz-cache-invalidate/
      │       └── env-{uuid-5}/
      └── system/                   # FizzLambda runtime overhead
          ├── scheduler/
          ├── warm-pool-manager/
          └── event-poller/
    ```

  - **Memory allocation**: the function's `memory_mb` is mapped to cgroup memory controller settings:
    - `memory.max` = `memory_mb * 1024 * 1024` (hard limit, triggers OOM kill)
    - `memory.high` = `memory.max * 0.9` (soft limit, triggers throttling -- reclaim pressure increases, processes slow down but are not killed)
    - `memory.swap.max` = `0` (no swap -- function execution must fit in allocated memory)
    - Peak memory tracking: `memory.peak` is read after each invocation and reported in the invocation response's `memory_used_mb` field

  - **CPU allocation**: proportional CPU allocation based on memory:
    - The mapping follows AWS Lambda's model: 1,769 MB = 1 full vCPU
    - `cpu.max` is set to `(memory_mb / 1769) * cpu_period` where `cpu_period` is 100,000 microseconds
    - Minimum CPU: functions with less than 1,769 MB still receive a proportional CPU slice (a 128 MB function gets ~7.2% of one CPU)
    - Maximum CPU: functions with more than 1,769 MB receive proportionally more CPU (a 10,240 MB function gets ~5.8 vCPUs)
    - CPU accounting: `cpu.stat` is read after each invocation to report `system_time_ms` and `user_time_ms` in the invocation metrics

  - **PID limit**: `pids.max` = 1,024 for all function execution environments. This prevents a malfunctioning function from fork-bombing the host. The limit is generous for legitimate use (a function spawning multiple threads or subprocesses) but bounded against runaway process creation

  - **I/O bandwidth**: optional I/O throttling for functions that perform disk-intensive operations:
    - `io.max` is configured based on the function's `ephemeral_storage_mb`: functions with larger ephemeral storage receive proportionally more I/O bandwidth
    - I/O throttling prevents a single function from saturating the host's I/O bandwidth and impacting other functions' performance

  - **Execution timeout enforcement**: while the function's `timeout_seconds` is enforced by the runtime's watchdog timer (not by the cgroup), the cgroup provides a backstop:
    - If the watchdog fails to kill the function process (e.g., the watchdog thread is blocked), the cgroup's `memory.oom.group` setting ensures that the entire execution environment is killed if any process in the cgroup exceeds the memory limit
    - A separate cgroup-level timeout (set to `timeout_seconds + 10`) is enforced by the warm pool manager: if an environment remains in `BUSY` state for longer than the timeout plus grace period, the manager forcibly destroys the environment

#### Function Packaging via FizzImage

The subsystem that integrates function code packaging with the FizzImage container image system, providing a standard function base image and a streamlined build process.

- **`FunctionPackager`**: function image build and management:

  - **`fizzbuzz-lambda-base` image**: the base image for all FizzLambda function execution environments:
    - Built on `fizzbuzz-base` (the platform's minimal base image containing the Python runtime and domain layer)
    - Adds the FizzLambda runtime bootstrap: the lightweight process that initializes the language runtime, loads the function handler, and manages the invocation lifecycle within the execution environment
    - Adds the FizzLambda runtime interface: the Unix domain socket server that receives invocation events and returns responses
    - Adds the FizzLambda logging agent: captures function stdout/stderr and forwards structured log output to the container's log driver
    - Image size: ~55 MB compressed (10 MB larger than `fizzbuzz-base` due to the runtime bootstrap and interface)

  - **Function image build**: creating a deployable function image:
    - **FizzFile template**: the packager generates a FizzFile for each function:
      ```
      FROM fizzbuzz-lambda-base:latest
      COPY function_code/ /var/task/
      ENV HANDLER=module.handler_name
      ENV FUNCTION_TIMEOUT=300
      ENV FUNCTION_MEMORY=512
      ENTRYPOINT ["/var/runtime/bootstrap"]
      ```
    - **Layer integration**: if the function references layers, the FizzFile includes additional `FROM` instructions that mount the layer images at `/opt/`:
      ```
      FROM fizzbuzz-lambda-base:latest
      FROM fizzbuzz-domain-layer:3 AS layer0
      COPY --from=layer0 /opt/ /opt/
      FROM fizzbuzz-ml-layer:1 AS layer1
      COPY --from=layer1 /opt/ /opt/
      COPY function_code/ /var/task/
      ```
    - **Build process**: the packager invokes FizzImage's `BaseImageBuilder` with the generated FizzFile. The resulting image is pushed to FizzRegistry with tags: `{function_name}:{version}`, `{function_name}:$LATEST`, and `{function_name}:{code_sha256[:12]}`

  - **Inline code packaging**: for functions with `InlineCode` source:
    - The packager writes the inline code to a temporary directory, generates a FizzFile, and builds an image. The inline code is small (< 4KB) so the image layer containing it is minimal
    - Inline code images are cached by content hash: if two functions have identical inline code, they share the same image layer (content-addressable deduplication in FizzRegistry)

  - **Image lifecycle**: function images follow the platform's image versioning scheme:
    - Each published function version has a corresponding immutable image tagged with the version number
    - `$LATEST` images are mutable (rebuilt when the function definition changes)
    - Old images are garbage-collected by FizzRegistry's garbage collector when the corresponding function version is cleaned up

#### Invocation Routing and Concurrency Control

The subsystem that routes invocation requests to execution environments with concurrency awareness, implementing the FizzLambda data plane.

- **`InvocationDispatcher`**: the central invocation routing engine:

  - **Request flow**:
    1. An invocation request arrives from a trigger (HTTP, timer, queue, event bus) or direct API call
    2. The dispatcher validates the request: function exists, qualifier resolves, payload size is within limits
    3. The dispatcher checks concurrency: if the function's active invocations equal its `reserved_concurrency`, the request is throttled (synchronous) or queued (asynchronous)
    4. The dispatcher acquires an execution environment from the warm pool manager (warm) or execution environment manager (cold)
    5. The dispatcher submits the event to the acquired environment and waits for the response (synchronous) or returns immediately (asynchronous)
    6. On completion, the dispatcher records metrics, updates concurrency counters, and returns the environment to the warm pool

  - **Concurrency model**:
    - Each function has a concurrency counter tracking active invocations
    - The account-level concurrency pool has a default limit of 1,000 concurrent executions across all functions
    - Functions with `reserved_concurrency` draw from a reserved partition of the pool (guaranteed capacity but reduced sharing)
    - Functions without `reserved_concurrency` share the unreserved partition of the pool
    - If the unreserved pool is exhausted, unreserved functions are throttled even if reserved functions have unused capacity (reserved capacity is not shared)

  - **Request queuing** (asynchronous invocations only):
    - When an asynchronous invocation cannot be served immediately (concurrency limit), it is placed in the function's internal event queue
    - The queue is drained by a background worker that submits invocations as concurrency becomes available
    - Queue ordering: FIFO (first in, first out)
    - Queue depth limit: 100,000 events (configurable). Events exceeding the depth limit are rejected with a 429 response
    - Queue age limit: events older than 6 hours in the queue are discarded and routed to the DLQ (if configured)

  - **Dispatch metrics**:
    - `fizzlambda.dispatch.invocations` (counter): total invocations by function, type (sync/async), and outcome (success/failure/throttled)
    - `fizzlambda.dispatch.duration_ms` (histogram): end-to-end invocation duration (from request receipt to response delivery)
    - `fizzlambda.dispatch.cold_start_ms` (histogram): cold start latency for invocations that required a new environment
    - `fizzlambda.dispatch.queue_wait_ms` (histogram): time async invocations spent in the queue before dispatch

#### FizzBuzz Evaluation Functions

The pre-built serverless functions that implement FizzBuzz evaluation as FizzLambda functions, demonstrating the runtime's capabilities and providing the canonical serverless FizzBuzz evaluation path.

- **`StandardEvaluationFunction`**: evaluates FizzBuzz using the standard rule engine (divisible by 3 = Fizz, divisible by 5 = Buzz, divisible by both = FizzBuzz):
  - Handler: receives `{"numbers": [1, 2, ..., 100]}` and returns `{"results": [{"number": 1, "output": "1"}, {"number": 3, "output": "Fizz"}, ...]}`
  - Layers: `fizzbuzz-domain-layer`, `fizzbuzz-application-layer`
  - Memory: 256 MB, Timeout: 30 seconds
  - Trigger: HTTP trigger at `/api/v1/fizzbuzz/evaluate`

- **`ConfigurableEvaluationFunction`**: evaluates FizzBuzz using configurable rules specified in the event payload:
  - Handler: receives `{"numbers": [1, ..., 100], "rules": [{"divisor": 3, "output": "Fizz"}, {"divisor": 7, "output": "Bazz"}]}` and returns results according to the custom rules
  - Layers: `fizzbuzz-domain-layer`, `fizzbuzz-application-layer`
  - Memory: 512 MB, Timeout: 60 seconds
  - Trigger: HTTP trigger at `/api/v1/fizzbuzz/evaluate/configurable`

- **`MLEvaluationFunction`**: evaluates FizzBuzz using the neural network classifier:
  - Handler: receives `{"numbers": [1, ..., 100], "model": "default"}` and returns results classified by the trained neural network
  - Layers: `fizzbuzz-domain-layer`, `fizzbuzz-application-layer`, `fizzbuzz-ml-layer`
  - Memory: 2,048 MB, Timeout: 120 seconds (model loading is the bottleneck -- warm starts serve in under 10ms)
  - Trigger: HTTP trigger at `/api/v1/fizzbuzz/evaluate/ml`
  - Provisioned concurrency: 2 (ML model loading on cold start takes ~800ms; provisioned environments eliminate this for the first 2 concurrent invocations)

- **`BatchEvaluationFunction`**: evaluates FizzBuzz for large ranges by splitting the range into chunks and invoking `StandardEvaluationFunction` in parallel:
  - Handler: receives `{"range_start": 1, "range_end": 1000000, "chunk_size": 10000}` and returns aggregated results
  - This function demonstrates FizzLambda's fan-out pattern: a coordinator function that invokes other functions. The coordinator uses synchronous invocation to invoke 100 parallel `StandardEvaluationFunction` instances (one per chunk), waits for all results, and merges them
  - Layers: `fizzbuzz-domain-layer`, `fizzbuzz-application-layer`
  - Memory: 512 MB, Timeout: 300 seconds (waiting for parallel sub-invocations)
  - Trigger: HTTP trigger at `/api/v1/fizzbuzz/evaluate/batch`

- **`ScheduledReportFunction`**: generates a daily FizzBuzz evaluation report and stores it in the filesystem persistence backend:
  - Handler: evaluates FizzBuzz for numbers 1 through 100, formats the output as JSON, appends a timestamp and metadata, and writes the report to persistent storage
  - Layers: `fizzbuzz-domain-layer`, `fizzbuzz-application-layer`, `fizzbuzz-data-layer`
  - Memory: 256 MB, Timeout: 60 seconds
  - Trigger: timer trigger with schedule `0 0 * * *` (midnight UTC daily)

- **`CacheInvalidationFunction`**: invalidates the MESI cache when configuration changes are detected:
  - Handler: receives an event bus event for `ConfigurationChanged`, reads the changed keys, and issues cache invalidation commands to the MESI cache coherence controller
  - Layers: `fizzbuzz-domain-layer`, `fizzbuzz-application-layer`
  - Memory: 256 MB, Timeout: 30 seconds
  - Trigger: event bus trigger with pattern `{"source": ["fizzbuzz.configuration"], "detail_type": ["ConfigurationChanged"]}`
  - Dead letter config: queue-based DLQ (missed cache invalidations must be recoverable)

- **`AuditLogFunction`**: processes FizzBuzz evaluation events and writes audit log entries for compliance:
  - Handler: receives batched evaluation events from a queue, formats them into SOX/GDPR/HIPAA-compliant audit records, and writes them to the compliance engine's audit journal
  - Layers: `fizzbuzz-domain-layer`, `fizzbuzz-data-layer`, `fizzbuzz-observability-layer`
  - Memory: 512 MB, Timeout: 60 seconds
  - Trigger: queue trigger with batch size 100 and batch window 30 seconds
  - Dead letter config: queue-based DLQ (compliance requires zero audit event loss)

#### FizzLambda Middleware Integration

- **`FizzLambdaMiddleware`**: integrates the serverless function runtime with the platform's middleware pipeline. When a FizzBuzz evaluation is served by a FizzLambda function (as opposed to the traditional container-based evaluation path), the middleware annotates the evaluation response with serverless execution metadata:
  - `X-FizzLambda-Function` header: the function name that served the evaluation
  - `X-FizzLambda-Version` header: the function version that executed
  - `X-FizzLambda-Invocation-Id` header: the unique invocation identifier for tracing
  - `X-FizzLambda-Cold-Start` header: `true` or `false` indicating whether the invocation triggered a cold start
  - `X-FizzLambda-Duration-Ms` header: the function execution duration in milliseconds
  - `X-FizzLambda-Memory-Used-Mb` header: the peak memory used by the function
  - `X-FizzLambda-Billed-Duration-Ms` header: the billed duration rounded to the nearest millisecond

  The middleware also routes evaluation requests to the appropriate path (container-based via FizzKubeV2 or serverless via FizzLambda) based on the `--fizzlambda-mode` flag:
  - `container` (default): evaluations are served by the traditional container-based path
  - `serverless`: evaluations are served by FizzLambda functions
  - `hybrid`: evaluations are routed based on load -- low-volume evaluations use serverless (cost-efficient for sporadic use), high-volume evaluations use containers (amortized cold start overhead)

#### FizzBob Cognitive Load Integration

- **`FizzLambdaCognitiveLoadGate`**: integrates with FizzBob's cognitive load model for serverless operations:
  - Function deployment (creating/updating functions, publishing versions, updating aliases) requires cognitive load assessment. If Bob McFizzington's NASA-TLX score exceeds 65, deployments are queued until cognitive load decreases
  - Function invocation does not require cognitive load assessment (invocations are automated event responses, not operator-initiated actions)
  - Chaos experiments targeting FizzLambda functions (via FizzContainerChaos) require cognitive load assessment at the chaos threshold (NASA-TLX score 60)
  - Emergency deployments (via `--fizzlambda-emergency-deploy`) bypass cognitive load gating

#### Compliance Integration

- **`FizzLambdaComplianceEngine`**: extends the platform's SOX/GDPR/HIPAA compliance engine to cover serverless operations:
  - **SOX compliance**: function deployments are logged as change events in the SOX audit trail. Function version history provides complete auditability of code changes. Dead letter queue retention ensures no financial evaluation events are lost
  - **GDPR compliance**: functions processing personal data (if the FizzBuzz input contains personal identifiers -- unlikely but architecturally possible) must declare data processing purposes in their tags. Function execution environments are ephemeral, supporting the "right to erasure" by design -- no personal data persists beyond the invocation
  - **HIPAA compliance**: functions processing protected health information (if FizzBuzz evaluations are classified as medical procedures -- enterprise classification pending) must run in VPC-configured execution environments with encrypted network traffic via FizzCNI's mTLS support

#### CLI Flags

- `--fizzlambda`: enable the FizzLambda serverless function runtime
- `--fizzlambda-mode <container|serverless|hybrid>`: set the evaluation routing mode (default: `container`)
- `--fizzlambda-create <name> --handler <handler> --runtime <runtime> --memory <mb> --timeout <seconds>`: create a new function
- `--fizzlambda-update <name>`: update an existing function's configuration
- `--fizzlambda-delete <name>`: delete a function and all its versions
- `--fizzlambda-publish <name>`: publish a new version of a function
- `--fizzlambda-list`: list all functions with their versions, aliases, and trigger counts
- `--fizzlambda-invoke <name> --payload <json>`: synchronously invoke a function with a JSON payload
- `--fizzlambda-invoke-async <name> --payload <json>`: asynchronously invoke a function
- `--fizzlambda-logs <name>`: stream function invocation logs
- `--fizzlambda-metrics <name>`: display function invocation metrics (duration, memory, cold starts, errors, throttles)
- `--fizzlambda-alias-create <function> <alias> --version <n>`: create an alias pointing to a version
- `--fizzlambda-alias-update <function> <alias> --version <n> --weight <0.0-1.0>`: update alias routing
- `--fizzlambda-alias-list <function>`: list all aliases for a function
- `--fizzlambda-trigger-create <function> --type <http|timer|queue|event_bus> --config <json>`: create an event trigger
- `--fizzlambda-trigger-list <function>`: list all triggers for a function
- `--fizzlambda-trigger-enable <trigger_id>`: enable a trigger
- `--fizzlambda-trigger-disable <trigger_id>`: disable a trigger
- `--fizzlambda-layer-create <name> --runtime <runtime> --content <path>`: create a new layer
- `--fizzlambda-layer-list`: list all layers with versions and compatible runtimes
- `--fizzlambda-layer-publish <name>`: publish a new layer version
- `--fizzlambda-queue-list`: list all FizzLambda queues (including DLQs) with message counts
- `--fizzlambda-queue-receive <queue>`: receive and display messages from a queue
- `--fizzlambda-queue-replay <queue> <message_id>`: replay a failed message from a DLQ
- `--fizzlambda-queue-purge <queue>`: purge all messages from a queue (requires FizzApproval)
- `--fizzlambda-warm-pool`: display warm pool status (environments per function, hit rate, evictions)
- `--fizzlambda-concurrency`: display concurrency utilization (reserved, provisioned, on-demand, throttled)
- `--fizzlambda-cold-starts`: display cold start metrics (latency distribution, snapshot hit rate, pre-warm accuracy)
- `--fizzlambda-emergency-deploy`: bypass cognitive load gating for emergency function deployments

### Why This Is Necessary

The Enterprise FizzBuzz Platform has containerized its 116 infrastructure modules. Containers run continuously. They are provisioned for capacity that may or may not arrive. When capacity is insufficient, they scale -- but scaling containers is measured in seconds, not milliseconds. When capacity is excessive, they idle -- but idle containers still consume memory, hold cgroup allocations, occupy network interfaces, and maintain overlay filesystem layers.

FizzBuzz evaluation is a stateless, event-driven computation. A number enters. A rule is applied. An output exits. No state persists. No connection is maintained. No long-running process is required. This is the canonical serverless workload: short-lived, stateless, event-driven, embarrassingly parallel. Running it in always-on containers is architecturally equivalent to renting a warehouse to store a single letter: the infrastructure exists for a purpose that does not require the infrastructure.

Serverless computing is not a replacement for containers. It is the natural complement. Containers serve the platform's long-running stateful workloads: the database replication engine, the event sourcing journal, the Paxos consensus cluster, the containerd daemon. Functions serve the platform's short-lived stateless workloads: FizzBuzz evaluation, cache invalidation, audit logging, report generation, event processing. The container runtime provides isolation, resource limits, and packaging. The function runtime provides lifecycle management, auto-scaling, event routing, and scale-to-zero.

The platform built the container engine in Round 16 and containerized the platform in Round 17. But containerization without serverless is like building an office building with only permanent desks: every worker gets a desk, and every desk is occupied whether the worker is present or not. Serverless adds hot-desking: workers arrive, use a desk, and leave. The desk is available for the next worker. No one owns a desk. No desk sits empty. The platform evaluates FizzBuzz once, infrequently, on demand. It does not need 47 pods standing by to evaluate FizzBuzz. It needs one function, invoked on demand, scaled to zero when idle, scaled to thousands when the enterprise's FizzBuzz evaluation demand requires it.

AWS, Google Cloud, Azure, Cloudflare, and every major cloud provider offers both containers and functions. The Enterprise FizzBuzz Platform now has containers. It must have functions. FizzLambda provides them.

### Estimated Scale

~4,200 lines of serverless function runtime, broken down as follows:

- ~400 lines of function model (`FunctionDefinition`, `FunctionContext`, `FunctionRegistry` with CRUD, namespace isolation, dependency validation, event emission, optimistic concurrency)
- ~350 lines of function runtime core (`FunctionRuntime`, `InvocationRequest`, `InvocationResponse`, `InvocationRouter` with version resolution, weighted routing, concurrency checks)
- ~450 lines of execution environment manager (`ExecutionEnvironment`, cold start sequence with image resolution/sandbox/cgroup/container/bootstrap, warm invocation path, environment recycling, environment destruction)
- ~350 lines of warm pool manager (`WarmPoolManager`, two-level pool structure, MRU acquisition, idle eviction sweep, provisioned concurrency maintenance, pool capacity limits, warm pool metrics)
- ~300 lines of cold start optimizer (`ColdStartOptimizer`, snapshot capture/restore with process memory and overlay state, predictive pre-warming with time-series analysis, layer caching with LRU, runtime pre-initialization with interpreter forking)
- ~400 lines of event trigger system (`EventTriggerManager`, `TriggerDefinition`, HTTP trigger with request/response mapping, timer trigger with cron/rate scheduling, queue trigger with batching and visibility timeout, event bus trigger with pattern matching and FIFO ordering)
- ~250 lines of auto-scaling engine (`AutoScaler`, scale-to-zero, scale-up with burst concurrency, scale-down via idle eviction, concurrency tracking, throttling for sync and async invocations)
- ~250 lines of function versioning and aliases (`FunctionVersionManager`, immutable version publishing, `FunctionAlias` with weighted routing, `TrafficShiftOrchestrator` for linear/canary/all-at-once deployment, version garbage collection)
- ~300 lines of dead letter queue system (`DeadLetterQueueManager`, `FizzLambdaQueue` with FIFO ordering and visibility timeout, `QueueMessage` with failure attributes, DLQ operations: send/receive/delete/purge/replay, DLQ monitoring and alerting)
- ~200 lines of layer system (`LayerManager`, `FunctionLayer` with versioned content, layer composition via FizzOverlay multi-layer mount, standard platform layers, layer versioning and pinning, layer caching integration)
- ~150 lines of invocation retry manager (`RetryManager`, failure classification, exponential backoff retry scheduling, DLQ routing on exhaustion)
- ~200 lines of resource allocation and cgroup integration (`ResourceAllocator`, cgroup hierarchy, memory/CPU/PID/IO mapping, execution timeout enforcement)
- ~150 lines of function packaging (`FunctionPackager`, `fizzbuzz-lambda-base` image, FizzFile generation, layer integration, inline code packaging, image lifecycle)
- ~200 lines of invocation dispatcher (`InvocationDispatcher`, request validation, concurrency check, environment acquisition, async queue draining)
- ~100 lines of pre-built FizzBuzz evaluation functions (standard, configurable, ML, batch, scheduled, cache invalidation, audit log)
- ~100 lines of middleware integration (`FizzLambdaMiddleware`, response annotation, routing mode selection)
- ~50 lines of cognitive load integration (`FizzLambdaCognitiveLoadGate`)
- ~50 lines of compliance integration (`FizzLambdaComplianceEngine`)
- ~200 lines of CLI integration (30 CLI flags with argument parsing and dispatch)
- ~500 tests covering function lifecycle, invocation routing, warm pool behavior, cold start optimization, trigger delivery, retry exhaustion, DLQ operations, auto-scaling, versioning, alias routing, layer composition, and cgroup resource enforcement

Total: ~4,900 lines of implementation + tests.
