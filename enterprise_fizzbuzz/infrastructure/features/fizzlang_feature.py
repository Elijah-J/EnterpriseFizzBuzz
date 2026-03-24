"""Feature descriptor for the FizzLang domain-specific language."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzLangFeature(FeatureDescriptor):
    name = "fizzlang"
    description = "FizzLang DSL with compiler, interpreter, REPL, and Language Complexity Index"
    middleware_priority = 58
    cli_flags = [
        ("--fizzlang", {"type": str, "metavar": "PROGRAM", "default": None,
                        "help": 'Execute a FizzLang program inline (e.g., --fizzlang \'rule fizz when n %% 3 == 0 emit "Fizz"\\nevaluate 1 to 20\')'}),
        ("--fizzlang-file", {"type": str, "metavar": "FILE", "default": None,
                             "help": "Execute a FizzLang program from a .fizz file"}),
        ("--fizzlang-repl", {"action": "store_true",
                             "help": "Start the FizzLang interactive REPL"}),
        ("--fizzlang-dashboard", {"action": "store_true",
                                  "help": "Display the FizzLang ASCII dashboard with source stats and Language Complexity Index"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzlang", None) is not None,
            getattr(args, "fizzlang_file", None) is not None,
            getattr(args, "fizzlang_repl", False),
            getattr(args, "fizzlang_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzlang", None) is not None,
            getattr(args, "fizzlang_file", None) is not None,
            getattr(args, "fizzlang_repl", False),
        ])

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.fizzlang import (
            FizzLangDashboard,
            FizzLangREPL,
            Interpreter,
            compile_program,
            run_program,
        )

        if getattr(args, "fizzlang_repl", False):
            repl = FizzLangREPL(
                prompt=config.fizzlang_repl_prompt,
                show_tokens=config.fizzlang_repl_show_tokens,
                show_ast=config.fizzlang_repl_show_ast,
                stdlib_enabled=config.fizzlang_stdlib_enabled,
            )
            repl.run()
            return 0

        source = None
        if getattr(args, "fizzlang_file", None):
            try:
                with open(args.fizzlang_file, "r") as f:
                    source = f.read()
            except FileNotFoundError:
                print(f"\n  FizzLang file not found: {args.fizzlang_file}\n")
                return 1
        elif getattr(args, "fizzlang", None):
            source = args.fizzlang

        if source is not None:
            try:
                program = compile_program(
                    source,
                    strict_type_checking=config.fizzlang_strict_type_checking,
                    max_program_length=config.fizzlang_max_program_length,
                )
                interpreter = Interpreter(stdlib_enabled=config.fizzlang_stdlib_enabled)
                result = interpreter.execute(program)
                print(run_program(source))

                if getattr(args, "fizzlang_dashboard", False):
                    print(FizzLangDashboard.render(
                        program,
                        interpreter=interpreter,
                        width=config.fizzlang_dashboard_width,
                        show_source_stats=config.fizzlang_dashboard_show_source_stats,
                        show_complexity_index=config.fizzlang_dashboard_show_complexity_index,
                    ))
            except Exception as e:
                print(f"\n  FizzLang error: {e}\n")
                return 1

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        return None, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
