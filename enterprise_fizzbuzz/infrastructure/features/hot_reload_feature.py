"""Feature descriptor for the Configuration Hot-Reload with Single-Node Raft Consensus."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class HotReloadFeature(FeatureDescriptor):
    name = "hot_reload"
    description = "Configuration hot-reload with Single-Node Raft Consensus"
    middleware_priority = 93
    cli_flags = [
        ("--hot-reload", {"action": "store_true",
                          "help": "Enable configuration hot-reload with Single-Node Raft Consensus (polls config.yaml for changes)"}),
        ("--reload-status", {"action": "store_true",
                             "help": "Display the hot-reload Raft consensus dashboard after execution"}),
        ("--config-diff", {"type": str, "metavar": "PATH", "default": None,
                           "help": "Compute and display a diff between current config and the specified YAML file"}),
        ("--config-validate", {"type": str, "metavar": "PATH", "default": None,
                               "help": "Validate the specified YAML configuration file and exit"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "hot_reload", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        import os
        from pathlib import Path
        from enterprise_fizzbuzz.infrastructure.hot_reload import create_hot_reload_subsystem

        config_path = Path(
            getattr(args, "config", None)
            or os.environ.get("EFP_CONFIG_PATH", str(Path(__file__).parents[2].parent / "config.yaml"))
        )

        raft, orchestrator, watcher, dep_graph, rollback_mgr = create_hot_reload_subsystem(
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

        watcher.start()

        return orchestrator, None

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | HOT-RELOAD: Single-Node Raft Consensus ENABLED          |\n"
            "  | Configuration changes will be detected and applied      |\n"
            "  | at runtime through a full Raft consensus protocol       |\n"
            "  | with 1 node. Elections: always unanimous. Heartbeats:   |\n"
            "  | sent to 0 followers. Consensus latency: 0.000ms.        |\n"
            "  | Democracy has never been more efficient.                |\n"
            "  +---------------------------------------------------------+"
        )
