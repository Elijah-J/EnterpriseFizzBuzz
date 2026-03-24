"""Feature descriptor for the Custom Bytecode VM (FBVM) subsystem."""

from __future__ import annotations

import time
from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class BytecodeVMFeature(FeatureDescriptor):
    name = "bytecode_vm"
    description = "Custom bytecode virtual machine for FizzBuzz evaluation with disassembly and tracing"
    middleware_priority = 0
    cli_flags = [
        ("--vm", {"action": "store_true", "default": False,
                  "help": "Execute FizzBuzz using the Custom Bytecode VM (FBVM) instead of Python — because direct execution was too efficient"}),
        ("--vm-disasm", {"action": "store_true", "default": False,
                         "help": "Display the FBVM disassembly listing of compiled bytecode before execution"}),
        ("--vm-trace", {"action": "store_true", "default": False,
                        "help": "Enable instruction-level execution tracing in the FBVM (log every fetch-decode-execute cycle)"}),
        ("--vm-dashboard", {"action": "store_true", "default": False,
                            "help": "Display the FBVM ASCII dashboard with register file, disassembly, and execution stats"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "vm", False),
            getattr(args, "vm_disasm", False),
            getattr(args, "vm_trace", False),
            getattr(args, "vm_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return self.is_enabled(args)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.bytecode_vm import (
            Disassembler,
            FizzBuzzVM,
            VMDashboard,
            compile_rules,
        )

        vm_rules = config.rules
        vm_trace = args.vm_trace or config.vm_trace_execution
        vm_optimize = config.vm_enable_optimizer

        vm_program, vm_compiler = compile_rules(
            vm_rules,
            enable_optimizer=vm_optimize,
            event_bus=None,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | FBVM: FizzBuzz Bytecode Virtual Machine ENABLED         |\n"
            f"  | Rules compiled: {len(vm_rules):<40}|\n"
            f"  | Instructions: {len(vm_program.instructions):<42}|\n"
            f"  | Optimized: {'Yes' if vm_program.optimized else 'No':<45}|\n"
            "  | Because Python was too efficient for modulo arithmetic. |\n"
            "  +---------------------------------------------------------+"
        )

        if args.vm_disasm:
            print()
            print(Disassembler.disassemble(vm_program))

        vm_instance = FizzBuzzVM(
            cycle_limit=config.vm_cycle_limit,
            trace_execution=vm_trace,
            register_count=config.vm_register_count,
            event_bus=None,
        )

        start = config.range_start
        end = config.range_end

        boot_time = time.perf_counter()
        vm_results_output = []

        for number in range(start, end + 1):
            result_str = vm_instance.execute(vm_program, number)
            vm_results_output.append(f"  {result_str}")

        wall_time_ms = (time.perf_counter() - boot_time) * 1000

        print()
        for line in vm_results_output:
            print(line)
        print()

        print(f"  FBVM evaluated {end - start + 1} numbers in {wall_time_ms:.2f}ms")
        print(f"  Average cycles per number: {vm_instance.state.cycles}")

        if vm_trace and vm_instance.execution_traces:
            print()
            print(VMDashboard.render_trace(
                vm_instance.execution_traces,
                width=config.vm_dashboard_width,
            ))

        if args.vm_dashboard:
            print()
            print(VMDashboard.render(
                vm_program,
                vm_instance,
                width=config.vm_dashboard_width,
                show_registers=config.vm_dashboard_show_registers,
                show_disassembly=config.vm_dashboard_show_disassembly,
            ))

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        return None, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
