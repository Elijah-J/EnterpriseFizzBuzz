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


class TracingError(FizzBuzzError):
    """Base exception for all distributed tracing errors.

    When your observability layer itself becomes unobservable,
    you've reached a level of meta-failure that most enterprise
    architectures can only dream of.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-T000"),
            context=kwargs.pop("context", {}),
        )


class SpanNotFoundError(TracingError):
    """Raised when a referenced span cannot be located in the trace.

    The span was here a moment ago. It was right here. We saw it.
    And now it's gone, like tears in rain, or like a FizzBuzz result
    that nobody bothered to log.
    """

    def __init__(self, span_id: str) -> None:
        super().__init__(
            f"Span '{span_id}' not found in trace. It may have been "
            f"garbage collected by an overzealous span reaper.",
            error_code="EFP-T001",
            context={"span_id": span_id},
        )
        self.span_id = span_id


class TraceNotFoundError(TracingError):
    """Raised when a referenced trace cannot be located.

    An entire trace has vanished. Not just a span — the whole trace.
    This is the distributed tracing equivalent of losing an entire
    filing cabinet instead of just one folder.
    """

    def __init__(self, trace_id: str) -> None:
        super().__init__(
            f"Trace '{trace_id}' not found. The trace may have already "
            f"been exported, or it never existed in the first place.",
            error_code="EFP-T002",
            context={"trace_id": trace_id},
        )
        self.trace_id = trace_id


class TraceAlreadyActiveError(TracingError):
    """Raised when attempting to start a trace while one is already active.

    You cannot begin a new trace when the current one hasn't ended.
    This is distributed tracing, not distributed multitasking.
    One existential crisis at a time, please.
    """

    def __init__(self, existing_trace_id: str) -> None:
        super().__init__(
            f"Cannot start new trace: trace '{existing_trace_id}' is "
            f"already active. End the current trace first.",
            error_code="EFP-T003",
            context={"existing_trace_id": existing_trace_id},
        )
        self.existing_trace_id = existing_trace_id


class SpanLifecycleError(TracingError):
    """Raised when a span operation violates the span lifecycle contract.

    Spans have a strict lifecycle: created → started → ended.
    Attempting to end a span that was never started, or start one
    that's already ended, is the temporal equivalent of dividing
    by zero — which, unlike dividing by 3 or 5, we do not support.
    """

    def __init__(self, span_name: str, operation: str, reason: str) -> None:
        super().__init__(
            f"Span '{span_name}' lifecycle violation during '{operation}': {reason}",
            error_code="EFP-T004",
            context={"span_name": span_name, "operation": operation},
        )
        self.span_name = span_name
        self.operation = operation


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
    arithmetic has been performed (ironic, given the context), and
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
    selecting a victim, composing a eulogy, and ceremonially removing
    the entry from memory. It's like a reality TV elimination round,
    but for modulo results.
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
    The result of 15 % 3 hasn't changed, of course, but the TTL policy
    doesn't care about mathematical constants — only about timestamps.
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
            f"The cache remains cold, which is ironic because warming it "
            f"was pointless anyway.",
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
    void. These are all violations of the sacred schema contract
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
    eulogy generator has failed in its sacred duty. The entry will be
    evicted without ceremony, without remembrance, without a single
    word spoken in its honor. This is the saddest failure mode in
    the entire Enterprise FizzBuzz Platform.
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

    When your IoC container — the thing responsible for wiring together
    your over-engineered FizzBuzz components — itself encounters an
    error, you've achieved a level of infrastructure failure that would
    make even the most seasoned Spring Framework developer shed a tear.
    The container was supposed to simplify construction. Instead, it
    has added an entirely new category of ways things can go wrong.
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
# Because monitoring the health of a FizzBuzz platform requires
# its own exception hierarchy. When your health check system
# itself becomes unhealthy, you've reached the final boss of
# enterprise over-engineering.
# ============================================================


class HealthCheckError(FizzBuzzError):
    """Base exception for all Kubernetes-style health check errors.

    When the system designed to tell you whether FizzBuzz is healthy
    encounters its own failure, you've reached a philosophical impasse
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
    commit or rollback, exit. Deviating from this sacred lifecycle
    is an affront to Martin Fowler and everyone who ever drew a
    UML sequence diagram of a transaction boundary.
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
    the first place. The answer, of course, is yes — because what
    gets measured gets managed, and what gets managed gets a 1200-line
    Python module with four metric types and an ASCII Grafana dashboard.
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
    or perform some other operation that violates the sacred contract
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
    refused to cooperate. The payload has been sentenced to the
    Dead Letter Queue, where it will reside for eternity alongside
    other permanently failed deliveries and unfulfilled dreams.
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
