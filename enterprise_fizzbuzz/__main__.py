"""
Enterprise FizzBuzz Platform - CLI Entry Point

Provides a comprehensive command-line interface for the Enterprise
FizzBuzz Platform with full argument parsing, configuration loading,
and graceful error handling.

Usage:
    python main.py
    python main.py --range 1 50
    python main.py --format json --verbose
    python main.py --strategy chain_of_responsibility --range 1 20
    python main.py --async --format xml
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from enterprise_fizzbuzz.infrastructure.auth import AuthorizationMiddleware, FizzBuzzTokenEngine, RoleRegistry
from enterprise_fizzbuzz.infrastructure.chaos import (
    ChaosMiddleware,
    ChaosMonkey,
    FaultSeverity,
    FaultType,
    GameDayRunner,
    PostMortemGenerator,
)
from enterprise_fizzbuzz.infrastructure.blockchain import BlockchainObserver, FizzBuzzBlockchain
from enterprise_fizzbuzz.infrastructure.cache import (
    CacheDashboard,
    CacheMiddleware,
    CacheStore,
    CacheWarmer,
    EvictionPolicyFactory,
)
from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
    CircuitBreakerDashboard,
    CircuitBreakerMiddleware,
    CircuitBreakerRegistry,
)
from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager, _SingletonMeta
from enterprise_fizzbuzz.infrastructure.feature_flags import (
    FlagEvaluationSummary,
    FlagMiddleware,
    apply_cli_overrides,
    create_flag_store_from_config,
    render_flag_list,
)
from enterprise_fizzbuzz.application.fizzbuzz_service import FizzBuzzServiceBuilder
from enterprise_fizzbuzz.infrastructure.formatters import FormatterFactory
from enterprise_fizzbuzz.infrastructure.i18n import LocaleManager
from enterprise_fizzbuzz.infrastructure.middleware import (
    LoggingMiddleware,
    TimingMiddleware,
    TranslationMiddleware,
    ValidationMiddleware,
)
from enterprise_fizzbuzz.domain.models import AuthContext, EvaluationStrategy, FizzBuzzRole, OutputFormat
from enterprise_fizzbuzz.infrastructure.observers import ConsoleObserver, EventBus, StatisticsObserver
from enterprise_fizzbuzz.infrastructure.adapters.strategy_adapters import StrategyAdapterFactory
from enterprise_fizzbuzz.infrastructure.rules_engine import RuleEngineFactory
from enterprise_fizzbuzz.infrastructure.event_sourcing import EventSourcingSystem
from enterprise_fizzbuzz.infrastructure.sla import (
    AlertSeverity,
    OnCallSchedule,
    SLADashboard,
    SLAMiddleware,
    SLAMonitor,
    SLODefinition,
    SLOType,
)
from enterprise_fizzbuzz.infrastructure.tracing import TraceExporter, TraceRenderer, TracingMiddleware, TracingService
from enterprise_fizzbuzz.infrastructure.migrations import (
    MigrationDashboard,
    MigrationRegistry,
    MigrationRunner,
    SchemaManager,
    SchemaVisualizer,
    SeedDataGenerator,
)
from enterprise_fizzbuzz.infrastructure.health import (
    CacheCoherenceHealthCheck,
    CircuitBreakerHealthCheck,
    ConfigHealthCheck,
    HealthCheckRegistry,
    HealthDashboard,
    LivenessProbe,
    MLEngineHealthCheck,
    ReadinessProbe,
    SelfHealingManager,
    SLABudgetHealthCheck,
    StartupProbe,
)
from enterprise_fizzbuzz.infrastructure.metrics import (
    CardinalityDetector,
    MetricsCollector,
    MetricsDashboard,
    MetricsMiddleware,
    MetricRegistry,
    PrometheusTextExporter,
    create_metrics_subsystem,
)
from enterprise_fizzbuzz.infrastructure.rate_limiter import (
    QuotaManager,
    RateLimitAlgorithm,
    RateLimitDashboard,
    RateLimitPolicy,
    RateLimiterMiddleware,
)
from enterprise_fizzbuzz.infrastructure.hot_reload import (
    ConfigDiffer,
    ConfigValidator,
    ConfigWatcher,
    HotReloadDashboard,
    ReloadOrchestrator,
    SingleNodeRaftConsensus,
    create_hot_reload_subsystem,
)
from enterprise_fizzbuzz.infrastructure.service_mesh import (
    MeshMiddleware,
    MeshTopologyVisualizer,
    create_service_mesh,
)
from enterprise_fizzbuzz.infrastructure.webhooks import (
    DeadLetterQueue,
    RetryPolicy,
    SimulatedHTTPClient,
    WebhookDashboard,
    WebhookManager,
    WebhookObserver,
    WebhookSignatureEngine,
)
from enterprise_fizzbuzz.infrastructure.compliance import (
    ComplianceDashboard,
    ComplianceFramework,
    ComplianceMiddleware,
    DataClassificationEngine,
    GDPRController,
    HIPAAGuard,
    SOXAuditor,
)

logger = logging.getLogger(__name__)


BANNER = r"""
  +===========================================================+
  |                                                           |
  |   FFFFFFFF II ZZZZZZZ ZZZZZZZ BBBBB   UU   UU ZZZZZZZ   |
  |   FF       II      ZZ      ZZ BB  BB  UU   UU      ZZ    |
  |   FFFFFF   II    ZZ      ZZ   BBBBB   UU   UU    ZZ      |
  |   FF       II   ZZ      ZZ   BB  BB  UU   UU   ZZ        |
  |   FF       II ZZZZZZZ ZZZZZZZ BBBBB   UUUUUU ZZZZZZZ    |
  |                                                           |
  |         E N T E R P R I S E   E D I T I O N              |
  |                    v1.0.0                                 |
  |                                                           |
  +===========================================================+
