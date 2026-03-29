# PLAN: FizzRunbook -- Runbook Automation Engine

## Overview

FizzRunbook provides automated operational remediation for the Enterprise FizzBuzz Platform. When a divisibility computation pipeline degrades, operators should not be manually executing recovery procedures from a wiki page. FizzRunbook codifies runbooks as versioned, multi-step execution plans with support for manual approval gates, automated remediation steps, conditional branching, and rollback on failure.

Architecture references: PagerDuty Runbook Automation, Rundeck, AWS Systems Manager (SSM) Automation Documents.

## Module Location

`enterprise_fizzbuzz/infrastructure/fizzrunbook.py`

## Data Model

### Enums

| Enum | Values | Purpose |
|------|--------|---------|
| `StepType` | `MANUAL`, `AUTOMATED`, `CONDITIONAL`, `NOTIFICATION` | Classifies what kind of action a step performs |
| `ExecutionState` | `PENDING`, `RUNNING`, `AWAITING_APPROVAL`, `COMPLETED`, `FAILED`, `ROLLED_BACK` | Lifecycle state of a runbook execution |
| `RunbookStatus` | `DRAFT`, `PUBLISHED`, `DEPRECATED` | Publication lifecycle of a runbook definition |

### Dataclasses

**`RunbookStep`**
- `step_id: str` -- UUID-based identifier (e.g., `STEP-a1b2c3d4`)
- `name: str` -- human-readable step name
- `step_type: StepType` -- classification of the step
- `description: str` -- what this step does
- `timeout_seconds: int` -- maximum duration before the step is considered failed (default 300)
- `on_failure: str` -- one of `"continue"`, `"abort"`, `"rollback"` (default `"abort"`)

**`RunbookDefinition`**
- `runbook_id: str` -- UUID-based identifier (e.g., `RB-a1b2c3d4`)
- `name: str`
- `description: str`
- `status: RunbookStatus` -- defaults to `DRAFT`
- `steps: List[RunbookStep]` -- ordered list of steps
- `version: int` -- incremented on publish (starts at 0 in draft, becomes 1 on first publish)
- `created_at: Optional[datetime]`
- `updated_at: Optional[datetime]`

**`ExecutionRecord`**
- `execution_id: str` -- UUID-based identifier (e.g., `EXEC-a1b2c3d4`)
- `runbook_id: str` -- which runbook was executed
- `state: ExecutionState` -- current execution state
- `current_step_index: int` -- index into the runbook's step list
- `step_results: List[dict]` -- per-step result records with keys: `step_id`, `status`, `started_at`, `completed_at`, `error`
- `started_at: Optional[datetime]`
- `completed_at: Optional[datetime]`

**`FizzRunbookConfig`**
- `dashboard_width: int` -- width for dashboard rendering (default 72)

### Constants

- `FIZZRUNBOOK_VERSION = "1.0.0"`
- `DEFAULT_DASHBOARD_WIDTH = 72`
- `MIDDLEWARE_PRIORITY = 211`

## Classes

### `RunbookEngine`

Central engine. Stores runbooks and executions in `OrderedDict` instances (in-memory).

**Runbook lifecycle methods:**

| Method | Signature | Behavior |
|--------|-----------|----------|
| `create_runbook` | `(name: str, description: str) -> RunbookDefinition` | Creates a DRAFT runbook with no steps |
| `add_step` | `(runbook_id: str, name: str, step_type: StepType, description: str = "", timeout_seconds: int = 300, on_failure: str = "abort") -> RunbookStep` | Appends a step to a DRAFT runbook. Raises `FizzRunbookStateError` if runbook is PUBLISHED/DEPRECATED |
| `publish` | `(runbook_id: str) -> RunbookDefinition` | Transitions DRAFT -> PUBLISHED, increments version. Raises `FizzRunbookStateError` if not DRAFT or has zero steps |
| `deprecate` | `(runbook_id: str) -> RunbookDefinition` | Transitions PUBLISHED -> DEPRECATED |
| `get_runbook` | `(runbook_id: str) -> RunbookDefinition` | Raises `FizzRunbookNotFoundError` if missing |
| `list_runbooks` | `(status: Optional[RunbookStatus] = None) -> List[RunbookDefinition]` | Optionally filtered by status |

**Execution methods:**

