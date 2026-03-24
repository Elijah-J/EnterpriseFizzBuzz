"""Feature descriptor for the Cross-Compiler subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class CrossCompilerFeature(FeatureDescriptor):
    name = "cross_compiler"
    description = "Cross-compile FizzBuzz rules to C, Rust, or WebAssembly Text Format"
    middleware_priority = 0
    cli_flags = [
        ("--compile-to", {"type": str, "choices": ["c", "rust", "wat"], "default": None,
                          "metavar": "TARGET",
                          "help": "Cross-compile FizzBuzz rules to a target language (c | rust | wat)"}),
        ("--compile-ir", {"action": "store_true", "default": False,
                          "help": "Display the cross-compiler Intermediate Representation (IR) without code generation"}),
        ("--compile-verify", {"action": "store_true", "default": False,
                              "help": "Run round-trip verification after cross-compilation (enabled by default with --compile-to)"}),
        ("--compile-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the Cross-Compiler ASCII dashboard with overhead metrics and enterprise analysis"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            bool(getattr(args, "compile_to", None)),
            getattr(args, "compile_ir", False),
            getattr(args, "compile_verify", False),
            getattr(args, "compile_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return bool(getattr(args, "compile_to", None)) or getattr(args, "compile_ir", False)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.cross_compiler import CrossCompiler

        cc = CrossCompiler(
            config.rules,
            emit_comments=config.cross_compiler_emit_comments,
            verify=config.cross_compiler_verify_round_trip or getattr(args, "compile_verify", False),
            verification_range_end=config.cross_compiler_verification_range_end,
            dashboard_width=config.cross_compiler_dashboard_width,
            dashboard_show_ir=config.cross_compiler_dashboard_show_ir,
        )

        if args.compile_ir:
            ir = cc.compile_ir_only()
            print(ir.dump())
            return 0

        result = cc.compile(args.compile_to)
        print(result.generated_code)

        if getattr(args, "compile_dashboard", False):
            print()
            print(cc.render_dashboard(result))

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        return None, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