"""


def build_argument_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser with all supported options."""
    parser = argparse.ArgumentParser(
        prog="fizzbuzz",
        description="Enterprise FizzBuzz Platform - Production-grade FizzBuzz evaluation engine",
        epilog="For support, please open a ticket with your Enterprise FizzBuzz Platform administrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--range",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        help="The numeric range to evaluate (default: from config)",
    )

    parser.add_argument(
        "--format",
        choices=["plain", "json", "xml", "csv"],
        help="Output format (default: from config)",
    )

    parser.add_argument(
        "--strategy",
        choices=["standard", "chain_of_responsibility", "parallel_async", "machine_learning"],
        help="Rule evaluation strategy (default: from config)",
    )

    parser.add_argument(
        "--config",
        type=str,
        help="Path to YAML configuration file",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose console output with event logging",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging",
    )

    parser.add_argument(
        "--async",
        dest="use_async",
        action="store_true",
        help="Use asynchronous evaluation engine",
    )

    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Suppress the startup banner",
    )

    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Suppress the session summary",
    )

    parser.add_argument(
        "--metadata",
        action="store_true",
        help="Include metadata in output (JSON format only)",
    )

    parser.add_argument(
        "--blockchain",
        action="store_true",
        help="Enable blockchain-based immutable audit ledger for tamper-proof compliance",
    )

    parser.add_argument(
        "--mining-difficulty",
        type=int,
        default=2,
        metavar="N",
        help="Proof-of-work difficulty for blockchain mining (default: 2)",
    )

    parser.add_argument(
        "--locale",
        type=str,
        metavar="LOCALE",
        default=None,
        help="Locale for internationalized output (en, de, fr, ja, tlh, sjn, qya)",
    )

    parser.add_argument(
        "--list-locales",
        action="store_true",
        help="Display available locales and exit",
    )

    parser.add_argument(
        "--circuit-breaker",
        action="store_true",
        help="Enable circuit breaker with exponential backoff for fault-tolerant FizzBuzz evaluation",
    )

    parser.add_argument(
        "--circuit-status",
        action="store_true",
        help="Display the circuit breaker status dashboard after execution",
    )

    parser.add_argument(
        "--event-sourcing",
        action="store_true",
        help="Enable Event Sourcing with CQRS for append-only FizzBuzz audit logging",
    )

    parser.add_argument(
        "--replay",
        action="store_true",
        help="Replay all events from the event store to rebuild projections",
    )

    parser.add_argument(
        "--temporal-query",
        type=int,
        metavar="SEQ",
        default=None,
        help="Reconstruct FizzBuzz state at a specific event sequence number",
    )

    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable distributed tracing with ASCII waterfall output",
    )

    parser.add_argument(
        "--trace-json",
        action="store_true",
        help="Enable distributed tracing with JSON export output",
    )

    parser.add_argument(
        "--user",
        type=str,
        metavar="USERNAME",
        help="Authenticate as the specified user (trust-mode, no token required)",
    )

    parser.add_argument(
        "--role",
        type=str,
        choices=[r.name for r in FizzBuzzRole],
        help="Assign the specified RBAC role (requires --user or --token)",
    )

    parser.add_argument(
        "--token",
        type=str,
        metavar="TOKEN",
        help="Authenticate using an Enterprise FizzBuzz Platform token",
    )

    # Chaos Engineering flags
    parser.add_argument(
        "--chaos",
        action="store_true",
        help="Enable Chaos Engineering fault injection (the monkey awakens)",
    )

    parser.add_argument(
        "--chaos-level",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=None,
        metavar="N",
        help="Chaos severity level 1-5 (1=gentle breeze, 5=apocalypse)",
    )

    parser.add_argument(
        "--gameday",
        type=str,
        nargs="?",
        const="total_chaos",
        default=None,
        metavar="SCENARIO",
        help="Run a Game Day chaos scenario (modulo_meltdown, confidence_crisis, slow_burn, total_chaos)",
    )

    parser.add_argument(
        "--post-mortem",
        action="store_true",
        help="Generate a satirical post-mortem incident report after chaos execution",
    )

    # SLA Monitoring
    parser.add_argument(
        "--sla",
        action="store_true",
        help="Enable SLA Monitoring with PagerDuty-style alerting for FizzBuzz evaluation",
    )

    parser.add_argument(
        "--sla-dashboard",
        action="store_true",
        help="Display the SLA monitoring dashboard after execution",
    )

    parser.add_argument(
        "--on-call",
        action="store_true",
        help="Display the current on-call status and escalation chain",
    )

    # Feature Flags
    # Cache flags
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Enable the in-memory caching layer for FizzBuzz evaluation results",
    )

    parser.add_argument(
        "--cache-policy",
        type=str,
        choices=["lru", "lfu", "fifo", "dramatic_random"],
        default=None,
        metavar="POLICY",
        help="Cache eviction policy (default: from config)",
    )

    parser.add_argument(
        "--cache-size",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of cache entries (default: from config)",
    )

    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="Display the cache statistics dashboard after execution",
    )

    parser.add_argument(
        "--cache-warm",
        action="store_true",
        help="Pre-populate the cache before execution (defeats the purpose of caching)",
    )

    # Feature Flags
    parser.add_argument(
        "--feature-flags",
        action="store_true",
        help="Enable the Feature Flag / Progressive Rollout subsystem",
    )

    parser.add_argument(
        "--flag",
        action="append",
        metavar="NAME=VALUE",
        default=[],
        help="Override a feature flag (e.g. --flag wuzz_rule_experimental=true)",
    )

    parser.add_argument(
        "--list-flags",
        action="store_true",
        help="Display all registered feature flags and exit",
    )

    # Database Migration Framework
    # Repository Pattern + Unit of Work
    parser.add_argument(
        "--repository",
        type=str,
        choices=["in_memory", "sqlite", "filesystem"],
        default=None,
        metavar="BACKEND",
        help="Enable result persistence via Repository Pattern (in_memory | sqlite | filesystem)",
    )

    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to SQLite database file (default: from config, only with --repository sqlite)",
    )

    parser.add_argument(
        "--results-dir",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to results directory (default: from config, only with --repository filesystem)",
    )

    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Apply all pending database migrations to the in-memory schema (it won't persist)",
    )

    parser.add_argument(
        "--migrate-status",
        action="store_true",
        help="Display the migration status dashboard for the ephemeral database",
    )

    parser.add_argument(
        "--migrate-rollback",
        type=int,
        nargs="?",
        const=1,
        default=None,
        metavar="N",
        help="Roll back the last N migrations (default: 1)",
    )

    parser.add_argument(
        "--migrate-seed",
        action="store_true",
        help="Generate FizzBuzz seed data using the FizzBuzz engine (the ouroboros)",
    )

    # Health Check Probes
    parser.add_argument(
        "--health",
        action="store_true",
        help="Enable Kubernetes-style health check probes for the FizzBuzz platform",
    )

    parser.add_argument(
        "--liveness",
        action="store_true",
        help="Run a liveness probe (canary evaluation of 15 must equal FizzBuzz)",
    )

    parser.add_argument(
        "--readiness",
        action="store_true",
        help="Run a readiness probe (aggregate subsystem health assessment)",
    )

    parser.add_argument(
        "--startup-probe",
        action="store_true",
        help="Display the startup probe status (boot milestone tracking)",
    )

    parser.add_argument(
        "--health-dashboard",
        action="store_true",
        help="Display the comprehensive health check dashboard after execution",
    )

    parser.add_argument(
        "--self-heal",
        action="store_true",
        help="Enable self-healing: automatically attempt recovery of failing subsystems",
    )

    # Prometheus-Style Metrics
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Enable Prometheus-style metrics collection for FizzBuzz evaluation",
    )

    parser.add_argument(
        "--metrics-export",
        action="store_true",
        help="Export all metrics in Prometheus text exposition format after execution",
    )

    parser.add_argument(
        "--metrics-dashboard",
        action="store_true",
        help="Display the ASCII Grafana metrics dashboard after execution",
    )

    # Webhook Notification System
    parser.add_argument(
        "--webhooks",
        action="store_true",
        help="Enable the Webhook Notification System for event-driven FizzBuzz telemetry",
    )

    parser.add_argument(
        "--webhook-url",
        action="append",
        metavar="URL",
        default=[],
        help="Register a webhook endpoint URL (can be specified multiple times)",
    )

    parser.add_argument(
        "--webhook-events",
        type=str,
        metavar="EVENTS",
        default=None,
        help="Comma-separated list of event types to subscribe to (default: from config)",
    )

    parser.add_argument(
        "--webhook-secret",
        type=str,
        metavar="SECRET",
        default=None,
        help="HMAC-SHA256 secret for signing webhook payloads (default: from config)",
    )

    parser.add_argument(
        "--webhook-test",
        action="store_true",
        help="Send a test webhook to all registered endpoints and exit",
    )

    parser.add_argument(
        "--webhook-log",
        action="store_true",
        help="Display the webhook delivery log after execution",
    )

    parser.add_argument(
        "--webhook-dlq",
        action="store_true",
        help="Display the Dead Letter Queue contents after execution",
    )

    # Service Mesh Simulation
    parser.add_argument(
        "--service-mesh",
        action="store_true",
        help="Enable the Service Mesh Simulation: decompose FizzBuzz into 7 microservices",
    )

    parser.add_argument(
        "--mesh-topology",
        action="store_true",
        help="Display the ASCII service mesh topology diagram after execution",
    )

    parser.add_argument(
        "--mesh-latency",
        action="store_true",
        help="Enable simulated network latency injection between mesh services",
    )

    parser.add_argument(
        "--mesh-packet-loss",
        action="store_true",
        help="Enable simulated packet loss between mesh services",
    )

    parser.add_argument(
        "--canary",
        action="store_true",
        help="Enable canary deployment routing (v2 DivisibilityService uses advanced formula)",
    )

    # Configuration Hot-Reload with Single-Node Raft Consensus
    parser.add_argument(
        "--hot-reload",
        action="store_true",
        help="Enable configuration hot-reload with Single-Node Raft Consensus (polls config.yaml for changes)",
    )

    parser.add_argument(
        "--reload-status",
        action="store_true",
        help="Display the hot-reload Raft consensus dashboard after execution",
    )

    parser.add_argument(
        "--config-diff",
        type=str,
        metavar="PATH",
        default=None,
        help="Compute and display a diff between current config and the specified YAML file",
    )

    parser.add_argument(
        "--config-validate",
        type=str,
        metavar="PATH",
        default=None,
        help="Validate the specified YAML configuration file and exit",
    )

    # Rate Limiting & API Quota Management
    parser.add_argument(
        "--rate-limit",
        action="store_true",
        help="Enable rate limiting for FizzBuzz evaluations (because unrestricted modulo is dangerous)",
    )

    parser.add_argument(
        "--rate-limit-rpm",
        type=int,
        default=None,
        metavar="N",
        help="Maximum FizzBuzz evaluations per minute (default: from config)",
    )

    parser.add_argument(
        "--rate-limit-algo",
        type=str,
        choices=["token_bucket", "sliding_window", "fixed_window"],
        default=None,
        help="Rate limiting algorithm (default: from config)",
    )

    parser.add_argument(
        "--rate-limit-dashboard",
        action="store_true",
        help="Display the rate limiting ASCII dashboard after execution",
    )

    parser.add_argument(
        "--quota",
        action="store_true",
        help="Display quota status summary after execution",
    )

    # Compliance & Regulatory Framework
    parser.add_argument(
        "--compliance",
        action="store_true",
        help="Enable SOX/GDPR/HIPAA compliance framework for FizzBuzz evaluation",
    )

    parser.add_argument(
        "--gdpr-erase",
        type=int,
        metavar="NUMBER",
        default=None,
        help="Submit a GDPR right-to-erasure request for the specified number (triggers THE COMPLIANCE PARADOX)",
    )

    parser.add_argument(
        "--sox-audit",
        action="store_true",
        help="Display the SOX segregation of duties audit trail after execution",
    )

    parser.add_argument(
        "--hipaa-check",
        action="store_true",
        help="Display HIPAA PHI access log and encryption statistics after execution",
    )

    parser.add_argument(
        "--compliance-report",
        action="store_true",
        help="Generate a comprehensive compliance report after execution",
    )

    parser.add_argument(
        "--compliance-dashboard",
        action="store_true",
        help="Display the compliance & regulatory ASCII dashboard after execution",
    )

    return parser


