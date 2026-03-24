"""Feature descriptor for the FizzMVCC MVCC transaction engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzMVCCFeature(FeatureDescriptor):
    name = "fizzmvcc"
    description = "Multi-Version Concurrency Control with ACID transactions, snapshot isolation, and connection pooling"
    middleware_priority = 118
    cli_flags = [
        ("--fizzmvcc", {"action": "store_true",
                        "help": "Enable the MVCC transaction engine"}),
        ("--fizzmvcc-isolation", {"type": str, "default": "read-committed",
                                  "choices": ["read-uncommitted", "read-committed", "repeatable-read", "serializable"],
                                  "help": "Default isolation level for transactions"}),
        ("--fizzmvcc-cc-mode", {"type": str, "default": "mvcc",
                                "choices": ["mvcc", "2pl", "occ"],
                                "help": "Concurrency control mode"}),
        ("--fizzmvcc-deadlock-timeout", {"type": int, "default": 1000, "metavar": "MS",
                                         "help": "Deadlock detection timeout in milliseconds"}),
        ("--fizzmvcc-deadlock-interval", {"type": int, "default": 100, "metavar": "MS",
                                          "help": "Deadlock detection cycle interval in milliseconds"}),
        ("--fizzmvcc-gc-strategy", {"type": str, "default": "lazy",
                                    "choices": ["eager", "lazy", "cooperative"],
                                    "help": "Garbage collection strategy"}),
        ("--fizzmvcc-gc-interval", {"type": int, "default": 5000, "metavar": "MS",
                                    "help": "Lazy GC cycle interval in milliseconds"}),
        ("--fizzmvcc-gc-warning-threshold", {"type": int, "default": 60, "metavar": "SECONDS",
                                             "help": "Seconds before warning about long-running transactions blocking GC"}),
        ("--fizzmvcc-gc-force-abort", {"type": int, "default": 300, "metavar": "SECONDS",
                                       "help": "Seconds before forcibly aborting long-running transactions blocking GC"}),
        ("--fizzmvcc-lock-escalation-threshold", {"type": int, "default": 5000,
                                                   "help": "Row locks before attempting table lock escalation"}),
        ("--fizzmvcc-plan-cache-size", {"type": int, "default": 1000,
                                        "help": "Maximum prepared statement plans in cache"}),
        ("--fizzmvcc-pool-min", {"type": int, "default": 5,
                                 "help": "Minimum connection pool size"}),
        ("--fizzmvcc-pool-max", {"type": int, "default": 20,
                                 "help": "Maximum connection pool size"}),
        ("--fizzmvcc-pool-timeout", {"type": int, "default": 30, "metavar": "SECONDS",
                                     "help": "Connection checkout timeout in seconds"}),
        ("--fizzmvcc-pool-max-lifetime", {"type": int, "default": 1800, "metavar": "SECONDS",
                                          "help": "Maximum connection lifetime in seconds"}),
        ("--fizzmvcc-explain-analyze", {"action": "store_true",
                                        "help": "Enable runtime statistics collection for EXPLAIN ANALYZE"}),
        ("--fizzmvcc-explain-buffers", {"action": "store_true",
                                        "help": "Include buffer statistics in EXPLAIN ANALYZE output"}),
        ("--fizzmvcc-auto-analyze-threshold", {"type": int, "default": 50,
                                               "help": "Modified tuples before auto-analyze triggers"}),
        ("--fizzmvcc-auto-analyze-scale-factor", {"type": float, "default": 0.1,
                                                   "help": "Fraction of table size added to auto-analyze threshold"}),
        ("--fizzmvcc-statistics-target", {"type": int, "default": 100,
                                          "help": "Pages sampled per analyze pass"}),
        ("--fizzmvcc-dashboard", {"action": "store_true",
                                   "help": "Enable the MVCC transaction dashboard"}),
        ("--fizzmvcc-occ-threshold", {"type": int, "default": 10,
                                      "help": "Read-to-write ratio above which OCC is recommended"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzmvcc", False),
            getattr(args, "fizzmvcc_dashboard", False),
            getattr(args, "fizzmvcc_explain_analyze", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzmvcc import (
            MVCCMiddleware,
            create_fizzmvcc_subsystem,
        )

        txn_manager, middleware = create_fizzmvcc_subsystem(
            isolation_level=getattr(args, "fizzmvcc_isolation", "read-committed").replace("-", "_"),
            cc_mode=getattr(args, "fizzmvcc_cc_mode", "mvcc"),
            deadlock_timeout_ms=getattr(args, "fizzmvcc_deadlock_timeout", 1000),
            deadlock_interval_ms=getattr(args, "fizzmvcc_deadlock_interval", 100),
            gc_strategy=getattr(args, "fizzmvcc_gc_strategy", "lazy"),
            gc_interval_ms=getattr(args, "fizzmvcc_gc_interval", 5000),
            gc_warning_threshold_s=getattr(args, "fizzmvcc_gc_warning_threshold", 60),
            gc_force_abort_threshold_s=getattr(args, "fizzmvcc_gc_force_abort", 300),
            lock_escalation_threshold=getattr(args, "fizzmvcc_lock_escalation_threshold", 5000),
            plan_cache_size=getattr(args, "fizzmvcc_plan_cache_size", 1000),
            pool_min=getattr(args, "fizzmvcc_pool_min", 5),
            pool_max=getattr(args, "fizzmvcc_pool_max", 20),
            pool_timeout=getattr(args, "fizzmvcc_pool_timeout", 30),
            pool_max_lifetime=getattr(args, "fizzmvcc_pool_max_lifetime", 1800),
            auto_analyze_threshold=getattr(args, "fizzmvcc_auto_analyze_threshold", 50),
            auto_analyze_scale_factor=getattr(args, "fizzmvcc_auto_analyze_scale_factor", 0.1),
            statistics_target=getattr(args, "fizzmvcc_statistics_target", 100),
            explain_analyze=getattr(args, "fizzmvcc_explain_analyze", False),
            explain_buffers=getattr(args, "fizzmvcc_explain_buffers", False),
            dashboard_width=config.fizzmvcc_dashboard_width,
            occ_threshold=getattr(args, "fizzmvcc_occ_threshold", 10),
        )

        return txn_manager, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzmvcc_dashboard", False):
            parts.append(middleware.render_dashboard())
        if getattr(args, "fizzmvcc", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
