# PLAN.md -- FizzCI: Continuous Integration Pipeline Engine

## Overview

The Enterprise FizzBuzz Platform maintains a version control system (FizzVCS), a deployment pipeline, a container runtime (FizzOCI), a secrets vault (FizzVault), and 19,900+ tests -- yet possesses no automated mechanism to validate correctness before release. Every merge today is an act of faith. FizzCI closes this gap by providing a production-grade continuous integration pipeline engine that parses YAML pipeline definitions, constructs a DAG of stages and jobs, executes them with parallelism within stages, manages artifacts between stages, evaluates conditional execution rules, injects secrets, caches build outputs, and reports status -- all within the platform's middleware architecture.

Architecture reference: GitHub Actions, GitLab CI/CD, Jenkins Pipeline, Tekton Pipelines, Dagger CI.

## File Manifest

| File | Purpose |
|------|---------|
| `enterprise_fizzbuzz/infrastructure/fizzci.py` | Main implementation (~3,500 lines) |
| `tests/test_fizzci.py` | Test suite (~500 tests) |
| `enterprise_fizzbuzz/domain/exceptions/fizzci.py` | Exception hierarchy (EFP-CI00 .. EFP-CI34) |
| `enterprise_fizzbuzz/infrastructure/config/mixins/fizzci.py` | Configuration mixin properties |
| `enterprise_fizzbuzz/infrastructure/features/fizzci_feature.py` | Feature descriptor for auto-wiring |
| `fizzci.py` | Backward-compatibility re-export stub (root level) |

## Exception Hierarchy (EFP-CI00 .. EFP-CI34)

All exceptions inherit from `FizzBuzzError` via `_base`.

| Code | Class | Trigger |
|------|-------|---------|
| EFP-CI00 | `FizzCIError` | Base exception for all CI errors |
| EFP-CI01 | `FizzCIPipelineParseError` | Malformed YAML pipeline definition |
| EFP-CI02 | `FizzCIPipelineNotFoundError` | Referenced pipeline does not exist |
| EFP-CI03 | `FizzCIPipelineValidationError` | Semantic validation failure (e.g., undefined stage reference) |
| EFP-CI04 | `FizzCIDAGCycleError` | Cycle detected in stage/job dependency graph |
| EFP-CI05 | `FizzCIDAGNodeError` | Invalid node reference in DAG |
| EFP-CI06 | `FizzCIStageError` | Stage-level execution failure |
| EFP-CI07 | `FizzCIStageTimeoutError` | Stage exceeded its timeout |
| EFP-CI08 | `FizzCIJobError` | Job-level execution failure |
| EFP-CI09 | `FizzCIJobTimeoutError` | Job exceeded its timeout |
| EFP-CI10 | `FizzCIStepError` | Step-level execution failure |
| EFP-CI11 | `FizzCIStepTimeoutError` | Step exceeded its timeout |
| EFP-CI12 | `FizzCIArtifactError` | Artifact upload/download failure |
| EFP-CI13 | `FizzCIArtifactNotFoundError` | Referenced artifact does not exist |
| EFP-CI14 | `FizzCIArtifactCorruptionError` | Artifact checksum mismatch |
| EFP-CI15 | `FizzCIBuildCacheError` | Build cache read/write failure |
| EFP-CI16 | `FizzCIBuildCacheMissError` | Cache key not found |
| EFP-CI17 | `FizzCIBuildCacheEvictionError` | Eviction failure during LRU cleanup |
| EFP-CI18 | `FizzCISecretInjectionError` | Secret not found or injection failed |
| EFP-CI19 | `FizzCISecretAccessDeniedError` | Caller lacks permission to read secret |
| EFP-CI20 | `FizzCIConditionError` | Conditional expression evaluation failure |
| EFP-CI21 | `FizzCIBranchFilterError` | Branch filter pattern is invalid |
| EFP-CI22 | `FizzCIPathFilterError` | Path filter pattern is invalid |
| EFP-CI23 | `FizzCIManualGateError` | Manual gate approval timeout or rejection |
| EFP-CI24 | `FizzCIMatrixError` | Matrix expansion failure |
| EFP-CI25 | `FizzCIMatrixDimensionError` | Matrix dimension exceeds maximum |
| EFP-CI26 | `FizzCIRetryExhaustedError` | All retry attempts exhausted |
| EFP-CI27 | `FizzCIWebhookError` | Webhook processing failure |
| EFP-CI28 | `FizzCIWebhookAuthError` | Webhook signature verification failed |
| EFP-CI29 | `FizzCITemplateError` | Pipeline template resolution failure |
| EFP-CI30 | `FizzCITemplateNotFoundError` | Referenced template does not exist |
| EFP-CI31 | `FizzCITemplateRecursionError` | Template include cycle detected |
| EFP-CI32 | `FizzCILogStreamError` | Log streaming failure |
| EFP-CI33 | `FizzCIStatusReportError` | Status reporting failure |
| EFP-CI34 | `FizzCIConfigError` | Configuration validation failure |

## Configuration Mixin Properties

