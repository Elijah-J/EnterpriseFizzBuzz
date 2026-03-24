"""Feature descriptor for the FizzDeploy container-native deployment pipeline."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzDeployFeature(FeatureDescriptor):
    name = "fizzdeploy"
    description = "Container-native deployment pipeline with four strategies, GitOps reconciliation, and cognitive load gating"
    middleware_priority = 115
    cli_flags = [
        ("--fizzdeploy", {"action": "store_true",
                          "help": "Enable FizzDeploy: container-native deployment pipeline with four strategies, GitOps reconciliation, and cognitive load gating"}),
        ("--fizzdeploy-apply", {"type": str, "default": None, "metavar": "MANIFEST",
                                "help": "Apply a deployment manifest (YAML file path or inline YAML)"}),
        ("--fizzdeploy-status", {"type": str, "default": None, "metavar": "DEPLOYMENT",
                                 "help": "Display deployment status and revision history"}),
        ("--fizzdeploy-rollback", {"nargs": 2, "default": None, "metavar": ("DEPLOYMENT", "REVISION"),
                                   "help": "Rollback a deployment to a specific revision number"}),
        ("--fizzdeploy-pipeline", {"type": str, "default": None, "metavar": "DEPLOYMENT",
                                   "help": "Display pipeline execution details for a deployment"}),
        ("--fizzdeploy-strategy", {"type": str, "default": None,
                                   "choices": ["rolling", "bluegreen", "canary", "recreate"],
                                   "help": "Override the default deployment strategy"}),
        ("--fizzdeploy-gitops-sync", {"action": "store_true",
                                      "help": "Trigger a manual GitOps reconciliation pass"}),
        ("--fizzdeploy-emergency", {"action": "store_true",
                                    "help": "Bypass cognitive load gating for emergency deployments"}),
        ("--fizzdeploy-dry-run", {"action": "store_true",
                                  "help": "Show what a deployment would change without applying"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzdeploy", False),
            getattr(args, "fizzdeploy_apply", None) is not None,
            getattr(args, "fizzdeploy_status", None) is not None,
            getattr(args, "fizzdeploy_rollback", None) is not None,
            getattr(args, "fizzdeploy_pipeline", None) is not None,
            getattr(args, "fizzdeploy_gitops_sync", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzdeploy import (
            FizzDeployMiddleware,
            create_fizzdeploy_subsystem,
        )

        pipeline_exec, gitops_rec, rollback_mgr, gate, manifest_parser, dashboard, middleware = (
            create_fizzdeploy_subsystem(
                default_strategy=config.fizzdeploy_default_strategy,
                max_revisions=config.fizzdeploy_max_revisions,
                health_check_interval=config.fizzdeploy_health_check_interval,
                dashboard_width=config.fizzdeploy_dashboard_width,
            )
        )

        return pipeline_exec, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.fizzdeploy import DeployDashboard
        parts = []
        if getattr(args, "fizzdeploy_status", None) is not None:
            parts.append(middleware.render_status(args.fizzdeploy_status))
        if getattr(args, "fizzdeploy_pipeline", None) is not None:
            parts.append(middleware.render_pipeline(args.fizzdeploy_pipeline))
        if getattr(args, "fizzdeploy", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
