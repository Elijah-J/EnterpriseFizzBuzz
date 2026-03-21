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