The `FizzciConfigMixin` class exposes the following properties from `config.yaml` under the `fizzci:` key:

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `fizzci_enabled` | `bool` | `False` | Whether FizzCI is enabled |
| `fizzci_max_parallel_jobs` | `int` | `4` | Maximum concurrent jobs per stage |
| `fizzci_default_timeout` | `int` | `3600` | Default job timeout in seconds |
| `fizzci_stage_timeout` | `int` | `7200` | Default stage timeout in seconds |
| `fizzci_pipeline_timeout` | `int` | `14400` | Default pipeline timeout in seconds |
| `fizzci_artifact_storage_path` | `str` | `".fizzci/artifacts"` | Artifact storage directory |
| `fizzci_cache_storage_path` | `str` | `".fizzci/cache"` | Build cache directory |
| `fizzci_cache_max_size_mb` | `int` | `1024` | Maximum cache size in MB |
| `fizzci_max_retry_attempts` | `int` | `3` | Default retry attempts for failed jobs |
| `fizzci_retry_backoff_base` | `float` | `2.0` | Exponential backoff base for retries |
| `fizzci_webhook_secret` | `str` | `None` | HMAC secret for webhook signature verification |
| `fizzci_max_matrix_combinations` | `int` | `64` | Maximum expanded matrix jobs |
| `fizzci_max_history_entries` | `int` | `1000` | Maximum pipeline run history entries |
| `fizzci_log_buffer_size` | `int` | `4096` | Per-job log buffer size in lines |
| `fizzci_dashboard_width` | `int` | `120` | ASCII dashboard rendering width |

## CLI Flags (13 flags)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--fizzci` | `store_true` | `False` | Enable FizzCI and show the pipeline dashboard |
| `--fizzci-run` | `str` | `None` | Run a named pipeline (e.g., `--fizzci-run fizzbuzz-ci`) |
| `--fizzci-trigger` | `str` | `None` | Simulate a webhook trigger event (format: `event_type,ref,commit_sha`) |
| `--fizzci-status` | `str` | `None` | Show status of a pipeline run by ID |
| `--fizzci-logs` | `str` | `None` | Stream logs for a job (format: `run_id/job_name`) |
| `--fizzci-artifacts` | `str` | `None` | List or download artifacts (format: `run_id` or `run_id/artifact_name`) |
| `--fizzci-pipelines` | `store_true` | `False` | List all registered pipeline definitions |
| `--fizzci-history` | `store_true` | `False` | Show pipeline run history |
| `--fizzci-cache-clear` | `store_true` | `False` | Clear the build cache |
| `--fizzci-matrix` | `str` | `None` | Preview matrix expansion for a pipeline |
| `--fizzci-dry-run` | `str` | `None` | Parse and validate a pipeline without executing it |
| `--fizzci-retry` | `str` | `None` | Retry a failed pipeline run by ID |
| `--fizzci-template` | `str` | `None` | Show a pipeline template definition |

## Feature Descriptor

`FizzCIFeature` in `enterprise_fizzbuzz/infrastructure/features/fizzci_feature.py`:

- `name = "fizzci"`
- `description = "Continuous integration pipeline engine with DAG execution, matrix builds, artifact passing, and build caching"`
- `middleware_priority = 121`
- `is_enabled()`: Returns `True` if any fizzci flag is active
- `create()`: Imports and calls `create_fizzci_subsystem()` from the main module
- `render()`: Dispatches to the appropriate rendering method based on active flags

## Implementation Phases

### Phase 1: Foundation (~500 lines)

**Scope**: Module docstring, imports, constants, enums, all dataclasses, and event type registration.

**Module docstring**: Describes FizzCI as the platform's continuous integration pipeline engine implementing YAML-driven pipeline definitions, DAG-based stage ordering with Kahn's topological sort, parallel job execution within stages, content-addressable artifact storage, content-addressable build caching with LRU eviction, conditional execution via branch filters and path filters and manual gates, secret injection from FizzVault, matrix build expansion, retry policies with exponential backoff, webhook triggers from FizzVCS, real-time log streaming, pipeline templates and reusable workflows, and ASCII pipeline visualization.

**Imports**: `__future__.annotations`, `base64`, `copy`, `hashlib`, `json`, `logging`, `math`, `os`, `random`, `re`, `struct`, `threading`, `time`, `uuid`, `zlib`, `collections.OrderedDict`, `collections.defaultdict`, `dataclasses.dataclass`, `dataclasses.field`, `datetime.datetime`, `datetime.timedelta`, `datetime.timezone`, `enum.Enum`, `enum.auto`, `typing` (standard set), plus domain exceptions and interfaces (`IMiddleware`, `EventType`, `FizzBuzzResult`, `ProcessingContext`).

**Event types** (registered via `EventType.register()`):
- `FIZZCI_PIPELINE_STARTED`
- `FIZZCI_PIPELINE_COMPLETED`
- `FIZZCI_PIPELINE_FAILED`
- `FIZZCI_STAGE_STARTED`
- `FIZZCI_STAGE_COMPLETED`
- `FIZZCI_JOB_STARTED`
- `FIZZCI_JOB_COMPLETED`
- `FIZZCI_JOB_FAILED`
- `FIZZCI_JOB_RETRIED`
- `FIZZCI_ARTIFACT_UPLOADED`
- `FIZZCI_ARTIFACT_DOWNLOADED`
- `FIZZCI_CACHE_HIT`
- `FIZZCI_CACHE_MISS`
- `FIZZCI_WEBHOOK_RECEIVED`

