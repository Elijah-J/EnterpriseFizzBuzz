"""Feature descriptor for FizzK8sOperator."""

from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzK8sOperatorFeature(FeatureDescriptor):
    name = "fizzk8soperator"
    description = "Kubernetes operator for CRD-based FizzBuzz resource management"
    middleware_priority = 164
    cli_flags = [
        ("--fizzk8soperator", {"action": "store_true", "default": False, "help": "Enable FizzK8sOperator"}),
        ("--fizzk8soperator-crds", {"action": "store_true", "default": False, "help": "List CRDs"}),
        ("--fizzk8soperator-resources", {"action": "store_true", "default": False, "help": "List resources"}),
        ("--fizzk8soperator-reconcile", {"type": str, "default": None, "help": "Reconcile a resource"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzk8soperator", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzk8soperator import (
            FizzK8sOperatorMiddleware, create_fizzk8soperator_subsystem,
        )
        ctrl, d, m = create_fizzk8soperator_subsystem(
            dashboard_width=config.fizzk8soperator_dashboard_width,
        )
        return ctrl, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        return middleware.render_dashboard()
