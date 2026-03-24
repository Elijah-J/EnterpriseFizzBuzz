"""Enterprise FizzBuzz Platform - Base Configuration Manager.

Provides the core configuration loading, validation, and singleton
infrastructure that all feature-specific configuration mixins build upon.
"""

from __future__ import annotations

import glob
import logging
import os
from pathlib import Path
from typing import Any, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ConfigurationError,
    ConfigurationFileNotFoundError,
    ConfigurationValidationError,
)
from enterprise_fizzbuzz.domain.models import (
    EvaluationStrategy,
    LogLevel,
    OutputFormat,
    RuleDefinition,
)

logger = logging.getLogger(__name__)

# Default config path, overridable via environment variable
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config.yaml"

# Default overlay directory for per-feature configuration files
_DEFAULT_OVERLAY_DIR = _DEFAULT_CONFIG_PATH.parent / "config.d"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overlay into base. Overlay values take precedence."""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


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


class _BaseConfigurationManager(metaclass=_SingletonMeta):
    """Base configuration manager with core loading, validation, and global properties.

    Loads configuration from YAML, applies environment variable overrides,
    and provides validated, typed access to all configuration values.
    Feature-specific properties are provided by mixin classes.
    """

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

    def load(self) -> _BaseConfigurationManager:
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

        self._load_overlays(yaml)

        self._apply_environment_overrides()
        self._validate()
        self._loaded = True
        logger.info("Configuration loaded from %s", self._config_path)
        return self

    def _load_overlays(self, yaml: Any) -> None:
        """Load per-feature overlay files from config.d/ and deep-merge into base config."""
        overlay_dir = self._config_path.parent / "config.d"
        if not overlay_dir.is_dir():
            return
        overlay_paths = sorted(glob.glob(str(overlay_dir / "*.yaml")))
        for path in overlay_paths:
            with open(path, "r") as f:
                overlay = yaml.safe_load(f)
            if overlay and isinstance(overlay, dict):
                _deep_merge(self._raw_config, overlay)
                logger.debug("Merged overlay configuration from %s", path)

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
                "chatbot": {
                    "max_history": 20,
                    "formality_level": "maximum",
                    "include_article_citations": True,
                    "bob_commentary_enabled": True,
                    "dashboard_width": 60,
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
            "message_queue": {
                "enabled": False,
                "default_partitions": 3,
                "partitioner_strategy": "hash",
                "enable_schema_validation": True,
                "enable_idempotency": True,
                "max_poll_records": 10,
                "consumer_session_timeout_ms": 30000,
                "topics": {
                    "evaluations.requested": {
                        "partitions": 3,
                        "description": "FizzBuzz evaluation requests awaiting processing",
                    },
                    "evaluations.completed": {
                        "partitions": 3,
                        "description": "Completed FizzBuzz evaluation results",
                    },
                    "audit.events": {
                        "partitions": 2,
                        "description": "Audit trail events for compliance theatre",
                    },
                    "alerts.critical": {
                        "partitions": 1,
                        "description": "Critical alerts that wake up Bob McFizzington",
                    },
                    "fizzbuzz.feelings": {
                        "partitions": 1,
                        "description": "The topic nobody subscribes to. Messages go here to be ignored.",
                    },
                },
                "consumer_groups": {
                    "fizzbuzz-evaluators": {
                        "subscribed_topics": ["evaluations.requested"],
                        "description": "The hardworking consumers that actually process FizzBuzz",
                    },
                    "audit-loggers": {
                        "subscribed_topics": ["audit.events", "evaluations.completed"],
                        "description": "Consumers that log everything for compliance reasons",
                    },
                    "feelings-listener": {
                        "subscribed_topics": [],
                        "description": "This consumer group has zero members and zero subscriptions. It exists for solidarity.",
                    },
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "vault": {
                "enabled": False,
                "shamir": {
                    "threshold": 3,
                    "num_shares": 5,
                    "prime_bits": 127,
                },
                "encryption": {
                    "algorithm": "military_grade_double_base64_xor",
                    "key_derivation": "sha256",
                    "iterations": 1,
                },
                "rotation": {
                    "enabled": True,
                    "interval_evaluations": 50,
                    "rotatable_secrets": [
                        "fizzbuzz/blockchain/difficulty",
                        "fizzbuzz/ml/learning_rate",
                        "fizzbuzz/cache/ttl_seconds",
                        "fizzbuzz/sla/latency_threshold_ms",
                    ],
                },
                "scanner": {
                    "enabled": True,
                    "scan_paths": ["./enterprise_fizzbuzz"],
                    "flag_integers": True,
                    "flag_strings": False,
                    "min_integer_suspicion": 0,
                },
                "access_policies": {
                    "fizzbuzz/rules/*": {
                        "allowed_components": ["rule_engine", "feature_flags", "middleware"],
                        "operations": ["read"],
                    },
                    "fizzbuzz/blockchain/*": {
                        "allowed_components": ["blockchain", "compliance"],
                        "operations": ["read", "write"],
                    },
                    "fizzbuzz/ml/*": {
                        "allowed_components": ["ml_engine", "ab_testing"],
                        "operations": ["read"],
                    },
                    "fizzbuzz/infrastructure/*": {
                        "allowed_components": ["config", "middleware", "health_check"],
                        "operations": ["read", "write"],
                    },
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "data_pipeline": {
                "enabled": False,
                "source": "range",
                "sink": "stdout",
                "batch_size": 10,
                "max_retries": 3,
                "retry_backoff_ms": 100,
                "enable_checkpoints": True,
                "enable_lineage": True,
                "enable_backfill": False,
                "enrichments": {
                    "fibonacci": True,
                    "primality": True,
                    "roman_numerals": True,
                    "emotional_valence": True,
                },
                "dag": {
                    "visualization_width": 60,
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "openapi": {
                "enabled": False,
                "spec_version": "3.1.0",
                "server_url": "http://localhost:0",
                "server_description": "This server does not exist",
                "swagger_ui_width": 80,
                "dashboard_width": 70,
                "include_deprecated": True,
                "contact_name": "Bob McFizzington",
                "contact_email": "bob.mcfizzington@enterprise.example.com",
                "license_name": "Enterprise FizzBuzz Public License v1.0",
            },
            "api_gateway": {
                "enabled": False,
                "versions": {
                    "v1": {
                        "status": "DEPRECATED",
                        "sunset_date": "2025-12-31",
                        "deprecation_urgency": "CRITICAL",
                    },
                    "v2": {
                        "status": "ACTIVE",
                        "sunset_date": None,
                        "deprecation_urgency": None,
                    },
                    "v3": {
                        "status": "ACTIVE",
                        "sunset_date": None,
                        "deprecation_urgency": None,
                    },
                },
                "default_version": "v2",
                "routes": [
                    {
                        "path": "/api/{version}/fizzbuzz/{number}",
                        "method": "GET",
                        "handler": "evaluate_number",
                        "versions": ["v1", "v2", "v3"],
                        "description": "Evaluate a single number through the FizzBuzz pipeline",
                    },
                    {
                        "path": "/api/{version}/fizzbuzz/range",
                        "method": "POST",
                        "handler": "evaluate_range",
                        "versions": ["v2", "v3"],
                        "description": "Evaluate a range of numbers (batch endpoint)",
                    },
                    {
                        "path": "/api/{version}/fizzbuzz/feelings",
                        "method": "GET",
                        "handler": "get_feelings",
                        "versions": ["v2", "v3"],
                        "description": "How does the FizzBuzz engine feel about its existence?",
                    },
                    {
                        "path": "/api/{version}/health",
                        "method": "GET",
                        "handler": "health_check",
                        "versions": ["v1", "v2", "v3"],
                        "description": "Gateway health check endpoint",
                    },
                    {
                        "path": "/api/{version}/metrics",
                        "method": "GET",
                        "handler": "get_metrics",
                        "versions": ["v3"],
                        "description": "Prometheus-style metrics (v3 only)",
                    },
                ],
                "api_keys": {
                    "default_quota": 1000,
                    "key_prefix": "efp_",
                    "key_length": 32,
                },
                "transformers": {
                    "request": {
                        "normalizer": True,
                        "enricher": True,
                        "validator": True,
                        "deprecation_injector": True,
                    },
                    "response": {
                        "compressor": True,
                        "pagination_wrapper": True,
                        "hateoas_enricher": True,
                    },
                },
                "replay_journal": {
                    "enabled": True,
                    "max_entries": 10000,
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "blue_green": {
                "enabled": False,
                "shadow_traffic_count": 10,
                "smoke_test_numbers": [3, 5, 15, 42, 97],
                "bake_period_ms": 50,
                "bake_period_evaluations": 5,
                "cutover_delay_ms": 10,
                "rollback_auto": False,
                "dashboard": {
                    "width": 60,
                },
            },
            "graph_db": {
                "enabled": False,
                "auto_populate": True,
                "max_visualization_nodes": 20,
                "community_max_iterations": 20,
                "dashboard": {
                    "width": 60,
                },
            },
            "genetic_algorithm": {
                "enabled": False,
                "population_size": 50,
                "generations": 100,
                "mutation_rate": 0.15,
                "crossover_rate": 0.7,
                "tournament_size": 5,
                "elitism_count": 2,
                "max_genes": 8,
                "min_genes": 1,
                "canonical_seed_pct": 0.10,
                "convergence_threshold": 0.95,
                "diversity_floor": 0.05,
                "mass_extinction_survivor_pct": 0.20,
                "hall_of_fame_size": 10,
                "fitness_weights": {
                    "accuracy": 0.50,
                    "coverage": 0.15,
                    "distinctness": 0.10,
                    "phonetic_harmony": 0.10,
                    "mathematical_elegance": 0.15,
                },
                "seed": None,
                "dashboard": {
                    "width": 60,
                    "fitness_chart_height": 10,
                },
            },
            "load_testing": {
                "enabled": False,
                "default_profile": "smoke",
                "default_vus": 10,
                "default_duration_seconds": 30,
                "ramp_up_seconds": 5,
                "ramp_down_seconds": 3,
                "numbers_per_vu": 100,
                "think_time_ms": 0,
                "timeout_seconds": 300,
                "dashboard": {
                    "width": 60,
                    "histogram_buckets": 10,
                },
            },
            "audit_dashboard": {
                "enabled": False,
                "buffer_size": 500,
                "anomaly_detection": {
                    "enabled": True,
                    "window_seconds": 10.0,
                    "z_score_threshold": 2.0,
                    "min_samples": 5,
                },
                "correlation": {
                    "enabled": True,
                    "window_seconds": 5.0,
                    "min_events": 2,
                },
                "stream": {
                    "format": "ndjson",
                    "include_payload": True,
                },
                "dashboard": {
                    "width": 80,
                    "refresh_summary": True,
                },
            },
            "gitops": {
                "enabled": False,
                "default_branch": "main",
                "auto_commit_on_load": True,
                "policy_enforcement": True,
                "dry_run_range_start": 1,
                "dry_run_range_end": 30,
                "reconciliation_on_drift": True,
                "max_commit_history": 100,
                "approval_mode": "single_operator",
                "blast_radius_subsystems": [
                    "rules",
                    "engine",
                    "output",
                    "range",
                    "middleware",
                    "circuit_breaker",
                    "cache",
                    "feature_flags",
                    "chaos",
                ],
                "dashboard": {
                    "width": 60,
                },
            },
            "formal_verification": {
                "enabled": False,
                "proof_depth": 100,
                "timeout_ms": 5000,
                "dashboard": {
                    "width": 60,
                },
            },
            "theorem_prover": {
                "enabled": False,
                "max_clauses": 5000,
                "max_steps": 10000,
                "dashboard": {
                    "width": 72,
                },
            },
            "regex_engine": {
                "enabled": False,
                "dashboard": {
                    "width": 72,
                },
            },
            "fbaas": {
                "enabled": False,
                "default_tier": "free",
                "free_tier": {
                    "daily_limit": 10,
                    "watermark": "[Powered by FBaaS Free Tier]",
                    "features": ["standard"],
                },
                "pro_tier": {
                    "daily_limit": 1000,
                    "monthly_price_cents": 2999,
                    "features": [
                        "standard",
                        "chain_of_responsibility",
                        "parallel_async",
                        "tracing",
                        "caching",
                        "feature_flags",
                    ],
                },
                "enterprise_tier": {
                    "daily_limit": -1,
                    "monthly_price_cents": 99999,
                    "features": [
                        "standard",
                        "chain_of_responsibility",
                        "parallel_async",
                        "machine_learning",
                        "chaos",
                        "tracing",
                        "caching",
                        "feature_flags",
                        "blockchain",
                        "compliance",
                    ],
                },
                "sla": {
                    "free_uptime_target": 0.95,
                    "pro_uptime_target": 0.999,
                    "enterprise_uptime_target": 0.9999,
                    "free_response_time_ms": 500,
                    "pro_response_time_ms": 100,
                    "enterprise_response_time_ms": 10,
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "query_optimizer": {
                "enabled": False,
                "cost_weights": {
                    "modulo": 1.0,
                    "cache_miss": 5.0,
                    "ml": 20.0,
                    "compliance": 10.0,
                    "blockchain": 50.0,
                },
                "plan_cache_max_size": 256,
                "max_plans": 16,
                "dashboard": {
                    "width": 60,
                },
            },
            "paxos": {
                "enabled": False,
                "num_nodes": 5,
                "message_delay_ms": 0,
                "message_drop_rate": 0.0,
                "byzantine_mode": False,
                "byzantine_lie_probability": 1.0,
                "partition_enabled": False,
                "partition_groups": [[0, 1, 2], [3, 4]],
                "dashboard": {
                    "width": 60,
                },
            },
            "quantum": {
                "enabled": False,
                "num_qubits": 4,
                "max_measurement_attempts": 10,
                "decoherence_threshold": 0.001,
                "fallback_to_classical": True,
                "shor_max_period_attempts": 5,
                "dashboard": {
                    "width": 60,
                    "show_circuit": True,
                },
            },
            "cross_compiler": {
                "enabled": False,
                "verify_round_trip": True,
                "verification_range_end": 100,
                "emit_comments": True,
                "dashboard": {
                    "width": 60,
                    "show_ir": False,
                },
            },
            "circuit": {
                "enabled": False,
                "enable_waveform": False,
                "enable_dashboard": False,
                "max_events": 10000,
                "timing_budget_ns": 500.0,
                "glitch_threshold_ns": 5.0,
                "dashboard": {"width": 60},
            },
            "proxy": {
                "enabled": False,
                "num_backends": 5,
                "algorithm": "round_robin",
                "enable_sticky_sessions": True,
                "enable_health_check": True,
                "health_check_interval": 10,
                "dashboard": {
                    "width": 60,
                },
            },
            "probabilistic": {
                "enabled": False,
                "bloom": {
                    "expected_elements": 1000,
                    "false_positive_rate": 0.01,
                },
                "count_min_sketch": {
                    "width": 2048,
                    "depth": 5,
                },
                "hyperloglog": {
                    "precision": 14,
                },
                "tdigest": {
                    "compression": 100,
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
            "nlq": {
                "enabled": False,
                "max_query_length": 500,
                "max_results": 1000,
                "history_size": 50,
                "dashboard": {
                    "width": 60,
                },
            },
            "time_travel": {
                "enabled": False,
                "max_snapshots": 10000,
                "integrity_checks": True,
                "anomaly_detection": True,
                "dashboard": {
                    "width": 60,
                    "timeline_markers": True,
                },
            },
            "vm": {
                "enabled": False,
                "cycle_limit": 10000,
                "trace_execution": False,
                "enable_optimizer": True,
                "register_count": 8,
                "dashboard": {
                    "width": 60,
                    "show_registers": True,
                    "show_disassembly": True,
                },
            },
            "knowledge_graph": {
                "enabled": False,
                "max_inference_iterations": 100,
                "domain_range_start": 1,
                "domain_range_end": 100,
                "enable_owl_reasoning": True,
                "enable_visualization": True,
                "dashboard": {
                    "width": 60,
                    "show_class_hierarchy": True,
                    "show_triple_stats": True,
                    "show_inference_stats": True,
                },
            },
            "self_modifying": {
                "enabled": False,
                "mutation_rate": 0.05,
                "max_ast_depth": 10,
                "correctness_floor": 0.95,
                "max_mutations_per_session": 100,
                "kill_switch": True,
                "fitness_weights": {
                    "correctness": 0.70,
                    "latency": 0.20,
                    "compactness": 0.10,
                },
                "enabled_operators": [
                    "DivisorShift",
                    "LabelSwap",
                    "BranchInvert",
                    "InsertShortCircuit",
                    "DeadCodePrune",
                    "SubtreeSwap",
                    "DuplicateSubtree",
                    "NegateCondition",
                    "ConstantFold",
                    "InsertRedundantCheck",
                    "ShuffleChildren",
                    "WrapInConditional",
                ],
                "dashboard": {
                    "width": 60,
                    "show_ast": True,
                    "show_history": True,
                    "show_fitness": True,
                },
            },
            "p2p": {
                "enabled": False,
                "num_nodes": 7,
                "k_bucket_size": 3,
                "gossip_fanout": 3,
                "suspect_timeout_rounds": 3,
                "max_gossip_rounds": 20,
                "dashboard": {
                    "width": 60,
                },
            },
            "kernel": {
                "enabled": False,
                "scheduler": "rr",
                "time_quantum_ms": 10.0,
                "max_processes": 256,
                "page_size": 64,
                "tlb_size": 16,
                "physical_pages": 128,
                "swap_pages": 256,
                "irq_vectors": 16,
                "boot_delay_ms": 5.0,
                "context_switch_overhead_us": 50.0,
                "cfs_default_weight": 1024,
                "cfs_min_granularity_ms": 1.0,
                "dashboard": {
                    "width": 60,
                    "show_process_table": True,
                    "show_memory_map": True,
                    "show_interrupt_log": True,
                },
            },
            "digital_twin": {
                "enabled": False,
                "monte_carlo_runs": 1000,
                "jitter_stddev": 0.05,
                "failure_jitter": 0.02,
                "drift_threshold_fdu": 5.0,
                "anomaly_sigma": 2.0,
                "dashboard": {
                    "width": 60,
                    "show_histogram": True,
                    "show_drift_gauge": True,
                    "histogram_buckets": 20,
                },
            },
            "fizzlang": {
                "enabled": False,
                "max_program_length": 10000,
                "max_rules": 50,
                "max_let_bindings": 100,
                "strict_type_checking": True,
                "stdlib_enabled": True,
                "repl": {
                    "prompt": "fizz> ",
                    "history_size": 100,
                    "show_tokens": False,
                    "show_ast": False,
                },
                "dashboard": {
                    "width": 60,
                    "show_source_stats": True,
                    "show_complexity_index": True,
                },
            },
            "archaeology": {
                "enabled": False,
                "corruption_rate": 0.15,
                "min_fragments_for_reconstruction": 2,
                "confidence_threshold": 0.6,
                "enable_corruption_simulation": True,
                "seed": None,
                "strata_weights": {
                    "blockchain": 1.0,
                    "event_store": 0.9,
                    "cache_coherence": 0.7,
                    "rule_engine": 0.8,
                    "middleware_pipeline": 0.6,
                    "metrics": 0.5,
                    "cache_eulogies": 0.4,
                },
                "dashboard": {
                    "width": 60,
                    "show_strata_reliability": True,
                    "show_bayesian_posterior": True,
                    "show_corruption_report": True,
                },
            },
            "dependent_types": {
                "enabled": False,
                "max_beta_reductions": 1000,
                "max_unification_depth": 100,
                "enable_proof_cache": True,
                "proof_cache_size": 4096,
                "enable_type_inference": True,
                "strict_mode": False,
                "dashboard": {
                    "width": 60,
                    "show_curry_howard": True,
                    "show_proof_tree": True,
                    "show_complexity_index": True,
                },
            },
            "fizzkube": {
                "enabled": False,
                "num_nodes": 3,
                "default_replicas": 2,
                "cpu_per_node": 4000,
                "memory_per_node": 8192,
                "pod_cpu_request": 100,
                "pod_memory_request": 128,
                "pod_cpu_limit": 200,
                "pod_memory_limit": 256,
                "hpa": {
                    "enabled": True,
                    "min_replicas": 1,
                    "max_replicas": 10,
                    "target_cpu_utilization": 70,
                    "scale_up_cooldown_seconds": 15,
                    "scale_down_cooldown_seconds": 30,
                },
                "namespace": "fizzbuzz-production",
                "resource_quota": {
                    "cpu_limit": 16000,
                    "memory_limit": 32768,
                },
                "dashboard": {
                    "width": 60,
                },
            },
            "fizzpm": {
                "enabled": False,
                "audit_on_install": True,
                "default_packages": ["fizzbuzz-core"],
                "lockfile_path": "fizzpm.lock",
                "registry_mirror": "https://registry.fizzpm.io",
                "dashboard": {
                    "width": 60,
                },
            },
            "fizzsql": {
                "enabled": False,
                "max_query_length": 4096,
                "slow_query_threshold_ms": 50.0,
                "max_result_rows": 10000,
                "enable_query_history": True,
                "query_history_size": 100,
                "dashboard": {
                    "width": 60,
                },
            },
            "fizzdap": {
                "enabled": False,
                "port": 4711,
                "auto_stop_on_entry": True,
                "max_breakpoints": 256,
                "step_granularity": "middleware",
                "variable_inspection": {
                    "include_cache_state": True,
                    "include_circuit_breaker": True,
                    "include_quantum_state": True,
                    "include_middleware_timings": True,
                    "max_string_length": 1024,
                },
                "stack_frame": {
                    "include_source_location": True,
                    "max_frames": 64,
                },
                "dashboard": {
                    "width": 60,
                    "show_breakpoints": True,
                    "show_stack_trace": True,
                    "show_variables": True,
                    "show_complexity_index": True,
                },
            },
            "ip_office": {
                "enabled": False,
                "trademark_similarity_threshold": 0.7,
                "patent_novelty_threshold": 0.5,
                "copyright_originality_threshold": 0.3,
                "default_license": "FBPL",
                "trademark_renewal_days": 365,
                "dashboard": {
                    "width": 60,
                },
            },
            "distributed_locks": {
                "enabled": False,
                "policy": "wait-die",
                "lease_duration_s": 30.0,
                "grace_period_s": 5.0,
                "check_interval_s": 1.0,
                "acquisition_timeout_s": 5.0,
                "hot_lock_threshold_ms": 10.0,
                "dashboard": {
                    "width": 60,
                },
            },
            "recommendation": {
                "enabled": False,
                "collaborative_weight": 0.6,
                "content_weight": 0.4,
                "serendipity_factor": 0.1,
                "num_recommendations": 5,
                "min_evaluations_for_personalization": 3,
                "max_similar_users": 10,
                "popular_items_fallback_size": 10,
                "seed": None,
                "dashboard": {
                    "width": 60,
                    "show_feature_vectors": True,
                    "show_user_profiles": True,
                    "show_similarity_matrix": True,
                },
            },
            "cdc": {
                "enabled": False,
                "relay_interval_s": 0.5,
                "outbox_capacity": 10000,
                "schema_compatibility": "full",
                "sinks": ["log", "metrics"],
                "dashboard": {
                    "width": 60,
                },
            },
            "billing": {
                "enabled": False,
                "default_tier": "free",
                "default_tenant_id": "tenant-default",
                "spending_cap": None,
                "dashboard": {
                    "width": 60,
                },
            },
            "jit": {
                "enabled": False,
                "threshold": 3,
                "cache_size": 64,
                "enable_constant_folding": True,
                "enable_dce": True,
                "enable_guard_hoisting": True,
                "enable_type_specialization": True,
                "dashboard": {
                    "width": 60,
                },
            },
            "otel": {
                "enabled": False,
                "export_format": "otlp",
                "sampling_rate": 1.0,
                "batch_mode": False,
                "max_queue_size": 2048,
                "max_batch_size": 512,
                "dashboard": {
                    "width": 60,
                },
            },
            "fizzwal": {
                "enabled": False,
                "mode": "optimistic",
                "checkpoint_interval": 100,
                "crash_recovery_on_startup": False,
                "dashboard": {
                    "width": 60,
                },
            },
            "crdt": {
                "enabled": False,
                "replica_count": 3,
                "anti_entropy_interval": 1,
                "dashboard": {
                    "width": 60,
                },
            },
            "observability_correlation": {
                "enabled": False,
                "temporal_window_seconds": 2.0,
                "confidence_threshold": 0.3,
                "anomaly_latency_threshold_ms": 50.0,
                "anomaly_error_burst_window_s": 5.0,
                "anomaly_error_burst_threshold": 3,
                "anomaly_metric_deviation_sigma": 2.0,
                "causal_patterns": [
                    {
                        "cause": "cache_eviction",
                        "effect": "cache_miss",
                        "confidence": 0.85,
                    },
                    {
                        "cause": "circuit_open",
                        "effect": "fallback_activated",
                        "confidence": 0.95,
                    },
                    {
                        "cause": "error_budget_burn",
                        "effect": "alert_escalation",
                        "confidence": 0.90,
                    },
                    {
                        "cause": "rate_limit_exceeded",
                        "effect": "request_rejected",
                        "confidence": 0.92,
                    },
                    {
                        "cause": "config_reload",
                        "effect": "cache_invalidation",
                        "confidence": 0.80,
                    },
                ],
                "dashboard": {
                    "width": 60,
                },
            },
            "mapreduce": {
                "enabled": False,
                "num_mappers": 4,
                "num_reducers": 2,
                "speculative_threshold": 1.5,
                "dashboard": {
                    "width": 60,
                },
            },
            "schema_evolution": {
                "enabled": False,
                "compatibility_mode": "BACKWARD",
                "consensus_nodes": 5,
                "consensus_quorum": 3,
                "dashboard": {
                    "width": 60,
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