**Enums**:
- `PipelineStatus`: PENDING, QUEUED, RUNNING, SUCCESS, FAILED, CANCELLED, SKIPPED, TIMED_OUT
- `JobStatus`: PENDING, QUEUED, RUNNING, SUCCESS, FAILED, CANCELLED, SKIPPED, TIMED_OUT, RETRYING
- `StepStatus`: PENDING, RUNNING, SUCCESS, FAILED, SKIPPED, TIMED_OUT
- `StageStatus`: PENDING, RUNNING, SUCCESS, FAILED, CANCELLED, SKIPPED, TIMED_OUT
- `TriggerType`: PUSH, PULL_REQUEST, TAG, SCHEDULE, MANUAL, WEBHOOK, API
- `ConditionType`: BRANCH, PATH, MANUAL_GATE, EXPRESSION, ALWAYS, NEVER
- `ArtifactType`: FILE, DIRECTORY, ARCHIVE
- `RetryStrategy`: FIXED, EXPONENTIAL, LINEAR

**Dataclasses** (all frozen where appropriate):
- `RetryPolicy`: `max_attempts: int`, `strategy: RetryStrategy`, `delay_seconds: float`, `backoff_base: float`, `max_delay_seconds: float`
- `ConditionSpec`: `condition_type: ConditionType`, `pattern: str`, `negate: bool`
- `ArtifactSpec`: `name: str`, `path: str`, `artifact_type: ArtifactType`, `retention_days: int`
- `MatrixConfig`: `parameters: Dict[str, List[Any]]`, `include: List[Dict]`, `exclude: List[Dict]`, `max_combinations: int`
- `SecretRef`: `name: str`, `vault_key: str`, `env_var: str`
- `StepDefinition`: `name: str`, `command: str`, `working_directory: str`, `environment: Dict[str, str]`, `timeout_seconds: int`, `continue_on_error: bool`, `condition: Optional[ConditionSpec]`
- `ServiceDefinition`: `name: str`, `image: str`, `ports: List[int]`, `environment: Dict[str, str]`
- `JobDefinition`: `name: str`, `steps: List[StepDefinition]`, `needs: List[str]`, `matrix: Optional[MatrixConfig]`, `services: List[ServiceDefinition]`, `artifacts_upload: List[ArtifactSpec]`, `artifacts_download: List[str]`, `secrets: List[SecretRef]`, `retry: RetryPolicy`, `timeout_seconds: int`, `condition: Optional[ConditionSpec]`, `environment: Dict[str, str]`, `container: Optional[str]`
- `StageDefinition`: `name: str`, `jobs: List[JobDefinition]`, `needs: List[str]`, `condition: Optional[ConditionSpec]`, `timeout_seconds: int`
- `PipelineDefinition`: `name: str`, `stages: List[StageDefinition]`, `triggers: List[TriggerSpec]`, `environment: Dict[str, str]`, `timeout_seconds: int`, `version: str`
- `TriggerSpec`: `trigger_type: TriggerType`, `branches: List[str]`, `paths: List[str]`, `tags: List[str]`, `cron: Optional[str]`
- `PipelineTemplate`: `name: str`, `description: str`, `parameters: Dict[str, Any]`, `definition: PipelineDefinition`
- `StepResult`: `step: str`, `status: StepStatus`, `exit_code: int`, `output: str`, `duration_seconds: float`, `started_at: datetime`, `finished_at: Optional[datetime]`
- `JobResult`: `job: str`, `status: JobStatus`, `step_results: List[StepResult]`, `attempt: int`, `duration_seconds: float`, `started_at: datetime`, `finished_at: Optional[datetime]`, `matrix_values: Optional[Dict[str, Any]]`
- `StageResult`: `stage: str`, `status: StageStatus`, `job_results: List[JobResult]`, `duration_seconds: float`, `started_at: datetime`, `finished_at: Optional[datetime]`
- `PipelineRun`: `run_id: str`, `pipeline_name: str`, `status: PipelineStatus`, `stage_results: List[StageResult]`, `trigger: TriggerSpec`, `started_at: datetime`, `finished_at: Optional[datetime]`, `duration_seconds: float`, `commit_sha: str`, `branch: str`, `artifacts: Dict[str, bytes]`, `logs: Dict[str, List[str]]`
- `CacheEntry`: `key: str`, `content_hash: str`, `data: bytes`, `size_bytes: int`, `created_at: datetime`, `last_accessed: datetime`, `hit_count: int`
- `WebhookPayload`: `event_type: str`, `ref: str`, `commit_sha: str`, `branch: str`, `author: str`, `message: str`, `timestamp: datetime`, `signature: str`, `paths_changed: List[str]`

**Constants**:
- `FIZZCI_VERSION = "1.0.0"`
- `FIZZCI_DEFAULT_TIMEOUT = 3600`
- `FIZZCI_MAX_PARALLEL_JOBS = 4`
- `FIZZCI_MAX_MATRIX_COMBINATIONS = 64`
- `FIZZCI_CACHE_MAX_SIZE_MB = 1024`
- `FIZZCI_LOG_BUFFER_SIZE = 4096`
- `FIZZCI_DASHBOARD_WIDTH = 120`

