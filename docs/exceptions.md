# Exception Catalog

Enterprise FizzBuzz Platform v1.0.0

## Overview

The Enterprise FizzBuzz Platform defines **86 custom exception classes** in the core domain module and **4 backward-compatibility aliases**, plus **129 additional exceptions** across 6 Round 17 infrastructure modules:

```
enterprise_fizzbuzz/domain/exceptions.py
```

Every exception inherits from `FizzBuzzError`, which itself extends Python's built-in `Exception`. This ensures that a single `except FizzBuzzError` clause can catch any platform-originated failure, from a configuration typo to a blockchain integrity violation to a cache entry dying without a eulogy.

## The FizzBuzzError Base Class

All exceptions carry two fields injected by `FizzBuzzError.__init__`:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `error_code` | `str` | `"EFP-0000"` | Machine-readable error identifier |
| `context` | `dict[str, Any]` | `{}` | Structured metadata about the failure |

The formatted message always begins with the error code in brackets: `[EFP-XXXX] Human-readable message`. This convention is enforced by the base class constructor and cannot be overridden without subverting `super().__init__`.

```python
class FizzBuzzError(Exception):
    def __init__(self, message, *, error_code=None, context=None):
        self.error_code = error_code or "EFP-0000"
        self.context = context or {}
        super().__init__(f"[{self.error_code}] {message}")
```

## Error Code Conventions

Error codes use the prefix `EFP-` followed by a subsystem identifier and a sequence number. The following ranges are in use:

| Code Range | Subsystem |
|------------|-----------|
| `EFP-0000` | Base / unclassified |
| `EFP-1000` | Configuration |
| `EFP-2000` | Rule evaluation |
| `EFP-3000` | Plugin system |
| `EFP-4000` | Middleware pipeline |
| `EFP-5000` | Output formatting |
| `EFP-6000` | Observer / event bus |
| `EFP-7000` | Service lifecycle |
| `EFP-8000` | Range validation |
| `EFP-9000` | ML engine |
| `EFP-A0xx` | Authentication & RBAC |
| `EFP-B000` | Blockchain audit ledger |
| `EFP-CA0x` | Caching layer |
| `EFP-CB0x` | Circuit breaker |
| `EFP-CH0x` | Chaos engineering |
| `EFP-DI0x` | Dependency injection |
| `EFP-ES0x` | Event sourcing / CQRS |
| `EFP-FF0x` | Feature flags |
| `EFP-I00x` | Internationalization |
| `EFP-MG0x` | Database migrations |
| `EFP-RP0x` | Repository / Unit of Work |
| `EFP-SL0x` | SLA monitoring |
| `EFP-T00x` | Distributed tracing (removed -- absorbed into FizzOTel `EFP-OT0x`) |
| `EFP-BOB0` through `EFP-BOB8` | Operator cognitive load (FizzBob) |
| `EFP-APR0` through `EFP-APR7` | Approval workflow (FizzApproval) |
| `EFP-PGR0` through `EFP-PGR7` | Incident paging & escalation (FizzPager) |
| `EFP-IMG00` through `EFP-IMG20` | Container image catalog (FizzImage) |
| `EFP-DPL00` through `EFP-DPL21` | Deployment pipeline (FizzDeploy) |
| `EFP-CMP00` through `EFP-CMP20` | Multi-container orchestration (FizzCompose) |
| `EFP-KV200` through `EFP-KV220` | Container-aware orchestrator (FizzKubeV2) |
| `EFP-CCH00` through `EFP-CCH23` | Container-native chaos engineering (FizzContainerChaos) |
| `EFP-COP00` through `EFP-COP19` | Container observability & diagnostics (FizzContainerOps) |

Numeric ranges (`EFP-1000` through `EFP-9000`) were assigned to the original subsystems. Later additions use alphabetic prefixes to avoid collisions, a decision that was never formally documented but has been consistently followed.

---

## Exception Catalog by Subsystem

### Configuration (`EFP-1000`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `ConfigurationError` | `FizzBuzzError` | `EFP-1000` | The configuration subsystem encountered an invalid state |
| `ConfigurationFileNotFoundError` | `ConfigurationError` | `EFP-1000` | The YAML configuration file cannot be located on disk |
| `ConfigurationValidationError` | `ConfigurationError` | `EFP-1000` | Configuration values failed schema validation |

`ConfigurationFileNotFoundError` and `ConfigurationValidationError` inherit their error code from `ConfigurationError`. The `config_key` context field identifies which configuration key caused the failure. `ConfigurationFileNotFoundError` sets this to the sentinel value `"__file__"`.

### Rule Evaluation (`EFP-2000`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `RuleEvaluationError` | `FizzBuzzError` | `EFP-2000` | A rule failed to evaluate against a given number |
| `RuleConflictError` | `RuleEvaluationError` | `EFP-2000` | Two or more rules produced conflicting results |

Both exceptions carry `rule_name` and `number` in their context. `RuleConflictError` adds a `conflicting_rule` instance attribute identifying the second rule in the conflict.

### Plugin System (`EFP-3000`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `PluginLoadError` | `FizzBuzzError` | `EFP-3000` | A plugin failed to load or register |
| `PluginNotFoundError` | `PluginLoadError` | `EFP-3000` | A requested plugin is not found in the registry |

### Middleware Pipeline (`EFP-4000`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `MiddlewareError` | `FizzBuzzError` | `EFP-4000` | A middleware component failed during pipeline execution |

Context includes `middleware_name` and `phase` (indicating whether the failure occurred during the inbound or outbound pass).

### Output Formatting (`EFP-5000`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `FormatterError` | `FizzBuzzError` | `EFP-5000` | An output formatter encountered an error |

### Observer / Event Bus (`EFP-6000`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `ObserverError` | `FizzBuzzError` | `EFP-6000` | An observer failed to handle an event |

Context includes `observer_name` and `event_type`.

### Service Lifecycle (`EFP-7000`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `ServiceNotInitializedError` | `FizzBuzzError` | `EFP-7000` | The FizzBuzz service was used before initialization |

Takes no constructor arguments. The message helpfully asks whether you forgot to call `FizzBuzzServiceBuilder.build()`.

### Range Validation (`EFP-8000`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `InvalidRangeError` | `FizzBuzzError` | `EFP-8000` | The numeric range for FizzBuzz evaluation is invalid |

Context includes `start` and `end`.

### ML Engine (`EFP-9000`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `ModelConvergenceError` | `FizzBuzzError` | `EFP-9000` | The ML model failed to converge during training |

Raised when the neural network cannot learn modulo arithmetic, a scenario the docstring concedes "should never happen" but which enterprise software must nonetheless be prepared for. Context includes `rule_name` and `final_loss`.

### Authentication & RBAC (`EFP-A0xx`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `AuthenticationError` | `FizzBuzzError` | `EFP-A000` | Authentication failed |
| `InsufficientFizzPrivilegesError` | `FizzBuzzError` | `EFP-A001` | User lacks the required FizzBuzz permissions |
| `NumberClassificationLevelExceededError` | `FizzBuzzError` | `EFP-A002` | A number exceeds the user's classification clearance |
| `TokenValidationError` | `AuthenticationError` | `EFP-A003` | A FizzBuzz authentication token failed validation |

Note that `InsufficientFizzPrivilegesError` and `NumberClassificationLevelExceededError` inherit directly from `FizzBuzzError`, not from `AuthenticationError`. This is an intentional design choice: they represent authorization failures, not authentication failures, and the hierarchy reflects the distinction.

