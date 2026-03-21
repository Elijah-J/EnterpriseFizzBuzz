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
import sys
import time
from pathlib import Path
from typing import Optional

from auth import AuthorizationMiddleware, FizzBuzzTokenEngine, RoleRegistry
from chaos import (
    ChaosMiddleware,
    ChaosMonkey,
    FaultSeverity,
    FaultType,
    GameDayRunner,
    PostMortemGenerator,
)
from blockchain import BlockchainObserver, FizzBuzzBlockchain
from circuit_breaker import (
    CircuitBreakerDashboard,
    CircuitBreakerMiddleware,
    CircuitBreakerRegistry,
)
from config import ConfigurationManager, _SingletonMeta
from fizzbuzz_service import FizzBuzzServiceBuilder
from formatters import FormatterFactory
from i18n import LocaleManager
from middleware import (
    LoggingMiddleware,
    TimingMiddleware,
    TranslationMiddleware,
    ValidationMiddleware,
)
from models import AuthContext, EvaluationStrategy, FizzBuzzRole, OutputFormat
from observers import ConsoleObserver, EventBus, StatisticsObserver
from rules_engine import RuleEngineFactory
from event_sourcing import EventSourcingSystem
from tracing import TraceExporter, TraceRenderer, TracingMiddleware, TracingService


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

    builder = (
        FizzBuzzServiceBuilder()
        .with_config(config)
        .with_event_bus(event_bus)
        .with_rule_engine(RuleEngineFactory.create(strategy))
        .with_output_format(output_format)
        .with_locale_manager(locale_mgr)
        .with_default_middleware()
    )

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

    if chaos_middleware is not None:
        builder.with_middleware(chaos_middleware)

    service = builder.build()

    # Print authentication status
    if auth_context is not None:
        print(f"  Authenticated as: {auth_context.user} ({auth_context.role.name})")

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
