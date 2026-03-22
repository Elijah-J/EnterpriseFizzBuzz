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
    identical results every time. That's kind of the point.
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
    would violate the sacred namespace of the message queue, and
    we simply cannot allow that. Not in this enterprise.
    """

    def __init__(self, topic_name: str) -> None:
        super().__init__(
            f"Topic '{topic_name}' already exists. Topic names are unique "
            f"in this enterprise message queue, just as they are in the real "
            f"Kafka clusters that inspired this unnecessary abstraction.",
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

    The secret scanner, which flags ALL integer literals as potential
    leaked secrets (because clearly the number 42 in a for loop is
    a security vulnerability), has encountered a problem during its
    noble crusade against numeracy.
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
    to endpoints that don't exist — and something in that process
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
# Because deploying a FizzBuzz engine that runs for 0.8 seconds
# and processes exactly one range of numbers requires the same
# blue/green deployment ceremony as a fleet of microservices
# serving millions of requests. Zero downtime for a process
# that has zero users. THIS IS THE JOKE.
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
    Attempting to skip a phase or go backwards violates the sacred
    deployment ceremony, and the orchestrator refuses to participate
    in such recklessness.
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
    relationships encounters an error, you've reached a level of
    over-engineered failure that most computer scientists can only
    dream of. These exceptions cover everything from node creation
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
    NLQ roadmap prioritizes other features, like adding more satirical
    error messages to the exception hierarchy.
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