### Phase 2: Core Engine (~1,200 lines)

**PipelineParser** (~200 lines):
- `parse(yaml_str: str) -> PipelineDefinition`: Parses a YAML string into a validated `PipelineDefinition`. Handles the full grammar: `name`, `triggers`, `environment`, `stages` (each with `jobs`, `needs`, `condition`), `jobs` (each with `steps`, `matrix`, `services`, `artifacts`, `secrets`, `retry`, `timeout`, `condition`, `container`), `steps` (each with `name`, `run`, `working-directory`, `env`, `timeout-minutes`, `continue-on-error`, `if`).
- `_parse_triggers(data: Dict) -> List[TriggerSpec]`
- `_parse_stages(data: Dict) -> List[StageDefinition]`
- `_parse_jobs(data: Dict) -> List[JobDefinition]`
- `_parse_steps(data: List) -> List[StepDefinition]`
- `_parse_matrix(data: Dict) -> MatrixConfig`
- `_parse_retry(data: Dict) -> RetryPolicy`
- `_parse_condition(data: Any) -> ConditionSpec`
- `_parse_artifacts(data: Dict) -> List[ArtifactSpec]`
- `_parse_secrets(data: List) -> List[SecretRef]`
- `validate(definition: PipelineDefinition) -> List[str]`: Semantic validation -- checks for undefined stage references in `needs`, circular dependencies, duplicate names, missing required fields, matrix dimension limits.

**DAGBuilder** (~150 lines):
- `build(stages: List[StageDefinition]) -> List[List[StageDefinition]]`: Constructs a directed acyclic graph from stage `needs` declarations and returns a topologically sorted list of execution tiers (stages that can run in parallel within the same tier).
- Uses Kahn's algorithm for topological sorting, consistent with the existing IoC container's cycle detection.
- `_build_adjacency(stages) -> Dict[str, Set[str]]`
- `_compute_in_degrees(adjacency) -> Dict[str, int]`
- `_topological_sort(adjacency, in_degrees) -> List[str]`: Raises `FizzCIDAGCycleError` if a cycle is detected.
- `_tier_assignment(sorted_nodes, adjacency) -> List[List[str]]`: Groups nodes into execution tiers such that all dependencies of a tier are in earlier tiers.
- `build_job_dag(jobs: List[JobDefinition]) -> List[List[JobDefinition]]`: Same logic but for job-level `needs` within a stage.

**MatrixExpander** (~120 lines):
- `expand(job: JobDefinition) -> List[JobDefinition]`: Takes a job with a `MatrixConfig` and expands it into concrete jobs, one per parameter combination. Applies `include` additions and `exclude` removals. Each expanded job's name is suffixed with the parameter values (e.g., `test (python=3.11, os=linux)`).
- `_cartesian_product(parameters: Dict[str, List]) -> List[Dict[str, Any]]`
- `_apply_includes(combinations, includes) -> List[Dict]`
- `_apply_excludes(combinations, excludes) -> List[Dict]`
- Raises `FizzCIMatrixDimensionError` if total combinations exceed `max_combinations`.

**ConditionalEvaluator** (~130 lines):
- `evaluate(condition: ConditionSpec, context: Dict) -> bool`: Evaluates whether a stage/job/step should execute given the current pipeline context (branch, changed paths, manual approval status).
- `_evaluate_branch(pattern: str, branch: str) -> bool`: Glob-style branch matching.
- `_evaluate_path(pattern: str, changed_paths: List[str]) -> bool`: Glob-style path matching.
- `_evaluate_manual_gate(gate_name: str, approvals: Dict) -> bool`: Checks approval status.
- `_evaluate_expression(expr: str, context: Dict) -> bool`: Simple expression evaluator for `${{ }}` syntax supporting `success()`, `failure()`, `always()`, `cancelled()`, variable references, boolean operators.
- `_evaluate_always() -> bool`: Always returns True.
- `_evaluate_never() -> bool`: Always returns False.
- Handles negation via `ConditionSpec.negate`.

**ArtifactManager** (~150 lines):
- Content-addressable storage: artifacts are stored by SHA-256 hash of their contents.
- `upload(run_id: str, artifact: ArtifactSpec, data: bytes) -> str`: Stores artifact data, returns content hash.
- `download(run_id: str, artifact_name: str) -> bytes`: Retrieves artifact by name, verifies integrity.
- `list_artifacts(run_id: str) -> List[Dict]`: Lists all artifacts for a run with metadata.
- `_compute_hash(data: bytes) -> str`: SHA-256 content hash.
- `_store: Dict[str, Dict[str, Tuple[str, bytes, ArtifactSpec]]]`: In-memory storage indexed by run_id then artifact name.
- Raises `FizzCIArtifactNotFoundError` on missing artifacts, `FizzCIArtifactCorruptionError` on hash mismatch.

