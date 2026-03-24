"""Feature descriptor for FizzPolicy declarative policy engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzPolicyFeature(FeatureDescriptor):
    name = "fizzpolicy"
    description = "Declarative policy engine with FizzRego language, bundle management, and decision logging"
    middleware_priority = 6
    cli_flags = [
        ("--fizzpolicy", {"action": "store_true", "default": False,
                          "help": "Enable FizzPolicy: declarative policy engine with FizzRego language"}),
        ("--fizzpolicy-bundle", {"type": str, "default": None, "metavar": "PATH",
                                  "help": "Load a policy bundle from the specified path"}),
        ("--fizzpolicy-bundle-build", {"type": str, "default": None, "metavar": "SOURCE_DIR",
                                        "help": "Build a policy bundle from a source directory"}),
        ("--fizzpolicy-bundle-push", {"type": str, "default": None, "metavar": "PATH",
                                       "help": "Push a built bundle to the bundle store"}),
        ("--fizzpolicy-bundle-activate", {"type": int, "default": None, "metavar": "REVISION",
                                           "help": "Activate a specific bundle revision"}),
        ("--fizzpolicy-bundle-rollback", {"type": int, "default": None, "metavar": "REVISION",
                                           "help": "Rollback to a previous bundle revision"}),
        ("--fizzpolicy-bundle-list", {"action": "store_true", "default": False,
                                       "help": "List all bundle revisions with metadata"}),
        ("--fizzpolicy-eval", {"type": str, "default": None, "metavar": "QUERY",
                                "help": "Evaluate a policy query (e.g., data.fizzbuzz.authz.allow)"}),
        ("--fizzpolicy-eval-explain", {"type": str, "default": None, "metavar": "QUERY",
                                        "help": "Evaluate a policy query with full explanation trace"}),
        ("--fizzpolicy-input", {"type": str, "default": None, "metavar": "JSON",
                                 "help": "Input document (JSON) for --fizzpolicy-eval or --fizzpolicy-eval-explain"}),
        ("--fizzpolicy-test", {"type": str, "default": None, "metavar": "BUNDLE_PATH",
                                "help": "Run all tests in a policy bundle"}),
        ("--fizzpolicy-test-coverage", {"type": str, "default": None, "metavar": "BUNDLE_PATH",
                                         "help": "Run tests with coverage analysis"}),
        ("--fizzpolicy-bench", {"type": str, "default": None, "metavar": "QUERY",
                                 "help": "Benchmark a policy query"}),
        ("--fizzpolicy-decisions", {"action": "store_true", "default": False,
                                     "help": "Query the decision log"}),
        ("--fizzpolicy-decisions-export", {"type": str, "default": None, "metavar": "FORMAT",
                                            "help": "Export decision logs (json, csv, fizzsheet)"}),
        ("--fizzpolicy-decisions-since", {"type": str, "default": None, "metavar": "TIMESTAMP",
                                           "help": "Filter decisions since timestamp (ISO 8601)"}),
        ("--fizzpolicy-decisions-until", {"type": str, "default": None, "metavar": "TIMESTAMP",
                                           "help": "Filter decisions until timestamp (ISO 8601)"}),
        ("--fizzpolicy-decisions-path", {"type": str, "default": None, "metavar": "PATH",
                                          "help": "Filter decisions by rule path"}),
        ("--fizzpolicy-decisions-result", {"type": str, "default": None, "metavar": "RESULT",
                                            "help": "Filter decisions by result (allow, deny)"}),
        ("--fizzpolicy-decisions-user", {"type": str, "default": None, "metavar": "USER",
                                          "help": "Filter decisions by user"}),
        ("--fizzpolicy-data-refresh", {"action": "store_true", "default": False,
                                        "help": "Trigger immediate refresh of all data adapters"}),
        ("--fizzpolicy-status", {"action": "store_true", "default": False,
                                  "help": "Show policy engine status (bundle, cache, latency, adapters)"}),
        ("--fizzpolicy-compile", {"type": str, "default": None, "metavar": "FILE",
                                   "help": "Compile a FizzRego file and show diagnostics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzpolicy", False),
            getattr(args, "fizzpolicy_status", False),
            getattr(args, "fizzpolicy_eval", None) is not None,
            getattr(args, "fizzpolicy_eval_explain", None) is not None,
            getattr(args, "fizzpolicy_decisions", False),
            getattr(args, "fizzpolicy_bundle_list", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzpolicy import (
            FizzPolicyMiddleware,
            create_fizzpolicy_subsystem,
        )

        engine, middleware = create_fizzpolicy_subsystem(
            signing_key=config.fizzpolicy_signing_key,
            eval_timeout_ms=config.fizzpolicy_eval_timeout_ms,
            max_iterations=config.fizzpolicy_max_iterations,
            cache_max_entries=config.fizzpolicy_cache_max_entries,
            explanation_mode=config.fizzpolicy_explanation_mode,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzpolicy_status", False):
            parts.append(middleware.render_status())
        if getattr(args, "fizzpolicy_decisions", False):
            parts.append(middleware.render_decisions(
                since=getattr(args, "fizzpolicy_decisions_since", None),
                until=getattr(args, "fizzpolicy_decisions_until", None),
                path=getattr(args, "fizzpolicy_decisions_path", None),
                result=getattr(args, "fizzpolicy_decisions_result", None),
                user=getattr(args, "fizzpolicy_decisions_user", None),
                page=1,
            ))
        if getattr(args, "fizzpolicy_bundle_list", False):
            parts.append(middleware.render_bundle_list())
        return "\n".join(parts) if parts else None
