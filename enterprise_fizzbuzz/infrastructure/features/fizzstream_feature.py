"""Feature descriptor for FizzStream distributed stream processing."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzStreamFeature(FeatureDescriptor):
    name = "fizzstream"
    description = "Distributed stream processing engine for continuous computation"
    middleware_priority = 38
    cli_flags = [
        ("--fizzstream", {"action": "store_true",
                          "help": "Enable FizzStream distributed stream processing engine"}),
        ("--fizzstream-job", {"type": str, "default": None, "metavar": "FILE",
                              "help": "Submit a stream processing job defined in YAML"}),
        ("--fizzstream-sql", {"type": str, "default": None, "metavar": "QUERY",
                              "help": "Execute a streaming SQL query"}),
        ("--fizzstream-list-jobs", {"action": "store_true",
                                    "help": "List all active and completed jobs"}),
        ("--fizzstream-cancel", {"type": str, "default": None, "metavar": "JOB_ID",
                                  "help": "Cancel a running stream processing job"}),
        ("--fizzstream-savepoint", {"nargs": 2, "default": None,
                                     "metavar": ("JOB_ID", "NAME"),
                                     "help": "Trigger a savepoint for a running job"}),
        ("--fizzstream-restore", {"nargs": 2, "default": None,
                                   "metavar": ("JOB_ID", "SAVEPOINT"),
                                   "help": "Restore a job from a savepoint"}),
        ("--fizzstream-scale", {"nargs": 3, "default": None,
                                 "metavar": ("JOB_ID", "OPERATOR", "PARALLELISM"),
                                 "help": "Adjust operator parallelism"}),
        ("--fizzstream-metrics", {"type": str, "default": None, "metavar": "JOB_ID",
                                   "help": "Display per-operator metrics"}),
        ("--fizzstream-dashboard", {"action": "store_true",
                                     "help": "Display real-time ASCII pipeline dashboard"}),
        ("--fizzstream-checkpoint-interval", {"type": int, "default": None, "metavar": "MS",
                                               "help": "Checkpoint interval (ms)"}),
        ("--fizzstream-state-backend", {"type": str, "default": None,
                                         "choices": ["hashmap", "rocksdb"],
                                         "help": "State backend type"}),
        ("--fizzstream-watermark-interval", {"type": int, "default": None, "metavar": "MS",
                                              "help": "Watermark emission interval (ms)"}),
        ("--fizzstream-parallelism", {"type": int, "default": None, "metavar": "N",
                                       "help": "Default operator parallelism"}),
        ("--fizzstream-max-parallelism", {"type": int, "default": None, "metavar": "N",
                                           "help": "Maximum parallelism / key groups"}),
        ("--fizzstream-buffer-timeout", {"type": int, "default": None, "metavar": "MS",
                                          "help": "Buffer flush timeout (ms)"}),
        ("--fizzstream-restart-strategy", {"type": str, "default": None,
                                            "choices": ["fixed", "exponential", "none"],
                                            "help": "Restart strategy type"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzstream", False),
            getattr(args, "fizzstream_dashboard", False),
            getattr(args, "fizzstream_list_jobs", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzstream import (
            FizzStreamMiddleware,
            create_fizzstream_subsystem,
        )

        env, middleware = create_fizzstream_subsystem(
            parallelism=config.fizzstream_parallelism,
            max_parallelism=config.fizzstream_max_parallelism,
            checkpoint_interval_ms=config.fizzstream_checkpoint_interval_ms,
            state_backend=config.fizzstream_state_backend,
            dashboard_width=config.fizzstream_dashboard_width,
        )

        return env, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        parallelism = getattr(args, "fizzstream_parallelism", None)
        if parallelism is None:
            parallelism = config.fizzstream_parallelism
        state_backend = getattr(args, "fizzstream_state_backend", None)
        if state_backend is None:
            state_backend = config.fizzstream_state_backend
        return (
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZSTREAM: DISTRIBUTED STREAM PROCESSING ENGINE        |\n"
            f"  |   Parallelism: {parallelism}  State Backend: {state_backend:<18}|\n"
            "  |   Exactly-once, event-time, windowed aggregation        |\n"
            '  |   "Continuous computation for n % 3."                   |\n'
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzstream_list_jobs", False):
            parts.append(middleware.render_jobs())
        if getattr(args, "fizzstream_dashboard", False):
            parts.append(middleware.render_dashboard())
        if getattr(args, "fizzstream", False) and not parts:
            parts.append(middleware.render_status())
        return "\n".join(parts) if parts else None