**BuildCache** (~180 lines):
- Content-addressable build cache with LRU eviction.
- `get(key: str) -> Optional[bytes]`: Retrieves cached data by key, updates access time and hit count. Returns `None` on miss.
- `put(key: str, data: bytes) -> str`: Stores data, returns content hash. Triggers eviction if cache exceeds `max_size_mb`.
- `invalidate(key: str) -> bool`: Removes a specific cache entry.
- `clear() -> int`: Clears entire cache, returns number of entries removed.
- `stats() -> Dict`: Returns hit rate, total size, entry count, eviction count.
- `_evict_lru() -> None`: Evicts least-recently-used entries until cache is within size limits.
- `_compute_cache_key(inputs: Dict) -> str`: Computes deterministic cache key from a dictionary of inputs using sorted-key JSON serialization and SHA-256.
- `_entries: OrderedDict[str, CacheEntry]`: LRU-ordered storage.
- `_total_size_bytes: int`, `_hit_count: int`, `_miss_count: int`, `_eviction_count: int`

**SecretInjector** (~100 lines):
- `inject(secrets: List[SecretRef], environment: Dict[str, str]) -> Dict[str, str]`: Resolves secret references from the platform's FizzVault (or simulated vault) and injects them into the job environment.
- `_resolve_from_vault(vault_key: str) -> str`: Attempts to import and call FizzVault. If unavailable, falls back to environment variables with `FIZZCI_SECRET_` prefix.
- `_mask_in_logs(value: str) -> str`: Returns a masked version for log output (`***`).
- `_masked_values: Set[str]`: Tracks all secret values for log masking.
- Raises `FizzCISecretInjectionError` if a required secret cannot be resolved, `FizzCISecretAccessDeniedError` if access policy denies it.

**LogStreamer** (~120 lines):
- Real-time buffered log output per job.
- `LogBuffer`: Ring buffer of configurable size per job.
  - `append(line: str)`: Adds a line, evicts oldest if buffer full.
  - `get_lines(offset: int = 0) -> List[str]`: Returns lines from offset.
  - `get_all() -> List[str]`: Returns all buffered lines.
  - `size() -> int`: Current line count.
- `LogStreamer`:
  - `create_buffer(job_id: str) -> LogBuffer`: Creates a new log buffer for a job.
  - `write(job_id: str, line: str)`: Writes a line to the job's buffer with timestamp prefix.
  - `read(job_id: str, offset: int = 0) -> List[str]`: Reads lines from offset.
  - `read_all(job_id: str) -> List[str]`: Reads all lines.
  - `format_output(job_id: str) -> str`: Formats the log buffer for display with ANSI-free timestamps.
  - `_buffers: Dict[str, LogBuffer]`

### Phase 3: Execution (~1,200 lines)

**StepExecutor** (~120 lines):
- `execute(step: StepDefinition, environment: Dict[str, str], log_streamer: LogStreamer, job_id: str) -> StepResult`: Executes a single step by simulating command execution. Captures output, measures duration, handles timeouts and `continue_on_error`.
- `_simulate_command(command: str, env: Dict) -> Tuple[int, str]`: Simulates command execution. For known FizzBuzz commands (e.g., `python -m pytest`, `python -m enterprise_fizzbuzz`), produces realistic output. For unknown commands, produces a generic success output.
- `_check_timeout(started: datetime, timeout: int)`: Raises `FizzCIStepTimeoutError` if exceeded.

**JobRunner** (~250 lines):
- `run(job: JobDefinition, environment: Dict[str, str], artifact_manager: ArtifactManager, secret_injector: SecretInjector, build_cache: BuildCache, log_streamer: LogStreamer, run_id: str) -> JobResult`: Executes a job's steps sequentially.
  1. Injects secrets into environment.
  2. Downloads required artifacts from previous stages.
  3. Checks build cache for cache hit.
  4. Executes each step via `StepExecutor`.
  5. Uploads output artifacts.
  6. Updates build cache on success.
  7. Handles retry policy on failure: re-executes the entire job up to `retry.max_attempts` with the configured backoff strategy.
- `_compute_job_cache_key(job: JobDefinition, env: Dict) -> str`
- `_apply_retry_delay(attempt: int, policy: RetryPolicy) -> float`: Computes delay based on strategy (fixed, exponential, linear).
- `_should_retry(result: JobResult, policy: RetryPolicy) -> bool`

**StageExecutor** (~200 lines):
- `execute(stage: StageDefinition, environment: Dict, artifact_manager: ArtifactManager, secret_injector: SecretInjector, build_cache: BuildCache, log_streamer: LogStreamer, run_id: str) -> StageResult`: Executes all jobs within a stage. Jobs without mutual `needs` dependencies run in parallel (simulated via threading). Jobs are grouped into tiers via `DAGBuilder.build_job_dag()`.
- `_execute_tier(jobs: List[JobDefinition], ...) -> List[JobResult]`: Runs a tier of independent jobs in parallel using `threading.Thread`.
- `_check_stage_timeout(started: datetime, timeout: int)`
- Handles `fail-fast` semantics: if any job in a tier fails and the stage is not configured to `continue-on-error`, remaining tiers are cancelled.

**PipelineExecutor** (~300 lines):
- `execute(definition: PipelineDefinition, trigger: TriggerSpec, context: Dict) -> PipelineRun`: Top-level orchestrator.
  1. Assigns a `run_id` (UUID).
  2. Builds the stage DAG via `DAGBuilder.build()`.
  3. Evaluates pipeline-level conditions.
  4. Iterates through stage tiers:
     a. For each tier, evaluates stage-level conditions.
     b. Expands matrix jobs via `MatrixExpander`.
     c. Delegates to `StageExecutor.execute()`.
     d. Collects results.
  5. Computes final pipeline status from stage results.
  6. Records in `PipelineHistory`.
  7. Fires events via `EventType`.
