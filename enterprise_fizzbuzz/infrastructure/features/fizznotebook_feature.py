"""Feature descriptor for the FizzNotebook interactive computational notebook."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzNotebookFeature(FeatureDescriptor):
    name = "fizznotebook"
    description = "Interactive computational notebook for FizzLang with cell execution, rich output, and export"
    middleware_priority = 136
    cli_flags = [
        ("--fizznotebook", {"action": "store_true", "default": False, "help": "Enable FizzNotebook"}),
        ("--fizznotebook-new", {"type": str, "default": None, "help": "Create a new notebook"}),
        ("--fizznotebook-open", {"type": str, "default": None, "help": "Open an existing notebook"}),
        ("--fizznotebook-run", {"type": str, "default": None, "help": "Run all cells in a notebook"}),
        ("--fizznotebook-list", {"action": "store_true", "default": False, "help": "List all notebooks"}),
        ("--fizznotebook-export", {"type": str, "default": None, "help": "Export notebook (name:format)"}),
        ("--fizznotebook-variables", {"type": str, "default": None, "help": "Show variables in a notebook session"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizznotebook", False), getattr(args, "fizznotebook_list", False),
                    getattr(args, "fizznotebook_run", None), getattr(args, "fizznotebook_new", None)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizznotebook import FizzNotebookMiddleware, create_fizznotebook_subsystem
        engine, dashboard, mw = create_fizznotebook_subsystem(
            max_cells=config.fizznotebook_max_cells, dashboard_width=config.fizznotebook_dashboard_width,
        )
        return engine, mw

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizznotebook_list", False): parts.append(middleware.render_list())
        if getattr(args, "fizznotebook_run", None): parts.append(middleware.render_run(args.fizznotebook_run))
        if getattr(args, "fizznotebook", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
