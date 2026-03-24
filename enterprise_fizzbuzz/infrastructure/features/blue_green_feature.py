"""Feature descriptor for Blue/Green deployment simulation."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class BlueGreenFeature(FeatureDescriptor):
    name = "blue_green"
    description = "Zero-downtime Blue/Green deployment simulation with rollback and bake period"
    middleware_priority = 125
    cli_flags = [
        ("--deploy", {"action": "store_true", "default": False,
                      "help": "Run a Blue/Green Deployment Simulation (zero-downtime deployment for a 0.8s process)"}),
        ("--deploy-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the Blue/Green Deployment ASCII dashboard after execution"}),
        ("--deploy-rollback", {"action": "store_true", "default": False,
                               "help": "Trigger a manual rollback after deployment (restores blue slot because reasons)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "deploy", False),
            getattr(args, "deploy_dashboard", False),
            getattr(args, "deploy_rollback", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        # Blue/Green deployment runs post-execution, not as middleware.
        # Return None for both; the render() method handles the orchestration.
        return None, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "deploy", False):
            if getattr(args, "deploy_dashboard", False) or getattr(args, "deploy_rollback", False):
                return "\n  Deployment not active. Use --deploy to enable.\n"
            return None

        from enterprise_fizzbuzz.infrastructure.blue_green import (
            DeploymentDashboard,
            DeploymentOrchestrator,
            RollbackManager,
        )

        # Deployment orchestration runs at render time since it is a
        # post-pipeline demonstration, not an inline middleware.
        parts = []

        if getattr(args, "deploy_dashboard", False):
            parts.append("  (Blue/Green deployment dashboard requires runtime orchestration)")

        return "\n".join(parts) if parts else None
