"""Feature descriptor for the FizzLSP Language Server Protocol server."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzLSPFeature(FeatureDescriptor):
    name = "fizzlsp"
    description = "Language Server Protocol server for FizzLang with completions, diagnostics, hover, definition, rename, and semantic tokens"
    middleware_priority = 92
    cli_flags = [
        ("--fizzlsp", {"action": "store_true", "default": False,
                       "help": "Enable the FizzLSP Language Server Protocol server"}),
        ("--fizzlsp-analyze", {"type": str, "metavar": "FILE", "default": None,
                               "help": "Run the full LSP analysis pipeline on a FizzLang file and print diagnostics"}),
        ("--fizzlsp-complete", {"type": str, "nargs": 3, "metavar": ("FILE", "LINE", "COL"), "default": None,
                                "help": "Simulate a completion request at the given cursor position"}),
        ("--fizzlsp-hover", {"type": str, "nargs": 3, "metavar": ("FILE", "LINE", "COL"), "default": None,
                             "help": "Simulate a hover request and print hover content"}),
        ("--fizzlsp-definition", {"type": str, "nargs": 3, "metavar": ("FILE", "LINE", "COL"), "default": None,
                                  "help": "Simulate a go-to-definition request"}),
        ("--fizzlsp-references", {"type": str, "nargs": 3, "metavar": ("FILE", "LINE", "COL"), "default": None,
                                  "help": "Simulate a find-references request"}),
        ("--fizzlsp-rename", {"type": str, "nargs": 4, "metavar": ("FILE", "LINE", "COL", "NEW_NAME"), "default": None,
                              "help": "Simulate a rename request and print the workspace edit"}),
        ("--fizzlsp-format", {"type": str, "metavar": "FILE", "default": None,
                              "help": "Format a FizzLang file according to canonical style"}),
        ("--fizzlsp-symbols", {"type": str, "metavar": "FILE", "default": None,
                               "help": "Print the document symbol outline for a FizzLang file"}),
        ("--fizzlsp-tokens", {"type": str, "metavar": "FILE", "default": None,
                              "help": "Print semantic token classifications for every token"}),
        ("--fizzlsp-simulate", {"action": "store_true", "default": False,
                                "help": "Run a predefined editor simulation session with full JSON-RPC message exchange"}),
        ("--fizzlsp-metrics", {"action": "store_true", "default": False,
                               "help": "Print FizzLSP performance metrics"}),
        ("--fizzlsp-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the FizzLSP ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzlsp", False),
            getattr(args, "fizzlsp_analyze", None) is not None,
            getattr(args, "fizzlsp_complete", None) is not None,
            getattr(args, "fizzlsp_hover", None) is not None,
            getattr(args, "fizzlsp_definition", None) is not None,
            getattr(args, "fizzlsp_references", None) is not None,
            getattr(args, "fizzlsp_rename", None) is not None,
            getattr(args, "fizzlsp_format", None) is not None,
            getattr(args, "fizzlsp_symbols", None) is not None,
            getattr(args, "fizzlsp_tokens", None) is not None,
            getattr(args, "fizzlsp_simulate", False),
            getattr(args, "fizzlsp_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzlsp_analyze", None) is not None,
            getattr(args, "fizzlsp_complete", None) is not None,
            getattr(args, "fizzlsp_hover", None) is not None,
            getattr(args, "fizzlsp_definition", None) is not None,
            getattr(args, "fizzlsp_references", None) is not None,
            getattr(args, "fizzlsp_rename", None) is not None,
            getattr(args, "fizzlsp_format", None) is not None,
            getattr(args, "fizzlsp_symbols", None) is not None,
            getattr(args, "fizzlsp_tokens", None) is not None,
            getattr(args, "fizzlsp_simulate", False),
        ])

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.fizzlsp import FizzLSPServer

        server = FizzLSPServer(
            transport_type=config.fizzlsp_transport,
            tcp_port=config.fizzlsp_tcp_port,
            debounce_ms=config.fizzlsp_diagnostic_debounce_ms,
            max_completion_items=config.fizzlsp_max_completion_items,
            semantic_tokens_enabled=config.fizzlsp_semantic_tokens_enabled,
            dependent_type_diagnostics=config.fizzlsp_dependent_type_diagnostics,
        )

        if getattr(args, "fizzlsp_simulate", False):
            responses = server.simulate_session()
            for r in responses:
                print(r)
            return 0

        # For file-based commands, read the file and open it
        file_arg = (
            getattr(args, "fizzlsp_analyze", None)
            or (getattr(args, "fizzlsp_complete", None) or [None])[0]
            or (getattr(args, "fizzlsp_hover", None) or [None])[0]
            or (getattr(args, "fizzlsp_definition", None) or [None])[0]
            or (getattr(args, "fizzlsp_references", None) or [None])[0]
            or (getattr(args, "fizzlsp_rename", None) or [None])[0]
            or getattr(args, "fizzlsp_format", None)
            or getattr(args, "fizzlsp_symbols", None)
            or getattr(args, "fizzlsp_tokens", None)
        )
        if file_arg:
            import os
            with open(file_arg, "r") as f:
                source = f.read()
            uri = f"file:///{os.path.abspath(file_arg).replace(os.sep, '/')}"
            server._initialize_handshake()
            server._doc_manager.open_document(uri, "fizzlang", 1, source)
            server._on_document_change(uri)

            if getattr(args, "fizzlsp_analyze", None):
                result = server._analysis_cache.get(uri)
                if result:
                    for d in result.diagnostics:
                        print(f"  [{d.severity.name}] L{d.range.start.line}:{d.range.start.character} {d.code}: {d.message}")
                    print(f"\nSymbols: {len(result.symbol_table.symbols)}")
                    print(f"Analysis time: {result.analysis_time_ms:.1f}ms")

            elif getattr(args, "fizzlsp_format", None):
                edits = server._formatting_provider.format(uri, server._analysis_cache.get(uri, None), source)
                formatted = source
                for edit in reversed(edits):
                    lines = formatted.split("\n")
                    formatted = server._formatting_provider._apply_edit(formatted, edit)
                print(formatted)

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzlsp import (
            FizzLSPMiddleware,
            FizzLSPServer,
        )

        server = FizzLSPServer(
            transport_type=config.fizzlsp_transport,
            tcp_port=config.fizzlsp_tcp_port,
            debounce_ms=config.fizzlsp_diagnostic_debounce_ms,
            max_completion_items=config.fizzlsp_max_completion_items,
            semantic_tokens_enabled=config.fizzlsp_semantic_tokens_enabled,
            dependent_type_diagnostics=config.fizzlsp_dependent_type_diagnostics,
        )
        server._initialize_handshake()

        middleware = FizzLSPMiddleware(server=server)
        return server, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "fizzlsp_dashboard", False):
            return None
        if middleware is None:
            return None
        server = middleware._server if hasattr(middleware, "_server") else middleware
        from enterprise_fizzbuzz.infrastructure.fizzlsp import FizzLSPDashboard
        return FizzLSPDashboard.render(server, width=60)
