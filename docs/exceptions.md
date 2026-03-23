# Exception Catalog

Enterprise FizzBuzz Platform v1.0.0

## Overview

The Enterprise FizzBuzz Platform defines **86 custom exception classes** and **4 backward-compatibility aliases** in a single module:

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

### Repository / Unit of Work (`EFP-RP0x`)

| Class | Parent | Code | Description |
|-------|--------|------|-------------|
| `RepositoryError` | `FizzBuzzError` | `EFP-RP00` | Base exception for all repository-layer failures |
| `ResultNotFoundError` | `RepositoryError` | `EFP-RP01` | A FizzBuzz result cannot be located in the repository |
| `UnitOfWorkError` | `RepositoryError` | `EFP-RP02` | The Unit of Work transaction lifecycle was violated |
| `RollbackError` | `RepositoryError` | `EFP-RP03` | A rollback operation itself failed |

`RepositoryError` accepts a `backend` keyword argument (default `"unknown"`) identifying the persistence backend. `UnitOfWorkError` describes deviations from the enter-work-commit/rollback-exit lifecycle as "an affront to Martin Fowler and everyone who ever drew a UML sequence diagram of a transaction boundary." `RollbackError` compares the situation to "trying to put out a fire with gasoline."

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
        └── RepositoryError                  EFP-RP00
              ├── ResultNotFoundError        EFP-RP01
              ├── UnitOfWorkError            EFP-RP02
              └── RollbackError              EFP-RP03
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