`InsufficientFizzPrivilegesError` carries a `denial_body` attribute containing the complete 47-field access denied response payload. `NumberClassificationLevelExceededError` includes the offending `number`, the user's `clearance_level`, and the `required_level`.

### Blockchain Audit Ledger (`EFP-B000`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `BlockchainIntegrityError` | `FizzBuzzError` | `EFP-B000` | The blockchain audit ledger detected tampering |

Raised when someone has modified a FizzBuzz result, which, as the docstring notes, is "arguably worse" than a distributed enterprise integrity violation. Context includes `block_index`.

### Circuit Breaker (`EFP-CB0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `CircuitOpenError` | `FizzBuzzError` | `EFP-CB00` | A request was rejected because the circuit breaker is open |
| `CircuitBreakerTimeoutError` | `FizzBuzzError` | `EFP-CB01` | A FizzBuzz evaluation exceeded the circuit breaker timeout |
| `DownstreamFizzBuzzDegradationError` | `FizzBuzzError` | `EFP-CB02` | Downstream FizzBuzz evaluation quality has degraded |

`CircuitOpenError` exposes `circuit_name` and `retry_after_ms` as instance attributes and describes the situation as "degraded modulo operations." `CircuitBreakerTimeoutError` adds `timeout_ms` and `elapsed_ms` to its context and observes that "the modulo operator appears to be running slower than expected."

`DownstreamFizzBuzzDegradationError` monitors ML confidence scores and evaluation latency. It is raised when the pipeline is "producing results with insufficient conviction."

### Internationalization (`EFP-I00x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `LocaleError` | `FizzBuzzError` | `EFP-I000` | Base exception for all i18n/l10n errors |
| `LocaleNotFoundError` | `LocaleError` | `EFP-I001` | The requested locale cannot be found on disk |
| `TranslationKeyError` | `LocaleError` | `EFP-I002` | A translation key cannot be resolved in any fallback locale |
| `FizzTranslationParseError` | `LocaleError` | `EFP-I003` | A `.fizztranslation` file contains a syntax error |
| `PluralizationError` | `LocaleError` | `EFP-I004` | The pluralization engine failed to determine a plural form |
| `LocaleChainExhaustedError` | `LocaleError` | `EFP-I005` | The entire locale fallback chain has been exhausted |

**Backward-compatibility aliases:**

| Alias | Canonical Class |
|-------|----------------|
| `LocalizationError` | `LocaleError` |
| `TranslationFileParseError` | `FizzTranslationParseError` |
| `TranslationKeyMissingError` | `TranslationKeyError` |
| `PluralizationRuleError` | `PluralizationError` |

These aliases exist at module scope (line 342-345) to support both naming conventions used across the codebase. They are simple assignments, not subclasses.

### Distributed Tracing (`EFP-T00x`) -- REMOVED

The legacy tracing exception hierarchy (`TracingError`, `SpanNotFoundError`, `TraceNotFoundError`, `TraceAlreadyActiveError`, `SpanLifecycleError`) was removed when the original `tracing.py` module was absorbed into `otel_tracing.py` (FizzOTel). The FizzOTel subsystem uses its own exception hierarchy under `EFP-OT0x` (`OTelError`, `OTelSpanError`, `OTelSamplingError`, `OTelExportError`).

### Event Sourcing / CQRS (`EFP-ES0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `EventStoreError` | `FizzBuzzError` | `EFP-ES00` | Base exception for all event sourcing and CQRS errors |
| `EventSequenceError` | `EventStoreError` | `EFP-ES01` | Events arrived out of sequence in the event store |
| `EventDeserializationError` | `EventStoreError` | `EFP-ES02` | A domain event cannot be deserialized from storage |
| `SnapshotCorruptionError` | `EventStoreError` | `EFP-ES03` | A snapshot failed integrity validation |
| `CommandValidationError` | `EventStoreError` | `EFP-ES04` | A command failed pre-execution validation |
| `CommandHandlerNotFoundError` | `EventStoreError` | `EFP-ES05` | No handler is registered for a given command type |
| `QueryHandlerNotFoundError` | `EventStoreError` | `EFP-ES06` | No handler is registered for a given query type |
| `ProjectionError` | `EventStoreError` | `EFP-ES07` | A read-model projection failed to process an event |
| `TemporalQueryError` | `EventStoreError` | `EFP-ES08` | A point-in-time query cannot be satisfied |
| `EventVersionConflictError` | `EventStoreError` | `EFP-ES09` | An event upcaster encountered an unsupported version |

This is the largest subsystem-specific exception family, with 10 classes covering the full CQRS lifecycle: command dispatch, event persistence, projection updates, temporal queries, and schema evolution. `EventSequenceError` warns that "causality may be compromised." `TemporalQueryError` concedes that "time-travel is harder than it looks."

### Chaos Engineering (`EFP-CH0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `ChaosError` | `FizzBuzzError` | `EFP-CH00` | Base exception for all chaos engineering errors |
| `ChaosInducedFizzBuzzError` | `ChaosError` | `EFP-CH01` | Chaos engineering deliberately corrupted a FizzBuzz result |
| `ChaosExperimentFailedError` | `ChaosError` | `EFP-CH02` | A chaos experiment itself failed to execute |
| `ChaosConfigurationError` | `ChaosError` | `EFP-CH03` | The chaos engineering configuration is invalid |
| `ResultCorruptionDetectedError` | `ChaosError` | `EFP-CH04` | Downstream validation detected chaos-induced corruption |

`ChaosInducedFizzBuzzError` is explicitly "not a bug" per its docstring. Its context includes the `original_output` and `corrupted_output`, and its message closes with "This is intentional. Your system's resilience is being tested. You're welcome."

`ChaosConfigurationError` covers the case where someone "managed to misconfigure the system designed to misconfigure other systems."

### Feature Flags (`EFP-FF0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `FeatureFlagError` | `FizzBuzzError` | `EFP-FF00` | Base exception for the feature flag / progressive rollout subsystem |
| `FlagNotFoundError` | `FeatureFlagError` | `EFP-FF01` | A referenced feature flag does not exist in the store |
| `FlagDependencyCycleError` | `FeatureFlagError` | `EFP-FF02` | The flag dependency graph contains a cycle |
| `FlagLifecycleError` | `FeatureFlagError` | `EFP-FF03` | A flag operation violated the lifecycle state machine |
| `FlagDependencyNotMetError` | `FeatureFlagError` | `EFP-FF04` | A flag's dependency is not satisfied |
| `FlagRolloutError` | `FeatureFlagError` | `EFP-FF05` | The progressive rollout engine encountered an error |
| `FlagTargetingError` | `FeatureFlagError` | `EFP-FF06` | A targeting rule failed to evaluate |

`FlagDependencyCycleError` notes that "Kahn is disappointed" when the topological sort fails. `FlagLifecycleError` directs the user to consult "the lifecycle state diagram (available in the 47-page architecture document)."

### SLA Monitoring (`EFP-SL0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `SLAError` | `FizzBuzzError` | `EFP-SL00` | Base exception for all SLA monitoring and alerting errors |
| `SLOViolationError` | `SLAError` | `EFP-SL01` | A Service Level Objective was violated |
| `ErrorBudgetExhaustedError` | `SLAError` | `EFP-SL02` | The error budget has been fully consumed |
| `AlertEscalationError` | `SLAError` | `EFP-SL03` | An alert escalation failed to proceed |
| `OnCallNotFoundError` | `SLAError` | `EFP-SL04` | The on-call engineer cannot be determined |
| `SLAConfigurationError` | `SLAError` | `EFP-SL05` | The SLA monitoring configuration is invalid |

