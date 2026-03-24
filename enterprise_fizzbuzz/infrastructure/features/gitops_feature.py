"""Feature descriptor for the GitOps Configuration-as-Code Simulator subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class GitOpsFeature(FeatureDescriptor):
    name = "gitops"
    description = "Configuration-as-Code simulator with version control, drift detection, and proposals"
    middleware_priority = 0
    cli_flags = [
        ("--gitops", {"action": "store_true", "default": False,
                      "help": "Enable the GitOps Configuration-as-Code Simulator (version-control your YAML in RAM)"}),
        ("--gitops-commit", {"type": str, "metavar": "MESSAGE", "default": None,
                             "help": "Create a GitOps commit with the specified message (requires --gitops)"}),
        ("--gitops-diff", {"action": "store_true", "default": False,
                           "help": "Display the diff of the most recent GitOps commit"}),
        ("--gitops-log", {"action": "store_true", "default": False,
                          "help": "Display the GitOps commit log for the current branch"}),
        ("--gitops-propose", {"type": str, "metavar": "KEY=VALUE", "action": "append",
                              "default": [],
                              "help": "Propose a configuration change through the GitOps pipeline (e.g. --gitops-propose range.start=5)"}),
        ("--gitops-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the GitOps ASCII dashboard with commit log, drift, and proposals"}),
        ("--gitops-drift", {"action": "store_true", "default": False,
                            "help": "Detect configuration drift between committed and running state"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "gitops", False),
            bool(getattr(args, "gitops_commit", None)),
            getattr(args, "gitops_diff", False),
            getattr(args, "gitops_log", False),
            bool(getattr(args, "gitops_propose", [])),
            getattr(args, "gitops_dashboard", False),
            getattr(args, "gitops_drift", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        # GitOps commands are early-exit when they are the only flags
        return self.is_enabled(args) and not getattr(args, "gitops", False)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.gitops import (
            GitOpsController,
            GitOpsDashboard,
        )

        gitops_controller = GitOpsController(
            default_branch=config.gitops_default_branch,
            max_history=config.gitops_max_commit_history,
            policy_enforcement=config.gitops_policy_enforcement,
            dry_run_range_start=config.gitops_dry_run_range_start,
            dry_run_range_end=config.gitops_dry_run_range_end,
            approval_mode=config.gitops_approval_mode,
            tracked_subsystems=config.gitops_blast_radius_subsystems,
        )

        # Build raw config for initialization
        raw_config = {}
        gitops_controller.initialize(raw_config, auto_commit=config.gitops_auto_commit_on_load)

        if args.gitops_commit:
            commit = gitops_controller.repository.commit(
                raw_config,
                message=args.gitops_commit,
            )
            print(f"\n  [GitOps] Committed {commit.short_sha}: {args.gitops_commit}\n")

        if getattr(args, "gitops_propose", []):
            for prop_str in args.gitops_propose:
                if "=" in prop_str:
                    key, value = prop_str.split("=", 1)
                    gitops_controller.propose_change(
                        key=key.strip(),
                        value=value.strip(),
                    )

        if args.gitops_diff:
            diff_entries = gitops_controller.get_diff()
            if diff_entries:
                for entry in diff_entries:
                    print(f"  {entry}")
            else:
                print("  No changes in the latest commit.")

        if args.gitops_log:
            commits = gitops_controller.get_log()
            for c in commits:
                print(f"  {c}")

        if args.gitops_drift:
            drift = gitops_controller.detect_drift(raw_config)
            if drift:
                for d in drift:
                    print(f"  {d}")
            else:
                print("  No configuration drift detected.")

        if args.gitops_dashboard:
            dashboard_output = gitops_controller.render_dashboard(
                raw_config,
                width=config.gitops_dashboard_width,
            )
            print(dashboard_output)

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.gitops import GitOpsController

        gitops_controller = GitOpsController(
            default_branch=config.gitops_default_branch,
            max_history=config.gitops_max_commit_history,
            policy_enforcement=config.gitops_policy_enforcement,
            dry_run_range_start=config.gitops_dry_run_range_start,
            dry_run_range_end=config.gitops_dry_run_range_end,
            approval_mode=config.gitops_approval_mode,
            tracked_subsystems=config.gitops_blast_radius_subsystems,
        )

        return gitops_controller, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
