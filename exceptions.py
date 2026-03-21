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