`ErrorBudgetExhaustedError` declares "zero tolerance for further FizzBuzz failures." `AlertEscalationError` advises manual escalation "by shouting loudly." `OnCallNotFoundError` observes that determining the on-call engineer involves modulo arithmetic, "ironic, given the context."

### Caching Layer (`EFP-CA0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `CacheError` | `FizzBuzzError` | `EFP-CA00` | Base exception for all in-memory caching layer errors |
| `CacheCapacityExceededError` | `CacheError` | `EFP-CA01` | The cache has reached its maximum capacity |
| `CacheCoherenceViolationError` | `CacheError` | `EFP-CA02` | The MESI cache coherence protocol detected an invalid transition |
| `CacheEntryExpiredError` | `CacheError` | `EFP-CA03` | An expired cache entry was accessed |
| `CacheWarmingError` | `CacheError` | `EFP-CA04` | The cache warming process encountered an error |
| `CachePolicyNotFoundError` | `CacheError` | `EFP-CA05` | The requested eviction policy does not exist |
| `CacheInvalidationCascadeError` | `CacheError` | `EFP-CA06` | A cache invalidation cascade spiraled out of control |
| `CacheEulogyCompositionError` | `CacheError` | `EFP-CA07` | The eulogy generator failed to compose a eulogy for an evicted entry |

The caching subsystem has 8 exception classes, the second-largest family after event sourcing. `CacheCoherenceViolationError` enforces MESI protocol compliance "even though we're running in a single Python process." `CacheEulogyCompositionError` is described as "the saddest failure mode in the entire Enterprise FizzBuzz Platform" -- the entry is evicted without ceremony, without remembrance, without a single word spoken in its honor.

`CachePolicyNotFoundError` lists the available eviction policies: `lru`, `lfu`, `fifo`, and `dramatic_random`.

### Database Migrations (`EFP-MG0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `MigrationError` | `FizzBuzzError` | `EFP-MG00` | Base exception for all database migration framework errors |
| `MigrationNotFoundError` | `MigrationError` | `EFP-MG01` | A referenced migration does not exist in the registry |
| `MigrationAlreadyAppliedError` | `MigrationError` | `EFP-MG02` | A migration that has already been applied was applied again |
| `MigrationRollbackError` | `MigrationError` | `EFP-MG03` | A migration rollback failed |
| `MigrationDependencyError` | `MigrationError` | `EFP-MG04` | A migration's dependencies are not satisfied |
| `MigrationConflictError` | `MigrationError` | `EFP-MG05` | Two migrations conflict with each other |
| `SchemaError` | `MigrationError` | `EFP-MG06` | A schema operation failed |
| `SeedDataError` | `MigrationError` | `EFP-MG07` | The seed data generator encountered an error |

These exceptions manage schema migrations for in-memory dicts that vanish when the process exits. `MigrationRollbackError` describes the schema state as "a superposition of applied and not-applied" and observes that "Schrodinger would be proud." `SeedDataError` covers the ouroboros scenario where FizzBuzz runs to populate a FizzBuzz database.

### Dependency Injection (`EFP-DI0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `DependencyInjectionError` | `FizzBuzzError` | `EFP-DI00` | Base exception for all dependency injection container errors |
| `CircularDependencyError` | `DependencyInjectionError` | `EFP-DI01` | The dependency graph contains a cycle |
| `MissingBindingError` | `DependencyInjectionError` | `EFP-DI02` | A requested service has no registered binding |
| `DuplicateBindingError` | `DependencyInjectionError` | `EFP-DI03` | A binding already exists for the given interface |
| `ScopeError` | `DependencyInjectionError` | `EFP-DI04` | A scoped service was resolved outside of an active scope |

`MissingBindingError` notes that "the container cannot conjure services from thin air, despite what the Spring documentation implies." `ScopeError` helpfully suggests changing the lifetime to `SINGLETON` or, "if you want it to live forever with more dignity," `ETERNAL`.

### Operator Cognitive Load / FizzBob (`EFP-BOB0` through `EFP-BOB8`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `OperatorModelError` | `FizzBuzzError` | `EFP-BOB0` | Base exception for all operator cognitive load modeling errors |
| `CircadianModelError` | `OperatorModelError` | `EFP-BOB1` | The circadian rhythm model encountered an invalid state |
| `CognitiveOverloadError` | `OperatorModelError` | `EFP-BOB2` | The operator's cognitive load index has exceeded the overload threshold |
| `FatigueEmergencyError` | `OperatorModelError` | `EFP-BOB3` | The operator has entered Fatigue Emergency Mode (24+ hours without rest) |
| `AlertFatigueThresholdError` | `OperatorModelError` | `EFP-BOB4` | The alert fatigue index has exceeded the configured threshold |
| `BurnoutThresholdExceededError` | `OperatorModelError` | `EFP-BOB5` | The operator's projected burnout date has passed or is imminent |
| `WorkloadEventValidationError` | `OperatorModelError` | `EFP-BOB6` | A workload event failed schema validation |
| `OperatorUnavailableError` | `OperatorModelError` | `EFP-BOB7` | The operator is unavailable (PTO scheduled, though none has ever been requested) |
| `OverloadControllerError` | `OperatorModelError` | `EFP-BOB8` | The overload controller failed to apply protective measures |

`OperatorModelError` is the base exception for the FizzBob subsystem. `CognitiveOverloadError` is raised when the NASA-TLX composite workload index exceeds 80 and includes `workload_index`, `threshold`, and all six TLX dimension scores in its context. `FatigueEmergencyError` is raised when the operator has been awake for 24+ consecutive hours and includes `hours_awake` and `fatigue_points` in its context. `BurnoutThresholdExceededError` carries `projected_burnout_date` and `current_fatigue_points` and is simultaneously logged to the compliance audit trail as a material SOX risk. `OperatorUnavailableError` is architecturally present for the hypothetical scenario in which Bob schedules PTO; it has never been raised in production.

### Approval Workflow / FizzApproval (`EFP-APR0` through `EFP-APR7`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `ApprovalError` | `FizzBuzzError` | `EFP-APR0` | Base exception for all FizzApproval workflow engine errors |
| `ApprovalPolicyError` | `ApprovalError` | `EFP-APR1` | An approval policy cannot be evaluated or applied |
| `ApprovalQuorumError` | `ApprovalError` | `EFP-APR2` | The Change Advisory Board cannot achieve quorum |
| `ApprovalConflictOfInterestError` | `ApprovalError` | `EFP-APR3` | A conflict of interest was detected in the approval chain |
| `ApprovalDelegationError` | `ApprovalError` | `EFP-APR4` | The delegation chain encountered an invalid state |
| `ApprovalTimeoutError` | `ApprovalError` | `EFP-APR5` | An approval request exceeded its time-to-live |
| `ApprovalAuditError` | `ApprovalError` | `EFP-APR6` | The approval audit trail encountered an integrity failure |
| `ApprovalMiddlewareError` | `ApprovalError` | `EFP-APR7` | The ApprovalMiddleware failed to process an evaluation |

