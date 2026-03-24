"""Feature descriptor for the FizzWASM WebAssembly runtime."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzWasmFeature(FeatureDescriptor):
    name = "fizzwasm"
    description = "WebAssembly 2.0 runtime with binary decoder, validator, stack-machine interpreter, WASI Preview 1, fuel metering, and Component Model"
    middleware_priority = 118
    cli_flags = [
        ("--fizzwasm", {"action": "store_true",
                        "help": "Enable FizzWASM: WebAssembly 2.0 runtime with WASI and Component Model"}),
        ("--fizzwasm-run", {"type": str, "default": None, "metavar": "FILE",
                            "help": "Decode, validate, and execute a .wasm module"}),
        ("--fizzwasm-validate", {"type": str, "default": None, "metavar": "FILE",
                                  "help": "Validate a .wasm module without executing"}),
        ("--fizzwasm-inspect", {"type": str, "default": None, "metavar": "FILE",
                                 "help": "Display module sections (types, imports, exports, memory, tables)"}),
        ("--fizzwasm-fuel", {"type": int, "default": None, "metavar": "N",
                              "help": "Set fuel budget for execution (default 10000000)"}),
        ("--fizzwasm-wasi-stdin", {"type": str, "default": None, "metavar": "FILE",
                                    "help": "Redirect WASI stdin from file"}),
        ("--fizzwasm-wasi-env", {"type": str, "action": "append", "default": None, "metavar": "KEY=VALUE",
                                  "help": "Add environment variable to WASI (repeatable)"}),
        ("--fizzwasm-wasi-args", {"type": str, "nargs": "*", "default": None, "metavar": "ARG",
                                   "help": "Set command-line arguments for WASI args_get"}),
        ("--fizzwasm-compile-and-run", {"action": "store_true",
                                         "help": "Compile current FizzBuzz config to WASM and execute via FizzWASM"}),
        ("--fizzwasm-component", {"type": str, "default": None, "metavar": "WIT_FILE",
                                   "help": "Load a WIT interface definition for Component Model linking"}),
        ("--fizzwasm-no-validate", {"action": "store_true",
                                     "help": "Skip validation for pre-validated modules"}),
        ("--fizzwasm-fuel-cost-model", {"type": str, "default": None,
                                         "choices": ["uniform", "weighted", "custom"],
                                         "help": "Select fuel cost model"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzwasm", False),
            getattr(args, "fizzwasm_run", None),
            getattr(args, "fizzwasm_validate", None),
            getattr(args, "fizzwasm_inspect", None),
            getattr(args, "fizzwasm_compile_and_run", False),
            getattr(args, "fizzwasm_component", None),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzwasm import (
            create_fizzwasm_subsystem,
        )

        wasi_env = {}
        if getattr(args, "fizzwasm_wasi_env", None):
            for pair in args.fizzwasm_wasi_env:
                key, _, value = pair.partition("=")
                wasi_env[key] = value

        runtime, middleware = create_fizzwasm_subsystem(
            fuel_budget=getattr(args, "fizzwasm_fuel", None) or config.fizzwasm_fuel_budget,
            fuel_cost_model=getattr(args, "fizzwasm_fuel_cost_model", None) or config.fizzwasm_fuel_cost_model,
            wasi_stdin=getattr(args, "fizzwasm_wasi_stdin", None),
            wasi_args=getattr(args, "fizzwasm_wasi_args", None),
            wasi_env=wasi_env or None,
            dashboard_width=config.fizzwasm_dashboard_width,
            event_bus=event_bus,
        )

        return runtime, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZWASM: WEBASSEMBLY 2.0 RUNTIME                      |\n"
            "  | Binary decoder | Validator | Stack-machine interpreter |\n"
            "  | WASI Preview 1 | Fuel metering | Component Model       |\n"
            "  | WebAssembly 2.0 specification compliant                |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None

        parts = []

        if getattr(args, "fizzwasm_inspect", None):
            parts.append(middleware.render_inspection())
        if getattr(args, "fizzwasm_run", None) or getattr(args, "fizzwasm_compile_and_run", False):
            parts.append(middleware.render_execution())
            parts.append(middleware.render_wasi_output())
        if getattr(args, "fizzwasm", False) and not parts:
            parts.append(middleware.render_dashboard())

        return "\n".join(parts) if parts else None
