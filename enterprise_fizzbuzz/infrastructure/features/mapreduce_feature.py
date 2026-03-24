"""Feature descriptor for the FizzReduce MapReduce framework."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class MapReduceFeature(FeatureDescriptor):
    name = "mapreduce"
    description = "Distributed MapReduce computation with parallel mappers, reducers, and speculative execution"
    middleware_priority = 135
    cli_flags = [
        ("--mapreduce", {"action": "store_true", "default": False,
                         "help": "Enable FizzReduce: distributed MapReduce computation for FizzBuzz classification"}),
        ("--mr-mappers", {"type": int, "default": None, "metavar": "N",
                          "help": "Number of parallel mapper tasks for FizzReduce (default: from config)"}),
        ("--mr-reducers", {"type": int, "default": None, "metavar": "N",
                           "help": "Number of reducer partitions for FizzReduce (default: from config)"}),
        ("--mr-dashboard", {"action": "store_true", "default": False,
                            "help": "Display the FizzReduce MapReduce ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "mapreduce", False),
            getattr(args, "mr_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.mapreduce import MapReduceMiddleware

        middleware = MapReduceMiddleware()
        return None, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        num_mappers = getattr(args, "mr_mappers", None)
        if num_mappers is None:
            num_mappers = config.mapreduce_num_mappers
        num_reducers = getattr(args, "mr_reducers", None)
        if num_reducers is None:
            num_reducers = config.mapreduce_num_reducers
        return (
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZREDUCE: MAPREDUCE FRAMEWORK ENABLED                  |\n"
            f"  |   Mappers: {num_mappers}  Reducers: {num_reducers}  Speculative exec: ON       |\n"
            "  |   Shuffle & sort with combiner optimization              |\n"
            '  |   "Divide and conquer for n % 3."                        |\n'
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not (getattr(args, "mapreduce", False) or getattr(args, "mr_dashboard", False)):
            return None
        from enterprise_fizzbuzz.infrastructure.mapreduce import (
            MapReduceDashboard,
            MapReduceJob,
        )
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()

        num_mappers = getattr(args, "mr_mappers", None)
        if num_mappers is None:
            num_mappers = config.mapreduce_num_mappers
        num_reducers = getattr(args, "mr_reducers", None)
        if num_reducers is None:
            num_reducers = config.mapreduce_num_reducers
        spec_threshold = config.mapreduce_speculative_threshold

        mr_job = MapReduceJob(
            rules=config.rules,
            num_mappers=num_mappers,
            num_reducers=num_reducers,
            speculative_threshold=spec_threshold,
        )
        middleware.job = mr_job

        mr_results = mr_job.execute(config.range_start, config.range_end)

        parts = []
        parts.append("\n  FizzReduce: MapReduce job completed.")
        parts.append(f"  Job ID: {mr_job.job_id}")
        parts.append(f"  Elapsed: {mr_job.elapsed_seconds:.3f}s")
        parts.append("  Classification distribution:")
        for key in sorted(mr_results.keys()):
            parts.append(f"    {key}: {mr_results[key]}")
        parts.append("")

        if getattr(args, "mr_dashboard", False):
            parts.append(MapReduceDashboard.render(
                job=mr_job,
                width=config.mapreduce_dashboard_width,
            ))

        return "\n".join(parts)
