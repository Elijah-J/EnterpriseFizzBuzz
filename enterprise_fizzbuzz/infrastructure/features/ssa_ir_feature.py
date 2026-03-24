"""Feature descriptor for the FizzIR LLVM-inspired SSA intermediate representation."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class SSAIRFeature(FeatureDescriptor):
    name = "ssa_ir"
    description = "LLVM-style SSA intermediate representation with Cytron construction and 8 optimization passes"
    middleware_priority = 136
    cli_flags = [
        ("--ir", {"action": "store_true", "default": False,
                  "help": "Enable FizzIR: compile FizzBuzz rules to LLVM-style SSA IR and interpret the result"}),
        ("--ir-optimize", {"action": "store_true", "default": False,
                           "help": "Run the 8-pass optimization pipeline on generated IR "
                                   "(constant propagation, DCE, CSE, instruction combining, "
                                   "CFG simplification, LICM, strength reduction, inlining)"}),
        ("--ir-print", {"action": "store_true", "default": False,
                        "help": "Print the LLVM-style textual IR representation to stdout"}),
        ("--ir-dashboard", {"action": "store_true", "default": False,
                            "help": "Display the FizzIR ASCII dashboard with block counts, instruction counts, and optimization statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "ir", False),
            getattr(args, "ir_optimize", False),
            getattr(args, "ir_print", False),
            getattr(args, "ir_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.ssa_ir import IRMiddleware

        ir_rules = [(r.divisor, r.label) for r in config.rules]
        ir_do_optimize = getattr(args, "ir_optimize", False) or config.ir_optimize
        ir_do_print = getattr(args, "ir_print", False) or config.ir_print

        middleware = IRMiddleware(
            rules=ir_rules,
            optimize=ir_do_optimize,
            print_ir=ir_do_print,
            dashboard=getattr(args, "ir_dashboard", False),
        )

        return None, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZIR: SSA INTERMEDIATE REPRESENTATION ENABLED         |\n"
            "  | LLVM-style IR | Cytron SSA | 8 optimization passes      |\n"
            "  | Opcodes: srem, icmp, br, phi, ret, select               |\n"
            '  | "Every modulo deserves a dominator tree."               |\n'
            "  | n % 3 has never been this well-optimized.               |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "ir_dashboard", False):
            return None
        if middleware.module is None:
            return None
        from enterprise_fizzbuzz.infrastructure.ssa_ir import IRDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        return IRDashboard.render(
            module=middleware.module,
            pass_results=middleware.pass_results,
            pre_opt_instructions=middleware.pre_opt_instructions,
            pre_opt_blocks=middleware.pre_opt_blocks,
            width=config.ir_dashboard_width,
        )