- `dry_run(definition: PipelineDefinition) -> Dict`: Validates and returns the execution plan without running.
- `cancel(run_id: str) -> bool`: Cancels a running pipeline.
- `retry(run_id: str) -> PipelineRun`: Re-executes a failed pipeline from the first failed stage.

**WebhookTriggerHandler** (~150 lines):
- `handle(payload: WebhookPayload) -> Optional[PipelineRun]`: Processes an incoming webhook from FizzVCS.
  1. Verifies HMAC-SHA256 signature.
  2. Matches event type and ref against registered pipeline triggers.
  3. Evaluates branch and path filters.
  4. If matched, constructs a `TriggerSpec` and invokes `PipelineExecutor.execute()`.
- `register_pipeline(definition: PipelineDefinition)`: Registers a pipeline for webhook matching.
- `_verify_signature(payload: str, signature: str, secret: str) -> bool`: HMAC-SHA256 verification.
- `_match_trigger(trigger: TriggerSpec, payload: WebhookPayload) -> bool`
- `_match_branch_pattern(pattern: str, branch: str) -> bool`: Supports glob patterns (`main`, `release/*`, `feature/**`).
- `_match_path_pattern(pattern: str, paths: List[str]) -> bool`: Supports glob patterns.

**StatusReporter** (~100 lines):
- `report(run: PipelineRun) -> str`: Generates a human-readable status report.
- `summary(run: PipelineRun) -> Dict`: Returns structured status summary.
- `_format_duration(seconds: float) -> str`: Formats duration as `1m 23s`.
- `_format_status_badge(status: PipelineStatus) -> str`: Returns ASCII status badge (`[PASS]`, `[FAIL]`, `[SKIP]`, etc.).
- `_stage_summary(result: StageResult) -> str`
- `_job_summary(result: JobResult) -> str`

**PipelineHistory** (~100 lines):
- In-memory storage of pipeline run history with LRU eviction.
- `record(run: PipelineRun)`: Stores a completed run.
- `get(run_id: str) -> Optional[PipelineRun]`: Retrieves by ID.
- `list_runs(pipeline_name: Optional[str] = None, limit: int = 50) -> List[PipelineRun]`: Lists runs, optionally filtered by pipeline name.
- `stats() -> Dict`: Returns aggregate statistics (total runs, success rate, average duration, most-failed stage).
- `_runs: OrderedDict[str, PipelineRun]`
- `_max_entries: int`

**PipelineTemplateEngine** (~100 lines):
- `register(template: PipelineTemplate)`: Registers a reusable template.
- `resolve(name: str, parameters: Dict[str, Any]) -> PipelineDefinition`: Resolves a template by name, substituting parameters into the definition.
- `list_templates() -> List[PipelineTemplate]`
- `_templates: Dict[str, PipelineTemplate]`
- `_substitute(definition: PipelineDefinition, params: Dict) -> PipelineDefinition`: Deep-copies the definition and substitutes `${{ parameters.X }}` placeholders.
- Raises `FizzCITemplateNotFoundError` on unknown template, `FizzCITemplateRecursionError` if template references form a cycle.

### Phase 4: Integration (~600 lines)

**PipelineVisualizer** (~180 lines):
- `render_dag(definition: PipelineDefinition) -> str`: Renders the pipeline's stage DAG as an ASCII diagram.
- `render_run(run: PipelineRun) -> str`: Renders a completed run with status indicators.
- `_node_box(name: str, status: Optional[str] = None, width: int = 20) -> List[str]`: Draws a single node box.
- `_connect_tiers(tiers: List[List[str]], arrows: List[Tuple[str, str]]) -> str`: Connects tier nodes with ASCII arrows.
- `_status_indicator(status) -> str`: Maps status to symbol (checkmark, cross, dash, spinner).
- Output format example:
  ```
  +----------------+
  |  build [PASS]  |
  +-------+--------+
          |
     +----+----+
     |         |
  +--+------+  +--+------+
  | test-py |  | test-js |
  |  [PASS] |  |  [PASS] |
  +----+----+  +----+----+
       |            |
       +-----+------+
             |
  +----------+----------+
  |    deploy [PASS]    |
  +---------------------+
  ```

**FizzCIDashboard** (~150 lines):
- `render(executor: PipelineExecutor, history: PipelineHistory, width: int = 120) -> str`: Renders a comprehensive ASCII dashboard.
- Sections:
  - Header: FizzCI version, uptime, registered pipelines count.
  - Recent Runs: Table of last 10 runs with pipeline name, status, duration, commit SHA.
  - Cache Stats: Hit rate, total size, entry count.
  - Active Pipelines: Currently running pipelines with progress bars.
  - Registered Pipelines: List of all pipeline definitions with trigger summaries.
- `_render_header(width) -> str`
- `_render_recent_runs(history, width) -> str`
- `_render_cache_stats(cache, width) -> str`
- `_render_active(executor, width) -> str`
- `_render_pipelines(executor, width) -> str`
- `_progress_bar(current, total, width) -> str`

