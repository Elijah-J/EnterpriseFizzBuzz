"""Feature descriptor for the FizzCI continuous integration pipeline engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzCIFeature(FeatureDescriptor):
    name = "fizzci"
    description = "Continuous integration pipeline engine with DAG execution, matrix builds, and artifact management"
    middleware_priority = 122
    cli_flags = [
        ("--fizzci", {"action": "store_true", "default": False,
                      "help": "Enable FizzCI: continuous integration pipeline engine with DAG execution and matrix builds"}),
        ("--fizzci-run", {"type": str, "default": None,
                          "help": "Run a named pipeline (e.g., fizzbuzz-ci)"}),
        ("--fizzci-trigger", {"type": str, "default": None,
                              "help": "Trigger a pipeline via simulated webhook event (push, pull_request, tag)"}),
        ("--fizzci-status", {"action": "store_true", "default": False,
                             "help": "Display current pipeline execution status"}),
        ("--fizzci-logs", {"type": str, "default": None,
                           "help": "Display logs for a specific job (format: pipeline/job)"}),
        ("--fizzci-artifacts", {"action": "store_true", "default": False,
                                "help": "List all stored artifacts across pipeline runs"}),
        ("--fizzci-pipelines", {"action": "store_true", "default": False,
                                "help": "List all registered pipeline definitions"}),
        ("--fizzci-history", {"action": "store_true", "default": False,
                              "help": "Display pipeline execution history"}),
        ("--fizzci-cache-clear", {"action": "store_true", "default": False,
                                  "help": "Clear the build cache"}),
        ("--fizzci-matrix", {"type": str, "default": None,
                             "help": "Preview matrix expansion for a pipeline without executing"}),
        ("--fizzci-dry-run", {"type": str, "default": None,
                              "help": "Dry-run a pipeline: parse, expand, and visualize DAG without executing"}),
        ("--fizzci-retry", {"type": str, "default": None,
                            "help": "Retry a failed pipeline run by run ID"}),
        ("--fizzci-template", {"type": str, "default": None,
                               "help": "Display a pipeline template definition"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzci", False),
            getattr(args, "fizzci_run", None),
            getattr(args, "fizzci_trigger", None),
            getattr(args, "fizzci_status", False),
            getattr(args, "fizzci_logs", None),
            getattr(args, "fizzci_artifacts", False),
            getattr(args, "fizzci_pipelines", False),
            getattr(args, "fizzci_history", False),
            getattr(args, "fizzci_cache_clear", False),
            getattr(args, "fizzci_matrix", None),
            getattr(args, "fizzci_dry_run", None),
            getattr(args, "fizzci_retry", None),
            getattr(args, "fizzci_template", None),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzci import (
            FizzCIMiddleware,
            create_fizzci_subsystem,
        )

        engine, dashboard, middleware = create_fizzci_subsystem(
            max_parallel_jobs=config.fizzci_max_parallel_jobs,
            job_timeout=config.fizzci_job_timeout,
            step_timeout=config.fizzci_step_timeout,
            max_retries=config.fizzci_max_retries,
            artifact_max_size=config.fizzci_artifact_max_size,
            cache_max_size=config.fizzci_cache_max_size,
            log_buffer_size=config.fizzci_log_buffer_size,
            history_max_runs=config.fizzci_history_max_runs,
            dashboard_width=config.fizzci_dashboard_width,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzci_pipelines", False):
            parts.append(middleware.render_pipelines())
        if getattr(args, "fizzci_run", None):
            parts.append(middleware.render_run_result(args.fizzci_run))
        if getattr(args, "fizzci_trigger", None):
            parts.append(middleware.render_trigger_result(args.fizzci_trigger))
        if getattr(args, "fizzci_status", False):
            parts.append(middleware.render_status())
        if getattr(args, "fizzci_logs", None):
            parts.append(middleware.render_logs(args.fizzci_logs))
        if getattr(args, "fizzci_artifacts", False):
            parts.append(middleware.render_artifacts())
        if getattr(args, "fizzci_history", False):
            parts.append(middleware.render_history())
        if getattr(args, "fizzci_cache_clear", False):
            parts.append(middleware.render_cache_clear())
        if getattr(args, "fizzci_matrix", None):
            parts.append(middleware.render_matrix_preview(args.fizzci_matrix))
        if getattr(args, "fizzci_dry_run", None):
            parts.append(middleware.render_dry_run(args.fizzci_dry_run))
        if getattr(args, "fizzci_template", None):
            parts.append(middleware.render_template(args.fizzci_template))
        if getattr(args, "fizzci", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