| Method | Signature | Behavior |
|--------|-----------|----------|
| `execute` | `(runbook_id: str) -> ExecutionRecord` | Only PUBLISHED runbooks. Creates PENDING execution, transitions to RUNNING, auto-advances through AUTOMATED steps. Pauses at MANUAL steps (state -> AWAITING_APPROVAL). NOTIFICATION steps log and auto-advance. CONDITIONAL steps evaluate and auto-advance. On step failure: honor `on_failure` policy |
| `approve_step` | `(execution_id: str) -> ExecutionRecord` | Advances past AWAITING_APPROVAL for MANUAL steps, then continues execution. Raises `FizzRunbookStateError` if not AWAITING_APPROVAL |
| `get_execution` | `(execution_id: str) -> ExecutionRecord` | Raises `FizzRunbookNotFoundError` if missing |
| `list_executions` | `(runbook_id: Optional[str] = None) -> List[ExecutionRecord]` | Optionally filtered by runbook_id |

**Execution advancement logic (`_advance_execution`):**

Private method that iterates steps from `current_step_index` forward:
1. For each step, record `started_at` in step_results
2. AUTOMATED: simulate execution (always succeeds for now), record completed, advance
3. MANUAL: set execution state to AWAITING_APPROVAL, return (caller must `approve_step`)
4. NOTIFICATION: log the notification message, record completed, advance
5. CONDITIONAL: evaluate (always true for now), record completed, advance
6. On failure at any step: check `on_failure`:
   - `"continue"`: record failure, advance to next step
   - `"abort"`: set execution state to FAILED, stop
   - `"rollback"`: set execution state to ROLLED_BACK, stop
7. After all steps complete: set execution state to COMPLETED, record `completed_at`

### `FizzRunbookDashboard`

- `__init__(engine: Optional[RunbookEngine], width: int)`
- `render() -> str`: ASCII dashboard showing version, runbook count, execution summary, recent executions (last 5)

### `FizzRunbookMiddleware(IMiddleware)`

- `get_name() -> "fizzrunbook"`
- `get_priority() -> 211`
- `process(ctx, next_handler)`: delegates to next_handler (passthrough)
- `render_dashboard() -> str`: delegates to dashboard

### `create_fizzrunbook_subsystem(dashboard_width: int = 72) -> Tuple[RunbookEngine, FizzRunbookDashboard, FizzRunbookMiddleware]`

Factory function. Creates engine, seeds a sample runbook ("FizzBuzz Cache Invalidation Procedure" with 4 steps: NOTIFICATION announce, AUTOMATED flush cache, MANUAL verify output, NOTIFICATION complete), publishes it, executes it (will pause at the MANUAL step). Returns the triple.

## Exceptions

File: `enterprise_fizzbuzz/domain/exceptions/fizzrunbook.py`

| Exception | Error Code | Purpose |
|-----------|-----------|---------|
| `FizzRunbookError(FizzBuzzError)` | `EFP-RB00` | Base exception |
| `FizzRunbookNotFoundError(FizzRunbookError)` | `EFP-RB01` | Runbook or execution ID not found |
| `FizzRunbookExecutionError(FizzRunbookError)` | `EFP-RB02` | Execution failed unexpectedly |
| `FizzRunbookStateError(FizzRunbookError)` | `EFP-RB03` | Invalid state transition |

## Supporting Files

### `enterprise_fizzbuzz/infrastructure/config/mixins/fizzrunbook.py`

Config mixin class `FizzrunbookConfigMixin` with properties:
- `fizzrunbook_enabled -> bool` (from `fizzrunbook.enabled`, default `False`)
- `fizzrunbook_dashboard_width -> int` (from `fizzrunbook.dashboard_width`, default `72`)

### `enterprise_fizzbuzz/infrastructure/config/_compose.py`

- Add import: `from .mixins.fizzrunbook import FizzrunbookConfigMixin`
- Add `FizzrunbookConfigMixin` to `ConfigurationManager` class bases (alphabetical insertion)

### `enterprise_fizzbuzz/infrastructure/features/fizzrunbook_feature.py`

Feature descriptor:
- `name = "fizzrunbook"`
- `description = "Runbook automation engine"`
- `middleware_priority = 211`
- `cli_flags = [("--fizzrunbook", {...})]`
- `is_enabled`: checks `args.fizzrunbook`
- `create`: imports and calls `create_fizzrunbook_subsystem`
- `render`: delegates to `middleware.render_dashboard()`