`ApprovalError` is the base exception for the FizzApproval subsystem. `ApprovalPolicyError` carries `policy_name` and `reason` in its context, covering invalid policy definitions and policy conflicts. `ApprovalQuorumError` is raised when the CAB cannot achieve quorum, carrying `required` and `present` member counts -- though in practice, quorum (1 of 1) is always met. `ApprovalConflictOfInterestError` is raised when the COI checker identifies a conflict between the requestor and an approver; it carries `approver_id` and `reason`. Since Bob is both requestor and sole approver, this exception's detection logic fires on every request, but the Sole Operator Exception permits the workflow to proceed. `ApprovalDelegationError` covers delegation cycles, exceeded chain depth limits, and invalid delegate references, carrying `chain_depth` and `reason`. `ApprovalTimeoutError` is raised when a request exceeds its TTL without obtaining the required approvals, carrying `request_id` and `timeout_seconds`. `ApprovalAuditError` indicates that an audit entry could not be written or that a consistency check on the tamper-evident hash chain failed, carrying `entry_id` and `reason`. `ApprovalMiddlewareError` covers failures in the request creation, policy evaluation, and approval routing path within the middleware pipeline, carrying `evaluation_number` and `reason`.

### Incident Paging & Escalation / FizzPager (`EFP-PGR0` through `EFP-PGR7`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `PagerError` | `FizzBuzzError` | `EFP-PGR0` | Base exception for all FizzPager incident paging and escalation errors |
| `PagerAlertError` | `PagerError` | `EFP-PGR1` | An alert cannot be processed through the paging pipeline |
| `PagerDeduplicationError` | `PagerError` | `EFP-PGR2` | Alert deduplication encountered an anomaly in key computation or window management |
| `PagerCorrelationError` | `PagerError` | `EFP-PGR3` | Alert correlation failed to match or register incidents |
| `PagerEscalationError` | `PagerError` | `EFP-PGR4` | Incident escalation encountered an invalid condition or misconfigured chain |
| `PagerIncidentError` | `PagerError` | `EFP-PGR5` | An incident lifecycle operation failed (invalid state transition, missing incident, timeline corruption) |
| `PagerScheduleError` | `PagerError` | `EFP-PGR6` | The on-call schedule encountered a configuration error (empty roster, invalid rotation) |
| `PagerDashboardError` | `PagerError` | `EFP-PGR7` | The FizzPager ASCII dashboard failed to render a panel |
| `PagerMiddlewareError` | `PagerError` | `EFP-PGR7` | The PagerMiddleware failed to process an evaluation |

`PagerError` is the base exception for the FizzPager subsystem. `PagerAlertError` carries `alert_id` and `reason` in its context, covering failures during alert ingestion, deduplication, correlation, and noise reduction stages. `PagerDeduplicationError` carries `dedup_key` and `reason`, indicating failures in the sliding-window deduplication engine. `PagerCorrelationError` carries `correlation_key` and `reason`, covering failures in temporal proximity grouping and incident clustering. `PagerEscalationError` carries `incident_id`, `tier`, and `reason`, raised when attempting to escalate beyond the terminal tier (L4) or when the escalation chain is misconfigured. `PagerIncidentError` carries `incident_id` and `reason`, covering invalid state transitions in the 7-state incident lifecycle. `PagerScheduleError` carries `schedule_key` and `reason`, raised when the on-call schedule cannot determine a responder -- architecturally present for the hypothetical case where the roster is empty, though the roster has never contained fewer than one entry. `PagerDashboardError` carries `panel` and `reason`, covering rendering failures in individual dashboard panels. `PagerMiddlewareError` carries `evaluation_number` and `reason`, covering failures in alert creation, incident simulation, and metadata injection within the middleware pipeline. `PagerDashboardError` and `PagerMiddlewareError` share error code `EFP-PGR7`, as both represent terminal presentation-layer failures.

### Repository / Unit of Work (`EFP-RP0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `RepositoryError` | `FizzBuzzError` | `EFP-RP00` | Base exception for all repository-layer failures |
| `ResultNotFoundError` | `RepositoryError` | `EFP-RP01` | A FizzBuzz result cannot be located in the repository |
| `UnitOfWorkError` | `RepositoryError` | `EFP-RP02` | The Unit of Work transaction lifecycle was violated |
| `RollbackError` | `RepositoryError` | `EFP-RP03` | A rollback operation itself failed |

`RepositoryError` accepts a `backend` keyword argument (default `"unknown"`) identifying the persistence backend. `UnitOfWorkError` describes deviations from the enter-work-commit/rollback-exit lifecycle as "an affront to Martin Fowler and everyone who ever drew a UML sequence diagram of a transaction boundary." `RollbackError` compares the situation to "trying to put out a fire with gasoline."

### FizzImage Container Image Catalog (`EFP-IMG0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `FizzImageError` | `FizzBuzzError` | `EFP-IMG00` | Base exception for FizzImage container image catalog errors |
| `CatalogInitializationError` | `FizzImageError` | `EFP-IMG01` | The image catalog failed to initialize |
| `ImageNotFoundError` | `FizzImageError` | `EFP-IMG02` | A referenced image does not exist in the catalog |
| `ImageAlreadyExistsError` | `FizzImageError` | `EFP-IMG03` | Attempting to register a duplicate image name |
| `ImageBuildError` | `FizzImageError` | `EFP-IMG04` | Image construction failed during FizzFile execution |
| `ImageBuildDependencyError` | `FizzImageError` | `EFP-IMG05` | An image's base or dependency image is missing |
| `FizzFileGenerationError` | `FizzImageError` | `EFP-IMG06` | FizzFile DSL generation failed for a module |
| `DependencyRuleViolationError` | `FizzImageError` | `EFP-IMG07` | An image violates the Clean Architecture dependency rule |
| `LayerCreationError` | `FizzImageError` | `EFP-IMG08` | A filesystem layer cannot be constructed |
| `DigestMismatchError` | `FizzImageError` | `EFP-IMG09` | A layer's computed digest does not match its expected digest |
| `VulnerabilityScanError` | `FizzImageError` | `EFP-IMG10` | The vulnerability scanner encountered an operational failure |
| `ImageBlockedByScanError` | `FizzImageError` | `EFP-IMG11` | An image is blocked due to scan policy violations |
| `VersionConflictError` | `FizzImageError` | `EFP-IMG12` | A version tag conflicts with an existing version |
| `MultiArchBuildError` | `FizzImageError` | `EFP-IMG13` | Multi-architecture manifest index generation failed |
| `PlatformResolutionError` | `FizzImageError` | `EFP-IMG14` | A platform cannot be resolved from a manifest index |
| `InitContainerBuildError` | `FizzImageError` | `EFP-IMG15` | An init container image build failed |
| `SidecarBuildError` | `FizzImageError` | `EFP-IMG16` | A sidecar container image build failed |
| `CatalogCapacityError` | `FizzImageError` | `EFP-IMG17` | The catalog exceeds its maximum image capacity |
| `CircularDependencyError` | `FizzImageError` | `EFP-IMG18` | Circular dependencies detected in subsystem imports |
| `MetadataValidationError` | `FizzImageError` | `EFP-IMG19` | Image metadata failed OCI annotation validation |
| `FizzImageMiddlewareError` | `FizzImageError` | `EFP-IMG20` | The FizzImage middleware failed to process an evaluation |

All FizzImage exceptions carry a `reason` field in their context. `FizzImageMiddlewareError` additionally carries `evaluation_number`. The catalog enforces the Clean Architecture dependency rule at the image level, and `DependencyRuleViolationError` is raised when an image includes imports from a layer it should not access.

