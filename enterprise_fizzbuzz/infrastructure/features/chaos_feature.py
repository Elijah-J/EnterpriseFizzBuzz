"""Feature descriptor for the Chaos Engineering subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ChaosFeature(FeatureDescriptor):
    name = "chaos"
    description = "Chaos Engineering fault injection with Game Day scenarios and post-mortems"
    middleware_priority = 92
    cli_flags = [
        ("--chaos", {"action": "store_true",
                     "help": "Enable Chaos Engineering fault injection (the monkey awakens)"}),
        ("--chaos-level", {"type": int, "choices": [1, 2, 3, 4, 5], "default": None, "metavar": "N",
                           "help": "Chaos severity level 1-5 (1=gentle breeze, 5=apocalypse)"}),
        ("--gameday", {"type": str, "nargs": "?", "const": "total_chaos", "default": None, "metavar": "SCENARIO",
                       "help": "Run a Game Day chaos scenario (modulo_meltdown, confidence_crisis, slow_burn, total_chaos)"}),
        ("--post-mortem", {"action": "store_true",
                           "help": "Generate a post-mortem incident report after chaos execution"}),
        ("--load-test", {"action": "store_true", "default": False,
                         "help": "Run a load test against the FizzBuzz evaluation engine (because n%%3 needs stress testing)"}),
        ("--load-profile", {"type": str,
                            "choices": ["smoke", "baseline", "stress", "spike", "soak"],
                            "default": None, "metavar": "PROFILE",
                            "help": "Workload profile for the load test (default: from config)"}),
        ("--load-vus", {"type": int, "default": None, "metavar": "N",
                        "help": "Number of Virtual Users for the load test (default: from config/profile)"}),
        ("--load-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the full ASCII load test dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "chaos", False),
            getattr(args, "gameday", None) is not None,
            getattr(args, "load_test", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        # Handle load-test only (no chaos monkey needed)
        if getattr(args, "load_test", False) and not getattr(args, "chaos", False) and getattr(args, "gameday", None) is None:
            self._run_load_test(args, config, event_bus)
            return None, None

        from enterprise_fizzbuzz.infrastructure.chaos import (
            ChaosMiddleware,
            ChaosMonkey,
            FaultSeverity,
            FaultType,
        )

        chaos_level = getattr(args, "chaos_level", None) or config.chaos_level
        chaos_severity = FaultSeverity(chaos_level)

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
            f"  | Severity: {f'Level {chaos_level} ({chaos_severity.label})':<46}|\n"
            f"  | Injection probability: {f'{chaos_severity.probability:.0%}':<33}|\n"
            "  | The Chaos Monkey is awake and hungry for modulo ops.    |\n"
            "  +---------------------------------------------------------+"
        )

        return chaos_monkey, chaos_middleware

    def _run_load_test(self, args: Any, config: Any, event_bus: Any) -> None:
        """Execute the load testing framework."""
        from enterprise_fizzbuzz.infrastructure.chaos import (
            LoadTestDashboard,
            WorkloadProfile,
            run_load_test,
        )

        profile_name = getattr(args, "load_profile", None) or config.load_testing_default_profile
        profile_map = {
            "smoke": WorkloadProfile.SMOKE,
            "load": WorkloadProfile.LOAD,
            "baseline": WorkloadProfile.LOAD,
            "stress": WorkloadProfile.STRESS,
            "spike": WorkloadProfile.SPIKE,
            "endurance": WorkloadProfile.ENDURANCE,
            "soak": WorkloadProfile.ENDURANCE,
        }
        lt_profile = profile_map.get(profile_name, WorkloadProfile.SMOKE)
        lt_vus = getattr(args, "load_vus", None) or config.load_testing_default_vus

        print(
            "  +---------------------------------------------------------+\n"
            "  | ENTERPRISE FIZZBUZZ LOAD TESTING FRAMEWORK              |\n"
            "  | Stress-testing modulo arithmetic since 2026             |\n"
            "  +---------------------------------------------------------+"
        )
        print(f"  Profile: {profile_name.upper()} | VUs: {lt_vus}")
        print(f"  Numbers per VU: {config.load_testing_numbers_per_vu}")
        print()
        print("  Spawning virtual users...")
        print()

        lt_report, lt_latencies = run_load_test(
            lt_profile,
            config.rules,
            num_vus=lt_vus,
            numbers_per_vu=config.load_testing_numbers_per_vu,
            event_callback=event_bus.publish if event_bus else None,
            timeout_seconds=config.load_testing_timeout_seconds,
        )

        print(f"  Load test complete: {lt_report.total_requests} requests in {lt_report.elapsed_seconds:.3f}s")
        print(f"  Throughput: {lt_report.requests_per_second:.1f} req/s")
        print(f"  Error rate: {lt_report.error_rate * 100:.2f}%")
        print(f"  Performance grade: {lt_report.grade.value}")
        print()

        if getattr(args, "load_dashboard", False):
            print(LoadTestDashboard.render(
                lt_report,
                latencies_ms=lt_latencies,
                width=config.load_testing_dashboard_width,
                histogram_buckets=config.load_testing_histogram_buckets,
            ))
