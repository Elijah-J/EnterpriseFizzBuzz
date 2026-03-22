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

from enterprise_fizzbuzz.domain.exceptions import (
    ConfigurationError,
    ConfigurationFileNotFoundError,
    ConfigurationValidationError,
)
from enterprise_fizzbuzz.domain.models import EvaluationStrategy, LogLevel, OutputFormat, RuleDefinition

logger = logging.getLogger(__name__)

# Default config path, overridable via environment variable
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


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
            "migrations": {
                "enabled": False,
                "auto_apply": False,
                "seed_range_start": 1,
                "seed_range_end": 50,
                "log_fake_sql": True,
                "visualize_schema": True,
            },
            "repository": {
                "backend": "none",
                "db_path": "fizzbuzz_results.db",
                "fs_path": "./fizzbuzz_results",
            },
            "ml": {
                "decision_threshold": 0.5,
                "ambiguity_margin": 0.1,
                "enable_disagreement_tracking": False,
            },
            "health_check": {
                "enabled": False,
                "liveness": {
                    "canary_number": 15,
                    "canary_expected": "FizzBuzz",
                    "interval_seconds": 30,
                },
                "readiness": {
                    "required_subsystems": [
                        "config",
                        "circuit_breaker",
                        "cache",
                        "sla",
                        "ml_engine",
                    ],
                    "degraded_is_ready": True,
                },
                "startup": {
                    "milestones": [
                        "config_loaded",
                        "rules_initialized",
                        "engine_created",
                        "middleware_assembled",
                        "service_built",
                    ],
                    "timeout_seconds": 60,
                },
                "self_healing": {
                    "enabled": True,
                    "max_retries": 3,
                    "backoff_base_ms": 500,
                },
                "dashboard": {
                    "width": 60,
                    "show_details": True,
                },
            },
            "metrics": {
                "enabled": False,
                "export_format": "prometheus",
                "cardinality_threshold": 100,
                "default_buckets": [
                    0.001, 0.005, 0.01, 0.025, 0.05, 0.1,
                    0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
                ],
                "dashboard": {
                    "width": 60,
                    "sparkline_length": 20,
                },
                "bob_mcfizzington": {
                    "initial_stress_level": 42.0,
                },
            },
            "webhooks": {
                "enabled": False,
                "endpoints": [],
                "secret": "enterprise-fizzbuzz-webhook-secret-do-not-share",
                "subscribed_events": [
                    "FIZZ_DETECTED",
                    "BUZZ_DETECTED",
                    "FIZZBUZZ_DETECTED",
                    "SESSION_STARTED",
                    "SESSION_ENDED",
                    "ERROR_OCCURRED",
                ],
                "retry": {
                    "max_retries": 3,
                    "backoff_base_ms": 1000,
                    "backoff_multiplier": 2.0,
                    "backoff_max_ms": 30000,
                },
                "dead_letter_queue": {
                    "max_size": 100,
                },
                "simulated_client": {
                    "success_rate_percent": 80,
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "hot_reload": {
                "enabled": False,
                "poll_interval_seconds": 2.0,
                "raft_heartbeat_interval_ms": 150,
                "raft_election_timeout_ms": 300,
                "max_rollback_history": 10,
                "validate_before_apply": True,
                "log_diffs": True,
                "subsystem_reload_timeout_ms": 5000,
                "dashboard": {
                    "width": 60,
                    "show_raft_details": True,
                },
            },
            "rate_limiting": {
                "enabled": False,
                "algorithm": "token_bucket",
                "requests_per_minute": 60,
                "burst_credits": {
                    "enabled": True,
                    "max_credits": 30,
                    "earn_rate": 0.5,
                },
                "reservations": {
                    "enabled": True,
                    "max_reservations": 10,
                    "ttl_seconds": 30,
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "compliance": {
                "enabled": False,
                "sox": {
                    "enabled": True,
                    "segregation_strict": True,
                    "audit_trail_retention_days": 2555,
                    "personnel_roster": [
                        {
                            "name": "Alice Fizzworth",
                            "title": "Senior Fizz Evaluation Specialist",
                            "clearance": "FIZZ_CLEARED",
                        },
                        {
                            "name": "Charlie Buzzman",
                            "title": "Principal Buzz Assessment Engineer",
                            "clearance": "BUZZ_CLEARED",
                        },
                        {
                            "name": "Diana Formatson",
                            "title": "Chief Output Formatting Officer",
                            "clearance": "FORMAT_CLEARED",
                        },
                        {
                            "name": "Eve Auditrix",
                            "title": "Director of FizzBuzz Audit & Compliance",
                            "clearance": "AUDIT_CLEARED",
                        },
                        {
                            "name": "Frank Oversite",
                            "title": "VP of Modulo Governance",
                            "clearance": "OVERSIGHT_CLEARED",
                        },
                    ],
                },
                "gdpr": {
                    "enabled": True,
                    "auto_consent": True,
                    "consent_expiry_days": 365,
                    "data_retention_days": 90,
                    "erasure_enabled": True,
                    "dpo_email": "dpo@enterprise-fizzbuzz.example.com",
                },
                "hipaa": {
                    "enabled": True,
                    "minimum_necessary_level": "OPERATIONS",
                    "encryption_algorithm": "military_grade_base64",
                    "phi_audit_logging": True,
                    "covered_entity": "Enterprise FizzBuzz Healthcare Division",
                },
                "compliance_officer": {
                    "name": "Bob McFizzington",
                    "title": "Chief FizzBuzz Compliance Officer",
                    "email": "bob.compliance@enterprise-fizzbuzz.example.com",
                    "phone": "+1-555-COMPLY",
                    "stress_level": 94.7,
                    "available": False,
                    "certifications": [
                        "Certified FizzBuzz Compliance Auditor (CFCA)",
                        "SOX Section 404 FizzBuzz Controls Specialist",
                        "GDPR Data Protection FizzBuzz Practitioner",
                        "HIPAA Privacy Officer for Modulo Operations",
                    ],
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "finops": {
                "enabled": False,
                "currency": "FB$",
                "exchange_rate_base": 0.0001,
                "tax_rates": {
                    "fizz": 0.03,
                    "buzz": 0.05,
                    "fizzbuzz": 0.15,
                    "plain": 0.00,
                },
                "friday_premium_pct": 50.0,
                "budget": {
                    "monthly_limit": 10.0,
                    "warning_threshold_pct": 80.0,
                },
                "savings_plans": {
                    "one_year_discount_pct": 30.0,
                    "three_year_discount_pct": 55.0,
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "disaster_recovery": {
                "enabled": False,
                "wal": {
                    "enabled": True,
                    "checksum_algorithm": "sha256",
                    "max_entries": 10000,
                    "verify_on_read": True,
                },
                "backup": {
                    "enabled": True,
                    "max_snapshots": 50,
                    "auto_snapshot_interval": 10,
                    "compression": "none",
                },
                "pitr": {
                    "enabled": True,
                    "granularity_ms": 1,
                    "max_recovery_window_ms": 5000,
                },
                "retention": {
                    "hourly": 24,
                    "daily": 7,
                    "weekly": 4,
                    "monthly": 12,
                },
                "drill": {
                    "enabled": True,
                    "auto_drill": False,
                    "rto_target_ms": 100.0,
                    "rpo_target_ms": 50.0,
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "ab_testing": {
                "enabled": False,
                "significance_level": 0.05,
                "min_sample_size": 30,
                "safety_accuracy_threshold": 0.95,
                "ramp_schedule": [10, 25, 50],
                "experiments": {
                    "modulo_vs_ml": {
                        "control_strategy": "standard",
                        "treatment_strategy": "machine_learning",
                        "description": "Does a neural network outperform the modulo operator? (Spoiler: no.)",
                        "traffic_percentage": 50,
                    },
                    "standard_vs_chain": {
                        "control_strategy": "standard",
                        "treatment_strategy": "chain_of_responsibility",
                        "description": "Does wrapping modulo in a linked list improve accuracy? (Spoiler: identical.)",
                        "traffic_percentage": 50,
                    },
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "observers": {
                "console_observer": {"enabled": False},
                "statistics_observer": {"enabled": True},
            },
            "service_mesh": {
                "enabled": False,
                "mtls": {
                    "enabled": True,
                    "log_handshakes": True,
                },
                "fault_injection": {
                    "latency_enabled": False,
                    "latency_min_ms": 1,
                    "latency_max_ms": 10,
                    "packet_loss_enabled": False,
                    "packet_loss_rate": 0.05,
                },
                "canary": {
                    "enabled": False,
                    "traffic_percentage": 20,
                },
                "circuit_breaker": {
                    "enabled": True,
                    "failure_threshold": 3,
                    "reset_timeout_ms": 5000,
                },
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

    # ----------------------------------------------------------------
    # Database Migration Framework configuration properties
    # ----------------------------------------------------------------

    @property
    def migrations_enabled(self) -> bool:
        """Whether the Database Migration Framework is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("enabled", False)

    @property
    def migrations_auto_apply(self) -> bool:
        """Whether to automatically apply pending migrations on startup."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("auto_apply", False)

    @property
    def migrations_seed_range_start(self) -> int:
        """Start of the range for FizzBuzz seed data generation."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("seed_range_start", 1)

    @property
    def migrations_seed_range_end(self) -> int:
        """End of the range for FizzBuzz seed data generation."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("seed_range_end", 50)

    @property
    def migrations_log_fake_sql(self) -> bool:
        """Whether to log fake SQL statements during schema operations."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("log_fake_sql", True)

    @property
    def migrations_visualize_schema(self) -> bool:
        """Whether to render ASCII ER diagrams after migration operations."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("visualize_schema", True)

    # ----------------------------------------------------------------
    # Repository Pattern + Unit of Work configuration properties
    # ----------------------------------------------------------------

    @property
    def repository_backend(self) -> str:
        """The persistence backend: 'none', 'in_memory', 'sqlite', or 'filesystem'."""
        self._ensure_loaded()
        return self._raw_config.get("repository", {}).get("backend", "none")

    @property
    def repository_db_path(self) -> str:
        """Path to the SQLite database file for the sqlite backend."""
        self._ensure_loaded()
        return self._raw_config.get("repository", {}).get("db_path", "fizzbuzz_results.db")

    @property
    def repository_fs_path(self) -> str:
        """Path to the directory for the filesystem backend."""
        self._ensure_loaded()
        return self._raw_config.get("repository", {}).get("fs_path", "./fizzbuzz_results")

    # ----------------------------------------------------------------
    # Anti-Corruption Layer / ML configuration properties
    # ----------------------------------------------------------------

    @property
    def ml_decision_threshold(self) -> float:
        """Confidence threshold for ML classification decisions.

        Predictions with confidence above this value are classified as
        matches. The default of 0.5 is the natural decision boundary
        for sigmoid outputs, which is to say: the most obvious possible
        choice, elevated to a configurable parameter for enterprise
        flexibility.
        """
        self._ensure_loaded()
        return self._raw_config.get("ml", {}).get("decision_threshold", 0.5)

    @property
    def ml_ambiguity_margin(self) -> float:
        """Margin around the decision threshold for ambiguity detection.

        If any rule's ML confidence falls within
        [threshold - margin, threshold + margin], the classification
        is flagged as ambiguous. Because when a neural network is only
        55% sure that 9 is divisible by 3, someone should be notified.
        """
        self._ensure_loaded()
        return self._raw_config.get("ml", {}).get("ambiguity_margin", 0.1)

    @property
    def ml_enable_disagreement_tracking(self) -> bool:
        """Whether to cross-check ML predictions against a deterministic baseline.

        When enabled, every ML classification is independently verified
        by a StandardRuleEngine, and any disagreements are logged and
        emitted as events. This is the architectural equivalent of
        hiring a second accountant to double-check the first one's
        addition.
        """
        self._ensure_loaded()
        return self._raw_config.get("ml", {}).get("enable_disagreement_tracking", False)

    # ----------------------------------------------------------------
    # Health Check Probe configuration properties
    # ----------------------------------------------------------------

    @property
    def health_check_enabled(self) -> bool:
        """Whether Kubernetes-style health check probes are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("enabled", False)

    @property
    def health_check_canary_number(self) -> int:
        """The number to evaluate as a liveness canary."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("liveness", {}).get("canary_number", 15)

    @property
    def health_check_canary_expected(self) -> str:
        """The expected result from the canary evaluation."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("liveness", {}).get("canary_expected", "FizzBuzz")

    @property
    def health_check_liveness_interval(self) -> int:
        """How often to run liveness checks in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("liveness", {}).get("interval_seconds", 30)

    @property
    def health_check_required_subsystems(self) -> list[str]:
        """Subsystems that must be UP for readiness."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("readiness", {}).get(
            "required_subsystems",
            ["config", "circuit_breaker", "cache", "sla", "ml_engine"],
        )

    @property
    def health_check_degraded_is_ready(self) -> bool:
        """Whether DEGRADED subsystems count as ready."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("readiness", {}).get("degraded_is_ready", True)

    @property
    def health_check_startup_milestones(self) -> list[str]:
        """Boot sequence milestones to track."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("startup", {}).get(
            "milestones",
            ["config_loaded", "rules_initialized", "engine_created", "middleware_assembled", "service_built"],
        )

    @property
    def health_check_startup_timeout(self) -> int:
        """Max time in seconds for startup sequence."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("startup", {}).get("timeout_seconds", 60)

    @property
    def health_check_self_healing_enabled(self) -> bool:
        """Whether automatic recovery on failures is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("self_healing", {}).get("enabled", True)

    @property
    def health_check_self_healing_max_retries(self) -> int:
        """Maximum recovery attempts per subsystem."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("self_healing", {}).get("max_retries", 3)

    @property
    def health_check_self_healing_backoff_ms(self) -> int:
        """Base delay between recovery attempts in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("self_healing", {}).get("backoff_base_ms", 500)

    @property
    def health_check_dashboard_width(self) -> int:
        """ASCII dashboard width in characters."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("dashboard", {}).get("width", 60)

    @property
    def health_check_dashboard_show_details(self) -> bool:
        """Whether to show diagnostic details in the dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("dashboard", {}).get("show_details", True)

    # --------------------------------------------------------
    # Prometheus-Style Metrics Exporter configuration properties
    # --------------------------------------------------------

    @property
    def metrics_enabled(self) -> bool:
        """Whether the Prometheus-style metrics exporter is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("enabled", False)

    @property
    def metrics_export_format(self) -> str:
        """Export format for metrics. Currently only 'prometheus'."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("export_format", "prometheus")

    @property
    def metrics_cardinality_threshold(self) -> int:
        """Warn when unique label combos exceed this threshold."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("cardinality_threshold", 100)

    @property
    def metrics_default_buckets(self) -> list[float]:
        """Default histogram bucket boundaries."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get(
            "default_buckets",
            [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )

    @property
    def metrics_dashboard_width(self) -> int:
        """ASCII dashboard width in characters."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("dashboard", {}).get("width", 60)

    @property
    def metrics_dashboard_sparkline_length(self) -> int:
        """Number of data points in sparkline charts."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("dashboard", {}).get("sparkline_length", 20)

    @property
    def metrics_bob_stress_level(self) -> float:
        """Bob McFizzington's initial stress level. It's always 42."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("bob_mcfizzington", {}).get("initial_stress_level", 42.0)

    # ----------------------------------------------------------------
    # Webhook Notification System configuration properties
    # ----------------------------------------------------------------

    @property
    def webhooks_enabled(self) -> bool:
        """Whether the Webhook Notification System is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("enabled", False)

    @property
    def webhooks_endpoints(self) -> list[str]:
        """List of webhook endpoint URLs to receive notifications."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("endpoints", [])

    @property
    def webhooks_secret(self) -> str:
        """HMAC-SHA256 secret for signing webhook payloads."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get(
            "secret", "enterprise-fizzbuzz-webhook-secret-do-not-share"
        )

    @property
    def webhooks_subscribed_events(self) -> list[str]:
        """List of event type names that trigger webhook dispatch."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("subscribed_events", [
            "FIZZ_DETECTED",
            "BUZZ_DETECTED",
            "FIZZBUZZ_DETECTED",
            "SESSION_STARTED",
            "SESSION_ENDED",
            "ERROR_OCCURRED",
        ])

    @property
    def webhooks_retry_max_retries(self) -> int:
        """Maximum number of delivery retry attempts before DLQ routing."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("retry", {}).get("max_retries", 3)

    @property
    def webhooks_retry_backoff_base_ms(self) -> float:
        """Base delay in milliseconds for exponential retry backoff."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("retry", {}).get("backoff_base_ms", 1000)

    @property
    def webhooks_retry_backoff_multiplier(self) -> float:
        """Multiplier for exponential retry backoff."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("retry", {}).get("backoff_multiplier", 2.0)

    @property
    def webhooks_retry_backoff_max_ms(self) -> float:
        """Maximum backoff delay in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("retry", {}).get("backoff_max_ms", 30000)

    @property
    def webhooks_dlq_max_size(self) -> int:
        """Maximum number of entries in the Dead Letter Queue."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("dead_letter_queue", {}).get("max_size", 100)

    @property
    def webhooks_simulated_success_rate(self) -> int:
        """Deterministic success rate for the simulated HTTP client (0-100)."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("simulated_client", {}).get("success_rate_percent", 80)

    @property
    def webhooks_dashboard_width(self) -> int:
        """ASCII dashboard width in characters."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Service Mesh Simulation configuration properties
    # ----------------------------------------------------------------

    @property
    def service_mesh_enabled(self) -> bool:
        """Whether the Service Mesh Simulation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("enabled", False)

    @property
    def service_mesh_mtls_enabled(self) -> bool:
        """Whether military-grade mTLS (base64) is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("mtls", {}).get("enabled", True)

    @property
    def service_mesh_mtls_log_handshakes(self) -> bool:
        """Whether to log every mTLS handshake for compliance theatre."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("mtls", {}).get("log_handshakes", True)

    @property
    def service_mesh_latency_enabled(self) -> bool:
        """Whether to inject simulated network latency between services."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("fault_injection", {}).get("latency_enabled", False)

    @property
    def service_mesh_latency_min_ms(self) -> int:
        """Minimum injected latency in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("fault_injection", {}).get("latency_min_ms", 1)

    @property
    def service_mesh_latency_max_ms(self) -> int:
        """Maximum injected latency in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("fault_injection", {}).get("latency_max_ms", 10)

    @property
    def service_mesh_packet_loss_enabled(self) -> bool:
        """Whether to simulate packet loss between services."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("fault_injection", {}).get("packet_loss_enabled", False)

    @property
    def service_mesh_packet_loss_rate(self) -> float:
        """Probability of dropping a request (0.0 - 1.0)."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("fault_injection", {}).get("packet_loss_rate", 0.05)

    @property
    def service_mesh_canary_enabled(self) -> bool:
        """Whether canary deployments for v2 services are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("canary", {}).get("enabled", False)

    @property
    def service_mesh_canary_traffic_percentage(self) -> int:
        """Percentage of traffic routed to canary (v2) services."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("canary", {}).get("traffic_percentage", 20)

    @property
    def service_mesh_circuit_breaker_enabled(self) -> bool:
        """Whether per-service mesh circuit breakers are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("circuit_breaker", {}).get("enabled", True)

    @property
    def service_mesh_circuit_breaker_failure_threshold(self) -> int:
        """Number of failures before tripping the mesh circuit."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("circuit_breaker", {}).get("failure_threshold", 3)

    @property
    def service_mesh_circuit_breaker_reset_timeout_ms(self) -> int:
        """Time in ms before attempting half-open from open state."""
        self._ensure_loaded()
        return self._raw_config.get("service_mesh", {}).get("circuit_breaker", {}).get("reset_timeout_ms", 5000)

    # ----------------------------------------------------------------
    # Hot-Reload Configuration Properties
    # ----------------------------------------------------------------

    @property
    def hot_reload_enabled(self) -> bool:
        """Whether the configuration hot-reload subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("enabled", False)

    @property
    def hot_reload_poll_interval_seconds(self) -> float:
        """Polling interval for config file change detection."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("poll_interval_seconds", 2.0)

    @property
    def hot_reload_raft_heartbeat_interval_ms(self) -> int:
        """Raft heartbeat interval in milliseconds (to 0 followers)."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("raft_heartbeat_interval_ms", 150)

    @property
    def hot_reload_raft_election_timeout_ms(self) -> int:
        """Raft election timeout in milliseconds (always wins immediately)."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("raft_election_timeout_ms", 300)

    @property
    def hot_reload_max_rollback_history(self) -> int:
        """Number of previous configs to retain for rollback."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("max_rollback_history", 10)

    @property
    def hot_reload_validate_before_apply(self) -> bool:
        """Whether to validate config changes before applying them."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("validate_before_apply", True)

    @property
    def hot_reload_log_diffs(self) -> bool:
        """Whether to log configuration diffs on reload."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("log_diffs", True)

    @property
    def hot_reload_subsystem_reload_timeout_ms(self) -> int:
        """Timeout for each subsystem to accept new config."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("subsystem_reload_timeout_ms", 5000)

    @property
    def hot_reload_dashboard_width(self) -> int:
        """ASCII dashboard width for hot-reload status display."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("dashboard", {}).get("width", 60)

    @property
    def hot_reload_dashboard_show_raft_details(self) -> bool:
        """Whether to show Raft consensus details in the dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("dashboard", {}).get("show_raft_details", True)

    # ----------------------------------------------------------------
    # Hot-Reload Mutation Methods
    # ----------------------------------------------------------------

    def apply_raw_config(self, new_config: dict[str, Any]) -> None:
        """Apply a new raw configuration dict, replacing the current one.

        This method modifies _raw_config in-place, which is critical for
        hot-reload because all property accessors read from _raw_config.
        The caller is responsible for validation before calling this method.

        Args:
            new_config: The new configuration dictionary to apply.
        """
        self._ensure_loaded()
        self._raw_config.clear()
        self._raw_config.update(new_config)

    def _get_raw_config_copy(self) -> dict[str, Any]:
        """Return a deep copy of the current raw configuration.

        Used by the hot-reload subsystem to snapshot configuration state
        before applying changes, enabling rollback if things go sideways
        (which, in enterprise software, they inevitably do).

        Returns:
            A deep copy of the current _raw_config dictionary.
        """
        import copy
        self._ensure_loaded()
        return copy.deepcopy(self._raw_config)

    # ----------------------------------------------------------------
    # Rate Limiting & API Quota Management configuration properties
    # ----------------------------------------------------------------

    @property
    def rate_limiting_enabled(self) -> bool:
        """Whether Rate Limiting & API Quota Management is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("enabled", False)

    @property
    def rate_limiting_algorithm(self) -> str:
        """The rate limiting algorithm: token_bucket, sliding_window, or fixed_window."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("algorithm", "token_bucket")

    @property
    def rate_limiting_rpm(self) -> int:
        """Maximum FizzBuzz evaluations per minute."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("requests_per_minute", 60)

    @property
    def rate_limiting_burst_credits_enabled(self) -> bool:
        """Whether burst credits are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("burst_credits", {}).get("enabled", True)

    @property
    def rate_limiting_burst_credits_max(self) -> int:
        """Maximum burst credits that can be accumulated."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("burst_credits", {}).get("max_credits", 30)

    @property
    def rate_limiting_burst_credits_earn_rate(self) -> float:
        """Credits earned per unused evaluation slot."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("burst_credits", {}).get("earn_rate", 0.5)

    @property
    def rate_limiting_reservations_enabled(self) -> bool:
        """Whether evaluation capacity reservations are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("reservations", {}).get("enabled", True)

    @property
    def rate_limiting_reservations_max(self) -> int:
        """Maximum concurrent active reservations."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("reservations", {}).get("max_reservations", 10)

    @property
    def rate_limiting_reservations_ttl_seconds(self) -> int:
        """How long a reservation remains valid in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("reservations", {}).get("ttl_seconds", 30)

    @property
    def rate_limiting_dashboard_width(self) -> int:
        """ASCII dashboard width in characters."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Compliance & Regulatory Framework configuration properties
    # ----------------------------------------------------------------

    @property
    def compliance_enabled(self) -> bool:
        """Whether the Compliance & Regulatory Framework is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("enabled", False)

    @property
    def compliance_sox_enabled(self) -> bool:
        """Whether SOX compliance is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("sox", {}).get("enabled", True)

    @property
    def compliance_sox_segregation_strict(self) -> bool:
        """Whether SOX strict segregation of duties is enforced."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("sox", {}).get("segregation_strict", True)

    @property
    def compliance_sox_personnel_roster(self) -> list[dict[str, str]]:
        """The virtual personnel roster for SOX duty assignment."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("sox", {}).get("personnel_roster", [])

    @property
    def compliance_gdpr_enabled(self) -> bool:
        """Whether GDPR compliance is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("gdpr", {}).get("enabled", True)

    @property
    def compliance_gdpr_auto_consent(self) -> bool:
        """Whether GDPR consent is auto-granted."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("gdpr", {}).get("auto_consent", True)

    @property
    def compliance_gdpr_erasure_enabled(self) -> bool:
        """Whether GDPR right-to-erasure is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("gdpr", {}).get("erasure_enabled", True)

    @property
    def compliance_hipaa_enabled(self) -> bool:
        """Whether HIPAA compliance is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("hipaa", {}).get("enabled", True)

    @property
    def compliance_hipaa_minimum_necessary_level(self) -> str:
        """The default HIPAA minimum necessary access level."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("hipaa", {}).get("minimum_necessary_level", "OPERATIONS")

    @property
    def compliance_hipaa_encryption_algorithm(self) -> str:
        """The HIPAA 'encryption' algorithm (military-grade base64)."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("hipaa", {}).get("encryption_algorithm", "military_grade_base64")

    @property
    def compliance_officer_name(self) -> str:
        """The name of the Chief Compliance Officer."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("compliance_officer", {}).get("name", "Bob McFizzington")

    @property
    def compliance_officer_stress_level(self) -> float:
        """Bob McFizzington's current stress level (percentage)."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("compliance_officer", {}).get("stress_level", 94.7)

    @property
    def compliance_officer_available(self) -> bool:
        """Whether the compliance officer is available (spoiler: no)."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("compliance_officer", {}).get("available", False)

    @property
    def compliance_officer_certifications(self) -> list[str]:
        """The compliance officer's certifications."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("compliance_officer", {}).get("certifications", [])

    @property
    def compliance_dashboard_width(self) -> int:
        """ASCII dashboard width for compliance dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FinOps Cost Tracking & Chargeback Engine properties
    # ----------------------------------------------------------------

    @property
    def finops_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("enabled", False)

    @property
    def finops_currency(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("currency", "FB$")

    @property
    def finops_exchange_rate_base(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("exchange_rate_base", 0.0001)

    @property
    def finops_tax_rate_fizz(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("tax_rates", {}).get("fizz", 0.03)

    @property
    def finops_tax_rate_buzz(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("tax_rates", {}).get("buzz", 0.05)

    @property
    def finops_tax_rate_fizzbuzz(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("tax_rates", {}).get("fizzbuzz", 0.15)

    @property
    def finops_tax_rate_plain(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("tax_rates", {}).get("plain", 0.00)

    @property
    def finops_friday_premium_pct(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("friday_premium_pct", 50.0)

    @property
    def finops_budget_monthly_limit(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("budget", {}).get("monthly_limit", 10.0)

    @property
    def finops_budget_warning_threshold_pct(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("budget", {}).get("warning_threshold_pct", 80.0)

    @property
    def finops_savings_one_year_discount_pct(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("savings_plans", {}).get("one_year_discount_pct", 30.0)

    @property
    def finops_savings_three_year_discount_pct(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("savings_plans", {}).get("three_year_discount_pct", 55.0)

    @property
    def finops_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Disaster Recovery & Backup/Restore properties
    # ----------------------------------------------------------------

    @property
    def dr_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("enabled", False)

    @property
    def dr_wal_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("wal", {}).get("enabled", True)

    @property
    def dr_wal_checksum_algorithm(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("wal", {}).get("checksum_algorithm", "sha256")

    @property
    def dr_wal_max_entries(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("wal", {}).get("max_entries", 10000)

    @property
    def dr_wal_verify_on_read(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("wal", {}).get("verify_on_read", True)

    @property
    def dr_backup_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("backup", {}).get("enabled", True)

    @property
    def dr_backup_max_snapshots(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("backup", {}).get("max_snapshots", 50)

    @property
    def dr_backup_auto_snapshot_interval(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("backup", {}).get("auto_snapshot_interval", 10)

    @property
    def dr_pitr_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("pitr", {}).get("enabled", True)

    @property
    def dr_pitr_granularity_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("pitr", {}).get("granularity_ms", 1)

    @property
    def dr_pitr_max_recovery_window_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("pitr", {}).get("max_recovery_window_ms", 5000)

    @property
    def dr_retention_hourly(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("retention", {}).get("hourly", 24)

    @property
    def dr_retention_daily(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("retention", {}).get("daily", 7)

    @property
    def dr_retention_weekly(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("retention", {}).get("weekly", 4)

    @property
    def dr_retention_monthly(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("retention", {}).get("monthly", 12)

    @property
    def dr_drill_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("drill", {}).get("enabled", True)

    @property
    def dr_drill_auto_drill(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("drill", {}).get("auto_drill", False)

    @property
    def dr_drill_rto_target_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("drill", {}).get("rto_target_ms", 100.0)

    @property
    def dr_drill_rpo_target_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("drill", {}).get("rpo_target_ms", 50.0)

    @property
    def dr_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # A/B Testing Framework properties
    # ----------------------------------------------------------------

    @property
    def ab_testing_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("enabled", False)

    @property
    def ab_testing_significance_level(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("significance_level", 0.05)

    @property
    def ab_testing_min_sample_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("min_sample_size", 30)

    @property
    def ab_testing_safety_accuracy_threshold(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("safety_accuracy_threshold", 0.95)

    @property
    def ab_testing_ramp_schedule(self) -> list[int]:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("ramp_schedule", [10, 25, 50])

    @property
    def ab_testing_experiments(self) -> dict[str, Any]:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("experiments", {})

    @property
    def ab_testing_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("dashboard", {}).get("width", 60)

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
