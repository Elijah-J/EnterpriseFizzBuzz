"""Feature descriptor for the FizzForensics digital forensics engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzForensicsFeature(FeatureDescriptor):
    name = "fizzforensics"
    description = "Digital forensics with disk image analysis, file carving, hash verification, timeline reconstruction, and chain of custody"
    middleware_priority = 283
    cli_flags = [
        ("--fizzforensics", {"action": "store_true", "default": False,
                             "help": "Enable FizzForensics: forensic analysis of FizzBuzz evaluation records"}),
        ("--fizzforensics-seed", {"type": int, "metavar": "SEED", "default": None,
                                   "help": "Random seed for forensic simulation reproducibility"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzforensics", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzforensics import (
            ForensicsEngine,
            ForensicsMiddleware,
        )

        seed = getattr(args, "fizzforensics_seed", None) or config.fizzforensics_seed
        middleware = ForensicsMiddleware(seed=seed)
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZFORENSICS: DIGITAL FORENSICS ENGINE                  |\n"
            "  |   Disk image analysis with sector hashing               |\n"
            "  |   File carving from unallocated space                    |\n"
            "  |   Chain of custody with cryptographic verification       |\n"
            "  +---------------------------------------------------------+"
        )