**FizzCIMiddleware** (~100 lines):
- Implements `IMiddleware` interface.
- `process(number: int, result: FizzBuzzResult, context: ProcessingContext) -> FizzBuzzResult`: Enriches the result with CI metadata if a pipeline is running. Fires CI-related events through the event bus.
- `render_dashboard() -> str`: Delegates to `FizzCIDashboard.render()`.
- `render_status(run_id: str) -> str`: Delegates to `StatusReporter.report()`.
- `render_logs(specifier: str) -> str`: Parses `run_id/job_name` and returns formatted logs.
- `render_artifacts(specifier: str) -> str`: Lists or shows artifact details.
- `render_pipelines() -> str`: Lists registered pipelines.
- `render_history() -> str`: Delegates to history.
- `render_matrix_preview(pipeline_name: str) -> str`: Shows expanded matrix.
- `render_dry_run(pipeline_name: str) -> str`: Shows validation result.
- `render_run_result(pipeline_name: str) -> str`: Runs and returns result.
- `render_trigger_result(specifier: str) -> str`: Simulates webhook.
- `render_retry_result(run_id: str) -> str`: Retries and returns result.
- `render_template(name: str) -> str`: Shows template definition.
- `render_cache_clear() -> str`: Clears cache and returns summary.

**create_fizzci_subsystem() factory** (~70 lines):
- Instantiates and wires all components:
  1. `ArtifactManager`
  2. `BuildCache` (with configured max size)
  3. `SecretInjector`
  4. `LogStreamer` (with configured buffer size)
  5. `DAGBuilder`
  6. `MatrixExpander`
  7. `ConditionalEvaluator`
  8. `PipelineParser`
  9. `StepExecutor`
  10. `JobRunner`
  11. `StageExecutor`
  12. `PipelineExecutor`
  13. `WebhookTriggerHandler`
  14. `StatusReporter`
  15. `PipelineHistory`
  16. `PipelineTemplateEngine`
  17. `PipelineVisualizer`
  18. `FizzCIDashboard`
  19. `FizzCIMiddleware`
- Registers two default pipeline definitions:
  - `fizzbuzz-ci`: lint stage -> test stage (with matrix: python=[3.10, 3.11, 3.12]) -> build stage
  - `fizzbuzz-deploy`: build stage -> staging deploy stage (with manual gate) -> production deploy stage (with manual gate)
- Registers two default pipeline templates:
  - `python-library`: Parameterized CI template for Python libraries
  - `deploy-service`: Parameterized deploy template with environment promotion
- Returns `(pipeline_executor, middleware)`

**Default Pipeline Definitions** (embedded YAML strings ~100 lines):
- `FIZZBUZZ_CI_PIPELINE`: A complete CI pipeline demonstrating all features.
- `FIZZBUZZ_DEPLOY_PIPELINE`: A deployment pipeline demonstrating manual gates and conditional execution.

## Backward-Compatibility Stub

`fizzci.py` at repo root:

```python
"""Backward-compatibility re-export stub for FizzCI."""
from enterprise_fizzbuzz.infrastructure.fizzci import *  # noqa: F401,F403
```

## Test Plan (~500 tests)

All tests in `tests/test_fizzci.py`. Uses `pytest` with per-file fixtures. No `conftest.py`.

### Test Organization

| Test Class | Count | Component |
|------------|-------|-----------|
| `TestPipelineStatus` | 10 | Enum transitions and properties |
| `TestJobStatus` | 10 | Enum transitions and properties |
| `TestStepStatus` | 8 | Enum transitions and properties |
| `TestStageStatus` | 8 | Enum transitions and properties |
| `TestTriggerType` | 7 | Trigger type enum completeness |
| `TestConditionType` | 6 | Condition type enum completeness |
| `TestRetryPolicy` | 10 | Retry policy dataclass validation |
| `TestMatrixConfig` | 8 | Matrix config dataclass validation |
| `TestArtifactSpec` | 8 | Artifact spec dataclass |
| `TestStepDefinition` | 10 | Step definition dataclass |
| `TestJobDefinition` | 12 | Job definition dataclass |
| `TestStageDefinition` | 10 | Stage definition dataclass |
| `TestPipelineDefinition` | 10 | Pipeline definition dataclass |
| `TestPipelineParser` | 35 | YAML parsing, validation, error cases |
| `TestDAGBuilder` | 25 | Topological sort, cycle detection, tier assignment |
| `TestMatrixExpander` | 20 | Cartesian product, include/exclude, dimension limits |
| `TestConditionalEvaluator` | 30 | Branch/path/gate/expression evaluation, negation |
| `TestArtifactManager` | 25 | Upload, download, integrity, not-found errors |
| `TestBuildCache` | 30 | Get, put, LRU eviction, stats, clear, size limits |
| `TestSecretInjector` | 15 | Injection, masking, vault fallback, access errors |
| `TestLogStreamer` | 15 | Buffer, append, read, overflow, format |
| `TestStepExecutor` | 20 | Step execution, timeout, continue-on-error |
| `TestJobRunner` | 30 | Job execution, retry, artifacts, secrets, cache |
| `TestStageExecutor` | 25 | Parallel jobs, fail-fast, timeout, conditions |
| `TestPipelineExecutor` | 30 | Full pipeline execution, dry-run, cancel, retry |
| `TestWebhookTriggerHandler` | 20 | Signature verification, matching, triggering |
| `TestStatusReporter` | 15 | Status report formatting, badges, durations |
| `TestPipelineHistory` | 15 | Record, get, list, stats, LRU eviction |
| `TestPipelineTemplateEngine` | 15 | Register, resolve, substitution, recursion detection |
| `TestPipelineVisualizer` | 15 | DAG rendering, run rendering, box drawing |
| `TestFizzCIDashboard` | 10 | Dashboard rendering, sections, formatting |
| `TestFizzCIMiddleware` | 15 | IMiddleware contract, rendering delegation |
| `TestCreateFizzCISubsystem` | 8 | Factory function, default pipelines, wiring |
| `TestDefaultPipelines` | 8 | Default pipeline definitions parse and validate |
| **Total** | **~503** | |

