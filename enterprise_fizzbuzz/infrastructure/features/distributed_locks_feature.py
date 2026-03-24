"""Feature descriptor for the FizzLock Distributed Lock Manager."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class DistributedLocksFeature(FeatureDescriptor):
    name = "distributed_locks"
    description = "Hierarchical multi-granularity locking with deadlock detection and fencing tokens"
    middleware_priority = 130
    cli_flags = [
        ("--locks", {"action": "store_true", "default": False,
                     "help": "Enable FizzLock Distributed Lock Manager: hierarchical multi-granularity locking for concurrent evaluation"}),
        ("--lock-policy", {"choices": ["wait-die", "wound-wait"], "default": None,
                           "help": "Deadlock prevention policy for the lock manager (default: from config)"}),
        ("--lock-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzLock ASCII dashboard with active locks, wait-for graph, deadlock history, and contention heatmap"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "locks", False),
            getattr(args, "lock_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.distributed_locks import (
            ContentionProfiler,
            FencingTokenGenerator,
            HierarchicalLockManager,
            LeaseManager,
            LockMiddleware,
            WaitPolicy,
            WaitPolicyType,
        )

        lock_policy_str = getattr(args, "lock_policy", None) or config.distributed_locks_policy
        if lock_policy_str == "wound-wait":
            policy_type = WaitPolicyType.WOUND_WAIT
        else:
            policy_type = WaitPolicyType.WAIT_DIE

        lock_wait_policy = WaitPolicy(policy_type=policy_type)
        lock_token_gen = FencingTokenGenerator()
        lock_profiler = ContentionProfiler(
            hot_lock_threshold_ms=config.distributed_locks_hot_lock_threshold_ms,
        )
        lock_lease_mgr = LeaseManager(
            lease_duration=config.distributed_locks_lease_duration,
            grace_period=config.distributed_locks_grace_period,
            check_interval=config.distributed_locks_check_interval,
        )
        lock_lease_mgr.start()

        lock_manager = HierarchicalLockManager(
            wait_policy=lock_wait_policy,
            token_generator=lock_token_gen,
            lease_manager=lock_lease_mgr,
            profiler=lock_profiler,
        )

        middleware = LockMiddleware(manager=lock_manager)
        return lock_manager, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        lock_policy_str = getattr(args, "lock_policy", None) or config.distributed_locks_policy
        return (
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZLOCK DISTRIBUTED LOCK MANAGER                       |\n"
            "  | Hierarchical Multi-Granularity Locking                   |\n"
            "  | X | S | IS | IX | U  —  5x5 Compatibility Matrix        |\n"
            f"  | Policy: {lock_policy_str:<48}|\n"
            f"  | Lease: {config.distributed_locks_lease_duration:.0f}s + {config.distributed_locks_grace_period:.0f}s grace{' ' * 32}|\n"
            "  | Tarjan SCC Deadlock Detection | Fencing Tokens           |\n"
            '  | "Serializability for modulo arithmetic."                 |\n'
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "lock_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.distributed_locks import LockDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        return LockDashboard.render(
            manager=middleware.manager,
            width=config.distributed_locks_dashboard_width,
        )
