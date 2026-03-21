"""
Enterprise FizzBuzz Platform - Configuration Management Module

Implements a Singleton-based configuration manager with YAML loading,
environment variable overrides, and runtime validation.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from exceptions import (
    ConfigurationError,
    ConfigurationFileNotFoundError,
    ConfigurationValidationError,
)
from models import EvaluationStrategy, LogLevel, OutputFormat, RuleDefinition

logger = logging.getLogger(__name__)

# Default config path, overridable via environment variable
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class _SingletonMeta(type):
    """Metaclass implementing the Singleton pattern.

    Ensures that only one instance of the ConfigurationManager exists
    across the entire application lifecycle.
    """

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def reset(mcs) -> None:
        """Reset all singleton instances. Used for testing."""
        mcs._instances.clear()


class ConfigurationManager(metaclass=_SingletonMeta):
    """Singleton configuration manager for the Enterprise FizzBuzz Platform.

    Loads configuration from YAML, applies environment variable overrides,
    and provides validated, typed access to all configuration values.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._config_path = Path(
            config_path
            or os.environ.get("EFP_CONFIG_PATH", str(_DEFAULT_CONFIG_PATH))
        )
        self._raw_config: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> ConfigurationManager:
        """Load and validate configuration from YAML file."""
        try:
            import yaml
        except ImportError:
            # Fallback to built-in defaults if PyYAML is not installed
            logger.warning(
                "PyYAML not installed. Using built-in default configuration."
            )
            self._raw_config = self._get_defaults()
            self._apply_environment_overrides()
            self._validate()
            self._loaded = True
            return self

        if not self._config_path.exists():
            raise ConfigurationFileNotFoundError(str(self._config_path))

        with open(self._config_path, "r") as f:
            self._raw_config = yaml.safe_load(f) or {}

        self._apply_environment_overrides()
        self._validate()
        self._loaded = True
        logger.info("Configuration loaded from %s", self._config_path)
        return self

    def _get_defaults(self) -> dict[str, Any]:
        """Return built-in default configuration."""
        return {
            "application": {
                "name": "Enterprise FizzBuzz Platform",
                "version": "1.0.0",
                "environment": "production",
            },
            "range": {"start": 1, "end": 100},
            "rules": [
                {"name": "FizzRule", "divisor": 3, "label": "Fizz", "priority": 1},
                {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
            ],
            "engine": {
                "strategy": "standard",
                "max_concurrent_evaluations": 10,
                "timeout_ms": 5000,
            },
            "output": {
                "format": "plain",
                "include_metadata": False,
                "include_summary": True,
                "colorize": False,
            },
            "logging": {
                "level": "INFO",
                "include_timestamps": True,
                "log_to_file": False,
                "log_file_path": "fizzbuzz.log",
            },
            "middleware": {
                "timing": {"enabled": True, "priority": 1},
                "logging": {"enabled": True, "priority": 2},
                "validation": {"enabled": True, "priority": 0},
            },
            "plugins": {
                "auto_discover": True,
                "plugin_directory": "./plugins",
                "enabled_plugins": [],
            },
            "circuit_breaker": {
                "enabled": False,
                "failure_threshold": 5,
                "success_threshold": 3,
                "timeout_ms": 30000,
                "sliding_window_size": 10,
                "half_open_max_calls": 3,
                "backoff_base_ms": 1000,
                "backoff_max_ms": 60000,
                "backoff_multiplier": 2.0,
                "ml_confidence_threshold": 0.7,
                "call_timeout_ms": 5000,
            },
            "i18n": {
                "enabled": True,
                "locale": "en",
                "locale_directory": "./locales",
                "strict_mode": False,
                "fallback_chain": ["en"],
                "log_missing_keys": True,
            },
            "rbac": {
                "enabled": False,
                "default_role": "ANONYMOUS",
                "token_secret": "enterprise-fizzbuzz-secret-do-not-share",
                "token_ttl_seconds": 3600,
                "token_issuer": "enterprise-fizzbuzz-platform",
                "access_denied_contact_email": "fizzbuzz-security@enterprise.example.com",
                "next_training_session": "2026-04-01T09:00:00Z",
            },
            "tracing": {
                "enabled": False,
                "export_format": "waterfall",
                "waterfall_width": 60,
                "timing_precision": "us",
            },
            "event_sourcing": {
                "enabled": False,
                "snapshot_interval": 10,
                "max_events_before_compaction": 1000,
                "enable_temporal_queries": True,
                "enable_projections": True,
                "event_version": 1,
            },
            "chaos": {
                "enabled": False,
                "level": 1,
                "fault_types": [
                    "RESULT_CORRUPTION",
                    "LATENCY_INJECTION",
                    "EXCEPTION_INJECTION",
                    "RULE_ENGINE_FAILURE",
                    "CONFIDENCE_MANIPULATION",
                ],
                "latency": {
                    "min_ms": 10,
                    "max_ms": 500,
                },
                "seed": None,
            },
            "feature_flags": {
                "enabled": False,
                "default_lifecycle": "ACTIVE",
                "log_evaluations": True,
                "strict_dependencies": True,
                "predefined_flags": {
                    "fizz_rule_enabled": {
                        "type": "BOOLEAN",
                        "enabled": True,
                        "description": "Controls the sacred Fizz rule (divisor=3)",
                    },
                    "buzz_rule_enabled": {
                        "type": "BOOLEAN",
                        "enabled": True,
                        "description": "Controls the venerable Buzz rule (divisor=5)",
                    },
                    "wuzz_rule_experimental": {
                        "type": "PERCENTAGE",
                        "enabled": True,
                        "percentage": 30,
                        "description": "Experimental Wuzz rule (divisor=7) -- 30% progressive rollout",
                    },
                    "wuzz_prime_targeting": {
                        "type": "TARGETING",
                        "enabled": True,
                        "targeting_rule": "prime",
                        "description": "Wuzz targeting: only activates for prime numbers",
                        "dependencies": ["wuzz_rule_experimental"],
                    },
                    "ml_strategy_canary": {
                        "type": "PERCENTAGE",
                        "enabled": False,
                        "percentage": 10,
                        "description": "Canary rollout for ML evaluation strategy",
                    },
                    "blockchain_audit": {
                        "type": "BOOLEAN",
                        "enabled": False,
                        "description": "Toggle blockchain audit ledger at runtime",
                    },
                    "tracing_enabled": {
                        "type": "BOOLEAN",
                        "enabled": False,
                        "description": "Toggle distributed tracing at runtime",
                    },
                },
            },
            "sla": {
                "enabled": False,
                "slos": {
                    "latency": {
                        "target": 0.999,
                        "threshold_ms": 100.0,
                    },
                    "accuracy": {
                        "target": 0.99999,
                    },
                    "availability": {
                        "target": 0.9999,
                    },
                },
                "error_budget": {
                    "window_days": 30,
                    "burn_rate_threshold": 2.0,
                },
                "alerting": {
                    "cooldown_seconds": 60,
                    "escalation_timeout_seconds": 300,
                },
                "on_call": {
                    "team_name": "FizzBuzz Reliability Engineering",
                    "rotation_interval_hours": 168,
                    "engineers": [
                        {
                            "name": "Bob McFizzington",
                            "email": "bob.mcfizzington@enterprise.example.com",
                            "phone": "+1-555-FIZZBUZZ",
                            "title": "Senior Principal Staff FizzBuzz Reliability Engineer II",
                        },
                    ],
                },
            },
            "cache": {
                "enabled": False,
                "max_size": 1024,
                "ttl_seconds": 3600.0,
                "eviction_policy": "lru",
                "enable_coherence_protocol": True,
                "enable_eulogies": True,
                "warming": {
                    "enabled": False,
                    "range_start": 1,
                    "range_end": 100,
                },
            },
            "observers": {
                "console_observer": {"enabled": False},
                "statistics_observer": {"enabled": True},
            },
        }

    def _apply_environment_overrides(self) -> None:
        """Apply environment variable overrides to configuration.

        Environment variables follow the pattern EFP_<SECTION>_<KEY>.
        Example: EFP_RANGE_START=1, EFP_OUTPUT_FORMAT=json
        """
        env_mappings = {
            "EFP_RANGE_START": ("range", "start", int),
            "EFP_RANGE_END": ("range", "end", int),
            "EFP_OUTPUT_FORMAT": ("output", "format", str),
            "EFP_LOG_LEVEL": ("logging", "level", str),
            "EFP_STRATEGY": ("engine", "strategy", str),
            "EFP_LOCALE": ("i18n", "locale", str),
            "EFP_TRACING_ENABLED": ("tracing", "enabled", lambda v: v.lower() in ("true", "1", "yes")),
        }

        for env_var, (section, key, cast) in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                try:
                    self._raw_config.setdefault(section, {})[key] = cast(value)
                    logger.debug(
                        "Environment override: %s=%s", env_var, value
                    )
                except (ValueError, TypeError) as e:
                    raise ConfigurationValidationError(
                        env_var, value, cast.__name__
                    ) from e

    def _validate(self) -> None:
        """Validate all configuration values."""
        range_cfg = self._raw_config.get("range", {})
        start = range_cfg.get("start", 1)
        end = range_cfg.get("end", 100)
        if not isinstance(start, int) or not isinstance(end, int):
            raise ConfigurationValidationError(
                "range.start/end", f"{start}/{end}", "int"
            )
        if start > end:
            raise ConfigurationValidationError(
                "range", f"start={start} > end={end}", "start <= end"
            )

        output_format = self._raw_config.get("output", {}).get("format", "plain")
        valid_formats = {"plain", "json", "xml", "csv"}
        if output_format not in valid_formats:
            raise ConfigurationValidationError(
                "output.format", output_format, f"one of {valid_formats}"
            )

        strategy = self._raw_config.get("engine", {}).get("strategy", "standard")
        valid_strategies = {"standard", "chain_of_responsibility", "parallel_async", "machine_learning"}
        if strategy not in valid_strategies:
            raise ConfigurationValidationError(
                "engine.strategy", strategy, f"one of {valid_strategies}"
            )

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise ConfigurationError("Configuration not loaded. Call load() first.")

    @property
    def app_name(self) -> str:
        self._ensure_loaded()
        return self._raw_config["application"]["name"]

    @property
    def app_version(self) -> str:
        self._ensure_loaded()
        return self._raw_config["application"]["version"]

    @property
    def range_start(self) -> int:
        self._ensure_loaded()
        return self._raw_config["range"]["start"]

    @property
    def range_end(self) -> int:
        self._ensure_loaded()
        return self._raw_config["range"]["end"]

    @property
    def rules(self) -> list[RuleDefinition]:
        self._ensure_loaded()
        return [
            RuleDefinition(
                name=r["name"],
                divisor=r["divisor"],
                label=r["label"],
                priority=r.get("priority", 0),
            )
            for r in self._raw_config.get("rules", [])
        ]

    @property
    def evaluation_strategy(self) -> EvaluationStrategy:
        self._ensure_loaded()
        strategy_map = {
            "standard": EvaluationStrategy.STANDARD,
            "chain_of_responsibility": EvaluationStrategy.CHAIN_OF_RESPONSIBILITY,
            "parallel_async": EvaluationStrategy.PARALLEL_ASYNC,
            "machine_learning": EvaluationStrategy.MACHINE_LEARNING,
        }
        return strategy_map[self._raw_config["engine"]["strategy"]]

    @property
    def output_format(self) -> OutputFormat:
        self._ensure_loaded()
        format_map = {
            "plain": OutputFormat.PLAIN,
            "json": OutputFormat.JSON,
            "xml": OutputFormat.XML,
            "csv": OutputFormat.CSV,
        }
        return format_map[self._raw_config["output"]["format"]]

    @property
    def log_level(self) -> LogLevel:
        self._ensure_loaded()
        level_map = {
            "SILENT": LogLevel.SILENT,
            "ERROR": LogLevel.ERROR,
            "WARNING": LogLevel.WARNING,
            "INFO": LogLevel.INFO,
            "DEBUG": LogLevel.DEBUG,
            "TRACE": LogLevel.TRACE,
        }
        return level_map.get(
            self._raw_config.get("logging", {}).get("level", "INFO"),
            LogLevel.INFO,
        )

    @property
    def include_summary(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("output", {}).get("include_summary", True)

    @property
    def include_metadata(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("output", {}).get("include_metadata", False)

    @property
    def circuit_breaker_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("enabled", False)

    @property
    def circuit_breaker_failure_threshold(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("failure_threshold", 5)

    @property
    def circuit_breaker_success_threshold(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("success_threshold", 3)

    @property
    def circuit_breaker_timeout_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("timeout_ms", 30000)

    @property
    def circuit_breaker_sliding_window_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("sliding_window_size", 10)

    @property
    def circuit_breaker_half_open_max_calls(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("half_open_max_calls", 3)

    @property
    def circuit_breaker_backoff_base_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("backoff_base_ms", 1000)

    @property
    def circuit_breaker_backoff_max_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("backoff_max_ms", 60000)

    @property
    def circuit_breaker_backoff_multiplier(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("backoff_multiplier", 2.0)

    @property
    def circuit_breaker_ml_confidence_threshold(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("ml_confidence_threshold", 0.7)

    @property
    def circuit_breaker_call_timeout_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("call_timeout_ms", 5000)

    @property
    def tracing_enabled(self) -> bool:
        """Whether the distributed tracing subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("tracing", {}).get("enabled", False)

    @property
    def tracing_export_format(self) -> str:
        """Export format for traces: 'waterfall' or 'json'."""
        self._ensure_loaded()
        return self._raw_config.get("tracing", {}).get("export_format", "waterfall")

    @property
    def tracing_waterfall_width(self) -> int:
        """Character width of the waterfall timeline bar."""
        self._ensure_loaded()
        return self._raw_config.get("tracing", {}).get("waterfall_width", 60)

    @property
    def tracing_timing_precision(self) -> str:
        """Timing precision: 'us' (microseconds) or 'ns' (nanoseconds)."""
        self._ensure_loaded()
        return self._raw_config.get("tracing", {}).get("timing_precision", "us")

    @property
    def i18n_enabled(self) -> bool:
        """Whether the internationalization subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("enabled", True)

    @property
    def i18n_locale(self) -> str:
        """The active locale code (e.g. 'en', 'fr', 'tlh')."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("locale", "en")

    @property
    def i18n_locale_directory(self) -> str:
        """Path to the directory containing .fizztranslation files."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("locale_directory", "./locales")

    @property
    def i18n_strict_mode(self) -> bool:
        """Whether missing translation keys should raise errors."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("strict_mode", False)

    @property
    def i18n_fallback_chain(self) -> list[str]:
        """Global fallback chain for locale resolution."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("fallback_chain", ["en"])

    @property
    def i18n_log_missing_keys(self) -> bool:
        """Whether to log warnings for missing translation keys."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("log_missing_keys", True)

    @property
    def rbac_enabled(self) -> bool:
        """Whether Role-Based Access Control is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get("enabled", False)

    @property
    def rbac_default_role(self) -> str:
        """The default role for unauthenticated users."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get("default_role", "ANONYMOUS")

    @property
    def rbac_token_secret(self) -> str:
        """The HMAC secret for token signing and validation."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get(
            "token_secret", "enterprise-fizzbuzz-secret-do-not-share"
        )

    @property
    def rbac_token_ttl_seconds(self) -> int:
        """Token time-to-live in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get("token_ttl_seconds", 3600)

    @property
    def rbac_token_issuer(self) -> str:
        """Token issuer identifier."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get(
            "token_issuer", "enterprise-fizzbuzz-platform"
        )

    @property
    def rbac_access_denied_contact_email(self) -> str:
        """Contact email for access denied responses."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get(
            "access_denied_contact_email", "fizzbuzz-security@enterprise.example.com"
        )

    @property
    def rbac_next_training_session(self) -> str:
        """Next available RBAC training session datetime."""
        self._ensure_loaded()
        return self._raw_config.get("rbac", {}).get(
            "next_training_session", "2026-04-01T09:00:00Z"
        )

    @property
    def event_sourcing_enabled(self) -> bool:
        """Whether the Event Sourcing / CQRS subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get("enabled", False)

    @property
    def event_sourcing_snapshot_interval(self) -> int:
        """Number of events between automatic snapshots."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get("snapshot_interval", 10)

    @property
    def event_sourcing_max_events_before_compaction(self) -> int:
        """Maximum events before the store considers compaction."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get(
            "max_events_before_compaction", 1000
        )

    @property
    def event_sourcing_enable_temporal_queries(self) -> bool:
        """Whether point-in-time state reconstruction is available."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get(
            "enable_temporal_queries", True
        )

    @property
    def event_sourcing_enable_projections(self) -> bool:
        """Whether materialized read-model projections are maintained."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get("enable_projections", True)

    @property
    def event_sourcing_event_version(self) -> int:
        """Current event schema version for upcasting."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get("event_version", 1)

    @property
    def chaos_enabled(self) -> bool:
        """Whether the Chaos Engineering subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("enabled", False)

    @property
    def chaos_level(self) -> int:
        """Chaos severity level (1-5). 1 = gentle breeze, 5 = category 5 hurricane."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("level", 1)

    @property
    def chaos_fault_types(self) -> list[str]:
        """List of armed fault type names."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("fault_types", [
            "RESULT_CORRUPTION",
            "LATENCY_INJECTION",
            "EXCEPTION_INJECTION",
            "RULE_ENGINE_FAILURE",
            "CONFIDENCE_MANIPULATION",
        ])

    @property
    def chaos_latency_min_ms(self) -> int:
        """Minimum injected latency in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("latency", {}).get("min_ms", 10)

    @property
    def chaos_latency_max_ms(self) -> int:
        """Maximum injected latency in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("latency", {}).get("max_ms", 500)

    @property
    def chaos_seed(self) -> int | None:
        """Random seed for reproducible chaos. None = true entropy."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("seed", None)

    @property
    def feature_flags_enabled(self) -> bool:
        """Whether the Feature Flags subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("feature_flags", {}).get("enabled", False)

    @property
    def feature_flags_default_lifecycle(self) -> str:
        """Default lifecycle state for newly created flags."""
        self._ensure_loaded()
        return self._raw_config.get("feature_flags", {}).get("default_lifecycle", "ACTIVE")

    @property
    def feature_flags_log_evaluations(self) -> bool:
        """Whether to log every flag evaluation for audit compliance."""
        self._ensure_loaded()
        return self._raw_config.get("feature_flags", {}).get("log_evaluations", True)

    @property
    def feature_flags_strict_dependencies(self) -> bool:
        """Whether to enforce dependency graph constraints."""
        self._ensure_loaded()
        return self._raw_config.get("feature_flags", {}).get("strict_dependencies", True)

    @property
    def feature_flags_predefined(self) -> dict[str, Any]:
        """Predefined feature flag definitions from config."""
        self._ensure_loaded()
        return self._raw_config.get("feature_flags", {}).get("predefined_flags", {})

    # ----------------------------------------------------------------
    # SLA Monitoring configuration properties
    # ----------------------------------------------------------------

    @property
    def sla_enabled(self) -> bool:
        """Whether SLA Monitoring is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("enabled", False)

    @property
    def sla_latency_target(self) -> float:
        """SLO target for latency compliance (fraction, e.g. 0.999)."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("slos", {}).get("latency", {}).get("target", 0.999)

    @property
    def sla_latency_threshold_ms(self) -> float:
        """Maximum acceptable latency per evaluation in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("slos", {}).get("latency", {}).get("threshold_ms", 100.0)

    @property
    def sla_accuracy_target(self) -> float:
        """SLO target for accuracy compliance (fraction, e.g. 0.99999)."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("slos", {}).get("accuracy", {}).get("target", 0.99999)

    @property
    def sla_availability_target(self) -> float:
        """SLO target for availability compliance (fraction, e.g. 0.9999)."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("slos", {}).get("availability", {}).get("target", 0.9999)

    @property
    def sla_error_budget_window_days(self) -> int:
        """Rolling window in days for error budget calculation."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("error_budget", {}).get("window_days", 30)

    @property
    def sla_error_budget_burn_rate_threshold(self) -> float:
        """Alert when error budget is burning N times faster than planned."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("error_budget", {}).get("burn_rate_threshold", 2.0)

    @property
    def sla_alerting_cooldown_seconds(self) -> int:
        """Minimum seconds between alerts of the same type."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("alerting", {}).get("cooldown_seconds", 60)

    @property
    def sla_alerting_escalation_timeout_seconds(self) -> int:
        """Seconds before escalating an alert to the next level."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("alerting", {}).get("escalation_timeout_seconds", 300)

    @property
    def sla_on_call_team_name(self) -> str:
        """Name of the on-call team."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("on_call", {}).get(
            "team_name", "FizzBuzz Reliability Engineering"
        )

    @property
    def sla_on_call_rotation_interval_hours(self) -> int:
        """Hours between on-call rotation shifts."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("on_call", {}).get("rotation_interval_hours", 168)

    @property
    def sla_on_call_engineers(self) -> list[dict[str, str]]:
        """List of on-call engineer dicts with name, email, phone, title."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("on_call", {}).get("engineers", [
            {
                "name": "Bob McFizzington",
                "email": "bob.mcfizzington@enterprise.example.com",
                "phone": "+1-555-FIZZBUZZ",
                "title": "Senior Principal Staff FizzBuzz Reliability Engineer II",
            },
        ])

    # ----------------------------------------------------------------
    # Cache configuration properties
    # ----------------------------------------------------------------

    @property
    def cache_enabled(self) -> bool:
        """Whether the in-memory caching layer is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("enabled", False)

    @property
    def cache_max_size(self) -> int:
        """Maximum number of entries in the FizzBuzz result cache."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("max_size", 1024)

    @property
    def cache_ttl_seconds(self) -> float:
        """Time-to-live for cache entries in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("ttl_seconds", 3600.0)

    @property
    def cache_eviction_policy(self) -> str:
        """Eviction policy name: lru, lfu, fifo, or dramatic_random."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("eviction_policy", "lru")

    @property
    def cache_enable_coherence_protocol(self) -> bool:
        """Whether to enable MESI cache coherence state tracking."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("enable_coherence_protocol", True)

    @property
    def cache_enable_eulogies(self) -> bool:
        """Whether to generate satirical eulogies for evicted cache entries."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("enable_eulogies", True)

    @property
    def cache_warming_enabled(self) -> bool:
        """Whether to pre-populate the cache on startup (defeats the purpose)."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("warming", {}).get("enabled", False)

    @property
    def cache_warming_range_start(self) -> int:
        """Start of the range to pre-populate in the cache."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("warming", {}).get("range_start", 1)

    @property
    def cache_warming_range_end(self) -> int:
        """End of the range to pre-populate in the cache."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("warming", {}).get("range_end", 100)

    def get_raw(self, key: str, default: Any = None) -> Any:
        """Get a raw configuration value by dot-separated key path."""
        self._ensure_loaded()
        keys = key.split(".")
        value: Any = self._raw_config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value
