"""Feature descriptor for the FizzELF binary format generator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ELFFormatFeature(FeatureDescriptor):
    name = "elf_format"
    description = "Standards-compliant ELF64 binary generator for FizzBuzz evaluation logic"
    middleware_priority = 132
    cli_flags = [
        ("--elf", {"action": "store_true", "default": False,
                   "help": "Generate a standards-compliant ELF64 binary containing FizzBuzz evaluation logic"}),
        ("--elf-output", {"type": str, "default": None, "metavar": "FILE",
                          "help": "Write the generated ELF binary to the specified file path"}),
        ("--readelf", {"action": "store_true", "default": False,
                       "help": "Display readelf-style ASCII output for the generated ELF binary"}),
        ("--elf-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzELF ASCII dashboard with section map, symbols, and segment layout"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "elf", False),
            getattr(args, "elf_output", None) is not None,
            getattr(args, "readelf", False),
            getattr(args, "elf_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.elf_format import (
            ELFMiddleware,
        )

        elf_middleware = ELFMiddleware(
            rules=list(config.rules),
            start=config.range_start,
            end=config.range_end,
            output_path=getattr(args, "elf_output", None),
            enable_readelf=getattr(args, "readelf", False),
            enable_dashboard=getattr(args, "elf_dashboard", False),
            event_bus=event_bus,
        )

        return elf_middleware, elf_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZELF: ELF BINARY FORMAT GENERATOR ENABLED            |\n"
            "  |   Format: ELF64 Little-Endian                           |\n"
            "  |   Machine: EM_FIZZ (0xFB)                               |\n"
            "  |   Sections: .text, .data, .fizz, .note.fizzbuzz         |\n"
            "  |   Every evaluation becomes a loadable binary.           |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None or getattr(middleware, "parsed", None) is None:
            return None

        from enterprise_fizzbuzz.infrastructure.elf_format import (
            ELFDashboard,
            ReadELF,
        )

        parts = []
        parsed_elf = middleware.parsed

        if getattr(args, "readelf", False):
            parts.append(ReadELF.format_all(parsed_elf))

        if getattr(args, "elf_dashboard", False):
            parts.append(ELFDashboard.render(parsed_elf))

        if getattr(args, "elf_output", None):
            parts.append(
                f"  ELF binary written to: {args.elf_output}\n"
                f"  Size: {len(middleware.elf_bytes)} bytes"
            )

        if (getattr(args, "elf", False)
                and not getattr(args, "readelf", False)
                and not getattr(args, "elf_dashboard", False)):
            parts.append(
                f"  ELF binary generated: {len(middleware.elf_bytes)} bytes, "
                f"{parsed_elf.header.e_shnum} sections, "
                f"{len(parsed_elf.symbols)} symbols"
            )

        return "\n".join(parts) if parts else None
