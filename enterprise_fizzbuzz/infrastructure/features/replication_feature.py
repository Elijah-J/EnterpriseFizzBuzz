"""Feature descriptor for the FizzReplica database replication subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ReplicationFeature(FeatureDescriptor):
    name = "replication"
    description = "Database replication with WAL shipping, automatic failover, and cascading topology"
    middleware_priority = 133
    cli_flags = [
        ("--replicate", {"action": "store_true", "default": False,
                         "help": "Enable database replication with WAL shipping and automatic failover for FizzBuzz state"}),
        ("--replicate-mode", {"type": str, "choices": ["sync", "async", "quorum"],
                              "default": None, "metavar": "MODE",
                              "help": "Replication mode: sync (all ack), async (fire-and-forget), quorum (majority ack)"}),
        ("--replicate-dashboard", {"action": "store_true", "default": False,
                                   "help": "Display the FizzReplica ASCII dashboard with topology, lag, and failover history"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "replicate", False),
            getattr(args, "replicate_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.replication import (
            CascadingReplication,
            FailoverManager,
            ReplicaSet,
            ReplicationLagMonitor,
            ReplicationMiddleware,
            ReplicationMode,
        )

        rep_mode_str = getattr(args, "replicate_mode", None) or config.replication_mode
        rep_mode = ReplicationMode(rep_mode_str)
        rep_count = config.replication_replica_count

        replica_set = ReplicaSet(mode=rep_mode, replica_count=rep_count)
        lag_monitor = ReplicationLagMonitor(
            replica_set=replica_set,
            alert_threshold=config.replication_lag_threshold,
        )
        failover_mgr = FailoverManager(
            replica_set=replica_set,
            heartbeat_timeout_s=config.replication_heartbeat_timeout,
        )
        cascading = CascadingReplication(replica_set)

        middleware = None
        if getattr(args, "replicate", False):
            middleware = ReplicationMiddleware(
                replica_set=replica_set,
                lag_monitor=lag_monitor,
                failover_manager=failover_mgr,
            )

        service = {
            "replica_set": replica_set,
            "lag_monitor": lag_monitor,
            "failover_manager": failover_mgr,
            "cascading": cascading,
        }
        return service, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        from enterprise_fizzbuzz.infrastructure.replication import ReplicationMode
        rep_mode_str = getattr(args, "replicate_mode", None) or config.replication_mode
        rep_mode = ReplicationMode(rep_mode_str)
        rep_count = config.replication_replica_count
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZREPLICA: DATABASE REPLICATION ENABLED               |\n"
            f"  |   Mode: {rep_mode.value.upper():49s}|\n"
            f"  |   Replicas: {rep_count:<46d}|\n"
            "  |   WAL shipping with automatic failover and fencing.     |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "replicate_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.replication import ReplicationDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        # middleware may be None if only --replicate-dashboard was used
        # In that case, we need the service dict stored during create
        return None
