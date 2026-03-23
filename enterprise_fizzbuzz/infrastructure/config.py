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
        """Whether to generate commemorative eulogies for evicted cache entries."""
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

    @property
    def compliance_chatbot_max_history(self) -> int:
        """Maximum conversation turns retained in chatbot session memory."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("chatbot", {}).get("max_history", 20)

    @property
    def compliance_chatbot_formality_level(self) -> str:
        """Response formality level for the compliance chatbot."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("chatbot", {}).get("formality_level", "maximum")

    @property
    def compliance_chatbot_include_citations(self) -> bool:
        """Whether to include regulatory article citations in chatbot responses."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("chatbot", {}).get("include_article_citations", True)

    @property
    def compliance_chatbot_bob_commentary(self) -> bool:
        """Whether to include Bob McFizzington's editorial comments."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("chatbot", {}).get("bob_commentary_enabled", True)

    @property
    def compliance_chatbot_dashboard_width(self) -> int:
        """ASCII dashboard width for the compliance chatbot dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("chatbot", {}).get("dashboard_width", 60)

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

    # ----------------------------------------------------------------
    # Message Queue & Event Bus properties
    # ----------------------------------------------------------------

    @property
    def mq_enabled(self) -> bool:
        """Whether the Message Queue subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("enabled", False)

    @property
    def mq_default_partitions(self) -> int:
        """Default number of partitions per topic (Python lists per topic)."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("default_partitions", 3)

    @property
    def mq_partitioner_strategy(self) -> str:
        """Partitioner strategy: hash, round_robin, or sticky."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("partitioner_strategy", "hash")

    @property
    def mq_enable_schema_validation(self) -> bool:
        """Whether to validate message payloads against the Schema Registry."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("enable_schema_validation", True)

    @property
    def mq_enable_idempotency(self) -> bool:
        """Whether to enforce exactly-once delivery via SHA-256 dedup."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("enable_idempotency", True)

    @property
    def mq_max_poll_records(self) -> int:
        """Maximum messages per consumer poll."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("max_poll_records", 10)

    @property
    def mq_consumer_session_timeout_ms(self) -> int:
        """Consumer session timeout in milliseconds (aspirational)."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("consumer_session_timeout_ms", 30000)

    @property
    def mq_topics(self) -> dict[str, Any]:
        """Topic definitions from configuration."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("topics", {})

    @property
    def mq_consumer_groups(self) -> dict[str, Any]:
        """Consumer group definitions from configuration."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("consumer_groups", {})

    @property
    def mq_dashboard_width(self) -> int:
        """ASCII dashboard width for message queue display."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Secrets Management Vault configuration properties
    # ----------------------------------------------------------------

    @property
    def vault_enabled(self) -> bool:
        """Whether the Secrets Management Vault is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("enabled", False)

    @property
    def vault_shamir_threshold(self) -> int:
        """Minimum number of Shamir shares required to unseal (k)."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("shamir", {}).get("threshold", 3)

    @property
    def vault_shamir_num_shares(self) -> int:
        """Total number of Shamir shares generated on init (n)."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("shamir", {}).get("num_shares", 5)

    @property
    def vault_shamir_prime_bits(self) -> int:
        """Mersenne prime exponent for GF(2^p - 1) arithmetic."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("shamir", {}).get("prime_bits", 127)

    @property
    def vault_encryption_algorithm(self) -> str:
        """The military-grade encryption algorithm name."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("encryption", {}).get(
            "algorithm", "military_grade_double_base64_xor"
        )

    @property
    def vault_encryption_key_derivation(self) -> str:
        """Key derivation function for XOR key generation."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("encryption", {}).get("key_derivation", "sha256")

    @property
    def vault_rotation_enabled(self) -> bool:
        """Whether automatic secret rotation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("rotation", {}).get("enabled", True)

    @property
    def vault_rotation_interval(self) -> int:
        """Number of evaluations between automatic secret rotations."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("rotation", {}).get("interval_evaluations", 50)

    @property
    def vault_rotatable_secrets(self) -> list[str]:
        """List of secret paths eligible for automatic rotation."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("rotation", {}).get("rotatable_secrets", [
            "fizzbuzz/blockchain/difficulty",
            "fizzbuzz/ml/learning_rate",
            "fizzbuzz/cache/ttl_seconds",
            "fizzbuzz/sla/latency_threshold_ms",
        ])

    @property
    def vault_scanner_enabled(self) -> bool:
        """Whether the AST-based secret scanner is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("scanner", {}).get("enabled", True)

    @property
    def vault_scanner_paths(self) -> list[str]:
        """Directories to scan for leaked secrets."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("scanner", {}).get("scan_paths", ["./enterprise_fizzbuzz"])

    @property
    def vault_scanner_flag_integers(self) -> bool:
        """Whether to flag ALL integer literals as potential secrets."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("scanner", {}).get("flag_integers", True)

    @property
    def vault_access_policies(self) -> dict[str, Any]:
        """Per-path access control policies for vault secrets."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("access_policies", {})

    @property
    def vault_dashboard_width(self) -> int:
        """ASCII dashboard width for the vault dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Data Pipeline & ETL Framework properties
    # ----------------------------------------------------------------

    @property
    def data_pipeline_enabled(self) -> bool:
        """Whether the Data Pipeline & ETL Framework is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("enabled", False)

    @property
    def data_pipeline_source(self) -> str:
        """Source connector type: 'range' or 'devnull'."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("source", "range")

    @property
    def data_pipeline_sink(self) -> str:
        """Sink connector type: 'stdout' or 'devnull'."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("sink", "stdout")

    @property
    def data_pipeline_batch_size(self) -> int:
        """Records per batch in the pipeline."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("batch_size", 10)

    @property
    def data_pipeline_max_retries(self) -> int:
        """Maximum retry attempts per stage on failure."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("max_retries", 3)

    @property
    def data_pipeline_retry_backoff_ms(self) -> int:
        """Base backoff between retries in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("retry_backoff_ms", 100)

    @property
    def data_pipeline_enable_checkpoints(self) -> bool:
        """Whether to save pipeline state after each stage."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("enable_checkpoints", True)

    @property
    def data_pipeline_enable_lineage(self) -> bool:
        """Whether to track full data provenance chain per record."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("enable_lineage", True)

    @property
    def data_pipeline_enable_backfill(self) -> bool:
        """Whether to allow retroactive enrichment of processed records."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("enable_backfill", False)

    @property
    def data_pipeline_enrichments(self) -> dict[str, bool]:
        """Which enrichments are enabled: fibonacci, primality, roman_numerals, emotional_valence."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("enrichments", {
            "fibonacci": True,
            "primality": True,
            "roman_numerals": True,
            "emotional_valence": True,
        })

    @property
    def data_pipeline_dag_width(self) -> int:
        """ASCII DAG visualization width."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("dag", {}).get("visualization_width", 60)

    @property
    def data_pipeline_dashboard_width(self) -> int:
        """ASCII dashboard width for the data pipeline dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # OpenAPI Specification Generator properties
    # ----------------------------------------------------------------

    @property
    def openapi_enabled(self) -> bool:
        """Whether the OpenAPI spec generator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("enabled", False)

    @property
    def openapi_spec_version(self) -> str:
        """OpenAPI specification version."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("spec_version", "3.1.0")

    @property
    def openapi_server_url(self) -> str:
        """The server URL. Always http://localhost:0. Always does not exist."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("server_url", "http://localhost:0")

    @property
    def openapi_server_description(self) -> str:
        """Server description."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("server_description", "This server does not exist")

    @property
    def openapi_swagger_ui_width(self) -> int:
        """ASCII Swagger UI width in characters."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("swagger_ui_width", 80)

    @property
    def openapi_dashboard_width(self) -> int:
        """ASCII dashboard width for the OpenAPI dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("dashboard_width", 70)

    @property
    def openapi_include_deprecated(self) -> bool:
        """Whether to include deprecated endpoints in output."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("include_deprecated", True)

    @property
    def openapi_contact_name(self) -> str:
        """API contact person name."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("contact_name", "Bob McFizzington")

    @property
    def openapi_contact_email(self) -> str:
        """API contact email."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("contact_email", "bob.mcfizzington@enterprise.example.com")

    @property
    def openapi_license_name(self) -> str:
        """API license name."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("license_name", "Enterprise FizzBuzz Public License v1.0")

    # ----------------------------------------------------------------
    # API Gateway properties
    # ----------------------------------------------------------------

    @property
    def api_gateway_enabled(self) -> bool:
        """Whether the API Gateway subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("enabled", False)

    @property
    def api_gateway_versions(self) -> dict[str, Any]:
        """Version configuration for the API Gateway."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("versions", {})

    @property
    def api_gateway_default_version(self) -> str:
        """Default API version when none is specified."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("default_version", "v2")

    @property
    def api_gateway_routes(self) -> list[dict[str, Any]]:
        """Route definitions for the API Gateway."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("routes", [])

    @property
    def api_gateway_api_keys_default_quota(self) -> int:
        """Default request quota per API key."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("api_keys", {}).get("default_quota", 1000)

    @property
    def api_gateway_api_keys_prefix(self) -> str:
        """Prefix for generated API keys."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("api_keys", {}).get("key_prefix", "efp_")

    @property
    def api_gateway_api_keys_length(self) -> int:
        """Length of generated API keys (after prefix)."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("api_keys", {}).get("key_length", 32)

    @property
    def api_gateway_transformers(self) -> dict[str, Any]:
        """Transformer configuration for request/response pipelines."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("transformers", {})

    @property
    def api_gateway_replay_journal_enabled(self) -> bool:
        """Whether the request replay journal is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("replay_journal", {}).get("enabled", True)

    @property
    def api_gateway_replay_journal_max_entries(self) -> int:
        """Maximum entries in the request replay journal."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("replay_journal", {}).get("max_entries", 10000)

    @property
    def api_gateway_dashboard_width(self) -> int:
        """ASCII dashboard width for the API Gateway dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("dashboard", {}).get("width", 60)

    # ------------------------------------------------------------------
    # Blue/Green Deployment Simulation properties
    # ------------------------------------------------------------------

    @property
    def blue_green_enabled(self) -> bool:
        """Whether the Blue/Green Deployment Simulation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("enabled", False)

    @property
    def blue_green_shadow_traffic_count(self) -> int:
        """Number of evaluations for shadow traffic comparison."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("shadow_traffic_count", 10)

    @property
    def blue_green_smoke_test_numbers(self) -> list[int]:
        """Canary numbers for deployment smoke testing."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("smoke_test_numbers", [3, 5, 15, 42, 97])

    @property
    def blue_green_bake_period_ms(self) -> int:
        """Post-cutover observation window in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("bake_period_ms", 50)

    @property
    def blue_green_bake_period_evaluations(self) -> int:
        """Number of evaluations during the bake period."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("bake_period_evaluations", 5)

    @property
    def blue_green_cutover_delay_ms(self) -> int:
        """Dramatic pause before the atomic variable assignment."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("cutover_delay_ms", 10)

    @property
    def blue_green_rollback_auto(self) -> bool:
        """Whether to automatically rollback on bake period failure."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("rollback_auto", False)

    @property
    def blue_green_dashboard_width(self) -> int:
        """ASCII dashboard width for the Blue/Green Deployment dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Graph Database properties
    # ----------------------------------------------------------------

    @property
    def graph_db_enabled(self) -> bool:
        """Whether the graph database subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("graph_db", {}).get("enabled", False)

    @property
    def graph_db_auto_populate(self) -> bool:
        """Whether to auto-populate the graph on startup."""
        self._ensure_loaded()
        return self._raw_config.get("graph_db", {}).get("auto_populate", True)

    @property
    def graph_db_max_visualization_nodes(self) -> int:
        """Maximum number of nodes to display in ASCII visualization."""
        self._ensure_loaded()
        return self._raw_config.get("graph_db", {}).get("max_visualization_nodes", 20)

    @property
    def graph_db_community_max_iterations(self) -> int:
        """Maximum iterations for community detection label propagation."""
        self._ensure_loaded()
        return self._raw_config.get("graph_db", {}).get("community_max_iterations", 20)

    @property
    def graph_db_dashboard_width(self) -> int:
        """ASCII dashboard width for the Graph Database dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("graph_db", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Genetic Algorithm properties
    # ----------------------------------------------------------------

    @property
    def genetic_algorithm_enabled(self) -> bool:
        """Whether the Genetic Algorithm subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("enabled", False)

    @property
    def genetic_algorithm_population_size(self) -> int:
        """Number of chromosomes per generation."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("population_size", 50)

    @property
    def genetic_algorithm_generations(self) -> int:
        """Maximum generations before termination."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("generations", 100)

    @property
    def genetic_algorithm_mutation_rate(self) -> float:
        """Probability of mutation per gene."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("mutation_rate", 0.15)

    @property
    def genetic_algorithm_crossover_rate(self) -> float:
        """Probability of crossover per mating."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("crossover_rate", 0.7)

    @property
    def genetic_algorithm_tournament_size(self) -> int:
        """Tournament selection pool size."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("tournament_size", 5)

    @property
    def genetic_algorithm_elitism_count(self) -> int:
        """Number of top chromosomes preserved each generation."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("elitism_count", 2)

    @property
    def genetic_algorithm_max_genes(self) -> int:
        """Maximum genes (rules) per chromosome."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("max_genes", 8)

    @property
    def genetic_algorithm_min_genes(self) -> int:
        """Minimum genes (rules) per chromosome."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("min_genes", 1)

    @property
    def genetic_algorithm_canonical_seed_pct(self) -> float:
        """Fraction of initial population seeded with canonical rules."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("canonical_seed_pct", 0.10)

    @property
    def genetic_algorithm_convergence_threshold(self) -> float:
        """Fitness above which we declare victory."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("convergence_threshold", 0.95)

    @property
    def genetic_algorithm_diversity_floor(self) -> float:
        """Diversity below which mass extinction is triggered."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("diversity_floor", 0.05)

    @property
    def genetic_algorithm_mass_extinction_survivor_pct(self) -> float:
        """Fraction of population that survives mass extinction."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("mass_extinction_survivor_pct", 0.20)

    @property
    def genetic_algorithm_hall_of_fame_size(self) -> int:
        """Number of all-time best chromosomes to remember."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("hall_of_fame_size", 10)

    @property
    def genetic_algorithm_fitness_weights(self) -> dict[str, float]:
        """Multi-objective fitness function weights."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("fitness_weights", {
            "accuracy": 0.50,
            "coverage": 0.15,
            "distinctness": 0.10,
            "phonetic_harmony": 0.10,
            "mathematical_elegance": 0.15,
        })

    @property
    def genetic_algorithm_seed(self) -> int | None:
        """Random seed for reproducibility."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("seed", None)

    @property
    def genetic_algorithm_dashboard_width(self) -> int:
        """ASCII dashboard width for the GA dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("dashboard", {}).get("width", 60)

    @property
    def genetic_algorithm_fitness_chart_height(self) -> int:
        """Height of the fitness sparkline chart."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("dashboard", {}).get("fitness_chart_height", 10)

    # ----------------------------------------------------------------
    # Natural Language Query Interface configuration properties
    # ----------------------------------------------------------------

    @property
    def nlq_enabled(self) -> bool:
        """Whether the Natural Language Query Interface is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("nlq", {}).get("enabled", False)

    @property
    def nlq_max_query_length(self) -> int:
        """Maximum allowed query string length."""
        self._ensure_loaded()
        return self._raw_config.get("nlq", {}).get("max_query_length", 500)

    @property
    def nlq_max_results(self) -> int:
        """Maximum number of results for LIST queries."""
        self._ensure_loaded()
        return self._raw_config.get("nlq", {}).get("max_results", 1000)

    @property
    def nlq_history_size(self) -> int:
        """Number of queries to retain in session history."""
        self._ensure_loaded()
        return self._raw_config.get("nlq", {}).get("history_size", 50)

    @property
    def nlq_dashboard_width(self) -> int:
        """ASCII dashboard width for NLQ output."""
        self._ensure_loaded()
        return self._raw_config.get("nlq", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Load Testing Framework Properties
    # ----------------------------------------------------------------

    @property
    def load_testing_enabled(self) -> bool:
        """Whether the load testing framework is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("enabled", False)

    @property
    def load_testing_default_profile(self) -> str:
        """Default workload profile for load tests."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("default_profile", "smoke")

    @property
    def load_testing_default_vus(self) -> int:
        """Default number of virtual users."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("default_vus", 10)

    @property
    def load_testing_default_duration_seconds(self) -> int:
        """Default test duration in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("default_duration_seconds", 30)

    @property
    def load_testing_ramp_up_seconds(self) -> int:
        """Ramp-up time in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("ramp_up_seconds", 5)

    @property
    def load_testing_ramp_down_seconds(self) -> int:
        """Ramp-down time in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("ramp_down_seconds", 3)

    @property
    def load_testing_numbers_per_vu(self) -> int:
        """Number of FizzBuzz evaluations per virtual user."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("numbers_per_vu", 100)

    @property
    def load_testing_think_time_ms(self) -> int:
        """Simulated think time between requests in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("think_time_ms", 0)

    @property
    def load_testing_timeout_seconds(self) -> int:
        """Maximum load test duration before forced stop."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("timeout_seconds", 300)

    @property
    def load_testing_dashboard_width(self) -> int:
        """ASCII dashboard width for load testing output."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("dashboard", {}).get("width", 60)

    @property
    def load_testing_histogram_buckets(self) -> int:
        """Number of histogram bars in latency distribution chart."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("dashboard", {}).get("histogram_buckets", 10)

    # ----------------------------------------------------------------
    # Audit Dashboard & Real-Time Event Streaming properties
    # ----------------------------------------------------------------

    @property
    def audit_dashboard_enabled(self) -> bool:
        """Whether the audit dashboard subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("enabled", False)

    @property
    def audit_dashboard_buffer_size(self) -> int:
        """Maximum events in the rolling audit buffer."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("buffer_size", 500)

    @property
    def audit_dashboard_anomaly_enabled(self) -> bool:
        """Whether z-score anomaly detection is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("anomaly_detection", {}).get("enabled", True)

    @property
    def audit_dashboard_anomaly_window_seconds(self) -> float:
        """Tumbling window duration for anomaly rate computation."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("anomaly_detection", {}).get("window_seconds", 10.0)

    @property
    def audit_dashboard_z_score_threshold(self) -> float:
        """Z-score threshold for anomaly alerting."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("anomaly_detection", {}).get("z_score_threshold", 2.0)

    @property
    def audit_dashboard_anomaly_min_samples(self) -> int:
        """Minimum samples before z-score computation is meaningful."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("anomaly_detection", {}).get("min_samples", 5)

    @property
    def audit_dashboard_correlation_enabled(self) -> bool:
        """Whether temporal event correlation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("correlation", {}).get("enabled", True)

    @property
    def audit_dashboard_correlation_window_seconds(self) -> float:
        """Time window for grouping correlated events."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("correlation", {}).get("window_seconds", 5.0)

    @property
    def audit_dashboard_correlation_min_events(self) -> int:
        """Minimum events to form a correlation insight."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("correlation", {}).get("min_events", 2)

    @property
    def audit_dashboard_stream_include_payload(self) -> bool:
        """Whether to include full event payload in stream output."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("stream", {}).get("include_payload", True)

    @property
    def audit_dashboard_width(self) -> int:
        """ASCII dashboard width."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("dashboard", {}).get("width", 80)

    # ----------------------------------------------------------------
    # GitOps Configuration-as-Code Simulator properties
    # ----------------------------------------------------------------

    @property
    def gitops_enabled(self) -> bool:
        """Whether the GitOps Configuration-as-Code Simulator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("enabled", False)

    @property
    def gitops_default_branch(self) -> str:
        """The default (trunk) branch name."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("default_branch", "main")

    @property
    def gitops_auto_commit_on_load(self) -> bool:
        """Whether to create an initial commit when configuration is loaded."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("auto_commit_on_load", True)

    @property
    def gitops_policy_enforcement(self) -> bool:
        """Whether policy rules are enforced on configuration changes."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("policy_enforcement", True)

    @property
    def gitops_dry_run_range_start(self) -> int:
        """Start of FizzBuzz range for dry-run simulation."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("dry_run_range_start", 1)

    @property
    def gitops_dry_run_range_end(self) -> int:
        """End of FizzBuzz range for dry-run simulation."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("dry_run_range_end", 30)

    @property
    def gitops_reconciliation_on_drift(self) -> bool:
        """Whether to auto-reconcile when drift is detected."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("reconciliation_on_drift", True)

    @property
    def gitops_max_commit_history(self) -> int:
        """Maximum commits to retain in the log."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("max_commit_history", 100)

    @property
    def gitops_approval_mode(self) -> str:
        """Approval mode: 'single_operator' or 'committee'."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("approval_mode", "single_operator")

    @property
    def gitops_blast_radius_subsystems(self) -> list[str]:
        """Subsystems tracked for blast radius estimation."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("blast_radius_subsystems", [
            "rules", "engine", "output", "range", "middleware",
            "circuit_breaker", "cache", "feature_flags", "chaos",
        ])

    @property
    def gitops_dashboard_width(self) -> int:
        """ASCII dashboard width for GitOps dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Formal Verification & Proof System properties
    # ----------------------------------------------------------------

    @property
    def formal_verification_enabled(self) -> bool:
        """Whether the Formal Verification & Proof System is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("formal_verification", {}).get("enabled", False)

    @property
    def formal_verification_proof_depth(self) -> int:
        """Maximum numbers to verify in induction proofs."""
        self._ensure_loaded()
        return self._raw_config.get("formal_verification", {}).get("proof_depth", 100)

    @property
    def formal_verification_timeout_ms(self) -> int:
        """Maximum time for property verification in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("formal_verification", {}).get("timeout_ms", 5000)

    @property
    def formal_verification_dashboard_width(self) -> int:
        """ASCII dashboard width for verification dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("formal_verification", {}).get("dashboard", {}).get("width", 60)

    # ------------------------------------------------------------------
    # FizzBuzz-as-a-Service (FBaaS) configuration properties
    # ------------------------------------------------------------------

    @property
    def fbaas_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("enabled", False)

    @property
    def fbaas_default_tier(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("default_tier", "free")

    @property
    def fbaas_free_daily_limit(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("free_tier", {}).get("daily_limit", 10)

    @property
    def fbaas_free_watermark(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("free_tier", {}).get("watermark", "[Powered by FBaaS Free Tier]")

    @property
    def fbaas_free_features(self) -> list[str]:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("free_tier", {}).get("features", ["standard"])

    @property
    def fbaas_pro_daily_limit(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("pro_tier", {}).get("daily_limit", 1000)

    @property
    def fbaas_pro_monthly_price_cents(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("pro_tier", {}).get("monthly_price_cents", 2999)

    @property
    def fbaas_pro_features(self) -> list[str]:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("pro_tier", {}).get("features", [
            "standard", "chain_of_responsibility", "parallel_async", "tracing", "caching", "feature_flags",
        ])

    @property
    def fbaas_enterprise_daily_limit(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("enterprise_tier", {}).get("daily_limit", -1)

    @property
    def fbaas_enterprise_monthly_price_cents(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("enterprise_tier", {}).get("monthly_price_cents", 99999)

    @property
    def fbaas_enterprise_features(self) -> list[str]:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("enterprise_tier", {}).get("features", [
            "standard", "chain_of_responsibility", "parallel_async", "machine_learning",
            "chaos", "tracing", "caching", "feature_flags", "blockchain", "compliance",
        ])

    @property
    def fbaas_sla_free_uptime(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("sla", {}).get("free_uptime_target", 0.95)

    @property
    def fbaas_sla_pro_uptime(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("sla", {}).get("pro_uptime_target", 0.999)

    @property
    def fbaas_sla_enterprise_uptime(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("sla", {}).get("enterprise_uptime_target", 0.9999)

    @property
    def fbaas_sla_free_response_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("sla", {}).get("free_response_time_ms", 500)

    @property
    def fbaas_sla_pro_response_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("sla", {}).get("pro_response_time_ms", 100)

    @property
    def fbaas_sla_enterprise_response_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("sla", {}).get("enterprise_response_time_ms", 10)

    @property
    def fbaas_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fbaas", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Time-Travel Debugger Configuration Properties
    # ----------------------------------------------------------------

    @property
    def time_travel_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("enabled", False)

    @property
    def time_travel_max_snapshots(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("max_snapshots", 10000)

    @property
    def time_travel_integrity_checks(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("integrity_checks", True)

    @property
    def time_travel_anomaly_detection(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("anomaly_detection", True)

    @property
    def time_travel_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("dashboard", {}).get("width", 60)

    @property
    def time_travel_timeline_markers(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("dashboard", {}).get("timeline_markers", True)

    # ----------------------------------------------------------------
    # Custom Bytecode VM (FBVM) properties
    # ----------------------------------------------------------------

    @property
    def vm_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("enabled", False)

    @property
    def vm_cycle_limit(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("cycle_limit", 10000)

    @property
    def vm_trace_execution(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("trace_execution", False)

    @property
    def vm_enable_optimizer(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("enable_optimizer", True)

    @property
    def vm_register_count(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("register_count", 8)

    @property
    def vm_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("dashboard", {}).get("width", 60)

    @property
    def vm_dashboard_show_registers(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("dashboard", {}).get("show_registers", True)

    @property
    def vm_dashboard_show_disassembly(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("dashboard", {}).get("show_disassembly", True)

    # ----------------------------------------------------------------
    # Query Optimizer properties
    # ----------------------------------------------------------------

    @property
    def query_optimizer_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("query_optimizer", {}).get("enabled", False)

    @property
    def query_optimizer_cost_weights(self) -> dict[str, float]:
        self._ensure_loaded()
        defaults = {"modulo": 1.0, "cache_miss": 5.0, "ml": 20.0, "compliance": 10.0, "blockchain": 50.0}
        return self._raw_config.get("query_optimizer", {}).get("cost_weights", defaults)

    @property
    def query_optimizer_plan_cache_max_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("query_optimizer", {}).get("plan_cache_max_size", 256)

    @property
    def query_optimizer_max_plans(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("query_optimizer", {}).get("max_plans", 16)

    @property
    def query_optimizer_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("query_optimizer", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Distributed Paxos Consensus properties
    # ----------------------------------------------------------------

    @property
    def paxos_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("enabled", False)

    @property
    def paxos_num_nodes(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("num_nodes", 5)

    @property
    def paxos_message_delay_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("message_delay_ms", 0)

    @property
    def paxos_message_drop_rate(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("message_drop_rate", 0.0)

    @property
    def paxos_byzantine_mode(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("byzantine_mode", False)

    @property
    def paxos_byzantine_lie_probability(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("byzantine_lie_probability", 1.0)

    @property
    def paxos_partition_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("partition_enabled", False)

    @property
    def paxos_partition_groups(self) -> list[list[int]]:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("partition_groups", [[0, 1, 2], [3, 4]])

    @property
    def paxos_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("paxos", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Quantum Computing Simulator properties
    # ----------------------------------------------------------------

    @property
    def quantum_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("enabled", False)

    @property
    def quantum_num_qubits(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("num_qubits", 4)

    @property
    def quantum_max_measurement_attempts(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("max_measurement_attempts", 10)

    @property
    def quantum_decoherence_threshold(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("decoherence_threshold", 0.001)

    @property
    def quantum_fallback_to_classical(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("fallback_to_classical", True)

    @property
    def quantum_shor_max_period_attempts(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("shor_max_period_attempts", 5)

    @property
    def quantum_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("dashboard", {}).get("width", 60)

    @property
    def quantum_dashboard_show_circuit(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("dashboard", {}).get("show_circuit", True)

    # ------------------------------------------------------------------
    # Cross-Compiler properties
    # ------------------------------------------------------------------
    @property
    def cross_compiler_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("enabled", False)

    @property
    def cross_compiler_verify_round_trip(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("verify_round_trip", True)

    @property
    def cross_compiler_verification_range_end(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("verification_range_end", 100)

    @property
    def cross_compiler_emit_comments(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("emit_comments", True)

    @property
    def cross_compiler_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("dashboard", {}).get("width", 60)

    @property
    def cross_compiler_dashboard_show_ir(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("dashboard", {}).get("show_ir", False)

    # ------------------------------------------------------------------
    # Federated Learning properties
    # ------------------------------------------------------------------

    @property
    def federated_learning_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("enabled", False)

    @property
    def federated_learning_num_rounds(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("num_rounds", 10)

    @property
    def federated_learning_num_clients(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("num_clients", 5)

    @property
    def federated_learning_local_epochs(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("local_epochs", 3)

    @property
    def federated_learning_learning_rate(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("learning_rate", 0.5)

    @property
    def federated_learning_aggregation_strategy(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("aggregation_strategy", "fedavg")

    @property
    def federated_learning_fedprox_mu(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get("fedprox_mu", 0.01)

    @property
    def federated_learning_dp_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "differential_privacy", {}
        ).get("enabled", True)

    @property
    def federated_learning_dp_epsilon(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "differential_privacy", {}
        ).get("epsilon_budget", 10.0)

    @property
    def federated_learning_dp_delta(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "differential_privacy", {}
        ).get("delta", 1e-5)

    @property
    def federated_learning_dp_noise_multiplier(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "differential_privacy", {}
        ).get("noise_multiplier", 1.0)

    @property
    def federated_learning_dp_max_grad_norm(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "differential_privacy", {}
        ).get("max_grad_norm", 1.0)

    @property
    def federated_learning_convergence_target(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "convergence", {}
        ).get("target_accuracy", 95.0)

    @property
    def federated_learning_convergence_patience(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "convergence", {}
        ).get("patience", 3)

    @property
    def federated_learning_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "dashboard", {}
        ).get("width", 60)

    @property
    def federated_learning_dashboard_show_convergence(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "dashboard", {}
        ).get("show_convergence_curve", True)

    @property
    def federated_learning_dashboard_show_clients(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("federated_learning", {}).get(
            "dashboard", {}
        ).get("show_client_details", True)

    # ── Knowledge Graph & Domain Ontology ──

    @property
    def knowledge_graph_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("enabled", False)

    @property
    def knowledge_graph_max_inference_iterations(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("max_inference_iterations", 100)

    @property
    def knowledge_graph_domain_range_start(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("domain_range_start", 1)

    @property
    def knowledge_graph_domain_range_end(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("domain_range_end", 100)

    @property
    def knowledge_graph_enable_owl_reasoning(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("enable_owl_reasoning", True)

    @property
    def knowledge_graph_enable_visualization(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("enable_visualization", True)

    @property
    def knowledge_graph_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("dashboard", {}).get("width", 60)

    @property
    def knowledge_graph_dashboard_show_class_hierarchy(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("dashboard", {}).get("show_class_hierarchy", True)

    @property
    def knowledge_graph_dashboard_show_triple_stats(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("dashboard", {}).get("show_triple_stats", True)

    @property
    def knowledge_graph_dashboard_show_inference_stats(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("dashboard", {}).get("show_inference_stats", True)

    # ── Self-Modifying Code properties ────────────────────────

    @property
    def self_modifying_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("enabled", False)

    @property
    def self_modifying_mutation_rate(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("mutation_rate", 0.05)

    @property
    def self_modifying_max_ast_depth(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("max_ast_depth", 10)

    @property
    def self_modifying_correctness_floor(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("correctness_floor", 0.95)

    @property
    def self_modifying_max_mutations_per_session(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("max_mutations_per_session", 100)

    @property
    def self_modifying_kill_switch(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("kill_switch", True)

    @property
    def self_modifying_fitness_correctness_weight(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("fitness_weights", {}).get("correctness", 0.70)

    @property
    def self_modifying_fitness_latency_weight(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("fitness_weights", {}).get("latency", 0.20)

    @property
    def self_modifying_fitness_compactness_weight(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("fitness_weights", {}).get("compactness", 0.10)

    @property
    def self_modifying_enabled_operators(self) -> list[str]:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("enabled_operators", [
            "DivisorShift", "LabelSwap", "BranchInvert", "InsertShortCircuit",
            "DeadCodePrune", "SubtreeSwap", "DuplicateSubtree", "NegateCondition",
            "ConstantFold", "InsertRedundantCheck", "ShuffleChildren", "WrapInConditional",
        ])

    @property
    def self_modifying_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("dashboard", {}).get("width", 60)

    @property
    def self_modifying_dashboard_show_ast(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("dashboard", {}).get("show_ast", True)

    @property
    def self_modifying_dashboard_show_history(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("dashboard", {}).get("show_history", True)

    @property
    def self_modifying_dashboard_show_fitness(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("dashboard", {}).get("show_fitness", True)

    # ── OS Kernel properties ────────────────────────────────

    @property
    def kernel_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("enabled", False)

    @property
    def kernel_scheduler(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("scheduler", "rr")

    @property
    def kernel_time_quantum_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("time_quantum_ms", 10.0)

    @property
    def kernel_max_processes(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("max_processes", 256)

    @property
    def kernel_page_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("page_size", 64)

    @property
    def kernel_tlb_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("tlb_size", 16)

    @property
    def kernel_physical_pages(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("physical_pages", 128)

    @property
    def kernel_swap_pages(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("swap_pages", 256)

    @property
    def kernel_irq_vectors(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("irq_vectors", 16)

    @property
    def kernel_boot_delay_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("boot_delay_ms", 5.0)

    @property
    def kernel_context_switch_overhead_us(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("context_switch_overhead_us", 50.0)

    @property
    def kernel_cfs_default_weight(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("cfs_default_weight", 1024)

    @property
    def kernel_cfs_min_granularity_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("cfs_min_granularity_ms", 1.0)

    @property
    def kernel_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("dashboard", {}).get("width", 60)

    @property
    def kernel_dashboard_show_process_table(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("dashboard", {}).get("show_process_table", True)

    @property
    def kernel_dashboard_show_memory_map(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("dashboard", {}).get("show_memory_map", True)

    @property
    def kernel_dashboard_show_interrupt_log(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("dashboard", {}).get("show_interrupt_log", True)

    # ------------------------------------------------------------------
    # Peer-to-Peer Gossip Network properties
    # ------------------------------------------------------------------

    @property
    def p2p_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("enabled", False)

    @property
    def p2p_num_nodes(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("num_nodes", 7)

    @property
    def p2p_k_bucket_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("k_bucket_size", 3)

    @property
    def p2p_gossip_fanout(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("gossip_fanout", 3)

    @property
    def p2p_suspect_timeout_rounds(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("suspect_timeout_rounds", 3)

    @property
    def p2p_max_gossip_rounds(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("max_gossip_rounds", 20)

    @property
    def p2p_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("p2p", {}).get("dashboard", {}).get("width", 60)

    # ------------------------------------------------------------------
    # Digital Twin Simulation properties
    # ------------------------------------------------------------------

    @property
    def digital_twin_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("enabled", False)

    @property
    def digital_twin_monte_carlo_runs(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("monte_carlo_runs", 1000)

    @property
    def digital_twin_jitter_stddev(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("jitter_stddev", 0.05)

    @property
    def digital_twin_failure_jitter(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("failure_jitter", 0.02)

    @property
    def digital_twin_drift_threshold_fdu(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("drift_threshold_fdu", 5.0)

    @property
    def digital_twin_anomaly_sigma(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("anomaly_sigma", 2.0)

    @property
    def digital_twin_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("dashboard", {}).get("width", 60)

    @property
    def digital_twin_dashboard_show_histogram(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("dashboard", {}).get("show_histogram", True)

    @property
    def digital_twin_dashboard_show_drift_gauge(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("dashboard", {}).get("show_drift_gauge", True)

    @property
    def digital_twin_histogram_buckets(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("dashboard", {}).get("histogram_buckets", 20)

    # ------------------------------------------------------------------
    # FizzLang DSL properties
    # ------------------------------------------------------------------

    @property
    def fizzlang_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("enabled", False)

    @property
    def fizzlang_max_program_length(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("max_program_length", 10000)

    @property
    def fizzlang_max_rules(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("max_rules", 50)

    @property
    def fizzlang_max_let_bindings(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("max_let_bindings", 100)

    @property
    def fizzlang_strict_type_checking(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("strict_type_checking", True)

    @property
    def fizzlang_stdlib_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("stdlib_enabled", True)

    @property
    def fizzlang_repl_prompt(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("repl", {}).get("prompt", "fizz> ")

    @property
    def fizzlang_repl_history_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("repl", {}).get("history_size", 100)

    @property
    def fizzlang_repl_show_tokens(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("repl", {}).get("show_tokens", False)

    @property
    def fizzlang_repl_show_ast(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("repl", {}).get("show_ast", False)

    @property
    def fizzlang_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("dashboard", {}).get("width", 60)

    @property
    def fizzlang_dashboard_show_source_stats(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("dashboard", {}).get("show_source_stats", True)

    @property
    def fizzlang_dashboard_show_complexity_index(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("dashboard", {}).get("show_complexity_index", True)

    # ------------------------------------------------------------------
    # Archaeological Recovery System properties
    # ------------------------------------------------------------------

    @property
    def archaeology_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("enabled", False)

    @property
    def archaeology_corruption_rate(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("corruption_rate", 0.15)

    @property
    def archaeology_min_fragments(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("min_fragments_for_reconstruction", 2)

    @property
    def archaeology_confidence_threshold(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("confidence_threshold", 0.6)

    @property
    def archaeology_enable_corruption(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("enable_corruption_simulation", True)

    @property
    def archaeology_seed(self) -> int | None:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("seed", None)

    @property
    def archaeology_strata_weights(self) -> dict[str, float]:
        self._ensure_loaded()
        defaults = {
            "blockchain": 1.0,
            "event_store": 0.9,
            "cache_coherence": 0.7,
            "rule_engine": 0.8,
            "middleware_pipeline": 0.6,
            "metrics": 0.5,
            "cache_eulogies": 0.4,
        }
        return self._raw_config.get("archaeology", {}).get("strata_weights", defaults)

    @property
    def archaeology_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("dashboard", {}).get("width", 60)

    @property
    def archaeology_dashboard_show_strata(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("dashboard", {}).get("show_strata_reliability", True)

    @property
    def archaeology_dashboard_show_bayesian(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("dashboard", {}).get("show_bayesian_posterior", True)

    @property
    def archaeology_dashboard_show_corruption(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("dashboard", {}).get("show_corruption_report", True)

    # Recommendation Engine properties
    # ------------------------------------------------------------------

    @property
    def recommendation_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("enabled", False)

    @property
    def recommendation_collaborative_weight(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("collaborative_weight", 0.6)

    @property
    def recommendation_content_weight(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("content_weight", 0.4)

    @property
    def recommendation_serendipity_factor(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("serendipity_factor", 0.1)

    @property
    def recommendation_num_recommendations(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("num_recommendations", 5)

    @property
    def recommendation_min_evaluations(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("min_evaluations_for_personalization", 3)

    @property
    def recommendation_max_similar_users(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("max_similar_users", 10)

    @property
    def recommendation_popular_items_fallback_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("popular_items_fallback_size", 10)

    @property
    def recommendation_seed(self) -> int | None:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("seed", None)

    @property
    def recommendation_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("dashboard", {}).get("width", 60)

    @property
    def recommendation_dashboard_show_feature_vectors(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("dashboard", {}).get("show_feature_vectors", True)

    @property
    def recommendation_dashboard_show_user_profiles(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("dashboard", {}).get("show_user_profiles", True)

    @property
    def recommendation_dashboard_show_similarity_matrix(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("dashboard", {}).get("show_similarity_matrix", True)

    # ------------------------------------------------------------------
    # Dependent Type System & Curry-Howard Proof Engine properties
    # ------------------------------------------------------------------

    @property
    def dependent_types_enabled(self) -> bool:
        """Whether the Dependent Type System is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("enabled", False)

    @property
    def dependent_types_max_beta_reductions(self) -> int:
        """Safety limit for beta-normalization steps."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("max_beta_reductions", 1000)

    @property
    def dependent_types_max_unification_depth(self) -> int:
        """Maximum depth for first-order unification."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("max_unification_depth", 100)

    @property
    def dependent_types_enable_proof_cache(self) -> bool:
        """Whether to cache proof terms."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("enable_proof_cache", True)

    @property
    def dependent_types_proof_cache_size(self) -> int:
        """Maximum entries in the proof cache."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("proof_cache_size", 4096)

    @property
    def dependent_types_enable_type_inference(self) -> bool:
        """Whether bidirectional type inference is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("enable_type_inference", True)

    @property
    def dependent_types_strict_mode(self) -> bool:
        """Whether strict mode (no auto tactic) is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("strict_mode", False)

    @property
    def dependent_types_dashboard_width(self) -> int:
        """Dashboard width for the type system dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("dashboard", {}).get("width", 60)

    @property
    def dependent_types_dashboard_show_curry_howard(self) -> bool:
        """Whether to show the Curry-Howard correspondence table."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("dashboard", {}).get("show_curry_howard", True)

    @property
    def dependent_types_dashboard_show_proof_tree(self) -> bool:
        """Whether to show proof tree structure."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("dashboard", {}).get("show_proof_tree", True)

    @property
    def dependent_types_dashboard_show_complexity_index(self) -> bool:
        """Whether to show the Proof Complexity Index."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("dashboard", {}).get("show_complexity_index", True)

    # ------------------------------------------------------------------
    # FizzKube Container Orchestration properties
    # ------------------------------------------------------------------

    @property
    def fizzkube_enabled(self) -> bool:
        """Whether FizzKube container orchestration is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("enabled", False)

    @property
    def fizzkube_num_nodes(self) -> int:
        """Number of simulated worker nodes in the cluster."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("num_nodes", 3)

    @property
    def fizzkube_default_replicas(self) -> int:
        """Default desired replica count per ReplicaSet."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("default_replicas", 2)

    @property
    def fizzkube_cpu_per_node(self) -> int:
        """CPU capacity per node in milliFizz."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("cpu_per_node", 4000)

    @property
    def fizzkube_memory_per_node(self) -> int:
        """Memory capacity per node in FizzBytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("memory_per_node", 8192)

    @property
    def fizzkube_pod_cpu_request(self) -> int:
        """CPU requested per pod in milliFizz."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("pod_cpu_request", 100)

    @property
    def fizzkube_pod_memory_request(self) -> int:
        """Memory requested per pod in FizzBytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("pod_memory_request", 128)

    @property
    def fizzkube_pod_cpu_limit(self) -> int:
        """CPU limit per pod in milliFizz."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("pod_cpu_limit", 200)

    @property
    def fizzkube_pod_memory_limit(self) -> int:
        """Memory limit per pod in FizzBytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("pod_memory_limit", 256)

    @property
    def fizzkube_hpa_enabled(self) -> bool:
        """Whether the Horizontal Pod Autoscaler is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("enabled", True)

    @property
    def fizzkube_hpa_min_replicas(self) -> int:
        """Minimum replica count for HPA."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("min_replicas", 1)

    @property
    def fizzkube_hpa_max_replicas(self) -> int:
        """Maximum replica count for HPA."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("max_replicas", 10)

    @property
    def fizzkube_hpa_target_cpu_utilization(self) -> int:
        """Target CPU utilization percentage for HPA."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("target_cpu_utilization", 70)

    @property
    def fizzkube_hpa_scale_up_cooldown(self) -> int:
        """Cooldown seconds after scale-up."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("scale_up_cooldown_seconds", 15)

    @property
    def fizzkube_hpa_scale_down_cooldown(self) -> int:
        """Cooldown seconds after scale-down."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("hpa", {}).get("scale_down_cooldown_seconds", 30)

    @property
    def fizzkube_namespace(self) -> str:
        """Default Kubernetes namespace."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("namespace", "fizzbuzz-production")

    @property
    def fizzkube_resource_quota_cpu(self) -> int:
        """Namespace CPU quota in milliFizz."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("resource_quota", {}).get("cpu_limit", 16000)

    @property
    def fizzkube_resource_quota_memory(self) -> int:
        """Namespace memory quota in FizzBytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("resource_quota", {}).get("memory_limit", 32768)

    @property
    def fizzkube_dashboard_width(self) -> int:
        """Dashboard width for the FizzKube dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkube", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzPM Package Manager
    # ----------------------------------------------------------------

    @property
    def fizzpm_enabled(self) -> bool:
        """Whether the FizzPM Package Manager is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("enabled", False)

    @property
    def fizzpm_audit_on_install(self) -> bool:
        """Whether to automatically run vulnerability scan after install."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("audit_on_install", True)

    @property
    def fizzpm_default_packages(self) -> list[str]:
        """Packages auto-installed when FizzPM is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("default_packages", ["fizzbuzz-core"])

    @property
    def fizzpm_lockfile_path(self) -> str:
        """Path to the deterministic lockfile."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("lockfile_path", "fizzpm.lock")

    @property
    def fizzpm_registry_mirror(self) -> str:
        """The fictional FizzPM registry URL."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("registry_mirror", "https://registry.fizzpm.io")

    @property
    def fizzpm_dashboard_width(self) -> int:
        """Dashboard width for the FizzPM dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzSQL Relational Query Engine
    # ----------------------------------------------------------------

    @property
    def fizzsql_enabled(self) -> bool:
        """Whether the FizzSQL Relational Query Engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("enabled", False)

    @property
    def fizzsql_max_query_length(self) -> int:
        """Maximum allowed query length in characters."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("max_query_length", 4096)

    @property
    def fizzsql_slow_query_threshold_ms(self) -> float:
        """Queries exceeding this threshold are logged as slow."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("slow_query_threshold_ms", 50.0)

    @property
    def fizzsql_max_result_rows(self) -> int:
        """Maximum rows returned before truncation."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("max_result_rows", 10000)

    @property
    def fizzsql_enable_query_history(self) -> bool:
        """Whether to maintain a query history."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("enable_query_history", True)

    @property
    def fizzsql_query_history_size(self) -> int:
        """Maximum entries in the query history ring buffer."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("query_history_size", 100)

    @property
    def fizzsql_dashboard_width(self) -> int:
        """Dashboard width for the FizzSQL dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzDAP Debug Adapter Protocol
    # ----------------------------------------------------------------

    @property
    def fizzdap_enabled(self) -> bool:
        """Whether the FizzDAP Debug Adapter Protocol server is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("enabled", False)

    @property
    def fizzdap_port(self) -> int:
        """The DAP server port (simulated)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("port", 4711)

    @property
    def fizzdap_auto_stop_on_entry(self) -> bool:
        """Whether to automatically break on first evaluation."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("auto_stop_on_entry", True)

    @property
    def fizzdap_max_breakpoints(self) -> int:
        """Maximum concurrent breakpoints."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("max_breakpoints", 256)

    @property
    def fizzdap_step_granularity(self) -> str:
        """Step granularity: middleware | instruction | evaluation."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("step_granularity", "middleware")

    @property
    def fizzdap_include_cache_state(self) -> bool:
        """Whether to expose cache MESI states as debugger variables."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("variable_inspection", {}).get("include_cache_state", True)

    @property
    def fizzdap_include_circuit_breaker(self) -> bool:
        """Whether to expose circuit breaker state as variables."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("variable_inspection", {}).get("include_circuit_breaker", True)

    @property
    def fizzdap_include_quantum_state(self) -> bool:
        """Whether to expose quantum register amplitudes as variables."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("variable_inspection", {}).get("include_quantum_state", True)

    @property
    def fizzdap_include_middleware_timings(self) -> bool:
        """Whether to expose per-middleware timing data."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("variable_inspection", {}).get("include_middleware_timings", True)

    @property
    def fizzdap_max_string_length(self) -> int:
        """Maximum string length for variable inspection."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("variable_inspection", {}).get("max_string_length", 1024)

    @property
    def fizzdap_include_source_location(self) -> bool:
        """Whether to synthesize source locations for middleware stack frames."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("stack_frame", {}).get("include_source_location", True)

    @property
    def fizzdap_max_frames(self) -> int:
        """Maximum stack frame depth."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("stack_frame", {}).get("max_frames", 64)

    @property
    def fizzdap_dashboard_width(self) -> int:
        """Dashboard width for the FizzDAP dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("dashboard", {}).get("width", 60)

    @property
    def fizzdap_dashboard_show_breakpoints(self) -> bool:
        """Whether to show breakpoint table in dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("dashboard", {}).get("show_breakpoints", True)

    @property
    def fizzdap_dashboard_show_stack_trace(self) -> bool:
        """Whether to show synthetic stack trace in dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("dashboard", {}).get("show_stack_trace", True)

    @property
    def fizzdap_dashboard_show_variables(self) -> bool:
        """Whether to show variable inspector in dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("dashboard", {}).get("show_variables", True)

    @property
    def fizzdap_dashboard_show_complexity_index(self) -> bool:
        """Whether to show Debug Complexity Index in dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("dashboard", {}).get("show_complexity_index", True)

    # ----------------------------------------------------------------
    # IP Office Configuration Properties
    # ----------------------------------------------------------------

    @property
    def ip_office_enabled(self) -> bool:
        """Whether the FizzBuzz Intellectual Property Office is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("enabled", False)

    @property
    def ip_office_trademark_similarity_threshold(self) -> float:
        """Phonetic similarity threshold for trademark conflict detection."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("trademark_similarity_threshold", 0.7)

    @property
    def ip_office_patent_novelty_threshold(self) -> float:
        """Prior art similarity threshold for patent novelty examination."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("patent_novelty_threshold", 0.5)

    @property
    def ip_office_copyright_originality_threshold(self) -> float:
        """Levenshtein distance threshold for copyright originality scoring."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("copyright_originality_threshold", 0.3)

    @property
    def ip_office_default_license(self) -> str:
        """Default license type for new IP registrations."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("default_license", "FBPL")

    @property
    def ip_office_trademark_renewal_days(self) -> int:
        """Number of days before trademark registration expires."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("trademark_renewal_days", 365)

    @property
    def ip_office_dashboard_width(self) -> int:
        """Dashboard width for the IP Office dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Distributed Lock Manager (FizzLock) configuration properties
    # ----------------------------------------------------------------

    @property
    def distributed_locks_enabled(self) -> bool:
        """Whether the Distributed Lock Manager is active."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("enabled", False)

    @property
    def distributed_locks_policy(self) -> str:
        """Deadlock prevention policy: 'wait-die' or 'wound-wait'."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("policy", "wait-die")

    @property
    def distributed_locks_lease_duration(self) -> float:
        """Lock lease time-to-live in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("lease_duration_s", 30.0)

    @property
    def distributed_locks_grace_period(self) -> float:
        """Grace period before forced lease revocation in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("grace_period_s", 5.0)

    @property
    def distributed_locks_check_interval(self) -> float:
        """Lease reaper background check interval in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("check_interval_s", 1.0)

    @property
    def distributed_locks_acquisition_timeout(self) -> float:
        """Maximum time to wait for a lock acquisition in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("acquisition_timeout_s", 5.0)

    @property
    def distributed_locks_hot_lock_threshold_ms(self) -> float:
        """Contention threshold in milliseconds for hot-lock detection."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("hot_lock_threshold_ms", 10.0)

    @property
    def distributed_locks_dashboard_width(self) -> int:
        """Dashboard width for the FizzLock dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # Change Data Capture (FizzCDC) configuration properties
    # ----------------------------------------------------------------

    @property
    def cdc_enabled(self) -> bool:
        """Whether the Change Data Capture subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("enabled", False)

    @property
    def cdc_relay_interval_s(self) -> float:
        """Background relay sweep interval in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("relay_interval_s", 0.5)

    @property
    def cdc_outbox_capacity(self) -> int:
        """Maximum number of events in the outbox before back-pressure."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("outbox_capacity", 10000)

    @property
    def cdc_schema_compatibility(self) -> str:
        """Schema compatibility mode: full, forward, or backward."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("schema_compatibility", "full")

    @property
    def cdc_sinks(self) -> list[str]:
        """List of enabled sink connector names."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("sinks", ["log", "metrics"])

    @property
    def cdc_dashboard_width(self) -> int:
        """Dashboard width for the CDC dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzBill Billing & Revenue Recognition properties
    # ----------------------------------------------------------------

    @property
    def billing_enabled(self) -> bool:
        """Whether the FizzBill billing subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("billing", {}).get("enabled", False)

    @property
    def billing_default_tier(self) -> str:
        """Default subscription tier for new tenants."""
        self._ensure_loaded()
        return self._raw_config.get("billing", {}).get("default_tier", "free")

    @property
    def billing_default_tenant_id(self) -> str:
        """Default tenant identifier."""
        self._ensure_loaded()
        return self._raw_config.get("billing", {}).get("default_tenant_id", "tenant-default")

    @property
    def billing_spending_cap(self) -> Optional[float]:
        """Optional monthly spending cap in FizzBucks."""
        self._ensure_loaded()
        return self._raw_config.get("billing", {}).get("spending_cap", None)

    @property
    def billing_dashboard_width(self) -> int:
        """Dashboard width for the billing dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("billing", {}).get("dashboard", {}).get("width", 60)


    # ------------------------------------------------------------------
    # FizzCorr Observability Correlation Engine properties
    # ------------------------------------------------------------------

    @property
    def observability_correlation_enabled(self) -> bool:
        """Whether the FizzCorr Observability Correlation Engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("enabled", False)

    @property
    def observability_correlation_temporal_window_seconds(self) -> float:
        """Maximum time delta for temporal correlation."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("temporal_window_seconds", 2.0)

    @property
    def observability_correlation_confidence_threshold(self) -> float:
        """Minimum confidence score to accept a correlation."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("confidence_threshold", 0.3)

    @property
    def observability_correlation_anomaly_latency_threshold_ms(self) -> float:
        """Latency threshold for anomaly detection in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("anomaly_latency_threshold_ms", 50.0)

    @property
    def observability_correlation_anomaly_error_burst_window_s(self) -> float:
        """Window for error burst detection in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("anomaly_error_burst_window_s", 5.0)

    @property
    def observability_correlation_anomaly_error_burst_threshold(self) -> int:
        """Number of errors in window to trigger burst anomaly."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("anomaly_error_burst_threshold", 3)

    @property
    def observability_correlation_anomaly_metric_deviation_sigma(self) -> float:
        """Standard deviations for metric deviation anomaly."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("anomaly_metric_deviation_sigma", 2.0)

    @property
    def observability_correlation_causal_patterns(self) -> list[dict]:
        """Known causal patterns for rule-based correlation."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("causal_patterns", [])

    @property
    def observability_correlation_dashboard_width(self) -> int:
        """Dashboard width for the observability correlation dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("dashboard", {}).get("width", 60)

    # ------------------------------------------------------------------
    # FizzJIT — Runtime Code Generation properties
    # ------------------------------------------------------------------

    @property
    def jit_enabled(self) -> bool:
        """Whether the FizzJIT trace-based compiler is active."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("enabled", False)

    @property
    def jit_threshold(self) -> int:
        """Number of range evaluations before JIT compilation triggers."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("threshold", 3)

    @property
    def jit_cache_size(self) -> int:
        """Maximum number of compiled traces in the LRU cache."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("cache_size", 64)

    @property
    def jit_enable_constant_folding(self) -> bool:
        """Whether constant folding optimization pass is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("enable_constant_folding", True)

    @property
    def jit_enable_dce(self) -> bool:
        """Whether dead code elimination optimization pass is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("enable_dce", True)

    @property
    def jit_enable_guard_hoisting(self) -> bool:
        """Whether guard hoisting optimization pass is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("enable_guard_hoisting", True)

    @property
    def jit_enable_type_specialization(self) -> bool:
        """Whether type specialization optimization pass is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("enable_type_specialization", True)

    @property
    def jit_dashboard_width(self) -> int:
        """Dashboard width for the JIT compiler dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("dashboard", {}).get("width", 60)

    # ------------------------------------------------------------------
    # FizzCap — Capability-Based Security properties
    # ------------------------------------------------------------------

    @property
    def capability_security_enabled(self) -> bool:
        """Whether the FizzCap capability-based security model is active."""
        self._ensure_loaded()
        return self._raw_config.get("capability_security", {}).get("enabled", False)

    @property
    def capability_security_mode(self) -> str:
        """Capability enforcement mode: native, bridge, or audit-only."""
        self._ensure_loaded()
        return self._raw_config.get("capability_security", {}).get("mode", "native")

    @property
    def capability_security_secret_key(self) -> str:
        """HMAC-SHA256 secret key for capability signing."""
        self._ensure_loaded()
        return self._raw_config.get("capability_security", {}).get("secret_key", "fizzcap-default-key")

    @property
    def capability_security_default_resource(self) -> str:
        """Default resource identifier for capability middleware."""
        self._ensure_loaded()
        return self._raw_config.get("capability_security", {}).get("default_resource", "fizzbuzz:evaluation")

    @property
    def capability_security_dashboard_width(self) -> int:
        """Dashboard width for the FizzCap dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("capability_security", {}).get("dashboard", {}).get("width", 60)

    # ------------------------------------------------------------------
    # FizzOTel — OpenTelemetry-Compatible Distributed Tracing properties
    # ------------------------------------------------------------------

    @property
    def otel_enabled(self) -> bool:
        """Whether the FizzOTel distributed tracing subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("enabled", False)

    @property
    def otel_export_format(self) -> str:
        """Export format for OTel traces: otlp, zipkin, or console."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("export_format", "otlp")

    @property
    def otel_sampling_rate(self) -> float:
        """Probabilistic sampling rate (0.0 to 1.0)."""
        self._ensure_loaded()
        return float(self._raw_config.get("otel", {}).get("sampling_rate", 1.0))

    @property
    def otel_batch_mode(self) -> bool:
        """Whether to use BatchSpanProcessor instead of SimpleSpanProcessor."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("batch_mode", False)

    @property
    def otel_max_queue_size(self) -> int:
        """Maximum spans in the batch queue."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("max_queue_size", 2048)

    @property
    def otel_max_batch_size(self) -> int:
        """Maximum spans per export batch."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("max_batch_size", 512)

    @property
    def otel_dashboard_width(self) -> int:
        """Dashboard width for the FizzOTel dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("dashboard", {}).get("width", 60)

    # ------------------------------------------------------------------
    # FizzWAL — Write-Ahead Intent Log properties
    # ------------------------------------------------------------------

    @property
    def fizzwal_enabled(self) -> bool:
        """Whether the FizzWAL Write-Ahead Intent Log subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwal", {}).get("enabled", False)

    @property
    def fizzwal_mode(self) -> str:
        """Execution mode: optimistic, pessimistic, or speculative."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwal", {}).get("mode", "optimistic")

    @property
    def fizzwal_checkpoint_interval(self) -> int:
        """Number of log records between automatic fuzzy checkpoints."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwal", {}).get("checkpoint_interval", 100)

    @property
    def fizzwal_crash_recovery_on_startup(self) -> bool:
        """Whether to run ARIES 3-phase recovery on startup."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwal", {}).get("crash_recovery_on_startup", False)

    @property
    def fizzwal_dashboard_width(self) -> int:
        """Dashboard width for the FizzWAL dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwal", {}).get("dashboard", {}).get("width", 60)

    # ------------------------------------------------------------------
    # FizzCRDT — Conflict-Free Replicated Data Types properties
    # ------------------------------------------------------------------

    @property
    def crdt_enabled(self) -> bool:
        """Whether the FizzCRDT subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("crdt", {}).get("enabled", False)

    @property
    def crdt_replica_count(self) -> int:
        """Number of simulated replicas for CRDT replication."""
        self._ensure_loaded()
        return self._raw_config.get("crdt", {}).get("replica_count", 3)

    @property
    def crdt_anti_entropy_interval(self) -> int:
        """Number of evaluations between anti-entropy rounds."""
        self._ensure_loaded()
        return self._raw_config.get("crdt", {}).get("anti_entropy_interval", 1)

    @property
    def crdt_dashboard_width(self) -> int:
        """Dashboard width for the FizzCRDT dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("crdt", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzGrammar -- Formal Grammar & Parser Generator
    # ----------------------------------------------------------------

    @property
    def grammar_enabled(self) -> bool:
        """Whether the FizzGrammar subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("grammar", {}).get("enabled", False)

    @property
    def grammar_dashboard_width(self) -> int:
        """Dashboard width for the FizzGrammar dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("grammar", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzAlloc — Custom Memory Allocator
    # ----------------------------------------------------------------

    @property
    def alloc_enabled(self) -> bool:
        """Whether the FizzAlloc memory allocator subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("enabled", False)

    @property
    def alloc_gc_enabled(self) -> bool:
        """Whether the tri-generational garbage collector is active."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("gc_enabled", True)

    @property
    def alloc_gc_young_threshold(self) -> int:
        """Number of GC cycles before promoting young objects to tenured."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("gc_young_threshold", 10)

    @property
    def alloc_gc_tenured_threshold(self) -> int:
        """Number of GC cycles before promoting tenured objects to permanent."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("gc_tenured_threshold", 5)

    @property
    def alloc_slab_sizes(self) -> dict[str, int]:
        """Slab slot sizes by object type (simulated bytes)."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("slab_sizes", {
            "result": 128,
            "cache_entry": 96,
            "event": 256,
        })

    @property
    def alloc_arena_tiers(self) -> list[int]:
        """Arena size tiers in simulated bytes."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("arena_tiers", [4096, 16384, 65536])

    @property
    def alloc_pressure_thresholds(self) -> dict[str, float]:
        """Memory pressure level thresholds as fraction of utilization."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("pressure_thresholds", {
            "elevated": 0.60,
            "high": 0.80,
            "critical": 0.95,
        })

    @property
    def alloc_dashboard_width(self) -> int:
        """Dashboard width for the FizzAlloc dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzColumn — Columnar Storage Engine
    # ----------------------------------------------------------------

    @property
    def columnar_enabled(self) -> bool:
        """Whether the FizzColumn columnar storage engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("columnar_storage", {}).get("enabled", False)

    @property
    def columnar_row_group_size(self) -> int:
        """Maximum rows per row group before automatic sealing."""
        self._ensure_loaded()
        return self._raw_config.get("columnar_storage", {}).get("row_group_size", 1024)

    @property
    def columnar_encoding_sample_size(self) -> int:
        """Number of values to sample when auto-selecting column encoding."""
        self._ensure_loaded()
        return self._raw_config.get("columnar_storage", {}).get("encoding_sample_size", 1024)

    @property
    def columnar_dictionary_cardinality_limit(self) -> int:
        """Maximum distinct values before dictionary encoding is rejected."""
        self._ensure_loaded()
        return self._raw_config.get("columnar_storage", {}).get("dictionary_cardinality_limit", 256)

    @property
    def columnar_dashboard_width(self) -> int:
        """Dashboard width for the FizzColumn dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("columnar_storage", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzReduce — MapReduce Framework
    # ----------------------------------------------------------------

    @property
    def mapreduce_enabled(self) -> bool:
        """Whether the FizzReduce MapReduce framework is active."""
        self._ensure_loaded()
        return self._raw_config.get("mapreduce", {}).get("enabled", False)

    @property
    def mapreduce_num_mappers(self) -> int:
        """Number of parallel mapper tasks for FizzReduce jobs."""
        self._ensure_loaded()
        return self._raw_config.get("mapreduce", {}).get("num_mappers", 4)

    @property
    def mapreduce_num_reducers(self) -> int:
        """Number of reducer partitions for FizzReduce jobs."""
        self._ensure_loaded()
        return self._raw_config.get("mapreduce", {}).get("num_reducers", 2)

    @property
    def mapreduce_speculative_threshold(self) -> float:
        """Speculative execution threshold multiplier (task_time > threshold * avg)."""
        self._ensure_loaded()
        return self._raw_config.get("mapreduce", {}).get("speculative_threshold", 1.5)

    @property
    def mapreduce_dashboard_width(self) -> int:
        """Dashboard width for the FizzReduce dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("mapreduce", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzSchema — Consensus-Based Schema Evolution
    # ----------------------------------------------------------------

    @property
    def schema_evolution_enabled(self) -> bool:
        """Whether the FizzSchema schema evolution subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("schema_evolution", {}).get("enabled", False)

    @property
    def schema_evolution_compatibility_mode(self) -> str:
        """Active compatibility mode for schema evolution (BACKWARD/FORWARD/FULL/NONE)."""
        self._ensure_loaded()
        return self._raw_config.get("schema_evolution", {}).get("compatibility_mode", "BACKWARD")

    @property
    def schema_evolution_consensus_nodes(self) -> int:
        """Number of Paxos consensus nodes for schema approval."""
        self._ensure_loaded()
        return self._raw_config.get("schema_evolution", {}).get("consensus_nodes", 5)

    @property
    def schema_evolution_consensus_quorum(self) -> int:
        """Minimum approvals required for schema change consensus."""
        self._ensure_loaded()
        return self._raw_config.get("schema_evolution", {}).get("consensus_quorum", 3)

    @property
    def schema_evolution_dashboard_width(self) -> int:
        """Dashboard width for the FizzSchema dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("schema_evolution", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzCheck — Formal Model Checking
    # ----------------------------------------------------------------

    @property
    def model_check_enabled(self) -> bool:
        """Whether the FizzCheck model checking subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("model_check", {}).get("enabled", False)

    @property
    def model_check_max_states(self) -> int:
        """Maximum number of states to explore before raising StateSpaceError."""
        self._ensure_loaded()
        return self._raw_config.get("model_check", {}).get("max_states", 100000)

    @property
    def model_check_dashboard_width(self) -> int:
        """Dashboard width for the FizzCheck model checking dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("model_check", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzSLI — Service Level Indicator Framework
    # ----------------------------------------------------------------

    @property
    def sli_enabled(self) -> bool:
        """Whether the FizzSLI Service Level Indicator Framework is active."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("enabled", False)

    @property
    def sli_default_target(self) -> float:
        """Default SLO target for all SLIs (e.g. 0.999 = 99.9%)."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("default_target", 0.999)

    @property
    def sli_measurement_window_seconds(self) -> int:
        """Default measurement window in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("measurement_window_seconds", 3600)

    @property
    def sli_burn_rate_short_window(self) -> int:
        """Short burn-rate window in seconds (default 1h)."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("burn_rate_short_window", 3600)

    @property
    def sli_burn_rate_medium_window(self) -> int:
        """Medium burn-rate window in seconds (default 6h)."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("burn_rate_medium_window", 21600)

    @property
    def sli_burn_rate_long_window(self) -> int:
        """Long burn-rate window in seconds (default 3d)."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("burn_rate_long_window", 259200)

    @property
    def sli_short_threshold(self) -> float:
        """Multi-window alert short window burn-rate threshold."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("short_threshold", 14.4)

    @property
    def sli_long_threshold(self) -> float:
        """Multi-window alert long window burn-rate threshold."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("long_threshold", 6.0)

    @property
    def sli_dashboard_width(self) -> int:
        """Dashboard width for the FizzSLI dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("dashboard", {}).get("width", 60)

    # ------------------------------------------------------------------
    # Reverse Proxy & Load Balancer properties
    # ------------------------------------------------------------------

    @property
    def proxy_enabled(self) -> bool:
        """Whether the reverse proxy subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("enabled", False)

    @property
    def proxy_num_backends(self) -> int:
        """Number of backend engine instances in the proxy pool."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("num_backends", 5)

    @property
    def proxy_algorithm(self) -> str:
        """Load balancing algorithm name."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("algorithm", "round_robin")

    @property
    def proxy_enable_sticky_sessions(self) -> bool:
        """Whether sticky sessions are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("enable_sticky_sessions", True)

    @property
    def proxy_enable_health_check(self) -> bool:
        """Whether health checking is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("enable_health_check", True)

    @property
    def proxy_health_check_interval(self) -> int:
        """Health check interval in requests."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("health_check_interval", 10)

    @property
    def proxy_dashboard_width(self) -> int:
        """Dashboard width for the proxy dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzGate Digital Logic Circuit Simulator Properties
    # ----------------------------------------------------------------

    @property
    def circuit_enabled(self) -> bool:
        """Whether the FizzGate circuit simulator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("enabled", False)

    @property
    def circuit_enable_waveform(self) -> bool:
        """Whether to capture and display ASCII waveform timing diagrams."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("enable_waveform", False)

    @property
    def circuit_enable_dashboard(self) -> bool:
        """Whether to display the circuit analysis dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("enable_dashboard", False)

    @property
    def circuit_max_events(self) -> int:
        """Maximum simulation events before declaring oscillation."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("max_events", 10000)

    @property
    def circuit_timing_budget_ns(self) -> float:
        """Maximum acceptable circuit settle time in nanoseconds."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("timing_budget_ns", 500.0)

    @property
    def circuit_glitch_threshold_ns(self) -> float:
        """Minimum time between transitions to avoid glitch counting."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("glitch_threshold_ns", 5.0)

    @property
    def circuit_dashboard_width(self) -> int:
        """Width of the FizzGate ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("dashboard", {}).get("width", 60)

    # ----------------------------------------------------------------
    # FizzBloom Probabilistic Data Structures Properties
    # ----------------------------------------------------------------

    @property
    def probabilistic_enabled(self) -> bool:
        """Whether the FizzBloom probabilistic analytics subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("enabled", False)

    @property
    def probabilistic_bloom_expected_elements(self) -> int:
        """Expected number of distinct elements for the Bloom filter."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("bloom", {}).get("expected_elements", 1000)

    @property
    def probabilistic_bloom_false_positive_rate(self) -> float:
        """Target false positive rate for the Bloom filter."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("bloom", {}).get("false_positive_rate", 0.01)

    @property
    def probabilistic_cms_width(self) -> int:
        """Number of counters per row in the Count-Min Sketch."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("count_min_sketch", {}).get("width", 2048)

    @property
    def probabilistic_cms_depth(self) -> int:
        """Number of hash function rows in the Count-Min Sketch."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("count_min_sketch", {}).get("depth", 5)

    @property
    def probabilistic_hll_precision(self) -> int:
        """HyperLogLog precision parameter p (register count = 2^p)."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("hyperloglog", {}).get("precision", 14)

    @property
    def probabilistic_tdigest_compression(self) -> int:
        """T-Digest compression parameter controlling centroid count."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("tdigest", {}).get("compression", 100)

    @property
    def probabilistic_dashboard_width(self) -> int:
        """Width of the FizzBloom ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("dashboard", {}).get("width", 60)

    @property
    def datalog_enabled(self) -> bool:
        """Whether the FizzLog Datalog query engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("datalog", {}).get("enabled", False)

    @property
    def datalog_dashboard_width(self) -> int:
        """Width of the FizzLog ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("datalog", {}).get("dashboard", {}).get("width", 60)

    # ------------------------------------------------------------------
    # FizzIR SSA Intermediate Representation Properties
    # ------------------------------------------------------------------

    @property
    def ir_enabled(self) -> bool:
        """Whether the FizzIR SSA IR subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("ir", {}).get("enabled", False)

    @property
    def ir_optimize(self) -> bool:
        """Whether to run the 8-pass optimization pipeline on generated IR."""
        self._ensure_loaded()
        return self._raw_config.get("ir", {}).get("optimize", True)

    @property
    def ir_print(self) -> bool:
        """Whether to print the LLVM-style textual IR to stdout."""
        self._ensure_loaded()
        return self._raw_config.get("ir", {}).get("print", False)

    @property
    def ir_dashboard_width(self) -> int:
        """Width of the FizzIR ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("ir", {}).get("dashboard", {}).get("width", 60)

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
