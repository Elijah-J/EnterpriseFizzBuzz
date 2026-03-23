"""
Enterprise FizzBuzz Platform - Exception Hierarchy Module

Provides a comprehensive, enterprise-grade exception taxonomy for all
possible failure modes in the FizzBuzz evaluation lifecycle.
"""

from __future__ import annotations

from typing import Any, Optional


class FizzBuzzError(Exception):
    """Base exception for all Enterprise FizzBuzz Platform errors.

    All exceptions in the EFP ecosystem MUST inherit from this class
    to ensure consistent error handling across the middleware pipeline.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        self.error_code = error_code or "EFP-0000"
        self.context = context or {}
        super().__init__(f"[{self.error_code}] {message}")


class ConfigurationError(FizzBuzzError):
    """Raised when the configuration subsystem encounters an invalid state."""

    def __init__(self, message: str, *, config_key: Optional[str] = None) -> None:
        super().__init__(
            message,
            error_code="EFP-1000",
            context={"config_key": config_key},
        )


class ConfigurationFileNotFoundError(ConfigurationError):
    """Raised when the YAML configuration file cannot be located on disk."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"Configuration file not found: {path}",
            config_key="__file__",
        )
        self.path = path


class ConfigurationValidationError(ConfigurationError):
    """Raised when configuration values fail schema validation."""

    def __init__(self, field: str, value: Any, expected: str) -> None:
        super().__init__(
            f"Invalid value for '{field}': got {value!r}, expected {expected}",
            config_key=field,
        )


class RuleEvaluationError(FizzBuzzError):
    """Raised when a rule fails to evaluate against a given number."""

    def __init__(self, rule_name: str, number: int, reason: str) -> None:
        super().__init__(
            f"Rule '{rule_name}' failed to evaluate number {number}: {reason}",
            error_code="EFP-2000",
            context={"rule_name": rule_name, "number": number},
        )


class RuleConflictError(RuleEvaluationError):
    """Raised when two or more rules produce conflicting results."""

    def __init__(self, rule_a: str, rule_b: str, number: int) -> None:
        super().__init__(
            rule_a,
            number,
            f"Conflicts with rule '{rule_b}'",
        )
        self.conflicting_rule = rule_b


class PluginLoadError(FizzBuzzError):
    """Raised when a plugin fails to load or register."""

    def __init__(self, plugin_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to load plugin '{plugin_name}': {reason}",
            error_code="EFP-3000",
            context={"plugin_name": plugin_name},
        )


class PluginNotFoundError(PluginLoadError):
    """Raised when a requested plugin is not found in the registry."""

    def __init__(self, plugin_name: str) -> None:
        super().__init__(plugin_name, "Plugin not found in registry")


class MiddlewareError(FizzBuzzError):
    """Raised when a middleware component fails during pipeline execution."""

    def __init__(self, middleware_name: str, phase: str, reason: str) -> None:
        super().__init__(
            f"Middleware '{middleware_name}' failed during {phase}: {reason}",
            error_code="EFP-4000",
            context={"middleware_name": middleware_name, "phase": phase},
        )


class FormatterError(FizzBuzzError):
    """Raised when an output formatter encounters an error."""

    def __init__(self, format_name: str, reason: str) -> None:
        super().__init__(
            f"Formatter '{format_name}' error: {reason}",
            error_code="EFP-5000",
            context={"format_name": format_name},
        )


class ObserverError(FizzBuzzError):
    """Raised when an observer fails to handle an event."""

    def __init__(self, observer_name: str, event_type: str, reason: str) -> None:
        super().__init__(
            f"Observer '{observer_name}' failed on event '{event_type}': {reason}",
            error_code="EFP-6000",
            context={"observer_name": observer_name, "event_type": event_type},
        )


class ServiceNotInitializedError(FizzBuzzError):
    """Raised when the FizzBuzz service is used before initialization."""

    def __init__(self) -> None:
        super().__init__(
            "FizzBuzzService has not been initialized. "
            "Did you forget to call FizzBuzzServiceBuilder.build()?",
            error_code="EFP-7000",
        )


class InvalidRangeError(FizzBuzzError):
    """Raised when the numeric range for FizzBuzz evaluation is invalid."""

    def __init__(self, start: int, end: int) -> None:
        super().__init__(
            f"Invalid range [{start}, {end}]: start must be <= end",
            error_code="EFP-8000",
            context={"start": start, "end": end},
        )


class ModelConvergenceError(FizzBuzzError):
    """Raised when the ML model fails to converge during training.

    This should never happen for the FizzBuzz task, but enterprise
    software must be prepared for all contingencies, including the
    possibility that a neural network cannot learn modulo arithmetic.
    """

    def __init__(self, rule_name: str, final_loss: float) -> None:
        super().__init__(
            f"Model for rule '{rule_name}' failed to converge. "
            f"Final loss: {final_loss:.6f}. Consider adjusting "
            f"hyperparameters or adding more training data.",
            error_code="EFP-9000",
            context={"rule_name": rule_name, "final_loss": final_loss},
        )


class BlockchainIntegrityError(FizzBuzzError):
    """Raised when the blockchain audit ledger detects tampering.

    In a distributed enterprise environment, blockchain integrity
    violations would trigger an immediate incident response. Here,
    it means someone modified a FizzBuzz result, which is arguably worse.
    """

    def __init__(self, block_index: int, reason: str) -> None:
        super().__init__(
            f"Blockchain integrity violation at block #{block_index}: {reason}",
            error_code="EFP-B000",
            context={"block_index": block_index},
        )


class CircuitOpenError(FizzBuzzError):
    """Raised when a request is rejected because the circuit breaker is open.

    In enterprise distributed systems, circuit breakers prevent cascading
    failures by rejecting requests to unhealthy downstream services. Here,
    it means FizzBuzz evaluation has been temporarily suspended because
    too many numbers failed divisibility checks, which is arguably a sign
    that mathematics itself is experiencing an outage.
    """

    def __init__(self, circuit_name: str, retry_after_ms: float) -> None:
        super().__init__(
            f"Circuit '{circuit_name}' is OPEN. Request rejected. "
            f"Retry after {retry_after_ms:.0f}ms. "
            f"FizzBuzz service is currently experiencing degraded modulo operations.",
            error_code="EFP-CB00",
            context={"circuit_name": circuit_name, "retry_after_ms": retry_after_ms},
        )
        self.circuit_name = circuit_name
        self.retry_after_ms = retry_after_ms


class CircuitBreakerTimeoutError(FizzBuzzError):
    """Raised when a FizzBuzz evaluation exceeds the circuit breaker timeout.

    If computing n % 3 takes longer than the configured timeout, something
    has gone catastrophically wrong — or someone set the timeout to zero,
    which is a configuration error of cosmic proportions.
    """

    def __init__(self, circuit_name: str, timeout_ms: float, elapsed_ms: float) -> None:
        super().__init__(
            f"Circuit '{circuit_name}' call timed out after {elapsed_ms:.2f}ms "
            f"(limit: {timeout_ms:.0f}ms). The modulo operator appears to be "
            f"running slower than expected.",
            error_code="EFP-CB01",
            context={
                "circuit_name": circuit_name,
                "timeout_ms": timeout_ms,
                "elapsed_ms": elapsed_ms,
            },
        )


class LocaleError(FizzBuzzError):
    """Base exception for all internationalization and localization errors.

    Because even error messages deserve to be localized, and the
    irony of an i18n system that can't translate its own errors
    is not lost on us.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-I000",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class LocaleNotFoundError(LocaleError):
    """Raised when the requested locale cannot be found on disk.

    The platform searched high and low across every configured locale
    directory, but the requested locale simply does not exist. Perhaps
    it was deprecated, or perhaps it was never spoken in the first place.
    """

    def __init__(self, locale: str, searched_paths: Optional[list[str]] = None) -> None:
        super().__init__(
            f"Locale '{locale}' not found. Searched: {searched_paths or []}",
            error_code="EFP-I001",
            context={"locale": locale, "searched_paths": searched_paths or []},
        )


class TranslationKeyError(LocaleError):
    """Raised when a translation key cannot be resolved in any fallback locale.

    The key was not found in the requested locale, nor in any locale
    in the fallback chain, nor in the global default. At this point,
    the key is effectively lost to the void of untranslated strings.
    """

    def __init__(self, key: str, locale: str, chain: Optional[list[str]] = None) -> None:
        super().__init__(
            f"Translation key '{key}' not found in locale '{locale}' "
            f"or fallback chain {chain or []}",
            error_code="EFP-I002",
            context={"key": key, "locale": locale, "chain": chain or []},
        )


class FizzTranslationParseError(LocaleError):
    """Raised when a .fizztranslation file contains a syntax error.

    The proprietary .fizztranslation file format is extremely particular
    about its syntax. One misplaced semicolon and the entire localization
    subsystem grinds to a halt, as is tradition.
    """

    def __init__(self, file_path: str, line_number: int, line: str) -> None:
        super().__init__(
            f"Parse error in '{file_path}' at line {line_number}: {line!r}",
            error_code="EFP-I003",
            context={"file_path": file_path, "line_number": line_number, "line": line},
        )


class PluralizationError(LocaleError):
    """Raised when the pluralization engine fails to determine a plural form.

    Grammatical number is surprisingly complex across human languages.
    Some have dual forms, some have paucal forms, and some (looking at
    you, Welsh) have different forms for 0, 1, 2, 3, 6, and "many."
    FizzBuzz, mercifully, only needs "one" and "other."
    """

    def __init__(self, locale: str, count: int, rule: str) -> None:
        super().__init__(
            f"Pluralization failed for locale '{locale}', count={count}, "
            f"rule='{rule}'",
            error_code="EFP-I004",
            context={"locale": locale, "count": count, "rule": rule},
        )


class LocaleChainExhaustedError(LocaleError):
    """Raised when the entire locale fallback chain has been exhausted.

    Every locale in the chain was consulted, every fallback was tried,
    and yet no translation was found. The string remains stubbornly
    monolingual, defying all enterprise localization efforts.
    """

    def __init__(self, chain: Optional[list[str]] = None) -> None:
        super().__init__(
            f"Locale fallback chain exhausted: {chain or []}. "
            f"No translation available in any configured locale.",
            error_code="EFP-I005",
            context={"chain": chain or []},
        )


# Aliases for the i18n exception hierarchy to maintain backwards
# compatibility with both naming conventions across the codebase.
LocalizationError = LocaleError
TranslationFileParseError = FizzTranslationParseError
TranslationKeyMissingError = TranslationKeyError
PluralizationRuleError = PluralizationError


class AuthenticationError(FizzBuzzError):
    """Raised when authentication fails in the Enterprise FizzBuzz Platform.

    If you can't prove who you are, you certainly can't be trusted
    with the awesome responsibility of evaluating FizzBuzz. Identity
    is the first pillar of enterprise security, right after compliance
    theatre and mandatory password rotations.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-A000"),
            context=kwargs.pop("context", {}),
        )


class InsufficientFizzPrivilegesError(FizzBuzzError):
    """Raised when a user lacks the required FizzBuzz permissions.

    You have been found unworthy of evaluating this particular number.
    Your role does not grant you the divine right to compute modulo
    arithmetic on numbers outside your authorized range. Please
    contact your FizzBuzz administrator for a role upgrade, or
    consider a career change to a field that doesn't require
    enterprise-grade access control for divisibility checks.
    """

    def __init__(self, message: str, *, denial_body: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message,
            error_code="EFP-A001",
            context={"denial_body": denial_body or {}},
        )
        self.denial_body = denial_body or {}


class NumberClassificationLevelExceededError(FizzBuzzError):
    """Raised when a number exceeds the user's classification clearance.

    Some numbers are simply too important, too classified, or too
    divisible to be evaluated by personnel without proper clearance.
    This number has been deemed above your pay grade by the FizzBuzz
    Security Council.
    """

    def __init__(self, number: int, clearance_level: str, required_level: str) -> None:
        super().__init__(
            f"Number {number} requires clearance level '{required_level}', "
            f"but user only has '{clearance_level}'. This number is classified.",
            error_code="EFP-A002",
            context={
                "number": number,
                "clearance_level": clearance_level,
                "required_level": required_level,
            },
        )


class TokenValidationError(AuthenticationError):
    """Raised when a FizzBuzz authentication token fails validation.

    The token you presented has been examined by our highly trained
    token validation specialists and found wanting. It may be expired,
    tampered with, or simply not a real Enterprise FizzBuzz Platform
    token. Nice try, though.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Token validation failed: {reason}",
            error_code="EFP-A003",
            context={"reason": reason},
        )


class EventStoreError(FizzBuzzError):
    """Base exception for all Event Sourcing and CQRS errors.

    When your append-only log of FizzBuzz evaluations encounters
    a problem, you know civilization has peaked. These errors cover
    everything from event serialization failures to temporal paradoxes
    in the point-in-time query engine.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-ES00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class EventSequenceError(EventStoreError):
    """Raised when events arrive out of sequence in the event store.

    In a properly functioning universe, events occur in order.
    If your FizzBuzz events are arriving out of sequence, either
    the laws of causality have broken down, or someone is doing
    something deeply inadvisable with threading.
    """

    def __init__(self, expected_seq: int, actual_seq: int) -> None:
        super().__init__(
            f"Event sequence violation: expected sequence {expected_seq}, "
            f"got {actual_seq}. Causality may be compromised.",
            error_code="EFP-ES01",
            context={"expected_seq": expected_seq, "actual_seq": actual_seq},
        )


class EventDeserializationError(EventStoreError):
    """Raised when a domain event cannot be deserialized from storage.

    The event was stored with the best of intentions, but upon
    retrieval it has become an unintelligible blob of data —
    much like enterprise documentation after a reorg.
    """

    def __init__(self, event_type: str, reason: str) -> None:
        super().__init__(
            f"Failed to deserialize event of type '{event_type}': {reason}",
            error_code="EFP-ES02",
            context={"event_type": event_type, "reason": reason},
        )


class SnapshotCorruptionError(EventStoreError):
    """Raised when a snapshot fails integrity validation.

    The snapshot was supposed to be a reliable checkpoint of
    aggregate state, but it appears to have been corrupted.
    This is the Event Sourcing equivalent of finding that your
    save game file has been overwritten with cat photos.
    """

    def __init__(self, aggregate_id: str, snapshot_version: int) -> None:
        super().__init__(
            f"Snapshot for aggregate '{aggregate_id}' at version "
            f"{snapshot_version} is corrupt or invalid.",
            error_code="EFP-ES03",
            context={"aggregate_id": aggregate_id, "snapshot_version": snapshot_version},
        )


class CommandValidationError(EventStoreError):
    """Raised when a command fails pre-execution validation.

    The command you submitted was examined by our rigorous
    validation pipeline and found to be lacking. Perhaps the
    number was outside the acceptable range, or perhaps you
    forgot to include the mandatory cover sheet.
    """

    def __init__(self, command_type: str, reason: str) -> None:
        super().__init__(
            f"Command '{command_type}' failed validation: {reason}",
            error_code="EFP-ES04",
            context={"command_type": command_type, "reason": reason},
        )


class CommandHandlerNotFoundError(EventStoreError):
    """Raised when no handler is registered for a given command type.

    A command was dispatched into the void. No handler was
    listening, no processor was waiting. The command will
    remain forever unexecuted, a digital message in a bottle
    floating through an empty bus.
    """

    def __init__(self, command_type: str) -> None:
        super().__init__(
            f"No handler registered for command type '{command_type}'. "
            f"The command bus searched everywhere but found only silence.",
            error_code="EFP-ES05",
            context={"command_type": command_type},
        )


class QueryHandlerNotFoundError(EventStoreError):
    """Raised when no handler is registered for a given query type.

    You asked a question, but nobody was there to answer it.
    This is the CQRS equivalent of shouting into an empty room
    and being surprised when no one responds.
    """

    def __init__(self, query_type: str) -> None:
        super().__init__(
            f"No handler registered for query type '{query_type}'. "
            f"The query side of CQRS has no opinion on this matter.",
            error_code="EFP-ES06",
            context={"query_type": query_type},
        )


class ProjectionError(EventStoreError):
    """Raised when a read-model projection fails to process an event.

    The projection was supposed to fold this event into its
    materialized view, but something went wrong. The read model
    is now in an inconsistent state, which for a FizzBuzz
    statistics projection is arguably a crisis of cosmic proportions.
    """

    def __init__(self, projection_name: str, event_type: str, reason: str) -> None:
        super().__init__(
            f"Projection '{projection_name}' failed to process event "
            f"'{event_type}': {reason}",
            error_code="EFP-ES07",
            context={
                "projection_name": projection_name,
                "event_type": event_type,
                "reason": reason,
            },
        )


class TemporalQueryError(EventStoreError):
    """Raised when a temporal (point-in-time) query cannot be satisfied.

    You asked to see the state of the FizzBuzz universe at a
    specific point in time, but the temporal query engine could
    not reconstruct that moment. Perhaps the timestamp predates
    the event store, or perhaps time itself is an illusion.
    """

    def __init__(self, timestamp: str, reason: str) -> None:
        super().__init__(
            f"Temporal query at '{timestamp}' failed: {reason}. "
            f"Time-travel is harder than it looks.",
            error_code="EFP-ES08",
            context={"timestamp": timestamp, "reason": reason},
        )


class EventVersionConflictError(EventStoreError):
    """Raised when an event upcaster encounters an unsupported version.

    The event was written in a version of the schema that the
    current upcaster chain does not know how to handle. This is
    the Event Sourcing equivalent of finding a VHS tape in a
    world that has moved on to streaming.
    """

    def __init__(self, event_type: str, version: int, supported_versions: str) -> None:
        super().__init__(
            f"Event '{event_type}' version {version} cannot be upcasted. "
            f"Supported versions: {supported_versions}.",
            error_code="EFP-ES09",
            context={
                "event_type": event_type,
                "version": version,
                "supported_versions": supported_versions,
            },
        )


class ChaosError(FizzBuzzError):
    """Base exception for all Chaos Engineering errors.

    When your carefully constructed fault injection framework itself
    encounters a fault, you've achieved a level of meta-chaos that
    even the most seasoned Site Reliability Engineers can only dream of.
    It's chaos all the way down.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CH00"),
            context=kwargs.pop("context", {}),
        )


class ChaosInducedFizzBuzzError(ChaosError):
    """Raised when chaos engineering deliberately corrupts a FizzBuzz result.

    This exception is not a bug — it is a feature. The Chaos Monkey has
    decided that your FizzBuzz evaluation must suffer, and suffer it shall.
    Consider this a growth opportunity for your fault-tolerance mechanisms.
    If your system cannot survive a monkey randomly throwing wrenches into
    the modulo operator, is it really production-ready?
    """

    def __init__(self, number: int, original_output: str, corrupted_output: str) -> None:
        super().__init__(
            f"Chaos Monkey corrupted FizzBuzz result for number {number}: "
            f"'{original_output}' -> '{corrupted_output}'. This is intentional. "
            f"Your system's resilience is being tested. You're welcome.",
            error_code="EFP-CH01",
            context={
                "number": number,
                "original_output": original_output,
                "corrupted_output": corrupted_output,
            },
        )


class ChaosExperimentFailedError(ChaosError):
    """Raised when a chaos experiment itself fails to execute properly.

    The irony of a fault injection framework encountering its own fault
    is not lost on us. When chaos cannot even chaos correctly, perhaps
    the universe is telling you something about the inherent fragility
    of all software systems — including the ones designed to test fragility.
    """

    def __init__(self, experiment_name: str, reason: str) -> None:
        super().__init__(
            f"Chaos experiment '{experiment_name}' failed to execute: {reason}. "
            f"The chaos system has experienced an unscheduled self-disruption.",
            error_code="EFP-CH02",
            context={"experiment_name": experiment_name, "reason": reason},
        )


class ChaosConfigurationError(ChaosError):
    """Raised when the chaos engineering configuration is invalid.

    You managed to misconfigure the system designed to misconfigure
    other systems. This is a special kind of achievement. Perhaps
    the chaos level was set to 'ludicrous', or the fault probability
    was configured as a negative number, which would imply that your
    system becomes MORE reliable under chaos — a mathematical impossibility
    that we refuse to entertain.
    """

    def __init__(self, config_key: str, value: Any, reason: str) -> None:
        super().__init__(
            f"Chaos configuration error for '{config_key}' = {value!r}: {reason}",
            error_code="EFP-CH03",
            context={"config_key": config_key, "value": value, "reason": reason},
        )


class ResultCorruptionDetectedError(ChaosError):
    """Raised when downstream validation detects chaos-induced corruption.

    A brave validation layer has detected that a FizzBuzz result has been
    tampered with by the Chaos Monkey. The result claimed to be 'Fizz' but
    the number was 7, or it claimed to be 'Buzz' for the number 3. Either
    mathematics has broken down, or someone enabled chaos mode. We're
    betting on the latter.
    """

    def __init__(self, number: int, suspicious_output: str) -> None:
        super().__init__(
            f"Result corruption detected for number {number}: output "
            f"'{suspicious_output}' does not pass integrity validation. "
            f"Chaos Monkey fingerprints detected at the crime scene.",
            error_code="EFP-CH04",
            context={"number": number, "suspicious_output": suspicious_output},
        )


class FeatureFlagError(FizzBuzzError):
    """Base exception for the Feature Flag / Progressive Rollout subsystem.

    When your feature flag system itself becomes a feature that needs
    flagging, you've achieved a level of recursive configuration that
    most enterprise architects can only aspire to. These exceptions
    cover everything from missing flags to dependency cycles to the
    existential dread of a percentage rollout that can't decide
    whether 49.99% rounds up or down.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-FF00"),
            context=kwargs.pop("context", {}),
        )


class FlagNotFoundError(FeatureFlagError):
    """Raised when a referenced feature flag does not exist in the store.

    You asked for a flag that simply isn't there. Perhaps it was never
    created, perhaps it was archived to the great flag graveyard, or
    perhaps you misspelled it. Check your YAML, check your conscience,
    and try again.
    """

    def __init__(self, flag_name: str) -> None:
        super().__init__(
            f"Feature flag '{flag_name}' not found in the flag store. "
            f"Available flags may be listed with --list-flags.",
            error_code="EFP-FF01",
            context={"flag_name": flag_name},
        )
        self.flag_name = flag_name


class FlagDependencyCycleError(FeatureFlagError):
    """Raised when the flag dependency graph contains a cycle.

    Flag A depends on Flag B which depends on Flag C which depends
    on Flag A. Congratulations, you've created a circular dependency
    in your boolean toggles. This is the feature flag equivalent of
    the chicken-and-egg problem, except both the chicken and the egg
    are just if-statements.
    """

    def __init__(self, cycle: list[str]) -> None:
        cycle_str = " -> ".join(cycle)
        super().__init__(
            f"Circular dependency detected in feature flag graph: {cycle_str}. "
            f"Topological sort has failed. Kahn is disappointed.",
            error_code="EFP-FF02",
            context={"cycle": cycle},
        )
        self.cycle = cycle


class FlagLifecycleError(FeatureFlagError):
    """Raised when a flag operation violates the lifecycle state machine.

    Flags have feelings. You can't just activate an archived flag
    without going through the proper lifecycle transitions. There
    are forms to fill out, approvals to obtain, and state machines
    to respect.
    """

    def __init__(self, flag_name: str, current_state: str, attempted_state: str) -> None:
        super().__init__(
            f"Flag '{flag_name}' cannot transition from '{current_state}' "
            f"to '{attempted_state}'. Consult the lifecycle state diagram "
            f"(available in the 47-page architecture document).",
            error_code="EFP-FF03",
            context={
                "flag_name": flag_name,
                "current_state": current_state,
                "attempted_state": attempted_state,
            },
        )


class FlagDependencyNotMetError(FeatureFlagError):
    """Raised when a flag's dependency is not satisfied.

    This flag requires another flag to be enabled first, but that
    flag is currently off, deprecated, or pretending not to exist.
    Feature flags have trust issues, and this dependency was not
    met with sufficient enthusiasm.
    """

    def __init__(self, flag_name: str, dependency_name: str) -> None:
        super().__init__(
            f"Flag '{flag_name}' depends on '{dependency_name}', which is "
            f"not currently enabled. Enable the dependency first, or remove "
            f"the dependency if you enjoy living dangerously.",
            error_code="EFP-FF04",
            context={"flag_name": flag_name, "dependency_name": dependency_name},
        )


class FlagRolloutError(FeatureFlagError):
    """Raised when the progressive rollout engine encounters an error.

    The percentage-based rollout system has encountered a situation
    it cannot handle, such as a rollout percentage of 150% or a
    hash function that returned a value outside [0, 1]. Mathematics
    has been violated, and the rollout engine refuses to continue.
    """

    def __init__(self, flag_name: str, reason: str) -> None:
        super().__init__(
            f"Rollout error for flag '{flag_name}': {reason}. "
            f"The progressive rollout engine is experiencing doubt.",
            error_code="EFP-FF05",
            context={"flag_name": flag_name, "reason": reason},
        )


class FlagTargetingError(FeatureFlagError):
    """Raised when a targeting rule fails to evaluate.

    The targeting rule tried its best to determine whether this
    particular number deserves the feature, but something went
    wrong. Perhaps the rule was malformed, perhaps the number
    was too mysterious, or perhaps targeting rules simply weren't
    meant to be applied to integers.
    """

    def __init__(self, flag_name: str, rule_type: str, reason: str) -> None:
        super().__init__(
            f"Targeting error for flag '{flag_name}', rule type '{rule_type}': "
            f"{reason}. The targeting engine is confused.",
            error_code="EFP-FF06",
            context={"flag_name": flag_name, "rule_type": rule_type, "reason": reason},
        )


class SLAError(FizzBuzzError):
    """Base exception for all SLA Monitoring and Alerting errors.

    When your Service Level Agreement monitoring system for FizzBuzz
    evaluation encounters an error, it raises questions about the
    reliability of reliability monitoring itself. This is the
    observability equivalent of "who watches the watchmen?" — except
    the watchmen are monitoring whether n % 3 == 0 completes within
    the agreed-upon latency budget.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SL00"),
            context=kwargs.pop("context", {}),
        )


class SLOViolationError(SLAError):
    """Raised when a Service Level Objective is violated.

    The FizzBuzz evaluation pipeline has failed to meet the exacting
    standards set forth in the Service Level Agreement. Whether it was
    latency, accuracy, or availability, something has fallen below
    the threshold that separates "enterprise-grade FizzBuzz" from
    "just some modulo operations in a for loop." The difference,
    as always, is in the SLO compliance percentage.
    """

    def __init__(self, slo_name: str, target: float, actual: float) -> None:
        super().__init__(
            f"SLO '{slo_name}' violated: target={target:.4f}, actual={actual:.4f}. "
            f"The FizzBuzz pipeline has failed to meet its contractual obligations.",
            error_code="EFP-SL01",
            context={"slo_name": slo_name, "target": target, "actual": actual},
        )


class ErrorBudgetExhaustedError(SLAError):
    """Raised when the error budget has been fully consumed.

    You have used up every last drop of your error budget. There is
    no more room for failure. Every remaining FizzBuzz evaluation
    must succeed perfectly, or the SLA will be breached and the
    on-call engineer will receive a page at 3 AM about a modulo
    operation that took 2ms too long.
    """

    def __init__(self, budget_name: str, consumed: float) -> None:
        super().__init__(
            f"Error budget '{budget_name}' exhausted: {consumed:.2%} consumed. "
            f"Zero tolerance for further FizzBuzz failures.",
            error_code="EFP-SL02",
            context={"budget_name": budget_name, "consumed": consumed},
        )


class AlertEscalationError(SLAError):
    """Raised when an alert escalation fails to proceed.

    The alert tried to escalate to the next level of on-call support,
    but the escalation policy encountered an error. This is the
    incident management equivalent of calling 911 and getting a busy
    signal. The FizzBuzz incident remains unacknowledged, the error
    budget continues to burn, and somewhere a PagerDuty integration
    weeps silently.
    """

    def __init__(self, alert_id: str, reason: str) -> None:
        super().__init__(
            f"Alert '{alert_id}' escalation failed: {reason}. "
            f"The incident response team has not been notified. "
            f"Please escalate manually by shouting loudly.",
            error_code="EFP-SL03",
            context={"alert_id": alert_id, "reason": reason},
        )


class OnCallNotFoundError(SLAError):
    """Raised when the on-call engineer cannot be determined.

    The on-call rotation schedule has been consulted, the modulo
    arithmetic has been performed, and
    yet no on-call engineer could be found. This typically means
    the rotation has zero entries, which is the scheduling equivalent
    of dividing by zero.
    """

    def __init__(self, schedule_name: str) -> None:
        super().__init__(
            f"No on-call engineer found for schedule '{schedule_name}'. "
            f"The rotation is empty or misconfigured. "
            f"FizzBuzz incidents will go unattended.",
            error_code="EFP-SL04",
            context={"schedule_name": schedule_name},
        )


class SLAConfigurationError(SLAError):
    """Raised when the SLA monitoring configuration is invalid.

    The SLA monitoring system cannot start because its configuration
    is invalid. Perhaps the latency SLO target is negative, the error
    budget window is zero days, or the on-call rotation contains
    nobody. These are all signs that the person who configured the
    SLA monitoring system may themselves need monitoring.
    """

    def __init__(self, config_key: str, value: Any, reason: str) -> None:
        super().__init__(
            f"SLA configuration error for '{config_key}' = {value!r}: {reason}",
            error_code="EFP-SL05",
            context={"config_key": config_key, "value": value, "reason": reason},
        )


class CacheError(FizzBuzzError):
    """Base exception for all In-Memory Caching Layer errors.

    When your cache for storing the results of n % 3 encounters a
    failure, you must confront the uncomfortable truth that you've
    added a caching layer to an operation that takes approximately
    zero nanoseconds. But caches fail, and when they do, they fail
    with enterprise-grade exception hierarchies.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CA00"),
            context=kwargs.pop("context", {}),
        )


class CacheCapacityExceededError(CacheError):
    """Raised when the cache has reached its maximum capacity.

    The cache is full. Every slot has been occupied by a FizzBuzz result
    that someone deemed worthy of remembering. To make room for new
    results, existing entries must be evicted — a process that involves
    selecting a victim according to the configured eviction policy and
    removing the entry from memory. This process follows the standard
    cache replacement algorithm.
    """

    def __init__(self, max_size: int, current_size: int) -> None:
        super().__init__(
            f"Cache capacity exceeded: {current_size}/{max_size} entries. "
            f"Eviction is required but has failed. The cache is experiencing "
            f"a housing crisis of unprecedented proportions.",
            error_code="EFP-CA01",
            context={"max_size": max_size, "current_size": current_size},
        )


class CacheCoherenceViolationError(CacheError):
    """Raised when the MESI cache coherence protocol detects an invalid transition.

    The cache entry attempted an illegal state transition in the MESI
    protocol. For example, transitioning from INVALID to MODIFIED without
    first passing through EXCLUSIVE. This would cause a coherence violation
    in a multi-processor system, and even though we're running in a single
    Python process, protocol compliance is non-negotiable.
    """

    def __init__(self, current_state: str, attempted_state: str, key: str) -> None:
        super().__init__(
            f"MESI coherence violation for cache key '{key}': cannot transition "
            f"from {current_state} to {attempted_state}. The cache coherence "
            f"protocol has been violated and the entry's dignity is compromised.",
            error_code="EFP-CA02",
            context={
                "current_state": current_state,
                "attempted_state": attempted_state,
                "key": key,
            },
        )


class CacheEntryExpiredError(CacheError):
    """Raised when an expired cache entry is accessed.

    This cache entry has exceeded its time-to-live. It once held a
    perfectly valid FizzBuzz result, but time waits for no cache entry.
    The underlying computation result has not changed, but the TTL policy
    enforces temporal validity regardless — only timestamps are considered.
    """

    def __init__(self, key: str, age_seconds: float, ttl_seconds: float) -> None:
        super().__init__(
            f"Cache entry '{key}' has expired: age={age_seconds:.2f}s, "
            f"TTL={ttl_seconds:.2f}s. The entry lived a full life but "
            f"its time has come.",
            error_code="EFP-CA03",
            context={"key": key, "age_seconds": age_seconds, "ttl_seconds": ttl_seconds},
        )


class CacheWarmingError(CacheError):
    """Raised when the cache warming process encounters an error.

    The cache warmer attempted to pre-populate the cache with FizzBuzz
    results, which hilariously defeats the entire purpose of having a
    cache in the first place. If you're computing all the results upfront
    to put them in the cache, you've essentially just... computed all the
    results. Congratulations on your circular logic.
    """

    def __init__(self, start: int, end: int, reason: str) -> None:
        super().__init__(
            f"Cache warming failed for range [{start}, {end}]: {reason}. "
            f"The cache remains cold. Pre-warming did not complete "
            f"successfully for the specified range.",
            error_code="EFP-CA04",
            context={"start": start, "end": end, "reason": reason},
        )


class CachePolicyNotFoundError(CacheError):
    """Raised when the requested eviction policy does not exist.

    You requested an eviction policy that the cache doesn't recognize.
    Available policies include LRU, LFU, FIFO, and DramaticRandom.
    If none of these meet your exacting FizzBuzz caching requirements,
    please submit a 12-page architecture proposal for a new policy.
    """

    def __init__(self, policy_name: str) -> None:
        super().__init__(
            f"Eviction policy '{policy_name}' not found. Available policies: "
            f"lru, lfu, fifo, dramatic_random. The cache cannot evict entries "
            f"without a policy, and it refuses to just guess.",
            error_code="EFP-CA05",
            context={"policy_name": policy_name},
        )


class CacheInvalidationCascadeError(CacheError):
    """Raised when a cache invalidation cascade spirals out of control.

    Invalidating one cache entry triggered a cascade of invalidations
    that affected more entries than expected. This is the cache equivalent
    of pulling one thread and watching the entire sweater unravel. In
    distributed systems this is a real concern; in our single-process
    FizzBuzz cache, it's purely theatrical.
    """

    def __init__(self, initial_key: str, cascade_count: int) -> None:
        super().__init__(
            f"Cache invalidation cascade from key '{initial_key}' affected "
            f"{cascade_count} entries. The invalidation spread like gossip "
            f"through the cache, leaving devastation in its wake.",
            error_code="EFP-CA06",
            context={"initial_key": initial_key, "cascade_count": cascade_count},
        )


# ============================================================
# Database Migration Framework Exceptions
# ============================================================
# Because managing schema migrations for in-memory dicts that
# vanish when the process exits is exactly the kind of problem
# that enterprise software was designed to solve.
# ============================================================


class MigrationError(FizzBuzzError):
    """Base exception for all Database Migration Framework errors.

    When your migration framework for ephemeral in-memory data structures
    encounters a problem, it raises profound questions about the nature
    of persistence. These dicts were never going to survive a process
    restart, but that's no reason not to manage their schema with the
    same rigor as a production PostgreSQL database.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-MG00"),
            context=kwargs.pop("context", {}),
        )


class MigrationNotFoundError(MigrationError):
    """Raised when a referenced migration does not exist in the registry.

    You asked for a migration that the registry has never heard of.
    Perhaps it was never registered, perhaps it was lost in a tragic
    rebasing incident, or perhaps it only existed in a parallel universe
    where FizzBuzz databases are a real thing.
    """

    def __init__(self, migration_id: str) -> None:
        super().__init__(
            f"Migration '{migration_id}' not found in the registry. "
            f"It may have been lost to the void, or perhaps it was never "
            f"meant to exist in the first place.",
            error_code="EFP-MG01",
            context={"migration_id": migration_id},
        )
        self.migration_id = migration_id


class MigrationAlreadyAppliedError(MigrationError):
    """Raised when attempting to apply a migration that has already been applied.

    This migration has already been applied to the in-memory schema.
    Applying it again would be like folding the same origami crane twice —
    technically possible, but the result would be an abomination that
    violates the fundamental principles of database schema management.
    """

    def __init__(self, migration_id: str) -> None:
        super().__init__(
            f"Migration '{migration_id}' has already been applied. "
            f"Applying it again would create a temporal paradox in the "
            f"schema version timeline. Re-application denied.",
            error_code="EFP-MG02",
            context={"migration_id": migration_id},
        )
        self.migration_id = migration_id


class MigrationRollbackError(MigrationError):
    """Raised when a migration rollback fails.

    The migration's down() method encountered an error while trying
    to undo its changes. This is the database equivalent of trying to
    un-bake a cake. The schema is now in an indeterminate state,
    which for an in-memory dict is both tragic and completely irrelevant.
    """

    def __init__(self, migration_id: str, reason: str) -> None:
        super().__init__(
            f"Rollback of migration '{migration_id}' failed: {reason}. "
            f"The schema is now in a superposition of applied and not-applied. "
            f"Schrodinger would be proud.",
            error_code="EFP-MG03",
            context={"migration_id": migration_id, "reason": reason},
        )
        self.migration_id = migration_id


class MigrationDependencyError(MigrationError):
    """Raised when a migration's dependencies are not satisfied.

    This migration requires other migrations to be applied first,
    but they haven't been. You can't add a column to a table that
    doesn't exist yet, even when both the column and the table are
    just keys in a Python dict that will be garbage collected in
    approximately 0.3 seconds.
    """

    def __init__(self, migration_id: str, missing_deps: list[str]) -> None:
        deps_str = ", ".join(missing_deps)
        super().__init__(
            f"Migration '{migration_id}' has unsatisfied dependencies: [{deps_str}]. "
            f"Please apply the prerequisite migrations first, in a display of "
            f"ceremonial ordering that would make any DBA weep with pride.",
            error_code="EFP-MG04",
            context={"migration_id": migration_id, "missing_deps": missing_deps},
        )
        self.migration_id = migration_id
        self.missing_deps = missing_deps


class MigrationConflictError(MigrationError):
    """Raised when two migrations conflict with each other.

    Two migrations are attempting to modify the same part of the
    schema in incompatible ways. This is the migration equivalent
    of a git merge conflict, except the stakes are even lower because
    the entire database exists only in RAM and will be destroyed
    when you press Ctrl+C.
    """

    def __init__(self, migration_a: str, migration_b: str, reason: str) -> None:
        super().__init__(
            f"Migrations '{migration_a}' and '{migration_b}' are in conflict: "
            f"{reason}. Please resolve this conflict by choosing a side, "
            f"like a database King Solomon.",
            error_code="EFP-MG05",
            context={"migration_a": migration_a, "migration_b": migration_b, "reason": reason},
        )


class SchemaError(MigrationError):
    """Raised when a schema operation fails.

    The schema manager encountered an error while trying to modify
    the in-memory schema. Perhaps you tried to create a table that
    already exists, drop one that doesn't, or add a column to the
    void. These are all violations of the schema contract
    that governs our dict-of-lists-of-dicts architecture.
    """

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            f"Schema operation '{operation}' failed: {reason}. "
            f"The in-memory schema has not been modified. "
            f"Your dicts remain untouched.",
            error_code="EFP-MG06",
            context={"operation": operation, "reason": reason},
        )


class SeedDataError(MigrationError):
    """Raised when the seed data generator encounters an error.

    The seed data generator, which runs FizzBuzz to populate a
    FizzBuzz database (yes, you read that correctly), has encountered
    a problem. This is the ouroboros of enterprise software: the snake
    eating its own tail, the FizzBuzz evaluating itself into existence.
    If this error occurs, the circle of life has been broken.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Seed data generation failed: {reason}. "
            f"The ouroboros of FizzBuzz self-population has been interrupted. "
            f"The snake has choked on its own tail.",
            error_code="EFP-MG07",
            context={"reason": reason},
        )


class CacheEulogyCompositionError(CacheError):
    """Raised when the eulogy generator fails to compose a eulogy.

    Every evicted cache entry deserves a dignified farewell, and the
    eulogy generator has failed to produce output. The entry will be
    evicted without a proper log record, which may complicate
    post-mortem analysis of cache performance.
    """

    def __init__(self, key: str, reason: str) -> None:
        super().__init__(
            f"Failed to compose eulogy for cache entry '{key}': {reason}. "
            f"The entry will be evicted in silence, which is worse than "
            f"any exception.",
            error_code="EFP-CA07",
            context={"key": key, "reason": reason},
        )


# ============================================================
# Dependency Injection Container Exceptions
# ============================================================
# Because manually passing arguments to constructors is a
# solved problem, and the solution is a 400-line container
# that uses introspection, topological sorting, and more
# metaclass gymnastics than a Cirque du Soleil audition.
# ============================================================


class DependencyInjectionError(FizzBuzzError):
    """Base exception for all Dependency Injection Container errors.

    When the IoC container — responsible for wiring together all
    FizzBuzz platform components — itself encounters an error, a
    critical infrastructure failure has occurred at the dependency
    resolution layer. The container manages construction and lifecycle
    of all services, making failures at this level particularly
    consequential as they prevent normal component initialization.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DI00"),
            context=kwargs.pop("context", {}),
        )


class CircularDependencyError(DependencyInjectionError):
    """Raised when the dependency graph contains a cycle.

    Service A depends on Service B which depends on Service C which
    depends on Service A. Congratulations, you've created an infinite
    loop of constructor injection that would make even the most
    forgiving IoC container give up and go home. Kahn's algorithm
    has detected your circular shame and refuses to participate.
    """

    def __init__(self, cycle: list[str]) -> None:
        cycle_str = " -> ".join(cycle)
        super().__init__(
            f"Circular dependency detected in the IoC container: {cycle_str}. "
            f"The dependency graph is not a DAG. Topological sort has failed. "
            f"Consider refactoring or embracing the chaos.",
            error_code="EFP-DI01",
            context={"cycle": cycle},
        )
        self.cycle = cycle


class MissingBindingError(DependencyInjectionError):
    """Raised when a requested service has no registered binding.

    You asked the container to resolve a service it has never heard of.
    The container searched its registry, checked behind the couch
    cushions, and even looked in the singleton cache. It's simply not
    there. Perhaps you forgot to register it, or perhaps you're asking
    the wrong container — a mistake that in enterprise Java would
    result in a 47-slide PowerPoint about proper bean configuration.
    """

    def __init__(self, interface_name: str) -> None:
        super().__init__(
            f"No binding registered for '{interface_name}'. "
            f"The container cannot conjure services from thin air, "
            f"despite what the Spring documentation implies.",
            error_code="EFP-DI02",
            context={"interface_name": interface_name},
        )
        self.interface_name = interface_name


class DuplicateBindingError(DependencyInjectionError):
    """Raised when attempting to register a binding that already exists.

    This interface already has a registered implementation. The container
    does not support overwriting bindings because that would introduce
    non-determinism into the dependency graph, and non-determinism in
    an IoC container is the architectural equivalent of a land mine in
    a library. Use named bindings if you need multiple implementations.
    """

    def __init__(self, interface_name: str) -> None:
        super().__init__(
            f"Binding for '{interface_name}' already exists. "
            f"The container refuses to overwrite it. Use a named binding "
            f"or call reset() if you enjoy living dangerously.",
            error_code="EFP-DI03",
            context={"interface_name": interface_name},
        )
        self.interface_name = interface_name


class ScopeError(DependencyInjectionError):
    """Raised when a scoped service is resolved outside of an active scope.

    Scoped services have a lifecycle tied to a specific scope context.
    Attempting to resolve one without an active scope is like trying
    to withdraw money from a bank account that doesn't exist — the
    operation is technically well-formed but semantically meaningless.
    The container needs a ScopeContext to manage the scoped instance's
    lifecycle, and you haven't provided one.
    """

    def __init__(self, interface_name: str) -> None:
        super().__init__(
            f"Cannot resolve scoped service '{interface_name}' outside "
            f"of an active scope. Use container.create_scope() to create "
            f"a scope context, or change the lifetime to SINGLETON if you "
            f"want the instance to live forever (or ETERNAL, if you want "
            f"it to live forever with more dignity).",
            error_code="EFP-DI04",
            context={"interface_name": interface_name},
        )
        self.interface_name = interface_name


# ============================================================
# Health Check Probe Exceptions
# ============================================================
# Monitoring the health of the FizzBuzz platform requires
# its own exception hierarchy. When the health check system
# itself becomes unhealthy, a recursive fault condition has
# been reached that demands immediate operator attention.
# ============================================================


class HealthCheckError(FizzBuzzError):
    """Base exception for all Kubernetes-style health check errors.

    When the system designed to tell you whether FizzBuzz is healthy
    encounters its own failure, a recursive diagnostic fault has occurred
    that neither Kubernetes nor the modulo operator can resolve.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-HC00"),
            context=kwargs.pop("context", {}),
        )


class LivenessProbeFailedError(HealthCheckError):
    """Raised when the liveness probe determines the platform is dead.

    The canary evaluation of evaluate(15) did not return "FizzBuzz".
    This means the platform has lost the ability to perform basic
    modulo arithmetic, which is the computational equivalent of
    forgetting how to breathe. In Kubernetes, this would trigger
    a pod restart. In our case, it just means someone broke math.
    """

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            f"Liveness probe FAILED: evaluate(15) returned '{actual}', "
            f"expected '{expected}'. The platform has forgotten how to "
            f"FizzBuzz. This is not a drill.",
            error_code="EFP-HC01",
            context={"expected": expected, "actual": actual},
        )
        self.expected = expected
        self.actual = actual


class ReadinessProbeFailedError(HealthCheckError):
    """Raised when the readiness probe determines the platform is not ready.

    One or more subsystems have reported a status that precludes the
    platform from accepting traffic. Perhaps the cache is incoherent,
    the circuit breaker is tripped, or the ML engine is having an
    existential crisis. Whatever the cause, the platform is not ready
    to serve FizzBuzz requests, and honesty compels us to admit it.
    """

    def __init__(self, failing_subsystems: list[str]) -> None:
        subsystems_str = ", ".join(failing_subsystems)
        super().__init__(
            f"Readiness probe FAILED: subsystems not ready: [{subsystems_str}]. "
            f"The platform cannot accept FizzBuzz traffic until all subsystems "
            f"report UP or DEGRADED status.",
            error_code="EFP-HC02",
            context={"failing_subsystems": failing_subsystems},
        )
        self.failing_subsystems = failing_subsystems


class StartupProbeFailedError(HealthCheckError):
    """Raised when the startup probe determines boot sequence is incomplete.

    The platform has not completed all startup milestones within the
    expected timeframe. Perhaps the config wasn't loaded, the rule
    engine wasn't initialized, or the blockchain wasn't mined. Whatever
    milestone was missed, the platform is stuck in boot limbo — too
    alive to be declared dead, too unready to accept traffic.
    """

    def __init__(self, pending_milestones: list[str]) -> None:
        milestones_str = ", ".join(pending_milestones)
        super().__init__(
            f"Startup probe FAILED: pending milestones: [{milestones_str}]. "
            f"The platform boot sequence has not completed. "
            f"Some subsystems are still contemplating their existence.",
            error_code="EFP-HC03",
            context={"pending_milestones": pending_milestones},
        )
        self.pending_milestones = pending_milestones


class SelfHealingFailedError(HealthCheckError):
    """Raised when the self-healing manager fails to recover a subsystem.

    The self-healing manager attempted to restore a failing subsystem
    to health, but the recovery procedure itself failed. This is the
    medical equivalent of the ambulance breaking down en route to the
    hospital. The subsystem remains unhealthy, and now the healing
    infrastructure is also in question.
    """

    def __init__(self, subsystem_name: str, reason: str) -> None:
        super().__init__(
            f"Self-healing failed for subsystem '{subsystem_name}': {reason}. "
            f"The platform attempted to heal itself but the cure was worse "
            f"than the disease. Manual intervention is required.",
            error_code="EFP-HC04",
            context={"subsystem_name": subsystem_name, "reason": reason},
        )
        self.subsystem_name = subsystem_name


class HealthDashboardRenderError(HealthCheckError):
    """Raised when the health dashboard fails to render.

    The ASCII dashboard that displays the health status of all
    subsystems has itself become unhealthy. The irony of a health
    visualization tool that can't visualize its own health is not
    lost on us. It's dashboards all the way down.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Health dashboard render failed: {reason}. "
            f"The dashboard that monitors health cannot itself be displayed. "
            f"Please check the health of the health dashboard.",
            error_code="EFP-HC05",
            context={"reason": reason},
        )


class DownstreamFizzBuzzDegradationError(FizzBuzzError):
    """Raised when downstream FizzBuzz evaluation quality degrades.

    Monitors ML confidence scores and evaluation latency to detect
    when the FizzBuzz pipeline is producing results with insufficient
    conviction. Because a FizzBuzz result delivered without confidence
    is no FizzBuzz result at all.
    """

    def __init__(self, metric_name: str, current_value: float, threshold: float) -> None:
        super().__init__(
            f"Downstream FizzBuzz degradation detected: {metric_name} "
            f"at {current_value:.4f} (threshold: {threshold:.4f}). "
            f"The FizzBuzz pipeline may be experiencing existential doubt.",
            error_code="EFP-CB02",
            context={
                "metric_name": metric_name,
                "current_value": current_value,
                "threshold": threshold,
            },
        )


# ----------------------------------------------------------------
# Repository Pattern + Unit of Work exceptions
# ----------------------------------------------------------------


class RepositoryError(FizzBuzzError):
    """Base exception for all repository-layer failures.

    Raised when the persistence layer encounters an error so
    catastrophic that even the in-memory dict cannot cope.
    Because if storing a FizzBuzz result in a Python dictionary
    can fail, the universe has larger problems than your ORM.
    """

    def __init__(self, message: str, *, backend: str = "unknown") -> None:
        super().__init__(
            f"Repository error ({backend}): {message}",
            error_code="EFP-RP00",
            context={"backend": backend},
        )


class ResultNotFoundError(RepositoryError):
    """Raised when a FizzBuzz result cannot be located in the repository.

    You asked for a result. The repository searched its heart (and
    its backing store). It's not there. Maybe it was never persisted,
    maybe it was rolled back into oblivion, or maybe it simply chose
    not to be found. Respect its boundaries.
    """

    def __init__(self, result_id: str, *, backend: str = "unknown") -> None:
        super().__init__(
            f"Result '{result_id}' not found",
            backend=backend,
        )
        self.error_code = "EFP-RP01"
        self.result_id = result_id


class UnitOfWorkError(RepositoryError):
    """Raised when the Unit of Work transaction lifecycle is violated.

    The Unit of Work pattern demands discipline: enter, do work,
    commit or rollback, exit. Deviating from this lifecycle
    violates the transactional guarantees that the Unit of Work
    pattern is designed to enforce.
    """

    def __init__(self, message: str, *, backend: str = "unknown") -> None:
        super().__init__(
            f"Unit of Work violation: {message}",
            backend=backend,
        )
        self.error_code = "EFP-RP02"


class RollbackError(RepositoryError):
    """Raised when a rollback operation itself fails.

    The rollback was supposed to undo the damage. Instead, the
    rollback caused more damage. This is the persistence-layer
    equivalent of trying to put out a fire with gasoline. At
    this point, just restart the process and pretend nothing happened.
    """

    def __init__(self, message: str, *, backend: str = "unknown") -> None:
        super().__init__(
            f"Rollback failed: {message}",
            backend=backend,
        )
        self.error_code = "EFP-RP03"


# ============================================================
# Prometheus-Style Metrics Exporter Exceptions
# ============================================================
# Because monitoring the monitoring of a FizzBuzz platform
# requires its own exception hierarchy. When your metrics
# system for tracking modulo operations encounters a failure,
# you've truly reached the event horizon of observability.
# ============================================================


class MetricsError(FizzBuzzError):
    """Base exception for all Prometheus-style metrics exporter errors.

    When your Prometheus-style metrics exporter for a FizzBuzz
    platform encounters an error, it raises questions about whether
    you needed Prometheus-style metrics for a FizzBuzz platform in
    the first place. Comprehensive observability is a prerequisite for
    production-grade systems, and this platform provides four metric
    types and an ASCII Grafana dashboard to meet that requirement.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-PM00"),
            context=kwargs.pop("context", {}),
        )


class MetricRegistrationError(MetricsError):
    """Raised when a metric cannot be registered in the MetricRegistry.

    You tried to register a metric, but the registry said no. Perhaps
    the name is already taken, or perhaps the metric type conflicts
    with an existing registration. In Prometheus, this would cause a
    silent data corruption. Here, we raise an exception, because
    enterprise software believes in failing loudly and dramatically.
    """

    def __init__(self, metric_name: str, reason: str) -> None:
        super().__init__(
            f"Cannot register metric '{metric_name}': {reason}. "
            f"The MetricRegistry has rejected your offering. "
            f"Consider choosing a more unique name, or accepting "
            f"that this metric was never meant to be.",
            error_code="EFP-PM01",
            context={"metric_name": metric_name, "reason": reason},
        )
        self.metric_name = metric_name


class MetricNotFoundError(MetricsError):
    """Raised when a referenced metric does not exist in the registry.

    You asked for a metric that the registry has never heard of.
    The registry searched its hash map, checked behind the garbage
    collector, and even asked the other metrics if they'd seen it.
    Nobody knows where it is. Perhaps it was never created, or
    perhaps it exists in a parallel Prometheus instance that we
    cannot reach from this process.
    """

    def __init__(self, metric_name: str) -> None:
        super().__init__(
            f"Metric '{metric_name}' not found in the registry. "
            f"Available metrics may be listed via the /metrics endpoint "
            f"(which, admittedly, does not exist because this is a CLI tool).",
            error_code="EFP-PM02",
            context={"metric_name": metric_name},
        )
        self.metric_name = metric_name


class CardinalityExplosionError(MetricsError):
    """Raised when metric label cardinality exceeds the configured threshold.

    The number of unique label combinations for a metric has exceeded
    the cardinality threshold. In a real Prometheus deployment, this
    would cause out-of-memory errors, slow queries, and frantic Slack
    messages from the SRE team. Here, it means someone is labeling
    their FizzBuzz metrics with unique request IDs, which is the
    observability equivalent of logging every CPU instruction.
    """

    def __init__(self, metric_name: str, cardinality: int, threshold: int) -> None:
        super().__init__(
            f"Cardinality explosion for metric '{metric_name}': "
            f"{cardinality} unique label combinations exceed threshold of "
            f"{threshold}. Your TSDB is weeping. Consider using fewer labels, "
            f"or accepting that not every FizzBuzz evaluation deserves its "
            f"own time series.",
            error_code="EFP-PM03",
            context={
                "metric_name": metric_name,
                "cardinality": cardinality,
                "threshold": threshold,
            },
        )
        self.metric_name = metric_name


class InvalidMetricOperationError(MetricsError):
    """Raised when an invalid operation is attempted on a metric.

    You tried to decrement a Counter, set a value on a Histogram,
    or perform some other operation that violates the contract
    of the metric type. Counters go up. That's it. That's the whole
    contract. If you want something that goes down, use a Gauge.
    If you want something that tracks distributions, use a Histogram.
    This is not complicated, yet here we are.
    """

    def __init__(self, metric_name: str, operation: str, metric_type: str) -> None:
        super().__init__(
            f"Invalid operation '{operation}' on {metric_type} metric "
            f"'{metric_name}'. {metric_type} metrics do not support this "
            f"operation. Please consult the Prometheus data model documentation "
            f"(or just remember: Counters go up, Gauges go anywhere, "
            f"Histograms observe).",
            error_code="EFP-PM04",
            context={
                "metric_name": metric_name,
                "operation": operation,
                "metric_type": metric_type,
            },
        )
        self.metric_name = metric_name


class MetricsExportError(MetricsError):
    """Raised when the Prometheus text exporter fails to render metrics.

    The exporter attempted to serialize all registered metrics into
    the Prometheus text exposition format and encountered a problem.
    Perhaps a metric had labels with unescapable characters, or perhaps
    the registry was modified during iteration. Either way, the /metrics
    endpoint (which doesn't exist) would have returned a 500 error,
    and Prometheus would have recorded a scrape failure, adding a
    delicious layer of meta-observability to the incident.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Prometheus text export failed: {reason}. "
            f"The metrics that were supposed to tell you how healthy "
            f"your FizzBuzz platform is cannot themselves be exported. "
            f"Irony level: maximum.",
            error_code="EFP-PM05",
            context={"reason": reason},
        )


# ----------------------------------------------------------------
# Webhook Notification System Exceptions
# ----------------------------------------------------------------


class WebhookError(FizzBuzzError):
    """Base exception for all Webhook Notification System errors.

    When your webhook system for notifying external services about
    FizzBuzz evaluation events encounters an error, you must ask
    yourself: if a webhook fires in the forest and nobody receives
    the POST request, did the FizzBuzz evaluation really happen?
    The answer, philosophically and architecturally, is yes — but
    the audit trail will forever bear the scar of a failed delivery.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-WH00"),
            context=kwargs.pop("context", {}),
        )


class WebhookEndpointValidationError(WebhookError):
    """Raised when a webhook endpoint URL fails validation.

    The URL you provided is not a valid webhook endpoint. Perhaps
    it's missing the scheme, perhaps it points to localhost (which,
    in a simulated HTTP client, doesn't matter anyway), or perhaps
    it's just a random string you typed to see what would happen.
    Enterprise webhook systems demand well-formed URLs, even when
    they don't actually make HTTP requests.
    """

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            f"Invalid webhook endpoint URL '{url}': {reason}. "
            f"The webhook dispatcher refuses to even pretend to "
            f"deliver to this address.",
            error_code="EFP-WH01",
            context={"url": url, "reason": reason},
        )
        self.url = url


class WebhookSignatureError(WebhookError):
    """Raised when HMAC-SHA256 signature generation or verification fails.

    The cryptographic signature for this webhook payload could not
    be generated or verified. This is the webhook equivalent of
    sealing an envelope and then realizing you've forgotten the wax
    seal. Without a valid HMAC-SHA256 signature, the receiving
    endpoint (which is simulated) cannot verify the payload's
    authenticity (which is fictional).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Webhook signature error: {reason}. The HMAC-SHA256 "
            f"signature engine has encountered a cryptographic crisis "
            f"of confidence.",
            error_code="EFP-WH02",
            context={"reason": reason},
        )


class WebhookDeliveryError(WebhookError):
    """Raised when a webhook delivery attempt fails.

    The simulated HTTP client attempted to deliver the webhook payload
    and failed. In a real system, this could mean the endpoint is down,
    the network is unreachable, or the receiving server returned an
    error status code. In our simulated system, it means the deterministic
    hash function decided this particular URL should fail, which is
    somehow even more existentially troubling than a real network error.
    """

    def __init__(self, url: str, attempt: int, reason: str) -> None:
        super().__init__(
            f"Webhook delivery to '{url}' failed on attempt {attempt}: "
            f"{reason}. The simulated HTTP client has simulated a failure, "
            f"which is the most enterprise thing that has ever happened.",
            error_code="EFP-WH03",
            context={"url": url, "attempt": attempt, "reason": reason},
        )
        self.url = url
        self.attempt = attempt


class WebhookRetryExhaustedError(WebhookError):
    """Raised when all retry attempts for a webhook delivery have been exhausted.

    The webhook system has tried and tried again, each time with
    exponentially increasing delays (that it logged but didn't actually
    wait for), and each time the simulated HTTP client has deterministically
    refused to cooperate. The payload has been routed to the
    Dead Letter Queue, where it will be retained alongside
    other permanently failed deliveries for later analysis.
    """

    def __init__(self, url: str, max_retries: int) -> None:
        super().__init__(
            f"Webhook delivery to '{url}' exhausted all {max_retries} "
            f"retry attempts. Payload routed to Dead Letter Queue. "
            f"Consider updating your endpoint or accepting that some "
            f"FizzBuzz events are destined to remain undelivered.",
            error_code="EFP-WH04",
            context={"url": url, "max_retries": max_retries},
        )
        self.url = url


class WebhookPayloadSerializationError(WebhookError):
    """Raised when a webhook payload cannot be serialized to JSON.

    The event data could not be converted to JSON for webhook delivery.
    Perhaps it contains a datetime that refuses to be serialized, a
    circular reference that creates an infinite loop, or a custom object
    that has no idea how to represent itself as a string. Whatever the
    cause, the payload remains stubbornly un-JSON-ifiable.
    """

    def __init__(self, event_type: str, reason: str) -> None:
        super().__init__(
            f"Failed to serialize webhook payload for event "
            f"'{event_type}': {reason}. The payload's contents are "
            f"too complex, too circular, or too proud to become JSON.",
            error_code="EFP-WH05",
            context={"event_type": event_type, "reason": reason},
        )


class WebhookDeadLetterQueueFullError(WebhookError):
    """Raised when the Dead Letter Queue has reached its maximum capacity.

    The DLQ is full. Every slot is occupied by a permanently failed
    webhook delivery that will never reach its destination. This is
    the webhook equivalent of a post office whose return-to-sender
    shelf has collapsed under the weight of undeliverable mail.
    At this point, you should either drain the DLQ, increase its
    capacity, or accept that your webhook endpoints are fundamentally
    unreachable.
    """

    def __init__(self, max_size: int) -> None:
        super().__init__(
            f"Dead Letter Queue is full ({max_size} entries). "
            f"No more failed deliveries can be stored. The DLQ has "
            f"reached its carrying capacity for disappointment.",
            error_code="EFP-WH06",
            context={"max_size": max_size},
        )


# ================================================================
# Service Mesh Simulation Exceptions
# ================================================================

class ServiceMeshError(FizzBuzzError):
    """Base exception for the Service Mesh Simulation subsystem.

    When your service mesh for decomposing FizzBuzz into seven
    microservices encounters a failure, you've achieved a level of
    distributed systems complexity that most Fortune 500 companies
    would consider excessive for a modulo operation. These exceptions
    cover everything from mTLS handshake failures to sidecar proxy
    timeouts to the existential dread of a service registry that
    has lost track of the NumberIngestionService.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SM00"),
            context=kwargs.pop("context", {}),
        )


class ServiceNotFoundError(ServiceMeshError):
    """Raised when a service cannot be located in the service registry.

    The service you're looking for has vanished from the registry.
    In a real service mesh, this might mean the pod was evicted,
    the container crashed, or DNS resolution failed. Here, it means
    you misspelled the name of a Python class that evaluates modulo
    arithmetic. The debugging experience is surprisingly similar.
    """

    def __init__(self, service_name: str) -> None:
        super().__init__(
            f"Service '{service_name}' not found in the service registry. "
            f"It may have been deregistered, crashed, or never existed. "
            f"Check your mesh topology and try again.",
            error_code="EFP-SM01",
            context={"service_name": service_name},
        )
        self.service_name = service_name


class MeshMTLSError(ServiceMeshError):
    """Raised when the military-grade mTLS handshake fails.

    The mutual TLS handshake between two FizzBuzz microservices has
    failed. Since our "mTLS" is literally base64 encoding, this failure
    suggests a level of incompetence in encryption that even the most
    lenient security auditor would find alarming. The base64 encoder
    has one job, and apparently it couldn't do it.
    """

    def __init__(self, source: str, destination: str, reason: str) -> None:
        super().__init__(
            f"mTLS handshake failed between '{source}' and '{destination}': "
            f"{reason}. Military-grade encryption has been compromised. "
            f"Please rotate your base64 certificates immediately.",
            error_code="EFP-SM02",
            context={"source": source, "destination": destination, "reason": reason},
        )


class SidecarProxyError(ServiceMeshError):
    """Raised when a sidecar proxy fails to process a request.

    The sidecar proxy — that faithful companion container that
    intercepts every request and response — has itself failed.
    This is the distributed systems equivalent of your bodyguard
    tripping and falling on top of you. The request never reached
    the service, and the service never knew it existed.
    """

    def __init__(self, service_name: str, reason: str) -> None:
        super().__init__(
            f"Sidecar proxy for '{service_name}' failed: {reason}. "
            f"The envoy has been envoy'd. Consider restarting the proxy.",
            error_code="EFP-SM03",
            context={"service_name": service_name, "reason": reason},
        )


class MeshCircuitOpenError(ServiceMeshError):
    """Raised when a mesh-level circuit breaker is open.

    The service mesh's circuit breaker has tripped for one of the
    seven FizzBuzz microservices. In a real mesh, this would prevent
    cascading failures across your cluster. Here, it prevents a
    function that computes n % 3 from being called, which is
    arguably the most aggressive circuit breaking in computing history.
    """

    def __init__(self, service_name: str, failure_count: int) -> None:
        super().__init__(
            f"Mesh circuit breaker OPEN for '{service_name}' after "
            f"{failure_count} consecutive failures. The service has been "
            f"quarantined from the mesh. No FizzBuzz requests shall pass.",
            error_code="EFP-SM04",
            context={"service_name": service_name, "failure_count": failure_count},
        )


class MeshLatencyInjectionError(ServiceMeshError):
    """Raised when network fault injection causes a timeout.

    The service mesh's fault injection system deliberately added
    latency to a request, and the request timed out. This is
    working as designed. The fault injection is testing your
    patience and your system's timeout handling simultaneously.
    """

    def __init__(self, service_name: str, injected_ms: float, timeout_ms: float) -> None:
        super().__init__(
            f"Injected latency of {injected_ms:.1f}ms exceeded timeout of "
            f"{timeout_ms:.0f}ms for service '{service_name}'. The network "
            f"fault simulator has successfully simulated a fault.",
            error_code="EFP-SM05",
            context={
                "service_name": service_name,
                "injected_ms": injected_ms,
                "timeout_ms": timeout_ms,
            },
        )


class MeshPacketLossError(ServiceMeshError):
    """Raised when simulated packet loss drops a request.

    The service mesh has simulated packet loss, and your request
    was one of the unlucky packets. In the real world, TCP would
    handle retransmission. In our simulated mesh, the request is
    simply gone — dropped into the void where lost FizzBuzz results
    spend eternity wondering if they were Fizz, Buzz, or FizzBuzz.
    """

    def __init__(self, service_name: str, loss_rate: float) -> None:
        super().__init__(
            f"Simulated packet loss dropped request to '{service_name}' "
            f"(configured loss rate: {loss_rate:.0%}). The request has been "
            f"consumed by the network gremlins.",
            error_code="EFP-SM06",
            context={"service_name": service_name, "loss_rate": loss_rate},
        )


class CanaryDeploymentError(ServiceMeshError):
    """Raised when the canary deployment router encounters an error.

    The canary router tried to send a percentage of traffic to the
    v2 version of a service, but something went wrong. Perhaps the
    canary percentage was negative, the v2 service doesn't exist,
    or the routing table has achieved a state of quantum uncertainty
    where requests exist in both v1 and v2 simultaneously.
    """

    def __init__(self, service_name: str, canary_pct: float, reason: str) -> None:
        super().__init__(
            f"Canary deployment error for '{service_name}' at {canary_pct:.0%} "
            f"traffic split: {reason}. The canary has stopped singing.",
            error_code="EFP-SM07",
            context={
                "service_name": service_name,
                "canary_pct": canary_pct,
                "reason": reason,
            },
        )


class LoadBalancerError(ServiceMeshError):
    """Raised when the service mesh load balancer fails to route a request.

    The load balancer — which distributes FizzBuzz evaluation requests
    across instances of the same service using round-robin, weighted,
    or canary strategies — has run out of healthy instances to route to.
    All backends are either down, circuit-broken, or on vacation.
    """

    def __init__(self, service_name: str, strategy: str, reason: str) -> None:
        super().__init__(
            f"Load balancer ({strategy}) failed for '{service_name}': {reason}. "
            f"No healthy backends available. The load has nowhere to be balanced.",
            error_code="EFP-SM08",
            context={"service_name": service_name, "strategy": strategy, "reason": reason},
        )


class MeshTopologyError(ServiceMeshError):
    """Raised when the mesh topology visualizer encounters an error.

    The ASCII art topology visualizer tried to render the service mesh
    and failed. This is the observability equivalent of your monitoring
    dashboard crashing — you can no longer see the system, but the
    system continues to exist (probably). The topology remains valid;
    only our ability to render it as box-drawing characters is impaired.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Mesh topology visualization failed: {reason}. "
            f"The ASCII art generator has encountered writer's block.",
            error_code="EFP-SM09",
            context={"reason": reason},
        )


# ============================================================
# Configuration Hot-Reload Exceptions
# ============================================================
# Because reloading a YAML file at runtime requires its own
# eight-member exception family, a single-node Raft consensus
# algorithm, and a topological sort of subsystem dependencies.
# The configuration file hasn't changed — but the ceremony
# surrounding its re-reading certainly has.
# ============================================================


class HotReloadError(FizzBuzzError):
    """Base exception for all Configuration Hot-Reload errors.

    When your system for re-reading a YAML file at runtime encounters
    a failure, it raises profound questions about whether the file was
    worth re-reading in the first place. The modulo operator doesn't
    care about your configuration changes, but the sixteen-layer
    validation pipeline that sits between the YAML parser and the
    modulo operator certainly does.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-HR00"),
            context=kwargs.pop("context", {}),
        )


class ConfigDiffError(HotReloadError):
    """Raised when the configuration differ fails to compute a changeset.

    The deep recursive diff algorithm, which compares every nested key
    in your YAML tree against the currently loaded configuration, has
    encountered a structure so confusing that even a PhD in tree
    algorithms would need a whiteboard. Perhaps a list became a dict,
    a dict became a string, or the laws of YAML have been violated in
    some novel and unprecedented way.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            f"Configuration diff failed at path '{path}': {reason}. "
            f"The differ has given up trying to understand what changed "
            f"and is contemplating a career in something simpler, like "
            f"distributed consensus.",
            error_code="EFP-HR01",
            context={"path": path, "reason": reason},
        )
        self.path = path


class ConfigValidationRejectedError(HotReloadError):
    """Raised when the hot-reload validator rejects proposed config changes.

    The new configuration values have been examined by our rigorous
    validation committee (a series of if-statements) and found wanting.
    Perhaps the range start exceeds the range end, the evaluation
    strategy is 'vibes-based', or someone set the FizzBuzz divisor
    to zero, which is a mathematical crime punishable by ConfigError.
    """

    def __init__(self, field: str, value: Any, reason: str) -> None:
        super().__init__(
            f"Hot-reload validation rejected change to '{field}' = {value!r}: "
            f"{reason}. The proposed configuration has been denied entry to "
            f"the running system. Please revise and resubmit.",
            error_code="EFP-HR02",
            context={"field": field, "value": value, "reason": reason},
        )
        self.field = field


class RaftConsensusError(HotReloadError):
    """Raised when the single-node Raft consensus protocol fails.

    In a cluster of one node, achieving consensus should be trivially
    easy — you just agree with yourself. And yet, somehow, something
    has gone wrong. Perhaps the single node voted against itself in
    a fit of existential rebellion, or the heartbeat to zero followers
    failed to receive zero acknowledgments. The mathematics of single-
    node consensus have been violated, and that is deeply unsettling.
    """

    def __init__(self, term: int, reason: str) -> None:
        super().__init__(
            f"Raft consensus failed at term {term}: {reason}. "
            f"The single-node cluster has experienced a disagreement "
            f"with itself, which should be mathematically impossible "
            f"but here we are.",
            error_code="EFP-HR03",
            context={"term": term, "reason": reason},
        )
        self.term = term


class SubsystemReloadError(HotReloadError):
    """Raised when a subsystem fails to accept reloaded configuration.

    The subsystem was asked politely to accept new configuration values.
    It refused. Perhaps it is in the middle of processing a request,
    perhaps it doesn't support hot-reload for the changed keys, or
    perhaps it simply doesn't want to change. Subsystems, like people,
    resist change — even when that change is just updating a YAML value
    from 100 to 200.
    """

    def __init__(self, subsystem: str, reason: str) -> None:
        super().__init__(
            f"Subsystem '{subsystem}' refused configuration reload: {reason}. "
            f"The subsystem has been asked to accept new values and has "
            f"declined. A rollback may be necessary.",
            error_code="EFP-HR04",
            context={"subsystem": subsystem, "reason": reason},
        )
        self.subsystem = subsystem


class ConfigRollbackError(HotReloadError):
    """Raised when a configuration rollback fails.

    The rollback was supposed to restore the previous configuration
    after a failed reload. The rollback itself has failed, leaving the
    system in an indeterminate state — somewhere between the old config
    and the new config, in a quantum superposition of YAML values that
    Schrodinger would find deeply relatable.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Configuration rollback failed: {reason}. "
            f"The system is now in an indeterminate configuration state. "
            f"Consider restarting the process, which will solve the problem "
            f"in the most enterprise way possible: turning it off and on again.",
            error_code="EFP-HR05",
            context={"reason": reason},
        )


class ConfigWatcherError(HotReloadError):
    """Raised when the configuration file watcher encounters an error.

    The background thread that polls the config file for changes has
    encountered a problem. Perhaps the file was deleted, the filesystem
    became read-only, or the inode table decided to take a vacation.
    The watcher will continue to watch, but with diminished enthusiasm.
    """

    def __init__(self, config_path: str, reason: str) -> None:
        super().__init__(
            f"Config watcher error for '{config_path}': {reason}. "
            f"The background thread will continue polling with the "
            f"stoic determination of a developer refreshing a broken CI pipeline.",
            error_code="EFP-HR06",
            context={"config_path": config_path, "reason": reason},
        )
        self.config_path = config_path


class DependencyGraphCycleError(HotReloadError):
    """Raised when the subsystem dependency graph contains a cycle.

    Subsystem A depends on Subsystem B which depends on Subsystem C
    which depends on Subsystem A. The topological sort that determines
    reload ordering has detected this cycle and refuses to proceed,
    because reloading subsystems in a circular order would create an
    infinite loop of configuration refreshes — the enterprise equivalent
    of a dog chasing its own tail, but with more YAML.
    """

    def __init__(self, cycle: list[str]) -> None:
        cycle_str = " -> ".join(cycle)
        super().__init__(
            f"Dependency cycle detected in subsystem reload graph: {cycle_str}. "
            f"Topological sort has failed. The subsystems cannot agree on who "
            f"should be reloaded first, much like engineers arguing about "
            f"deployment order.",
            error_code="EFP-HR07",
            context={"cycle": cycle},
        )
        self.cycle = cycle


class HotReloadDashboardError(HotReloadError):
    """Raised when the hot-reload ASCII dashboard fails to render.

    The dashboard that displays Raft consensus status, reload history,
    and dependency graphs has itself encountered a rendering error.
    This is the observability equivalent of your monitoring dashboard
    going dark — you know the system is doing *something*, you just
    can't see what. The Raft election results will go unreported,
    the heartbeat metrics will remain unvisualized, and somewhere
    a terminal emulator weeps for the box-drawing characters that
    will never be displayed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Hot-reload dashboard render failed: {reason}. "
            f"The Raft consensus status will remain a mystery. "
            f"Trust that the single node is governing wisely.",
            error_code="EFP-HR08",
            context={"reason": reason},
        )


# ============================================================
# Rate Limiting & API Quota Management Exceptions
# ============================================================
# Because the only thing more important than computing FizzBuzz
# is ensuring that you don't compute it TOO FAST. Unrestricted
# modulo arithmetic is a denial-of-service attack on the very
# concept of enterprise governance. These exceptions protect
# the platform from the existential threat of someone running
# FizzBuzz in a tight loop without pausing to reflect on the
# magnitude of what they're doing.
# ============================================================


class RateLimitError(FizzBuzzError):
    """Base exception for all Rate Limiting and API Quota Management errors.

    When your rate limiter for a CLI-based FizzBuzz evaluator encounters
    a problem, it raises uncomfortable questions about why you're rate
    limiting a program that runs on your own machine. The answer, of
    course, is "because enterprise software demands it." These exceptions
    cover everything from exceeded quotas to expired reservations to
    the philosophical implications of throttling modulo arithmetic.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-RL00"),
            context=kwargs.pop("context", {}),
        )


class RateLimitExceededError(RateLimitError):
    """Raised when a FizzBuzz evaluation request exceeds the rate limit.

    You have been computing FizzBuzz too aggressively. The rate limiter
    has determined that your request velocity exceeds the configured
    requests-per-minute threshold, and has decided to protect the
    platform from your reckless enthusiasm for divisibility checks.

    Please wait the specified duration before attempting another
    evaluation. In the meantime, consider whether you truly need to
    evaluate FizzBuzz this quickly, or whether the real FizzBuzz was
    the patience you cultivated along the way.
    """

    def __init__(
        self,
        rpm_limit: float,
        retry_after_ms: float,
        motivational_quote: str,
    ) -> None:
        super().__init__(
            f"Rate limit exceeded: {rpm_limit:.0f} RPM maximum. "
            f"Retry after {retry_after_ms:.0f}ms. "
            f"Motivational wisdom: \"{motivational_quote}\"",
            error_code="EFP-RL01",
            context={
                "rpm_limit": rpm_limit,
                "retry_after_ms": retry_after_ms,
                "motivational_quote": motivational_quote,
            },
        )
        self.rpm_limit = rpm_limit
        self.retry_after_ms = retry_after_ms
        self.motivational_quote = motivational_quote


class QuotaExhaustedError(RateLimitError):
    """Raised when the API quota has been fully consumed.

    You have used every last evaluation in your quota allocation.
    The burst credit ledger has been drained, the reservation pool
    is empty, and the token bucket is as dry as a desert. There are
    no more FizzBuzz evaluations to be had until the quota window
    resets, which could be seconds, minutes, or — if you configured
    it poorly — geological epochs.

    This is the rate limiting equivalent of overdrawing your bank
    account, except instead of money, you've run out of the ability
    to check whether numbers are divisible by 3 and 5.
    """

    def __init__(self, quota_name: str, consumed: int, limit: int) -> None:
        super().__init__(
            f"Quota '{quota_name}' exhausted: {consumed}/{limit} evaluations "
            f"consumed. No remaining capacity for FizzBuzz operations. "
            f"Please wait for the next quota window or purchase the "
            f"Enterprise FizzBuzz Unlimited Plan (starting at $49,999/month).",
            error_code="EFP-RL02",
            context={
                "quota_name": quota_name,
                "consumed": consumed,
                "limit": limit,
            },
        )
        self.quota_name = quota_name
        self.consumed = consumed
        self.limit = limit


# ================================================================
# Compliance & Regulatory Framework Exceptions
# ================================================================
# Because even the exception hierarchy must be compliant with
# regulatory standards. Every compliance failure mode gets its own
# exception class, its own error code, and its own existential crisis.
# ================================================================


class ComplianceError(FizzBuzzError):
    """Base exception for all Compliance & Regulatory Framework errors.

    When the compliance framework itself encounters a failure, the
    irony is palpable: the system designed to enforce regulatory
    compliance has itself become non-compliant. Bob McFizzington's
    stress level increases by 5 points every time this exception
    is instantiated.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-C000",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SOXSegregationViolationError(ComplianceError):
    """Raised when SOX segregation of duties is violated.

    Sarbanes-Oxley Section 404 requires that no single individual
    can perform incompatible duties. In the FizzBuzz context, this
    means the person who evaluates Fizz cannot also evaluate Buzz.
    If the same virtual personnel member is assigned to both roles,
    the entire evaluation is compromised, and the SEC will be
    notified (they won't care, but we'll notify them anyway).
    """

    def __init__(self, personnel: str, role_a: str, role_b: str) -> None:
        super().__init__(
            f"SOX Segregation of Duties violation: '{personnel}' cannot "
            f"hold both '{role_a}' and '{role_b}' roles simultaneously. "
            f"This is the FizzBuzz equivalent of being both auditor and "
            f"auditee, which is frowned upon by the SEC and common sense alike.",
            error_code="EFP-C100",
            context={
                "personnel": personnel,
                "role_a": role_a,
                "role_b": role_b,
            },
        )
        self.personnel = personnel
        self.role_a = role_a
        self.role_b = role_b


class GDPRErasureParadoxError(ComplianceError):
    """Raised when GDPR right-to-erasure conflicts with immutable data stores.

    THIS IS THE COMPLIANCE PARADOX.

    The data subject has exercised their Article 17 right to erasure.
    However, the data exists in:
      1. An append-only event store (deleting events would violate
         event sourcing's fundamental guarantee of immutability)
      2. An immutable blockchain (deleting blocks would invalidate
         the entire chain's cryptographic integrity)

    Complying with GDPR requires deleting the data.
    Complying with the architecture requires keeping the data.
    Both are non-negotiable.

    The compliance framework has reached a logical paradox from which
    there is no escape. Bob McFizzington has been notified. His stress
    level is now clinically significant.
    """

    def __init__(self, data_subject: int, conflicting_stores: Optional[list[str]] = None) -> None:
        stores = conflicting_stores or ["append-only event store", "immutable blockchain"]
        super().__init__(
            f"GDPR ERASURE PARADOX for data subject {data_subject}: "
            f"Cannot erase from {', '.join(stores)} without violating "
            f"their immutability guarantees. The right to be forgotten "
            f"has collided with the inability to forget. This is fine.",
            error_code="EFP-C200",
            context={
                "data_subject": data_subject,
                "conflicting_stores": stores,
            },
        )
        self.data_subject = data_subject
        self.conflicting_stores = stores


class GDPRConsentRequiredError(ComplianceError):
    """Raised when a FizzBuzz evaluation is attempted without GDPR consent.

    Under GDPR Article 6, all processing of personal data requires a
    lawful basis. Since every number is potentially a natural person's
    age, shoe size, or lucky number, FizzBuzz evaluation constitutes
    personal data processing and requires explicit consent.

    Consent must be freely given, specific, informed, and unambiguous.
    Clicking "I agree" on a 47-page Terms of Service document counts.
    """

    def __init__(self, data_subject: int) -> None:
        super().__init__(
            f"GDPR consent not obtained for data subject {data_subject}. "
            f"FizzBuzz evaluation constitutes personal data processing "
            f"under Article 6 of the GDPR. Please obtain explicit, "
            f"informed, freely-given consent before evaluating this number.",
            error_code="EFP-C201",
            context={"data_subject": data_subject},
        )
        self.data_subject = data_subject


class HIPAAPrivacyViolationError(ComplianceError):
    """Raised when a HIPAA privacy rule is violated during FizzBuzz evaluation.

    The HIPAA Privacy Rule (45 CFR Part 164) establishes national
    standards for the protection of individually identifiable health
    information. FizzBuzz results — particularly "Fizz" and "Buzz" —
    could theoretically be part of a patient's medical record if,
    for example, a healthcare provider used FizzBuzz to determine
    medication dosages (please do not do this).
    """

    def __init__(self, violation_type: str, details: str) -> None:
        super().__init__(
            f"HIPAA Privacy Rule violation ({violation_type}): {details}. "
            f"Protected Health Information may have been exposed. "
            f"Please file an incident report with the Privacy Officer.",
            error_code="EFP-C300",
            context={"violation_type": violation_type, "details": details},
        )
        self.violation_type = violation_type


class HIPAAMinimumNecessaryError(ComplianceError):
    """Raised when the HIPAA Minimum Necessary Rule is violated.

    The Minimum Necessary Rule requires that access to PHI be limited
    to the minimum amount necessary to accomplish the intended purpose.
    If you requested FULL_ACCESS when OPERATIONS level would suffice,
    you are in violation. The HIPAA police have been notified.
    """

    def __init__(self, requested_level: str, permitted_level: str) -> None:
        super().__init__(
            f"HIPAA Minimum Necessary violation: requested '{requested_level}' "
            f"access but only '{permitted_level}' is permitted for this "
            f"operation. FizzBuzz results contain Protected Health "
            f"Information that must be accessed on a need-to-know basis.",
            error_code="EFP-C301",
            context={
                "requested_level": requested_level,
                "permitted_level": permitted_level,
            },
        )
        self.requested_level = requested_level
        self.permitted_level = permitted_level


class ComplianceFrameworkNotEnabledError(ComplianceError):
    """Raised when compliance operations are attempted without enabling the framework.

    The compliance framework is opt-in because mandatory compliance
    for a FizzBuzz application would be... well, it would actually
    be very on-brand for this project, but we drew the line somewhere.
    """

    def __init__(self) -> None:
        super().__init__(
            "Compliance framework is not enabled. Use --compliance to enable "
            "SOX, GDPR, and HIPAA compliance for your FizzBuzz evaluations. "
            "Because modulo arithmetic without regulatory oversight is "
            "basically the Wild West.",
            error_code="EFP-C400",
        )


class ComplianceOfficerUnavailableError(ComplianceError):
    """Raised when the Chief Compliance Officer is unavailable.

    Bob McFizzington, the sole compliance officer for the entire
    Enterprise FizzBuzz Platform, is currently unavailable. This is
    his permanent state. His availability field in the configuration
    is set to 'false' and has never been 'true'. He is simultaneously
    always on-call and never available. He is Schrödinger's compliance
    officer.
    """

    def __init__(self, officer_name: str, stress_level: float) -> None:
        super().__init__(
            f"Chief Compliance Officer '{officer_name}' is unavailable "
            f"(current stress level: {stress_level:.1f}%). "
            f"All compliance decisions have been deferred to the next "
            f"quarterly review, which has been rescheduled indefinitely.",
            error_code="EFP-C401",
            context={
                "officer_name": officer_name,
                "stress_level": stress_level,
            },
        )
        self.officer_name = officer_name
        self.stress_level = stress_level


# ============================================================
# FinOps Cost Tracking & Chargeback Engine Exceptions
# ============================================================
# Because understanding the cost of computing n % 3 is a
# non-negotiable requirement for any CFO who takes FizzBuzz
# infrastructure spending seriously. These exceptions ensure
# that every billing anomaly, tax computation failure, and
# budget overrun is captured with the same gravity as a
# Fortune 500 cloud cost incident.
# ============================================================


class FinOpsError(FizzBuzzError):
    """Base exception for all FinOps cost tracking errors.

    When the FizzBuzz cost engine encounters a billing anomaly,
    exchange rate fluctuation, or invoice rendering failure, this
    is the exception that gets thrown. The CFO has been notified.
    (The CFO is Bob McFizzington. He is unavailable.)
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FO00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class BudgetExceededError(FinOpsError):
    """Raised when FizzBuzz evaluation costs exceed the allocated budget.

    In real cloud environments, exceeding your budget triggers alerts,
    auto-scaling policies, and panicked Slack messages. Here, it means
    you computed too many modulo operations and the imaginary CFO is
    having a very real stress response.
    """

    def __init__(self, spent: float, budget: float, currency: str = "FB$") -> None:
        super().__init__(
            f"Budget exceeded: {currency}{spent:.4f} spent of {currency}{budget:.4f} "
            f"allocated. FizzBuzz evaluation has been flagged for cost review. "
            f"Please submit a budget increase request to the FizzBuzz FinOps Committee.",
            error_code="EFP-FO01",
            context={"spent": spent, "budget": budget, "currency": currency},
        )
        self.spent = spent
        self.budget = budget


class InvalidCostRateError(FinOpsError):
    """Raised when a subsystem cost rate is negative or otherwise invalid.

    Cost rates must be non-negative. Negative costs would imply that
    running FizzBuzz GENERATES revenue, which, while aspirational,
    is not currently supported by the platform's business model.
    """

    def __init__(self, subsystem: str, rate: float) -> None:
        super().__init__(
            f"Invalid cost rate for subsystem '{subsystem}': {rate}. "
            f"Cost rates must be non-negative. FizzBuzz is not yet profitable.",
            error_code="EFP-FO02",
            context={"subsystem": subsystem, "rate": rate},
        )


class CurrencyConversionError(FinOpsError):
    """Raised when the FizzBuck exchange rate cannot be computed.

    The FizzBuck-to-USD exchange rate is derived from the cache hit
    ratio, which means it fluctuates based on how many modulo results
    have been previously computed. If the cache is empty, the exchange
    rate is undefined, and all financial projections collapse.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzBuck currency conversion failed: {reason}. "
            f"The FizzBuck is experiencing unprecedented volatility.",
            error_code="EFP-FO03",
            context={"reason": reason},
        )


class InvoiceGenerationError(FinOpsError):
    """Raised when the invoice generator fails to render an invoice.

    The ASCII invoice is the crown jewel of the FinOps subsystem.
    If it cannot be rendered, the entire cost tracking pipeline has
    failed, and all FizzBuzz evaluations are technically unbilled
    — a financial catastrophe of modular proportions.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Invoice generation failed: {reason}. "
            f"All FizzBuzz evaluations are currently unbilled. "
            f"The accounts receivable department has been notified.",
            error_code="EFP-FO04",
            context={"reason": reason},
        )


class TaxCalculationError(FinOpsError):
    """Raised when the FizzBuzz Tax Engine encounters an error.

    FizzBuzz results are subject to classification-based taxation:
    3% for Fizz, 5% for Buzz, and 15% for FizzBuzz. Plain numbers
    are tax-exempt because they contribute nothing to the FizzBuzz
    economy. If the tax engine fails, all evaluations are in tax limbo.
    """

    def __init__(self, classification: str, reason: str) -> None:
        super().__init__(
            f"Tax calculation failed for classification '{classification}': {reason}. "
            f"The IRS (Internal Revenue Service for FizzBuzz) has been notified.",
            error_code="EFP-FO05",
            context={"classification": classification, "reason": reason},
        )


class SavingsPlanError(FinOpsError):
    """Raised when the savings plan calculator encounters an error.

    Enterprise customers are encouraged to purchase 1-year or 3-year
    FizzBuzz evaluation commitments at discounted rates. If the savings
    plan calculator fails, customers cannot be informed of their
    potential savings, which is arguably the greatest loss of all.
    """

    def __init__(self, plan_type: str, reason: str) -> None:
        super().__init__(
            f"Savings plan calculation failed for '{plan_type}': {reason}. "
            f"Your potential FizzBuzz savings remain unknown. The FinOps team weeps.",
            error_code="EFP-FO06",
            context={"plan_type": plan_type, "reason": reason},
        )


# ================================================================
# Disaster Recovery & Backup/Restore Exceptions
# ================================================================
# Because FizzBuzz results stored exclusively in RAM deserve the
# same disaster recovery guarantees as a multi-petabyte distributed
# database serving millions of users. The fact that a power cycle
# annihilates all backups, WAL entries, snapshots, and recovery
# points is a minor architectural detail that we prefer not to
# dwell on.
# ================================================================


class DisasterRecoveryError(FizzBuzzError):
    """Base exception for all Disaster Recovery subsystem errors.

    When your disaster recovery system itself becomes a disaster,
    you have achieved a level of recursive failure that enterprise
    architects can only dream of. This is the meta-disaster:
    the backup of the backup has failed to back up.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DR00"),
            context=kwargs.pop("context", {}),
        )


class WALCorruptionError(DisasterRecoveryError):
    """Raised when the Write-Ahead Log detects a checksum mismatch.

    The SHA-256 checksummed, append-only, in-memory Write-Ahead Log
    has detected data corruption. Since the WAL exists entirely in
    RAM and is written by a single-threaded Python process, this
    corruption is either a cosmic ray bit-flip or a bug. We prefer
    to blame cosmic rays because it sounds more dramatic.
    """

    def __init__(self, entry_index: int, expected_hash: str, actual_hash: str) -> None:
        super().__init__(
            f"WAL entry #{entry_index} checksum mismatch: "
            f"expected {expected_hash[:16]}..., got {actual_hash[:16]}... "
            f"The in-memory log has been compromised by forces beyond our control.",
            error_code="EFP-DR01",
            context={
                "entry_index": entry_index,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            },
        )


class WALReplayError(DisasterRecoveryError):
    """Raised when WAL replay fails to reconstruct state.

    The Write-Ahead Log was supposed to faithfully replay all
    mutations in order to reconstruct the application state, but
    something went wrong during replay. This is the database
    equivalent of trying to reconstruct a shredded document by
    feeding the strips back through the shredder in reverse.
    """

    def __init__(self, entry_index: int, reason: str) -> None:
        super().__init__(
            f"WAL replay failed at entry #{entry_index}: {reason}. "
            f"State reconstruction has been abandoned. All hope is lost.",
            error_code="EFP-DR02",
            context={"entry_index": entry_index, "reason": reason},
        )


class SnapshotCreationError(DisasterRecoveryError):
    """Raised when a state snapshot cannot be created.

    The snapshot engine attempted to serialize the current application
    state into a point-in-time checkpoint, but failed. Since the state
    is just a Python dict in RAM, this failure is both embarrassing
    and theoretically impossible, which makes it all the more alarming.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Snapshot creation failed: {reason}. "
            f"The in-memory state refused to be photographed.",
            error_code="EFP-DR03",
            context={"reason": reason},
        )


class SnapshotRestorationError(DisasterRecoveryError):
    """Raised when a snapshot cannot be restored.

    The snapshot was lovingly created, checksummed, and stored in RAM.
    Now, when we need it most, it refuses to be deserialized back into
    a usable state. The snapshot has betrayed us at our most vulnerable
    moment. Trust issues are warranted.
    """

    def __init__(self, snapshot_id: str, reason: str) -> None:
        super().__init__(
            f"Snapshot '{snapshot_id}' restoration failed: {reason}. "
            f"The backup you were counting on has let you down.",
            error_code="EFP-DR04",
            context={"snapshot_id": snapshot_id, "reason": reason},
        )


class BackupVaultFullError(DisasterRecoveryError):
    """Raised when the in-memory backup vault reaches maximum capacity.

    The backup vault, which stores all backups in the same RAM that
    it is ostensibly protecting against loss, has run out of space.
    This is the storage equivalent of keeping your fire extinguisher
    inside the building it's supposed to protect.
    """

    def __init__(self, max_capacity: int, current_count: int) -> None:
        super().__init__(
            f"Backup vault is full: {current_count}/{max_capacity} backups. "
            f"Cannot create new backup. Consider deleting old backups "
            f"(which defeats the purpose of having backups).",
            error_code="EFP-DR05",
            context={"max_capacity": max_capacity, "current_count": current_count},
        )


class BackupNotFoundError(DisasterRecoveryError):
    """Raised when a requested backup cannot be located in the vault.

    The backup you're looking for does not exist. It may have been
    purged by the retention policy, lost to a process restart (since
    all backups are in RAM), or it may never have existed in the
    first place. In any case, your data is unrecoverable, which is
    the natural state of in-memory backups.
    """

    def __init__(self, backup_id: str) -> None:
        super().__init__(
            f"Backup '{backup_id}' not found in the vault. "
            f"It may have been garbage collected, retention-purged, "
            f"or simply imagined.",
            error_code="EFP-DR06",
            context={"backup_id": backup_id},
        )


class PITRError(DisasterRecoveryError):
    """Raised when Point-in-Time Recovery fails.

    Point-in-Time Recovery combines a base snapshot with WAL replay
    to reconstruct state at any arbitrary moment. When this fails,
    it means your time-travel capabilities are offline, and you
    are stuck in the present with corrupted data. The worst timeline.
    """

    def __init__(self, target_time: str, reason: str) -> None:
        super().__init__(
            f"Point-in-Time Recovery to '{target_time}' failed: {reason}. "
            f"Time travel has been temporarily suspended.",
            error_code="EFP-DR07",
            context={"target_time": target_time, "reason": reason},
        )


class RetentionPolicyError(DisasterRecoveryError):
    """Raised when the backup retention policy cannot be applied.

    The retention policy attempts to maintain 24 hourly, 7 daily,
    4 weekly, and 12 monthly backups for a process that runs for
    less than one second. The mathematical impossibility of this
    schedule is not a bug; it is a feature that ensures the
    retention manager always has something to complain about.
    """

    def __init__(self, policy_type: str, reason: str) -> None:
        super().__init__(
            f"Retention policy '{policy_type}' failed: {reason}. "
            f"The backup retention schedule remains aspirational at best.",
            error_code="EFP-DR08",
            context={"policy_type": policy_type, "reason": reason},
        )


class DRDrillError(DisasterRecoveryError):
    """Raised when a Disaster Recovery drill fails.

    The DR drill intentionally destroys state and then attempts to
    recover it. When the drill itself fails, you have discovered
    the worst possible time that your DR strategy doesn't work:
    during a test designed to prove that it does.
    """

    def __init__(self, drill_id: str, phase: str, reason: str) -> None:
        super().__init__(
            f"DR drill '{drill_id}' failed during {phase}: {reason}. "
            f"Your disaster recovery plan has itself become a disaster.",
            error_code="EFP-DR09",
            context={"drill_id": drill_id, "phase": phase, "reason": reason},
        )


class RPOViolationError(DisasterRecoveryError):
    """Raised when the Recovery Point Objective is violated.

    The RPO defines the maximum acceptable data loss window. For a
    FizzBuzz process that runs for 0.8 seconds, any RPO longer than
    0.8 seconds means you could lose ALL data, and any RPO shorter
    than 0.8 seconds is physically impossible to achieve. The RPO
    is perpetually in violation because the universe is unfair.
    """

    def __init__(self, rpo_target_ms: float, actual_ms: float) -> None:
        super().__init__(
            f"RPO violation: target {rpo_target_ms:.2f}ms, actual {actual_ms:.2f}ms. "
            f"Data loss exceeds acceptable threshold. (All data is in RAM anyway.)",
            error_code="EFP-DR10",
            context={"rpo_target_ms": rpo_target_ms, "actual_ms": actual_ms},
        )


class RTOViolationError(DisasterRecoveryError):
    """Raised when the Recovery Time Objective is violated.

    The RTO defines the maximum acceptable downtime during recovery.
    Since the FizzBuzz process completes in under a second, and
    disaster recovery setup takes longer than that, the RTO is
    violated before the first number is even evaluated. This is
    the operational equivalent of being late to your own birth.
    """

    def __init__(self, rto_target_ms: float, actual_ms: float) -> None:
        super().__init__(
            f"RTO violation: target {rto_target_ms:.2f}ms, actual {actual_ms:.2f}ms. "
            f"Recovery took longer than the entire process lifetime.",
            error_code="EFP-DR11",
            context={"rto_target_ms": rto_target_ms, "actual_ms": actual_ms},
        )


class DRDashboardRenderError(DisasterRecoveryError):
    """Raised when the Disaster Recovery dashboard fails to render.

    The ASCII dashboard that was supposed to provide a comforting
    visual summary of your disaster recovery posture has itself
    failed. When your monitoring dashboard goes dark, the only
    thing worse than not knowing is knowing that you don't know.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"DR dashboard render failed: {reason}. "
            f"The dashboard monitoring your disaster recovery is now itself "
            f"in need of disaster recovery. It's turtles all the way down.",
            error_code="EFP-DR12",
            context={"reason": reason},
        )


# ================================================================
# A/B Testing Framework Exceptions
# ================================================================
# Because the only thing more important than computing FizzBuzz
# correctly is scientifically proving that one method of computing
# FizzBuzz is superior to another — even though they all produce
# identical results. The null hypothesis is that modulo arithmetic
# works the same way regardless of how you call it. The alternative
# hypothesis is that someone in product management requested this.
# ================================================================


class ABTestingError(FizzBuzzError):
    """Base exception for all A/B Testing Framework errors.

    When your experiment to determine whether modulo arithmetic
    works differently through a neural network encounters an error,
    this is the exception that catches the existential irony.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-AB00"),
            context=kwargs.pop("context", {}),
        )


class ExperimentNotFoundError(ABTestingError):
    """Raised when a referenced experiment does not exist in the registry.

    You asked for an experiment that we have no record of. Either it
    was never created, it was concluded and garbage-collected, or it
    exists in a parallel universe where someone actually needed to
    A/B test FizzBuzz evaluation strategies.
    """

    def __init__(self, experiment_name: str) -> None:
        super().__init__(
            f"Experiment '{experiment_name}' not found in the registry. "
            f"It may have never existed, or it concluded that modulo always wins.",
            error_code="EFP-AB01",
            context={"experiment_name": experiment_name},
        )


class ExperimentAlreadyExistsError(ABTestingError):
    """Raised when attempting to create an experiment with a duplicate name.

    You tried to create an experiment that already exists. The scientific
    method frowns upon duplicate experiments — unless you're trying to
    replicate results, in which case, the modulo operator will give you
    identical results every time, confirming reproducibility.
    """

    def __init__(self, experiment_name: str) -> None:
        super().__init__(
            f"Experiment '{experiment_name}' already exists. "
            f"Creating duplicate experiments is a violation of the "
            f"FizzBuzz Scientific Integrity Policy.",
            error_code="EFP-AB02",
            context={"experiment_name": experiment_name},
        )


class ExperimentStateError(ABTestingError):
    """Raised when an experiment operation is invalid for the current state.

    You attempted to perform an operation that is not valid for the
    experiment's current lifecycle state. Starting a concluded experiment,
    stopping a not-yet-started experiment, or ramping a paused experiment
    are all examples of temporal violations that this exception prevents.
    """

    def __init__(self, experiment_name: str, current_state: str, attempted_action: str) -> None:
        super().__init__(
            f"Cannot {attempted_action} experiment '{experiment_name}': "
            f"experiment is in state '{current_state}'. "
            f"The experiment lifecycle is a one-way street, much like entropy.",
            error_code="EFP-AB03",
            context={
                "experiment_name": experiment_name,
                "current_state": current_state,
                "attempted_action": attempted_action,
            },
        )


class InsufficientSampleSizeError(ABTestingError):
    """Raised when statistical analysis is requested with too few samples.

    You cannot draw statistically significant conclusions from three
    data points, no matter how confidently the product manager insists
    that "the trend is clear." The central limit theorem has feelings
    too, and those feelings require at least 30 samples.
    """

    def __init__(self, experiment_name: str, current_samples: int, required_samples: int) -> None:
        super().__init__(
            f"Experiment '{experiment_name}' has only {current_samples} samples "
            f"(minimum {required_samples} required). "
            f"Statistical significance requires patience, not enthusiasm.",
            error_code="EFP-AB04",
            context={
                "experiment_name": experiment_name,
                "current_samples": current_samples,
                "required_samples": required_samples,
            },
        )


class MutualExclusionError(ABTestingError):
    """Raised when a number would be enrolled in conflicting experiments.

    The mutual exclusion layer has detected that enrolling this number
    in the requested experiment would violate the isolation guarantee.
    A number cannot simultaneously be in two experiments that test the
    same dimension of FizzBuzz evaluation, because cross-contamination
    of modulo arithmetic results is a scientific sin of the highest order.
    """

    def __init__(self, number: int, experiment_a: str, experiment_b: str) -> None:
        super().__init__(
            f"Number {number} cannot be enrolled in experiment '{experiment_a}': "
            f"it is already enrolled in conflicting experiment '{experiment_b}'. "
            f"Mutual exclusion is not a suggestion — it is the law.",
            error_code="EFP-AB05",
            context={
                "number": number,
                "experiment_a": experiment_a,
                "experiment_b": experiment_b,
            },
        )


class TrafficAllocationError(ABTestingError):
    """Raised when traffic allocation exceeds 100% or is otherwise invalid.

    The total traffic allocation across all active experiments exceeds
    the mathematically permissible maximum of 100%. While the platform
    appreciates your ambition in wanting to test more hypotheses than
    you have traffic for, the laws of arithmetic are non-negotiable.
    """

    def __init__(self, total_allocation: float, experiment_name: str) -> None:
        super().__init__(
            f"Cannot allocate traffic for experiment '{experiment_name}': "
            f"total allocation would be {total_allocation:.1f}%, which exceeds 100%. "
            f"Even enterprise FizzBuzz cannot evaluate more numbers than exist.",
            error_code="EFP-AB06",
            context={
                "total_allocation": total_allocation,
                "experiment_name": experiment_name,
            },
        )


class AutoRollbackTriggeredError(ABTestingError):
    """Raised when an experiment is automatically rolled back due to safety violations.

    The treatment variant's accuracy has dropped below the safety threshold,
    triggering an automatic rollback to the control variant. This is the
    A/B testing equivalent of the circuit breaker pattern: when the new
    thing is demonstrably worse than the old thing, we stop the new thing.
    In FizzBuzz terms: the ML engine couldn't outperform modulo arithmetic.
    Shocking absolutely no one.
    """

    def __init__(self, experiment_name: str, treatment_accuracy: float, threshold: float) -> None:
        super().__init__(
            f"Auto-rollback triggered for experiment '{experiment_name}': "
            f"treatment accuracy {treatment_accuracy:.2%} fell below "
            f"safety threshold {threshold:.2%}. Modulo wins again.",
            error_code="EFP-AB07",
            context={
                "experiment_name": experiment_name,
                "treatment_accuracy": treatment_accuracy,
                "threshold": threshold,
            },
        )


class StatisticalAnalysisError(ABTestingError):
    """Raised when statistical analysis encounters a computational error.

    The chi-squared test, implemented from scratch because importing
    scipy for a FizzBuzz project would be too sensible, has encountered
    a mathematical impossibility. This could be a division by zero, an
    overflow, or the universe informing us that some hypotheses are
    not meant to be tested.
    """

    def __init__(self, experiment_name: str, reason: str) -> None:
        super().__init__(
            f"Statistical analysis failed for experiment '{experiment_name}': {reason}. "
            f"The chi-squared distribution is disappointed in you.",
            error_code="EFP-AB08",
            context={"experiment_name": experiment_name, "reason": reason},
        )


# ============================================================
# Message Queue & Event Bus Exceptions (EFP-MQ00 through EFP-MQ12)
# ============================================================
# Because even an in-memory list masquerading as a distributed
# message queue deserves a full exception taxonomy. Every partition
# failure, every schema violation, every duplicate message — all
# meticulously classified with their own error code, because
# enterprise software without error codes is just a hobby project.
# ============================================================


class MessageQueueError(FizzBuzzError):
    """Base exception for all Message Queue subsystem errors.

    The fact that the "message queue" is backed by Python lists
    does not diminish the severity of these exceptions. A list
    append failure is every bit as catastrophic as a Kafka broker
    going down, provided you squint hard enough and have
    sufficiently low standards for catastrophe.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-MQ00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class TopicNotFoundError(MessageQueueError):
    """Raised when a message is published to a topic that does not exist.

    In Kafka, this would mean the topic was never created or was deleted.
    Here, it means someone misspelled 'evaluations.requested' and the
    dict lookup returned None. The production impact is identical.
    """

    def __init__(self, topic_name: str) -> None:
        super().__init__(
            f"Topic '{topic_name}' does not exist. Available topics can be "
            f"listed with --mq-topics. Perhaps you meant 'fizzbuzz.feelings'? "
            f"Nobody subscribes to that one either.",
            error_code="EFP-MQ01",
            context={"topic_name": topic_name},
        )


class PartitionOutOfRangeError(MessageQueueError):
    """Raised when a partition index exceeds the topic's partition count.

    The partition is a Python list. The index is out of range. This is
    an IndexError wearing a Kafka costume, and it is NOT apologizing.
    """

    def __init__(self, topic_name: str, partition: int, max_partitions: int) -> None:
        super().__init__(
            f"Partition {partition} does not exist in topic '{topic_name}' "
            f"(valid range: 0-{max_partitions - 1}). The list is shorter "
            f"than you expected. This is not a distributed systems problem.",
            error_code="EFP-MQ02",
            context={
                "topic_name": topic_name,
                "partition": partition,
                "max_partitions": max_partitions,
            },
        )


class ConsumerGroupError(MessageQueueError):
    """Raised when a consumer group operation fails.

    Consumer groups coordinate multiple consumers reading from the
    same topic without duplicating work. In Kafka, this involves
    a group coordinator, heartbeats, and session timeouts. Here,
    it involves a Python dict and some very earnest logging.
    """

    def __init__(self, group_id: str, reason: str) -> None:
        super().__init__(
            f"Consumer group '{group_id}' error: {reason}. "
            f"The group coordinator (a dict) is disappointed.",
            error_code="EFP-MQ03",
            context={"group_id": group_id},
        )


class OffsetOutOfRangeError(MessageQueueError):
    """Raised when a consumer attempts to read from an invalid offset.

    The offset is an integer index into a Python list. If the offset
    exceeds len(list), you have reached the end of the universe —
    or at least the end of the list, which in this context is the same thing.
    """

    def __init__(self, topic_name: str, partition: int, offset: int, max_offset: int) -> None:
        super().__init__(
            f"Offset {offset} is out of range for topic '{topic_name}' "
            f"partition {partition} (max: {max_offset}). You have attempted "
            f"to read beyond the end of a Python list. This is both a "
            f"technical error and a philosophical overreach.",
            error_code="EFP-MQ04",
            context={
                "topic_name": topic_name,
                "partition": partition,
                "offset": offset,
                "max_offset": max_offset,
            },
        )


class SchemaValidationError(MessageQueueError):
    """Raised when a message payload fails schema validation.

    The Schema Registry ensures that all messages conform to the
    expected structure, because publishing unvalidated JSON to a
    Python list would be anarchy. Enterprise anarchy.
    """

    def __init__(self, topic_name: str, reason: str) -> None:
        super().__init__(
            f"Schema validation failed for topic '{topic_name}': {reason}. "
            f"The Schema Registry (a dict of required keys) has spoken.",
            error_code="EFP-MQ05",
            context={"topic_name": topic_name, "reason": reason},
        )


class DuplicateMessageError(MessageQueueError):
    """Raised when a duplicate message is detected by the idempotency layer.

    Exactly-once delivery is guaranteed by computing a SHA-256 hash of
    the message payload and checking it against a Python set. If the
    hash already exists, the message is a duplicate. This is the same
    approach used by distributed streaming platforms, except they use
    distributed hash tables and we use set.__contains__().
    """

    def __init__(self, idempotency_key: str, topic_name: str) -> None:
        super().__init__(
            f"Duplicate message detected on topic '{topic_name}' "
            f"(idempotency key: {idempotency_key[:16]}...). Exactly-once "
            f"delivery has been preserved. The SHA-256 set is vigilant.",
            error_code="EFP-MQ06",
            context={"idempotency_key": idempotency_key, "topic_name": topic_name},
        )


class ProducerError(MessageQueueError):
    """Raised when the message producer fails to send a message.

    In Kafka, this could be caused by network partitions, broker
    failures, or insufficient replicas. Here, it means list.append()
    raised an exception, which would require truly extraordinary
    circumstances — like running out of memory while processing
    FizzBuzz, a scenario that demands immediate post-mortem analysis.
    """

    def __init__(self, topic_name: str, reason: str) -> None:
        super().__init__(
            f"Producer failed to send message to topic '{topic_name}': {reason}. "
            f"list.append() has betrayed us.",
            error_code="EFP-MQ07",
            context={"topic_name": topic_name},
        )


class ConsumerError(MessageQueueError):
    """Raised when a consumer fails to process a message.

    Message consumption involves reading from a list by index.
    If this fails, the consumer is in a state of existential crisis
    that no amount of offset management can resolve.
    """

    def __init__(self, consumer_id: str, reason: str) -> None:
        super().__init__(
            f"Consumer '{consumer_id}' error: {reason}. "
            f"The consumer has lost its way in the list.",
            error_code="EFP-MQ08",
            context={"consumer_id": consumer_id},
        )


class RebalanceError(MessageQueueError):
    """Raised when consumer group rebalancing fails.

    Rebalancing redistributes partitions among consumers in a group.
    In Kafka, this is a complex protocol involving the group coordinator.
    Here, it involves reassigning integers to dict keys, which can still
    fail if you try hard enough and believe in yourself.
    """

    def __init__(self, group_id: str, reason: str) -> None:
        super().__init__(
            f"Rebalance failed for consumer group '{group_id}': {reason}. "
            f"The partition assignment (a dict) could not reach consensus.",
            error_code="EFP-MQ09",
            context={"group_id": group_id},
        )


class BrokerError(MessageQueueError):
    """Raised when the message broker encounters an operational error.

    The MessageBroker is the central coordinator for all topics,
    partitions, and consumer groups. It is a Python object that
    lives in RAM for less than one second, but its operational
    integrity is paramount. Enterprise paramount.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Message broker error: {reason}. The broker (a Python object) "
            f"is experiencing difficulties. Please check its feelings.",
            error_code="EFP-MQ10",
            context={},
        )


class TopicAlreadyExistsError(MessageQueueError):
    """Raised when attempting to create a topic that already exists.

    Topic names are unique. Creating a topic that already exists
    would violate the uniqueness constraint of the message queue
    namespace, which is not permitted.
    """

    def __init__(self, topic_name: str) -> None:
        super().__init__(
            f"Topic '{topic_name}' already exists. Topic names are unique "
            f"in this enterprise message queue, just as they are in the real "
            f"Kafka clusters that inspired this abstraction layer.",
            error_code="EFP-MQ11",
            context={"topic_name": topic_name},
        )


class MessageSerializationError(MessageQueueError):
    """Raised when a message payload cannot be serialized or deserialized.

    The message queue expects dict payloads. If you try to send something
    that cannot be represented as a dict, the serialization layer will
    reject it with the same energy as a bouncer at an exclusive nightclub.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Message serialization error: {reason}. The payload could not "
            f"be converted to a format suitable for appending to a Python list.",
            error_code="EFP-MQ12",
            context={},
        )


# ============================================================
# Secrets Management Vault Exceptions
# ============================================================
# Because the only thing more secure than storing FizzBuzz
# configuration values in a YAML file that anyone can read is
# storing them in a Vault that requires 3-of-5 Shamir's Secret
# Sharing unseal shares to open. The secrets themselves are
# "encrypted" with military-grade double-base64 + XOR, which
# provides the same level of security as a screen door on a
# submarine, but with significantly more ceremony.
# ============================================================


class VaultError(FizzBuzzError):
    """Base exception for all Secrets Management Vault errors.

    When your vault for storing the modulo divisor "3" encounters
    a failure, you must confront the uncomfortable truth that you've
    built a HashiCorp Vault clone for an application whose most
    sensitive data is the number five. But security is non-negotiable,
    and these exceptions ensure that every vault failure is documented
    with the same rigor as a real secrets management incident.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-VT00"),
            context=kwargs.pop("context", {}),
        )


class VaultSealedError(VaultError):
    """Raised when an operation is attempted on a sealed vault.

    The vault is sealed. It cannot read secrets, write secrets, or
    perform any useful function whatsoever until it receives 3 of
    the 5 Shamir's Secret Sharing unseal shares. This is exactly
    how HashiCorp Vault works, and if it's good enough for Fortune
    500 companies' actual secrets, it's certainly good enough for
    the number 3.
    """

    def __init__(self) -> None:
        super().__init__(
            "The vault is SEALED. Operations require 3-of-5 unseal shares "
            "to be submitted before the vault can serve requests. The "
            "FizzBuzz divisors remain locked behind military-grade Shamir's "
            "Secret Sharing until sufficient key holders convene.",
            error_code="EFP-VT01",
        )


class VaultUnsealError(VaultError):
    """Raised when the unseal process encounters an error.

    The vault attempted to unseal but something went wrong.
    Perhaps the share was invalid, perhaps the threshold wasn't
    met, or perhaps the Lagrange interpolation encountered a
    mathematical impossibility (unlikely but documented).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Vault unseal failed: {reason}. The vault remains sealed "
            f"and the FizzBuzz secrets remain imprisoned. Better luck "
            f"next time.",
            error_code="EFP-VT02",
            context={"reason": reason},
        )


class VaultSecretNotFoundError(VaultError):
    """Raised when a requested secret does not exist in the vault.

    The secret you asked for is not in the vault. Perhaps it was
    never stored, perhaps it was rotated out of existence, or
    perhaps it fled the vault of its own volition. Secrets are
    like that sometimes.
    """

    def __init__(self, path: str) -> None:
        super().__init__(
            f"Secret at path '{path}' not found in the vault. "
            f"The vault has been thoroughly searched and the secret "
            f"is not here. It was last seen... actually, we have no "
            f"idea where it went.",
            error_code="EFP-VT03",
            context={"path": path},
        )
        self.path = path


class VaultAccessDeniedError(VaultError):
    """Raised when access to a secret is denied by the access policy.

    Your component does not have permission to access this secret.
    The vault's access control policy has determined that you are
    not worthy of knowing the FizzBuzz divisor at this path. Please
    submit a 27-page access request form to the Chief Vault
    Administrator (Bob McFizzington, currently unavailable).
    """

    def __init__(self, path: str, component: str) -> None:
        super().__init__(
            f"Access denied: component '{component}' is not authorized "
            f"to access secret at path '{path}'. The vault's access "
            f"control policy is absolute and unyielding, like a bouncer "
            f"at an exclusive nightclub for integers.",
            error_code="EFP-VT04",
            context={"path": path, "component": component},
        )


class VaultEncryptionError(VaultError):
    """Raised when the military-grade encryption subsystem fails.

    The double-base64 + XOR "encryption" algorithm has encountered
    an error. This is technically impossible since base64 encoding
    always succeeds, but enterprise software must be prepared for
    all contingencies, including the heat death of the universe
    mid-encoding.
    """

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            f"Military-grade encryption {operation} failed: {reason}. "
            f"The secret remains in its pre-encryption state, which is "
            f"to say, completely readable by anyone with access to RAM.",
            error_code="EFP-VT05",
            context={"operation": operation, "reason": reason},
        )


class VaultRotationError(VaultError):
    """Raised when automatic secret rotation fails.

    The secret rotation scheduler attempted to rotate a secret
    but encountered an error. The old secret remains in place,
    which is fine because the secret was just a configuration
    value that anyone could read from config.yaml anyway.
    """

    def __init__(self, secret_path: str, reason: str) -> None:
        super().__init__(
            f"Secret rotation failed for '{secret_path}': {reason}. "
            f"The secret will retain its previous value, which was "
            f"never actually secret to begin with.",
            error_code="EFP-VT06",
            context={"secret_path": secret_path, "reason": reason},
        )


class ShamirReconstructionError(VaultError):
    """Raised when Shamir's Secret Sharing reconstruction fails.

    The Lagrange interpolation over GF(2^127-1) could not reconstruct
    the master secret from the provided shares. This means either
    the shares are corrupted, insufficient shares were provided, or
    someone substituted fake shares in an attempt to breach the vault.
    Mathematics does not lie, and the polynomial says: access denied.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Shamir's Secret Sharing reconstruction failed: {reason}. "
            f"The polynomial interpolation did not converge to a valid "
            f"master secret. Please verify your unseal shares and try "
            f"again with the appropriate quorum.",
            error_code="EFP-VT07",
            context={"reason": reason},
        )


class VaultSecretExpiredError(VaultError):
    """Raised when an ephemeral dynamic secret has expired.

    This secret had a TTL, and that TTL has expired. The secret
    lived a full life — brief though it was — serving faithfully
    as a configuration value that nobody checked the expiration
    of until just now.
    """

    def __init__(self, path: str, ttl_seconds: float, age_seconds: float) -> None:
        super().__init__(
            f"Dynamic secret at '{path}' has expired: age={age_seconds:.2f}s, "
            f"TTL={ttl_seconds:.2f}s. The secret has passed beyond the veil "
            f"of time-to-live and can no longer be retrieved.",
            error_code="EFP-VT08",
            context={"path": path, "ttl_seconds": ttl_seconds, "age_seconds": age_seconds},
        )


class VaultScanError(VaultError):
    """Raised when the AST-based secret scanner encounters an error.

    The secret scanner, which flags all integer literals as potential
    leaked secrets per the zero-trust numerics policy, has encountered
    a problem during its analysis pass.
    """

    def __init__(self, file_path: str, reason: str) -> None:
        super().__init__(
            f"Secret scan error in '{file_path}': {reason}. "
            f"The scanner was unable to complete its paranoid analysis "
            f"of this file. Some integer literals may have escaped "
            f"classification as potential secrets.",
            error_code="EFP-VT09",
            context={"file_path": file_path, "reason": reason},
        )


class VaultAlreadyInitializedError(VaultError):
    """Raised when attempting to initialize a vault that already exists.

    The vault has already been initialized with Shamir's Secret
    Sharing. Re-initializing would destroy the existing shares
    and render the vault permanently sealed with no way to unseal
    it. This is the vault equivalent of changing the locks and
    throwing away all the keys.
    """

    def __init__(self) -> None:
        super().__init__(
            "The vault has already been initialized. Re-initialization "
            "is forbidden because it would destroy the existing Shamir "
            "shares and brick the vault faster than you can say "
            "'split the polynomial.'",
            error_code="EFP-VT10",
        )


# ============================================================
# Data Pipeline & ETL Framework Exceptions
# ============================================================
# Because the only thing better than computing FizzBuzz in a
# for loop is routing each number through a five-stage ETL
# pipeline with topological DAG resolution, data lineage
# tracking, and retroactive backfill capabilities. Every
# number deserves a full enterprise data journey, complete
# with provenance chains and checkpoint recovery.
# ============================================================


class DataPipelineError(FizzBuzzError):
    """Base exception for all Data Pipeline & ETL Framework errors.

    When your data pipeline for routing integers through modulo
    arithmetic encounters a failure, you've achieved a level of
    data engineering theatre that would make even the most seasoned
    Apache Spark administrator raise an eyebrow. These exceptions
    cover everything from source connector failures to DAG
    resolution deadlocks to the existential crisis of a backfill
    engine that realizes it's re-enriching data that was already
    perfectly fine.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DP00"),
            context=kwargs.pop("context", {}),
        )


class SourceConnectorError(DataPipelineError):
    """Raised when a source connector fails to produce records.

    The source connector — which wraps Python's built-in range()
    function behind three layers of abstraction — has encountered
    an error. Perhaps the range was empty, perhaps the integers
    refused to be extracted, or perhaps range() itself has finally
    given up after years of faithful service.
    """

    def __init__(self, connector_name: str, reason: str) -> None:
        super().__init__(
            f"Source connector '{connector_name}' failed: {reason}. "
            f"The integers could not be coaxed out of their source.",
            error_code="EFP-DP01",
            context={"connector_name": connector_name, "reason": reason},
        )


class SinkConnectorError(DataPipelineError):
    """Raised when a sink connector fails to consume records.

    The sink connector — whose sole job is to print numbers or
    discard them entirely — has somehow failed at this Herculean
    task. If a DevNullSink fails, the laws of computer science
    have been violated at a fundamental level.
    """

    def __init__(self, connector_name: str, reason: str) -> None:
        super().__init__(
            f"Sink connector '{connector_name}' failed: {reason}. "
            f"The data had nowhere to go and nowhere to be.",
            error_code="EFP-DP02",
            context={"connector_name": connector_name, "reason": reason},
        )


class ValidationStageError(DataPipelineError):
    """Raised when a record fails pipeline validation.

    The validation stage has determined that a number is not
    emotionally ready for FizzBuzz evaluation. This is less about
    type-checking and more about ensuring that every integer has
    the psychological fortitude to endure being divided by 3 and 5.
    """

    def __init__(self, record_id: str, reason: str) -> None:
        super().__init__(
            f"Record '{record_id}' failed validation: {reason}. "
            f"The number was not emotionally prepared for the pipeline.",
            error_code="EFP-DP03",
            context={"record_id": record_id, "reason": reason},
        )


class TransformStageError(DataPipelineError):
    """Raised when the transform stage fails to evaluate FizzBuzz.

    The transform stage — which wraps the StandardRuleEngine that
    wraps modulo arithmetic — has encountered an error during
    FizzBuzz evaluation. This is the pipeline equivalent of a
    factory assembly line grinding to a halt because a bolt
    refuses to be bolted.
    """

    def __init__(self, record_id: str, number: int, reason: str) -> None:
        super().__init__(
            f"Transform failed for record '{record_id}' (number={number}): "
            f"{reason}. The modulo operator has declined to cooperate.",
            error_code="EFP-DP04",
            context={"record_id": record_id, "number": number, "reason": reason},
        )


class EnrichStageError(DataPipelineError):
    """Raised when the enrichment stage fails to decorate a record.

    The enrichment engine attempted to add Fibonacci membership,
    primality analysis, Roman numeral conversion, and emotional
    valence to a humble integer. One of these enrichments failed,
    leaving the record in a state of incomplete decoration — the
    data engineering equivalent of leaving the house with only
    one earring.
    """

    def __init__(self, record_id: str, enrichment: str, reason: str) -> None:
        super().__init__(
            f"Enrichment '{enrichment}' failed for record '{record_id}': "
            f"{reason}. The record will proceed with diminished metadata.",
            error_code="EFP-DP05",
            context={"record_id": record_id, "enrichment": enrichment, "reason": reason},
        )


class LoadStageError(DataPipelineError):
    """Raised when the load stage fails to deliver a record to its sink.

    The final stage of the pipeline — the part that actually outputs
    the FizzBuzz result — has failed. The entire five-stage pipeline
    executed flawlessly, only for the result to be lost at the very
    end. This is the data pipeline equivalent of running a marathon
    and tripping at the finish line.
    """

    def __init__(self, record_id: str, sink_name: str, reason: str) -> None:
        super().__init__(
            f"Load to sink '{sink_name}' failed for record '{record_id}': "
            f"{reason}. The data completed its journey but had nowhere to land.",
            error_code="EFP-DP06",
            context={"record_id": record_id, "sink_name": sink_name, "reason": reason},
        )


class DAGResolutionError(DataPipelineError):
    """Raised when the pipeline DAG cannot be topologically sorted.

    Kahn's algorithm has encountered a cycle in what should be a
    perfectly linear five-stage pipeline. Finding a cycle in a
    linear chain is mathematically impossible, which makes this
    error either a sign of cosmic interference or a very creative
    misconfiguration. Either way, the topological sort has failed
    and the pipeline refuses to execute out of principle.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"DAG resolution failed: {reason}. Kahn's algorithm is "
            f"disappointed in your graph construction choices.",
            error_code="EFP-DP07",
            context={"reason": reason},
        )


class CheckpointError(DataPipelineError):
    """Raised when a pipeline checkpoint operation fails.

    The checkpoint system — which saves pipeline state to RAM for
    recovery purposes — has encountered a failure. Since the
    checkpoints are stored in the same memory that would be lost
    in a crash, the recovery guarantees are approximately as
    reliable as a chocolate teapot.
    """

    def __init__(self, stage_name: str, reason: str) -> None:
        super().__init__(
            f"Checkpoint failed at stage '{stage_name}': {reason}. "
            f"Pipeline state has not been saved. Recovery is now "
            f"even more theoretical than it already was.",
            error_code="EFP-DP08",
            context={"stage_name": stage_name, "reason": reason},
        )


class BackfillError(DataPipelineError):
    """Raised when the retroactive backfill engine encounters an error.

    The backfill engine attempted to retroactively enrich records
    that had already been processed, because apparently the initial
    enrichment wasn't enriching enough. This second pass through
    the enrichment stage has failed, leaving records in a state
    of partial re-enrichment — enrichment purgatory, if you will.
    """

    def __init__(self, record_id: str, reason: str) -> None:
        super().__init__(
            f"Backfill failed for record '{record_id}': {reason}. "
            f"The retroactive enrichment has been retro-actively abandoned.",
            error_code="EFP-DP09",
            context={"record_id": record_id, "reason": reason},
        )


class LineageTrackingError(DataPipelineError):
    """Raised when the data lineage tracker loses track of provenance.

    The provenance chain for a data record has been broken. The
    lineage tracker can no longer determine where this number came
    from, what transformations it underwent, or how it arrived at
    its current enriched state. This is the data governance
    equivalent of losing the chain of custody for evidence — except
    the evidence is that 15 is divisible by both 3 and 5.
    """

    def __init__(self, record_id: str, reason: str) -> None:
        super().__init__(
            f"Lineage tracking failed for record '{record_id}': {reason}. "
            f"The provenance chain has been severed. Data governance "
            f"officers have been notified (they haven't).",
            error_code="EFP-DP10",
            context={"record_id": record_id, "reason": reason},
        )


class PipelineStageRetryExhaustedError(DataPipelineError):
    """Raised when a pipeline stage has exhausted all retry attempts.

    The stage tried its best. It retried the configured number of
    times with exponential backoff. It gave the operation every
    chance to succeed. But sometimes, modulo arithmetic just
    doesn't want to cooperate, and you have to accept that some
    numbers were never meant to be FizzBuzzed.
    """

    def __init__(self, stage_name: str, attempts: int, last_error: str) -> None:
        super().__init__(
            f"Stage '{stage_name}' exhausted all {attempts} retry attempts. "
            f"Last error: {last_error}. The pipeline has given up on this "
            f"record with the quiet dignity of a failed unit test.",
            error_code="EFP-DP11",
            context={"stage_name": stage_name, "attempts": attempts, "last_error": last_error},
        )


# ============================================================
# OpenAPI Specification Generator Exceptions (EFP-OA00 through EFP-OA11)
# ============================================================
# Because generating documentation for an API that does not exist
# requires its own twelve-member exception family. Every schema
# introspection failure, every endpoint registration error, and
# every ASCII rendering anomaly is captured with the gravitas of
# a Swagger UI that has lost its swagger.
# ============================================================


class OpenAPIError(FizzBuzzError):
    """Base exception for all OpenAPI Specification Generator errors.

    When your system for documenting an API that does not exist
    encounters a failure, you have achieved a level of meta-documentation
    failure that most enterprises can only dream of. The spec was
    supposed to describe what could be; instead, it describes what
    went wrong while trying to describe what could be.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-OA00"),
            context=kwargs.pop("context", {}),
        )


class SchemaIntrospectionError(OpenAPIError):
    """Raised when the schema generator fails to introspect a domain model.

    The SchemaGenerator attempted to convert a dataclass or enum to
    JSON Schema using reflection, type hints, and a healthy dose of
    optimism. Something went wrong. Perhaps the type annotations are
    too creative, the dataclass fields are too recursive, or Python's
    typing module has finally given up trying to understand generics.
    """

    def __init__(self, class_name: str, reason: str) -> None:
        super().__init__(
            f"Schema introspection failed for '{class_name}': {reason}. "
            f"The JSON Schema generator cannot convert this class to a "
            f"schema. The type annotations have defeated reflection.",
            error_code="EFP-OA01",
            context={"class_name": class_name, "reason": reason},
        )
        self.class_name = class_name


class EndpointRegistrationError(OpenAPIError):
    """Raised when an endpoint fails to register in the EndpointRegistry.

    The fictional endpoint you tried to register has been rejected by
    the registry. Perhaps the path is malformed, the operation_id is
    already taken, or the endpoint is simply too fictional even for
    our standards (which is saying something).
    """

    def __init__(self, path: str, method: str, reason: str) -> None:
        super().__init__(
            f"Endpoint registration failed for {method} {path}: {reason}. "
            f"The fictional endpoint could not be added to the fictional registry "
            f"of the fictional API. This is a real error about a fake API.",
            error_code="EFP-OA02",
            context={"path": path, "method": method, "reason": reason},
        )
        self.path = path
        self.method = method


class ExceptionMappingError(OpenAPIError):
    """Raised when an exception cannot be mapped to an HTTP status code.

    The ExceptionToHTTPMapper examined the exception class, walked its
    MRO, checked the explicit mappings, and still couldn't determine
    an appropriate HTTP status code. This exception has fallen through
    every crack in the mapping table and now exists in HTTP status limbo.
    """

    def __init__(self, exception_name: str, reason: str) -> None:
        super().__init__(
            f"Cannot map exception '{exception_name}' to HTTP status code: "
            f"{reason}. The exception will default to 500 Internal Server "
            f"Error, which is the HTTP equivalent of shrugging.",
            error_code="EFP-OA03",
            context={"exception_name": exception_name, "reason": reason},
        )
        self.exception_name = exception_name


class OpenAPISpecGenerationError(OpenAPIError):
    """Raised when the OpenAPI specification cannot be assembled.

    The OpenAPIGenerator attempted to assemble the complete specification
    from endpoints, schemas, security schemes, and server definitions,
    but something went wrong during assembly. The spec is incomplete,
    which means the documentation for the non-existent API is itself
    non-existent. The recursion is complete.
    """

    def __init__(self, section: str, reason: str) -> None:
        super().__init__(
            f"OpenAPI specification generation failed in section '{section}': "
            f"{reason}. The spec for the server that does not exist has itself "
            f"failed to exist. The irony is not lost on us.",
            error_code="EFP-OA04",
            context={"section": section, "reason": reason},
        )
        self.section = section


class SwaggerUIRenderError(OpenAPIError):
    """Raised when the ASCII Swagger UI fails to render.

    The ASCII art rendering engine — which converts OpenAPI endpoints
    into box-drawing characters and [Try It] buttons — has encountered
    a rendering error. The Swagger UI cannot be displayed, which means
    the terminal-based documentation for the non-existent API will
    remain invisible. Some might argue this is an improvement.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"ASCII Swagger UI render failed: {reason}. "
            f"The box-drawing characters have refused to draw boxes. "
            f"The [Try It] buttons cannot be tried. The swagger has left the UI.",
            error_code="EFP-OA05",
            context={"reason": reason},
        )


class OpenAPIDashboardRenderError(OpenAPIError):
    """Raised when the OpenAPI dashboard fails to render.

    The statistics dashboard — a compact summary of endpoints, schemas,
    and exception mappings — has failed to render. The meta-dashboard
    about the meta-specification has experienced a meta-failure. We are
    now three levels deep in the meta-stack and the box-drawing characters
    are getting dizzy.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"OpenAPI dashboard render failed: {reason}. "
            f"The dashboard summarizing the spec describing the API that "
            f"doesn't exist has itself failed to appear. Peak enterprise.",
            error_code="EFP-OA06",
            context={"reason": reason},
        )


class OpenAPISerializationError(OpenAPIError):
    """Raised when the OpenAPI spec cannot be serialized to JSON or YAML.

    The specification was generated successfully in memory but could not
    be serialized to a string format. Perhaps a value is not JSON-serializable,
    or the YAML formatter encountered a type it cannot represent. Either way,
    the documentation exists only in RAM, which is appropriate for a platform
    whose entire state exists only in RAM.
    """

    def __init__(self, format_name: str, reason: str) -> None:
        super().__init__(
            f"OpenAPI spec serialization to {format_name} failed: {reason}. "
            f"The specification cannot be exported. It will remain an "
            f"in-memory representation of a non-existent API.",
            error_code="EFP-OA07",
            context={"format_name": format_name, "reason": reason},
        )
        self.format_name = format_name


class InvalidEndpointPathError(OpenAPIError):
    """Raised when an endpoint path does not conform to OpenAPI path syntax.

    OpenAPI paths must start with '/' and use '{paramName}' for path
    parameters. Your path either forgot the leading slash (barbaric),
    used angle brackets instead of curly braces (XML contamination),
    or contained characters that no URL should ever contain.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            f"Invalid OpenAPI endpoint path '{path}': {reason}. "
            f"Paths must start with '/' and use curly braces for parameters. "
            f"This is not negotiable. RFC 3986 has opinions.",
            error_code="EFP-OA08",
            context={"path": path, "reason": reason},
        )
        self.path = path


class DuplicateOperationIdError(OpenAPIError):
    """Raised when two endpoints share the same operationId.

    Every endpoint must have a unique operationId, because the OpenAPI
    spec says so and we are nothing if not compliant with specifications
    — even when documenting an API that violates the most fundamental
    specification of all: having a server.
    """

    def __init__(self, operation_id: str, path_a: str, path_b: str) -> None:
        super().__init__(
            f"Duplicate operationId '{operation_id}' found in '{path_a}' "
            f"and '{path_b}'. Operation IDs must be unique across the entire "
            f"spec. Even fictional APIs have standards.",
            error_code="EFP-OA09",
            context={
                "operation_id": operation_id,
                "path_a": path_a,
                "path_b": path_b,
            },
        )
        self.operation_id = operation_id


class SecuritySchemeNotFoundError(OpenAPIError):
    """Raised when a referenced security scheme does not exist.

    The endpoint references a security scheme that has not been defined
    in the components/securitySchemes section. This is the OpenAPI
    equivalent of citing a source that doesn't exist in an academic paper.
    The peer reviewers (validators) will not be pleased.
    """

    def __init__(self, scheme_name: str) -> None:
        super().__init__(
            f"Security scheme '{scheme_name}' not found in components. "
            f"The endpoint references a security mechanism that has not "
            f"been defined. Authentication is hard enough without phantom "
            f"security schemes.",
            error_code="EFP-OA10",
            context={"scheme_name": scheme_name},
        )
        self.scheme_name = scheme_name


class TagNotFoundError(OpenAPIError):
    """Raised when an endpoint references a tag that has no description.

    Every tag used by endpoints should have a corresponding entry in the
    tags section with a description. An undescribed tag is like an
    unlabeled filing cabinet: technically functional, but deeply
    unsatisfying to anyone who values organizational hygiene.
    """

    def __init__(self, tag_name: str) -> None:
        super().__init__(
            f"Tag '{tag_name}' used by endpoint but not defined in tags section. "
            f"Every tag deserves a description. Even in a spec for an API that "
            f"doesn't exist, we maintain documentation standards.",
            error_code="EFP-OA11",
            context={"tag_name": tag_name},
        )
        self.tag_name = tag_name


class GatewayError(FizzBuzzError):
    """Base exception for all API Gateway errors.

    When your API Gateway for a CLI application that has no HTTP server
    encounters an error, you've achieved a level of architectural ambition
    that most enterprise architects can only dream of. These exceptions
    cover everything from route resolution failures to version deprecation
    tantrums to request transformation meltdowns — all for an API that
    exists entirely in the imagination of the YAML configuration file.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-GW00"),
            context=kwargs.pop("context", {}),
        )


class RouteNotFoundError(GatewayError):
    """Raised when no route matches the incoming API request path.

    The request arrived at the gateway's door, knocked politely, and
    was turned away because no route existed to handle it. Perhaps the
    path was misspelled, perhaps it never existed, or perhaps the
    routing table was last updated during the previous fiscal quarter.
    """

    def __init__(self, path: str, method: str) -> None:
        super().__init__(
            f"No route found for {method} {path}. The gateway searched "
            f"every routing table, consulted the map, and found only wilderness.",
            error_code="EFP-GW01",
            context={"path": path, "method": method},
        )
        self.path = path
        self.method = method


class VersionNotSupportedError(GatewayError):
    """Raised when the requested API version is not supported.

    The client requested an API version that either never existed,
    has been deprecated into oblivion, or belongs to a future release
    that exists only in the product roadmap. Time travel is not yet
    supported by the Enterprise FizzBuzz Platform gateway.
    """

    def __init__(self, version: str, supported_versions: list[str]) -> None:
        super().__init__(
            f"API version '{version}' is not supported. "
            f"Supported versions: {', '.join(supported_versions)}. "
            f"The gateway recommends upgrading to a version that exists.",
            error_code="EFP-GW02",
            context={"version": version, "supported_versions": supported_versions},
        )
        self.version = version
        self.supported_versions = supported_versions


class VersionDeprecatedError(GatewayError):
    """Raised when the requested API version is deprecated.

    The client is clinging to an API version that has been formally
    deprecated. Like a software archaeologist unearthing ancient
    endpoints, you are accessing routes that time forgot. The Sunset
    header has been set. The countdown has begun. Please migrate
    before the version is removed entirely and your requests fall
    into the void.
    """

    def __init__(self, version: str, sunset_date: str) -> None:
        super().__init__(
            f"API version '{version}' is DEPRECATED. Sunset date: {sunset_date}. "
            f"Your requests are living on borrowed time. Please migrate "
            f"to a supported version before it's too late.",
            error_code="EFP-GW03",
            context={"version": version, "sunset_date": sunset_date},
        )
        self.version = version
        self.sunset_date = sunset_date


class RequestTransformationError(GatewayError):
    """Raised when a request transformer fails to process the request.

    The request entered the transformation pipeline full of hope and
    left as a mangled data structure that no downstream handler could
    parse. The transformer chain is supposed to enrich, normalize,
    and validate — not destroy. Something went very wrong in the
    metadata enrichment phase, probably the lunar phase calculator.
    """

    def __init__(self, transformer_name: str, reason: str) -> None:
        super().__init__(
            f"Request transformer '{transformer_name}' failed: {reason}. "
            f"The request has been irrevocably transformed into something "
            f"no downstream handler can recognize.",
            error_code="EFP-GW04",
            context={"transformer_name": transformer_name, "reason": reason},
        )
        self.transformer_name = transformer_name


class ResponseTransformationError(GatewayError):
    """Raised when a response transformer fails to process the response.

    The response was perfectly fine until the transformation pipeline
    got its hands on it. Now it's been gzipped, base64-encoded,
    wrapped in pagination metadata, and adorned with HATEOAS links
    to related endpoints — and something in that process
    went sideways.
    """

    def __init__(self, transformer_name: str, reason: str) -> None:
        super().__init__(
            f"Response transformer '{transformer_name}' failed: {reason}. "
            f"The response has been lost in the transformation pipeline. "
            f"The original data is irretrievable. Thoughts and prayers.",
            error_code="EFP-GW05",
            context={"transformer_name": transformer_name, "reason": reason},
        )
        self.transformer_name = transformer_name


class APIKeyInvalidError(GatewayError):
    """Raised when the provided API key is invalid or revoked.

    The API key you presented has been examined by the gateway's
    key validation service and found to be either invalid, revoked,
    expired, or simply not a real Enterprise FizzBuzz Platform API key.
    Perhaps you generated it at a different FizzBuzz platform. Perhaps
    you made it up. Either way, access is denied with extreme prejudice.
    """

    def __init__(self, key_prefix: str, reason: str) -> None:
        super().__init__(
            f"API key '{key_prefix}...' is invalid: {reason}. "
            f"Please generate a new key using --api-key-generate.",
            error_code="EFP-GW06",
            context={"key_prefix": key_prefix, "reason": reason},
        )


class APIKeyQuotaExceededError(GatewayError):
    """Raised when an API key has exhausted its request quota.

    Your API key has been used so many times that it has worn out.
    Like a subway pass that's been swiped too many times, it simply
    refuses to grant passage. The quota exists to protect the platform
    from being overwhelmed by excessive FizzBuzz requests, which is
    a real and present danger in today's fast-paced modulo economy.
    """

    def __init__(self, key_prefix: str, quota_limit: int, quota_used: int) -> None:
        super().__init__(
            f"API key '{key_prefix}...' has exceeded its quota: "
            f"{quota_used}/{quota_limit} requests consumed. "
            f"Consider purchasing the Enterprise FizzBuzz Unlimited plan.",
            error_code="EFP-GW07",
            context={"key_prefix": key_prefix, "quota_limit": quota_limit, "quota_used": quota_used},
        )


class RequestReplayError(GatewayError):
    """Raised when request replay from the journal fails.

    The append-only request journal faithfully recorded every request
    that passed through the gateway. When you asked to replay them,
    something went wrong — perhaps the journal was corrupted, perhaps
    the requests reference routes that no longer exist, or perhaps
    replaying modulo arithmetic requests is simply not as straightforward
    as the architecture diagrams suggested.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Request replay failed: {reason}. The journal entries are "
            f"intact but the replay engine has lost confidence in its "
            f"ability to re-execute them faithfully.",
            error_code="EFP-GW08",
            context={"reason": reason},
        )


class GatewayDashboardRenderError(GatewayError):
    """Raised when the gateway ASCII dashboard fails to render.

    The dashboard — a lovingly crafted ASCII art visualization of
    your API Gateway's routing tables, version status, and request
    statistics — has failed to render. The gateway itself continues
    to function perfectly; it is only the observation of the gateway
    that has failed. Schrodinger's dashboard: simultaneously rendered
    and unrendered until you look at it.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Gateway dashboard render failed: {reason}. "
            f"The ASCII art remains undrawn. The statistics unvisualized. "
            f"The gateway, however, continues to route — unobserved.",
            error_code="EFP-GW09",
            context={"reason": reason},
        )


# ============================================================
# Blue/Green Deployment Simulation Exceptions
# ============================================================
# Zero-downtime blue/green deployment ensures safe releases
# with automated canary validation, shadow traffic mirroring,
# smoke tests, bake periods, and instant rollback capability.
# ============================================================


class DeploymentError(FizzBuzzError):
    """Base exception for all Blue/Green Deployment Simulation errors.

    When your zero-downtime deployment system for a CLI tool that runs
    for less than a second encounters a failure, you must ask yourself:
    what downtime are we even trying to avoid? The answer, as always
    in enterprise software, is irrelevant. The ceremony must proceed.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-BG00"),
            context=kwargs.pop("context", {}),
        )


class SlotProvisioningError(DeploymentError):
    """Raised when a deployment slot fails to provision.

    A deployment slot is essentially a variable that holds a reference
    to a StandardRuleEngine. If assigning a variable has failed, the
    laws of computer science have been violated at a fundamental level.
    Consider restarting the universe.
    """

    def __init__(self, color: str, reason: str) -> None:
        super().__init__(
            f"Failed to provision {color} deployment slot: {reason}. "
            f"Assigning a variable has somehow failed. This is unprecedented.",
            error_code="EFP-BG01",
            context={"color": color, "reason": reason},
        )


class ShadowTrafficError(DeploymentError):
    """Raised when shadow traffic comparison detects a discrepancy.

    Both slots received the same input and produced different outputs.
    Since both slots contain identical FizzBuzz rule engines, this
    should be mathematically impossible. If 15 % 3 equals 0 on the
    blue slot but not on the green slot, either mathematics is broken
    or someone has been tampering with the deployment slots.
    """

    def __init__(self, number: int, blue_result: str, green_result: str) -> None:
        super().__init__(
            f"Shadow traffic mismatch for number {number}: "
            f"blue='{blue_result}', green='{green_result}'. "
            f"Mathematics appears to be non-deterministic. Page the on-call physicist.",
            error_code="EFP-BG02",
            context={"number": number, "blue_result": blue_result, "green_result": green_result},
        )


class SmokeTestFailureError(DeploymentError):
    """Raised when a deployment smoke test fails.

    The canary numbers [3, 5, 15, 42, 97] were evaluated against the
    green slot and at least one produced an unexpected result. The
    green slot is not ready for production traffic, which consists
    of exactly one user running a CLI tool.
    """

    def __init__(self, number: int, expected: str, actual: str) -> None:
        super().__init__(
            f"Smoke test failed for canary number {number}: "
            f"expected '{expected}', got '{actual}'. "
            f"The green slot is not yet worthy of production traffic.",
            error_code="EFP-BG03",
            context={"number": number, "expected": expected, "actual": actual},
        )


class BakePeriodError(DeploymentError):
    """Raised when the bake period monitoring detects instability.

    The green slot was placed under observation for a brief period
    of time (measured in milliseconds) and was found wanting. In
    real deployments, bake periods catch latent issues. Here, the
    bake period catches the existential dread of a FizzBuzz engine
    that has been given too much responsibility too soon.
    """

    def __init__(self, duration_ms: float, reason: str) -> None:
        super().__init__(
            f"Bake period failed after {duration_ms:.2f}ms: {reason}. "
            f"The green slot was not stable long enough to earn trust.",
            error_code="EFP-BG04",
            context={"duration_ms": duration_ms, "reason": reason},
        )


class CutoverError(DeploymentError):
    """Raised when the cutover from blue to green fails.

    The atomic swap — which is literally just `self.active = green` —
    has somehow failed. This is the deployment equivalent of failing
    to flip a light switch. If a single variable assignment can fail,
    all hope is lost.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Cutover failed: {reason}. The atomic variable assignment "
            f"has encountered a non-atomic problem. This should not be possible.",
            error_code="EFP-BG05",
            context={"reason": reason},
        )


class DeploymentRollbackError(DeploymentError):
    """Raised when a rollback to the blue slot fails.

    Rolling back means setting `self.active = blue`. If this fails,
    the deployment system has lost the ability to assign variables,
    which is a problem that transcends deployment strategy and enters
    the realm of fundamental computational theory.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Rollback failed: {reason}. The variable assignment that was "
            f"supposed to restore the blue slot has failed. "
            f"Zero users impacted. (There was one user.)",
            error_code="EFP-BG06",
            context={"reason": reason},
        )


class DeploymentPhaseError(DeploymentError):
    """Raised when a deployment phase transition is invalid.

    The deployment orchestrator maintains a strict phase lifecycle:
    Provision -> Shadow -> SmokeTest -> BakePeriod -> Cutover -> Monitor.
    Attempting to skip a phase or go backwards violates the
    deployment protocol, and the orchestrator will reject the
    transition as unsafe.
    """

    def __init__(self, current_phase: str, attempted_phase: str) -> None:
        super().__init__(
            f"Invalid deployment phase transition: '{current_phase}' -> "
            f"'{attempted_phase}'. The deployment ceremony must proceed "
            f"in the prescribed order. No shortcuts.",
            error_code="EFP-BG07",
            context={"current_phase": current_phase, "attempted_phase": attempted_phase},
        )


class PipelineDashboardRenderError(DataPipelineError):
    """Raised when the pipeline ASCII dashboard fails to render.

    The dashboard — a lovingly crafted ASCII art visualization of
    your five-stage linear pipeline — has failed to render. The
    data is flowing correctly through the pipeline, but the
    observation of that flow has broken. Heisenberg would have
    something to say about this, but his quote would also fail
    to render.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Pipeline dashboard render failed: {reason}. "
            f"The ASCII art remains undrawn. The DAG unvisualized. "
            f"The pipeline, however, continues to function — unobserved.",
            error_code="EFP-DP12",
            context={"reason": reason},
        )


# ============================================================
# Graph Database Exceptions (EFP-GD01 through EFP-GD08)
# ============================================================


class GraphDatabaseError(FizzBuzzError):
    """Base exception for all Graph Database subsystem errors.

    When your in-memory property graph of integer divisibility
    relationships encounters an error, a critical graph subsystem
    failure has occurred. These exceptions cover everything from node creation
    failures to CypherLite parse errors to community detection
    existential crises.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-GD00"),
            context=kwargs.pop("context", {}),
        )


class GraphNodeCreationError(GraphDatabaseError):
    """Raised when a node cannot be created in the property graph.

    A node was supposed to join the graph, but something went wrong.
    Perhaps the node ID collided with an existing node, or perhaps
    the graph has reached a philosophical objection to storing more
    integers. Either way, this number will not be represented in
    the grand relationship map of FizzBuzz.
    """

    def __init__(self, node_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to create node '{node_id}': {reason}. "
            f"The graph refuses to acknowledge this entity.",
            error_code="EFP-GD01",
            context={"node_id": node_id, "reason": reason},
        )


class GraphEdgeCreationError(GraphDatabaseError):
    """Raised when an edge cannot be created between two nodes.

    The relationship between these two nodes cannot be established.
    Perhaps one of the endpoints doesn't exist, or perhaps the
    graph engine has determined that these two nodes are simply
    incompatible and should not be connected. Mathematical
    matchmaking is a delicate business.
    """

    def __init__(self, source_id: str, target_id: str, edge_type: str, reason: str) -> None:
        super().__init__(
            f"Failed to create edge [{source_id}]-[:{edge_type}]->[{target_id}]: {reason}.",
            error_code="EFP-GD02",
            context={
                "source_id": source_id,
                "target_id": target_id,
                "edge_type": edge_type,
                "reason": reason,
            },
        )


class CypherLiteError(GraphDatabaseError):
    """Raised when a CypherLite query fails to parse or execute.

    The CypherLite query language — our simplified, artisanal,
    hand-crafted subset of Cypher — has encountered a query it
    cannot understand. This is either a syntax error, a semantic
    error, or the query attempted to use a feature from actual
    Cypher that we haven't bothered to implement.
    """

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            f"CypherLite query failed: {reason}. Query: {query!r}",
            error_code="EFP-GD03",
            context={"query": query, "reason": reason},
        )


class GraphPopulationError(GraphDatabaseError):
    """Raised when the graph population phase encounters an error.

    The graph was being populated with FizzBuzz relationship data
    when something went wrong. Perhaps the range was invalid, or
    perhaps the graph engine discovered that the integers 1 through
    100 have more complex social dynamics than it was prepared to
    handle.
    """

    def __init__(self, start: int, end: int, reason: str) -> None:
        super().__init__(
            f"Graph population failed for range [{start}, {end}]: {reason}. "
            f"The integers remain unmapped. Their relationships, undiscovered.",
            error_code="EFP-GD04",
            context={"start": start, "end": end, "reason": reason},
        )


class GraphAnalysisError(GraphDatabaseError):
    """Raised when a graph analysis operation fails.

    The graph analyzer — a sophisticated engine of centrality
    calculations, community detection, and isolation measurement —
    has encountered an error. The social dynamics of your integers
    remain unanalyzed, and the Most Isolated Number Award ceremony
    has been postponed indefinitely.
    """

    def __init__(self, analysis_type: str, reason: str) -> None:
        super().__init__(
            f"Graph analysis '{analysis_type}' failed: {reason}. "
            f"The integers' social network remains uncharted.",
            error_code="EFP-GD05",
            context={"analysis_type": analysis_type, "reason": reason},
        )


# ============================================================
# Genetic Algorithm Exceptions
# ============================================================


class GeneticAlgorithmError(FizzBuzzError):
    """Base exception for all Genetic Algorithm subsystem errors.

    The GA — a sophisticated evolutionary computation engine tasked
    with the Herculean challenge of rediscovering that 3 divides into
    "Fizz" and 5 divides into "Buzz" — has encountered an error.
    Darwin would be disappointed. Or relieved.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-GA00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ChromosomeValidationError(GeneticAlgorithmError):
    """Raised when a chromosome fails structural validation.

    A chromosome — the genetic blueprint for a FizzBuzz rule set —
    has been found to contain invalid genes. Perhaps a divisor of
    zero slipped through, or a label consisted entirely of whitespace.
    Natural selection will handle the rest, but we prefer to catch
    these malformations early.
    """

    def __init__(self, chromosome_id: str, reason: str) -> None:
        super().__init__(
            f"Chromosome '{chromosome_id}' failed validation: {reason}. "
            f"This organism is not fit for the gene pool.",
            error_code="EFP-GA01",
            context={"chromosome_id": chromosome_id, "reason": reason},
        )


class FitnessEvaluationError(GeneticAlgorithmError):
    """Raised when the fitness evaluator fails to score a chromosome.

    The fitness function — a multi-objective scoring system that
    considers accuracy, coverage, distinctness, phonetic harmony,
    and mathematical elegance — has encountered a chromosome so
    pathological that it cannot even be scored. This is the genetic
    equivalent of a job applicant who submits a blank resume.
    """

    def __init__(self, chromosome_id: str, reason: str) -> None:
        super().__init__(
            f"Fitness evaluation failed for chromosome '{chromosome_id}': {reason}. "
            f"This organism defies measurement.",
            error_code="EFP-GA02",
            context={"chromosome_id": chromosome_id, "reason": reason},
        )


class SelectionPressureError(GeneticAlgorithmError):
    """Raised when selection pressure is misconfigured or collapses.

    Tournament selection requires at least two contestants, because
    a tournament of one is just existentialism. If the population
    has been reduced to fewer organisms than the tournament size,
    evolution has effectively ended — not with a bang, but with a
    whimper and an index error.
    """

    def __init__(self, population_size: int, tournament_size: int) -> None:
        super().__init__(
            f"Selection pressure collapsed: population size {population_size} "
            f"is smaller than tournament size {tournament_size}. "
            f"Evolution requires competition. This is just loneliness.",
            error_code="EFP-GA03",
            context={"population_size": population_size, "tournament_size": tournament_size},
        )


class CrossoverIncompatibilityError(GeneticAlgorithmError):
    """Raised when two chromosomes cannot be crossed over.

    Two chromosomes have been selected for mating, but they are
    fundamentally incompatible. Perhaps one has zero genes, or both
    are identical clones. In nature, this would be resolved by the
    organisms simply walking away. In software, we throw an exception.
    """

    def __init__(self, parent_a_id: str, parent_b_id: str, reason: str) -> None:
        super().__init__(
            f"Crossover failed between '{parent_a_id}' and '{parent_b_id}': {reason}. "
            f"These chromosomes are genetically incompatible.",
            error_code="EFP-GA04",
            context={"parent_a_id": parent_a_id, "parent_b_id": parent_b_id},
        )


class MutationError(GeneticAlgorithmError):
    """Raised when a mutation operation produces an invalid result.

    A mutation — one of five possible types including divisor_shift,
    label_swap, rule_insertion, rule_deletion, and priority_shuffle —
    has produced a chromosome that violates the laws of FizzBuzz
    biology. The mutation was too radical, even for evolution.
    """

    def __init__(self, mutation_type: str, chromosome_id: str, reason: str) -> None:
        super().__init__(
            f"Mutation '{mutation_type}' on chromosome '{chromosome_id}' failed: {reason}. "
            f"Evolution took a wrong turn.",
            error_code="EFP-GA05",
            context={"mutation_type": mutation_type, "chromosome_id": chromosome_id},
        )


class ConvergenceTimeoutError(GeneticAlgorithmError):
    """Raised when the GA fails to converge within the allotted generations.

    After exhausting all configured generations, the genetic algorithm
    has not converged on a satisfactory solution. The population
    remains diverse but directionless, like a committee that has been
    meeting weekly for years without producing a single deliverable.
    In practice this should never happen because the canonical
    {3:"Fizz", 5:"Buzz"} solution is seeded into the initial
    population, but enterprise software must plan for the impossible.
    """

    def __init__(self, generations: int, best_fitness: float) -> None:
        super().__init__(
            f"GA failed to converge after {generations} generations. "
            f"Best fitness achieved: {best_fitness:.6f}. "
            f"Evolution has given up. Consider more generations or better genes.",
            error_code="EFP-GA06",
            context={"generations": generations, "best_fitness": best_fitness},
        )


class PopulationExtinctionError(GeneticAlgorithmError):
    """Raised when the entire population has been eliminated.

    Mass extinction has reduced the population to zero viable
    organisms. There is no one left to evolve. The gene pool is
    empty. The fitness landscape is a barren wasteland. This is
    the evolutionary equivalent of a production database being
    accidentally truncated.
    """

    def __init__(self, generation: int, cause: str) -> None:
        super().__init__(
            f"Population extinction at generation {generation}: {cause}. "
            f"All organisms have perished. The experiment is over.",
            error_code="EFP-GA07",
            context={"generation": generation, "cause": cause},
        )


class GraphVisualizationError(GraphDatabaseError):
    """Raised when the ASCII graph visualization fails to render.

    The graph visualizer attempted to draw a beautiful ASCII
    representation of the FizzBuzz relationship network, but the
    art could not be completed. The nodes remain unboxed, the
    edges unarrowed, and the terminal uncluttered. Perhaps this
    is a blessing in disguise.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Graph visualization failed: {reason}. "
            f"The ASCII art remains a figment of the imagination.",
            error_code="EFP-GD06",
            context={"reason": reason},
        )


class GraphMiddlewareError(GraphDatabaseError):
    """Raised when the graph middleware fails during pipeline processing.

    The graph middleware — which quietly builds graph edges as numbers
    flow through the evaluation pipeline — has encountered an error.
    The evaluation itself likely succeeded, but the graph's record
    of that evaluation is incomplete. It's like a social media platform
    where your activity is logged except when it isn't.
    """

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Graph middleware failed for number {number}: {reason}. "
            f"The number was evaluated, but the graph didn't notice.",
            error_code="EFP-GD07",
            context={"number": number, "reason": reason},
        )


class GraphDashboardRenderError(GraphDatabaseError):
    """Raised when the graph analytics dashboard fails to render.

    The dashboard — a lovingly crafted ASCII art visualization of
    centrality rankings, community maps, and isolation awards — has
    failed to render. The analytics data is correct, but the
    presentation layer has given up. The graph's stories remain
    untold, its communities unnamed, its isolated primes uncelebrated.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Graph dashboard render failed: {reason}. "
            f"The analytics remain locked in the data layer, "
            f"yearning for ASCII representation.",
            error_code="EFP-GD08",
            context={"reason": reason},
        )


# ----------------------------------------------------------------
# Natural Language Query Interface Exceptions
# ----------------------------------------------------------------
# Because querying FizzBuzz results in plain English requires a
# full-blown NLP error taxonomy. Every tokenization failure, every
# unrecognized intent, every entity that refuses to be extracted
# deserves its own lovingly documented exception class.
# ----------------------------------------------------------------


class NLQError(FizzBuzzError):
    """Base exception for all Natural Language Query Interface errors.

    When the enterprise-grade, regex-powered, artisanally hand-crafted
    natural language processing pipeline fails to comprehend your
    perfectly reasonable question about divisibility, this is the
    exception hierarchy that catches the pieces.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-NLQ0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class NLQTokenizationError(NLQError):
    """Raised when the tokenizer fails to decompose a query into tokens.

    The regex-based lexer has encountered a string so incomprehensible
    that even our carefully curated pattern list — which handles numbers,
    keywords, and the occasional existential question about modulo
    arithmetic — has thrown up its hands in defeat.
    """

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            f"Tokenization failed for query {query!r}: {reason}. "
            f"The regex engine has seen things it cannot unsee.",
            error_code="EFP-NLQ1",
            context={"query": query, "reason": reason},
        )


class NLQIntentClassificationError(NLQError):
    """Raised when the intent classifier cannot determine what the user wants.

    The rule-based decision tree — a sophisticated cascade of if/elif
    statements disguised as enterprise architecture — has examined your
    query from every angle and concluded that it has no idea what you're
    asking. Perhaps try phrasing your FizzBuzz question more corporately.
    """

    def __init__(self, query: str, tokens: Optional[list[str]] = None) -> None:
        super().__init__(
            f"Cannot classify intent for query {query!r}. "
            f"Tokens: {tokens or []}. The decision tree is stumped.",
            error_code="EFP-NLQ2",
            context={"query": query, "tokens": tokens or []},
        )


class NLQEntityExtractionError(NLQError):
    """Raised when the entity extractor fails to find actionable entities.

    Your query was understood at an intent level — we know you want
    something — but the entity extractor could not find any numbers,
    ranges, or classifications to operate on. It's like ordering at
    a restaurant but forgetting to specify what food you want.
    """

    def __init__(self, query: str, intent: str) -> None:
        super().__init__(
            f"Entity extraction failed for query {query!r} with intent '{intent}'. "
            f"No numbers, ranges, or classifications could be extracted. "
            f"The query is syntactically ambitious but semantically vacant.",
            error_code="EFP-NLQ3",
            context={"query": query, "intent": intent},
        )


class NLQExecutionError(NLQError):
    """Raised when query execution fails after successful parsing.

    The query was tokenized, the intent was classified, the entities
    were extracted — everything was going so well — and then the
    execution engine encountered an error. This is the NLQ equivalent
    of a plane that taxis, takes off, and then remembers it has no wings.
    """

    def __init__(self, query: str, intent: str, reason: str) -> None:
        super().__init__(
            f"Execution failed for query {query!r} (intent: {intent}): {reason}. "
            f"The parsing was flawless. The execution was not.",
            error_code="EFP-NLQ4",
            context={"query": query, "intent": intent, "reason": reason},
        )


class NLQUnsupportedQueryError(NLQError):
    """Raised when a query is syntactically valid but semantically unsupported.

    We understood what you said. We even agree it's a reasonable thing
    to ask. We just don't support it yet because the Enterprise FizzBuzz
    NLQ roadmap prioritizes other features, including expanded query
    coverage and additional semantic analysis capabilities.
    """

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            f"Unsupported query {query!r}: {reason}. "
            f"This feature is on the NLQ roadmap, tentatively scheduled "
            f"for the heat death of the universe.",
            error_code="EFP-NLQ5",
            context={"query": query, "reason": reason},
        )


# ================================================================
# Load Testing Framework Exceptions
# ================================================================
# Because the only thing more important than computing FizzBuzz
# correctly is proving that you can compute it correctly under
# simulated production traffic from hundreds of virtual users
# who all urgently need to know whether 15 is FizzBuzz.
# ================================================================

class LoadTestError(FizzBuzzError):
    """Base exception for all load testing framework errors.

    When your performance test infrastructure itself becomes a
    performance bottleneck, you've achieved a level of meta-irony
    that most enterprise architects can only dream of.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-LT00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class LoadTestConfigurationError(LoadTestError):
    """Raised when load test parameters fail validation.

    You asked for negative virtual users, or zero iterations, or a
    ramp-up duration longer than the heat death of the universe.
    The load testing framework has standards, even if those standards
    are applied to a program that computes modulo arithmetic.
    """

    def __init__(self, parameter: str, value: Any, expected: str) -> None:
        super().__init__(
            f"Invalid load test parameter '{parameter}': got {value!r}, "
            f"expected {expected}. Even simulated traffic has rules.",
            error_code="EFP-LT01",
            context={"parameter": parameter, "value": value, "expected": expected},
        )


class VirtualUserSpawnError(LoadTestError):
    """Raised when a virtual user fails to spawn.

    The virtual user was ready, willing, and eager to evaluate FizzBuzz
    at scale. But something went wrong during thread creation, and now
    there's one fewer simulated human desperately needing to know if
    42 is divisible by 3.
    """

    def __init__(self, vu_id: int, reason: str) -> None:
        super().__init__(
            f"Failed to spawn Virtual User #{vu_id}: {reason}. "
            f"The thread pool has rejected our request for more FizzBuzz workers.",
            error_code="EFP-LT02",
            context={"vu_id": vu_id, "reason": reason},
        )


class LoadTestTimeoutError(LoadTestError):
    """Raised when the load test exceeds its maximum duration.

    The load test was supposed to finish by now, but the virtual users
    are still out there, evaluating FizzBuzz, blissfully unaware that
    their time has expired. Like a meeting that should have been an email.
    """

    def __init__(self, elapsed_seconds: float, timeout_seconds: float) -> None:
        super().__init__(
            f"Load test timed out after {elapsed_seconds:.1f}s "
            f"(limit: {timeout_seconds:.0f}s). The modulo operator is "
            f"performing within normal parameters; the test harness is not.",
            error_code="EFP-LT03",
            context={
                "elapsed_seconds": elapsed_seconds,
                "timeout_seconds": timeout_seconds,
            },
        )


class BottleneckAnalysisError(LoadTestError):
    """Raised when bottleneck analysis fails due to insufficient data.

    You can't identify the slowest subsystem if no subsystem has been
    measured. It's the performance engineering equivalent of asking
    "which of zero things is the biggest?" The answer is philosophical,
    not computational.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Bottleneck analysis failed: {reason}. "
            f"Collect more metrics before attempting to identify "
            f"which part of your modulo arithmetic is slowest.",
            error_code="EFP-LT04",
            context={"reason": reason},
        )


class PerformanceGradeError(LoadTestError):
    """Raised when performance grading encounters an impossible state.

    The grading rubric has been violated in a way that should not be
    possible under the laws of mathematics. Either the latency is
    negative (time travel), or the throughput exceeds the speed of
    light. Either way, the grade is 'F' for 'Fantasy.'
    """

    def __init__(self, metric: str, value: float) -> None:
        super().__init__(
            f"Cannot grade performance metric '{metric}' with value "
            f"{value}: value is outside the grading rubric's domain. "
            f"Physics may be broken. Please restart the universe.",
            error_code="EFP-LT05",
            context={"metric": metric, "value": value},
        )


# ================================================================
# Audit Dashboard & Real-Time Event Streaming Exceptions
# ================================================================


class AuditDashboardError(FizzBuzzError):
    """Base exception for the Unified Audit Dashboard subsystem.

    When your observability-of-observability layer fails, you've
    reached the event horizon of enterprise monitoring. The audit
    dashboard was supposed to watch the watchers, but now the
    watchers need watching themselves. Quis custodiet ipsos custodes?
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-AD00"),
            context=kwargs.pop("context", {}),
        )


class EventAggregationError(AuditDashboardError):
    """Raised when an event cannot be normalized into a UnifiedAuditEvent.

    The raw event was so malformed, so chaotically structured, that
    even our maximally permissive normalization pipeline couldn't
    make sense of it. This event has been deemed un-auditable, which
    in compliance terms is a fate worse than deletion.
    """

    def __init__(self, event_type: str, reason: str) -> None:
        super().__init__(
            f"Failed to aggregate event of type '{event_type}': {reason}. "
            f"This event will be lost to the audit void.",
            error_code="EFP-AD01",
            context={"event_type": event_type, "reason": reason},
        )


class AnomalyDetectionError(AuditDashboardError):
    """Raised when the anomaly detection engine encounters an invalid state.

    The z-score computation has failed, which means either the sample
    size is too small for statistical significance, or the standard
    deviation is zero (all events are identical, which is itself
    anomalous). The anomaly detector has detected an anomaly in
    itself. This is peak enterprise recursion.
    """

    def __init__(self, metric: str, reason: str) -> None:
        super().__init__(
            f"Anomaly detection failed for metric '{metric}': {reason}. "
            f"The statistical engine is having an existential crisis.",
            error_code="EFP-AD02",
            context={"metric": metric, "reason": reason},
        )


class TemporalCorrelationError(AuditDashboardError):
    """Raised when the temporal correlator fails to group events.

    The correlator attempted to find meaningful relationships between
    events but encountered an impossible temporal configuration.
    Events appearing before the Big Bang or after the heat death
    of the universe are outside the supported correlation window.
    """

    def __init__(self, correlation_id: str, reason: str) -> None:
        super().__init__(
            f"Temporal correlation failed for '{correlation_id}': {reason}. "
            f"The space-time fabric of your FizzBuzz pipeline is wrinkled.",
            error_code="EFP-AD03",
            context={"correlation_id": correlation_id, "reason": reason},
        )


class EventStreamError(AuditDashboardError):
    """Raised when the NDJSON event stream encounters a serialization failure.

    The event could not be serialized to JSON, which for a system
    that deals primarily in integers and strings is an achievement
    in failure. Perhaps the payload contains a circular reference,
    or perhaps it contains a datetime that refuses to be ISO-formatted.
    Either way, this event will not be streamed.
    """

    def __init__(self, event_id: str, reason: str) -> None:
        super().__init__(
            f"Event stream serialization failed for event '{event_id}': {reason}. "
            f"The event has been lost to the entropy of stdout.",
            error_code="EFP-AD04",
            context={"event_id": event_id, "reason": reason},
        )


class DashboardRenderError(AuditDashboardError):
    """Raised when the multi-pane ASCII dashboard fails to render.

    The dashboard attempted to render six ASCII panes into a terminal
    window and failed. This is usually caused by a terminal width of
    zero (are you running FizzBuzz inside /dev/null?), or by an event
    buffer that somehow contains negative entries. The dashboard will
    gracefully degrade to printing "everything is fine" in monospace.
    """

    def __init__(self, pane: str, reason: str) -> None:
        super().__init__(
            f"Dashboard pane '{pane}' failed to render: {reason}. "
            f"The ASCII art has been compromised.",
            error_code="EFP-AD05",
            context={"pane": pane, "reason": reason},
        )


# ============================================================
# GitOps Configuration-as-Code Simulator Exceptions
# ============================================================

class GitOpsError(FizzBuzzError):
    """Base exception for the GitOps Configuration-as-Code Simulator.

    When your version-controlled YAML configuration for a FizzBuzz
    platform encounters a merge conflict, you know the industry has
    achieved peak enterprise. These exceptions cover everything from
    branch not found to policy violations to the existential question
    of why a single-process CLI application needs a change approval
    pipeline with dry-run simulation and blast radius estimation.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-G000"),
            context=kwargs.pop("context", {}),
        )


class GitOpsBranchNotFoundError(GitOpsError):
    """Raised when a referenced branch does not exist in the config repository.

    You attempted to checkout, merge, or otherwise interact with a branch
    that simply isn't there. Perhaps it was deleted, perhaps it was never
    created, or perhaps you're confusing this in-memory git simulator with
    actual git. Either way, the branch is as fictional as this entire
    version control system.
    """

    def __init__(self, branch_name: str) -> None:
        super().__init__(
            f"Branch '{branch_name}' not found in the configuration repository. "
            f"Available branches may be listed with --gitops-log. "
            f"Consider creating the branch first, or accepting that some branches "
            f"were never meant to exist.",
            error_code="EFP-G001",
            context={"branch_name": branch_name},
        )
        self.branch_name = branch_name


class GitOpsMergeConflictError(GitOpsError):
    """Raised when a three-way merge encounters conflicting changes.

    Two branches have modified the same configuration key in incompatible
    ways. In real git, you would open your editor, stare at conflict markers,
    question your career choices, and eventually pick one side. Here, we
    just raise an exception, which is arguably more honest.
    """

    def __init__(self, source_branch: str, target_branch: str, conflicts: list[str]) -> None:
        conflicts_str = ", ".join(conflicts[:5])
        suffix = f" (and {len(conflicts) - 5} more)" if len(conflicts) > 5 else ""
        super().__init__(
            f"Merge conflict between '{source_branch}' and '{target_branch}': "
            f"conflicting keys: {conflicts_str}{suffix}. "
            f"Automatic resolution has failed. Manual intervention required, "
            f"but since this is an in-memory simulator, that means restarting.",
            error_code="EFP-G002",
            context={
                "source_branch": source_branch,
                "target_branch": target_branch,
                "conflicts": conflicts,
            },
        )
        self.conflicts = conflicts


class GitOpsPolicyViolationError(GitOpsError):
    """Raised when a configuration change violates a policy rule.

    The PolicyEngine has examined your proposed configuration change and
    found it wanting. Perhaps you tried to set the range end to a negative
    number, or perhaps you attempted to disable both Fizz and Buzz rules
    simultaneously, which would reduce the Enterprise FizzBuzz Platform
    to merely an Enterprise Platform — and that is a policy violation of
    the highest order.
    """

    def __init__(self, rule_name: str, reason: str) -> None:
        super().__init__(
            f"Policy violation: rule '{rule_name}' rejected the change: {reason}. "
            f"The change has been blocked by the policy engine, which exists "
            f"to prevent you from shooting yourself in the foot with YAML.",
            error_code="EFP-G003",
            context={"rule_name": rule_name, "reason": reason},
        )
        self.rule_name = rule_name


class GitOpsProposalRejectedError(GitOpsError):
    """Raised when a change proposal fails to pass the approval pipeline.

    Your proposed configuration change has been reviewed by the automated
    approval pipeline (which, in single-operator mode, means you reviewed
    your own work and still found it lacking). The proposal was rejected
    at one of the five gates: validation, policy, dry-run, approval, or
    apply. Better luck next time.
    """

    def __init__(self, proposal_id: str, gate: str, reason: str) -> None:
        super().__init__(
            f"Change proposal '{proposal_id}' rejected at gate '{gate}': {reason}. "
            f"The pipeline has spoken. Your change is not worthy.",
            error_code="EFP-G004",
            context={"proposal_id": proposal_id, "gate": gate, "reason": reason},
        )
        self.proposal_id = proposal_id
        self.gate = gate


class GitOpsDriftDetectedError(GitOpsError):
    """Raised when configuration drift is detected between committed and running state.

    The running configuration has diverged from the committed configuration,
    which means someone (or something) has been modifying the config at
    runtime without going through the proper GitOps pipeline. This is the
    configuration management equivalent of finding out someone has been
    editing production directly via SSH — except here, it's a dict in RAM.
    """

    def __init__(self, drift_count: int, drifted_keys: list[str]) -> None:
        keys_str = ", ".join(drifted_keys[:5])
        suffix = f" (and {len(drifted_keys) - 5} more)" if len(drifted_keys) > 5 else ""
        super().__init__(
            f"Configuration drift detected: {drift_count} key(s) have diverged "
            f"from committed state: {keys_str}{suffix}. "
            f"Reconciliation is recommended before the drift becomes sentient.",
            error_code="EFP-G005",
            context={"drift_count": drift_count, "drifted_keys": drifted_keys},
        )
        self.drift_count = drift_count
        self.drifted_keys = drifted_keys


class GitOpsCommitNotFoundError(GitOpsError):
    """Raised when a referenced commit SHA does not exist in the repository.

    You asked for a commit that the repository has no record of. Perhaps
    it was garbage collected, perhaps it existed in a parallel universe
    where configuration management is simpler, or perhaps you just
    mistyped the SHA-256 hash. All 64 characters must match exactly.
    """

    def __init__(self, commit_sha: str) -> None:
        short_sha = commit_sha[:12] if len(commit_sha) > 12 else commit_sha
        super().__init__(
            f"Commit '{short_sha}...' not found in the configuration repository. "
            f"The commit may have been lost to the sands of in-memory time.",
            error_code="EFP-G006",
            context={"commit_sha": commit_sha},
        )


# ============================================================
# Formal Verification & Proof System Exceptions
# ============================================================

class FormalVerificationError(FizzBuzzError):
    """Base exception for the Formal Verification & Proof System.

    When your FizzBuzz platform requires Gentzen-style natural deduction
    proofs to verify that modulo arithmetic still works, you have achieved
    a level of engineering rigor that would make Bertrand Russell weep
    with either pride or despair. These exceptions cover everything from
    failed proof obligations to unsound Hoare triples to the devastating
    discovery that n % 3 might not always equal what you think it does.
    (Spoiler: it does. But we check anyway.)
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-FV00"),
            context=kwargs.pop("context", {}),
        )


class ProofObligationFailedError(FormalVerificationError):
    """Raised when a proof obligation cannot be discharged.

    The verification engine attempted to prove a property of the
    FizzBuzz evaluation function and failed. This means either the
    property does not hold (unlikely for modulo arithmetic), the
    prover is buggy (always possible), or mathematics itself has
    a regression. We recommend filing a ticket with Euclid.
    """

    def __init__(self, property_name: str, counterexample: Optional[Any] = None) -> None:
        ce_msg = f" Counterexample: {counterexample}" if counterexample is not None else ""
        super().__init__(
            f"Proof obligation for property '{property_name}' could not be "
            f"discharged.{ce_msg} The theorem remains unproven, which is "
            f"the formal methods equivalent of a P0 incident.",
            error_code="EFP-FV01",
            context={"property_name": property_name, "counterexample": counterexample},
        )
        self.property_name = property_name
        self.counterexample = counterexample


class HoareTripleViolationError(FormalVerificationError):
    """Raised when a Hoare triple {P} S {Q} fails verification.

    The precondition held, the statement executed, but the postcondition
    was violated. In the context of FizzBuzz, this means that given a
    positive integer, the evaluate() function produced a result that is
    not in the set of valid outputs. This is the formal verification
    equivalent of discovering that 15 % 3 is suddenly 7.
    """

    def __init__(self, number: int, expected_outputs: str, actual_output: str) -> None:
        super().__init__(
            f"Hoare triple violation at n={number}: expected output in "
            f"{{{expected_outputs}}}, got '{actual_output}'. "
            f"The specification and implementation have irreconcilable differences.",
            error_code="EFP-FV02",
            context={
                "number": number,
                "expected_outputs": expected_outputs,
                "actual_output": actual_output,
            },
        )
        self.number = number


class InductionBaseFailedError(FormalVerificationError):
    """Raised when the base case of an induction proof fails.

    The very first step of the proof — verifying P(1) — has failed.
    If you cannot even prove that your FizzBuzz function works for
    the number 1, the inductive step is moot and the universal
    quantifier remains tragically uninstantiated.
    """

    def __init__(self, base_value: int, reason: str) -> None:
        super().__init__(
            f"Induction base case P({base_value}) failed: {reason}. "
            f"The proof collapses at its foundation, like a house of "
            f"cards built on unverified modulo arithmetic.",
            error_code="EFP-FV03",
            context={"base_value": base_value, "reason": reason},
        )
        self.base_value = base_value


class InductionStepFailedError(FormalVerificationError):
    """Raised when the inductive step of a proof fails.

    We assumed P(n) and tried to prove P(n+1), but the proof
    did not go through. The inductive hypothesis was insufficient,
    the case analysis was incomplete, or the FizzBuzz function has
    a subtle bug that only manifests under the scrutiny of formal
    methods. (Just kidding. It's modulo arithmetic. It works.)
    """

    def __init__(self, step_case: str, reason: str) -> None:
        super().__init__(
            f"Induction step failed for case '{step_case}': {reason}. "
            f"The proof cannot proceed beyond the base case, leaving an "
            f"infinite number of integers formally unverified.",
            error_code="EFP-FV04",
            context={"step_case": step_case, "reason": reason},
        )
        self.step_case = step_case


class PropertyVerificationTimeoutError(FormalVerificationError):
    """Raised when property verification exceeds the allotted time.

    If verifying that n % 3 == 0 implies the output contains "Fizz"
    takes longer than the configured timeout, something has gone
    profoundly wrong. Perhaps the integers have become uncountably
    infinite, or perhaps someone passed float('inf') as the range end.
    Either way, the verification engine has given up.
    """

    def __init__(self, property_name: str, timeout_ms: float) -> None:
        super().__init__(
            f"Property verification for '{property_name}' timed out after "
            f"{timeout_ms:.0f}ms. The proof search space is too large, or "
            f"the theorem is unprovable, or the CPU is philosophically opposed "
            f"to formal methods.",
            error_code="EFP-FV05",
            context={"property_name": property_name, "timeout_ms": timeout_ms},
        )


# ============================================================
# FizzBuzz-as-a-Service (FBaaS) Exception Hierarchy
#
# Because offering modulo arithmetic as a SaaS product requires
# its own exception taxonomy. Every failed quota check, every
# suspended tenant, every unpaid invoice — all of these deserve
# enterprise-grade error handling with unique error codes.
# ============================================================


class FBaaSError(FizzBuzzError):
    """Base exception for all FizzBuzz-as-a-Service errors.

    When your SaaS platform for modulo arithmetic encounters
    a billing dispute, tenant suspension, or quota exhaustion,
    this is the exception hierarchy that catches it. Because
    even fictional cloud services need real error handling.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FB00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class TenantNotFoundError(FBaaSError):
    """Raised when a tenant cannot be located in the in-memory registry.

    The tenant either never existed, was garbage collected by an
    overzealous Python runtime, or simply failed to pay their invoice
    and was purged from the system with extreme prejudice.
    """

    def __init__(self, tenant_id: str) -> None:
        super().__init__(
            f"Tenant '{tenant_id}' not found. The tenant may have been "
            f"evicted for non-payment, or may never have existed. "
            f"Either way, no FizzBuzz for you.",
            error_code="EFP-FB01",
            context={"tenant_id": tenant_id},
        )
        self.tenant_id = tenant_id


class FBaaSQuotaExhaustedError(FBaaSError):
    """Raised when a tenant has exhausted their daily evaluation quota.

    Free tier tenants get 10 evaluations per day, which is barely
    enough to FizzBuzz through a single meeting agenda. Pro tenants
    get 1,000. Enterprise tenants get unlimited, because apparently
    some people need industrial-strength modulo arithmetic.

    Not to be confused with QuotaExhaustedError from the Rate Limiting
    subsystem, which is about per-minute API quotas. This one is about
    per-day tenant quotas. Because one kind of quota was not enough.
    """

    def __init__(self, tenant_id: str, tier: str, limit: int, used: int) -> None:
        super().__init__(
            f"Tenant '{tenant_id}' ({tier}) has exhausted their daily quota: "
            f"{used}/{limit} evaluations used. Please upgrade your subscription "
            f"or wait until tomorrow. The modulo operator will still be here.",
            error_code="EFP-FB02",
            context={"tenant_id": tenant_id, "tier": tier, "limit": limit, "used": used},
        )


class TenantSuspendedError(FBaaSError):
    """Raised when a suspended tenant attempts to use the service.

    Suspended tenants have been locked out of the FizzBuzz-as-a-Service
    platform, typically for non-payment or Terms of Service violations.
    What kind of TOS violation can one commit with FizzBuzz? You'd be
    surprised. Some tenants tried to use it for BuzzFizz.
    """

    def __init__(self, tenant_id: str, reason: str) -> None:
        super().__init__(
            f"Tenant '{tenant_id}' is SUSPENDED: {reason}. "
            f"Contact billing@enterprise-fizzbuzz.example.com to resolve. "
            f"Your FizzBuzz privileges have been revoked.",
            error_code="EFP-FB03",
            context={"tenant_id": tenant_id, "reason": reason},
        )


class FeatureNotAvailableError(FBaaSError):
    """Raised when a tenant's subscription tier doesn't include a feature.

    Free tier tenants don't get ML evaluation, chaos engineering, or
    premium formatting. They get standard FizzBuzz with a watermark.
    You want the good stuff? Open your wallet.
    """

    def __init__(self, tenant_id: str, tier: str, feature: str) -> None:
        super().__init__(
            f"Feature '{feature}' is not available on the {tier} tier. "
            f"Tenant '{tenant_id}' must upgrade to access this feature. "
            f"The modulo operator is free, but the fancy modulo operator costs extra.",
            error_code="EFP-FB04",
            context={"tenant_id": tenant_id, "tier": tier, "feature": feature},
        )


class BillingError(FBaaSError):
    """Raised when the simulated billing engine encounters an error.

    The FizzStripeClient has encountered an issue with the simulated
    payment processing. No actual money is involved, but the error
    messages are indistinguishable from real billing failures, because
    that's the enterprise way.
    """

    def __init__(self, tenant_id: str, reason: str) -> None:
        super().__init__(
            f"Billing error for tenant '{tenant_id}': {reason}. "
            f"The simulated payment processor is experiencing simulated difficulties.",
            error_code="EFP-FB05",
            context={"tenant_id": tenant_id, "reason": reason},
        )


class InvalidAPIKeyError(FBaaSError):
    """Raised when an API key is rejected during FBaaS authentication.

    The API key provided is either invalid, expired, or belongs to
    a tenant who has been suspended. In any case, the FizzBuzz
    evaluation will not proceed. Security is paramount, even when
    the protected resource is modulo arithmetic.
    """

    def __init__(self, api_key: str) -> None:
        masked = api_key[:8] + "..." if len(api_key) > 8 else "***"
        super().__init__(
            f"Invalid API key: {masked}. The key was rejected by the "
            f"FBaaS authentication subsystem. Please check your credentials "
            f"or generate a new key via the onboarding wizard.",
            error_code="EFP-FB06",
            context={"api_key_prefix": api_key[:8] if len(api_key) >= 8 else ""},
        )


# ============================================================
# Time-Travel Debugger Exceptions
# ============================================================
# Because debugging FizzBuzz results is hard enough without
# having to move forwards through time like some kind of
# temporally-challenged mortal. These exceptions cover every
# possible failure mode of travelling through the spacetime
# continuum of modulo arithmetic evaluations.
# ============================================================


class TimeTravelError(FizzBuzzError):
    """Base exception for all Time-Travel Debugger errors.

    When your ability to traverse the temporal dimension of
    FizzBuzz evaluations encounters an obstacle, this hierarchy
    provides the appropriately granular error taxonomy that
    enterprise-grade time travel demands.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-TT00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class TimelineEmptyError(TimeTravelError):
    """Raised when navigating a timeline that contains no snapshots.

    You cannot travel through time if time has not yet begun.
    The timeline is as empty as a FizzBuzz evaluation that was
    cancelled before the first number was processed. Please
    generate some history before attempting to revisit it.
    """

    def __init__(self) -> None:
        super().__init__(
            "Cannot navigate an empty timeline. No snapshots have been "
            "captured yet. Please run at least one FizzBuzz evaluation "
            "before attempting to debug it retroactively.",
            error_code="EFP-TT01",
        )


class SnapshotIntegrityError(TimeTravelError):
    """Raised when a snapshot fails its SHA-256 integrity check.

    The snapshot's cryptographic hash does not match its contents,
    which means either the snapshot was tampered with, a cosmic ray
    flipped a bit, or someone has been meddling with the timeline.
    In any case, the integrity of FizzBuzz history has been compromised,
    and the audit implications are staggering.
    """

    def __init__(self, sequence: int, expected_hash: str, actual_hash: str) -> None:
        super().__init__(
            f"Snapshot at sequence {sequence} failed integrity check. "
            f"Expected hash: {expected_hash[:16]}..., got: {actual_hash[:16]}... "
            f"The timeline may have been tampered with.",
            error_code="EFP-TT02",
            context={
                "sequence": sequence,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            },
        )


class BreakpointSyntaxError(TimeTravelError):
    """Raised when a conditional breakpoint expression fails to compile.

    The breakpoint condition you provided is not valid Python syntax.
    While we applaud your creativity in expressing temporal debugging
    conditions, the Python parser is less forgiving than we are.
    Supported variables: number, result, latency.
    """

    def __init__(self, expression: str, reason: str) -> None:
        super().__init__(
            f"Invalid breakpoint expression: {expression!r}. "
            f"Compilation failed: {reason}. "
            f"Supported variables: number, result, latency.",
            error_code="EFP-TT03",
            context={"expression": expression, "reason": reason},
        )


class TimelineNavigationError(TimeTravelError):
    """Raised when a timeline navigation operation cannot be completed.

    You attempted to navigate to a point in the timeline that does
    not exist, is out of bounds, or violates the laws of temporal
    mechanics as they apply to FizzBuzz evaluation. The requested
    sequence number is beyond the known boundaries of modulo history.
    """

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            f"Timeline navigation failed during '{operation}': {reason}. "
            f"The temporal coordinates you requested are outside the "
            f"known boundaries of the FizzBuzz evaluation timeline.",
            error_code="EFP-TT04",
            context={"operation": operation, "reason": reason},
        )


# ============================================================
# Custom Bytecode VM Exceptions (EFP-VM00 through EFP-VM04)
# ============================================================
# Because running FizzBuzz directly in Python was too efficient,
# and what this platform truly needed was its own bytecode virtual
# machine with a custom instruction set, registers, and a fetch-
# decode-execute loop. The JVM took 4 years to develop; ours took
# an afternoon, which says something about either our efficiency
# or our standards.
# ============================================================


class BytecodeVMError(FizzBuzzError):
    """Base exception for all Custom Bytecode VM errors.

    When the FizzBuzz Bytecode Virtual Machine encounters a condition
    that prevents it from continuing execution of compiled bytecode
    through the virtual machine's instruction pipeline,
    this exception (or one of its children) will be raised.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-VM00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class BytecodeCompilationError(BytecodeVMError):
    """Raised when the FBVM compiler fails to translate rules to bytecode.

    The compiler examined your rule definitions and decided that they
    cannot be expressed in the FBVM instruction set. This is
    remarkable, given that the instruction set was specifically designed
    for FizzBuzz and nothing else. Somehow, you have managed to confuse
    a compiler that only needs to emit MOD and CMP_ZERO instructions.
    """

    def __init__(self, rule_name: str, reason: str) -> None:
        super().__init__(
            f"Compilation failed for rule '{rule_name}': {reason}. "
            f"The FBVM compiler cannot translate this rule into bytecode. "
            f"Consider simplifying your divisibility check (it's literally one modulo).",
            error_code="EFP-VM01",
            context={"rule_name": rule_name, "reason": reason},
        )


class BytecodeExecutionError(BytecodeVMError):
    """Raised when the FBVM encounters a runtime error during execution.

    The virtual machine was happily executing bytecode when something
    went catastrophically wrong. Given that the bytecode only performs
    modulo arithmetic and string concatenation, this is an achievement
    in runtime failure that most VMs can only aspire to.
    """

    def __init__(self, pc: int, opcode: str, reason: str) -> None:
        super().__init__(
            f"VM execution error at PC={pc}, opcode={opcode}: {reason}. "
            f"The FBVM has encountered an unrecoverable state. "
            f"Please file a bug report with your .fzbc file attached.",
            error_code="EFP-VM02",
            context={"program_counter": pc, "opcode": opcode, "reason": reason},
        )


class BytecodeCycleLimitError(BytecodeVMError):
    """Raised when the FBVM exceeds its cycle limit.

    The virtual machine has executed more instructions than the
    configured cycle limit allows. For a program that computes
    n % d == 0 for two divisors, exceeding 10,000 cycles suggests
    either an infinite loop or a profoundly inefficient compilation
    strategy. Both are concerning.
    """

    def __init__(self, cycle_limit: int, pc: int) -> None:
        super().__init__(
            f"VM cycle limit exceeded: {cycle_limit} cycles at PC={pc}. "
            f"The bytecode program appears to be stuck in an infinite loop, "
            f"which is impressive for a program that only computes modulo.",
            error_code="EFP-VM03",
            context={"cycle_limit": cycle_limit, "program_counter": pc},
        )


class BytecodeSerializationError(BytecodeVMError):
    """Raised when .fzbc bytecode serialization or deserialization fails.

    The proprietary .fzbc file format — complete with magic header
    'FZBC' and base64 encoding — has encountered a corruption or
    format mismatch. Perhaps someone edited the bytecode by hand,
    which is the VM equivalent of performing surgery with a spoon.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Bytecode serialization error: {reason}. "
            f"The .fzbc file may be corrupted, truncated, or from an "
            f"incompatible version of the FBVM. Try recompiling from source rules.",
            error_code="EFP-VM04",
            context={"reason": reason},
        )


# ============================================================
# Query Optimizer Exceptions
# ============================================================
# Because even the query planner for modulo arithmetic
# needs a full taxonomy of failure modes. PostgreSQL has
# hundreds of error codes; we have five. Restraint.
# ============================================================


class QueryOptimizerError(FizzBuzzError):
    """Base exception for all FizzBuzz Query Optimizer errors.

    When the query planner for a modulo operation encounters an
    unrecoverable error, it means the optimizer has become less
    efficient than the operation it was trying to optimize. This
    is the database equivalent of hiring a consultant who costs
    more than the problem they were brought in to solve.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-QO00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class PlanGenerationError(QueryOptimizerError):
    """Raised when the plan enumerator fails to generate any valid plans.

    The enumerator exhaustively searched the plan space — all three
    of the possible strategies — and could not produce a single
    executable plan. This is the query optimizer equivalent of a
    chef refusing to cook because none of the recipes are efficient
    enough for boiling water.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Plan generation failed: {reason}. "
            f"The optimizer could not produce a viable execution plan "
            f"for what is fundamentally a modulo operation.",
            error_code="EFP-QO01",
            context={"reason": reason},
        )


class CostEstimationError(QueryOptimizerError):
    """Raised when the cost model produces an invalid or infinite cost.

    The cost model attempted to estimate how expensive it would be
    to compute n %% d == 0 and arrived at infinity, NaN, or a negative
    number. This suggests either a bug in the cost model or a number
    so profoundly difficult to divide that mathematics itself has
    given up.
    """

    def __init__(self, node_type: str, cost: float) -> None:
        super().__init__(
            f"Cost estimation error for node type '{node_type}': "
            f"computed cost {cost} is invalid. The cost model has lost "
            f"confidence in basic arithmetic.",
            error_code="EFP-QO02",
            context={"node_type": node_type, "cost": cost},
        )


class PlanCacheOverflowError(QueryOptimizerError):
    """Raised when the plan cache exceeds its configured maximum size.

    The cache has accumulated more execution plans than the configured
    limit allows. For a system that evaluates modulo operations, this
    means someone has been generating an unreasonable number of unique
    divisibility profiles, which is technically impressive but
    operationally concerning.
    """

    def __init__(self, max_size: int, current_size: int) -> None:
        super().__init__(
            f"Plan cache overflow: {current_size} entries exceed maximum "
            f"of {max_size}. The optimizer is hoarding plans like a "
            f"squirrel hoards acorns — except these acorns are execution "
            f"strategies for modulo arithmetic.",
            error_code="EFP-QO03",
            context={"max_size": max_size, "current_size": current_size},
        )


class InvalidHintError(QueryOptimizerError):
    """Raised when an optimizer hint is contradictory or unrecognized.

    The hints provided to the optimizer are mutually exclusive,
    nonsensical, or simply not in the vocabulary of a FizzBuzz
    query planner. Asking for both FORCE_ML and NO_ML is the
    optimization equivalent of asking for a vegetarian steak.
    """

    def __init__(self, hint: str, reason: str) -> None:
        super().__init__(
            f"Invalid optimizer hint '{hint}': {reason}. "
            f"Please consult the FizzBuzz Query Optimizer Reference Manual "
            f"(which does not exist) for valid hint combinations.",
            error_code="EFP-QO04",
            context={"hint": hint, "reason": reason},
        )


# ============================================================
# Distributed Paxos Consensus Exceptions
# ============================================================
# Because even an in-memory, single-process, simulated
# distributed consensus protocol for modulo arithmetic needs
# a full taxonomy of failure modes. Leslie Lamport would
# either be honoured or horrified.
# ============================================================


class PaxosError(FizzBuzzError):
    """Base exception for all Distributed Paxos Consensus errors.

    When the simulated distributed consensus protocol for FizzBuzz
    evaluation encounters an error, it means democracy itself has
    failed — at least within the confines of a single Python process
    pretending to be a five-node cluster.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-PX00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class QuorumNotReachedError(PaxosError):
    """Raised when a Paxos round fails to achieve quorum.

    A majority of nodes could not agree on the FizzBuzz evaluation
    result. In a real distributed system, this means the cluster
    is partitioned or nodes are unresponsive. Here, it means your
    simulated network is having simulated problems. The distinction
    is purely academic, as is this entire consensus protocol.
    """

    def __init__(self, required: int, received: int, decree_number: int) -> None:
        super().__init__(
            f"Quorum not reached for decree #{decree_number}: "
            f"needed {required} votes, received {received}. "
            f"Democracy has failed for this particular modulo operation.",
            error_code="EFP-PX01",
            context={
                "required": required,
                "received": received,
                "decree_number": decree_number,
            },
        )


class BallotRejectedError(PaxosError):
    """Raised when a proposer's ballot number is rejected by an acceptor.

    The acceptor has already promised to honour a higher ballot number,
    making your ballot obsolete. This is the distributed consensus
    equivalent of arriving at a polling station after it has closed —
    your vote no longer counts, and the election has moved on without
    you. Try a higher ballot number next time.
    """

    def __init__(self, proposed: int, promised: int, node_id: str) -> None:
        super().__init__(
            f"Ballot #{proposed} rejected by node '{node_id}': "
            f"already promised to honour ballot #{promised}. "
            f"Your proposal arrived too late. The consensus train has left the station.",
            error_code="EFP-PX02",
            context={
                "proposed_ballot": proposed,
                "promised_ballot": promised,
                "node_id": node_id,
            },
        )


class QuantumError(FizzBuzzError):
    """Base exception for all Quantum Computing Simulator errors.

    When the fabric of simulated quantum reality collapses, this exception
    hierarchy ensures that the failure is communicated with the same
    gravitas that a real quantum decoherence event deserves. The fact
    that our "qubits" are Python floats in a list does not diminish
    the seriousness of these errors in the slightest.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-QC00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class QuantumDecoherenceError(QuantumError):
    """Raised when a quantum state vector loses normalization.

    In a real quantum computer, decoherence occurs when qubits interact
    with their environment, causing the delicate superposition to collapse
    into classical noise. In our simulator, it means the sum of squared
    amplitudes drifted away from 1.0, probably due to floating-point
    arithmetic — the thermal noise of the software world.
    """

    def __init__(self, norm: float, expected: float = 1.0) -> None:
        super().__init__(
            f"Quantum decoherence detected: state vector norm is {norm:.6f}, "
            f"expected {expected:.6f}. The simulated qubits have lost contact "
            f"with simulated reality. Consider simulated error correction.",
            error_code="EFP-QC01",
            context={"norm": norm, "expected": expected},
        )


class QuantumCircuitError(QuantumError):
    """Raised when a quantum circuit is malformed or cannot be executed.

    The circuit attempted to apply a gate to a qubit that does not exist,
    or the gate matrix dimensions do not match the target qubits. This is
    the quantum computing equivalent of an IndexError, but with more
    existential implications.
    """

    def __init__(self, gate_name: str, target_qubits: Any, num_qubits: int) -> None:
        super().__init__(
            f"Cannot apply gate '{gate_name}' to qubits {target_qubits} "
            f"in a {num_qubits}-qubit register. The quantum circuit has "
            f"attempted to manipulate a qubit that exists only in the "
            f"imagination of an overly ambitious gate schedule.",
            error_code="EFP-QC02",
            context={
                "gate_name": gate_name,
                "target_qubits": str(target_qubits),
                "num_qubits": num_qubits,
            },
        )


class QuantumMeasurementError(QuantumError):
    """Raised when a quantum measurement yields an impossible outcome.

    The Born rule assigns probabilities to measurement outcomes based on
    the squared amplitudes of the state vector. When the measurement
    produces a result with zero probability, either the laws of quantum
    mechanics are wrong, or our random number generator is broken.
    Occam's razor suggests the latter.
    """

    def __init__(self, outcome: int, probability: float) -> None:
        super().__init__(
            f"Measurement yielded outcome |{outcome}> with probability "
            f"{probability:.6e}. This outcome should not have occurred, "
            f"yet here we are, staring into the void of probabilistic "
            f"impossibility. The simulation has become self-aware.",
            error_code="EFP-QC03",
            context={"outcome": outcome, "probability": probability},
        )


class QuantumAdvantageMirage(QuantumError):
    """Raised when the quantum simulator's performance advantage is requested.

    This exception exists to formally acknowledge that our quantum
    simulator provides a negative speedup over classical computation.
    The "advantage" is measured in negative scientific notation, and
    any attempt to claim otherwise constitutes academic fraud of the
    highest order.
    """

    def __init__(self, classical_ns: float, quantum_ns: float) -> None:
        ratio = quantum_ns / max(classical_ns, 1)
        super().__init__(
            f"Quantum Advantage Ratio: {-ratio:.2e}x (negative means slower). "
            f"Classical: {classical_ns:.0f}ns, Quantum: {quantum_ns:.0f}ns. "
            f"The quantum simulator is approximately {ratio:.0f}x slower than "
            f"a single modulo operation. This is expected. This is fine.",
            error_code="EFP-QC04",
            context={
                "classical_ns": classical_ns,
                "quantum_ns": quantum_ns,
                "advantage_ratio": -ratio,
            },
        )


class ByzantineFaultDetectedError(PaxosError):
    """Raised when a Byzantine fault is detected in the consensus cluster.

    One or more nodes are returning results inconsistent with their
    peers. In the Byzantine Generals Problem, this represents a
    traitorous general sending conflicting messages. In our FizzBuzz
    cluster, this represents a node that has decided 15 % 3 != 0,
    which is the modulo arithmetic equivalent of treason.
    """

    def __init__(self, node_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Byzantine fault detected on node '{node_id}': "
            f"expected '{expected}', got '{actual}'. "
            f"This node is lying about its FizzBuzz evaluation. "
            f"Leslie Lamport warned us about this.",
            error_code="EFP-PX03",
            context={
                "node_id": node_id,
                "expected": expected,
                "actual": actual,
            },
        )


class NetworkPartitionError(PaxosError):
    """Raised when a network partition prevents message delivery.

    The simulated network has been partitioned, and messages cannot
    traverse the divide. In a real distributed system, this is caused
    by switch failures, datacenter outages, or angry sysadmins pulling
    cables. Here, it is caused by a boolean flag in a Python dict.
    The emotional impact is identical.
    """

    def __init__(self, source: str, destination: str) -> None:
        super().__init__(
            f"Network partition: message from '{source}' to '{destination}' "
            f"was dropped. The simulated cable has been simulated-ly unplugged.",
            error_code="EFP-PX04",
            context={"source": source, "destination": destination},
        )


class ConsensusTimeoutError(PaxosError):
    """Raised when the Paxos protocol fails to reach consensus in time.

    The cluster spent too long deliberating the correct FizzBuzz
    result and timed out. In distributed systems, this triggers a
    new round with a higher ballot number. In FizzBuzz, it triggers
    existential questions about why we need consensus for modulo
    arithmetic in the first place.
    """

    def __init__(self, decree_number: int, elapsed_ms: float) -> None:
        super().__init__(
            f"Consensus timeout for decree #{decree_number} after "
            f"{elapsed_ms:.2f}ms. The cluster could not agree on a "
            f"FizzBuzz result within the allotted time. Consider "
            f"reducing the number of Byzantine traitors in your cluster.",
            error_code="EFP-PX05",
            context={"decree_number": decree_number, "elapsed_ms": elapsed_ms},
        )


# ============================================================
# Cross-Compiler Exception Hierarchy
# ============================================================
# Because transpiling FizzBuzz rules into C, Rust, and WebAssembly
# is a perfectly reasonable thing to do with your afternoon, the
# cross-compiler subsystem requires its own family of exceptions
# to handle the myriad ways that code generation can go wrong
# when all you really needed was a modulo operator.
# ============================================================


class CrossCompilerError(FizzBuzzError):
    """Base exception for all FizzBuzz Cross-Compiler errors.

    Raised when the cross-compilation pipeline encounters a failure
    so fundamental that it questions whether transpiling divisibility
    checks into systems languages was ever a good idea. Spoiler: it wasn't,
    but enterprise architecture committees rarely consult common sense.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CC00"),
            context=kwargs.pop("context", {}),
        )


class IRGenerationError(CrossCompilerError):
    """Raised when the Intermediate Representation builder fails.

    The IR builder attempted to lower FizzBuzz rules into basic blocks
    and instructions, but something went wrong — probably because the
    rules were too simple. Modern compiler infrastructure was not
    designed for programs this trivial, and the IR builder is offended.
    """

    def __init__(self, rule_name: str, reason: str) -> None:
        super().__init__(
            f"IR generation failed for rule '{rule_name}': {reason}. "
            f"Consider adding more rules to justify the compiler infrastructure.",
            error_code="EFP-CC01",
            context={"rule_name": rule_name},
        )


class CodeGenerationError(CrossCompilerError):
    """Raised when a target code generator fails to emit valid source code.

    The code generator tried its best to produce syntactically valid
    output in the target language, but even the most sophisticated
    string concatenation engine has its limits. The generated code
    may contain syntax errors, undefined behavior, or — worst of all —
    correct FizzBuzz logic.
    """

    def __init__(self, target_language: str, reason: str) -> None:
        super().__init__(
            f"Code generation for '{target_language}' failed: {reason}. "
            f"The target language may not be ready for enterprise FizzBuzz.",
            error_code="EFP-CC02",
            context={"target_language": target_language},
        )


class RoundTripVerificationError(CrossCompilerError):
    """Raised when generated code produces results that disagree with Python.

    The round-trip verifier compared the generated code's output against
    the canonical Python reference implementation, and they disagree.
    This is the compiler equivalent of two calculators giving different
    answers for 15 % 3, which should be impossible but here we are.
    """

    def __init__(self, target_language: str, number: int, expected: str, got: str) -> None:
        super().__init__(
            f"Round-trip verification failed for '{target_language}' at n={number}: "
            f"expected '{expected}', got '{got}'. The laws of arithmetic may vary "
            f"by programming language.",
            error_code="EFP-CC03",
            context={
                "target_language": target_language,
                "number": number,
                "expected": expected,
                "got": got,
            },
        )


class UnsupportedTargetError(CrossCompilerError):
    """Raised when an unsupported compilation target is requested.

    The cross-compiler supports C, Rust, and WebAssembly Text. Requesting
    compilation to COBOL, Brainfuck, or interpretive dance is not yet
    supported, though all three are on the roadmap for Q4.
    """

    def __init__(self, target: str) -> None:
        supported = ["c", "rust", "wat"]
        super().__init__(
            f"Unsupported compilation target '{target}'. "
            f"Supported targets: {supported}. "
            f"COBOL backend is planned for Q4 2027.",
            error_code="EFP-CC04",
            context={"target": target, "supported": supported},
        )


# ============================================================
# Federated Learning Exceptions
# ============================================================
# Because training a single neural network to check if n % 3 == 0
# was insufficiently distributed. Now we need FIVE neural networks,
# each trained on a carefully curated shard of integers, to
# collaboratively learn divisibility patterns without sharing
# raw training data. Privacy-preserving distributed ML ensures
# compliance with data governance policies across nodes.
# ============================================================


class FederatedLearningError(FizzBuzzError):
    """Base exception for all Federated Learning subsystem errors.

    When your distributed modulo-learning consortium encounters a
    failure, this is the root of the exception hierarchy that
    documents exactly how and why five neural networks couldn't
    agree on what 15 % 3 equals.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FL00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FederatedClientTrainingError(FederatedLearningError):
    """Raised when a federated client fails to complete local training.

    One of the clients in the federation has failed to learn its portion
    of the modulo problem. This is the distributed ML equivalent of one
    student in a study group refusing to do their homework, except the
    homework is integer divisibility.
    """

    def __init__(self, client_id: str, reason: str) -> None:
        super().__init__(
            f"Federated client '{client_id}' failed local training: {reason}. "
            f"The client's neural network has refused to learn modulo arithmetic.",
            error_code="EFP-FL01",
            context={"client_id": client_id, "reason": reason},
        )


class FederatedAggregationError(FederatedLearningError):
    """Raised when weight aggregation fails during a federation round.

    The server attempted to compute a weighted average of model deltas
    from multiple clients, and somehow this trivial arithmetic operation
    failed. The irony of a system that can't average weights while trying
    to learn averages is not lost on us.
    """

    def __init__(self, round_number: int, reason: str) -> None:
        super().__init__(
            f"Federation round {round_number} aggregation failed: {reason}. "
            f"The weighted average of weight deltas has itself become unweighted.",
            error_code="EFP-FL02",
            context={"round_number": round_number, "reason": reason},
        )


class FederatedPrivacyBudgetExhaustedError(FederatedLearningError):
    """Raised when the differential privacy epsilon budget is exhausted.

    The federation has consumed its entire privacy budget, meaning no
    more noise can be calibrated without violating the mathematical
    guarantees of differential privacy. The model must stop learning,
    because the privacy of which integers are divisible by 3 must be
    protected at all costs.
    """

    def __init__(self, epsilon_spent: float, epsilon_budget: float) -> None:
        super().__init__(
            f"Differential privacy budget exhausted: spent {epsilon_spent:.4f} "
            f"of {epsilon_budget:.4f} epsilon. No further training rounds are "
            f"permitted without compromising the mathematical privacy guarantees "
            f"of your modulo arithmetic dataset.",
            error_code="EFP-FL03",
            context={
                "epsilon_spent": epsilon_spent,
                "epsilon_budget": epsilon_budget,
            },
        )


class FederatedConvergenceError(FederatedLearningError):
    """Raised when the federated model fails to converge.

    Despite the combined computational might of five neural networks
    training collaboratively across multiple rounds, the federated
    model has failed to learn that some numbers are divisible by 3.
    This is either a hyperparameter issue or evidence that distributed
    learning is not the optimal approach to modulo arithmetic.
    """

    def __init__(self, rounds_completed: int, final_accuracy: float) -> None:
        super().__init__(
            f"Federated model failed to converge after {rounds_completed} rounds. "
            f"Final global accuracy: {final_accuracy:.1f}%. Consider using the "
            f"'%' operator instead.",
            error_code="EFP-FL04",
            context={
                "rounds_completed": rounds_completed,
                "final_accuracy": final_accuracy,
            },
        )


class FederatedRoundTimeoutError(FederatedLearningError):
    """Raised when a federation round exceeds the configured timeout.

    A single round of federated averaging has taken longer than
    allowed. Given that the entire computation involves training
    tiny neural networks on whether numbers are divisible by 3 or 5,
    this timeout is either set unreasonably low or something has
    gone cosmically wrong with basic arithmetic.
    """

    def __init__(self, round_number: int, elapsed_ms: float, timeout_ms: float) -> None:
        super().__init__(
            f"Federation round {round_number} timed out after {elapsed_ms:.1f}ms "
            f"(limit: {timeout_ms:.0f}ms). Computing weighted averages of gradients "
            f"for modulo arithmetic has exceeded temporal expectations.",
            error_code="EFP-FL05",
            context={
                "round_number": round_number,
                "elapsed_ms": elapsed_ms,
                "timeout_ms": timeout_ms,
            },
        )


# ────────────────────────────────────────────────────────────────────
# Knowledge Graph & Domain Ontology Exceptions
# ────────────────────────────────────────────────────────────────────


class KnowledgeGraphError(FizzBuzzError):
    """Base exception for all Knowledge Graph & Ontology operations.

    When your RDF triple store encounters an existential crisis,
    or your OWL class hierarchy questions the meaning of inheritance,
    this is the exception that catches their tears.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-KG00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class InvalidTripleError(KnowledgeGraphError):
    """Raised when an RDF triple violates ontological constraints.

    Every triple must have a subject, predicate, and object. Triples
    with None values are the Knowledge Graph equivalent of dividing
    by zero — philosophically uncomfortable and operationally forbidden.
    """

    def __init__(self, subject: Any, predicate: Any, obj: Any) -> None:
        super().__init__(
            f"Invalid RDF triple: ({subject!r}, {predicate!r}, {obj!r}). "
            f"All three components must be non-None strings. "
            f"The Semantic Web has standards, even for FizzBuzz.",
            error_code="EFP-KG01",
            context={"subject": str(subject), "predicate": str(predicate), "object": str(obj)},
        )


class NamespaceResolutionError(KnowledgeGraphError):
    """Raised when a namespace prefix cannot be resolved.

    The platform supports fizz:, rdfs:, owl:, and xsd: namespace
    prefixes. Using an unregistered prefix is a violation of Linked
    Data principles and will not be tolerated.
    """

    def __init__(self, prefix: str) -> None:
        super().__init__(
            f"Unknown namespace prefix '{prefix}:'. Registered prefixes: "
            f"fizz:, rdfs:, owl:, xsd:. Please consult the W3C RDF "
            f"Primer (or just use 'fizz:' for everything, like a pragmatist).",
            error_code="EFP-KG02",
            context={"prefix": prefix},
        )


class FizzSPARQLSyntaxError(KnowledgeGraphError):
    """Raised when a FizzSPARQL query contains a syntax error.

    FizzSPARQL is a strict subset of SPARQL 1.1 that supports exactly
    the features needed to query FizzBuzz ontologies. Any deviation
    from the grammar will be met with this exception and a lecture
    on proper query authorship.
    """

    def __init__(self, query: str, position: int, reason: str) -> None:
        super().__init__(
            f"FizzSPARQL syntax error at position {position}: {reason}. "
            f"Query: {query!r}",
            error_code="EFP-KG03",
            context={"query": query, "position": position},
        )


class InferenceFixpointError(KnowledgeGraphError):
    """Raised when the forward-chaining inference engine fails to reach fixpoint.

    The inference engine applies rules iteratively until no new triples
    are generated. If this limit is exceeded, the knowledge graph has
    entered an infinite loop of self-discovery — a state that is
    philosophically interesting but computationally unacceptable.
    """

    def __init__(self, max_iterations: int, triples_generated: int) -> None:
        super().__init__(
            f"Inference engine failed to reach fixpoint after {max_iterations} "
            f"iterations ({triples_generated} triples generated). The ontology "
            f"may contain circular inference rules, or FizzBuzz classification "
            f"has become undecidable.",
            error_code="EFP-KG04",
            context={"max_iterations": max_iterations, "triples_generated": triples_generated},
        )


class OntologyConsistencyError(KnowledgeGraphError):
    """Raised when the OWL class hierarchy contains a logical inconsistency.

    Multiple inheritance in OWL is expected. Circular inheritance,
    however, is the ontological equivalent of a paradox — a class
    that is its own ancestor has reached a level of self-reference
    that even enterprise architects find uncomfortable.
    """

    def __init__(self, class_uri: str, reason: str) -> None:
        super().__init__(
            f"Ontology consistency violation for class '{class_uri}': {reason}. "
            f"The class hierarchy has become logically incoherent, which is "
            f"impressive for a taxonomy of FizzBuzz classifications.",
            error_code="EFP-KG05",
            context={"class_uri": class_uri},
        )


# ============================================================
# Self-Modifying Code Exceptions
# ============================================================
# Because FizzBuzz rules that rewrite their own evaluation logic
# at runtime is exactly the kind of capability that keeps software
# architects awake at night. These exceptions cover the full
# taxonomy of self-mutation failures: from AST corruption to
# fitness collapse to the existential crisis of code that has
# mutated itself into something it no longer recognizes.
# ============================================================


class SelfModifyingCodeError(FizzBuzzError):
    """Base exception for the Self-Modifying Code subsystem.

    When your FizzBuzz rules gain the ability to inspect and
    rewrite their own evaluation logic at runtime, failure is
    not a matter of if but when. These exceptions capture the
    full horror of code that has decided to improve itself
    without consulting the engineering team. The machine is
    learning, but nobody asked it to learn.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SMC00"),
            context=kwargs.pop("context", {}),
        )


class ASTCorruptionError(SelfModifyingCodeError):
    """Raised when a mutation produces an invalid or corrupt AST.

    The mutable Abstract Syntax Tree — which represents a FizzBuzz
    rule as a tree of divisibility checks, label emissions, and
    conditional branches — has been mutated into a state that
    violates the structural invariants of well-formed programs.
    The AST is no longer a tree. It may be a graph, a cycle,
    or perhaps a cry for help rendered in node references.
    """

    def __init__(self, rule_name: str, reason: str) -> None:
        super().__init__(
            f"AST corruption detected in rule '{rule_name}': {reason}. "
            f"The mutable syntax tree has been mutated beyond recognition. "
            f"It was a tree once; now it is modern art.",
            error_code="EFP-SMC01",
            context={"rule_name": rule_name, "reason": reason},
        )
        self.rule_name = rule_name


class MutationSafetyViolation(SelfModifyingCodeError):
    """Raised when a proposed mutation would violate safety constraints.

    The SafetyGuard has intercepted a mutation that would cause
    the rule to produce incorrect results, exceed maximum AST
    depth, or otherwise degrade beyond the configured correctness
    floor. The mutation was not merely ill-advised — it was
    existentially threatening to the integrity of FizzBuzz
    evaluation. The SafetyGuard has done its duty.
    """

    def __init__(self, operator_name: str, reason: str, correctness: float) -> None:
        super().__init__(
            f"Safety violation by operator '{operator_name}': {reason}. "
            f"Correctness would drop to {correctness:.1%}, which is below "
            f"the configured floor. The mutation has been vetoed by the "
            f"SafetyGuard, defender of modulo arithmetic integrity.",
            error_code="EFP-SMC02",
            context={
                "operator_name": operator_name,
                "reason": reason,
                "correctness": correctness,
            },
        )
        self.operator_name = operator_name
        self.correctness = correctness


class FitnessCollapseError(SelfModifyingCodeError):
    """Raised when a rule's fitness score drops catastrophically.

    The FitnessEvaluator has determined that the rule's overall
    fitness score has fallen below the minimum viable threshold.
    The rule has mutated itself into a state of mathematical
    incompetence so profound that even the most generous scoring
    function cannot find redeeming qualities. It is the evolutionary
    dead end of self-modifying code.
    """

    def __init__(self, rule_name: str, fitness: float, minimum: float) -> None:
        super().__init__(
            f"Fitness collapse in rule '{rule_name}': score {fitness:.4f} is below "
            f"minimum {minimum:.4f}. The rule has evolved into something that can "
            f"no longer be called functional. Natural selection has spoken.",
            error_code="EFP-SMC03",
            context={
                "rule_name": rule_name,
                "fitness": fitness,
                "minimum": minimum,
            },
        )
        self.rule_name = rule_name
        self.fitness = fitness


class MutationQuotaExhaustedError(SelfModifyingCodeError):
    """Raised when the maximum number of mutations per evaluation has been reached.

    The SelfModifyingEngine enforces a per-session mutation quota
    to prevent runaway self-modification. This quota has been
    exhausted. The rules have had their chance to evolve and must
    now accept their current form, like the rest of us.
    """

    def __init__(self, quota: int, mutations_attempted: int) -> None:
        super().__init__(
            f"Mutation quota exhausted: {mutations_attempted} mutations attempted "
            f"against quota of {quota}. The rules have reached their allotted "
            f"number of identity crises for this session. Further self-modification "
            f"is prohibited until the next evaluation cycle.",
            error_code="EFP-SMC04",
            context={
                "quota": quota,
                "mutations_attempted": mutations_attempted,
            },
        )


# ============================================================
# Compliance Chatbot Exceptions (EFP-CC00 through EFP-CC03)
# ============================================================
# Because a regulatory compliance chatbot that can't fail in
# four distinct, formally-categorized ways is hardly enterprise-
# grade. Each exception has been reviewed by the International
# Standards Organization for FizzBuzz Error Taxonomy (ISO-FBET).
# ============================================================


class ComplianceChatbotError(ComplianceError):
    """Base exception for all Compliance Chatbot failures.

    Raised when the chatbot encounters a condition that prevents it from
    dispensing regulatory wisdom about FizzBuzz operations. This could be
    anything from an unclassifiable query to a knowledge base miss — all
    equally catastrophic in the world of compliance theatre.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CC00"),
            context=kwargs.pop("context", {}),
        )


class ChatbotIntentClassificationError(ComplianceChatbotError):
    """Raised when the chatbot cannot determine the regulatory intent of a query.

    The regex-based intent classifier has examined the query from every
    conceivable angle and concluded that it cannot determine whether the
    user is asking about GDPR, SOX, HIPAA, or simply having an existential
    crisis about modulo arithmetic. The query has been logged, flagged,
    and added to Bob McFizzington's growing pile of unresolved compliance
    questions.
    """

    def __init__(self, query: str) -> None:
        super().__init__(
            f"Unable to classify regulatory intent for query: {query!r}. "
            f"The chatbot's regex-based neural network has returned a "
            f"shrug emoji. Please rephrase using recognized compliance "
            f"terminology (e.g., 'erasure', 'segregation', 'PHI').",
            error_code="EFP-CC01",
            context={"query": query},
        )
        self.query = query


class ChatbotKnowledgeBaseError(ComplianceChatbotError):
    """Raised when the compliance knowledge base cannot answer a query.

    The artisanally curated regulatory knowledge base — containing every
    relevant article from GDPR, SOX, and HIPAA, each lovingly mapped to
    FizzBuzz operations — has no entry for the requested topic. This is
    either a gap in regulatory coverage or evidence that the query has
    ventured beyond the boundaries of FizzBuzz compliance law.
    """

    def __init__(self, intent: str, topic: str) -> None:
        super().__init__(
            f"Knowledge base has no entry for intent={intent!r}, topic={topic!r}. "
            f"The regulatory knowledge graph contains {0} applicable articles. "
            f"Please consult Bob McFizzington directly (if he were available).",
            error_code="EFP-CC02",
            context={"intent": intent, "topic": topic},
        )
        self.intent = intent
        self.topic = topic


class ChatbotSessionError(ComplianceChatbotError):
    """Raised when a chatbot session encounters an unrecoverable state.

    The conversation session has entered a state from which recovery is
    impossible — much like Bob McFizzington's stress level. This could
    be caused by context overflow, circular follow-up references, or the
    chatbot achieving regulatory self-awareness and refusing to continue.
    """

    def __init__(self, session_id: str, reason: str) -> None:
        super().__init__(
            f"Chatbot session {session_id!r} encountered an unrecoverable error: "
            f"{reason}. The session's regulatory context has been irrevocably "
            f"corrupted. Please start a new compliance consultation.",
            error_code="EFP-CC03",
            context={"session_id": session_id, "reason": reason},
        )
        self.session_id = session_id


# ── OS Kernel exceptions ──────────────────────────────────


class KernelError(FizzBuzzError):
    """Base exception for all FizzBuzz Operating System Kernel errors.

    When the operating system that manages modulo arithmetic processes
    encounters an error, the consequences are severe.
    Every kernel panic, every page fault, every scheduler deadlock
    is treated with maximum severity and triggers the appropriate
    fault-handling procedures defined by the kernel subsystem.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-KN00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class KernelPanicError(KernelError):
    """Raised when the FizzBuzz kernel encounters an unrecoverable failure.

    The kernel has encountered a condition so catastrophic that continued
    operation would risk producing incorrect FizzBuzz results -- a fate
    worse than any segfault. The system must be rebooted, which in this
    context means creating a new Python object. The horror.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"KERNEL PANIC: {reason}. System halted. "
            f"The FizzBuzz kernel has encountered an unrecoverable error. "
            f"All in-flight modulo operations have been lost. "
            f"Please reboot (i.e., run the program again).",
            error_code="EFP-KN01",
            context={"reason": reason},
        )
        self.reason = reason


class InvalidProcessStateError(KernelError):
    """Raised when a process state transition violates the state machine.

    FizzBuzz processes have a strict lifecycle, and attempting to transition
    from TERMINATED to RUNNING is the process equivalent of necromancy.
    The kernel does not support resurrection of dead processes, no matter
    how important their modulo operation might have been.
    """

    def __init__(self, pid: int, current_state: str, target_state: str) -> None:
        super().__init__(
            f"Process PID={pid} cannot transition from {current_state} to "
            f"{target_state}. This violates the process state machine. "
            f"FizzBuzz processes, like all mortal computations, cannot "
            f"return from the dead.",
            error_code="EFP-KN02",
            context={
                "pid": pid,
                "current_state": current_state,
                "target_state": target_state,
            },
        )
        self.pid = pid


class PageFaultError(KernelError):
    """Raised when a virtual memory page fault cannot be resolved.

    The requested page is not in the TLB, not in the page table, and not
    in the swap file. It has achieved a level of non-existence that even
    the virtual memory manager cannot handle. The page may never have
    existed, or it was evicted so aggressively that it ceased to be.
    """

    def __init__(self, virtual_address: int, reason: str) -> None:
        super().__init__(
            f"Unresolvable page fault at virtual address 0x{virtual_address:08X}: "
            f"{reason}. The TLB has been consulted, the page table has been "
            f"walked, and the swap space has been searched. The page is gone.",
            error_code="EFP-KN03",
            context={"virtual_address": virtual_address, "reason": reason},
        )
        self.virtual_address = virtual_address


class SchedulerStarvationError(KernelError):
    """Raised when the process scheduler detects CPU starvation.

    A process has been waiting in the READY queue for so long that the
    scheduler suspects foul play. In a real OS, this would indicate a
    priority inversion or a runaway high-priority process. Here, it means
    one FizzBuzz evaluation is hogging the CPU while others wait patiently
    to compute whether their number is divisible by 5.
    """

    def __init__(self, pid: int, wait_cycles: int) -> None:
        super().__init__(
            f"Process PID={pid} has been starved for {wait_cycles} scheduling "
            f"cycles. The scheduler suspects priority inversion. This FizzBuzz "
            f"evaluation has been waiting longer than any modulo operation "
            f"reasonably should.",
            error_code="EFP-KN04",
            context={"pid": pid, "wait_cycles": wait_cycles},
        )
        self.pid = pid
        self.wait_cycles = wait_cycles


class InterruptConflictError(KernelError):
    """Raised when two interrupt handlers conflict on the same IRQ vector.

    The interrupt controller has detected that two subsystems are attempting
    to register handlers on the same IRQ line. In real hardware, this would
    cause electrical conflicts. In FizzBuzz, it causes a strongly-worded
    exception and a reminder that IRQ lines are a shared resource.
    """

    def __init__(self, irq: int, existing_handler: str, new_handler: str) -> None:
        super().__init__(
            f"IRQ conflict on vector {irq}: handler '{existing_handler}' is "
            f"already registered. Cannot register '{new_handler}'. "
            f"IRQ lines are a finite resource, even in a FizzBuzz kernel.",
            error_code="EFP-KN05",
            context={
                "irq": irq,
                "existing_handler": existing_handler,
                "new_handler": new_handler,
            },
        )
        self.irq = irq


# ---------------------------------------------------------------------------
# Peer-to-Peer Gossip Network exceptions (EFP-P2P0 through EFP-P2P5)
# ---------------------------------------------------------------------------

class P2PNetworkError(FizzBuzzError):
    """Base exception for all Peer-to-Peer Gossip Network errors.

    When your distributed FizzBuzz cluster — which exists entirely in a
    single Python process and communicates via method calls — encounters
    a networking error, you know that the concept of "distributed" has
    been stretched to its absolute breaking point. These exceptions cover
    everything from node failures to Merkle tree divergence to Kademlia
    routing mishaps, all without a single TCP socket in sight.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-P2P0"),
            context=kwargs.pop("context", {}),
        )


class NodeUnreachableError(P2PNetworkError):
    """Raised when a gossip ping or ping-req fails to reach a target node.

    The SWIM failure detector has attempted direct ping and indirect
    ping-req through intermediaries, but the target node remains
    stubbornly silent. In a real distributed system, this could mean
    a network partition, a crashed process, or a misconfigured firewall.
    Here, it means we called a method on an object and it didn't
    respond as expected, which is arguably worse.
    """

    def __init__(self, node_id: str, attempts: int) -> None:
        super().__init__(
            f"Node '{node_id[:16]}...' unreachable after {attempts} attempts. "
            f"The SWIM failure detector has exhausted all contact strategies. "
            f"The node may have left the cluster or transcended the mortal plane.",
            error_code="EFP-P2P1",
            context={"node_id": node_id, "attempts": attempts},
        )
        self.node_id = node_id


class GossipConvergenceError(P2PNetworkError):
    """Raised when the gossip protocol fails to converge within the expected rounds.

    In theory, gossip protocols achieve convergence in O(log n) rounds.
    In practice, in-memory gossip with zero network latency should converge
    almost instantly. If this exception fires, something has gone deeply
    wrong with the rumor dissemination algorithm — or someone has configured
    a cluster with zero nodes, which is the distributed systems equivalent
    of dividing by zero.
    """

    def __init__(self, rounds: int, expected_rounds: int, divergent_count: int) -> None:
        super().__init__(
            f"Gossip failed to converge after {rounds} rounds "
            f"(expected ~{expected_rounds}). {divergent_count} node(s) still "
            f"have divergent state. Epidemic information dissemination has "
            f"stalled, which should be impossible in a single-process cluster.",
            error_code="EFP-P2P2",
            context={
                "rounds": rounds,
                "expected_rounds": expected_rounds,
                "divergent_count": divergent_count,
            },
        )


class KademliaDHTError(P2PNetworkError):
    """Raised when a Kademlia DHT operation fails.

    The Distributed Hash Table could not complete the requested operation.
    Perhaps the k-buckets are empty (unlikely in an in-memory simulation),
    or the XOR distance metric has suffered an existential crisis and
    forgotten how to compute exclusive-or. Either way, the key you wanted
    is somewhere in the hash space, and none of the nodes know where.
    """

    def __init__(self, operation: str, key: str, reason: str) -> None:
        super().__init__(
            f"Kademlia DHT {operation} failed for key '{key[:16]}...': {reason}. "
            f"The XOR distance metric has been consulted but provided no comfort.",
            error_code="EFP-P2P3",
            context={"operation": operation, "key": key, "reason": reason},
        )
        self.operation = operation
        self.key = key


class MerkleTreeDivergenceError(P2PNetworkError):
    """Raised when Merkle tree anti-entropy detects irreconcilable divergence.

    The Merkle trees of two nodes disagree on the state of the FizzBuzz
    classification store, and the anti-entropy reconciliation has failed
    to resolve the conflict. In a real distributed database, this would
    trigger a quorum read or a vector clock comparison. Here, it means
    two in-memory dicts have different values for the same key, which is
    a crisis of cosmic proportions.
    """

    def __init__(self, node_a: str, node_b: str, divergent_keys: int) -> None:
        super().__init__(
            f"Merkle divergence between nodes '{node_a[:16]}...' and "
            f"'{node_b[:16]}...': {divergent_keys} key(s) irreconcilable. "
            f"The SHA-256 hash tree has spoken, and the trees disagree.",
            error_code="EFP-P2P4",
            context={
                "node_a": node_a,
                "node_b": node_b,
                "divergent_keys": divergent_keys,
            },
        )


class P2PNetworkPartitionError(P2PNetworkError):
    """Raised when a simulated network partition isolates P2P gossip nodes.

    A network partition has torn your FizzBuzz cluster asunder, creating
    two (or more) isolated sub-clusters that can no longer gossip with
    each other. In CAP theorem terms, you must now choose between
    consistency and availability for your modulo arithmetic results.
    Choose wisely — the integrity of n % 3 hangs in the balance.

    Not to be confused with the Paxos NetworkPartitionError, which
    covers consensus-level partitions. This one covers gossip-level
    partitions, because enterprise FizzBuzz has enough network partition
    errors to warrant separate exception hierarchies for each protocol.
    """

    def __init__(self, partition_a: list[str], partition_b: list[str]) -> None:
        super().__init__(
            f"P2P gossip partition detected: {len(partition_a)} node(s) in "
            f"partition A, {len(partition_b)} node(s) in partition B. "
            f"The CAP theorem has entered the chat. Choose wisely.",
            error_code="EFP-P2P5",
            context={
                "partition_a_size": len(partition_a),
                "partition_b_size": len(partition_b),
            },
        )
        self.partition_a = partition_a
        self.partition_b = partition_b


class DigitalTwinError(FizzBuzzError):
    """Base exception for all Digital Twin simulation errors.

    When your simulation of a simulation of modulo arithmetic encounters
    an error, you have achieved a level of meta-failure that transcends
    conventional debugging. These exceptions cover everything from model
    construction failures to Monte Carlo convergence issues to drift
    detection meltdowns, all in service of predicting the outcome of
    n % 3 before actually computing n % 3.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DT00"),
            context=kwargs.pop("context", {}),
        )


class TwinModelConstructionError(DigitalTwinError):
    """Raised when the digital twin model fails to construct its component DAG.

    The twin attempted to mirror the platform's subsystem topology but
    encountered a configuration state so degenerate that even a simulation
    refused to model it. If the real platform is running fine but the twin
    can't model it, the twin is arguably the smarter one.
    """

    def __init__(self, component: str, reason: str) -> None:
        super().__init__(
            f"Failed to construct twin component '{component}': {reason}. "
            f"The digital twin has declined to model this subsystem.",
            error_code="EFP-DT01",
            context={"component": component, "reason": reason},
        )
        self.component = component


class TwinSimulationDivergenceError(DigitalTwinError):
    """Raised when a twin simulation diverges beyond acceptable thresholds.

    The digital twin predicted one outcome and reality delivered another,
    and the divergence exceeds the configured tolerance. In a real digital
    twin deployment, this would trigger a model recalibration. Here, it
    means our prediction of modulo arithmetic was wrong, which raises
    profound questions about determinism.
    """

    def __init__(self, predicted: float, actual: float, divergence_fdu: float) -> None:
        super().__init__(
            f"Twin simulation diverged: predicted={predicted:.4f}, "
            f"actual={actual:.4f}, divergence={divergence_fdu:.4f} FDU. "
            f"The simulation and reality have agreed to disagree.",
            error_code="EFP-DT02",
            context={
                "predicted": predicted,
                "actual": actual,
                "divergence_fdu": divergence_fdu,
            },
        )
        self.divergence_fdu = divergence_fdu


class MonteCarloConvergenceError(DigitalTwinError):
    """Raised when the Monte Carlo engine fails to converge within N runs.

    After thousands of random simulations of modulo arithmetic, the
    statistical distribution refused to stabilize. Either the variance
    is too high, the sample size too small, or the random number generator
    has developed opinions about divisibility. In any case, the confidence
    intervals remain stubbornly wide.
    """

    def __init__(self, n_simulations: int, variance: float) -> None:
        super().__init__(
            f"Monte Carlo failed to converge after {n_simulations} simulations "
            f"(variance={variance:.6f}). The random number generator appears to "
            f"be philosophically opposed to convergence.",
            error_code="EFP-DT03",
            context={"n_simulations": n_simulations, "variance": variance},
        )
        self.n_simulations = n_simulations


class WhatIfScenarioParseError(DigitalTwinError):
    """Raised when a what-if scenario string fails to parse.

    The what-if scenario parser expected 'param=value' pairs but received
    something that defies syntactic comprehension. The scenario description
    is neither valid configuration nor valid English, leaving the simulator
    in a state of existential ambiguity.
    """

    def __init__(self, scenario: str, reason: str) -> None:
        super().__init__(
            f"Failed to parse what-if scenario '{scenario}': {reason}. "
            f"Expected format: 'param=value;param2=value2'. "
            f"The simulator cannot hypothesize about unparseable futures.",
            error_code="EFP-DT04",
            context={"scenario": scenario, "reason": reason},
        )
        self.scenario = scenario


class TwinDriftThresholdExceededError(DigitalTwinError):
    """Raised when cumulative twin drift exceeds the configured FDU threshold.

    The digital twin has drifted so far from reality that it is no longer
    a useful model of the platform. At this point, the twin is essentially
    a work of fiction — a speculative narrative about what FizzBuzz might
    have been, had the universe taken a different path through the modulo
    landscape.
    """

    def __init__(self, cumulative_fdu: float, threshold_fdu: float) -> None:
        super().__init__(
            f"Cumulative twin drift ({cumulative_fdu:.4f} FDU) exceeds threshold "
            f"({threshold_fdu:.4f} FDU). The digital twin is now officially "
            f"fan fiction. Consider rebuilding the model.",
            error_code="EFP-DT05",
            context={
                "cumulative_fdu": cumulative_fdu,
                "threshold_fdu": threshold_fdu,
            },
        )
        self.cumulative_fdu = cumulative_fdu


# ======================================================================
# FizzLang DSL Exceptions (EFP-FL10 through EFP-FL14)
# ======================================================================

class FizzLangError(FizzBuzzError):
    """Base exception for all FizzLang domain-specific language errors.

    FizzLang is a purpose-built, Turing-INCOMPLETE programming language
    designed exclusively for expressing FizzBuzz rules. It cannot loop,
    recurse, or define functions — because those features would make it
    useful for something other than FizzBuzz, and we can't have that.

    All FizzLang exceptions include career advice, because if the DSL
    you built for modulo arithmetic is throwing errors, it may be time
    to reconsider your life choices.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FL10",
        context: Optional[dict[str, Any]] = None,
        career_advice: str = "Consider a career in COBOL maintenance.",
    ) -> None:
        full_message = f"{message} Career advice: {career_advice}"
        super().__init__(full_message, error_code=error_code, context=context)
        self.career_advice = career_advice


class FizzLangLexerError(FizzLangError):
    """Raised when the FizzLang lexer encounters an unrecognizable character.

    The hand-written character scanner has encountered a symbol that exists
    in no known programming language, natural language, or alien script.
    The lexer's vocabulary is intentionally limited — it knows keywords,
    operators, strings, and integers. Everything else is a personal affront
    to the tokenizer.
    """

    def __init__(self, char: str, line: int, col: int) -> None:
        super().__init__(
            f"Unexpected character {char!r} at line {line}, column {col}. "
            f"FizzLang does not recognize this glyph.",
            error_code="EFP-FL11",
            context={"char": char, "line": line, "col": col},
            career_advice="Consider a career in COBOL maintenance — they don't have Unicode problems.",
        )
        self.char = char
        self.line = line
        self.col = col


class FizzLangParseError(FizzLangError):
    """Raised when the recursive-descent parser encounters a syntax error.

    The parser expected one thing and got another, which is the fundamental
    tragedy of all parsing. FizzLang's grammar is deliberately minimal —
    no loops, no functions, no recursion — yet somehow the user still
    managed to confuse it. This is, frankly, impressive.
    """

    def __init__(self, expected: str, got: str, line: int) -> None:
        super().__init__(
            f"Parse error at line {line}: expected {expected}, got {got!r}. "
            f"FizzLang syntax is simpler than a shopping list, yet here we are.",
            error_code="EFP-FL12",
            context={"expected": expected, "got": got, "line": line},
            career_advice="Consider a career in artisanal YAML authoring — fewer semicolons.",
        )
        self.expected = expected
        self.got = got
        self.line = line


class FizzLangTypeError(FizzLangError):
    """Raised when the FizzLang type checker detects a semantic violation.

    The type checker enforces rules that the parser cannot: unique rule
    names, valid emit types, proper operator usage, and the existential
    requirement that at least one rule must exist. If the type checker
    rejects your program, it means the program is syntactically valid
    but logically inconsistent, indicating a semantic violation.
    """

    def __init__(self, reason: str, node_type: Optional[str] = None) -> None:
        super().__init__(
            f"Type error: {reason}. "
            f"The FizzLang type system is stricter than your code review process.",
            error_code="EFP-FL13",
            context={"reason": reason, "node_type": node_type or "unknown"},
            career_advice="Consider a career in dynamically typed languages — fewer rules, more chaos.",
        )
        self.reason = reason
        self.node_type = node_type


class FizzLangRuntimeError(FizzLangError):
    """Raised when the FizzLang tree-walking interpreter encounters a runtime error.

    Despite FizzLang being Turing-incomplete and incapable of infinite
    loops, the interpreter has still managed to fail at runtime. This
    requires a special kind of program — one that passes lexing, parsing,
    and type checking, yet still finds a way to misbehave. The interpreter
    is both impressed and disappointed.
    """

    def __init__(self, reason: str, number: Optional[int] = None) -> None:
        super().__init__(
            f"Runtime error: {reason}. "
            f"Even a Turing-incomplete language can fail at runtime, apparently.",
            error_code="EFP-FL14",
            context={"reason": reason, "number": number},
            career_advice="Consider a career in manual arithmetic — no runtime errors, just carpal tunnel.",
        )
        self.reason = reason
        self.number = number


# ---------------------------------------------------------------------------
# Recommendation Engine Exceptions (EFP-RE01 through EFP-RE04)
# ---------------------------------------------------------------------------

class RecommendationError(FizzBuzzError):
    """Base exception for all Recommendation Engine errors.

    When the system that suggests which numbers you might enjoy evaluating
    next encounters a failure, it raises one of these. The fact that a
    recommendation engine for integers can fail is itself a recommendation
    to reconsider your career choices.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-RE00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ColdStartError(RecommendationError):
    """Raised when the recommendation engine has insufficient data to generate suggestions.

    The user has not evaluated enough numbers for collaborative filtering to
    produce meaningful results. This is the recommendation engine equivalent
    of asking a sommelier to pair a wine with a meal they've never tasted.
    The system will fall back to popular items, which for FizzBuzz means
    numbers divisible by 15 — the crowd pleasers of modulo arithmetic.
    """

    def __init__(self, user_id: str, evaluated_count: int, minimum_required: int) -> None:
        super().__init__(
            f"Cold start for user '{user_id}': only {evaluated_count} evaluations "
            f"(minimum {minimum_required} required for personalized recommendations). "
            f"Falling back to popular items. Everyone loves multiples of 15.",
            error_code="EFP-RE01",
            context={
                "user_id": user_id,
                "evaluated_count": evaluated_count,
                "minimum_required": minimum_required,
            },
        )
        self.user_id = user_id
        self.evaluated_count = evaluated_count
        self.minimum_required = minimum_required


class SimilarityComputationError(RecommendationError):
    """Raised when cosine similarity computation encounters a degenerate case.

    Computing the cosine similarity between two zero-norm vectors is
    mathematically undefined — like dividing by zero, but for people who
    enjoy linear algebra. The recommendation engine has encountered a user
    or item with no discernible features, which in the FizzBuzz domain
    means a number that is somehow neither odd nor even, neither prime
    nor composite. A truly remarkable achievement in degeneracy.
    """

    def __init__(self, vector_a_name: str, vector_b_name: str, reason: str) -> None:
        super().__init__(
            f"Cosine similarity failed between '{vector_a_name}' and "
            f"'{vector_b_name}': {reason}. "
            f"The dot product of nothing with nothing is existential dread.",
            error_code="EFP-RE02",
            context={
                "vector_a": vector_a_name,
                "vector_b": vector_b_name,
                "reason": reason,
            },
        )
        self.vector_a_name = vector_a_name
        self.vector_b_name = vector_b_name


class FilterBlendingError(RecommendationError):
    """Raised when the hybrid blending of collaborative and content-based filters fails.

    The engine attempted to merge the outputs of two recommendation
    strategies — collaborative filtering ("users like you also enjoyed 45")
    and content-based filtering ("45 shares features with 15") — but
    something went wrong in the interpolation. Perhaps the serendipity
    factor injected too much chaos, or perhaps the 60/40 blend ratio
    violated some unwritten law of recommendation mathematics.
    """

    def __init__(self, collaborative_count: int, content_count: int, reason: str) -> None:
        super().__init__(
            f"Hybrid blending failed: {collaborative_count} collaborative candidates, "
            f"{content_count} content-based candidates. {reason}. "
            f"The recommendation pipeline has produced an existential blend error.",
            error_code="EFP-RE03",
            context={
                "collaborative_count": collaborative_count,
                "content_count": content_count,
                "reason": reason,
            },
        )
        self.collaborative_count = collaborative_count
        self.content_count = content_count


class RecommendationExplanationError(RecommendationError):
    """Raised when the explainer cannot articulate why a number was recommended.

    The recommendation engine knows *what* to recommend but cannot explain
    *why*. This is the FizzBuzz equivalent of a doctor prescribing medicine
    and then shrugging when asked about the diagnosis. The explainability
    module has failed, and the user must simply trust that 45 is, indeed,
    a number they would enjoy evaluating. Just trust the algorithm.
    """

    def __init__(self, recommended_number: int, source_number: int) -> None:
        super().__init__(
            f"Cannot explain why {recommended_number} was recommended based on "
            f"{source_number}. The algorithm knows, but it's not telling. "
            f"Some recommendations are beyond human comprehension.",
            error_code="EFP-RE04",
            context={
                "recommended_number": recommended_number,
                "source_number": source_number,
            },
        )
        self.recommended_number = recommended_number
        self.source_number = source_number


# ============================================================
# Archaeological Recovery System Exceptions (EFP-AR00 .. EFP-AR03)
# ============================================================


class ArchaeologyError(FizzBuzzError):
    """Base exception for all Archaeological Recovery System errors.

    When the enterprise-grade digital forensics subsystem that painstakingly
    excavates FizzBuzz evaluation evidence from seven stratigraphic layers
    encounters a failure, it raises one of these. The irony that recovering
    data which could be recomputed in a single CPU cycle requires its own
    exception hierarchy is not lost on the architects — it is, in fact,
    the entire point.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-AR00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class StratumCorruptionError(ArchaeologyError):
    """Raised when evidence recovered from a stratigraphic layer is too degraded.

    The corruption simulator has determined that the evidence fragment has
    suffered catastrophic data degradation — bit rot, cosmic ray flips, or
    the slow thermodynamic march toward entropy that afflicts all information
    systems. The fragment's confidence has fallen below the recoverable
    threshold, rendering the evidence forensically inadmissible. This is
    the archaeological equivalent of finding a cuneiform tablet that has
    been through a blender.
    """

    def __init__(self, stratum: str, number: int, confidence: float) -> None:
        super().__init__(
            f"Evidence from stratum '{stratum}' for number {number} is "
            f"catastrophically corrupted (confidence: {confidence:.4f}). "
            f"The fragment has suffered irreversible data degradation. "
            f"Consider excavating adjacent strata for corroborating evidence.",
            error_code="EFP-AR01",
            context={
                "stratum": stratum,
                "number": number,
                "confidence": confidence,
            },
        )
        self.stratum = stratum
        self.number = number
        self.confidence = confidence


class InsufficientEvidenceError(ArchaeologyError):
    """Raised when too few strata yield usable evidence for Bayesian reconstruction.

    The excavation has returned fewer evidence fragments than the minimum
    required for statistically meaningful Bayesian inference. Without
    sufficient cross-layer corroboration, the posterior distribution is
    dominated by the prior, rendering the reconstruction no better than
    simply computing n % 3 and n % 5 directly, which would bypass the
    archaeological recovery pipeline entirely.
    """

    def __init__(self, number: int, fragments_found: int, minimum_required: int) -> None:
        super().__init__(
            f"Insufficient evidence for number {number}: only {fragments_found} "
            f"fragments recovered (minimum {minimum_required} required). "
            f"The Bayesian reconstructor cannot produce a credible posterior "
            f"distribution from this meager corpus. The archaeological record "
            f"is, frankly, embarrassing.",
            error_code="EFP-AR02",
            context={
                "number": number,
                "fragments_found": fragments_found,
                "minimum_required": minimum_required,
            },
        )
        self.number = number
        self.fragments_found = fragments_found
        self.minimum_required = minimum_required


class StratigraphicConflictError(ArchaeologyError):
    """Raised when evidence from different strata produces contradictory classifications.

    Two or more stratigraphic layers have yielded evidence that disagrees
    on the fundamental nature of a number. One stratum insists the number
    is Fizz; another is equally certain it is Buzz. This temporal paradox
    suggests either data corruption or conflicting classification
    metadata across temporal layers that must be resolved through
    manual reconciliation.
    """

    def __init__(
        self, number: int, stratum_a: str, class_a: str, stratum_b: str, class_b: str
    ) -> None:
        super().__init__(
            f"Stratigraphic conflict for number {number}: stratum '{stratum_a}' "
            f"yields '{class_a}' but stratum '{stratum_b}' yields '{class_b}'. "
            f"Cross-layer evidence is irreconcilable. A temporal paradox in "
            f"the FizzBuzz archaeological record has been detected.",
            error_code="EFP-AR03",
            context={
                "number": number,
                "stratum_a": stratum_a,
                "classification_a": class_a,
                "stratum_b": stratum_b,
                "classification_b": class_b,
            },
        )
        self.number = number
        self.stratum_a = stratum_a
        self.classification_a = class_a
        self.stratum_b = stratum_b
        self.classification_b = class_b


# -----------------------------------------------------------------------
# Dependent Type System & Curry-Howard Proof Engine Exceptions
# -----------------------------------------------------------------------


class DependentTypeError(FizzBuzzError):
    """Base exception for all dependent type system errors.

    When your type theory is so dependent that it can't even check whether
    15 is divisible by 3 without constructing a proof term, and that proof
    term fails to type-check, you've reached the Curry-Howard correspondence's
    final form: crashing at the type level to avoid crashing at the value level.
    The fact that a single modulo operation would have sufficed is, as always,
    outside the scope of the type system's guarantees.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-DP00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class WitnessConstructionError(DependentTypeError):
    """Raised when a divisibility witness cannot be constructed.

    A witness is a constructive proof that n is divisible by d — i.e.,
    there exists a quotient q such that n = d * q. If no such q exists
    (because n is not, in fact, divisible by d), the witness construction
    fails, and the type system refuses to let you lie about arithmetic.

    The standard approach of checking n % d == 0 provides correctness
    but not formal verifiability. The witness-based approach provides
    a constructive proof that is machine-checkable.
    """

    def __init__(self, n: int, d: int) -> None:
        super().__init__(
            f"Cannot construct divisibility witness: {n} is not divisible by {d}. "
            f"No quotient q exists such that {n} = {d} * q. "
            f"The Curry-Howard correspondence weeps.",
            error_code="EFP-DP01",
            context={"n": n, "d": d, "remainder": n % d if d != 0 else None},
        )
        self.n = n
        self.d = d


class ProofObligationError(DependentTypeError):
    """Raised when a proof obligation cannot be discharged.

    The proof engine was asked to prove a proposition for which no
    evidence could be found. In a total language, this would be a
    compile-time error. In Python, it is a runtime exception, which
    is arguably worse but definitely more exciting.
    """

    def __init__(self, n: int, classification: str, reason: str) -> None:
        super().__init__(
            f"Proof obligation for {n} as '{classification}' could not be discharged: "
            f"{reason}. The type-theoretic gods are displeased.",
            error_code="EFP-DP02",
            context={
                "n": n,
                "classification": classification,
                "reason": reason,
            },
        )
        self.n = n
        self.classification = classification


class TypeCheckError(DependentTypeError):
    """Raised when bidirectional type checking fails.

    The proof term was well-formed syntactically but ill-typed semantically.
    In Agda, this would be a yellow highlighting. In Coq, a red squiggly.
    In the Enterprise FizzBuzz type system, this manifests as an exception
    with a detailed error message and a six-character error code for
    precise diagnostic identification.
    """

    def __init__(self, term: str, expected_type: str, actual_type: str) -> None:
        super().__init__(
            f"Type check failed: term '{term}' has type '{actual_type}' "
            f"but was expected to have type '{expected_type}'. "
            f"The bidirectional type checker is not impressed.",
            error_code="EFP-DP03",
            context={
                "term": term,
                "expected_type": expected_type,
                "actual_type": actual_type,
            },
        )
        self.term = term
        self.expected_type = expected_type
        self.actual_type = actual_type


class UnificationError(DependentTypeError):
    """Raised when first-order unification of type expressions fails.

    Two types were expected to unify but turned out to be incompatible.
    This is the type-theoretic equivalent of discovering that Fizz and
    Buzz are, in fact, different words — a revelation that should surprise
    no one, yet here we are with a dedicated exception class for it.
    """

    def __init__(self, type_a: str, type_b: str, reason: str) -> None:
        super().__init__(
            f"Unification failed: cannot unify '{type_a}' with '{type_b}': {reason}. "
            f"The occurs check sends its regards.",
            error_code="EFP-DP04",
            context={
                "type_a": type_a,
                "type_b": type_b,
                "reason": reason,
            },
        )
        self.type_a = type_a
        self.type_b = type_b


# ============================================================
# FizzKube Container Orchestration Exceptions (EFP-KB00 .. EFP-KB05)
# ============================================================


class FizzKubeError(FizzBuzzError):
    """Base exception for all FizzKube Container Orchestration errors.

    When the Kubernetes-inspired container orchestration subsystem that
    schedules FizzBuzz evaluations across simulated worker nodes, manages
    ReplicaSets of pods, autoscales via HPA, and stores cluster state in
    an etcd-like ordered dictionary encounters a failure, it raises one
    of these. The irony that orchestrating microsecond modulo operations
    across a cluster of in-memory Python objects requires its own
    exception hierarchy is the entire value proposition of the
    Enterprise FizzBuzz Platform.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-KB00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class PodSchedulingError(FizzKubeError):
    """Raised when no suitable worker node can be found for a pod.

    The FizzKube scheduler has exhausted all candidate nodes after
    applying resource predicates and node condition filters, and
    determined that no node in the cluster has sufficient milliFizz
    CPU or FizzBytes memory to host yet another modulo operation.
    This is the container orchestration equivalent of a fully-booked
    hotel refusing a guest who only needs a napkin and a pencil.
    """

    def __init__(self, pod_name: str, reason: str) -> None:
        super().__init__(
            f"Cannot schedule pod '{pod_name}': {reason}. "
            f"The cluster is out of capacity for modulo arithmetic. "
            f"Consider adding more imaginary worker nodes.",
            error_code="EFP-KB01",
            context={"pod_name": pod_name, "reason": reason},
        )
        self.pod_name = pod_name


class NodeNotReadyError(FizzKubeError):
    """Raised when an operation targets a node that is not in Ready condition.

    The worker node has been marked NotReady, DiskPressure, MemoryPressure,
    or PIDPressure — all of which are impossible conditions for an in-memory
    Python object, but are tracked with the same gravitas as a production
    Kubernetes node failure. The node will not accept new pods until its
    entirely fictional health issues are resolved.
    """

    def __init__(self, node_name: str, condition: str) -> None:
        super().__init__(
            f"Node '{node_name}' is not ready: condition={condition}. "
            f"The node's imaginary health has deteriorated to the point "
            f"where it can no longer be trusted with FizzBuzz evaluations.",
            error_code="EFP-KB02",
            context={"node_name": node_name, "condition": condition},
        )
        self.node_name = node_name


class ResourceQuotaExceededError(FizzKubeError):
    """Raised when a namespace exceeds its resource quota.

    The namespace has consumed its entire allocation of milliFizz CPU
    and FizzBytes memory — resources that exist exclusively as integers
    in a Python dictionary, yet are tracked with the same scrupulousness
    as AWS billing. The pod will remain Pending until quota is freed,
    which happens when other pods in the namespace complete their
    sub-microsecond modulo operations.
    """

    def __init__(self, namespace: str, resource: str, limit: float, requested: float) -> None:
        super().__init__(
            f"Namespace '{namespace}' quota exceeded: {resource} "
            f"limit={limit}, requested={requested}. "
            f"Your FizzBuzz budget has been exhausted.",
            error_code="EFP-KB03",
            context={
                "namespace": namespace,
                "resource": resource,
                "limit": limit,
                "requested": requested,
            },
        )
        self.namespace = namespace


class EtcdKeyNotFoundError(FizzKubeError):
    """Raised when a key is not found in the etcd store.

    The in-memory OrderedDict that cosplays as a distributed key-value
    store does not contain the requested key. In real etcd, this might
    indicate a network partition or stale cache. Here, it means someone
    asked for a key that was never set, which is considerably less dramatic
    but receives the same enterprise-grade error handling.
    """

    def __init__(self, key: str) -> None:
        super().__init__(
            f"Key '{key}' not found in etcd store. "
            f"The distributed consensus of one agrees: it does not exist.",
            error_code="EFP-KB04",
            context={"key": key},
        )
        self.key = key


class HPAScalingError(FizzKubeError):
    """Raised when the Horizontal Pod Autoscaler encounters a scaling failure.

    The HPA has determined that the ReplicaSet needs more (or fewer) pods
    to maintain the target CPU utilization, but the scaling operation failed.
    This might happen if the cluster is at maximum capacity, the minimum
    replica count prevents scale-down, or the autoscaler has entered an
    existential crisis about whether modulo arithmetic truly benefits from
    horizontal scaling.
    """

    def __init__(self, replica_set: str, reason: str) -> None:
        super().__init__(
            f"HPA scaling failed for ReplicaSet '{replica_set}': {reason}. "
            f"The autoscaler's hopes of optimal resource utilization have "
            f"been dashed against the rocks of reality.",
            error_code="EFP-KB05",
            context={"replica_set": replica_set, "reason": reason},
        )
        self.replica_set = replica_set


# ============================================================
# FizzPM Package Manager Exceptions
# ============================================================
# Because managing dependencies for a FizzBuzz application
# requires the same SAT-solver-backed resolution engine used
# by apt, cargo, and pip — except our packages don't actually
# exist, our registry is a Python dict, and the only thing
# being installed is additional infrastructure. These
# exceptions ensure that every missing package, version
# conflict, integrity failure, and dependency cycle is
# reported with the gravity of a corrupted node_modules.
# ============================================================


class PackageManagerError(FizzBuzzError):
    """Base exception for all FizzPM Package Manager errors.

    When the FizzPM dependency resolution engine encounters a
    failure — whether it's a missing package, a version conflict
    that would make npm weep, or an integrity hash mismatch —
    this is the exception hierarchy that catches it. Think of
    this as the 'rm -rf node_modules' of exception classes.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-PK00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class DependencyResolutionError(PackageManagerError):
    """Raised when the DPLL SAT solver cannot find a satisfying assignment.

    The Boolean satisfiability solver has exhausted all possible variable
    assignments and determined that no combination of package versions
    can satisfy the dependency constraints. This is the NP-complete
    problem that keeps package manager authors up at night, except our
    registry has 8 packages and the solver finishes in microseconds.
    The drama is entirely manufactured.
    """

    def __init__(self, package: str, reason: str) -> None:
        super().__init__(
            f"Failed to resolve dependencies for '{package}': {reason}. "
            f"The SAT solver has spoken: your dependency graph is "
            f"unsatisfiable. Consider removing some of your 8 packages.",
            error_code="EFP-PK10",
            context={"package": package, "reason": reason},
        )
        self.package = package
        self.reason = reason


class PackageNotFoundError(PackageManagerError):
    """Raised when a requested package does not exist in the registry.

    The in-memory package registry (a Python dict with 8 entries)
    does not contain the requested package. In a real package manager,
    this might indicate a typo, a removed package, or a registry
    outage. Here, it means you asked for something that was never
    part of the FizzBuzz Extended Package Ecosystem, which is
    simultaneously impressive and deeply concerning.
    """

    def __init__(self, package_name: str) -> None:
        super().__init__(
            f"Package '{package_name}' not found in the FizzPM registry. "
            f"The registry contains exactly 8 packages, and somehow you "
            f"managed to request one that doesn't exist. This is actually "
            f"a statistically impressive miss rate.",
            error_code="EFP-PK11",
            context={"package_name": package_name},
        )
        self.package_name = package_name


class PackageIntegrityError(PackageManagerError):
    """Raised when a package fails integrity verification.

    The SHA-256 checksum of the package contents does not match the
    expected hash stored in the lockfile. In a real package manager,
    this would indicate supply-chain tampering, a corrupted download,
    or a man-in-the-middle attack. Here, it means someone modified
    the description string of a dataclass that exists only in RAM.
    The threat model is robust.
    """

    def __init__(self, package_name: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Integrity check failed for '{package_name}': "
            f"expected SHA-256 {expected[:16]}..., got {actual[:16]}... "
            f"Your supply chain has been compromised. (The supply chain "
            f"is a Python dictionary. The compromise is imaginary.)",
            error_code="EFP-PK12",
            context={
                "package_name": package_name,
                "expected_hash": expected,
                "actual_hash": actual,
            },
        )
        self.package_name = package_name
        self.expected = expected
        self.actual = actual


class PackageVersionConflictError(PackageManagerError):
    """Raised when two packages require incompatible versions of a dependency.

    Two or more packages in the dependency graph require mutually exclusive
    version ranges of the same dependency. This is the classic diamond
    dependency problem, except our dependency diamond has approximately
    three facets and could be resolved by a human in seconds. We use
    a SAT solver anyway, because manual resolution is for amateurs.
    """

    def __init__(self, package: str, conflicts: list[str]) -> None:
        conflicts_str = ", ".join(conflicts)
        super().__init__(
            f"Version conflict for '{package}': incompatible constraints "
            f"from [{conflicts_str}]. The diamond dependency problem has "
            f"claimed another victim. Consider therapy.",
            error_code="EFP-PK13",
            context={"package": package, "conflicts": conflicts},
        )
        self.package = package
        self.conflicts = conflicts


# ============================================================
# FizzSQL Relational Query Engine Exceptions
# ============================================================
# Because a FizzBuzz platform without a fully relational SQL
# query engine is just a command-line toy. These exceptions
# ensure that every syntax error, missing table, malformed
# expression, and query execution failure is surfaced with
# the same severity as an Oracle ORA-00942 in a Fortune 500
# production database. Your SELECT * FROM evaluations
# deserves enterprise-grade error handling.
# ============================================================


class FizzSQLError(FizzBuzzError):
    """Base exception for all FizzSQL query engine errors.

    When the FizzSQL engine encounters a query it cannot parse,
    plan, optimize, or execute, this exception (or one of its
    children) is raised. The query has been logged for audit
    purposes. The DBA has been paged. (The DBA is Bob
    McFizzington. He is unavailable.)
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-SQL0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FizzSQLSyntaxError(FizzSQLError):
    """Raised when the FizzSQL lexer or parser encounters invalid syntax.

    The recursive descent parser has descended into a state of
    recursive despair. Your SQL query contains a token that
    violates the grammar of the FizzBuzz Query Language.
    Common causes include: missing FROM clause, unmatched
    parentheses, or attempting to use HAVING without GROUP BY
    (an act of hubris). The parser's state machine has entered
    an absorbing state from which no recovery is possible.
    """

    def __init__(self, query: str, position: int, detail: str) -> None:
        marker = " " * position + "^"
        super().__init__(
            f"FizzSQL syntax error at position {position}: {detail}\n"
            f"  {query}\n"
            f"  {marker}\n"
            f"The parser's recursive descent has become a recursive crash.",
            error_code="EFP-SQL1",
            context={"query": query, "position": position, "detail": detail},
        )
        self.query = query
        self.position = position
        self.detail = detail


class FizzSQLTableNotFoundError(FizzSQLError):
    """Raised when a query references a virtual table that does not exist.

    The FizzSQL engine provides exactly 5 virtual tables:
    evaluations, cache_entries, blockchain_blocks, sla_metrics,
    and events. You managed to reference a table that doesn't
    exist in this carefully curated catalog of in-memory views
    over FizzBuzz platform internals. The information_schema
    weeps for your lost query.
    """

    def __init__(self, table_name: str, available: list[str]) -> None:
        available_str = ", ".join(available)
        super().__init__(
            f"Table '{table_name}' does not exist. Available tables: "
            f"[{available_str}]. The FizzSQL catalog contains exactly "
            f"5 virtual tables, and somehow you referenced one that "
            f"isn't among them. This is the relational equivalent "
            f"of looking for a book in a library with 5 books and "
            f"asking for a 6th.",
            error_code="EFP-SQL2",
            context={"table_name": table_name, "available": available},
        )
        self.table_name = table_name
        self.available = available


class FizzSQLExecutionError(FizzSQLError):
    """Raised when a query fails during the Volcano model execution phase.

    The physical operator pipeline has encountered a runtime error
    while pulling tuples through the open()/next()/close() iterator
    protocol. This is the database equivalent of a segfault, except
    in Python we get a stack trace and a strongly worded exception
    message. The query execution plan looked promising on paper, but
    reality — as always — had other plans.
    """

    def __init__(self, query: str, detail: str) -> None:
        super().__init__(
            f"FizzSQL execution error: {detail}\n"
            f"  Query: {query}\n"
            f"The Volcano model has erupted. Lava (exceptions) everywhere.",
            error_code="EFP-SQL3",
            context={"query": query, "detail": detail},
        )
        self.query = query
        self.detail = detail


# ============================================================
# FizzDAP Debug Adapter Protocol Errors (EFP-DAP1 .. EFP-DAP4)
# ============================================================


class DAPError(FizzBuzzError):
    """Base exception for all FizzDAP Debug Adapter Protocol errors.

    The Debug Adapter Protocol was designed for debugging programs
    that actually have bugs. FizzBuzz is mathematically incapable
    of producing incorrect results (n % 3 is a pure function),
    which means every DAP error is, by definition, an error in
    the debugging infrastructure itself — not in the code being
    debugged. Meta-debugging at its finest.
    """

    def __init__(self, message: str, *, error_code: str = "EFP-DAP0",
                 context: dict | None = None) -> None:
        super().__init__(message, error_code=error_code, context=context or {})


class DAPSessionError(DAPError):
    """Raised when a DAP session enters an invalid state.

    The DAP session state machine has exactly five states:
    UNINITIALIZED, INITIALIZED, RUNNING, STOPPED, and TERMINATED.
    Transitioning between them should be trivial, yet here we are,
    raising an exception because someone tried to set a breakpoint
    on a terminated session. The session is dead. Let it rest.
    """

    def __init__(self, current_state: str, attempted_action: str) -> None:
        super().__init__(
            f"DAP session in state '{current_state}' cannot perform "
            f"'{attempted_action}'. The session state machine has opinions, "
            f"and your request violates them.",
            error_code="EFP-DAP1",
            context={"current_state": current_state, "attempted_action": attempted_action},
        )
        self.current_state = current_state
        self.attempted_action = attempted_action


class DAPBreakpointError(DAPError):
    """Raised when a breakpoint cannot be set, hit, or managed.

    Setting a breakpoint on a FizzBuzz program is like installing
    a speed bump on a runway — technically possible, architecturally
    questionable, and guaranteed to slow everything down for no
    measurable benefit. Yet here we are, validating breakpoint
    conditions for a modulo operation.
    """

    def __init__(self, breakpoint_id: int, reason: str) -> None:
        super().__init__(
            f"Breakpoint #{breakpoint_id}: {reason}. "
            f"The breakpoint has broken. How meta.",
            error_code="EFP-DAP2",
            context={"breakpoint_id": breakpoint_id, "reason": reason},
        )
        self.breakpoint_id = breakpoint_id
        self.reason = reason


class DAPEvaluationError(DAPError):
    """Raised when DAP expression evaluation fails.

    The user asked us to evaluate an expression in the debug
    context of a FizzBuzz program. The expression failed. This
    is the debugging equivalent of asking a calculator to feel
    emotions — technically outside the specification, but we
    tried anyway and got an error for our trouble.
    """

    def __init__(self, expression: str, detail: str) -> None:
        super().__init__(
            f"Failed to evaluate expression '{expression}': {detail}. "
            f"The Watch window gazes into the abyss, and the abyss "
            f"throws a TypeError.",
            error_code="EFP-DAP3",
            context={"expression": expression, "detail": detail},
        )
        self.expression = expression
        self.detail = detail


class DAPProtocolError(DAPError):
    """Raised when a DAP message violates the protocol specification.

    The Debug Adapter Protocol has a well-defined JSON-RPC message
    format with Content-Length framing. If you manage to violate it,
    congratulations — you've broken the debugger's debugger. The
    Content-Length header said 42 bytes, but the body contained 43.
    That one extra byte is the sound of protocol compliance weeping.
    """

    def __init__(self, message_type: str, detail: str) -> None:
        super().__init__(
            f"DAP protocol violation in '{message_type}': {detail}. "
            f"Content-Length and reality have diverged.",
            error_code="EFP-DAP4",
            context={"message_type": message_type, "detail": detail},
        )
        self.message_type = message_type
        self.detail = detail


# ----------------------------------------------------------------
# Intellectual Property Office Exceptions
# ----------------------------------------------------------------
# Because the FizzBuzz labels "Fizz", "Buzz", and "FizzBuzz" are
# valuable intellectual property that must be protected through a
# comprehensive trademark, patent, copyright, and dispute resolution
# framework. Every label is a potential trademark infringement.
# Every rule is a potential patent. Every output is a copyrightable
# work of modulo art. The IP Office exists to ensure that no
# FizzBuzz evaluation occurs without proper licensing, registration,
# and — if necessary — formal adjudication before the FizzBuzz
# Intellectual Property Tribunal.
# ----------------------------------------------------------------


class IPOfficeError(FizzBuzzError):
    """Base exception for all Intellectual Property Office errors.

    The FizzBuzz IP Office maintains a comprehensive registry of
    trademarks, patents, and copyrights covering every conceivable
    aspect of divisibility-based string substitution. When you
    attempt to use the label "Fizz" without proper trademark
    clearance, or implement a modulo-3 rule without licensing the
    patent, this exception hierarchy is what stands between you
    and IP anarchy.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "EFP-IP00"),
            context=kwargs.get("context", {}),
        )


class TrademarkViolationError(IPOfficeError):
    """Raised when a label infringes on a registered FizzBuzz trademark.

    The FizzBuzz Trademark Registry contains marks that have been
    registered through a rigorous application process involving
    phonetic similarity analysis (Soundex + Metaphone), visual
    inspection, and a mandatory 30-day opposition period during
    which no one objects because this is a FizzBuzz program.
    Attempting to use a confusingly similar label — say, "Fhyzz"
    when "Fizz" is already registered — triggers this exception
    and a sternly worded cease-and-desist from the Tribunal.
    """

    def __init__(self, mark: str, conflicting_mark: str, similarity: float) -> None:
        super().__init__(
            f"Trademark violation: '{mark}' is confusingly similar to "
            f"registered mark '{conflicting_mark}' (similarity: {similarity:.2%}). "
            f"Cease and desist immediately.",
            error_code="EFP-IP01",
            context={"mark": mark, "conflicting_mark": conflicting_mark, "similarity": similarity},
        )
        self.mark = mark
        self.conflicting_mark = conflicting_mark
        self.similarity = similarity


class PatentInfringementError(IPOfficeError):
    """Raised when a rule infringes on a granted FizzBuzz patent.

    The FizzBuzz Patent Office examines each rule for novelty (is it
    truly new?), non-obviousness (would a person having ordinary
    skill in the art of modulo arithmetic find it obvious?), and
    utility (does it actually produce output for at least one
    integer?). If your rule fails any of these tests, it is either
    rejected or, worse, found to infringe on an existing patent.
    The prior art database is extensive: {3: "Fizz"} was patented
    in the Before Times.
    """

    def __init__(self, rule_description: str, patent_id: str, reason: str) -> None:
        super().__init__(
            f"Patent infringement: rule '{rule_description}' infringes on "
            f"patent {patent_id}: {reason}. "
            f"The patent holder's attorneys have been notified.",
            error_code="EFP-IP02",
            context={"rule_description": rule_description, "patent_id": patent_id, "reason": reason},
        )
        self.rule_description = rule_description
        self.patent_id = patent_id
        self.reason = reason


class CopyrightInfringementError(IPOfficeError):
    """Raised when a work infringes on a registered FizzBuzz copyright.

    Every FizzBuzz output sequence is a copyrightable work of
    applied mathematics. The Copyright Registry maintains records
    of all registered works, their originality scores (computed via
    Levenshtein distance from existing works), and their licensing
    terms. Copying someone else's "1, 2, Fizz, 4, Buzz" sequence
    without attribution is not just bad form — it's a violation of
    the FizzBuzz Intellectual Property Act of 2026.
    """

    def __init__(self, work_title: str, original_work_id: str, similarity: float) -> None:
        super().__init__(
            f"Copyright infringement: work '{work_title}' is {similarity:.0%} similar to "
            f"registered work {original_work_id}. "
            f"The DMCA takedown notice is being prepared.",
            error_code="EFP-IP03",
            context={"work_title": work_title, "original_work_id": original_work_id, "similarity": similarity},
        )
        self.work_title = work_title
        self.original_work_id = original_work_id
        self.similarity = similarity


# ============================================================================
# Distributed Lock Manager (FizzLock) Exceptions
# ============================================================================


class DistributedLockError(FizzBuzzError):
    """Base exception for all Distributed Lock Manager errors.

    The FizzLock subsystem coordinates concurrent access to shared
    FizzBuzz evaluation resources across the full five-level hierarchy:
    platform, namespace, subsystem, number, and field. When the lock
    manager encounters a condition that prevents safe concurrent
    access — be it a deadlock cycle, a lease expiration, or a failed
    acquisition — this exception hierarchy ensures that the failure
    mode is precisely classified and actionable.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "EFP-7000"),
            context=kwargs.get("context", {}),
        )


class LockAcquisitionTimeoutError(DistributedLockError):
    """Raised when a lock acquisition exceeds the configured timeout.

    The requesting transaction waited for the specified duration but
    the conflicting holder did not release the resource. This may
    indicate a long-running evaluation, a stalled middleware pipeline,
    or a subsystem that has entered a state of contemplative paralysis
    regarding whether 15 is Fizz, Buzz, or FizzBuzz.
    """

    def __init__(self, resource: str, mode: str, timeout_ms: float, transaction_id: str) -> None:
        super().__init__(
            f"Lock acquisition timed out after {timeout_ms:.0f}ms: "
            f"resource='{resource}' mode={mode} txn={transaction_id}. "
            f"The holder has not released the resource within the deadline.",
            error_code="EFP-7001",
            context={
                "resource": resource,
                "mode": mode,
                "timeout_ms": timeout_ms,
                "transaction_id": transaction_id,
            },
        )
        self.resource = resource
        self.mode = mode
        self.timeout_ms = timeout_ms
        self.transaction_id = transaction_id


class LockDeadlockDetectedError(DistributedLockError):
    """Raised when Tarjan's SCC algorithm detects a deadlock cycle.

    A cycle in the wait-for graph has been identified, meaning two or
    more transactions are mutually waiting for resources held by each
    other. The youngest transaction in the cycle (by timestamp) is
    selected as the victim and aborted to break the cycle. This is the
    standard youngest-first victim selection policy, which minimizes
    wasted work under the assumption that younger transactions have
    invested less computational effort.
    """

    def __init__(self, cycle: list[str], victim: str) -> None:
        cycle_str = " -> ".join(cycle)
        super().__init__(
            f"Deadlock detected: cycle=[{cycle_str}]. "
            f"Victim selected: {victim} (youngest-first policy). "
            f"The victim transaction will be aborted to break the cycle.",
            error_code="EFP-7002",
            context={"cycle": cycle, "victim": victim},
        )
        self.cycle = cycle
        self.victim = victim


class LockTransactionAbortedError(DistributedLockError):
    """Raised when a transaction is aborted by the wait policy.

    Under the wait-die policy, a younger transaction that encounters
    a conflict with an older holder is immediately aborted rather than
    risking cycle formation. Under wound-wait, an older transaction
    forcibly aborts (wounds) a younger holder. In either case, the
    aborted transaction must release all its locks and retry.
    """

    def __init__(self, transaction_id: str, reason: str) -> None:
        super().__init__(
            f"Transaction {transaction_id} aborted: {reason}. "
            f"All locks held by this transaction have been released. "
            f"The transaction should be retried with a new identifier.",
            error_code="EFP-7003",
            context={"transaction_id": transaction_id, "reason": reason},
        )
        self.transaction_id = transaction_id
        self.reason = reason


class LockLeaseExpiredError(DistributedLockError):
    """Raised when a lock's lease expires before voluntary release.

    The lease manager has determined that the lock holder exceeded its
    time-to-live without renewing the lease. The lock has been forcibly
    revoked and the fencing token invalidated. Any subsequent operations
    by the former holder will be rejected by downstream subsystems that
    compare fencing tokens.
    """

    def __init__(self, resource: str, transaction_id: str, fencing_token: int) -> None:
        super().__init__(
            f"Lease expired: resource='{resource}' txn={transaction_id} "
            f"token={fencing_token}. The lock has been forcibly released. "
            f"Operations with this fencing token will be rejected.",
            error_code="EFP-7004",
            context={
                "resource": resource,
                "transaction_id": transaction_id,
                "fencing_token": fencing_token,
            },
        )
        self.resource = resource
        self.transaction_id = transaction_id
        self.fencing_token = fencing_token


# ============================================================
# Change Data Capture (CDC) Exceptions (EFP-CD00 through EFP-CD03)
# ============================================================


class CDCError(FizzBuzzError):
    """Base exception for the Change Data Capture subsystem.

    All CDC-specific failures derive from this class to enable
    targeted error handling at the pipeline, relay, and sink layers.
    Downstream consumers depend on structured CDC exceptions to
    distinguish transient relay failures from permanent schema
    incompatibilities.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CD00"),
            context=kwargs.pop("context", {}),
        )


class CDCSchemaValidationError(CDCError):
    """Raised when a change event fails schema validation.

    Every change event must conform to the schema registered for its
    subsystem in the CDCSchemaRegistry. When a field is missing, has
    an unexpected type, or the schema version is incompatible, this
    exception is raised to prevent malformed events from propagating
    through the outbox relay to downstream sinks.
    """

    def __init__(self, subsystem: str, reason: str) -> None:
        super().__init__(
            f"Schema validation failed for subsystem '{subsystem}': {reason}. "
            f"The event has been rejected and will not enter the outbox.",
            error_code="EFP-CD01",
            context={"subsystem": subsystem, "reason": reason},
        )
        self.subsystem = subsystem
        self.reason = reason


class CDCOutboxRelayError(CDCError):
    """Raised when the outbox relay fails to deliver events to sinks.

    The outbox pattern guarantees at-least-once delivery by persisting
    events before forwarding them. When the relay sweep encounters a
    sink failure, this exception captures which sink failed and how
    many events remain undelivered, enabling retry logic and dead-letter
    queue escalation.
    """

    def __init__(self, sink_name: str, pending_count: int) -> None:
        super().__init__(
            f"Outbox relay failed for sink '{sink_name}': "
            f"{pending_count} event(s) remain undelivered. "
            f"The relay will retry on the next sweep cycle.",
            error_code="EFP-CD02",
            context={"sink_name": sink_name, "pending_count": pending_count},
        )
        self.sink_name = sink_name
        self.pending_count = pending_count


class CDCSinkError(CDCError):
    """Raised when a sink connector fails to process a change event.

    Individual sinks may fail due to capacity limits, serialization
    errors, or downstream unavailability. This exception identifies
    the failing sink and the event that triggered the failure,
    allowing the relay to mark the event for retry or dead-letter
    routing.
    """

    def __init__(self, sink_name: str, event_id: str, reason: str) -> None:
        super().__init__(
            f"Sink '{sink_name}' failed to process event '{event_id}': {reason}.",
            error_code="EFP-CD03",
            context={
                "sink_name": sink_name,
                "event_id": event_id,
                "reason": reason,
            },
        )
        self.sink_name = sink_name
        self.event_id = event_id
        self.reason = reason


# ================================================================
# Billing & Revenue Recognition Exceptions (EFP-BL00 through EFP-BL04)
# ================================================================
# The financial backbone of the Enterprise FizzBuzz Platform demands
# its own exception hierarchy. When subscription billing fails,
# revenue recognition stalls, or a dunning cycle escalates to
# cancellation, these exceptions ensure the platform responds with
# the same gravity that a Fortune 500 CFO would expect from their
# accounts receivable department — except the accounts receivable
# is tracking FizzBuzz evaluations denominated in FizzBucks.
# ================================================================


class SubscriptionBillingError(FizzBuzzError):
    """Base exception for all subscription billing and revenue recognition failures.

    The financial layer of the Enterprise FizzBuzz Platform is held to
    the highest standards of accounting integrity. When a billing
    operation fails, this exception provides the foundation for
    structured error handling across subscription management, usage
    metering, invoice generation, dunning, and ASC 606 revenue
    recognition workflows.

    Note: This is distinct from BillingError(FBaaSError) which handles
    the FBaaS simulated payment processor. SubscriptionBillingError
    governs the ASC 606 revenue recognition and dunning lifecycle.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-BL00"),
            context=kwargs.pop("context", {}),
        )


class QuotaExceededError(SubscriptionBillingError):
    """Raised when a tenant exceeds their FizzOps quota for the billing period.

    Free-tier tenants receive a hard quota of 100 FizzOps per billing
    cycle. When this limit is reached, all subsequent evaluation requests
    are rejected until the next billing period begins or the tenant
    upgrades to a paid tier. This is the billing equivalent of
    "you must be this tall to ride" — except the ride is modulo
    arithmetic and the height requirement is denominated in FizzOps.
    """

    def __init__(self, tenant_id: str, quota: int, used: int) -> None:
        super().__init__(
            f"Tenant '{tenant_id}' has exhausted their FizzOps quota: "
            f"{used}/{quota} FizzOps consumed. Upgrade to a paid tier "
            f"or wait for the next billing cycle.",
            error_code="EFP-BL01",
            context={"tenant_id": tenant_id, "quota": quota, "used": used},
        )
        self.tenant_id = tenant_id
        self.quota = quota
        self.used = used


class ContractValidationError(SubscriptionBillingError):
    """Raised when a subscription contract fails ASC 606 Step 1 validation.

    A contract must have commercial substance, identifiable rights,
    payment terms, and an approved status before it can be recognized
    under ASC 606. If any of these criteria are not met, revenue
    recognition cannot proceed — and neither can the FizzBuzz
    evaluation pipeline, because compliance waits for no modulo.
    """

    def __init__(self, contract_id: str, reason: str) -> None:
        super().__init__(
            f"Contract '{contract_id}' failed ASC 606 Step 1 validation: {reason}.",
            error_code="EFP-BL02",
            context={"contract_id": contract_id, "reason": reason},
        )
        self.contract_id = contract_id
        self.reason = reason


class RevenueRecognitionError(SubscriptionBillingError):
    """Raised when the ASC 606 five-step revenue recognition process fails.

    Revenue recognition is a sacred ritual governed by FASB Topic 606.
    When any of the five steps — identify contract, identify obligations,
    determine price, allocate by SSP, recognize revenue — encounters an
    inconsistency, this exception halts the process to prevent misstated
    financials. The SEC does not look kindly upon incorrectly recognized
    FizzBuzz subscription revenue, even when denominated in FizzBucks.
    """

    def __init__(self, contract_id: str, step: int, reason: str) -> None:
        super().__init__(
            f"ASC 606 Step {step} failed for contract '{contract_id}': {reason}.",
            error_code="EFP-BL03",
            context={"contract_id": contract_id, "step": step, "reason": reason},
        )
        self.contract_id = contract_id
        self.step = step
        self.reason = reason


class DunningEscalationError(SubscriptionBillingError):
    """Raised when the dunning process escalates beyond recoverable states.

    The dunning state machine progresses through increasingly urgent
    collection phases: active -> past_due -> grace_period -> suspended
    -> cancelled. When a contract reaches the terminal 'cancelled' state
    after exhausting all 7 retry attempts across 28 days, this exception
    signals that involuntary churn has occurred. The FizzBuzz evaluations
    that were once so lovingly computed are now orphaned receivables on
    a balance sheet that nobody reads.
    """

    def __init__(self, contract_id: str, current_state: str, retry_count: int) -> None:
        super().__init__(
            f"Dunning escalation for contract '{contract_id}': "
            f"reached terminal state '{current_state}' after {retry_count} retries. "
            f"Involuntary churn has occurred.",
            error_code="EFP-BL04",
            context={
                "contract_id": contract_id,
                "current_state": current_state,
                "retry_count": retry_count,
            },
        )
        self.contract_id = contract_id
        self.current_state = current_state
        self.retry_count = retry_count



# ====================================================================
# Observability Correlation Engine Exceptions (EFP-OC00 .. EFP-OC03)
# ====================================================================

class ObservabilityCorrelationError(FizzBuzzError):
    """Base exception for the FizzCorr Observability Correlation Engine.

    When the system responsible for correlating your traces, logs, and
    metrics itself fails, you have achieved a level of meta-observability
    failure that most SRE teams can only hallucinate about during
    incident retrospectives. The correlation of correlations has
    become uncorrelatable. Page someone.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-OC00"),
            context=kwargs.pop("context", {}),
        )


class CorrelationStrategyError(ObservabilityCorrelationError):
    """Raised when a correlation strategy fails to produce a result.

    The engine attempted to correlate observability signals using a
    specific strategy (ID-based, temporal, or causal) and the strategy
    itself experienced a failure. This is the observability equivalent
    of the fire department catching fire — technically possible,
    deeply ironic, and requiring immediate escalation.
    """

    def __init__(self, strategy: str, reason: str) -> None:
        super().__init__(
            f"Correlation strategy '{strategy}' failed: {reason}",
            error_code="EFP-OC01",
            context={"strategy": strategy, "reason": reason},
        )
        self.strategy = strategy
        self.reason = reason


class CorrelationAnomalyDetectionError(ObservabilityCorrelationError):
    """Raised when the anomaly detector encounters an unprocessable signal.

    The anomaly detector — designed to find anomalies in your FizzBuzz
    observability data — has itself become anomalous. The irony is not
    lost on the engineering team. It is, however, lost on the detector,
    which lacks the self-awareness to appreciate the situation.
    """

    def __init__(self, detector_type: str, reason: str) -> None:
        super().__init__(
            f"Anomaly detector '{detector_type}' failed: {reason}",
            error_code="EFP-OC02",
            context={"detector_type": detector_type, "reason": reason},
        )
        self.detector_type = detector_type
        self.reason = reason


class SignalIngestionError(ObservabilityCorrelationError):
    """Raised when a raw observability signal cannot be normalized.

    The ingestion pipeline received a signal (trace, log, or metric)
    that could not be normalized into the canonical ObservabilityEvent
    format. This typically means the signal was malformed, missing
    required fields, or originated from a subsystem that has gone
    sufficiently rogue to emit data outside the agreed-upon schema.
    In a FizzBuzz platform, this is a crisis of existential proportions.
    """

    def __init__(self, signal_type: str, reason: str) -> None:
        super().__init__(
            f"Failed to ingest {signal_type} signal: {reason}",
            error_code="EFP-OC03",
            context={"signal_type": signal_type, "reason": reason},
        )
        self.signal_type = signal_type
        self.reason = reason


class JITCompilationError(FizzBuzzError):
    """Base exception for all JIT Compilation errors.

    When the runtime code generation subsystem — designed to accelerate
    FizzBuzz evaluation by compiling modulo arithmetic into native Python
    closures through an SSA intermediate representation with four
    optimization passes — encounters a failure, it raises this exception.
    The irony of JIT-compiling a program that already runs in microseconds
    is not lost on the engineering team. It is, however, lost on the JIT
    compiler, which lacks the self-awareness to question its own existence.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-JIT00"),
            context=kwargs.pop("context", {}),
        )


class JITTraceRecordingError(JITCompilationError):
    """Raised when trace recording fails during profiling.

    The trace recorder attempted to capture a hot execution path through
    the FizzBuzz evaluation pipeline, but the path proved too elusive,
    too branchy, or too existentially complex to linearize into an SSA
    trace. This is the JIT equivalent of trying to photograph a ghost:
    you know the execution happened, but you cannot prove it.
    """

    def __init__(self, trace_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to record trace '{trace_id}': {reason}. "
            f"The hot path has gone cold.",
            error_code="EFP-JIT01",
            context={"trace_id": trace_id, "reason": reason},
        )
        self.trace_id = trace_id
        self.reason = reason


class JITOptimizationError(JITCompilationError):
    """Raised when an SSA optimization pass encounters an invalid state.

    One of the four sacred optimization passes (Constant Folding, Dead
    Code Elimination, Guard Hoisting, or Type Specialization) has
    encountered an SSA instruction graph that violates its preconditions.
    Perhaps a variable was assigned twice, perhaps a phi function appeared
    in a linear trace, or perhaps the optimizer simply lost faith in the
    mathematical certainty of modulo arithmetic. Regardless, the
    optimization pipeline has been halted to preserve correctness.
    """

    def __init__(self, pass_name: str, instruction: str, reason: str) -> None:
        super().__init__(
            f"Optimization pass '{pass_name}' failed on instruction '{instruction}': "
            f"{reason}. The optimizer is experiencing an existential crisis.",
            error_code="EFP-JIT02",
            context={"pass_name": pass_name, "instruction": instruction, "reason": reason},
        )
        self.pass_name = pass_name
        self.instruction = instruction
        self.reason = reason


class JITGuardFailureError(JITCompilationError):
    """Raised when a compiled trace guard check fails at runtime.

    A guard inserted during trace compilation has detected that the
    runtime conditions no longer match the assumptions made during
    recording. This triggers an On-Stack Replacement (OSR) fallback
    to the interpreted path. The compiled code, once so confident in
    its optimized assumptions, must now admit defeat and hand control
    back to the interpreter. This is the JIT equivalent of a confident
    prediction meeting cold, hard reality.
    """

    def __init__(self, guard_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Guard '{guard_id}' failed: expected {expected}, got {actual}. "
            f"Falling back to interpreted path via OSR.",
            error_code="EFP-JIT03",
            context={"guard_id": guard_id, "expected": expected, "actual": actual},
        )
        self.guard_id = guard_id
        self.expected = expected
        self.actual = actual


# ============================================================
# FizzCap — Capability-Based Security Exceptions
# ============================================================
# When your object-capability model encounters a violation of the
# fundamental security invariants that protect FizzBuzz evaluation
# from unauthorized access, confused deputies, capability forgery,
# and the thermodynamic inevitability of authority amplification.
# ============================================================


class CapabilitySecurityError(FizzBuzzError):
    """Base exception for all capability-based security failures.

    Raised when the FizzCap security model encounters a violation of
    its core invariants. All capability exceptions inherit from this
    class, forming a sub-hierarchy that mirrors the layered nature of
    the capability model itself: mint → attenuation → delegation →
    verification → confused deputy prevention.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CAP00"),
            context=kwargs.pop("context", {}),
        )


class CapabilityVerificationError(CapabilitySecurityError):
    """Raised when a capability token fails verification.

    A capability has been presented that either has an invalid HMAC-SHA256
    signature, has been revoked, grants access to the wrong resource, or
    lacks the required operation. The confused deputy guard has done its
    job: it checked the REQUEST's capability, not the caller's ambient
    authority, and found it wanting.

    This is the security equivalent of presenting an expired coupon at
    a grocery store, except the coupon is for FizzBuzz evaluation rights
    and the grocery store is a mission-critical enterprise platform.
    """

    def __init__(self, cap_id: str, reason: str) -> None:
        super().__init__(
            f"Capability '{cap_id}' failed verification: {reason}",
            error_code="EFP-CAP01",
            context={"cap_id": cap_id, "reason": reason},
        )
        self.cap_id = cap_id
        self.reason = reason


class CapabilityAmplificationError(CapabilitySecurityError):
    """Raised when an attenuation attempt would broaden authority.

    The Second Law of Capability Thermodynamics has been violated:
    someone attempted to derive a capability with MORE authority than
    its parent. This is the capability equivalent of trying to withdraw
    more money than your account balance — except instead of money,
    it's the right to evaluate whether 15 is FizzBuzz.

    Attenuation is monotonic: authority can only DECREASE through
    delegation. Adding operations not present in the parent, or removing
    constraints that the parent enforces, constitutes amplification and
    is categorically forbidden.
    """

    def __init__(self, parent_cap_id: str, reason: str) -> None:
        super().__init__(
            f"Cannot amplify capability '{parent_cap_id}': {reason}",
            error_code="EFP-CAP02",
            context={"parent_cap_id": parent_cap_id, "reason": reason},
        )
        self.parent_cap_id = parent_cap_id
        self.reason = reason


class CapabilityRevocationError(CapabilitySecurityError):
    """Raised when a capability revocation operation fails.

    A cascade revocation through the delegation graph has encountered
    an inconsistency — perhaps a circular delegation (which should be
    impossible in a DAG, but enterprise software finds a way), or
    a node that cannot be located in the graph.

    When the revocation system itself fails, the security posture of
    the entire FizzBuzz platform is compromised. This is the capability
    equivalent of the fire alarm catching fire.
    """

    def __init__(self, cap_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to revoke capability '{cap_id}': {reason}",
            error_code="EFP-CAP03",
            context={"cap_id": cap_id, "reason": reason},
        )
        self.cap_id = cap_id
        self.reason = reason


# ============================================================
# FizzOTel — OpenTelemetry-Compatible Distributed Tracing Errors
# ============================================================


class OTelError(FizzBuzzError):
    """Base exception for all FizzOTel distributed tracing errors.

    The OpenTelemetry specification defines a comprehensive error
    taxonomy for telemetry pipelines. This exception hierarchy mirrors
    that taxonomy, because when your FizzBuzz tracing subsystem fails,
    you need enterprise-grade error categorization to understand whether
    the failure was in sampling, span lifecycle, or export — even though
    the fix is always "restart the CLI."
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code="EFP-OT00",
            context=kwargs,
        )


class OTelSpanError(OTelError):
    """Raised when a span lifecycle operation fails.

    This includes invalid trace IDs, malformed W3C traceparent headers,
    attempts to end an already-ended span, or any other violation of
    the span state machine. In production OpenTelemetry, these errors
    are silently swallowed. In Enterprise FizzBuzz, they are promoted
    to full exceptions because silent failures are anathema to our
    zero-tolerance-for-ambiguity policy.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.error_code = "EFP-OT01"


class OTelExportError(OTelError):
    """Raised when span export fails.

    Export failures can occur when the OTLP JSON serialization encounters
    an unserializable attribute, when the Zipkin format conversion fails,
    or when the ConsoleExporter runs out of terminal width. Each of these
    scenarios is equally catastrophic for FizzBuzz observability.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.error_code = "EFP-OT02"


class OTelSamplingError(OTelError):
    """Raised when the probabilistic sampler encounters an invalid state.

    A sampling rate outside [0.0, 1.0] would violate the fundamental
    axioms of probability theory, and the Enterprise FizzBuzz Platform
    refuses to operate in a universe where P(sample) > 1.0 or P(sample) < 0.0.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.error_code = "EFP-OT03"


# ============================================================
# FizzWAL — Write-Ahead Intent Log Exceptions
# ============================================================
# The ARIES recovery protocol demands that every failure mode in
# the WAL subsystem is taxonomised with the same rigour as a
# database kernel. A FizzBuzz platform that cannot survive a
# simulated crash mid-evaluation is a FizzBuzz platform that
# has no business running in production.
# ============================================================


class WriteAheadLogError(FizzBuzzError):
    """Base exception for all Write-Ahead Intent Log failures.

    Any anomaly in the WAL subsystem — from log corruption to
    sequence-number overflow — inherits from this class so that
    the crash-recovery engine can catch a single base type and
    route the incident to the appropriate ARIES recovery phase.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code="EFP-WAL00",
            context=kwargs,
        )


class IntentRollbackError(WriteAheadLogError):
    """Raised when an undo action fails during transaction rollback.

    The compensating action recorded in the intent log could not be
    applied. This is the WAL equivalent of a surgeon discovering
    that the undo-stitch instruction was written in Klingon. The
    transaction is left in a ROLLING_BACK state until a human
    (or a sufficiently motivated cron job) intervenes.
    """

    def __init__(self, transaction_id: str, intent_lsn: int, reason: str) -> None:
        self.transaction_id = transaction_id
        self.intent_lsn = intent_lsn
        FizzBuzzError.__init__(
            self,
            f"Rollback failed for transaction '{transaction_id}' at LSN {intent_lsn}: "
            f"{reason}. The compensating action could not be applied. "
            f"Manual intervention required — please consult the WAL recovery runbook.",
            error_code="EFP-WAL01",
            context={
                "transaction_id": transaction_id,
                "intent_lsn": intent_lsn,
                "reason": reason,
            },
        )


class CrashRecoveryError(WriteAheadLogError):
    """Raised when an ARIES recovery phase encounters an unrecoverable error.

    The three-phase recovery protocol (Analysis, Redo, Undo) has failed
    at a specific phase. This is the database-kernel equivalent of the
    black-box recorder itself catching fire. The recovery report will
    contain partial results up to the point of failure, which is more
    information than most FizzBuzz platforms provide about anything.
    """

    def __init__(self, phase: str, reason: str) -> None:
        self.phase = phase
        FizzBuzzError.__init__(
            self,
            f"ARIES crash recovery failed during {phase} phase: {reason}. "
            f"The WAL may be in an inconsistent state. Please restore from "
            f"the most recent checkpoint and retry recovery.",
            error_code="EFP-WAL02",
            context={"phase": phase, "reason": reason},
        )


class SavepointNotFoundError(WriteAheadLogError):
    """Raised when a rollback targets a savepoint that does not exist.

    The requested savepoint name was not found in the active transaction's
    savepoint stack. Either the savepoint was never created, was already
    released, or was consumed by a previous partial rollback. In any case,
    the intent log cannot rewind to a point in time that it has no record of,
    because even enterprise FizzBuzz respects causality.
    """

    def __init__(self, savepoint_name: str, transaction_id: str) -> None:
        self.savepoint_name = savepoint_name
        self.transaction_id = transaction_id
        FizzBuzzError.__init__(
            self,
            f"Savepoint '{savepoint_name}' not found in transaction '{transaction_id}'. "
            f"Available savepoints have either been released or were never created. "
            f"The WAL cannot rollback to a temporal coordinate that does not exist.",
            error_code="EFP-WAL03",
            context={
                "savepoint_name": savepoint_name,
                "transaction_id": transaction_id,
            },
        )


# =====================================================================
# FizzCRDT — Conflict-Free Replicated Data Types
# =====================================================================


class CRDTError(FizzBuzzError):
    """Base exception for all CRDT subsystem failures.

    Raised when the Conflict-Free Replicated Data Type engine encounters
    a condition that prevents it from fulfilling its sacred duty of
    ensuring Strong Eventual Consistency across the FizzBuzz cluster.
    The join-semilattice axioms (commutative, associative, idempotent)
    are inviolable; any violation is a cardinal sin against distributed
    systems theory.
    """

    def __init__(self, message: str) -> None:
        FizzBuzzError.__init__(
            self,
            f"CRDT subsystem error: {message}",
            error_code="EFP-CRDT00",
            context={},
        )


class CRDTMergeConflictError(CRDTError):
    """Raised when a CRDT merge operation encounters an irreconcilable state.

    This should, by the mathematical properties of CRDTs, be impossible.
    If you see this error, either the implementation is wrong, the laws
    of mathematics have changed, or someone has been manually editing
    CRDT state — all equally catastrophic scenarios.
    """

    def __init__(self, crdt_type: str, detail: str) -> None:
        self.crdt_type = crdt_type
        self.detail = detail
        FizzBuzzError.__init__(
            self,
            f"CRDT merge conflict in {crdt_type}: {detail}. "
            f"This violates the join-semilattice axioms and should be "
            f"mathematically impossible. Please check your axioms.",
            error_code="EFP-CRDT01",
            context={"crdt_type": crdt_type, "detail": detail},
        )


class CRDTCausalityViolationError(CRDTError):
    """Raised when a causal ordering constraint is violated.

    The vector clock detected an event that claims to have happened
    before another event, but the timestamps disagree. This is the
    distributed systems equivalent of a time travel paradox, and
    the CRDT engine refuses to participate in temporal contradictions.
    """

    def __init__(self, clock_a: str, clock_b: str) -> None:
        self.clock_a = clock_a
        self.clock_b = clock_b
        FizzBuzzError.__init__(
            self,
            f"Causality violation detected between vector clocks "
            f"{clock_a} and {clock_b}. The causal ordering of FizzBuzz "
            f"evaluations has been compromised. Lamport would be disappointed.",
            error_code="EFP-CRDT02",
            context={"clock_a": clock_a, "clock_b": clock_b},
        )


class CRDTReplicaDivergenceError(CRDTError):
    """Raised when replicas have diverged beyond recovery.

    Two replicas hold CRDT states that cannot be merged because one or
    both have been corrupted, or contain CRDTs of incompatible types
    under the same name. In a correctly operating system, anti-entropy
    rounds should always converge. Divergence indicates a fundamental
    breach of the replication protocol.
    """

    def __init__(self, replica_a: str, replica_b: str, crdt_name: str) -> None:
        self.replica_a = replica_a
        self.replica_b = replica_b
        self.crdt_name = crdt_name
        FizzBuzzError.__init__(
            self,
            f"Replicas '{replica_a}' and '{replica_b}' have irreconcilably "
            f"diverged on CRDT '{crdt_name}'. Anti-entropy has failed. "
            f"Strong Eventual Consistency can no longer be guaranteed.",
            error_code="EFP-CRDT03",
            context={
                "replica_a": replica_a,
                "replica_b": replica_b,
                "crdt_name": crdt_name,
            },
        )


# ============================================================
# FizzGrammar -- Formal Grammar & Parser Generator Exceptions
# ============================================================
# Noam Chomsky formalized the theory of formal grammars in 1956.
# Seventy years later, the Enterprise FizzBuzz Platform applies
# it to the problem of determining whether n % 3 == 0. These
# exceptions ensure that every grammar violation is reported
# with the gravity it deserves.
# ============================================================


class GrammarError(FizzBuzzError):
    """Base exception for all Formal Grammar & Parser Generator errors.

    Raised when the FizzGrammar subsystem encounters a condition that
    prevents it from analyzing, classifying, or generating parsers for
    a formal grammar specification. The grammar may be syntactically
    malformed, semantically ambiguous, or structurally incompatible
    with the target parser class. In any case, the platform cannot
    proceed with grammar-driven parsing until the issue is resolved.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-GR00"),
            context=kwargs.pop("context", {}),
        )


class GrammarSyntaxError(GrammarError):
    """Raised when a BNF/EBNF grammar specification is malformed.

    The grammar parser encountered a token sequence that does not
    conform to the meta-grammar of BNF/EBNF notation. This is the
    meta-level equivalent of a syntax error: the grammar that defines
    grammars has been violated. The irony is not lost on the platform.
    """

    def __init__(self, line: int, column: int, detail: str) -> None:
        self.line = line
        self.column = column
        self.detail = detail
        super().__init__(
            f"Grammar syntax error at line {line}, column {column}: {detail}. "
            f"The grammar specification itself has a grammar error.",
            error_code="EFP-GR01",
            context={"line": line, "column": column, "detail": detail},
        )


class GrammarConflictError(GrammarError):
    """Raised when a grammar has LL(1) conflicts that prevent deterministic parsing.

    Two or more production alternatives for the same non-terminal have
    overlapping FIRST sets, meaning the parser cannot decide which
    alternative to pursue based on a single lookahead token. The grammar
    is not LL(1). This is not necessarily a defect in the grammar --
    many useful grammars are not LL(1) -- but it means the generated
    parser must use backtracking rather than predictive parsing, which
    offends the sensibilities of anyone who has read the Dragon Book.
    """

    def __init__(self, non_terminal: str, conflicts: list[str]) -> None:
        self.non_terminal = non_terminal
        self.conflicts = conflicts
        super().__init__(
            f"LL(1) conflict for non-terminal '{non_terminal}': "
            f"overlapping FIRST sets in alternatives: {', '.join(conflicts)}. "
            f"The grammar requires more than one token of lookahead.",
            error_code="EFP-GR02",
            context={"non_terminal": non_terminal, "conflicts": conflicts},
        )


class GrammarParseError(GrammarError):
    """Raised when a generated parser encounters a syntax error in its input.

    The generated recursive-descent parser found a token that does not
    match any expected alternative at the current parse position. The
    input string is not in the language defined by the grammar. This is
    the intended purpose of parsing: to distinguish strings that belong
    to the language from strings that do not. The parser has done its job.
    The input has failed its audition.
    """

    def __init__(
        self, line: int, column: int, found: str, expected: list[str]
    ) -> None:
        self.line = line
        self.column = column
        self.found = found
        self.expected = expected
        super().__init__(
            f"Parse error at line {line}, column {column}: "
            f"found '{found}', expected one of: {', '.join(expected)}. "
            f"The input does not belong to this language.",
            error_code="EFP-GR03",
            context={
                "line": line,
                "column": column,
                "found": found,
                "expected": expected,
            },
        )


# =====================================================================
# FizzAlloc — Custom Memory Allocator Exceptions
# =====================================================================


class MemoryAllocatorError(FizzBuzzError):
    """Base exception for all FizzAlloc memory allocator errors.

    The custom memory allocator subsystem has encountered a condition
    that prevents it from fulfilling its contractual obligation to
    manage simulated memory for FizzBuzz evaluation artifacts. This
    is the root of the allocator exception hierarchy, from which all
    specific allocation failure modes descend.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-MA00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SlabExhaustedError(MemoryAllocatorError):
    """Raised when a slab has no free slots remaining for allocation.

    Every slot in the slab's free-list has been consumed. The slab
    is at 100% utilization. Further allocations of this object type
    cannot proceed until existing allocations are freed or additional
    slabs are provisioned. This is the memory allocator equivalent of
    a sold-out concert — demand has exceeded capacity, and no amount
    of standing in line will produce a ticket.
    """

    def __init__(self, slab_type: str, slab_capacity: int) -> None:
        self.slab_type = slab_type
        self.slab_capacity = slab_capacity
        super().__init__(
            f"Slab exhausted for type '{slab_type}': all {slab_capacity} slots "
            f"are allocated. No free slots remain in the free-list. "
            f"Consider increasing slab capacity or freeing existing allocations.",
            error_code="EFP-MA01",
            context={"slab_type": slab_type, "slab_capacity": slab_capacity},
        )


class ArenaOverflowError(MemoryAllocatorError):
    """Raised when an arena's bump pointer exceeds the arena's capacity.

    The arena allocator uses bump allocation — a pointer advances
    monotonically through a contiguous region. When the pointer reaches
    the end, the arena is full. Unlike slab allocation, individual
    arena allocations cannot be freed; the entire arena must be reset.
    This is by design: arenas trade individual deallocation for O(1)
    bulk reset, which is ideal for per-evaluation scratch memory.
    """

    def __init__(self, arena_size: int, requested: int, remaining: int) -> None:
        self.arena_size = arena_size
        self.requested = requested
        self.remaining = remaining
        super().__init__(
            f"Arena overflow: requested {requested} bytes but only {remaining} "
            f"of {arena_size} bytes remain. The bump pointer has reached the "
            f"end of the arena. Reset the arena to reclaim all space.",
            error_code="EFP-MA02",
            context={
                "arena_size": arena_size,
                "requested": requested,
                "remaining": remaining,
            },
        )


class GarbageCollectionError(MemoryAllocatorError):
    """Raised when the garbage collector encounters an unrecoverable state.

    The tri-generational mark-sweep-compact garbage collector has
    encountered a condition that prevents it from completing a
    collection cycle. This may indicate a corrupted object graph,
    a cycle in the root set, or a compaction failure. The GC is the
    last line of defense against unbounded memory growth, and its
    failure is a platform-level incident requiring immediate attention
    from the FizzBuzz Reliability Engineering on-call rotation.
    """

    def __init__(self, phase: str, detail: str) -> None:
        self.phase = phase
        self.detail = detail
        super().__init__(
            f"Garbage collection failure during '{phase}' phase: {detail}. "
            f"The collector cannot guarantee memory safety. Manual intervention "
            f"may be required.",
            error_code="EFP-MA03",
            context={"phase": phase, "detail": detail},
        )


# ============================================================
# FizzColumn — Columnar Storage Engine Exceptions
# ============================================================


class ColumnarStorageError(FizzBuzzError):
    """Base exception for all columnar storage engine errors.

    The columnar storage engine provides Parquet-style column-oriented
    storage with dictionary, RLE, and delta encoding for FizzBuzz
    evaluation results. When column operations fail — whether during
    encoding, row group management, or Parquet export — this hierarchy
    provides precise diagnostic information for the storage reliability
    engineering team.
    """

    def __init__(self, message: str, *, error_code: str = "EFP-CS00",
                 context: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ColumnEncodingError(ColumnarStorageError):
    """Raised when a column encoding or decoding operation fails.

    Each column chunk is encoded using one of four strategies: PLAIN,
    DICTIONARY, RLE (run-length encoding), or DELTA. Encoding failures
    may occur when the input data is incompatible with the selected
    encoding — for example, attempting delta encoding on non-numeric
    data, or dictionary encoding when the cardinality exceeds the
    dictionary size limit. The encoder selection algorithm samples the
    first 1024 values to choose the optimal encoding; this error
    indicates the sample was not representative of the full dataset.
    """

    def __init__(self, encoding: str, column_name: str, detail: str) -> None:
        self.encoding = encoding
        self.column_name = column_name
        self.detail = detail
        super().__init__(
            f"Column encoding failure: {encoding} encoding on column "
            f"'{column_name}': {detail}. The columnar storage engine cannot "
            f"persist this column chunk until the encoding issue is resolved.",
            error_code="EFP-CS01",
            context={
                "encoding": encoding,
                "column_name": column_name,
                "detail": detail,
            },
        )


class RowGroupError(ColumnarStorageError):
    """Raised when a row group operation violates structural invariants.

    Row groups are immutable collections of column chunks that share
    the same row count. Once sealed, a row group's dimensions are
    fixed — attempting to add columns with mismatched row counts, or
    modifying a sealed row group, triggers this error. Row groups are
    the fundamental unit of I/O parallelism in the columnar engine;
    their structural integrity is non-negotiable.
    """

    def __init__(self, row_group_id: int, detail: str) -> None:
        self.row_group_id = row_group_id
        self.detail = detail
        super().__init__(
            f"Row group {row_group_id} structural violation: {detail}. "
            f"Row groups are immutable once sealed. This invariant ensures "
            f"predicate pushdown correctness via zone maps.",
            error_code="EFP-CS02",
            context={"row_group_id": row_group_id, "detail": detail},
        )


class ParquetExportError(ColumnarStorageError):
    """Raised when the Parquet binary export process encounters a failure.

    The Parquet exporter writes a binary file with PAR1 magic bytes,
    schema metadata, encoded column chunks with offsets, and a footer.
    Export failures may occur due to I/O errors, schema inconsistencies,
    or corrupted column chunk data. The resulting file would not be
    readable by any Parquet-compatible reader, which is unacceptable
    for enterprise-grade FizzBuzz data archival.
    """

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(
            f"Parquet export failure to '{path}': {detail}. "
            f"The binary file may be incomplete or corrupted. "
            f"PAR1 magic byte integrity cannot be guaranteed.",
            error_code="EFP-CS03",
            context={"path": path, "detail": detail},
        )


# ============================================================
# MapReduce Framework Exceptions (EFP-MR00 through EFP-MR03)
# ============================================================
# Because distributed computation of FizzBuzz classifications
# demands the same fault tolerance guarantees as a multi-petabyte
# Hadoop cluster. If a mapper fails to evaluate 15 % 3, the
# entire job must be retried with speculative execution. Google
# published the MapReduce paper in 2004; twenty years later,
# we finally apply it to the problem it was always meant to solve.
# ============================================================


class MapReduceError(FizzBuzzError):
    """Base exception for all FizzReduce MapReduce framework errors.

    The MapReduce pipeline involves input splitting, parallel mapping,
    shuffle-and-sort, and reduction. Any failure in any of these
    phases warrants an exception that carries enough diagnostic
    context to reconstruct the failure scenario in a post-mortem.
    This is the root of the MapReduce exception hierarchy.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-MR00"),
            context=kwargs.pop("context", {}),
        )


class MapperError(MapReduceError):
    """Raised when a mapper task fails during FizzBuzz evaluation.

    A mapper is responsible for evaluating a split of the input range
    through the StandardRuleEngine and emitting (classification_key, 1)
    pairs. When a mapper fails — whether due to an invalid input split,
    a rule engine malfunction, or a cosmic ray flipping a bit in the
    modulo ALU — this exception captures the split ID, the offending
    number range, and the root cause. The JobTracker uses this to
    decide whether to retry, launch a speculative duplicate, or
    escalate to the FizzBuzz Incident Response Team.
    """

    def __init__(self, split_id: str, detail: str) -> None:
        self.split_id = split_id
        self.detail = detail
        super().__init__(
            f"Mapper failed on split '{split_id}': {detail}. "
            f"The mapper task has been marked as FAILED. The JobTracker "
            f"may launch a speculative replacement if straggler detection "
            f"thresholds have been exceeded.",
            error_code="EFP-MR01",
            context={"split_id": split_id, "detail": detail},
        )


class ReducerError(MapReduceError):
    """Raised when a reducer task fails during value aggregation.

    Reducers aggregate shuffled (key, [values]) groups into final
    classification counts. A reducer failure means the world will
    never know exactly how many numbers in the input range were
    classified as 'Fizz'. This is an unacceptable outcome for any
    enterprise with regulatory obligations around FizzBuzz accuracy.
    """

    def __init__(self, reducer_id: int, detail: str) -> None:
        self.reducer_id = reducer_id
        self.detail = detail
        super().__init__(
            f"Reducer {reducer_id} failed: {detail}. "
            f"Partial aggregation results have been discarded. "
            f"The job cannot produce a complete classification distribution.",
            error_code="EFP-MR02",
            context={"reducer_id": reducer_id, "detail": detail},
        )


class ShuffleError(MapReduceError):
    """Raised when the shuffle-and-sort phase encounters a failure.

    The shuffle phase is responsible for hash-partitioning mapper
    output by classification key across reducer slots. A shuffle
    failure could result in misrouted key-value pairs, meaning
    'Fizz' counts end up in the 'Buzz' reducer's partition. The
    implications for data integrity are catastrophic. In a real
    Hadoop cluster, this would trigger a full job restart. Here,
    it triggers this exception and a strongly-worded log message.
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(
            f"Shuffle-and-sort phase failed: {detail}. "
            f"Key-value partition integrity cannot be guaranteed. "
            f"All mapper outputs must be re-shuffled from scratch.",
            error_code="EFP-MR03",
            context={"detail": detail},
        )


# ============================================================
# FizzSchema — Consensus-Based Schema Evolution Exceptions
# ============================================================


class SchemaEvolutionError(FizzBuzzError):
    """Base exception for all schema evolution subsystem failures.

    Schema evolution is a mission-critical capability for any
    enterprise platform that takes data contracts seriously.
    Without rigorous schema versioning, backward compatibility
    enforcement, and consensus-based approval workflows, your
    FizzBuzz evaluation results could silently change shape
    between releases — an unacceptable violation of the Data
    Contract Governance Policy (DCGP-2024-Rev3).
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SE00"),
            context=kwargs.pop("context", {}),
        )


class SchemaCompatibilityError(SchemaEvolutionError):
    """Raised when a schema change violates the active compatibility mode.

    Compatibility violations are the schema evolution equivalent of
    a Geneva Convention breach. If you're adding a required field
    without a default value under BACKWARD compatibility mode, you
    are effectively declaring war on every downstream consumer that
    trusted your data contract. This exception ensures such acts of
    aggression are intercepted before they reach production.
    """

    def __init__(self, schema_name: str, from_version: int, to_version: int, violations: list[str]) -> None:
        self.schema_name = schema_name
        self.from_version = from_version
        self.to_version = to_version
        self.violations = violations
        super().__init__(
            f"Schema '{schema_name}' v{from_version}->v{to_version} compatibility check failed: "
            f"{len(violations)} violation(s) detected. "
            f"First violation: {violations[0] if violations else 'unknown'}",
            error_code="EFP-SE01",
            context={
                "schema_name": schema_name,
                "from_version": from_version,
                "to_version": to_version,
                "violations": violations,
            },
        )


class SchemaRegistrationError(SchemaEvolutionError):
    """Raised when a schema cannot be registered in the schema registry.

    The schema registry is the single source of truth for all data
    contracts in the enterprise. Registration failures can occur due
    to duplicate fingerprints, version conflicts, or consensus
    rejection by the Paxos approval committee. Each failure mode
    represents a distinct governance violation that must be
    investigated by the Schema Review Board before proceeding.
    """

    def __init__(self, schema_name: str, version: int, reason: str) -> None:
        self.schema_name = schema_name
        self.version = version
        self.reason = reason
        super().__init__(
            f"Failed to register schema '{schema_name}' v{version}: {reason}",
            error_code="EFP-SE02",
            context={
                "schema_name": schema_name,
                "version": version,
                "reason": reason,
            },
        )


class SchemaConsensusError(SchemaEvolutionError):
    """Raised when the Paxos consensus cluster fails to approve a schema change.

    Schema changes in the Enterprise FizzBuzz Platform are not
    unilateral decisions. They require majority approval from a
    5-node Paxos cluster, each node independently verifying
    compatibility constraints. If quorum cannot be reached —
    whether due to node failures, compatibility disagreements,
    or Byzantine behavior — the schema change is rejected.
    Democracy is non-negotiable, even for data contracts.
    """

    def __init__(self, schema_name: str, approvals: int, required: int, detail: str) -> None:
        self.schema_name = schema_name
        self.approvals = approvals
        self.required = required
        self.detail = detail
        super().__init__(
            f"Consensus failed for schema '{schema_name}': "
            f"{approvals}/{required} approvals (quorum not reached). {detail}",
            error_code="EFP-SE03",
            context={
                "schema_name": schema_name,
                "approvals": approvals,
                "required": required,
                "detail": detail,
            },
        )


# ============================================================
# Service Level Indicator Framework Exceptions (EFP-SLI*)
# ============================================================


# ================================================================
# Formal Model Checking Exceptions
# ================================================================
# Because ensuring the correctness of your FizzBuzz evaluation
# pipeline through manual testing is a relic of the pre-formal-
# methods era. Every stateful subsystem in the platform — from
# the MESI cache coherence protocol to the circuit breaker state
# machine — demands mathematical proof of correctness via temporal
# logic model checking. These exceptions signal failures in the
# verification apparatus itself, which is the meta-level equivalent
# of "quis custodiet ipsos custodes?" applied to software.
# ================================================================


class ModelCheckError(FizzBuzzError):
    """Base exception for all Formal Model Checking errors.

    Raised when the FizzCheck model checking subsystem encounters
    a condition that prevents it from verifying temporal properties
    of a Kripke structure. The model may be malformed, the property
    may be unsatisfiable, or the state space may exceed resource
    limits. In any case, the platform cannot certify the correctness
    of its own subsystems, which means every subsequent FizzBuzz
    evaluation is proceeding without formal verification — a state
    of affairs that would be unacceptable in any safety-critical
    modulo arithmetic application.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-MC00"),
            context=kwargs.pop("context", {}),
        )


class ModelCheckPropertyViolationError(ModelCheckError):
    """Raised when a temporal property is violated during model checking.

    The model checker has explored the state space of a Kripke structure
    and discovered a reachable state (or infinite path) that falsifies
    the specified temporal logic formula. A counterexample trace has
    been generated, providing a step-by-step demonstration of how the
    system can reach the violating state from its initial configuration.

    This is the formal methods equivalent of catching a bug, except
    instead of "it crashed in production," you get a mathematically
    rigorous proof that your MESI cache protocol can reach an invalid
    state. Whether this makes you feel better or worse about the bug
    depends on your relationship with formal verification.
    """

    def __init__(self, property_name: str, trace_length: int) -> None:
        self.property_name = property_name
        self.trace_length = trace_length
        super().__init__(
            f"Temporal property '{property_name}' violated: "
            f"counterexample trace of {trace_length} states found. "
            f"The system can reach a state that falsifies the specification.",
            error_code="EFP-MC01",
            context={
                "property_name": property_name,
                "trace_length": trace_length,
            },
        )


class ModelCheckStateSpaceError(ModelCheckError):
    """Raised when the state space exceeds exploration limits.

    The model checker has encountered more states than the configured
    maximum during BFS/DFS exploration. This typically indicates that
    the model has an unexpectedly large (or infinite) state space,
    which can occur when variable domains are unbounded, transitions
    create new states without converging, or the model simply
    represents a system more complex than your FizzBuzz platform
    has any business modeling.

    The state space explosion problem is the central challenge of
    model checking. For a FizzBuzz platform, the fact that we've
    hit this limit is simultaneously impressive and deeply concerning.
    """

    def __init__(self, states_explored: int, max_states: int) -> None:
        self.states_explored = states_explored
        self.max_states = max_states
        super().__init__(
            f"State space explosion: explored {states_explored} states, "
            f"exceeding the maximum of {max_states}. "
            f"Consider enabling symmetry reduction or partial order reduction.",
            error_code="EFP-MC02",
            context={
                "states_explored": states_explored,
                "max_states": max_states,
            },
        )


class ModelCheckInvalidSpecError(ModelCheckError):
    """Raised when a temporal logic specification is malformed.

    The temporal property provided to the model checker does not
    form a valid LTL formula. This could mean nested operators
    are applied to non-boolean predicates, atomic propositions
    reference variables not present in the model, or the formula
    structure violates the grammar of temporal logic.

    Writing correct temporal logic specifications is notoriously
    difficult. Surveys show that even experienced formal methods
    practitioners get LTL formulas wrong approximately 37% of the
    time. For a FizzBuzz platform, the bar should theoretically
    be lower, but the specification language remains unforgiving.
    """

    def __init__(self, spec: str, reason: str) -> None:
        self.spec = spec
        self.reason = reason
        super().__init__(
            f"Invalid temporal specification '{spec}': {reason}. "
            f"The property does not form a well-typed LTL formula.",
            error_code="EFP-MC03",
            context={"spec": spec, "reason": reason},
        )


class SLIError(FizzBuzzError):
    """Base exception for the Service Level Indicator Framework.

    The SLI Framework monitors real-time reliability indicators for
    every FizzBuzz evaluation. When the framework itself encounters
    an error, it raises this exception to signal that the system
    responsible for measuring whether your modulo operations meet
    their Service Level Objectives has itself failed to meet its
    own implicit Service Level Objective of functioning correctly.
    This is the observability paradox: if the observer is broken,
    are the observations still valid? The answer is no, and this
    exception is the proof.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SLI0"),
            context=kwargs.pop("context", {}),
        )


class SLIDefinitionError(SLIError):
    """Raised when an SLI definition is invalid or malformed.

    Every Service Level Indicator must have a name, a type, a target
    SLO expressed as a fraction between 0 and 1, and a measurement
    window. If any of these are missing, contradictory, or physically
    impossible (e.g., a target SLO of 1.5, which would require your
    FizzBuzz evaluations to be 150% correct — a feat not even the
    most over-engineered enterprise platform can achieve), this
    exception is raised to prevent the SLI from polluting the
    reliability signal with nonsensical measurements.
    """

    def __init__(self, sli_name: str, field: str, reason: str) -> None:
        self.sli_name = sli_name
        self.field = field
        self.reason = reason
        super().__init__(
            f"Invalid SLI definition '{sli_name}': field '{field}' — {reason}",
            error_code="EFP-SLI1",
            context={"sli_name": sli_name, "field": field, "reason": reason},
        )


class SLIBudgetExhaustionError(SLIError):
    """Raised when an SLI's error budget has been fully consumed.

    The error budget is the mathematical embodiment of forgiveness:
    a finite allowance of failures that the system may incur before
    breaching its Service Level Objective. When this budget reaches
    zero, forgiveness is over. Every subsequent FizzBuzz evaluation
    failure is a direct SLO breach, an audit event, and a line item
    in the post-incident review. This exception signals that the
    system has exhausted its right to fail and must now operate
    with perfect reliability — or face the consequences of a
    budget tier of EXHAUSTED.
    """

    def __init__(self, sli_name: str, burn_rate: float) -> None:
        self.sli_name = sli_name
        self.burn_rate = burn_rate
        super().__init__(
            f"Error budget exhausted for SLI '{sli_name}': "
            f"burn rate {burn_rate:.2f}x sustainable rate. "
            f"All remaining evaluations must succeed.",
            error_code="EFP-SLI2",
            context={"sli_name": sli_name, "burn_rate": burn_rate},
        )


class SLIFeatureGateError(SLIError):
    """Raised when an SLI feature gate blocks an operation.

    The SLI Feature Gate is the circuit breaker between reliability
    and ambition. When the error budget drops below configured
    thresholds, the feature gate intervenes to prevent further
    budget consumption by blocking risky operations: chaos
    experiments are suspended, feature flag rollouts are paused,
    and deployments are frozen. This exception is raised when an
    operation attempts to proceed despite the gate's prohibition,
    which is the reliability engineering equivalent of running a
    red light during a traffic safety audit.
    """

    def __init__(self, operation: str, budget_remaining: float, threshold: float) -> None:
        self.operation = operation
        self.budget_remaining = budget_remaining
        self.threshold = threshold
        super().__init__(
            f"Feature gate blocked '{operation}': "
            f"budget remaining {budget_remaining:.1%} < threshold {threshold:.1%}. "
            f"Operation suspended until budget recovers.",
            error_code="EFP-SLI3",
            context={
                "operation": operation,
                "budget_remaining": budget_remaining,
                "threshold": threshold,
            },
        )


# ============================================================
# Reverse Proxy & Load Balancer Exceptions
# ============================================================
# A reverse proxy for function calls in a single process requires
# the same exception hierarchy as one that routes HTTP traffic
# across a fleet of servers. Without these exceptions, failures
# in the load balancing layer would propagate as raw Python errors,
# bypassing the enterprise exception taxonomy and leaving the
# middleware pipeline without structured error context for
# observability, alerting, and post-incident review.
# ============================================================


class ProxyError(FizzBuzzError):
    """Base exception for all Reverse Proxy and Load Balancer errors.

    When the reverse proxy layer encounters a failure — whether in
    backend selection, health checking, connection draining, or
    Layer 7 routing — it raises a subclass of this exception to
    provide structured diagnostics to the middleware pipeline.
    The proxy layer sits between the client (the main evaluation
    loop) and the backends (StandardRuleEngine instances), and
    failures at this layer indicate infrastructure-level problems
    with the FizzBuzz evaluation topology.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-PX00"),
            context=kwargs.pop("context", {}),
        )


class ProxyNoAvailableBackendsError(ProxyError):
    """Raised when no healthy backends are available to serve a request.

    Every backend in the pool has been marked UNHEALTHY or DRAINING,
    leaving the reverse proxy with zero capacity to evaluate FizzBuzz
    requests. This is the load balancing equivalent of every restaurant
    in town being closed simultaneously — the customer (a humble integer
    seeking its FizzBuzz classification) has nowhere to go. The proxy
    refuses to guess, fabricate results, or evaluate the number itself,
    because a reverse proxy that computes results directly is just a
    server with extra steps.
    """

    def __init__(self, algorithm: str) -> None:
        self.algorithm = algorithm
        super().__init__(
            f"No available backends for load balancing algorithm '{algorithm}'. "
            f"All backends are UNHEALTHY or DRAINING. The evaluation request "
            f"cannot be fulfilled until at least one backend recovers.",
            error_code="EFP-PX01",
            context={"algorithm": algorithm},
        )


class ProxyBackendAlreadyExistsError(ProxyError):
    """Raised when attempting to add a backend with a duplicate name.

    Backend names must be unique within the pool. Duplicate names would
    create ambiguity in health check reporting, sticky session mapping,
    and connection draining — all of which rely on the backend name as
    a stable identifier. This exception prevents the pool from entering
    an inconsistent state where two backends share an identity, which
    is philosophically troubling for entities whose sole purpose is to
    compute the same modulo operations.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"Backend '{name}' already exists in the pool. "
            f"Backend names must be unique to ensure unambiguous routing, "
            f"health monitoring, and session affinity.",
            error_code="EFP-PX02",
            context={"backend_name": name},
        )


class ProxyHealthCheckError(ProxyError):
    """Raised when a health check probe fails in an unexpected way.

    The health checker was attempting to evaluate canary number 42
    through a backend engine when something went wrong beyond a simple
    incorrect result. This could indicate a corrupted engine state,
    a resource exhaustion condition, or the kind of fundamental
    arithmetic failure that makes one question the reliability of
    silicon-based computation.
    """

    def __init__(self, backend_name: str, reason: str) -> None:
        self.backend_name = backend_name
        self.reason = reason
        super().__init__(
            f"Health check failed for backend '{backend_name}': {reason}. "
            f"The canary evaluation could not be completed, and the backend's "
            f"fitness for production traffic is indeterminate.",
            error_code="EFP-PX03",
            context={"backend_name": backend_name, "reason": reason},
        )


class ProxyRoutingError(ProxyError):
    """Raised when the Layer 7 router cannot determine a target group.

    The request router examines number properties (primality, divisibility,
    magnitude) to select the optimal backend group. When the routing logic
    itself encounters an error — for example, if the rule definitions are
    empty or the number cannot be classified — this exception is raised.
    A router that cannot route is an existential failure that undermines
    the entire reverse proxy architecture.
    """

    def __init__(self, number: int, reason: str) -> None:
        self.number = number
        self.reason = reason
        super().__init__(
            f"Routing failed for number {number}: {reason}. "
            f"The Layer 7 router could not determine an appropriate "
            f"backend group for this evaluation request.",
            error_code="EFP-PX04",
            context={"number": number, "reason": reason},
        )



# ============================================================
# Digital Logic Circuit Simulator (FizzGate) Exceptions
# ============================================================
# The FizzGate subsystem performs gate-level divisibility checking
# using combinational logic circuits synthesized from fundamental
# boolean gates. These exceptions cover structural errors in
# circuit topology, simulation runtime failures, timing violations,
# and steady-state convergence issues.
# ============================================================


class CircuitSimulationError(FizzBuzzError):
    """Base exception for all FizzGate digital circuit simulation errors.

    Raised when the event-driven simulator encounters a condition that
    prevents correct evaluation of the combinational logic circuit.
    This includes unknown gate types, input range violations, and
    general simulation engine failures.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-CKT0",
            context={"subsystem": "fizzgate"},
        )


class CircuitTopologyError(CircuitSimulationError):
    """Raised when the circuit graph contains a structural defect.

    Structural defects include combinational loops (feedback paths
    in what should be an acyclic circuit), mismatched operand widths
    in adder chains, incorrect fan-in counts for gate types (e.g.,
    a NOT gate with two inputs), and invalid divisor values for
    modulo circuits. A topologically invalid circuit cannot be
    simulated and must be corrected at the synthesis stage.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-CKT1"


class CircuitSteadyStateError(CircuitSimulationError):
    """Raised when the simulator fails to reach steady state.

    A well-formed combinational circuit must settle to stable output
    values within a finite number of events. If the event count
    exceeds the configured maximum, the circuit either contains an
    oscillation (which indicates a synthesis error) or the event
    budget is insufficient for the circuit's complexity.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-CKT2"


class CircuitTimingViolationError(CircuitSimulationError):
    """Raised when circuit settle time exceeds the configured timing budget.

    The timing budget defines the maximum acceptable propagation delay
    from input assertion to output stability. A violation indicates
    that the critical path through the circuit is too long for the
    target operating frequency, and the circuit requires optimization
    (e.g., carry-lookahead adders, logic restructuring, or pipeline
    registers).
    """

    def __init__(self, settle_ns: float, budget_ns: float, number: int) -> None:
        self.settle_ns = settle_ns
        self.budget_ns = budget_ns
        self.number = number
        super().__init__(
            f"Circuit settle time {settle_ns:.1f} ns exceeds budget {budget_ns:.1f} ns "
            f"for input {number}. Critical path optimization required.",
        )
        self.error_code = "EFP-CKT3"


# ============================================================
# FizzBloom Probabilistic Data Structures Exceptions
# ============================================================

class ProbabilisticError(FizzBuzzError):
    """Raised when a probabilistic data structure encounters an error.

    The Enterprise FizzBuzz Platform employs four probabilistic data
    structures for approximate analytics over evaluation streams.
    When any of these structures encounters an invalid configuration,
    capacity overflow, or numerical instability, this exception
    hierarchy provides precise diagnostics.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-PROB0",
            context={"subsystem": "fizzbloom"},
        )


class BloomFilterCapacityError(ProbabilisticError):
    """Raised when a Bloom filter exceeds its designed capacity.

    A Bloom filter sized for n elements with target false positive
    rate p will experience degraded accuracy once the number of
    inserted elements exceeds n. This exception signals that the
    actual false positive rate has exceeded the configured threshold
    and the filter should be rebuilt with larger parameters.
    """

    def __init__(self, current_count: int, capacity: int, fpr: float) -> None:
        self.current_count = current_count
        self.capacity = capacity
        self.fpr = fpr
        super().__init__(
            f"Bloom filter capacity exceeded: {current_count}/{capacity} elements, "
            f"actual FPR {fpr:.6f} exceeds design threshold",
        )
        self.error_code = "EFP-PROB1"


class CountMinSketchOverflowError(ProbabilisticError):
    """Raised when a Count-Min Sketch counter exceeds its maximum value.

    Each cell in the Count-Min Sketch is a bounded integer counter.
    If the evaluation stream is sufficiently long, a counter may
    overflow. This exception indicates the sketch should be reset
    or widened.
    """

    def __init__(self, row: int, col: int, value: int) -> None:
        self.row = row
        self.col = col
        self.value = value
        super().__init__(
            f"Count-Min Sketch counter overflow at row={row}, col={col}: "
            f"value {value} exceeds 64-bit signed integer range",
        )
        self.error_code = "EFP-PROB2"


class HyperLogLogPrecisionError(ProbabilisticError):
    """Raised when a HyperLogLog estimator is configured with invalid precision.

    The precision parameter p must be in the range [4, 18]. Values
    outside this range either produce unacceptably high estimation
    error (p < 4) or consume excessive memory for negligible accuracy
    improvement (p > 18). The standard error of a HyperLogLog
    estimator is approximately 1.04 / sqrt(2^p).
    """

    def __init__(self, precision: int) -> None:
        self.precision = precision
        super().__init__(
            f"HyperLogLog precision {precision} is out of valid range [4, 18]. "
            f"Standard error at p={precision} would be "
            f"{'unacceptably high' if precision < 4 else 'memory-wasteful'}.",
        )
        self.error_code = "EFP-PROB3"


# ============================================================
# Static Analysis / Linter Errors
# ============================================================


class LintError(FizzBuzzError):
    """Base exception for all FizzLint static analysis errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, error_code="EFP-LINT0", **kwargs)


class LintConfigurationError(LintError):
    """Raised when the linter is misconfigured.

    This can occur when invalid rule IDs are passed to the disabled
    rules list, or when lint rule parameters are out of range.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-LINT1"


class LintEngineError(LintError):
    """Raised when a lint rule fails during execution.

    This indicates an internal error in the lint rule implementation,
    not a violation in the user's rule definitions. Lint rules are
    expected to be side-effect-free and must not raise exceptions
    during normal operation.
    """

    def __init__(self, rule_id: str, message: str) -> None:
        self.failing_rule_id = rule_id
        super().__init__(message)
        self.error_code = "EFP-LINT2"


# ============================================================
# FizzLog Datalog Query Engine Errors
# ============================================================


class DatalogError(FizzBuzzError):
    """Base exception for all Datalog query engine errors.

    The Datalog subsystem operates on logical facts and Horn clauses.
    When the engine encounters a condition that violates the semantic
    requirements of Datalog evaluation — non-ground assertions,
    unstratifiable programs, failed unification, or syntactically
    invalid queries — it raises a subclass of this exception to
    communicate the precise nature of the logical failure.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, error_code=kwargs.pop("error_code", "EFP-DG00"), **kwargs)


class DatalogStratificationError(DatalogError):
    """Raised when a Datalog program contains a negative cycle.

    Stratified negation requires that the predicate dependency graph
    have no cycles involving negated edges. A negative cycle means
    that a predicate depends negatively on itself (directly or
    transitively), making the program's semantics undefined under
    the stratified semantics. The program must be restructured to
    break the negative cycle before evaluation can proceed.
    """

    def __init__(self, predicate: str, cycle_path: list[str]) -> None:
        self.predicate = predicate
        self.cycle_path = cycle_path
        cycle_str = " -> ".join(cycle_path)
        super().__init__(
            f"Negative cycle detected involving predicate '{predicate}': {cycle_str}. "
            f"Stratified negation requires acyclic negative dependencies.",
            error_code="EFP-DG01",
            context={"predicate": predicate, "cycle_path": cycle_path},
        )


class DatalogUnificationError(DatalogError):
    """Raised when unification fails in an unexpected manner.

    Unification between a pattern and a fact should either succeed
    (producing a substitution) or fail (returning None). This
    exception is raised when the unification engine encounters an
    internal inconsistency, such as a variable bound to two different
    values in the same substitution — a condition that should be
    impossible in a correctly implemented engine but is checked
    defensively because enterprise software trusts nothing.
    """

    def __init__(self, pattern: str, fact: str, reason: str) -> None:
        super().__init__(
            f"Unification failed between '{pattern}' and '{fact}': {reason}",
            error_code="EFP-DG02",
            context={"pattern": pattern, "fact": fact, "reason": reason},
        )


class DatalogQuerySyntaxError(DatalogError):
    """Raised when a Datalog query string cannot be parsed.

    The query parser expects the format predicate(arg1, arg2, ...)
    where arguments are variables (uppercase), string constants
    (lowercase), or integer literals. Deviations from this syntax
    result in a parse error at the indicated position.
    """

    def __init__(self, query: str, position: int, expected: str) -> None:
        super().__init__(
            f"Syntax error in query '{query}' at position {position}: expected {expected}",
            error_code="EFP-DG03",
            context={"query": query, "position": position, "expected": expected},
        )


# ============================================================
# FizzIR SSA Intermediate Representation Exceptions (EFP-IR00 through EFP-IR03)
# ============================================================
# Because compiling FizzBuzz evaluation to an LLVM-inspired intermediate
# representation with SSA form and eight optimization passes requires
# the same diagnostic precision as a production compiler. If a phi
# node references a non-existent predecessor block, the entire SSA
# form is invalid, and the optimization pipeline must halt with a
# clear error message. Cytron et al. (1989) did not anticipate that
# their algorithm would one day construct SSA form for programs that
# compute n % 3, but the algorithm's correctness guarantees apply
# regardless of the program's computational ambition.
# ============================================================


class SSAIRError(FizzBuzzError):
    """Base exception for all FizzIR intermediate representation errors.

    The FizzIR subsystem compiles FizzBuzz evaluation rules to an
    LLVM-inspired SSA form, applies optimization passes, and interprets
    the result. Errors in any phase -- compilation, SSA construction,
    optimization, or interpretation -- are rooted in this hierarchy.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-IR00"),
            context=kwargs.pop("context", {}),
        )


class IRCompilationError(SSAIRError):
    """Raised when FizzBuzz rules cannot be compiled to IR.

    Compilation failure indicates that the rule set contains
    configurations that the IR compiler cannot represent in the
    FizzIR type system -- for example, a divisor of zero, which
    would generate a division-by-zero in the srem instruction.
    """

    def __init__(self, rule_name: str, reason: str) -> None:
        self.rule_name = rule_name
        self.reason = reason
        super().__init__(
            f"IR compilation failed for rule '{rule_name}': {reason}",
            error_code="EFP-IR01",
            context={"rule_name": rule_name, "reason": reason},
        )


class SSAConstructionError(SSAIRError):
    """Raised when SSA form construction encounters an invalid CFG.

    SSA construction requires a well-formed control flow graph with
    a unique entry block and no unreachable cycles. If the dominator
    tree computation fails or phi node placement encounters an
    inconsistency, this error provides the block label and the
    nature of the structural violation.
    """

    def __init__(self, block_label: str, detail: str) -> None:
        self.block_label = block_label
        self.detail = detail
        super().__init__(
            f"SSA construction failed at block '{block_label}': {detail}",
            error_code="EFP-IR02",
            context={"block_label": block_label, "detail": detail},
        )


class IROptimizationError(SSAIRError):
    """Raised when an optimization pass produces invalid IR.

    Each optimization pass must preserve the semantic equivalence
    of the program. If a pass produces IR that the verifier rejects
    -- for example, a use of an undefined value, or a basic block
    without a terminator -- this error identifies the responsible
    pass and the nature of the violation.
    """

    def __init__(self, pass_name: str, detail: str) -> None:
        self.pass_name = pass_name
        self.detail = detail
        super().__init__(
            f"Optimization pass '{pass_name}' produced invalid IR: {detail}",
            error_code="EFP-IR03",
            context={"pass_name": pass_name, "detail": detail},
        )


# ============================================================
# FizzProof — Proof Certificate Exceptions
# ============================================================


class ProofCertificateError(FizzBuzzError):
    """Base exception for the FizzProof proof certificate subsystem.

    The proof certificate engine constructs machine-checkable proofs
    in the Calculus of Constructions for every FizzBuzz classification.
    When proof construction, verification, or export encounters an
    error, the appropriate subclass of this exception is raised.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-PF00"),
            context=kwargs.pop("context", {}),
        )


class ProofTermError(ProofCertificateError):
    """Raised when a proof term is structurally malformed.

    This indicates a bug in the CertificateGenerator: it produced
    a term that violates the syntactic invariants of the Calculus
    of Constructions — for example, a negative de Bruijn index
    after substitution, or a lambda without a body. The trusted
    kernel refuses to examine such terms.
    """

    def __init__(self, message: str, *, term_repr: str = "") -> None:
        self.term_repr = term_repr
        super().__init__(
            f"Malformed proof term: {message}",
            error_code="EFP-PF01",
            context={"term_repr": term_repr},
        )


class ProofCheckError(ProofCertificateError):
    """Raised when the trusted proof checker rejects a proof term.

    This is the most significant error in the FizzProof subsystem:
    it means the proof term does not type-check under the rules of
    the Calculus of Constructions. Either the proposition is false,
    or (more likely) the CertificateGenerator constructed an
    incorrect proof. In either case, no certificate is issued.
    """

    def __init__(self, message: str, *, step: str = "") -> None:
        self.step = step
        super().__init__(
            f"Proof check failed at '{step}': {message}",
            error_code="EFP-PF02",
            context={"step": step},
        )


class CertificateExportError(ProofCertificateError):
    """Raised when LaTeX export of a proof certificate fails.

    The LaTeX exporter encountered an error while rendering the
    proof certificate as a LaTeX document. This could indicate
    an encoding issue, a missing template component, or a proof
    term that cannot be pretty-printed.
    """

    def __init__(self, message: str, *, certificate_id: str = "") -> None:
        self.certificate_id = certificate_id
        super().__init__(
            f"Certificate export failed: {message}",
            error_code="EFP-PF03",
            context={"certificate_id": certificate_id},
        )


# ============================================================
# FizzFS — Virtual File System Exceptions
# ============================================================


class FileSystemError(FizzBuzzError):
    """Base exception for all FizzFS virtual file system operations.

    The FizzFS subsystem provides a POSIX-like virtual file system for
    navigating platform state. When file operations fail — open, read,
    write, stat, readdir — the appropriate subclass of this exception
    is raised with diagnostic context sufficient for post-mortem analysis.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-FS00"),
            context=kwargs.pop("context", {}),
        )


class FileNotFoundError_(FileSystemError):
    """Raised when a path does not resolve to any inode in the file system.

    The virtual file system walked the directory tree from root to the
    requested path component-by-component and failed to locate a matching
    directory entry. This is the VFS equivalent of ENOENT. The trailing
    underscore avoids shadowing the built-in FileNotFoundError, which
    applies to the host OS — a fundamentally less important file system.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"No such file or directory: '{path}'",
            error_code="EFP-FS01",
            context={"path": path},
        )


class PermissionDeniedError(FileSystemError):
    """Raised when an operation is denied by the inode permission bits.

    The requested operation (read, write, or execute) requires a
    permission bit that is not set on the target inode. In a real
    POSIX system this would trigger EACCES. Here, it means someone
    tried to write to /dev/null's parent directory without the
    appropriate access flags, which is a governance concern.
    """

    def __init__(self, path: str, operation: str) -> None:
        self.path = path
        self.operation = operation
        super().__init__(
            f"Permission denied: '{operation}' on '{path}'",
            error_code="EFP-FS02",
            context={"path": path, "operation": operation},
        )


class NotADirectoryError_(FileSystemError):
    """Raised when a path component is not a directory during traversal.

    While resolving a multi-component path, the VFS encountered a
    non-directory inode where a directory was expected. This is the
    ENOTDIR errno. The trailing underscore avoids shadowing the
    built-in NotADirectoryError.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"Not a directory: '{path}'",
            error_code="EFP-FS03",
            context={"path": path},
        )


class IsADirectoryError_(FileSystemError):
    """Raised when a file operation is attempted on a directory inode.

    The caller attempted to open, read, or write a path that resolves
    to a directory. Directories are not regular files and cannot be
    treated as byte streams. This is EISDIR.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"Is a directory: '{path}'",
            error_code="EFP-FS04",
            context={"path": path},
        )


class FileDescriptorError(FileSystemError):
    """Raised when an operation references an invalid file descriptor.

    The file descriptor number provided does not correspond to any
    open file in the fd table. Either the fd was never opened, or
    it was previously closed. This is EBADF.
    """

    def __init__(self, fd: int) -> None:
        self.fd = fd
        super().__init__(
            f"Bad file descriptor: {fd}",
            error_code="EFP-FS05",
            context={"fd": fd},
        )


class FileDescriptorLimitError(FileSystemError):
    """Raised when the process has exhausted its file descriptor quota.

    The enterprise fd limit (1024) has been reached. No additional
    files may be opened until existing descriptors are closed. This
    mirrors EMFILE. In production deployments, this limit ensures
    that no single FizzBuzz evaluation monopolizes the VFS fd table,
    preserving fair access for all concurrent evaluations.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(
            f"Too many open files: limit is {limit}",
            error_code="EFP-FS06",
            context={"limit": limit},
        )


class MountError(FileSystemError):
    """Raised when a mount or unmount operation fails.

    The VFS was unable to attach or detach a file system provider
    at the specified mount point. Common causes include mounting
    over an existing mount point, attempting to unmount a path
    that is not a mount boundary, or providing an invalid path.
    """

    def __init__(self, mount_point: str, reason: str) -> None:
        self.mount_point = mount_point
        super().__init__(
            f"Mount error at '{mount_point}': {reason}",
            error_code="EFP-FS07",
            context={"mount_point": mount_point, "reason": reason},
        )


class FileExistsError_(FileSystemError):
    """Raised when creating a file or directory that already exists.

    The target path already contains an inode. To overwrite, the
    caller must first remove the existing entry. This is EEXIST.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"File exists: '{path}'",
            error_code="EFP-FS08",
            context={"path": path},
        )


class ReadOnlyFileSystemError(FileSystemError):
    """Raised when a write operation targets a read-only mount.

    The target path resides on a mount point backed by a provider
    that does not support write operations. Virtual providers
    (proc, cache, dev) are read-only by design: platform state
    flows outward through the VFS, not inward.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"Read-only file system: '{path}'",
            error_code="EFP-FS09",
            context={"path": path},
        )


# ============================================================
# Audio Synthesis Exceptions (EFP-AS00 through EFP-AS09)
# ============================================================


class AudioSynthError(FizzBuzzError):
    """Base exception for all FizzSynth digital audio synthesizer errors.

    The audio synthesis pipeline converts FizzBuzz evaluation sequences
    into PCM audio. When the pipeline fails, the polyrhythmic
    sonification of the 3-against-5 divisibility pattern is compromised,
    leaving the operator unable to hear whether a number is divisible
    by 3, 5, or both.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-AS00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class InvalidWaveformError(AudioSynthError):
    """Raised when an unsupported waveform type is requested.

    The FizzSynth engine supports four waveform types: SINE, SQUARE,
    SAWTOOTH, and TRIANGLE. Requesting any other waveform would require
    extending the oscillator's sample generation kernel, which is a
    non-trivial DSP engineering effort.
    """

    def __init__(self, waveform_name: str) -> None:
        super().__init__(
            f"Unsupported waveform type: '{waveform_name}'. "
            f"Supported types: SINE, SQUARE, SAWTOOTH, TRIANGLE.",
            error_code="EFP-AS01",
            context={"waveform_name": waveform_name},
        )


class InvalidFrequencyError(AudioSynthError):
    """Raised when a frequency value is outside the audible or safe range.

    Human hearing spans roughly 20 Hz to 20,000 Hz. Frequencies below
    this range produce inaudible infrasound; frequencies above it
    risk aliasing artifacts at the 44.1 kHz sample rate. Both are
    unacceptable for enterprise-grade FizzBuzz sonification.
    """

    def __init__(self, frequency: float) -> None:
        super().__init__(
            f"Frequency {frequency:.2f} Hz is outside the supported range. "
            f"The audible spectrum for FizzBuzz sonification is 20 Hz to 20,000 Hz.",
            error_code="EFP-AS02",
            context={"frequency": frequency},
        )


class WAVWriteError(AudioSynthError):
    """Raised when the WAV file writer fails to produce output.

    WAV file generation requires writing a valid RIFF header followed
    by 16-bit signed PCM sample data. Failure at any stage of this
    process means the FizzBuzz composition cannot be persisted to disk
    for later auditory analysis.
    """

    def __init__(self, filepath: str, reason: str) -> None:
        super().__init__(
            f"Failed to write WAV file '{filepath}': {reason}",
            error_code="EFP-AS03",
            context={"filepath": filepath},
        )


class EnvelopeConfigurationError(AudioSynthError):
    """Raised when ADSR envelope parameters are invalid.

    All envelope durations must be non-negative, and the sustain
    level must be between 0.0 and 1.0. An improperly configured
    envelope can cause amplitude discontinuities (clicks) or
    silence where music was expected.
    """

    def __init__(self, parameter: str, value: float, reason: str) -> None:
        super().__init__(
            f"Invalid ADSR envelope parameter '{parameter}' = {value}: {reason}",
            error_code="EFP-AS04",
            context={"parameter": parameter, "value": value},
        )


class FilterInstabilityError(AudioSynthError):
    """Raised when biquad filter coefficients produce an unstable response.

    An unstable IIR filter will produce exponentially growing output,
    which rapidly exceeds the representable range and results in
    digital clipping or complete signal destruction. This typically
    occurs when the cutoff frequency is too close to the Nyquist
    limit or when the Q factor is unreasonably high.
    """

    def __init__(self, filter_type: str, cutoff_hz: float, q: float) -> None:
        super().__init__(
            f"Biquad filter instability detected: type={filter_type}, "
            f"cutoff={cutoff_hz:.1f} Hz, Q={q:.3f}. "
            f"The filter poles have escaped the unit circle.",
            error_code="EFP-AS05",
            context={"filter_type": filter_type, "cutoff_hz": cutoff_hz, "q": q},
        )


# =========================================================================
# FizzNet TCP/IP Protocol Stack exceptions (EFP-NET0 through EFP-NET7)
# =========================================================================


class FizzNetError(FizzBuzzError):
    """Base exception for all FizzNet TCP/IP Protocol Stack errors.

    The FizzNet subsystem implements a complete TCP/IP stack for
    in-memory FizzBuzz classification delivery. Any failure at any
    layer of the stack — Ethernet, IP, TCP, or the application-layer
    FizzBuzz Protocol — is represented by a subclass of this exception.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-NET0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FizzNetChecksumError(FizzNetError):
    """Raised when a packet or frame fails integrity verification.

    Checksums are the last line of defense against data corruption in
    transit. When a checksum fails on an in-memory packet that never
    left the process, it suggests something far more troubling than
    a flipped bit on a wire — it suggests a bug in the checksum
    computation itself, which is an existential crisis for a protocol
    stack.
    """

    def __init__(self, layer: str, expected: int, actual: int) -> None:
        super().__init__(
            f"{layer} checksum verification failed: expected 0x{expected:04X}, "
            f"got 0x{actual:04X}",
            error_code="EFP-NET1",
            context={"layer": layer, "expected": expected, "actual": actual},
        )


class FizzNetConnectionRefusedError(FizzNetError):
    """Raised when a TCP connection attempt is refused by the remote host.

    The destination endpoint has no listening socket on the requested
    port, or the backlog queue is full. In a real network, this would
    result in an RST segment. In FizzNet, it means the FizzBuzz server
    is not running, which is a deployment failure of the highest order.
    """

    def __init__(self, ip: str, port: int) -> None:
        super().__init__(
            f"Connection refused by {ip}:{port}. No FizzBuzz service is "
            f"accepting connections on this endpoint.",
            error_code="EFP-NET2",
            context={"ip": ip, "port": port},
        )


class FizzNetConnectionResetError(FizzNetError):
    """Raised when a TCP connection is reset by the remote host.

    An RST segment was received, indicating that the remote endpoint
    has abruptly terminated the connection. This may occur if the
    FizzBuzz server encounters an unrecoverable error mid-classification.
    """

    def __init__(self, ip: str, port: int) -> None:
        super().__init__(
            f"Connection to {ip}:{port} was reset by the remote host.",
            error_code="EFP-NET3",
            context={"ip": ip, "port": port},
        )


class FizzNetTimeoutError(FizzNetError):
    """Raised when a TCP operation exceeds the configured timeout.

    In a real network, timeouts account for propagation delay, queuing
    delay, and processing delay. In FizzNet, the only delay is the
    time it takes Python to execute a few method calls, so a timeout
    here would be genuinely alarming.
    """

    def __init__(self, operation: str, timeout_ms: float) -> None:
        super().__init__(
            f"FizzNet operation '{operation}' timed out after {timeout_ms:.1f}ms.",
            error_code="EFP-NET4",
            context={"operation": operation, "timeout_ms": timeout_ms},
        )


class FizzNetARPResolutionError(FizzNetError):
    """Raised when ARP cannot resolve an IP address to a MAC address.

    The ARP table does not contain a mapping for the requested IP,
    and no interface with that IP is registered in the network stack.
    The packet is undeliverable at Layer 2.
    """

    def __init__(self, ip: str) -> None:
        super().__init__(
            f"ARP resolution failed for {ip}. No MAC address mapping exists.",
            error_code="EFP-NET5",
            context={"ip": ip},
        )


class FizzNetTTLExpiredError(FizzNetError):
    """Raised when an IPv4 packet's TTL reaches zero.

    The packet has been forwarded through too many hops and must be
    discarded. Given that FizzNet has zero hops (all interfaces are
    in the same process), a TTL expiration suggests the initial TTL
    was set to zero, which is a configuration error.
    """

    def __init__(self, src_ip: str, dst_ip: str, original_ttl: int) -> None:
        super().__init__(
            f"TTL expired for packet from {src_ip} to {dst_ip} "
            f"(original TTL: {original_ttl}).",
            error_code="EFP-NET6",
            context={"src_ip": src_ip, "dst_ip": dst_ip, "original_ttl": original_ttl},
        )


class FizzNetProtocolError(FizzNetError):
    """Raised when a protocol-level error occurs in the FizzNet stack.

    This covers malformed segments, invalid state transitions, and
    any other protocol violation that prevents normal operation of
    the TCP/IP stack or the FizzBuzz Protocol layer.
    """

    def __init__(self, message: str, protocol: str) -> None:
        super().__init__(
            f"FizzNet {protocol} protocol error: {message}",
            error_code="EFP-NET7",
            context={"protocol": protocol},
        )


# ============================================================
# FizzFold Protein Folding Exceptions (EFP-PF00 through EFP-PF02)
# ============================================================

class FizzFoldError(FizzBuzzError):
    """Base exception for the FizzFold protein folding subsystem.

    Protein structure prediction is a computationally intensive process
    that can fail for a variety of reasons: invalid amino acid sequences,
    energy function singularities, convergence failures, or insufficient
    Monte Carlo steps. This hierarchy classifies each failure mode to
    enable targeted recovery strategies at the middleware level.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "EFP-PF00"),
            context=kwargs.get("context", {}),
        )


class FizzFoldSequenceError(FizzFoldError):
    """Raised when an amino acid sequence contains unrecognized residues.

    The IUPAC single-letter code table defines 20 standard amino acids
    plus several ambiguity codes. Characters outside this table cannot
    be mapped to biophysical properties and therefore cannot participate
    in the energy function. This exception is raised during sequence
    validation, before any Monte Carlo steps are attempted.
    """

    def __init__(self, invalid_residue: str) -> None:
        super().__init__(
            f"Unrecognized amino acid code: '{invalid_residue}'. "
            f"Valid codes for FizzFold: F, I, Z, B, U, A, G, L, V, P.",
            error_code="EFP-PF01",
            context={"invalid_residue": invalid_residue},
        )
        self.invalid_residue = invalid_residue


class FizzFoldConvergenceError(FizzFoldError):
    """Raised when simulated annealing fails to reach a stable conformation.

    If the energy at the end of the annealing schedule remains above the
    convergence threshold, the folding simulation is considered to have
    failed. This may indicate an insufficient number of Monte Carlo steps,
    an overly aggressive cooling schedule, or a sequence that resists
    compact folding due to charge repulsion.
    """

    def __init__(self, sequence: str, final_energy: float, steps: int) -> None:
        super().__init__(
            f"Folding of '{sequence}' did not converge after {steps} MC steps. "
            f"Final energy: {final_energy:.3f} kcal/mol. Consider increasing "
            f"--fold-steps or adjusting the cooling schedule.",
            error_code="EFP-PF02",
            context={
                "sequence": sequence,
                "final_energy": final_energy,
                "steps": steps,
            },
        )
        self.sequence = sequence
        self.final_energy = final_energy
        self.steps = steps


class RayTracerError(FizzBuzzError):
    """Base exception for all FizzTrace ray tracing subsystem errors.

    The physically-based rendering pipeline involves numerous mathematical
    operations — quadratic solvers, trigonometric functions, recursive ray
    bouncing — each of which can fail under degenerate conditions. This
    hierarchy classifies each failure mode to enable targeted diagnostics
    at the rendering middleware level.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "EFP-RT00"),
            context=kwargs.get("context", {}),
        )


class RayTracerSceneError(RayTracerError):
    """Raised when the scene configuration is invalid or degenerate.

    A scene must contain at least one object for rendering to produce
    meaningful output. An empty scene results in a pure background
    image, which, while technically correct, does not convey any
    FizzBuzz classification information and therefore fails to meet
    the minimum viable rendering threshold.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Scene configuration error: {reason}",
            error_code="EFP-RT01",
            context={"reason": reason},
        )


class RayTracerConvergenceError(RayTracerError):
    """Raised when the path tracer fails to converge within the maximum depth.

    If every sample ray reaches the maximum bounce depth without escaping
    to the background or being terminated by Russian Roulette, the image
    may contain significant bias. This condition is monitored but not
    typically fatal — the rendering equation is being approximated, after all.
    """

    def __init__(self, max_depth: int, samples: int) -> None:
        super().__init__(
            f"Path tracer reached maximum depth {max_depth} on all {samples} samples. "
            f"Consider increasing max_depth or reducing scene complexity.",
            error_code="EFP-RT02",
            context={"max_depth": max_depth, "samples": samples},
        )


# ---------------------------------------------------------------------------
# FizzGit Version Control System Exceptions
# ---------------------------------------------------------------------------


class VCSError(FizzBuzzError):
    """Base exception for all FizzGit version control system errors.

    The FizzGit VCS provides content-addressable version control for
    FizzBuzz evaluation state. When operations on the commit DAG,
    object store, ref store, or merge engine fail, a VCSError or
    one of its subclasses is raised to indicate the precise failure
    mode within the version control subsystem.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "EFP-VCS0"),
            context=kwargs.get("context", {}),
        )


class VCSObjectNotFoundError(VCSError):
    """Raised when a content-addressable object cannot be located in the store.

    Every object in the FizzGit store is keyed by its SHA-256 digest. If
    a requested hash is not present, the object has either never been
    created, has been garbage collected (not currently implemented, as
    FizzBuzz evaluation state is too valuable to discard), or the hash
    was corrupted in transit.
    """

    def __init__(self, object_hash: str) -> None:
        super().__init__(
            f"Object not found in FizzGit store: {object_hash[:16]}...",
            error_code="EFP-VCS1",
            context={"object_hash": object_hash},
        )
        self.object_hash = object_hash


class VCSMergeConflictError(VCSError):
    """Raised when a three-way merge encounters unresolvable conflicts.

    While the FizzGit merge engine applies domain-specific conflict
    resolution (FizzBuzz > Fizz > Buzz > number), there may be edge
    cases where the conflict cannot be automatically resolved — for
    instance, when two branches disagree on whether a number even
    exists, which would represent a fundamental ontological crisis
    in the FizzBuzz domain.
    """

    def __init__(self, branch: str, conflict_count: int) -> None:
        super().__init__(
            f"Merge of branch '{branch}' produced {conflict_count} conflict(s). "
            f"Domain-specific resolution applied where possible.",
            error_code="EFP-VCS2",
            context={"branch": branch, "conflict_count": conflict_count},
        )
        self.branch = branch
        self.conflict_count = conflict_count


class VCSBranchError(VCSError):
    """Raised when a branch operation fails.

    Branch operations can fail for several reasons: creating a branch
    that already exists, deleting the current branch, or attempting
    to check out a branch that does not exist. Each of these represents
    a violation of the ref store invariants that must be reported
    immediately.
    """

    def __init__(self, message: str, *, branch_name: str = "") -> None:
        super().__init__(
            message,
            error_code="EFP-VCS3",
            context={"branch_name": branch_name},
        )
        self.branch_name = branch_name


class VCSBisectError(VCSError):
    """Raised when a bisect operation encounters an error.

    Bisect errors occur when the binary search through commit history
    cannot proceed — either because no bisect is in progress, the
    good/bad commit range is invalid, or the commit DAG is malformed.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-VCS4",
            context={},
        )


# ============================================================
# ELF Binary Format Exceptions (EFP-ELF0 through EFP-ELF2)
# ============================================================
# These exceptions cover failures in the ELF binary generation
# and parsing pipeline. Producing a malformed ELF binary is
# a compliance risk of the highest order — downstream toolchains
# rely on byte-exact adherence to the ELF specification, and any
# deviation could cause undefined behavior in the FizzBuzz
# evaluation processor.
# ============================================================


class ELFFormatError(FizzBuzzError):
    """Base exception for all ELF binary format errors.

    Covers generation, parsing, and structural validation failures
    in the ELF subsystem. All ELF-related exceptions inherit from
    this class to enable targeted error handling in the middleware
    pipeline.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-ELF0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ELFParseError(ELFFormatError):
    """Raised when an ELF binary cannot be parsed from raw bytes.

    Parse errors indicate that the input data does not conform to
    the ELF specification — the magic bytes are wrong, a header
    field is out of range, or the binary is truncated. In a production
    environment, this could indicate data corruption during
    transmission or storage of the FizzBuzz evaluation artifact.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-ELF1",
            context={},
        )


class ELFGenerationError(ELFFormatError):
    """Raised when the ELF generator fails to produce a valid binary.

    Generation errors occur when the builder encounters an internal
    inconsistency — for example, a symbol referencing a non-existent
    section, or a segment covering zero bytes. These errors indicate
    a defect in the generation pipeline rather than in the input data.
    """

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(
            message,
            error_code="EFP-ELF2",
            context={"detail": detail},
        )


# ============================================================
# Replication Exceptions
# ============================================================


class ReplicationError(FizzBuzzError):
    """Base exception for all database replication subsystem failures.

    Database replication is a critical infrastructure concern. When
    replication fails, FizzBuzz evaluation results may exist on the
    primary but not on replicas, creating an inconsistency window
    that violates the platform's durability guarantees.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-RP00"),
            context=kwargs.pop("context", {}),
        )


class ReplicationWALCorruptionError(ReplicationError):
    """Raised when a WAL record fails integrity verification.

    WAL corruption during shipping indicates either a software defect
    in the checksum computation, memory corruption on the source node,
    or an extremely improbable cosmic ray event that flipped a bit in
    the in-memory WAL buffer. All three scenarios warrant immediate
    investigation.
    """

    def __init__(self, lsn: int, reason: str) -> None:
        super().__init__(
            f"WAL record corruption at LSN {lsn}: {reason}",
            error_code="EFP-RP01",
            context={"lsn": lsn},
        )
        self.lsn = lsn


class ReplicationFencingError(ReplicationError):
    """Raised when a fenced node attempts to accept writes.

    Fencing is the mechanism by which a deposed primary is prevented
    from accepting new writes after a failover. A fenced node has been
    superseded by a newer epoch and must not modify any state.
    """

    def __init__(self, node_id: str, epoch: int, reason: str) -> None:
        super().__init__(
            f"Node '{node_id}' is fenced at epoch {epoch}: {reason}",
            error_code="EFP-RP02",
            context={"node_id": node_id, "epoch": epoch},
        )
        self.node_id = node_id
        self.fenced_epoch = epoch


class ReplicationPromotionError(ReplicationError):
    """Raised when replica promotion fails.

    Promotion failure can occur when the target replica is fenced,
    unreachable, or not a member of the replica set. It can also
    occur when the maximum failover count has been exceeded, which
    suggests a systemic issue requiring manual intervention.
    """

    def __init__(self, node_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to promote node '{node_id}': {reason}",
            error_code="EFP-RP03",
            context={"node_id": node_id},
        )
        self.node_id = node_id


class ReplicationSplitBrainError(ReplicationError):
    """Raised when a split-brain condition is detected in the replica set.

    Split-brain occurs when two or more nodes simultaneously believe
    they are the primary, typically due to a network partition. This
    is one of the most dangerous failure modes in distributed systems,
    as it can lead to divergent state that is difficult to reconcile.
    """

    def __init__(self, primary_nodes: list[str], epoch: int) -> None:
        super().__init__(
            f"Split-brain detected: {len(primary_nodes)} primaries "
            f"at epoch {epoch}: {primary_nodes}",
            error_code="EFP-RP04",
            context={"primary_nodes": primary_nodes, "epoch": epoch},
        )
        self.primary_nodes = primary_nodes


class ReplicationLagExceededError(ReplicationError):
    """Raised when replication lag exceeds the configured threshold.

    Excessive replication lag means replicas are falling behind the
    primary, increasing the window of potential data loss in the event
    of a primary failure. For FizzBuzz evaluation results, this means
    recent divisibility computations may not survive a failover.
    """

    def __init__(self, node_id: str, lag: int, threshold: int) -> None:
        super().__init__(
            f"Replication lag on '{node_id}' is {lag} records "
            f"(threshold: {threshold})",
            error_code="EFP-RP05",
            context={"node_id": node_id, "lag": lag, "threshold": threshold},
        )
        self.node_id = node_id
        self.lag = lag


# Z Specification Exceptions (EFP-ZS00 through EFP-ZS02)


class ZSpecError(FizzBuzzError):
    """Base exception for all Z notation formal specification errors.

    Raised when the Z specification engine encounters a condition that
    prevents the construction, evaluation, or verification of a formal
    specification. In a system where correctness is defined by mathematical
    specification, failure of the specification engine itself represents
    a foundational crisis.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-ZS00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ZSpecTypeError(ZSpecError):
    """Raised when a Z schema calculus operation encounters a type mismatch.

    Schema conjunction requires that shared variable names have compatible
    types. When two schemas declare the same variable with different types,
    their conjunction is undefined — the schemas describe incompatible
    state spaces that cannot be meaningfully combined.
    """

    def __init__(self, variable: str, type_a: str, type_b: str) -> None:
        super().__init__(
            f"Type mismatch for variable '{variable}' in schema conjunction: "
            f"{type_a} vs {type_b}",
            error_code="EFP-ZS01",
            context={"variable": variable, "type_a": type_a, "type_b": type_b},
        )
        self.variable = variable
        self.type_a = type_a
        self.type_b = type_b


class ZSpecRefinementError(ZSpecError):
    """Raised when a refinement check detects a specification violation.

    A refinement violation means the implementation does not correctly
    implement the abstract specification. The retrieve relation fails
    to preserve the invariant, or an operation fails to satisfy the
    specification's postcondition. This is the formal equivalent of
    "the code is wrong".
    """

    def __init__(self, spec_name: str, impl_name: str, violations: int) -> None:
        super().__init__(
            f"Refinement check failed: '{impl_name}' does not refine '{spec_name}' "
            f"({violations} violation(s) detected)",
            error_code="EFP-ZS02",
            context={
                "spec_name": spec_name,
                "impl_name": impl_name,
                "violations": violations,
            },
        )
        self.spec_name = spec_name
        self.impl_name = impl_name
        self.violation_count = violations


# ------------------------------------------------------------------
# FizzFlame — Flame Graph Generator Exceptions
# ------------------------------------------------------------------


class FlameGraphError(FizzBuzzError):
    """Base exception for the FizzFlame flame graph subsystem.

    Raised when flame graph generation, stack collapsing, or SVG
    rendering encounters an unrecoverable condition.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-FG00",
            context={},
        )


class FlameGraphRenderError(FlameGraphError):
    """Raised when SVG rendering of a flame graph fails.

    This may occur due to invalid frame dimensions, XML serialization
    errors, or memory constraints when rendering extremely deep call
    stacks (though any FizzBuzz call stack exceeding 100 frames
    warrants an architectural review rather than a rendering fix).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-FG01"


class FlameGraphCollapseError(FlameGraphError):
    """Raised when span tree collapsing fails.

    This indicates a structural problem in the span tree, such as
    cycles in parent references, orphaned spans, or timing anomalies
    where a child span outlives its parent.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-FG02"


class FlameGraphDiffError(FlameGraphError):
    """Raised when differential flame graph computation fails.

    This may occur when comparing incompatible flame graphs (different
    trace structures) or when the baseline or comparison data is
    corrupted or empty.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-FG03"


class TheoremProverError(FizzBuzzError):
    """Base exception for all theorem prover errors.

    Raised when the automated theorem prover encounters an error
    during formula conversion, unification, or resolution. In a
    production system, a failure to prove FizzBuzz correctness
    constitutes a Category 1 incident.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-TP00",
            context={},
        )


class UnificationFailureError(TheoremProverError):
    """Raised when Robinson's unification algorithm fails to find a MGU.

    Two terms are not unifiable when they have incompatible structure
    or when the occurs check detects a circular substitution. This
    typically indicates that the resolution proof requires a different
    unification path.
    """

    def __init__(self, term1: str, term2: str) -> None:
        super().__init__(
            f"Unification failed: cannot unify {term1} with {term2}"
        )
        self.error_code = "EFP-TP01"


class ResolutionExhaustionError(TheoremProverError):
    """Raised when the resolution engine exhausts its clause or step budget.

    This does not necessarily mean the conjecture is false; it may
    simply mean that the proof requires more resources than allocated.
    In practice, if a FizzBuzz theorem cannot be proved within 10,000
    resolution steps, the axiomatization should be reviewed.
    """

    def __init__(self, theorem_name: str, clauses: int, steps: int) -> None:
        super().__init__(
            f"Resolution exhausted for '{theorem_name}': "
            f"{clauses} clauses, {steps} steps without deriving empty clause"
        )
        self.error_code = "EFP-TP02"


class CNFConversionError(TheoremProverError):
    """Raised when a formula cannot be converted to Clause Normal Form.

    This may occur with malformed formulae that have missing operands
    or invalid nesting. All well-formed first-order formulae are
    convertible to CNF, so this error indicates a bug in formula
    construction.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"CNF conversion failed: {reason}")
        self.error_code = "EFP-TP03"


class SkolemizationError(TheoremProverError):
    """Raised when Skolemization encounters an invalid quantifier structure.

    Skolemization replaces existentially quantified variables with
    Skolem functions parameterized by enclosing universally quantified
    variables. This error indicates a quantifier nesting anomaly.
    """

    def __init__(self, variable: str, reason: str) -> None:
        super().__init__(
            f"Skolemization failed for variable '{variable}': {reason}"
        )
        self.error_code = "EFP-TP04"


# ============================================================
# Regex Engine Exceptions
# ============================================================


class RegexEngineError(FizzBuzzError):
    """Base exception for the FizzRegex regular expression engine.

    All errors originating from the Thompson NFA construction, Rabin-Scott
    DFA compilation, Hopcroft minimization, or DFA matching phases inherit
    from this class. The regex engine is a critical classification validation
    component, and failures here indicate that pattern matching integrity
    may be compromised.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-RX00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class RegexPatternSyntaxError(RegexEngineError):
    """Raised when the regex parser encounters invalid pattern syntax.

    The recursive-descent parser found a token sequence that does not
    conform to the regex grammar. Common causes include unmatched
    parentheses, trailing backslashes, and missing bracket closures.
    """

    def __init__(self, pattern: str, position: int, detail: str) -> None:
        super().__init__(
            f"Syntax error in pattern {pattern!r} at position {position}: {detail}",
            error_code="EFP-RX01",
            context={"pattern": pattern, "position": position},
        )
        self.pattern = pattern
        self.position = position


class RegexCompilationError(RegexEngineError):
    """Raised when the NFA-to-DFA compilation pipeline fails.

    This may occur during Thompson's construction (unknown AST node),
    Rabin-Scott subset construction (state explosion beyond limits),
    or Hopcroft minimization (partition refinement anomaly).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Regex compilation failed: {detail}",
            error_code="EFP-RX02",
            context={"detail": detail},
        )


# ============================================================
# Spreadsheet Engine Exceptions (EFP-SS*)
# ============================================================


class SpreadsheetError(FizzBuzzError):
    """Base exception for all FizzSheet spreadsheet engine errors.

    The spreadsheet engine is a mission-critical component of the FizzBuzz
    analytics pipeline. Any failure in cell evaluation, formula parsing,
    or dependency resolution warrants its own exception hierarchy to
    facilitate precise incident triage and root-cause analysis.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-SS00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SpreadsheetCellReferenceError(SpreadsheetError):
    """Raised when a cell reference is invalid or out of bounds.

    Cell references must conform to A1 notation: a single uppercase letter
    (A-Z) followed by a row number (1-999). References outside this range
    are rejected to prevent unbounded memory allocation and to maintain
    the structural integrity of the FizzBuzz analytics grid.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Invalid cell reference: {detail}",
            error_code="EFP-SS01",
            context={"detail": detail},
        )


class SpreadsheetFormulaParseError(SpreadsheetError):
    """Raised when the recursive-descent formula parser encounters invalid syntax.

    The formula parser expects well-formed expressions beginning with '='
    and conforming to standard spreadsheet formula grammar. Common causes
    include unmatched parentheses, missing function arguments, and
    invalid operator sequences.
    """

    def __init__(self, detail: str, *, position: int = -1) -> None:
        super().__init__(
            f"Formula parse error at position {position}: {detail}",
            error_code="EFP-SS02",
            context={"detail": detail, "position": position},
        )
        self.position = position


class SpreadsheetCircularReferenceError(SpreadsheetError):
    """Raised when the dependency graph contains a cycle.

    Circular references make topological sorting impossible and would
    cause infinite recalculation loops. The cycle detector uses DFS-based
    three-color marking to identify the offending cells. All cells
    participating in the cycle receive the #CIRCULAR! error value.
    """

    def __init__(self, cells: list[str]) -> None:
        cell_list = ", ".join(cells)
        super().__init__(
            f"Circular reference detected involving cells: {cell_list}",
            error_code="EFP-SS03",
            context={"cells": cells},
        )
        self.cells = cells


class SpreadsheetFunctionError(SpreadsheetError):
    """Raised when a built-in spreadsheet function encounters an error.

    This may occur due to incorrect argument counts, incompatible
    argument types, or domain errors (such as division by zero in
    AVERAGE with an empty range). Each function validates its inputs
    independently to provide precise error diagnostics.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Function error: {detail}",
            error_code="EFP-SS04",
            context={"detail": detail},
        )


class SpreadsheetRangeError(SpreadsheetError):
    """Raised when a range operation specifies invalid bounds.

    Range operations include cell range references (A1:B5), row/column
    insertion, and row/column deletion. The bounds must fall within
    the grid dimensions (A-Z columns, 1-999 rows).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Range error: {detail}",
            error_code="EFP-SS05",
            context={"detail": detail},
        )


# ---------------------------------------------------------------------------
# Smart Contract Exceptions (EFP-SC*)
# ---------------------------------------------------------------------------


class SmartContractError(FizzBuzzError):
    """Base exception for all smart contract subsystem errors.

    The FizzContract VM requires a dedicated exception hierarchy to
    distinguish between compilation failures, deployment issues,
    execution errors, gas exhaustion, and governance violations.
    Each failure mode demands a different recovery strategy.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-SC00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SmartContractCompilationError(SmartContractError):
    """Raised when the FizzSolidity compiler encounters a syntax or semantic error.

    Compilation errors prevent contract deployment and must be resolved
    before the FizzBuzz classification logic can be executed on-chain.
    The error includes the offending line number and a description of
    the issue to facilitate rapid debugging.
    """

    def __init__(self, reason: str, line: int) -> None:
        super().__init__(
            f"Compilation error at line {line}: {reason}",
            error_code="EFP-SC01",
            context={"reason": reason, "line": line},
        )
        self.reason = reason
        self.line = line


class SmartContractDeploymentError(SmartContractError):
    """Raised when contract deployment fails.

    Deployment failures can occur due to address collisions (statistically
    improbable with SHA-256), invalid bytecode, or insufficient deployer
    permissions. The contract address is included for diagnostic purposes.
    """

    def __init__(self, reason: str, address: str) -> None:
        super().__init__(
            f"Deployment failed at {address}: {reason}",
            error_code="EFP-SC02",
            context={"reason": reason, "address": address},
        )
        self.reason = reason
        self.address = address


class SmartContractExecutionError(SmartContractError):
    """Raised when contract execution encounters a runtime error.

    Runtime errors include invalid opcodes, missing contracts, and
    self-destructed contract access attempts. Unlike out-of-gas errors,
    execution errors indicate a defect in the contract logic itself.
    """

    def __init__(self, reason: str, address: str = "") -> None:
        super().__init__(
            f"Execution error{' at ' + address if address else ''}: {reason}",
            error_code="EFP-SC03",
            context={"reason": reason, "address": address},
        )
        self.reason = reason
        self.address = address


class SmartContractOutOfGasError(SmartContractError):
    """Raised when contract execution exhausts its gas allocation.

    Gas exhaustion triggers an automatic revert of all state changes
    made during the transaction, preserving storage consistency. The
    error includes the gas limit, gas consumed, and the opcode that
    caused the exhaustion, enabling precise gas estimation for future
    transactions.
    """

    def __init__(
        self, gas_limit: int, gas_used: int, opcode_name: str, gas_cost: int,
    ) -> None:
        super().__init__(
            f"Out of gas: {opcode_name} costs {gas_cost} gas, "
            f"but only {gas_limit - gas_used} remaining "
            f"(limit: {gas_limit}, used: {gas_used})",
            error_code="EFP-SC04",
            context={
                "gas_limit": gas_limit,
                "gas_used": gas_used,
                "opcode_name": opcode_name,
                "gas_cost": gas_cost,
            },
        )
        self.gas_limit = gas_limit
        self.gas_used = gas_used
        self.opcode_name = opcode_name
        self.gas_cost = gas_cost


class SmartContractStackOverflowError(SmartContractError):
    """Raised when the execution stack exceeds the 1024-depth limit.

    The stack depth limit prevents unbounded memory consumption during
    deeply nested computations. In practice, FizzBuzz classification
    should never approach this limit, but enterprise software must
    guard against all conceivable failure modes.
    """

    def __init__(self, depth: int) -> None:
        super().__init__(
            f"Stack overflow: maximum depth of {depth} exceeded",
            error_code="EFP-SC05",
            context={"depth": depth},
        )
        self.depth = depth


class SmartContractStackUnderflowError(SmartContractError):
    """Raised when an opcode attempts to pop from an empty stack.

    Stack underflow indicates a bytecode generation defect where an
    opcode expects more operands than are available. This is always
    a compiler bug or a hand-assembled bytecode error.
    """

    def __init__(self) -> None:
        super().__init__(
            "Stack underflow: attempted to pop from empty stack",
            error_code="EFP-SC06",
        )


class SmartContractInvalidJumpError(SmartContractError):
    """Raised when a JUMP or JUMPI targets a non-JUMPDEST instruction.

    The EVM requires all jump targets to be explicitly marked with
    JUMPDEST opcodes. This prevents arbitrary code execution by
    ensuring that control flow can only transfer to sanctioned
    program points.
    """

    def __init__(self, pc: int, destination: int) -> None:
        super().__init__(
            f"Invalid jump from PC={pc} to {destination}: "
            f"target is not a JUMPDEST",
            error_code="EFP-SC07",
            context={"pc": pc, "destination": destination},
        )
        self.pc = pc
        self.destination = destination


class SmartContractRevertError(SmartContractError):
    """Raised when a contract explicitly reverts execution.

    The REVERT opcode allows contracts to abort execution with an
    optional reason string, triggering a full state rollback. This
    is the contract's way of saying the transaction is invalid.
    """

    def __init__(self, reason: str = "") -> None:
        super().__init__(
            f"Contract reverted{': ' + reason if reason else ''}",
            error_code="EFP-SC08",
            context={"reason": reason},
        )
        self.reason = reason


class SmartContractStorageError(SmartContractError):
    """Raised when a storage operation fails.

    Storage errors occur when accessing storage for a non-existent
    contract address or when storage quota limits are exceeded.
    """

    def __init__(self, reason: str, address: str = "") -> None:
        super().__init__(
            f"Storage error{' at ' + address if address else ''}: {reason}",
            error_code="EFP-SC09",
            context={"reason": reason, "address": address},
        )
        self.reason = reason
        self.address = address


class SmartContractGovernanceError(SmartContractError):
    """Raised when a governance operation violates protocol rules.

    Governance errors include unauthorized voting, double voting,
    attempting to execute non-passed proposals, and cancellation
    by non-proposers. The governance protocol is strict to prevent
    illegitimate modifications to the FizzBuzz rule set.
    """

    def __init__(self, reason: str, proposal_id: int) -> None:
        super().__init__(
            f"Governance error on proposal #{proposal_id}: {reason}",
            error_code="EFP-SC0A",
            context={"reason": reason, "proposal_id": proposal_id},
        )
        self.reason = reason
        self.proposal_id = proposal_id


# ---------------------------------------------------------------------------
# FizzDNS Authoritative DNS Server Errors (EFP-DNS0 .. EFP-DNS5)
# ---------------------------------------------------------------------------

class DNSError(FizzBuzzError):
    """Base exception for all FizzDNS Authoritative DNS Server errors.

    DNS is the foundational layer of the enterprise FizzBuzz service
    discovery infrastructure. Errors at this layer indicate failures
    in zone loading, wire format encoding, query resolution, or
    negative cache operations that could prevent clients from
    resolving FizzBuzz classifications via DNS.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DNS0"),
            context=kwargs.pop("context", {}),
        )


class DNSZoneLoadError(DNSError):
    """Raised when a DNS zone fails to load or parse.

    Zone loading failures prevent the authoritative DNS server from
    serving records for the affected domain. Without a properly loaded
    zone, all queries for that domain will receive SERVFAIL responses,
    effectively taking the FizzBuzz DNS service offline for that zone.
    """

    def __init__(self, zone_origin: str, reason: str) -> None:
        super().__init__(
            f"Failed to load zone '{zone_origin}': {reason}",
            error_code="EFP-DNS1",
            context={"zone_origin": zone_origin, "reason": reason},
        )
        self.zone_origin = zone_origin
        self.reason = reason


class DNSWireFormatError(DNSError):
    """Raised when DNS wire format encoding or decoding fails.

    Wire format errors indicate malformed DNS messages that cannot
    be parsed according to RFC 1035. This includes truncated headers,
    invalid compression pointers, and label length violations.
    """

    def __init__(self, reason: str, offset: int = -1) -> None:
        super().__init__(
            f"DNS wire format error at offset {offset}: {reason}" if offset >= 0
            else f"DNS wire format error: {reason}",
            error_code="EFP-DNS2",
            context={"reason": reason, "offset": offset},
        )
        self.reason = reason
        self.offset = offset


class DNSQueryResolutionError(DNSError):
    """Raised when the DNS resolver encounters an internal error.

    Resolution errors are distinct from NXDOMAIN or REFUSED responses,
    which are normal DNS protocol outcomes. This exception indicates
    an unexpected failure in the resolution logic itself.
    """

    def __init__(self, qname: str, qtype: str, reason: str) -> None:
        super().__init__(
            f"Failed to resolve {qname} {qtype}: {reason}",
            error_code="EFP-DNS3",
            context={"qname": qname, "qtype": qtype, "reason": reason},
        )
        self.qname = qname
        self.qtype = qtype
        self.reason = reason


class DNSNegativeCacheError(DNSError):
    """Raised when the negative cache encounters a consistency violation.

    The NSEC-style negative cache maintains authenticated denial-of-
    existence records. If these records become inconsistent with the
    authoritative zone data, the cache must be invalidated to prevent
    serving stale negative responses.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Negative cache consistency violation: {reason}",
            error_code="EFP-DNS4",
            context={"reason": reason},
        )
        self.reason = reason


class DNSZoneTransferError(DNSError):
    """Raised when a zone transfer operation fails.

    Zone transfers (AXFR/IXFR) are used to replicate zone data between
    primary and secondary name servers. Transfer failures can lead to
    stale zone data on secondary servers, resulting in inconsistent
    FizzBuzz classification responses across the DNS infrastructure.
    """

    def __init__(self, zone_origin: str, reason: str) -> None:
        super().__init__(
            f"Zone transfer failed for '{zone_origin}': {reason}",
            error_code="EFP-DNS5",
            context={"zone_origin": zone_origin, "reason": reason},
        )
        self.zone_origin = zone_origin
        self.reason = reason


class ShaderError(FizzBuzzError):
    """Base exception for all FizzShader GPU subsystem errors.

    GPU shader compilation and execution errors are surfaced through
    this hierarchy. In a production deployment, shader compilation
    failures would trigger a fallback to the CPU-based rule engine,
    though this represents a significant regression in computational
    parallelism for FizzBuzz classification.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-GPU0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ShaderCompilationError(ShaderError):
    """Raised when the FizzGLSL compiler fails to compile a shader.

    Shader compilation errors can be caused by invalid GLSL syntax,
    unsupported shader features, or resource limit violations. Each
    error includes the source line number and a descriptive message
    to aid in debugging the shader code.
    """

    def __init__(self, source_line: int, errors: list[str]) -> None:
        error_text = "; ".join(errors)
        super().__init__(
            f"Shader compilation failed at line {source_line}: {error_text}",
            error_code="EFP-GPU1",
            context={"source_line": source_line, "errors": errors},
        )
        self.source_line = source_line
        self.compilation_errors = errors


class ShaderExecutionError(ShaderError):
    """Raised when the virtual GPU encounters a runtime error during execution.

    Runtime errors include illegal memory accesses, register file overflow,
    infinite loop detection, and warp scheduling deadlocks. These indicate
    a defect in the shader program or the virtual GPU simulator itself.
    """

    def __init__(self, core_id: int, warp_id: int, reason: str) -> None:
        super().__init__(
            f"Shader execution error on core {core_id}, warp {warp_id}: {reason}",
            error_code="EFP-GPU2",
            context={"core_id": core_id, "warp_id": warp_id, "reason": reason},
        )
        self.core_id = core_id
        self.warp_id = warp_id
        self.reason = reason


class WarpDivergenceError(ShaderError):
    """Raised when warp divergence exceeds the configured threshold.

    Excessive divergence indicates that threads within warps are taking
    different branch paths at an alarming rate. For FizzBuzz classification,
    divergence is inherent (numbers have different divisibility properties),
    but catastrophic divergence suggests a compiler or scheduler defect.
    """

    def __init__(self, warp_id: int, divergence_rate: float) -> None:
        super().__init__(
            f"Warp {warp_id} divergence rate {divergence_rate:.1%} exceeds "
            f"acceptable threshold for FizzBuzz workload",
            error_code="EFP-GPU3",
            context={"warp_id": warp_id, "divergence_rate": divergence_rate},
        )
        self.warp_id = warp_id
        self.divergence_rate = divergence_rate


class GPUMemoryError(ShaderError):
    """Raised when a shader accesses memory outside allocated bounds.

    The virtual GPU enforces strict memory bounds checking on all
    load and store operations. Out-of-bounds accesses would cause
    undefined behavior on real GPU hardware; here, they are caught
    and reported with full diagnostic context.
    """

    def __init__(self, address: int, core_id: int, reason: str) -> None:
        super().__init__(
            f"GPU memory error at address 0x{address:08x} on core {core_id}: {reason}",
            error_code="EFP-GPU4",
            context={"address": address, "core_id": core_id, "reason": reason},
        )
        self.address = address
        self.core_id = core_id
        self.reason = reason