### FizzDeploy Deployment Pipeline (`EFP-DPL0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `DeployError` | `FizzBuzzError` | `EFP-DPL00` | Base exception for all FizzDeploy deployment pipeline errors |
| `DeployPipelineError` | `DeployError` | `EFP-DPL01` | Pipeline execution failed (timeout, illegal state, internal error) |
| `DeployStageError` | `DeployError` | `EFP-DPL02` | A pipeline stage execution failed |
| `DeployStepError` | `DeployError` | `EFP-DPL03` | A pipeline step failed after exhausting all retry attempts |
| `DeployStrategyError` | `DeployError` | `EFP-DPL04` | An unknown or unsupported deployment strategy was requested |
| `RollingUpdateError` | `DeployError` | `EFP-DPL05` | The rolling update strategy encountered a failure |
| `BlueGreenError` | `DeployError` | `EFP-DPL06` | The blue-green deployment strategy failed |
| `CanaryError` | `DeployError` | `EFP-DPL07` | The canary deployment detected a regression |
| `RecreateError` | `DeployError` | `EFP-DPL08` | The recreate deployment strategy failed |
| `DeployManifestError` | `DeployError` | `EFP-DPL09` | General deployment manifest error |
| `ManifestParseError` | `DeployManifestError` | `EFP-DPL10` | YAML syntax errors prevent manifest parsing |
| `ManifestValidationError` | `DeployManifestError` | `EFP-DPL11` | Manifest fails schema validation |
| `GitOpsReconcileError` | `DeployError` | `EFP-DPL12` | The GitOps reconciliation loop encountered a failure |
| `GitOpsDriftError` | `DeployError` | `EFP-DPL13` | Configuration drift detected between declared and actual state |
| `GitOpsSyncError` | `DeployError` | `EFP-DPL14` | Drift correction failed during synchronization |
| `RollbackError` | `DeployError` | `EFP-DPL15` | General rollback operation failure |
| `RollbackRevisionNotFoundError` | `RollbackError` | `EFP-DPL16` | Target revision does not exist in revision history |
| `RollbackStrategyError` | `RollbackError` | `EFP-DPL17` | Strategy-aware rollback operation failed |
| `DeployGateError` | `DeployError` | `EFP-DPL18` | General deployment gate error |
| `CognitiveLoadGateError` | `DeployGateError` | `EFP-DPL19` | Operator cognitive load exceeds deployment threshold |
| `DeployDashboardError` | `DeployError` | `EFP-DPL20` | Deployment dashboard failed to render |
| `DeployMiddlewareError` | `DeployError` | `EFP-DPL21` | The FizzDeploy middleware failed to process an evaluation |

`CognitiveLoadGateError` carries `deployment_name`, `current_score`, and `threshold` in its context, recording the NASA-TLX assessment that blocked the deployment. Emergency deployments bypass this gate via the `--fizzdeploy-emergency` flag, which is logged for post-incident review.

### FizzCompose Multi-Container Orchestration (`EFP-CMP0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `ComposeError` | `Exception` | `EFP-CMP00` | Base exception for FizzCompose multi-container orchestration errors |
| `ComposeFileNotFoundError` | `ComposeError` | `EFP-CMP01` | The compose file cannot be located |
| `ComposeFileParseError` | `ComposeError` | `EFP-CMP02` | The compose file contains invalid YAML or schema violations |
| `ComposeVariableInterpolationError` | `ComposeError` | `EFP-CMP03` | Variable interpolation in the compose file failed |
| `ComposeCircularDependencyError` | `ComposeError` | `EFP-CMP04` | The service dependency graph contains a cycle |
| `ComposeServiceNotFoundError` | `ComposeError` | `EFP-CMP05` | A referenced service does not exist in the compose file |
| `ComposeServiceStartError` | `ComposeError` | `EFP-CMP06` | A service failed to start |
| `ComposeServiceStopError` | `ComposeError` | `EFP-CMP07` | A service failed to stop gracefully |
| `ComposeHealthCheckTimeoutError` | `ComposeError` | `EFP-CMP08` | A service failed to become healthy within the timeout |
| `ComposeNetworkCreateError` | `ComposeError` | `EFP-CMP09` | A compose-scoped network cannot be created |
| `ComposeNetworkNotFoundError` | `ComposeError` | `EFP-CMP10` | A service references an undefined network |
| `ComposeVolumeCreateError` | `ComposeError` | `EFP-CMP11` | A compose-scoped volume cannot be created |
| `ComposeVolumeNotFoundError` | `ComposeError` | `EFP-CMP12` | A service references an undefined volume |
| `ComposeScaleError` | `ComposeError` | `EFP-CMP13` | A scale operation failed |
| `ComposeExecError` | `ComposeError` | `EFP-CMP14` | Exec into a service container failed |
| `ComposeRestartError` | `ComposeError` | `EFP-CMP15` | A service restart operation failed |
| `ComposeRestartPolicyExhaustedError` | `ComposeError` | `EFP-CMP16` | A service has exhausted its restart attempts |
| `ComposePortConflictError` | `ComposeError` | `EFP-CMP17` | Two services attempt to bind the same host port |
| `ComposeImageNotFoundError` | `ComposeError` | `EFP-CMP18` | A service's image is not in the FizzImage catalog |
| `ComposeProjectAlreadyRunningError` | `ComposeError` | `EFP-CMP19` | Compose up called on an already-running project |
| `ComposeMiddlewareError` | `ComposeError` | `EFP-CMP20` | The FizzCompose middleware encountered an error |

`ComposeError` inherits from `Exception` rather than `FizzBuzzError`, as the compose system operates at the application topology level. All exceptions carry structured context via the `context` dictionary and `error_code` attribute, following the same EFP-coded pattern as the rest of the platform.

### FizzKubeV2 Container-Aware Orchestrator (`EFP-KV2xx`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `KubeV2Error` | `Exception` | `EFP-KV200` | Base exception for all FizzKubeV2 errors |
| `KubeletV2Error` | `KubeV2Error` | `EFP-KV201` | CRI-integrated kubelet lifecycle failure |
| `KV2ImagePullError` | `KubeV2Error` | `EFP-KV202` | Image pull operation failed |
| `ImagePullBackOffError` | `KubeV2Error` | `EFP-KV203` | Image pull entered exponential backoff |
| `ImageNotPresentError` | `KubeV2Error` | `EFP-KV204` | Image not present locally with pull policy Never |
| `PullSecretError` | `KubeV2Error` | `EFP-KV205` | Pull secret retrieval or authentication failed |
| `InitContainerFailedError` | `KubeV2Error` | `EFP-KV206` | Init container exited with a non-zero code |
| `InitContainerTimeoutError` | `KubeV2Error` | `EFP-KV207` | Init container exceeded its execution timeout |
| `SidecarInjectionError` | `KubeV2Error` | `EFP-KV208` | Sidecar injection failed for a pod |
| `SidecarLifecycleError` | `KubeV2Error` | `EFP-KV209` | Sidecar container lifecycle ordering violated |
| `ProbeFailedError` | `KubeV2Error` | `EFP-KV210` | A health probe failed |
| `ProbeTimeoutError` | `KubeV2Error` | `EFP-KV211` | A probe execution exceeded its timeout |
| `ReadinessProbeFailedError` | `ProbeFailedError` | `EFP-KV212` | Readiness probe threshold breached |
| `LivenessProbeFailedError` | `ProbeFailedError` | `EFP-KV213` | Liveness probe threshold breached |
| `StartupProbeFailedError` | `ProbeFailedError` | `EFP-KV214` | Startup probe never succeeded in time |
| `VolumeProvisionError` | `KubeV2Error` | `EFP-KV215` | Volume provisioning failed |
| `VolumeMountError` | `KubeV2Error` | `EFP-KV216` | Volume mount into a container failed |
| `PVCNotFoundError` | `KubeV2Error` | `EFP-KV217` | Referenced PersistentVolumeClaim does not exist |
| `ContainerRestartBackoffError` | `KubeV2Error` | `EFP-KV218` | Container is in restart backoff |
| `PodTerminationError` | `KubeV2Error` | `EFP-KV219` | Graceful pod termination failed |
| `KubeV2MiddlewareError` | `KubeV2Error` | `EFP-KV220` | FizzKubeV2 middleware failed to process an evaluation |

