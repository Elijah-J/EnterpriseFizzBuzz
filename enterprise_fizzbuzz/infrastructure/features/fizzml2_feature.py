"""Feature descriptor for FizzML2."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzML2Feature(FeatureDescriptor):
    name = "fizzml2"
    description = "AutoML and model serving with registry, training, deployment, and feature store"
    middleware_priority = 140
    cli_flags = [
        ("--fizzml2", {"action": "store_true", "default": False, "help": "Enable FizzML2"}),
        ("--fizzml2-train", {"type": str, "default": None, "help": "Train a model (name:type)"}),
        ("--fizzml2-deploy", {"type": str, "default": None, "help": "Deploy model to endpoint"}),
        ("--fizzml2-predict", {"type": str, "default": None, "help": "Predict (endpoint:input)"}),
        ("--fizzml2-models", {"action": "store_true", "default": False, "help": "List models"}),
        ("--fizzml2-endpoints", {"action": "store_true", "default": False, "help": "List endpoints"}),
        ("--fizzml2-features", {"action": "store_true", "default": False, "help": "List features"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzml2", False), getattr(args, "fizzml2_models", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzml2 import FizzML2Middleware, create_fizzml2_subsystem
        r, s, d, m = create_fizzml2_subsystem(dashboard_width=config.fizzml2_dashboard_width)
        return r, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzml2_models", False): parts.append(middleware.render_models())
        if getattr(args, "fizzml2", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
