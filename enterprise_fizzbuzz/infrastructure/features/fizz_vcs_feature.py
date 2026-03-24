"""Feature descriptor for the FizzGit content-addressable version control system."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzVCSFeature(FeatureDescriptor):
    name = "fizz_vcs"
    description = "Content-addressable version control with SHA-256 object store, branching, diff, and bisect"
    middleware_priority = 181
    cli_flags = [
        ("--vcs", {"action": "store_true", "default": False,
                   "help": "Enable FizzGit content-addressable version control for evaluation state"}),
        ("--vcs-log", {"action": "store_true", "default": False,
                       "help": "Display the FizzGit commit log after execution"}),
        ("--vcs-diff", {"action": "store_true", "default": False,
                        "help": "Display the FizzGit diff of the last commit"}),
        ("--vcs-bisect", {"action": "store_true", "default": False,
                          "help": "Run a FizzGit bisect demonstration to locate a simulated regression"}),
        ("--vcs-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzGit ASCII dashboard with commit graph, branch list, and diff stats"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "vcs", False),
            getattr(args, "vcs_log", False),
            getattr(args, "vcs_diff", False),
            getattr(args, "vcs_bisect", False),
            getattr(args, "vcs_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizz_vcs import (
            FizzGitRepository,
            VCSMiddleware,
        )

        repo = FizzGitRepository(author=config.vcs_author)
        repo.init()

        middleware = VCSMiddleware(
            repo=repo,
            auto_commit=config.vcs_auto_commit,
            enable_dashboard=getattr(args, "vcs_dashboard", False),
        )

        return repo, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZGIT: CONTENT-ADDRESSABLE VCS ENABLED                |\n"
            "  |   Object Store: SHA-256 content-addressed               |\n"
            "  |   Branch: main  |  Auto-commit: ON                      |\n"
            "  |   Every evaluation is an immutable commit.              |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.fizz_vcs import VCSDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()

        repo = middleware.repo if hasattr(middleware, "repo") else None
        if repo is None:
            return None

        parts = []

        if getattr(args, "vcs_log", False):
            parts.append("\n  FizzGit Commit Log:")
            parts.append(VCSDashboard.render_log(repo))
            parts.append("")

        if getattr(args, "vcs_diff", False):
            head_commit = repo.ref_store.get_head_commit()
            if head_commit is not None:
                diffs = repo.diff(head_commit)
                parts.append("\n  FizzGit Diff (HEAD vs parent):")
                parts.append(VCSDashboard.render_diff(diffs))
                parts.append("")
            else:
                parts.append("\n  FizzGit: No commits to diff.\n")

        if getattr(args, "vcs_bisect", False):
            commits = repo.log(max_count=100)
            if len(commits) >= 3:
                good = commits[-1].hash
                bad = commits[0].hash
                parts.append(f"\n  FizzGit Bisect: searching {len(commits)} commits...")
                mid = repo.bisect_start(good, bad)
                while mid is not None:
                    idx = next(
                        (i for i, c in enumerate(commits) if c.hash == mid),
                        len(commits) // 2,
                    )
                    if idx > len(commits) // 2:
                        mid = repo.bisect_bad()
                    else:
                        mid = repo.bisect_good()
                result = repo.bisect_engine.result
                if result and result.first_bad_commit:
                    parts.append(f"  Bisect complete in {result.steps_taken} steps.")
                    parts.append(f"  First bad commit: {result.first_bad_commit[:12]}")
                repo.bisect_reset()
            else:
                parts.append("\n  FizzGit Bisect: Need at least 3 commits for bisect.\n")

        if getattr(args, "vcs_dashboard", False):
            parts.append(VCSDashboard.render(repo, width=config.vcs_dashboard_width))

        return "\n".join(parts) if parts else None
