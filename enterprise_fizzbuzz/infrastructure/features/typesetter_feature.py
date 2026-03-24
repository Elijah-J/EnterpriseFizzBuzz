"""Feature descriptor for the FizzPrint TeX-inspired typesetting engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class TypesetterFeature(FeatureDescriptor):
    name = "typesetter"
    description = "TeX-inspired typesetting engine with Knuth-Plass line breaking and PostScript output"
    middleware_priority = 131
    cli_flags = [
        ("--typeset", {"action": "store_true", "default": False,
                       "help": "Enable FizzPrint TeX-inspired typesetting engine for publication-quality reports"}),
        ("--typeset-output", {"type": str, "default": None, "metavar": "FILE",
                              "help": "Write PostScript typeset output to FILE (requires --typeset)"}),
        ("--typeset-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the FizzPrint typesetting statistics dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "typeset", False),
            bool(getattr(args, "typeset_output", None)),
            getattr(args, "typeset_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.typesetter import (
            FontMetrics,
            PageLayout,
            TypesetMiddleware,
        )

        ts_layout = PageLayout(
            page_width=config.typeset_page_width,
            page_height=config.typeset_page_height,
        )
        ts_font = FontMetrics(
            name=config.typeset_font_name,
            size=config.typeset_font_size,
        )
        typeset_middleware = TypesetMiddleware(
            output_path=getattr(args, "typeset_output", None) or config.typeset_output_path,
            enable_dashboard=getattr(args, "typeset_dashboard", False),
            layout=ts_layout,
            font=ts_font,
        )

        return typeset_middleware, typeset_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "typeset_dashboard", False):
                return "\n  FizzPrint not enabled. Use --typeset to enable.\n"
            return None

        from enterprise_fizzbuzz.infrastructure.typesetter import TypesetDashboard

        typeset_report = middleware.finalize()
        parts = []

        if typeset_report is not None:
            output_file = getattr(args, "typeset_output", None)
            if output_file:
                parts.append(
                    f"\n  FizzPrint PostScript written to: {output_file}"
                    f"\n  Pages: {len(typeset_report.pages)}, Lines: {typeset_report.total_lines}"
                )

            if getattr(args, "typeset_dashboard", False):
                parts.append(TypesetDashboard.render(
                    typeset_report,
                    width=80,
                ))
        elif getattr(args, "typeset_dashboard", False):
            parts.append("\n  FizzPrint: No results to typeset.\n")

        return "\n".join(parts) if parts else None