### `fizzrunbook.py` (root stub)

Re-export stub: `from enterprise_fizzbuzz.infrastructure.fizzrunbook import *`

### `enterprise_fizzbuzz/domain/exceptions/__init__.py`

Add fizzrunbook exception imports to the exceptions package.

## Test File

File: `tests/test_fizzrunbook.py`

### Test Classes and Cases

**`TestRunbookStepType`** (4 tests)
- Verify all four StepType enum values exist and have correct string values

**`TestRunbookDefinitionLifecycle`** (8 tests)
- `test_create_runbook`: creates a runbook, asserts DRAFT status, empty steps, version 0
- `test_add_step_to_draft`: adds steps, verifies they appear in definition
- `test_add_step_to_published_raises`: publish then try to add step, expect `FizzRunbookStateError`
- `test_publish_runbook`: publish a runbook with steps, assert PUBLISHED and version 1
- `test_publish_empty_runbook_raises`: try to publish with no steps, expect `FizzRunbookStateError`
- `test_deprecate_runbook`: publish then deprecate, assert DEPRECATED
- `test_get_nonexistent_raises`: `FizzRunbookNotFoundError`
- `test_list_runbooks_filter`: create multiple, filter by status

**`TestRunbookExecution`** (10 tests)
- `test_execute_all_automated`: runbook with only AUTOMATED steps completes immediately
- `test_execute_pauses_at_manual`: runbook with MANUAL step results in AWAITING_APPROVAL
- `test_approve_advances_past_manual`: approve then verify execution continues
- `test_approve_when_not_awaiting_raises`: `FizzRunbookStateError`
- `test_execute_draft_raises`: cannot execute a DRAFT runbook
- `test_execute_notification_step`: NOTIFICATION steps auto-advance
- `test_execute_conditional_step`: CONDITIONAL steps auto-advance
- `test_on_failure_abort`: step failure with abort policy sets FAILED state
- `test_on_failure_continue`: step failure with continue policy advances to next step
- `test_on_failure_rollback`: step failure with rollback policy sets ROLLED_BACK state

**`TestExecutionRecord`** (4 tests)
- `test_step_results_populated`: verify step_results list has entries after execution
- `test_execution_timestamps`: started_at set on execute, completed_at set on completion
- `test_get_execution_nonexistent_raises`: `FizzRunbookNotFoundError`
- `test_list_executions_filter`: filter by runbook_id

**`TestFizzRunbookDashboard`** (3 tests)
- `test_render_contains_header`: dashboard output contains "FizzRunbook Dashboard" and version
- `test_render_shows_counts`: shows runbook and execution counts
- `test_render_no_engine`: renders gracefully with None engine

**`TestFizzRunbookMiddleware`** (3 tests)
- `test_name`: returns `"fizzrunbook"`
- `test_priority`: returns `211`
- `test_process_passthrough`: delegates to next_handler

**`TestFizzRunbookSubsystem`** (3 tests)
- `test_factory_returns_triple`: `create_fizzrunbook_subsystem` returns `(RunbookEngine, FizzRunbookDashboard, FizzRunbookMiddleware)`
- `test_factory_seeds_runbook`: engine has at least one PUBLISHED runbook after creation
- `test_factory_seeds_execution`: engine has at least one execution (paused at MANUAL step)

**Total: 35 tests**

## Implementation Order

1. `enterprise_fizzbuzz/domain/exceptions/fizzrunbook.py` -- exception hierarchy
2. `enterprise_fizzbuzz/domain/exceptions/__init__.py` -- register new exceptions
3. `tests/test_fizzrunbook.py` -- full test suite (TDD: tests first)
4. `enterprise_fizzbuzz/infrastructure/fizzrunbook.py` -- engine, dashboard, middleware, factory
5. `enterprise_fizzbuzz/infrastructure/config/mixins/fizzrunbook.py` -- config mixin
6. `enterprise_fizzbuzz/infrastructure/config/_compose.py` -- wire mixin into ConfigurationManager
7. `enterprise_fizzbuzz/infrastructure/features/fizzrunbook_feature.py` -- feature descriptor
8. `fizzrunbook.py` -- root re-export stub
9. Run `python -m pytest tests/test_fizzrunbook.py -v` -- all 35 tests must pass