### Key Test Patterns

- **DAG cycle detection**: Construct graphs with known cycles, verify `FizzCIDAGCycleError` is raised with the cycle path.
- **Matrix expansion**: Verify Cartesian product correctness with multi-dimensional matrices, include/exclude filtering, and dimension limits.
- **Retry policies**: Verify exponential backoff timing, attempt counting, and exhaustion.
- **Build cache LRU**: Insert entries exceeding max size, verify oldest are evicted, verify access order updates.
- **Artifact integrity**: Upload artifacts, corrupt stored data, verify `FizzCIArtifactCorruptionError` on download.
- **Webhook signature**: Verify HMAC-SHA256 signatures with known test vectors, verify rejection of invalid signatures.
- **Conditional evaluation**: Test branch globs, path globs, expression parsing, negation, always/never.
- **Pipeline execution end-to-end**: Parse a YAML pipeline, execute it, verify all stages/jobs/steps produce expected results.
- **Template substitution**: Register templates with parameters, resolve with values, verify substitution in all nested fields.
- **Log streaming**: Write lines from multiple concurrent jobs, verify isolation and ordering.

### Fixture Strategy

- `@pytest.fixture` for `pipeline_parser`, `dag_builder`, `matrix_expander`, `conditional_evaluator`, `artifact_manager`, `build_cache`, `secret_injector`, `log_streamer`, `step_executor`, `job_runner`, `stage_executor`, `pipeline_executor`, `webhook_handler`, `status_reporter`, `pipeline_history`, `template_engine`, `visualizer`, `dashboard`, `middleware`.
- `@pytest.fixture` for `sample_pipeline_yaml`: A complete YAML pipeline definition used across multiple test classes.
- `@pytest.fixture` for `sample_pipeline_definition`: Pre-parsed `PipelineDefinition` object.
- `@pytest.fixture` for `sample_webhook_payload`: A valid webhook payload with correct HMAC signature.
- Singleton reset via `_SingletonMeta.reset()` where applicable.

## Documentation Updates

After implementation, update the following files:
- `README.md`: Add FizzCI to the subsystem overview table.
- `FEATURES.md`: Add FizzCI feature description.
- `SUBSYSTEMS.md`: Add FizzCI subsystem entry with component list.
- `CLI_REFERENCE.md`: Add all 13 CLI flags with descriptions and examples.
- `CHANGELOG.md`: Add FizzCI entry under the next version.
- `CLAUDE.md`: Update infrastructure module count, CLI flag count, test count, and line count.
- `config.yaml`: Add `fizzci:` section with all configuration defaults.

## Implementation Order

The implementation agent should proceed in this exact order:

1. **Exceptions file** (`enterprise_fizzbuzz/domain/exceptions/fizzci.py`) -- 35 exception classes.
2. **Config mixin** (`enterprise_fizzbuzz/infrastructure/config/mixins/fizzci.py`) -- 16 properties.
3. **Feature descriptor** (`enterprise_fizzbuzz/infrastructure/features/fizzci_feature.py`) -- feature auto-wiring.
4. **Main module Phase 1** (`enterprise_fizzbuzz/infrastructure/fizzci.py`) -- Foundation: docstring, imports, constants, enums, dataclasses (~500 lines).
5. **Main module Phase 2** -- Core engine classes appended to fizzci.py (~1,200 lines).
6. **Main module Phase 3** -- Execution classes appended to fizzci.py (~1,200 lines).
7. **Main module Phase 4** -- Integration classes, factory, default pipelines appended to fizzci.py (~600 lines).
8. **Backward-compat stub** (`fizzci.py` at repo root).
9. **Tests** (`tests/test_fizzci.py`) -- ~500 tests covering all components.
10. **Documentation updates** -- README, FEATURES, SUBSYSTEMS, CLI_REFERENCE, CHANGELOG.

## Estimated Totals

| Artifact | Lines |
|----------|-------|
| `fizzci.py` (main module) | ~3,500 |
| `test_fizzci.py` | ~4,500 |
| Exception file | ~350 |
| Config mixin | ~160 |
| Feature descriptor | ~110 |
| Backward-compat stub | ~3 |
| **Total new code** | **~8,620** |
