"""Feature descriptor for FizzAdmit admission controllers and CRD operator framework."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzAdmitFeature(FeatureDescriptor):
    name = "fizzadmit"
    description = "Kubernetes-style admission controllers and CRD operator framework for FizzKube"
    middleware_priority = 119
    cli_flags = [
        ("--fizzadmit", {"action": "store_true", "default": False,
                         "help": "Enable FizzAdmit: admission controllers and CRD operator framework"}),
        ("--fizzadmit-admission-chain", {"action": "store_true", "default": False,
                                          "help": "Display the registered admission chain"}),
        ("--fizzadmit-dry-run", {"type": str, "default": None, "metavar": "RESOURCE_YAML",
                                  "help": "Submit a resource through admission in dry-run mode"}),
        ("--fizzadmit-quota-status", {"type": str, "default": None, "metavar": "NAMESPACE",
                                       "help": "Display resource quota utilization for a namespace"}),
        ("--fizzadmit-limit-range", {"type": str, "default": None, "metavar": "NAMESPACE",
                                      "help": "Display LimitRange configuration for a namespace"}),
        ("--fizzadmit-security-profile", {"type": str, "default": None, "metavar": "NAMESPACE",
                                           "help": "Display pod security profile for a namespace"}),
        ("--fizzadmit-image-policy", {"action": "store_true", "default": False,
                                       "help": "Display configured image policy rules"}),
        ("--fizzadmit-webhooks", {"action": "store_true", "default": False,
                                   "help": "List registered webhook configurations"}),
        ("--fizzadmit-crd-list", {"action": "store_true", "default": False,
                                   "help": "List all registered CustomResourceDefinitions"}),
        ("--fizzadmit-crd-describe", {"type": str, "default": None, "metavar": "NAME",
                                       "help": "Describe a CRD schema, versions, and subresources"}),
        ("--fizzadmit-crd-instances", {"type": str, "default": None, "metavar": "KIND",
                                        "help": "List instances of a custom resource type"}),
        ("--fizzadmit-operators", {"action": "store_true", "default": False,
                                    "help": "List operators with reconciliation status"}),
        ("--fizzadmit-force-finalize", {"type": str, "default": None, "metavar": "RESOURCE",
                                         "help": "Forcibly remove all finalizers from a stuck resource"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzadmit", False),
            getattr(args, "fizzadmit_admission_chain", False),
            getattr(args, "fizzadmit_crd_list", False),
            getattr(args, "fizzadmit_operators", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzadmit import (
            FizzAdmitMiddleware,
            create_fizzadmit_subsystem,
        )

        subsystem, middleware = create_fizzadmit_subsystem(
            admission_timeout=config.fizzadmit_admission_timeout,
            finalizer_timeout=config.fizzadmit_finalizer_timeout,
            reconcile_max_concurrent=config.fizzadmit_reconcile_max_concurrent,
            reconcile_backoff_base=config.fizzadmit_reconcile_backoff_base,
            reconcile_backoff_cap=config.fizzadmit_reconcile_backoff_cap,
            leader_election_lease=config.fizzadmit_leader_election_lease,
            enable_default_image_rules=config.fizzadmit_enable_default_image_rules,
            default_security_profile=config.fizzadmit_default_security_profile,
            dashboard_width=config.fizzadmit_dashboard_width,
        )

        return subsystem, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzadmit_admission_chain", False):
            parts.append(middleware.render_admission_chain())
        if getattr(args, "fizzadmit_image_policy", False):
            parts.append(middleware.render_image_policy())
        if getattr(args, "fizzadmit_webhooks", False):
            parts.append(middleware.render_webhooks())
        if getattr(args, "fizzadmit_crd_list", False):
            parts.append(middleware.render_crd_list())
        if getattr(args, "fizzadmit_crd_describe", None) is not None:
            parts.append(middleware.render_crd_describe(args.fizzadmit_crd_describe))
        if getattr(args, "fizzadmit_operators", False):
            parts.append(middleware.render_operators())
        if getattr(args, "fizzadmit", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