`KubeV2Error` inherits from `Exception` rather than `FizzBuzzError`, as the KubeV2 subsystem operates at the orchestrator level. The probe failure hierarchy uses `ProbeFailedError` as a generic base, with `ReadinessProbeFailedError`, `LivenessProbeFailedError`, and `StartupProbeFailedError` as specialized subtypes. Readiness failures remove the container from service endpoints but do not trigger a restart; liveness failures cause container restart; startup failures indicate the container never became ready.

### FizzContainerChaos Container-Native Chaos Engineering (`EFP-CCH0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `ContainerChaosError` | `FizzBuzzError` | `EFP-CCH00` | Base exception for FizzContainerChaos errors |
| `ChaosExperimentNotFoundError` | `ContainerChaosError` | `EFP-CCH01` | A referenced chaos experiment does not exist |
| `ChaosExperimentAlreadyRunningError` | `ContainerChaosError` | `EFP-CCH02` | Attempting to start an already-running experiment |
| `ChaosExperimentAbortedError` | `ContainerChaosError` | `EFP-CCH03` | A chaos experiment was aborted due to safety conditions |
| `ChaosExperimentFailedStartError` | `ContainerChaosError` | `EFP-CCH04` | A chaos experiment failed during the pre-check phase |
| `ChaosFaultInjectionError` | `ContainerChaosError` | `EFP-CCH05` | Fault injection failed |
| `ChaosFaultRemovalError` | `ContainerChaosError` | `EFP-CCH06` | Fault removal failed after experiment completion |
| `ChaosContainerKillError` | `ContainerChaosError` | `EFP-CCH07` | Container kill fault failed to terminate a container |
| `ChaosNetworkPartitionError` | `ContainerChaosError` | `EFP-CCH08` | Network partition fault failed |
| `ChaosCPUStressError` | `ContainerChaosError` | `EFP-CCH09` | CPU stress fault failed |
| `ChaosMemoryPressureError` | `ContainerChaosError` | `EFP-CCH10` | Memory pressure fault failed |
| `ChaosDiskFillError` | `ContainerChaosError` | `EFP-CCH11` | Disk fill fault failed |
| `ChaosImagePullFailureError` | `ContainerChaosError` | `EFP-CCH12` | Image pull failure fault failed to intercept pulls |
| `ChaosDNSFailureError` | `ContainerChaosError` | `EFP-CCH13` | DNS failure fault failed to disrupt resolution |
| `ChaosNetworkLatencyError` | `ContainerChaosError` | `EFP-CCH14` | Network latency fault failed to inject delay |
| `ChaosGameDayError` | `ContainerChaosError` | `EFP-CCH15` | Game day orchestration encountered an error |
| `ChaosGameDayAbortError` | `ContainerChaosError` | `EFP-CCH16` | Game day aborted due to system-level conditions |
| `ChaosBlastRadiusExceededError` | `ContainerChaosError` | `EFP-CCH17` | Fault injection would exceed the blast radius limit |
| `ChaosSteadyStateViolationError` | `ContainerChaosError` | `EFP-CCH18` | Steady-state metrics deviated beyond tolerance |
| `ChaosCognitiveLoadGateError` | `ContainerChaosError` | `EFP-CCH19` | Operator cognitive load exceeds the chaos threshold |
| `ChaosScheduleError` | `ContainerChaosError` | `EFP-CCH20` | A chaos schedule configuration error |
| `ChaosReportGenerationError` | `ContainerChaosError` | `EFP-CCH21` | Experiment or game day report generation failed |
| `ChaosTargetResolutionError` | `ContainerChaosError` | `EFP-CCH22` | Target container resolution failed |
| `ChaosContainerChaosMiddlewareError` | `ContainerChaosError` | `EFP-CCH23` | FizzContainerChaos middleware failed during evaluation |

The eight per-fault-type exceptions (EFP-CCH07 through EFP-CCH14) correspond one-to-one with the eight fault injection types. `ChaosBlastRadiusExceededError` prevents chaos experiments from affecting too many containers simultaneously, while `ChaosCognitiveLoadGateError` gates on the operator's NASA-TLX score via FizzBob.

### FizzContainerOps Container Observability & Diagnostics (`EFP-COP0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `ContainerOpsError` | `FizzBuzzError` | `EFP-COP00` | Base exception for FizzContainerOps errors |
| `ContainerOpsLogCollectorError` | `ContainerOpsError` | `EFP-COP01` | Log collector failed to tail container output |
| `ContainerOpsLogIndexError` | `ContainerOpsError` | `EFP-COP02` | Inverted log index corruption or capacity error |
| `ContainerOpsLogQueryError` | `ContainerOpsError` | `EFP-COP03` | Log query failed during execution |
| `ContainerOpsLogRetentionError` | `ContainerOpsError` | `EFP-COP04` | Log retention policy error during eviction |
| `ContainerOpsMetricsCollectorError` | `ContainerOpsError` | `EFP-COP05` | Metrics collector failed to scrape cgroup statistics |
| `ContainerOpsMetricsStoreError` | `ContainerOpsError` | `EFP-COP06` | Time-series metrics store encountered a storage error |
| `ContainerOpsMetricsAlertError` | `ContainerOpsError` | `EFP-COP07` | Alerting subsystem encountered an evaluation error |
| `ContainerOpsTraceExtenderError` | `ContainerOpsError` | `EFP-COP08` | Trace extender failed to annotate spans with container context |
| `ContainerOpsTraceDashboardError` | `ContainerOpsError` | `EFP-COP09` | Trace dashboard encountered a query or rendering error |
| `ContainerOpsExecError` | `ContainerOpsError` | `EFP-COP10` | Exec command failed inside a container |
| `ContainerOpsExecTimeoutError` | `ContainerOpsError` | `EFP-COP11` | Exec command exceeded its timeout |
| `ContainerOpsOverlayDiffError` | `ContainerOpsError` | `EFP-COP12` | Overlay filesystem diff computation failed |
| `ContainerOpsProcessTreeError` | `ContainerOpsError` | `EFP-COP13` | Container process tree cannot be constructed |
| `ContainerOpsFlameGraphError` | `ContainerOpsError` | `EFP-COP14` | Cgroup-scoped flame graph generation failed |
| `ContainerOpsDashboardError` | `ContainerOpsError` | `EFP-COP15` | ASCII container dashboard encountered a data error |
| `ContainerOpsDashboardRenderError` | `ContainerOpsError` | `EFP-COP16` | Dashboard rendering engine failed to produce output |
| `ContainerOpsCorrelationError` | `ContainerOpsError` | `EFP-COP17` | Correlation ID propagation or lookup failed |
| `ContainerOpsQuerySyntaxError` | `ContainerOpsError` | `EFP-COP18` | Log query DSL expression has invalid syntax |
| `ContainerOpsMiddlewareError` | `ContainerOpsError` | `EFP-COP19` | FizzContainerOps middleware encountered an error |

