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
from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager, _SingletonMeta
from enterprise_fizzbuzz.application.fizzbuzz_service import FizzBuzzServiceBuilder
from enterprise_fizzbuzz.infrastructure.middleware import (
    TranslationMiddleware,
)
from enterprise_fizzbuzz.domain.models import (
    AuthContext,
    EvaluationStrategy,
    FizzBuzzRole,
    OutputFormat,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.observers import ConsoleObserver, EventBus, StatisticsObserver
from enterprise_fizzbuzz.infrastructure.adapters.strategy_adapters import StrategyAdapterFactory
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule, RuleEngineFactory
from enterprise_fizzbuzz.infrastructure.auth import AuthorizationMiddleware, FizzBuzzTokenEngine, RoleRegistry
from enterprise_fizzbuzz.infrastructure.i18n import LocaleManager
from enterprise_fizzbuzz.infrastructure.features import FeatureRegistry

logger = logging.getLogger(__name__)


BANNER = r"""
  +===========================================================+
  |                                                           |
  |   FFFFFFFF II ZZZZZZZ ZZZZZZZ BBBBB   UU   UU ZZZZZZZ     |
  |   FF       II      ZZ      ZZ BB  BB  UU   UU      ZZ     |
  |   FFFFFF   II    ZZ      ZZ   BBBBB   UU   UU    ZZ       |
  |   FF       II   ZZ      ZZ   BB  BB  UU   UU   ZZ         |
  |   FF       II ZZZZZZZ ZZZZZZZ BBBBB   UUUUUU ZZZZZZZ      |
  |                                                           |
  |         E N T E R P R I S E   E D I T I O N               |
  |                    v1.0.0                                 |
  |                                                           |
  +===========================================================+
"""


def build_argument_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser with all supported options.

    Core platform flags are defined here. Feature-specific flags are
    registered dynamically via the FeatureRegistry plugin system.
    """
    parser = argparse.ArgumentParser(
        prog="fizzbuzz",
        description="Enterprise FizzBuzz Platform - Production-grade FizzBuzz evaluation engine",
        epilog="For support, please open a ticket with your Enterprise FizzBuzz Platform administrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ----------------------------------------------------------------
    # Core Platform Flags
    # ----------------------------------------------------------------
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
        choices=["standard", "chain_of_responsibility", "parallel_async", "machine_learning", "fizzchat", "fizzchat_debate"],
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

    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable distributed tracing with ASCII waterfall output (alias for --otel --otel-export console)",
    )

    parser.add_argument(
        "--trace-json",
        action="store_true",
        help="Enable distributed tracing with OTLP JSON export output (alias for --otel --otel-export otlp)",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all output except evaluation results",
    )

    # ----------------------------------------------------------------
    # Feature-Specific Flags (registered by feature descriptors)
    # ----------------------------------------------------------------
    FeatureRegistry.discover()
    FeatureRegistry.register_cli_flags(parser)

    return parser


def _walk_all_frames(roots: list) -> list:
    """Recursively collect all FlameFrame objects from a frame forest."""
    result = []
    for r in roots:
        result.append(r)
        result.extend(_walk_all_frames(r.children))
    return result


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
    if not getattr(args, "no_banner", False):
        print(BANNER)

    # Reset singleton for fresh config
    _SingletonMeta.reset()

    # Configuration
    config = ConfigurationManager(config_path=args.config)
    config.load()

    # ----------------------------------------------------------------
    # Feature Registry: Early Exits
    # ----------------------------------------------------------------
    # Some features (cross-compiler, bytecode VM, FizzSQL, etc.) handle
    # standalone commands that print output and exit before the main
    # evaluation pipeline runs.
    exit_code = FeatureRegistry.run_early_exits(args, config)
    if exit_code is not None:
        return exit_code

    # ----------------------------------------------------------------
    # Evaluation Parameters (CLI overrides config)
    # ----------------------------------------------------------------
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

    # Metadata flag (CLI overrides config)
    if args.metadata:
        config._raw_config.setdefault("output", {})["include_metadata"] = True

    # Strategy
    strategy_map = {
        "standard": EvaluationStrategy.STANDARD,
        "chain_of_responsibility": EvaluationStrategy.CHAIN_OF_RESPONSIBILITY,
        "parallel_async": EvaluationStrategy.PARALLEL_ASYNC,
        "machine_learning": EvaluationStrategy.MACHINE_LEARNING,
        "fizzchat": EvaluationStrategy.FIZZCHAT,
        "fizzchat_debate": EvaluationStrategy.FIZZCHAT_DEBATE,
    }
    strategy = (
        strategy_map.get(args.strategy) if args.strategy else config.evaluation_strategy
    )

    # ----------------------------------------------------------------
    # Core Services
    # ----------------------------------------------------------------
    event_bus = EventBus()
    stats_observer = StatisticsObserver()
    event_bus.subscribe(stats_observer)

    if args.verbose:
        console_observer = ConsoleObserver(verbose=True)
        event_bus.subscribe(console_observer)

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

    # ----------------------------------------------------------------
    # Role-Based Access Control (RBAC) setup
    # ----------------------------------------------------------------
    auth_context = None
    rbac_active = False

    if args.token:
        try:
            auth_context = FizzBuzzTokenEngine.validate_token(
                args.token, config.rbac_token_secret
            )
            rbac_active = True
        except Exception as e:
            print(f"  [AUTHENTICATION FAILED] {e}")
            return 1

    elif args.user:
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
            "  | your password on a Post-It note and sticking it to      |\n"
            "  | your monitor. Proceed with existential dread.           |\n"
            "  +---------------------------------------------------------+"
        )

    elif config.rbac_enabled:
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

    # ----------------------------------------------------------------
    # Feature Registry: Create Enabled Features
    # ----------------------------------------------------------------
    # Each feature descriptor checks its CLI flags, creates its service
    # and middleware objects, and prints its banner. The registry returns
    # (feature, service, middleware) tuples sorted by middleware_priority.
    enabled_features = FeatureRegistry.create_enabled(args, config, event_bus)

    # ----------------------------------------------------------------
    # Rule Engine & Builder
    # ----------------------------------------------------------------
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

    # Add Unit of Work if any feature provided one
    for feature, service_obj, mw in enabled_features:
        if hasattr(service_obj, '_is_unit_of_work') and service_obj._is_unit_of_work:
            builder.with_unit_of_work(service_obj)

    # Add auth context to builder
    if auth_context is not None:
        builder.with_auth_context(auth_context)

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

    # Wire all feature middleware into the builder pipeline
    for feature, service_obj, middleware in enabled_features:
        if middleware is not None:
            builder.with_middleware(middleware)

    # Build the service
    service = builder.build()

    # ----------------------------------------------------------------
    # Dependency Injection Container Demonstration
    # ----------------------------------------------------------------
    # The DI container exists alongside the builder. It does NOT replace
    # the existing wiring — it merely proves that we COULD have used an
    # IoC container instead of a builder, had we wanted to add yet another
    # layer of abstraction to our already stratospheric abstraction stack.
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
    flag_store = None
    for feature, service_obj, mw in enabled_features:
        if feature.name == "feature_flags" and service_obj is not None:
            flag_store = service_obj
            break

    if flag_store is not None:
        wuzz_rule_def = RuleDefinition(
            name="WuzzRule", divisor=7, label="Wuzz", priority=3
        )
        wuzz_rule = ConcreteRule(wuzz_rule_def)
        service._rules.append(wuzz_rule)

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

    # ----------------------------------------------------------------
    # Feature Registry: Post-Execution Rendering
    # ----------------------------------------------------------------
    # Each feature descriptor's render() method produces dashboards,
    # reports, and statistics for post-execution display.
    middleware_map = {f.name: mw for f, svc, mw in enabled_features}
    rendered = FeatureRegistry.render_all(args, middleware_map)
    for output in rendered:
        print()
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
