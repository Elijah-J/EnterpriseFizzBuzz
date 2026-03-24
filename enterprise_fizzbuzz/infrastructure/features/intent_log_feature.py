"""Feature descriptor for FizzWAL write-ahead intent log."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class IntentLogFeature(FeatureDescriptor):
    name = "intent_log"
    description = "ARIES-style write-ahead intent log with 3-phase crash recovery and checkpoint management"
    middleware_priority = 850
    cli_flags = [
        ("--wal-intent", {"action": "store_true",
                          "help": "Enable FizzWAL: write-ahead intent log with ARIES 3-phase crash recovery"}),
        ("--wal-mode", {"type": str, "choices": ["optimistic", "pessimistic", "speculative"], "default": None,
                        "help": "WAL execution mode: optimistic (write-through + rollback), pessimistic (shadow buffer), speculative (post-condition validation)"}),
        ("--wal-dashboard", {"action": "store_true",
                             "help": "Display the FizzWAL ASCII dashboard with log stats, active transactions, checkpoint history, and recovery report"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "wal_intent", False),
            getattr(args, "wal_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.intent_log import (
            CheckpointManager,
            CrashRecoveryEngine,
            ExecutionMode,
            IntentMiddleware,
            WriteAheadIntentLog,
        )

        mode_str = getattr(args, "wal_mode", None) or config.fizzwal_mode
        wal_mode_map = {
            "optimistic": ExecutionMode.OPTIMISTIC,
            "pessimistic": ExecutionMode.PESSIMISTIC,
            "speculative": ExecutionMode.SPECULATIVE,
        }
        exec_mode = wal_mode_map.get(mode_str, ExecutionMode.OPTIMISTIC)

        wal = WriteAheadIntentLog(mode=exec_mode)
        checkpoint_mgr = CheckpointManager(
            wal=wal,
            interval=config.fizzwal_checkpoint_interval,
        )
        recovery_engine = CrashRecoveryEngine(
            wal=wal,
            checkpoint_manager=checkpoint_mgr,
        )

        middleware = IntentMiddleware(
            wal=wal,
            checkpoint_manager=checkpoint_mgr,
        )

        # Attach recovery engine for dashboard rendering
        middleware._recovery_engine = recovery_engine

        return wal, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "wal_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.intent_log import IntentDashboard
        return IntentDashboard.render(
            wal=middleware._wal,
            checkpoint_manager=middleware._checkpoint_manager,
            recovery_engine=getattr(middleware, "_recovery_engine", None),
            width=60,
        )