def configure_logging(debug: bool = False) -> None:
    """Set up the logging subsystem."""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)-25s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the Enterprise FizzBuzz Platform."""
    # Ensure stdout can handle Unicode (box-drawing chars, etc.)
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        import io
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    # Logging
    configure_logging(debug=args.debug)

    # Banner
    if not args.no_banner:
        print(BANNER)

    # Reset singleton for fresh config
    _SingletonMeta.reset()

    # Configuration
    config = ConfigurationManager(config_path=args.config)
    config.load()

    # ----------------------------------------------------------------
    # Configuration Validation (--config-validate, early exit)
    # ----------------------------------------------------------------
    if args.config_validate:
        try:
            import yaml
        except ImportError:
            print("\n  PyYAML not installed. Cannot validate.\n")
            return 1

        validate_path = Path(args.config_validate)
        if not validate_path.exists():
            print(f"\n  Configuration file not found: {validate_path}\n")
            return 1

        with open(validate_path, "r") as f:
            validate_config = yaml.safe_load(f) or {}

        errors = ConfigValidator.validate(validate_config)
        if errors:
            print(
                "  +---------------------------------------------------------+\n"
                "  | CONFIGURATION VALIDATION: FAILED                        |\n"
                "  +---------------------------------------------------------+"
            )
            for err in errors:
                print(f"    [X] {err}")
            print()
            return 1
        else:
            print(
                "  +---------------------------------------------------------+\n"
                "  | CONFIGURATION VALIDATION: PASSED                        |\n"
                "  | The configuration file is valid. All values are within  |\n"
                "  | acceptable enterprise parameters. Congratulations on   |\n"
                "  | authoring a syntactically correct YAML file.           |\n"
                "  +---------------------------------------------------------+"
            )
            return 0

    # ----------------------------------------------------------------
    # Configuration Diff (--config-diff, early exit)
    # ----------------------------------------------------------------
    if args.config_diff:
        try:
            import yaml
        except ImportError:
            print("\n  PyYAML not installed. Cannot compute diff.\n")
            return 1

        diff_path = Path(args.config_diff)
        if not diff_path.exists():
            print(f"\n  Configuration file not found: {diff_path}\n")
            return 1

        with open(diff_path, "r") as f:
            diff_config = yaml.safe_load(f) or {}

        current_config = config._get_raw_config_copy()
        changeset = ConfigDiffer.diff(current_config, diff_config)

        if changeset.is_empty:
            print(
                "  +---------------------------------------------------------+\n"
                "  | CONFIGURATION DIFF: No changes detected.               |\n"
                "  | The files are identical. This diff was anticlimactic.   |\n"
                "  +---------------------------------------------------------+"
            )
        else:
            print(HotReloadDashboard.render_diff(changeset, width=58))
        return 0

    # ----------------------------------------------------------------
    # Database Migration Framework (opt-in via --migrate flags)
    # ----------------------------------------------------------------
    if args.migrate or args.migrate_status or args.migrate_rollback is not None or args.migrate_seed:
        MigrationRegistry.reset()
        # Re-import to re-register built-in migrations after reset
        from enterprise_fizzbuzz.infrastructure.migrations import _register_builtin_migrations
        _register_builtin_migrations()

        migration_schema = SchemaManager(log_fake_sql=config.migrations_log_fake_sql)
        migration_runner = MigrationRunner(migration_schema)

        if args.migrate:
            print(
                "  +---------------------------------------------------------+\n"
                "  | DATABASE MIGRATION FRAMEWORK: Applying Migrations       |\n"
                "  | All schema changes apply to in-memory dicts that will   |\n"
                "  | be destroyed when this process exits. You're welcome.   |\n"
                "  +---------------------------------------------------------+"
            )
            print()

            applied = migration_runner.apply_all()
            for record in applied:
                print(f"  [+] Applied: {record.migration_id} ({record.duration_ms:.2f}ms)")

            if not applied:
                print("  No pending migrations. The ephemeral schema is up to date.")

            print()

            if config.migrations_visualize_schema:
                print(SchemaVisualizer.render(migration_schema))

        if args.migrate_seed:
            if not migration_schema.table_exists("fizzbuzz_results"):
                # Auto-apply migrations first
                migration_runner.apply_all()

            seeder = SeedDataGenerator(migration_schema)
            seed_start = config.migrations_seed_range_start
            seed_end = config.migrations_seed_range_end
            count = seeder.generate(seed_start, seed_end)
            print(
                f"  Seeded {count} rows using FizzBuzz to populate the FizzBuzz database.\n"
                f"  The ouroboros is complete. The snake has eaten its own tail.\n"
            )

        if args.migrate_rollback is not None:
            rolled_back = migration_runner.rollback(args.migrate_rollback)
            for record in rolled_back:
                print(f"  [-] Rolled back: {record.migration_id}")
            if not rolled_back:
                print("  No migrations to roll back.")
            print()

        if args.migrate_status:
            print(MigrationDashboard.render(migration_runner))

        # Show fake SQL log if enabled
        if config.migrations_log_fake_sql and migration_schema.sql_log:
            print("  +-- FAKE SQL LOG (for enterprise cosplay) --+")
            for sql in migration_schema.sql_log:
                print(f"  |  {sql}")
            print("  +--------------------------------------------+")
            print()

        return 0

    # Determine parameters (CLI overrides config)
    start = args.range[0] if args.range else config.range_start
    end = args.range[1] if args.range else config.range_end

    # Output format
    format_map = {
        "plain": OutputFormat.PLAIN,
        "json": OutputFormat.JSON,
        "xml": OutputFormat.XML,
        "csv": OutputFormat.CSV,
    }
    output_format = format_map.get(args.format) if args.format else config.output_format

    # Strategy
    strategy_map = {
        "standard": EvaluationStrategy.STANDARD,
        "chain_of_responsibility": EvaluationStrategy.CHAIN_OF_RESPONSIBILITY,
        "parallel_async": EvaluationStrategy.PARALLEL_ASYNC,
        "machine_learning": EvaluationStrategy.MACHINE_LEARNING,
    }
    strategy = (
        strategy_map.get(args.strategy) if args.strategy else config.evaluation_strategy
    )

    # Build the service
    event_bus = EventBus()
    stats_observer = StatisticsObserver()
    event_bus.subscribe(stats_observer)

    if args.verbose:
        console_observer = ConsoleObserver(verbose=True)
        event_bus.subscribe(console_observer)

    blockchain_observer = None
    if args.blockchain:
        blockchain = FizzBuzzBlockchain(difficulty=args.mining_difficulty)
        blockchain_observer = BlockchainObserver(blockchain=blockchain)
        event_bus.subscribe(blockchain_observer)

    # Circuit breaker
    cb_middleware = None
    if args.circuit_breaker:
        cb_middleware = CircuitBreakerMiddleware(
            event_bus=event_bus,
            failure_threshold=config.circuit_breaker_failure_threshold,
            success_threshold=config.circuit_breaker_success_threshold,
            timeout_ms=config.circuit_breaker_timeout_ms,
            sliding_window_size=config.circuit_breaker_sliding_window_size,
            half_open_max_calls=config.circuit_breaker_half_open_max_calls,
            backoff_base_ms=config.circuit_breaker_backoff_base_ms,
            backoff_max_ms=config.circuit_breaker_backoff_max_ms,
            backoff_multiplier=config.circuit_breaker_backoff_multiplier,
            ml_confidence_threshold=config.circuit_breaker_ml_confidence_threshold,
            call_timeout_ms=config.circuit_breaker_call_timeout_ms,
        )
        # Register in global registry for dashboard access
        registry = CircuitBreakerRegistry.get_instance()
        registry.get_or_create(
            cb_middleware.circuit_breaker.name,
        )

    # Internationalization (i18n) setup
    locale_mgr = None
    locale = args.locale or config.i18n_locale

    if config.i18n_enabled:
        LocaleManager.reset()
        locale_mgr = LocaleManager()
        locale_dir = str(Path(config.i18n_locale_directory))
        locale_mgr.load_all(locale_dir)
        locale_mgr.set_strict_mode(config.i18n_strict_mode)

        # Set the active locale (CLI overrides config)
        if locale in locale_mgr.get_available_locales():
            locale_mgr.set_locale(locale)
        elif locale != "en":
            # Locale not available, warn and fall back to English
            print(f"  Warning: locale '{locale}' not available, using 'en'")
            locale = "en"

    # Handle --list-locales
    if args.list_locales:
        if locale_mgr is not None:
            info = locale_mgr.get_locale_info()
            print("\n  Available Locales:")
            print("  " + "-" * 60)
            print(f"  {'Code':<8} {'Name':<20} {'Fallback':<12} {'Keys':<8} {'Plural Rule'}")
            print("  " + "-" * 60)
            for loc in info:
                print(
                    f"  {loc['code']:<8} {loc['name']:<20} {loc['fallback']:<12} "
                    f"{loc['keys']:<8} {loc['plural_rule']}"
                )
            print("  " + "-" * 60)
            print()
        else:
            print("\n  i18n is disabled. Enable it in config.yaml.\n")
        return 0

    # Distributed tracing setup
    tracing_service = TracingService()
    tracing_service.reset()
    tracing_enabled = args.trace or args.trace_json
    tracing_mw = None
    if tracing_enabled:
        tracing_service.enable()
        tracing_mw = TracingMiddleware()

    # ----------------------------------------------------------------
    # Role-Based Access Control (RBAC) setup
    # ----------------------------------------------------------------
    auth_context = None
    rbac_active = False

    if args.token:
        # Token-based authentication — the secure way
        try:
            auth_context = FizzBuzzTokenEngine.validate_token(
                args.token, config.rbac_token_secret
            )
            rbac_active = True
        except Exception as e:
            print(f"  [AUTHENTICATION FAILED] {e}")
            return 1

    elif args.user:
        # Trust-mode authentication — the "just trust me" protocol
        role = FizzBuzzRole[args.role] if args.role else FizzBuzzRole[config.rbac_default_role]
        effective_permissions = RoleRegistry.get_effective_permissions(role)
        auth_context = AuthContext(
            user=args.user,
            role=role,
            token_id=None,
            effective_permissions=tuple(effective_permissions),
            trust_mode=True,
        )
        rbac_active = True
        print(
            "  +---------------------------------------------------------+\n"
            "  | WARNING: Trust-mode authentication enabled.             |\n"
            "  | The user's identity has not been cryptographically      |\n"
            "  | verified. This is the security equivalent of writing    |\n"
            "  | your password on a Post-It note and sticking it to     |\n"
            "  | your monitor. Proceed with existential dread.          |\n"
            "  +---------------------------------------------------------+"
        )

    elif config.rbac_enabled:
        # No auth flags but RBAC is enabled — default to ANONYMOUS
        role = FizzBuzzRole[config.rbac_default_role]
        effective_permissions = RoleRegistry.get_effective_permissions(role)
        auth_context = AuthContext(
            user="anonymous",
            role=role,
            token_id=None,
            effective_permissions=tuple(effective_permissions),
            trust_mode=False,
        )
        rbac_active = True

    # Event Sourcing / CQRS setup
    es_system = None
    es_middleware = None
    if args.event_sourcing:
        es_system = EventSourcingSystem(
            snapshot_interval=config.event_sourcing_snapshot_interval,
        )
        es_middleware = es_system.create_middleware()

    # Feature Flags setup
    flag_store = None
    flag_middleware = None
    if args.feature_flags:
        from enterprise_fizzbuzz.domain.models import RuleDefinition
        from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule

        flag_store = create_flag_store_from_config(config)

        # Apply CLI overrides
        if args.flag:
            apply_cli_overrides(flag_store, args.flag)

        # Handle --list-flags
        if args.list_flags:
            print(render_flag_list(flag_store))
            return 0

        flag_middleware = FlagMiddleware(
            flag_store=flag_store,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | FEATURE FLAGS: Progressive Rollout ENABLED              |\n"
            "  | Flags are now controlling which rules are active.       |\n"
            "  | The FizzBuzz rules you know and love are now subject    |\n"
            "  | to the whims of a configuration-driven toggle system.   |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.list_flags:
        print("\n  Feature flags not enabled. Use --feature-flags to enable.\n")
        return 0

    # SLA Monitoring setup
    sla_monitor = None
    sla_middleware = None
    if args.sla:
        slo_definitions = [
            SLODefinition(
                name="latency",
                slo_type=SLOType.LATENCY,
                target=config.sla_latency_target,
                threshold_ms=config.sla_latency_threshold_ms,
            ),
            SLODefinition(
                name="accuracy",
                slo_type=SLOType.ACCURACY,
                target=config.sla_accuracy_target,
            ),
            SLODefinition(
                name="availability",
                slo_type=SLOType.AVAILABILITY,
                target=config.sla_availability_target,
            ),
        ]

        on_call_schedule = OnCallSchedule(
            team_name=config.sla_on_call_team_name,
            rotation_interval_hours=config.sla_on_call_rotation_interval_hours,
            engineers=config.sla_on_call_engineers,
        )

        sla_monitor = SLAMonitor(
            slo_definitions=slo_definitions,
            event_bus=event_bus,
            on_call_schedule=on_call_schedule,
            burn_rate_threshold=config.sla_error_budget_burn_rate_threshold,
        )

        sla_middleware = SLAMiddleware(
            sla_monitor=sla_monitor,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | SLA MONITORING: PagerDuty-Style Alerting ENABLED        |\n"
            "  | Latency, accuracy, and availability SLOs are now being  |\n"
            "  | tracked with error budgets and escalation policies.     |\n"
            "  | On-call: Bob McFizzington (he's always on call).        |\n"
            "  +---------------------------------------------------------+"
        )

    elif args.sla_dashboard:
        print("\n  SLA monitoring not enabled. Use --sla to enable.\n")
        return 0
    elif args.on_call:
        # Allow --on-call without --sla for quick status check
        on_call_schedule = OnCallSchedule(
            team_name=config.sla_on_call_team_name,
            rotation_interval_hours=config.sla_on_call_rotation_interval_hours,
            engineers=config.sla_on_call_engineers,
        )
        sla_monitor = SLAMonitor(
            slo_definitions=[],
            on_call_schedule=on_call_schedule,
        )
        print(SLADashboard.render_on_call(sla_monitor))
        return 0

    # Cache setup
    cache_middleware = None
    cache_store = None
    cache_warmer = None
    if args.cache:
        cache_policy_name = args.cache_policy or config.cache_eviction_policy
        cache_max_size = args.cache_size or config.cache_max_size
        eviction_policy = EvictionPolicyFactory.create(cache_policy_name)

        cache_store = CacheStore(
            max_size=cache_max_size,
            ttl_seconds=config.cache_ttl_seconds,
            eviction_policy=eviction_policy,
            enable_coherence=config.cache_enable_coherence_protocol,
            enable_eulogies=config.cache_enable_eulogies,
            event_bus=event_bus,
        )

        cache_middleware = CacheMiddleware(
            cache_store=cache_store,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | CACHING: In-Memory Cache Layer ENABLED                  |\n"
            f"  | Policy: {eviction_policy.get_name():<49}|\n"
            f"  | Max Size: {cache_max_size:<48}|\n"
            "  | MESI coherence protocol: ACTIVE (pointlessly)           |\n"
            "  | Every eviction will be mourned with a eulogy.           |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.cache_stats:
        print("\n  Cache not enabled. Use --cache to enable.\n")
        return 0

    # Prometheus-Style Metrics setup
    metrics_registry = None
    metrics_collector = None
    metrics_middleware = None
    metrics_cardinality = None
    if args.metrics or args.metrics_export or args.metrics_dashboard:
        MetricRegistry.reset()
        metrics_registry, metrics_collector, metrics_middleware, metrics_cardinality = (
            create_metrics_subsystem(
                event_bus=event_bus,
                bob_initial_stress=config.metrics_bob_stress_level,
                cardinality_threshold=config.metrics_cardinality_threshold,
                default_buckets=config.metrics_default_buckets,
            )
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | PROMETHEUS METRICS: Collection ENABLED                   |\n"
            "  | Counters, gauges, histograms, and summaries are now      |\n"
            "  | tracking every aspect of your FizzBuzz evaluations.      |\n"
            "  | Bob McFizzington's stress level: monitored.              |\n"
            "  | is_tuesday label: mandatory.                             |\n"
            "  +---------------------------------------------------------+"
        )

    # Webhook Notification System setup
    webhook_manager = None
    webhook_observer = None
    if args.webhooks or args.webhook_url or args.webhook_test:
        webhook_secret = args.webhook_secret or config.webhooks_secret
        sig_engine = WebhookSignatureEngine(webhook_secret)

        success_rate = config.webhooks_simulated_success_rate
        http_client = SimulatedHTTPClient(success_rate_percent=success_rate)

        retry_policy = RetryPolicy(
            max_retries=config.webhooks_retry_max_retries,
            backoff_base_ms=config.webhooks_retry_backoff_base_ms,
            backoff_multiplier=config.webhooks_retry_backoff_multiplier,
            backoff_max_ms=config.webhooks_retry_backoff_max_ms,
        )

        dlq = DeadLetterQueue(max_size=config.webhooks_dlq_max_size)

        webhook_manager = WebhookManager(
            signature_engine=sig_engine,
            http_client=http_client,
            retry_policy=retry_policy,
            dead_letter_queue=dlq,
            event_bus=event_bus,
        )

        # Register endpoints from CLI
        for url in args.webhook_url:
            webhook_manager.register_endpoint(url)

        # Register endpoints from config
        for url in config.webhooks_endpoints:
            webhook_manager.register_endpoint(url)

        # Determine subscribed events
        if args.webhook_events:
            subscribed = set(args.webhook_events.split(","))
        else:
            subscribed = set(config.webhooks_subscribed_events)

        # Create and subscribe the observer
        webhook_observer = WebhookObserver(
            webhook_manager=webhook_manager,
            subscribed_events=subscribed,
        )
        event_bus.subscribe(webhook_observer)

        print(
            "  +---------------------------------------------------------+\n"
            "  | WEBHOOKS: Notification System ENABLED                    |\n"
            "  | All matching events will be dispatched to registered     |\n"
            "  | endpoints via simulated HTTP POST with HMAC-SHA256       |\n"
            "  | signatures. No actual HTTP requests will be made.        |\n"
            "  | X-FizzBuzz-Seriousness-Level: MAXIMUM                   |\n"
            "  +---------------------------------------------------------+"
        )

        # Handle --webhook-test
        if args.webhook_test:
            from enterprise_fizzbuzz.domain.models import Event, EventType
            test_event = Event(
                event_type=EventType.SESSION_STARTED,
                payload={"test": True, "message": "Webhook connectivity test"},
                source="WebhookTestRunner",
            )
            print("\n  Sending test webhook to all registered endpoints...\n")
            results = webhook_manager.dispatch(test_event)
            success_count = sum(1 for r in results if r.success)
            print(
                f"\n  Test complete: {success_count}/{len(results)} endpoints "
                f"accepted the test webhook.\n"
            )
            if args.webhook_dlq:
                print(WebhookDashboard.render_dlq(webhook_manager))
            return 0

    elif args.webhook_test:
        print("\n  Webhooks not enabled. Use --webhooks to enable.\n")
        return 0
    elif args.webhook_log:
        print("\n  Webhooks not enabled. Use --webhooks to enable.\n")
        return 0
    elif args.webhook_dlq:
        print("\n  Webhooks not enabled. Use --webhooks to enable.\n")
        return 0

    # Service Mesh Simulation setup
    mesh_middleware = None
    mesh_control_plane = None
    if args.service_mesh:
        mesh_control_plane, mesh_orchestrator = create_service_mesh(
            mtls_enabled=config.service_mesh_mtls_enabled,
            log_handshakes=config.service_mesh_mtls_log_handshakes,
            latency_enabled=args.mesh_latency or config.service_mesh_latency_enabled,
            latency_min_ms=config.service_mesh_latency_min_ms,
            latency_max_ms=config.service_mesh_latency_max_ms,
            packet_loss_enabled=args.mesh_packet_loss or config.service_mesh_packet_loss_enabled,
            packet_loss_rate=config.service_mesh_packet_loss_rate,
            canary_enabled=args.canary or config.service_mesh_canary_enabled,
            canary_percentage=config.service_mesh_canary_traffic_percentage / 100.0,
            circuit_breaker_enabled=config.service_mesh_circuit_breaker_enabled,
            circuit_breaker_threshold=config.service_mesh_circuit_breaker_failure_threshold,
            event_bus=event_bus,
        )

        # Build divisor info from config rules
        divisors = [r.divisor for r in config.rules]
        divisor_labels = {str(r.divisor): r.label for r in config.rules}

        mesh_middleware = MeshMiddleware(
            control_plane=mesh_control_plane,
            divisors=divisors,
            divisor_labels=divisor_labels,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | SERVICE MESH: 7 Microservices ENABLED                    |\n"
            "  | FizzBuzz has been decomposed into:                       |\n"
            "  |   1. NumberIngestionService                              |\n"
            "  |   2. DivisibilityService                                |\n"
            "  |   3. ClassificationService                              |\n"
            "  |   4. FormattingService                                  |\n"
            "  |   5. AuditService                                       |\n"
            "  |   6. CacheService                                       |\n"
            "  |   7. OrchestratorService                                |\n"
            "  | mTLS (base64): ARMED. Military-grade encryption active. |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.mesh_topology:
        print("\n  Service mesh not enabled. Use --service-mesh to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Configuration Hot-Reload with Single-Node Raft Consensus
    # ----------------------------------------------------------------
    hot_reload_raft = None
    hot_reload_orchestrator = None
    hot_reload_watcher = None
    hot_reload_dep_graph = None
    hot_reload_rollback_mgr = None

    if args.hot_reload:
        config_path = Path(
            args.config
            or os.environ.get("EFP_CONFIG_PATH", str(Path(__file__).parent.parent / "config.yaml"))
        )

        hot_reload_raft, hot_reload_orchestrator, hot_reload_watcher, hot_reload_dep_graph, hot_reload_rollback_mgr = (
            create_hot_reload_subsystem(
                config_manager=config,
                config_path=config_path,
                poll_interval_seconds=config.hot_reload_poll_interval_seconds,
                heartbeat_interval_ms=config.hot_reload_raft_heartbeat_interval_ms,
                election_timeout_ms=config.hot_reload_raft_election_timeout_ms,
                max_rollback_history=config.hot_reload_max_rollback_history,
                validate_before_apply=config.hot_reload_validate_before_apply,
                log_diffs=config.hot_reload_log_diffs,
                event_bus=event_bus,
            )
        )

        # Start the file watcher
        hot_reload_watcher.start()

        print(
            "  +---------------------------------------------------------+\n"
            "  | HOT-RELOAD: Single-Node Raft Consensus ENABLED          |\n"
            "  | Configuration changes will be detected and applied      |\n"
            "  | at runtime through a full Raft consensus protocol       |\n"
            "  | with 1 node. Elections: always unanimous. Heartbeats:   |\n"
            "  | sent to 0 followers. Consensus latency: 0.000ms.       |\n"
            "  | Democracy has never been more efficient.                |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.reload_status:
        print("\n  Hot-reload not enabled. Use --hot-reload to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Rate Limiting & API Quota Management setup
    # ----------------------------------------------------------------
    rate_limit_middleware = None
    rate_limit_quota_manager = None
    if args.rate_limit:
        algo_map = {
            "token_bucket": RateLimitAlgorithm.TOKEN_BUCKET,
            "sliding_window": RateLimitAlgorithm.SLIDING_WINDOW,
            "fixed_window": RateLimitAlgorithm.FIXED_WINDOW,
        }
        algo_name = args.rate_limit_algo or config.rate_limiting_algorithm
        algo = algo_map.get(algo_name, RateLimitAlgorithm.TOKEN_BUCKET)
        rpm = args.rate_limit_rpm or config.rate_limiting_rpm

        rl_policy = RateLimitPolicy(
            algorithm=algo,
            requests_per_minute=float(rpm),
            burst_credits_enabled=config.rate_limiting_burst_credits_enabled,
            burst_credits_max=float(config.rate_limiting_burst_credits_max),
            burst_credits_earn_rate=config.rate_limiting_burst_credits_earn_rate,
            reservations_enabled=config.rate_limiting_reservations_enabled,
            reservations_max=config.rate_limiting_reservations_max,
            reservations_ttl_seconds=config.rate_limiting_reservations_ttl_seconds,
        )

        rate_limit_quota_manager = QuotaManager(
            policy=rl_policy,
            event_bus=event_bus,
        )

        rate_limit_middleware = RateLimiterMiddleware(
            quota_manager=rate_limit_quota_manager,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | RATE LIMITING: API Quota Management ENABLED              |\n"
            f"  | Algorithm: {algo.name:<46}|\n"
            f"  | RPM Limit: {rpm:<47}|\n"
            "  | Burst credits: ARMED. Unused quota carries over.        |\n"
            "  | Motivational quotes: LOADED and READY.                  |\n"
            "  | Because unrestricted FizzBuzz is a security incident.   |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.rate_limit_dashboard:
        print("\n  Rate limiting not enabled. Use --rate-limit to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Compliance & Regulatory Framework setup
    # ----------------------------------------------------------------
    compliance_framework = None
    compliance_middleware = None
    if args.compliance or args.gdpr_erase is not None or args.compliance_dashboard or args.compliance_report:
        sox_auditor = SOXAuditor(
            personnel_roster=config.compliance_sox_personnel_roster,
            strict_mode=config.compliance_sox_segregation_strict,
            event_bus=event_bus,
        ) if config.compliance_sox_enabled else None

        gdpr_controller = GDPRController(
            auto_consent=config.compliance_gdpr_auto_consent,
            erasure_enabled=config.compliance_gdpr_erasure_enabled,
            event_bus=event_bus,
        ) if config.compliance_gdpr_enabled else None

        hipaa_guard = HIPAAGuard(
            minimum_necessary_level=config.compliance_hipaa_minimum_necessary_level,
            encryption_algorithm=config.compliance_hipaa_encryption_algorithm,
            event_bus=event_bus,
        ) if config.compliance_hipaa_enabled else None

        compliance_framework = ComplianceFramework(
            sox_auditor=sox_auditor,
            gdpr_controller=gdpr_controller,
            hipaa_guard=hipaa_guard,
            event_bus=event_bus,
            bob_stress_level=config.compliance_officer_stress_level,
        )

        compliance_middleware = ComplianceMiddleware(
            compliance_framework=compliance_framework,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | COMPLIANCE: SOX/GDPR/HIPAA Framework ENABLED            |\n"
            "  | Segregation of duties: ENFORCED (no dual FizzBuzz roles) |\n"
            "  | GDPR consent: AUTO-GRANTED (for convenience)            |\n"
            "  | HIPAA encryption: MILITARY-GRADE BASE64                 |\n"
            "  | Compliance Officer: Bob McFizzington (UNAVAILABLE)      |\n"
            f"  | Bob's stress level: {config.compliance_officer_stress_level:.1f}%"
            + " " * max(0, 37 - len(f"{config.compliance_officer_stress_level:.1f}%"))
            + "|\n"
            "  +---------------------------------------------------------+"
        )

        # Handle --gdpr-erase (early exit)
        if args.gdpr_erase is not None:
            if gdpr_controller is not None:
                certificate = compliance_framework.process_erasure_request(args.gdpr_erase)
                print(ComplianceDashboard.render_erasure_certificate(certificate))
                print(
                    f"  Bob McFizzington's stress level is now "
                    f"{compliance_framework.bob_stress_level:.1f}%.\n"
                    f"  Please send thoughts and prayers to "
                    f"{config.compliance_officer_name}.\n"
                )
            else:
                print("\n  GDPR is not enabled in the compliance configuration.\n")
            return 0

    elif args.gdpr_erase is not None:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")
        return 0
    elif args.sox_audit:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")
        return 0
    elif args.hipaa_check:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")
        return 0
    elif args.compliance_dashboard:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")
        return 0
    elif args.compliance_report:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")
        return 0

    # Chaos Engineering setup
    chaos_monkey = None
    chaos_middleware = None
    if args.chaos or args.gameday:
        chaos_level = args.chaos_level or config.chaos_level
        chaos_severity = FaultSeverity(chaos_level)

        # Parse armed fault types from config
        armed_types = []
        for ft_name in config.chaos_fault_types:
            try:
                armed_types.append(FaultType[ft_name])
            except KeyError:
                pass
        if not armed_types:
            armed_types = list(FaultType)

        ChaosMonkey.reset()
        chaos_monkey = ChaosMonkey.initialize(
            severity=chaos_severity,
            seed=config.chaos_seed,
            armed_fault_types=armed_types,
            latency_min_ms=config.chaos_latency_min_ms,
            latency_max_ms=config.chaos_latency_max_ms,
            event_bus=event_bus,
        )
        chaos_middleware = ChaosMiddleware(chaos_monkey)

        print(
            "  +---------------------------------------------------------+\n"
            "  | WARNING: Chaos Engineering ENABLED                      |\n"
            f"  | Severity: Level {chaos_level} ({chaos_severity.label})"
            + " " * (39 - len(f"Level {chaos_level} ({chaos_severity.label})"))
            + "|\n"
            f"  | Injection probability: {chaos_severity.probability:.0%}"
            + " " * (35 - len(f"{chaos_severity.probability:.0%}"))
            + "|\n"
            "  | The Chaos Monkey is awake and hungry for modulo ops.    |\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # Repository Pattern + Unit of Work setup (opt-in via --repository)
    # ----------------------------------------------------------------
    uow = None
    repo_backend = args.repository or config.repository_backend
    if repo_backend and repo_backend != "none":
        from enterprise_fizzbuzz.infrastructure.persistence import (
            InMemoryUnitOfWork,
            SqliteUnitOfWork,
            FileSystemUnitOfWork,
        )

        if repo_backend == "in_memory":
            uow = InMemoryUnitOfWork()
        elif repo_backend == "sqlite":
            db_path = args.db_path or config.repository_db_path
            uow = SqliteUnitOfWork(db_path=db_path)
        elif repo_backend == "filesystem":
            fs_path = args.results_dir or config.repository_fs_path
            uow = FileSystemUnitOfWork(base_dir=fs_path)

        if uow is not None:
            print(
                "  +---------------------------------------------------------+\n"
                f"  | REPOSITORY: {repo_backend.upper():<45}|\n"
                "  | FizzBuzz results will now be persisted via the          |\n"
                "  | Repository Pattern + Unit of Work, because storing     |\n"
                "  | modulo results in a variable was insufficiently durable.|\n"
                "  +---------------------------------------------------------+"
            )

    # Create rule engine via factory (the ACL wraps this in an adapter below)
    rule_engine = RuleEngineFactory.create(strategy)

    builder = (
        FizzBuzzServiceBuilder()
        .with_config(config)
        .with_event_bus(event_bus)
        .with_rule_engine(rule_engine)
        .with_output_format(output_format)
        .with_locale_manager(locale_mgr)
        .with_default_middleware()
    )

    # Add Unit of Work to builder if configured
    if uow is not None:
        builder.with_unit_of_work(uow)

    # Add auth context to builder
    if auth_context is not None:
        builder.with_auth_context(auth_context)

    # Add tracing middleware (priority -2, runs first)
    if tracing_mw is not None:
        builder.with_middleware(tracing_mw)

    # Add authorization middleware if RBAC is active
    if rbac_active and auth_context is not None:
        auth_middleware = AuthorizationMiddleware(
            auth_context=auth_context,
            contact_email=config.rbac_access_denied_contact_email,
            next_training_session=config.rbac_next_training_session,
            event_bus=event_bus,
        )
        builder.with_middleware(auth_middleware)

    # Add translation middleware if i18n is active
    if locale_mgr is not None:
        builder.with_middleware(TranslationMiddleware(locale_manager=locale_mgr))

    if es_middleware is not None:
        builder.with_middleware(es_middleware)

    if cb_middleware is not None:
        builder.with_middleware(cb_middleware)

    if cache_middleware is not None:
        builder.with_middleware(cache_middleware)

    if chaos_middleware is not None:
        builder.with_middleware(chaos_middleware)

    if sla_middleware is not None:
        builder.with_middleware(sla_middleware)

    if metrics_middleware is not None:
        builder.with_middleware(metrics_middleware)

    if mesh_middleware is not None:
        builder.with_middleware(mesh_middleware)

    if rate_limit_middleware is not None:
        builder.with_middleware(rate_limit_middleware)

    if compliance_middleware is not None:
        builder.with_middleware(compliance_middleware)

    # Add feature flag middleware (priority -3, runs before tracing)
    if flag_middleware is not None:
        builder.with_middleware(flag_middleware)

    service = builder.build()

    # ----------------------------------------------------------------
    # Dependency Injection Container Demonstration
    # ----------------------------------------------------------------
    # The DI container exists alongside the builder. It does NOT replace
    # the existing wiring — it merely proves that we COULD have used an
    # IoC container instead of a builder, had we wanted to add yet another
    # layer of abstraction to our already stratospheric abstraction stack.
    # ----------------------------------------------------------------
    from enterprise_fizzbuzz.infrastructure.container import Container, Lifetime
    from enterprise_fizzbuzz.domain.interfaces import IEventBus

    di_container = Container()
    di_container.register(
        IEventBus,
        lifetime=Lifetime.SINGLETON,
        factory=lambda: event_bus,
    ).register(
        ConfigurationManager,
        lifetime=Lifetime.ETERNAL,
        factory=lambda: config,
    )

    logger.debug(
        "DI Container initialized with %d bindings. "
        "These bindings coexist peacefully with the builder-based wiring, "
        "because two parallel object construction strategies are better than one.",
        di_container.get_registration_count(),
    )

    # Wire up the Anti-Corruption Layer strategy adapter.
    # This is done after build() because the adapter needs the resolved
    # rules list, which is only available on the built service.
    # The ACL wraps the rule engine in a strategy adapter that translates
    # raw FizzBuzzResults into clean EvaluationResults and back again,
    # because one layer of abstraction is never enough.
    strategy_adapter = StrategyAdapterFactory.create(
        strategy=strategy,
        rules=service._rules,
        event_bus=event_bus,
        decision_threshold=config.ml_decision_threshold,
        ambiguity_margin=config.ml_ambiguity_margin,
        enable_disagreement_tracking=config.ml_enable_disagreement_tracking,
    )
    service._strategy_port = strategy_adapter

    # Inject the Wuzz rule when feature flags are active
    if flag_store is not None:
        wuzz_rule_def = RuleDefinition(
            name="WuzzRule", divisor=7, label="Wuzz", priority=3
        )
        wuzz_rule = ConcreteRule(wuzz_rule_def)
        service._rules.append(wuzz_rule)

    # Print authentication status
    if auth_context is not None:
        print(f"  Authenticated as: {auth_context.user} ({auth_context.role.name})")

    # ----------------------------------------------------------------
    # Health Check Probes (Kubernetes-style)
    # ----------------------------------------------------------------
    health_registry = None
    startup_probe = None
    liveness_probe_inst = None
    readiness_probe_inst = None
    self_healing_mgr = None

    if args.health or args.liveness or args.readiness or args.startup_probe or args.health_dashboard or args.self_heal:
        HealthCheckRegistry.reset()
        health_registry = HealthCheckRegistry.get_instance()

        # Register subsystem health checks
        health_registry.register(ConfigHealthCheck(config))
        health_registry.register(CircuitBreakerHealthCheck(
            registry=CircuitBreakerRegistry.get_instance() if args.circuit_breaker else None,
        ))
        health_registry.register(CacheCoherenceHealthCheck(
            cache_store=cache_store,
        ))
        health_registry.register(SLABudgetHealthCheck(
            sla_monitor=sla_monitor,
        ))

        # ML engine health check — only if using ML strategy
        if strategy == EvaluationStrategy.MACHINE_LEARNING:
            health_registry.register(MLEngineHealthCheck(
                engine=rule_engine,
                rules=service._rules,
            ))
        else:
            health_registry.register(MLEngineHealthCheck())

        # Create probes
        def _evaluate_canary(n: int) -> str:
            """Evaluate a single number for liveness check."""
            results = service.run(n, n)
            return results[0].output if results else ""

        liveness_probe_inst = LivenessProbe(
            evaluate_fn=_evaluate_canary,
            canary_number=config.health_check_canary_number,
            canary_expected=config.health_check_canary_expected,
            event_bus=event_bus,
        )

        readiness_probe_inst = ReadinessProbe(
            registry=health_registry,
            degraded_is_ready=config.health_check_degraded_is_ready,
            event_bus=event_bus,
        )

        startup_probe = StartupProbe(
            milestones=config.health_check_startup_milestones,
            timeout_seconds=config.health_check_startup_timeout,
            event_bus=event_bus,
        )

        # Record startup milestones that have already been reached
        startup_probe.record_milestone("config_loaded")
        startup_probe.record_milestone("rules_initialized")
        startup_probe.record_milestone("engine_created")
        startup_probe.record_milestone("middleware_assembled")
        startup_probe.record_milestone("service_built")

        if args.self_heal:
            self_healing_mgr = SelfHealingManager(
                registry=health_registry,
                max_retries=config.health_check_self_healing_max_retries,
                backoff_base_ms=config.health_check_self_healing_backoff_ms,
                event_bus=event_bus,
            )

        print(
            "  +---------------------------------------------------------+\n"
            "  | HEALTH CHECKS: Kubernetes-Style Probes ENABLED          |\n"
            "  | Liveness, readiness, and startup probes are now active.  |\n"
            "  | The platform's vital signs are being monitored with     |\n"
            "  | the same rigor as a Kubernetes pod in production.        |\n"
            "  +---------------------------------------------------------+"
        )

    # Handle standalone probe commands (run and exit)
    if args.liveness and liveness_probe_inst is not None:
        report = liveness_probe_inst.probe()
        print(HealthDashboard.render(report, show_details=config.health_check_dashboard_show_details))
        if not (args.readiness or args.startup_probe):
            return 0 if report.overall_status.name == "UP" else 1

    if args.readiness and readiness_probe_inst is not None:
        report = readiness_probe_inst.probe()
        if self_healing_mgr is not None and report.overall_status.name not in ("UP",):
            healing_results = self_healing_mgr.heal_all_unhealthy(report.subsystem_checks)
            if any(healing_results.values()):
                # Re-probe after healing
                report = readiness_probe_inst.probe()
        print(HealthDashboard.render(report, show_details=config.health_check_dashboard_show_details))
        if not args.startup_probe:
            return 0 if report.overall_status.name in ("UP", "DEGRADED") else 1

    if args.startup_probe and startup_probe is not None:
        report = startup_probe.probe()
        print(HealthDashboard.render(report, show_details=config.health_check_dashboard_show_details))
        return 0 if report.overall_status.name == "UP" else 1

    # Cache warming (pre-populate cache, defeating the purpose)
    if args.cache_warm and cache_store is not None:
        cache_warmer = CacheWarmer(
            cache_store=cache_store,
            rule_engine=service._rule_engine,
            rules=service._rules,
        )
        warmed_count = cache_warmer.warm(start, end)
        print(
            f"  Cache warmed with {warmed_count} entries for range [{start}, {end}]."
        )
        print(
            "  (The entire purpose of caching has been defeated. Congratulations.)"
        )
        print()
    elif args.cache_warm:
        print("\n  Cache not enabled. Use --cache to enable.\n")
        return 0

    # Execute -- use locale manager for status messages if available
    if locale_mgr is not None:
        print(f"  {locale_mgr.t('messages.evaluating', start=start, end=end)}")
        print(f"  {locale_mgr.t('messages.strategy', name=strategy.name)}")
        print(f"  {locale_mgr.t('messages.output_format', name=output_format.name)}")
    else:
        print(f"  Evaluating FizzBuzz for range [{start}, {end}]...")
        print(f"  Strategy: {strategy.name}")
        print(f"  Output Format: {output_format.name}")
    print()

    boot_time = time.perf_counter()

    if args.use_async:
        results = asyncio.run(service.run_async(start, end))
    else:
        results = service.run(start, end)

    wall_time_ms = (time.perf_counter() - boot_time) * 1000

    # Output results
    formatted = service.format_results(results)
    print(formatted)

    # Summary
    if not args.no_summary:
        summary_text = service.format_summary()
        print(summary_text)
        if locale_mgr is not None:
            print(f"\n  {locale_mgr.t('messages.wall_clock', time=f'{wall_time_ms:.2f}')}")
        else:
            print(f"\n  Wall clock time: {wall_time_ms:.2f}ms")

    # Distributed tracing output
    if tracing_enabled:
        completed_traces = tracing_service.get_completed_traces()
        if args.trace_json:
            print(TraceExporter.export_json(completed_traces))
        else:
            # Waterfall for each trace
            for trace in completed_traces:
                print(TraceRenderer.render_waterfall(trace))
            print(TraceRenderer.render_summary(completed_traces))

    # Event Sourcing summary and temporal queries
    if es_system is not None:
        print(es_system.render_summary())

        if args.replay:
            replay_result = es_system.replay_events()
            print(f"  Replayed {replay_result['replayed_events']} events.")
            print(f"  Statistics after replay: {replay_result['statistics']}")
            print()

        if args.temporal_query is not None:
            temporal_state = es_system.temporal_engine.query_at_sequence(
                args.temporal_query
            )
            print("  +===========================================================+")
            print("  |             TEMPORAL QUERY RESULT                          |")
            print("  +===========================================================+")
            print(f"  |  As-of sequence    : {args.temporal_query:<37}|")
            print(f"  |  Events processed  : {temporal_state['events_processed']:<37}|")
            print(f"  |  Evaluations       : {temporal_state['total_evaluations']:<37}|")
            print(f"  |  Fizz Count        : {temporal_state['fizz_count']:<37}|")
            print(f"  |  Buzz Count        : {temporal_state['buzz_count']:<37}|")
            print(f"  |  FizzBuzz Count    : {temporal_state['fizzbuzz_count']:<37}|")
            print(f"  |  Plain Count       : {temporal_state['plain_count']:<37}|")
            print("  +===========================================================+")
            print()

    if blockchain_observer is not None:
        print(blockchain_observer.get_blockchain().get_chain_summary())

    # Chaos Engineering post-mortem
    if args.post_mortem and chaos_monkey is not None:
        scenario_name = args.gameday if args.gameday else None
        print(PostMortemGenerator.generate(chaos_monkey, scenario_name))

    if args.circuit_status and cb_middleware is not None:
        print(CircuitBreakerDashboard.render(cb_middleware.circuit_breaker))
    elif args.circuit_status:
        if locale_mgr is not None:
            print(f"\n  {locale_mgr.t('messages.circuit_breaker_not_enabled')}\n")
        else:
            print("\n  Circuit breaker not enabled. Use --circuit-breaker to enable.\n")

    # Feature flag evaluation summary
    if flag_store is not None:
        print(FlagEvaluationSummary.render(flag_store))

    # SLA dashboard
    if args.sla_dashboard and sla_monitor is not None:
        print(SLADashboard.render(sla_monitor))
    elif args.sla_dashboard:
        print("\n  SLA monitoring not enabled. Use --sla to enable.\n")

    # On-call status (when combined with --sla)
    if args.on_call and sla_monitor is not None:
        print(SLADashboard.render_on_call(sla_monitor))

    # Health check dashboard (post-execution)
    if args.health_dashboard and readiness_probe_inst is not None:
        report = readiness_probe_inst.probe()
        if self_healing_mgr is not None and report.overall_status.name not in ("UP",):
            healing_results = self_healing_mgr.heal_all_unhealthy(report.subsystem_checks)
            if any(healing_results.values()):
                report = readiness_probe_inst.probe()
        print(HealthDashboard.render(report, show_details=config.health_check_dashboard_show_details))
    elif args.health_dashboard:
        print("\n  Health checks not enabled. Use --health to enable.\n")

    # Cache statistics dashboard
    if args.cache_stats and cache_store is not None:
        stats = cache_store.get_statistics()
        print(CacheDashboard.render(stats))
    elif args.cache_stats:
        print("\n  Cache not enabled. Use --cache to enable.\n")

    # Prometheus metrics export
    if args.metrics_export and metrics_registry is not None:
        print("\n  +-- PROMETHEUS TEXT EXPOSITION FORMAT --+")
        print(PrometheusTextExporter.export(metrics_registry))
        print("  +--------------------------------------+\n")
    elif args.metrics_export:
        print("\n  Metrics not enabled. Use --metrics to enable.\n")

    # Metrics dashboard
    if args.metrics_dashboard and metrics_registry is not None:
        print(MetricsDashboard.render(metrics_registry, width=config.metrics_dashboard_width))
        # Run cardinality check
        if metrics_cardinality is not None:
            cardinalities = metrics_cardinality.check_all(metrics_registry)
            print("  Cardinality report:")
            for name, count in cardinalities.items():
                status = "OK" if count <= config.metrics_cardinality_threshold else "WARNING"
                print(f"    {name}: {count} unique label combos [{status}]")
            print()
    elif args.metrics_dashboard:
        print("\n  Metrics not enabled. Use --metrics to enable.\n")

    # Webhook dashboard and logs
    if webhook_manager is not None:
        print(WebhookDashboard.render(webhook_manager))

    if args.webhook_log and webhook_manager is not None:
        print(WebhookDashboard.render_delivery_log(webhook_manager))

    if args.webhook_dlq and webhook_manager is not None:
        print(WebhookDashboard.render_dlq(webhook_manager))

    # Service mesh topology
    if args.mesh_topology and mesh_control_plane is not None:
        print(MeshTopologyVisualizer.render(
            mesh_control_plane.registry,
            mesh_control_plane,
        ))
    elif args.mesh_topology:
        print("\n  Service mesh not enabled. Use --service-mesh to enable.\n")

    # Hot-reload dashboard
    if args.reload_status and hot_reload_raft is not None:
        print(HotReloadDashboard.render(
            raft=hot_reload_raft,
            orchestrator=hot_reload_orchestrator,
            watcher=hot_reload_watcher,
            dependency_graph=hot_reload_dep_graph,
            rollback_manager=hot_reload_rollback_mgr,
            width=config.hot_reload_dashboard_width,
            show_raft_details=config.hot_reload_dashboard_show_raft_details,
        ))

    # Rate limiting dashboard
    if args.rate_limit_dashboard and rate_limit_quota_manager is not None:
        print(RateLimitDashboard.render(
            rate_limit_quota_manager,
            width=config.rate_limiting_dashboard_width,
        ))
    elif args.rate_limit_dashboard:
        print("\n  Rate limiting not enabled. Use --rate-limit to enable.\n")

    # Quota status summary
    if args.quota and rate_limit_quota_manager is not None:
        qm = rate_limit_quota_manager
        print(
            "  +---------------------------------------------------------+\n"
            "  | QUOTA STATUS SUMMARY                                    |\n"
            "  +---------------------------------------------------------+\n"
            f"  | Requests:  {qm.total_allowed} allowed / {qm.total_denied} denied"
            + " " * max(0, 36 - len(f"{qm.total_allowed} allowed / {qm.total_denied} denied"))
            + "|\n"
            f"  | Denial Rate: {qm.denial_rate:.1f}%"
            + " " * max(0, 44 - len(f"{qm.denial_rate:.1f}%"))
            + "|\n"
            "  +---------------------------------------------------------+"
        )
    elif args.quota:
        print("\n  Rate limiting not enabled. Use --rate-limit to enable.\n")

    # Compliance dashboard and reports
    if args.compliance_dashboard and compliance_framework is not None:
        print(ComplianceDashboard.render(compliance_framework, width=config.compliance_dashboard_width))
    elif args.compliance_dashboard:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")

    if args.compliance_report and compliance_framework is not None:
        print(ComplianceDashboard.render_report(compliance_framework))
    elif args.compliance_report:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")

    if args.sox_audit and compliance_framework is not None:
        posture = compliance_framework.get_posture_summary()
        sox_trail = posture.get("sox_stats", [])
        if sox_trail:
            print(
                "  +---------------------------------------------------------+\n"
                "  | SOX SEGREGATION OF DUTIES AUDIT TRAIL                   |\n"
                "  +---------------------------------------------------------+"
            )
            for entry in sox_trail[-10:]:  # Last 10 entries
                assignments = entry.get("assignments", {})
                segregated = entry.get("segregation_satisfied", False)
                status = "OK" if segregated else "VIOLATION"
                print(f"  | Number {entry.get('number', '?'):>5} [{status}]")
                for role, person in assignments.items():
                    print(f"  |   {role}: {person.get('name', '?')}")
            if len(sox_trail) > 10:
                print(f"  | ... and {len(sox_trail) - 10} more entries")
            print("  +---------------------------------------------------------+")
            print()
        else:
            print("\n  No SOX audit trail entries recorded.\n")

    if args.hipaa_check and compliance_framework is not None:
        posture = compliance_framework.get_posture_summary()
        hipaa_stats = posture.get("hipaa_stats", {})
        if hipaa_stats:
            print(
                "  +---------------------------------------------------------+\n"
                "  | HIPAA PHI ACCESS LOG & ENCRYPTION STATISTICS            |\n"
                "  +---------------------------------------------------------+\n"
                f"  | PHI Encryptions:    {hipaa_stats.get('phi_encryptions', 0):<37}|\n"
                f"  | PHI Redactions:     {hipaa_stats.get('phi_redactions', 0):<37}|\n"
                f"  | PHI Access Events:  {hipaa_stats.get('phi_access_events', 0):<37}|\n"
                f"  | Algorithm:          {hipaa_stats.get('encryption_algorithm', 'N/A'):<37}|\n"
                f"  | Actual Security:    {hipaa_stats.get('actual_security_provided', 'None'):<37}|\n"
                "  +---------------------------------------------------------+"
            )
            print()
        else:
            print("\n  No HIPAA statistics recorded.\n")

    # Stop the hot-reload watcher on exit
    if hot_reload_watcher is not None and hot_reload_watcher.is_running:
        hot_reload_watcher.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