The exceptions are organized along the five observability pillars: logs (EFP-COP01 through EFP-COP04), metrics (EFP-COP05 through EFP-COP07), traces (EFP-COP08 through EFP-COP09), diagnostics (EFP-COP10 through EFP-COP14), and dashboard (EFP-COP15 through EFP-COP16). `ContainerOpsQuerySyntaxError` covers the log query DSL syntax validation, supporting AND, OR, NOT operators, field:value matching, wildcard patterns, and time range expressions.

---

## Inheritance Summary

```
Exception
  └── FizzBuzzError                          EFP-0000
        ├── ConfigurationError               EFP-1000
        │     ├── ConfigurationFileNotFoundError
        │     └── ConfigurationValidationError
        ├── RuleEvaluationError              EFP-2000
        │     └── RuleConflictError
        ├── PluginLoadError                  EFP-3000
        │     └── PluginNotFoundError
        ├── MiddlewareError                  EFP-4000
        ├── FormatterError                   EFP-5000
        ├── ObserverError                    EFP-6000
        ├── ServiceNotInitializedError       EFP-7000
        ├── InvalidRangeError                EFP-8000
        ├── ModelConvergenceError            EFP-9000
        ├── BlockchainIntegrityError         EFP-B000
        ├── CircuitOpenError                 EFP-CB00
        ├── CircuitBreakerTimeoutError       EFP-CB01
        ├── DownstreamFizzBuzzDegradationError EFP-CB02
        ├── LocaleError                      EFP-I000
        │     ├── LocaleNotFoundError        EFP-I001
        │     ├── TranslationKeyError        EFP-I002
        │     ├── FizzTranslationParseError  EFP-I003
        │     ├── PluralizationError         EFP-I004
        │     └── LocaleChainExhaustedError  EFP-I005
        ├── AuthenticationError              EFP-A000
        │     └── TokenValidationError       EFP-A003
        ├── InsufficientFizzPrivilegesError  EFP-A001
        ├── NumberClassificationLevelExceededError EFP-A002
        ├── EventStoreError                  EFP-ES00
        │     ├── EventSequenceError         EFP-ES01
        │     ├── EventDeserializationError  EFP-ES02
        │     ├── SnapshotCorruptionError    EFP-ES03
        │     ├── CommandValidationError     EFP-ES04
        │     ├── CommandHandlerNotFoundError EFP-ES05
        │     ├── QueryHandlerNotFoundError  EFP-ES06
        │     ├── ProjectionError            EFP-ES07
        │     ├── TemporalQueryError         EFP-ES08
        │     └── EventVersionConflictError  EFP-ES09
        ├── ChaosError                       EFP-CH00
        │     ├── ChaosInducedFizzBuzzError  EFP-CH01
        │     ├── ChaosExperimentFailedError EFP-CH02
        │     ├── ChaosConfigurationError    EFP-CH03
        │     └── ResultCorruptionDetectedError EFP-CH04
        ├── FeatureFlagError                 EFP-FF00
        │     ├── FlagNotFoundError          EFP-FF01
        │     ├── FlagDependencyCycleError   EFP-FF02
        │     ├── FlagLifecycleError         EFP-FF03
        │     ├── FlagDependencyNotMetError  EFP-FF04
        │     ├── FlagRolloutError           EFP-FF05
        │     └── FlagTargetingError         EFP-FF06
        ├── SLAError                         EFP-SL00
        │     ├── SLOViolationError          EFP-SL01
        │     ├── ErrorBudgetExhaustedError  EFP-SL02
        │     ├── AlertEscalationError       EFP-SL03
        │     ├── OnCallNotFoundError        EFP-SL04
        │     └── SLAConfigurationError      EFP-SL05
        ├── CacheError                       EFP-CA00
        │     ├── CacheCapacityExceededError EFP-CA01
        │     ├── CacheCoherenceViolationError EFP-CA02
        │     ├── CacheEntryExpiredError     EFP-CA03
        │     ├── CacheWarmingError          EFP-CA04
        │     ├── CachePolicyNotFoundError   EFP-CA05
        │     ├── CacheInvalidationCascadeError EFP-CA06
        │     └── CacheEulogyCompositionError EFP-CA07
        ├── MigrationError                   EFP-MG00
        │     ├── MigrationNotFoundError     EFP-MG01
        │     ├── MigrationAlreadyAppliedError EFP-MG02
        │     ├── MigrationRollbackError     EFP-MG03
        │     ├── MigrationDependencyError   EFP-MG04
        │     ├── MigrationConflictError     EFP-MG05
        │     ├── SchemaError                EFP-MG06
        │     └── SeedDataError              EFP-MG07
        ├── DependencyInjectionError         EFP-DI00
        │     ├── CircularDependencyError    EFP-DI01
        │     ├── MissingBindingError        EFP-DI02
        │     ├── DuplicateBindingError      EFP-DI03
        │     └── ScopeError                 EFP-DI04
        ├── OperatorModelError                EFP-BOB0
        │     ├── CircadianModelError        EFP-BOB1
        │     ├── CognitiveOverloadError     EFP-BOB2
        │     ├── FatigueEmergencyError      EFP-BOB3
        │     ├── AlertFatigueThresholdError EFP-BOB4
        │     ├── BurnoutThresholdExceededError EFP-BOB5
        │     ├── WorkloadEventValidationError EFP-BOB6
        │     ├── OperatorUnavailableError   EFP-BOB7
        │     └── OverloadControllerError    EFP-BOB8
        ├── ApprovalError                     EFP-APR0
        │     ├── ApprovalPolicyError        EFP-APR1
        │     ├── ApprovalQuorumError        EFP-APR2
        │     ├── ApprovalConflictOfInterestError EFP-APR3
        │     ├── ApprovalDelegationError    EFP-APR4
        │     ├── ApprovalTimeoutError       EFP-APR5
        │     ├── ApprovalAuditError         EFP-APR6
        │     └── ApprovalMiddlewareError    EFP-APR7
        ├── PagerError                        EFP-PGR0
        │     ├── PagerAlertError            EFP-PGR1
        │     ├── PagerDeduplicationError    EFP-PGR2
        │     ├── PagerCorrelationError      EFP-PGR3
        │     ├── PagerEscalationError       EFP-PGR4
        │     ├── PagerIncidentError         EFP-PGR5
        │     ├── PagerScheduleError         EFP-PGR6
        │     ├── PagerDashboardError        EFP-PGR7
        │     └── PagerMiddlewareError       EFP-PGR7
        ├── RepositoryError                  EFP-RP00
        │     ├── ResultNotFoundError        EFP-RP01
        │     ├── UnitOfWorkError            EFP-RP02
        │     └── RollbackError              EFP-RP03
        ├── FizzImageError                   EFP-IMG00
        │     ├── CatalogInitializationError EFP-IMG01
        │     ├── ImageNotFoundError         EFP-IMG02
        │     ├── ImageAlreadyExistsError    EFP-IMG03
        │     ├── ImageBuildError            EFP-IMG04
        │     ├── ImageBuildDependencyError  EFP-IMG05
        │     ├── FizzFileGenerationError    EFP-IMG06
        │     ├── DependencyRuleViolationError EFP-IMG07
        │     ├── LayerCreationError         EFP-IMG08
        │     ├── DigestMismatchError        EFP-IMG09
        │     ├── VulnerabilityScanError     EFP-IMG10
        │     ├── ImageBlockedByScanError    EFP-IMG11
        │     ├── VersionConflictError       EFP-IMG12
        │     ├── MultiArchBuildError        EFP-IMG13
        │     ├── PlatformResolutionError    EFP-IMG14
        │     ├── InitContainerBuildError    EFP-IMG15
        │     ├── SidecarBuildError          EFP-IMG16
        │     ├── CatalogCapacityError       EFP-IMG17
        │     ├── CircularDependencyError    EFP-IMG18
        │     ├── MetadataValidationError    EFP-IMG19
        │     └── FizzImageMiddlewareError   EFP-IMG20
        └── ContainerChaosError              EFP-CCH00
              ├── ChaosExperimentNotFoundError EFP-CCH01
              ├── ChaosExperimentAlreadyRunningError EFP-CCH02
              ├── ChaosExperimentAbortedError EFP-CCH03
              ├── ChaosExperimentFailedStartError EFP-CCH04
              ├── ChaosFaultInjectionError   EFP-CCH05
              ├── ChaosFaultRemovalError     EFP-CCH06
              ├── ChaosContainerKillError    EFP-CCH07
              ├── ChaosNetworkPartitionError EFP-CCH08
              ├── ChaosCPUStressError        EFP-CCH09
              ├── ChaosMemoryPressureError   EFP-CCH10
              ├── ChaosDiskFillError         EFP-CCH11
              ├── ChaosImagePullFailureError EFP-CCH12
              ├── ChaosDNSFailureError       EFP-CCH13
              ├── ChaosNetworkLatencyError   EFP-CCH14
              ├── ChaosGameDayError          EFP-CCH15
              ├── ChaosGameDayAbortError     EFP-CCH16
              ├── ChaosBlastRadiusExceededError EFP-CCH17
              ├── ChaosSteadyStateViolationError EFP-CCH18
              ├── ChaosCognitiveLoadGateError EFP-CCH19
              ├── ChaosScheduleError         EFP-CCH20
              ├── ChaosReportGenerationError EFP-CCH21
              ├── ChaosTargetResolutionError EFP-CCH22
              └── ChaosContainerChaosMiddlewareError EFP-CCH23

Exception
  └── ComposeError                             EFP-CMP00
        ├── ComposeFileNotFoundError           EFP-CMP01
        ├── ComposeFileParseError              EFP-CMP02
        ├── ComposeVariableInterpolationError  EFP-CMP03
        ├── ComposeCircularDependencyError     EFP-CMP04
        ├── ComposeServiceNotFoundError        EFP-CMP05
        ├── ComposeServiceStartError           EFP-CMP06
        ├── ComposeServiceStopError            EFP-CMP07
        ├── ComposeHealthCheckTimeoutError     EFP-CMP08
        ├── ComposeNetworkCreateError          EFP-CMP09
        ├── ComposeNetworkNotFoundError        EFP-CMP10
        ├── ComposeVolumeCreateError           EFP-CMP11
        ├── ComposeVolumeNotFoundError         EFP-CMP12
        ├── ComposeScaleError                  EFP-CMP13
        ├── ComposeExecError                   EFP-CMP14
        ├── ComposeRestartError                EFP-CMP15
        ├── ComposeRestartPolicyExhaustedError EFP-CMP16
        ├── ComposePortConflictError           EFP-CMP17
        ├── ComposeImageNotFoundError          EFP-CMP18
        ├── ComposeProjectAlreadyRunningError  EFP-CMP19
        └── ComposeMiddlewareError             EFP-CMP20

Exception
  └── KubeV2Error                              EFP-KV200
        ├── KubeletV2Error                     EFP-KV201
        ├── KV2ImagePullError                  EFP-KV202
        ├── ImagePullBackOffError              EFP-KV203
        ├── ImageNotPresentError               EFP-KV204
        ├── PullSecretError                    EFP-KV205
        ├── InitContainerFailedError           EFP-KV206
        ├── InitContainerTimeoutError          EFP-KV207
        ├── SidecarInjectionError              EFP-KV208
        ├── SidecarLifecycleError              EFP-KV209
        ├── ProbeFailedError                   EFP-KV210
        │     ├── ReadinessProbeFailedError    EFP-KV212
        │     ├── LivenessProbeFailedError     EFP-KV213
        │     └── StartupProbeFailedError      EFP-KV214
        ├── ProbeTimeoutError                  EFP-KV211
        ├── VolumeProvisionError               EFP-KV215
        ├── VolumeMountError                   EFP-KV216
        ├── PVCNotFoundError                   EFP-KV217
        ├── ContainerRestartBackoffError       EFP-KV218
        ├── PodTerminationError                EFP-KV219
        └── KubeV2MiddlewareError              EFP-KV220

Exception
  └── DeployError                              EFP-DPL00
        ├── DeployPipelineError                EFP-DPL01
        ├── DeployStageError                   EFP-DPL02
        ├── DeployStepError                    EFP-DPL03
        ├── DeployStrategyError                EFP-DPL04
        ├── RollingUpdateError                 EFP-DPL05
        ├── BlueGreenError                     EFP-DPL06
        ├── CanaryError                        EFP-DPL07
        ├── RecreateError                      EFP-DPL08
        ├── DeployManifestError                EFP-DPL09
        │     ├── ManifestParseError           EFP-DPL10
        │     └── ManifestValidationError      EFP-DPL11
        ├── GitOpsReconcileError               EFP-DPL12
        ├── GitOpsDriftError                   EFP-DPL13
        ├── GitOpsSyncError                    EFP-DPL14
        ├── RollbackError                      EFP-DPL15
        │     ├── RollbackRevisionNotFoundError EFP-DPL16
        │     └── RollbackStrategyError        EFP-DPL17
        ├── DeployGateError                    EFP-DPL18
        │     └── CognitiveLoadGateError       EFP-DPL19
        ├── DeployDashboardError               EFP-DPL20
        └── DeployMiddlewareError              EFP-DPL21

Exception
  └── ContainerOpsError                        EFP-COP00
        ├── ContainerOpsLogCollectorError      EFP-COP01
        ├── ContainerOpsLogIndexError          EFP-COP02
        ├── ContainerOpsLogQueryError          EFP-COP03
        ├── ContainerOpsLogRetentionError      EFP-COP04
        ├── ContainerOpsMetricsCollectorError  EFP-COP05
        ├── ContainerOpsMetricsStoreError      EFP-COP06
        ├── ContainerOpsMetricsAlertError      EFP-COP07
        ├── ContainerOpsTraceExtenderError     EFP-COP08
        ├── ContainerOpsTraceDashboardError    EFP-COP09
        ├── ContainerOpsExecError              EFP-COP10
        ├── ContainerOpsExecTimeoutError       EFP-COP11
        ├── ContainerOpsOverlayDiffError       EFP-COP12
        ├── ContainerOpsProcessTreeError       EFP-COP13
        ├── ContainerOpsFlameGraphError        EFP-COP14
        ├── ContainerOpsDashboardError         EFP-COP15
        ├── ContainerOpsDashboardRenderError   EFP-COP16
        ├── ContainerOpsCorrelationError       EFP-COP17
        ├── ContainerOpsQuerySyntaxError       EFP-COP18
        └── ContainerOpsMiddlewareError        EFP-COP19
```

## Aliases

Four module-level aliases provide backward compatibility with earlier naming conventions:

```python
LocalizationError = LocaleError                    # line 342
TranslationFileParseError = FizzTranslationParseError  # line 343
TranslationKeyMissingError = TranslationKeyError       # line 344
PluralizationRuleError = PluralizationError            # line 345
```

These are direct assignments, not subclasses. `isinstance` checks against either name will behave identically.
