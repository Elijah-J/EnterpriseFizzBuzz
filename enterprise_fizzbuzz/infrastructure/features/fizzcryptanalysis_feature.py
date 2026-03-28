"""Feature descriptor for the FizzCryptanalysis cipher breaking engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzCryptanalysisFeature(FeatureDescriptor):
    name = "fizzcryptanalysis"
    description = "Cipher breaking with frequency analysis, Kasiski examination, index of coincidence, and differential cryptanalysis"
    middleware_priority = 289
    cli_flags = [
        ("--fizzcryptanalysis", {"action": "store_true", "default": False,
                                  "help": "Enable FizzCryptanalysis: automated cipher breaking of encrypted FizzBuzz output"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzcryptanalysis", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcryptanalysis import (
            CryptanalysisEngine,
            CryptanalysisMiddleware,
        )

        middleware = CryptanalysisMiddleware()
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZCRYPTANALYSIS: CIPHER BREAKING ENGINE                |\n"
            "  |   Frequency analysis and Caesar cipher recovery          |\n"
            "  |   Kasiski examination for polyalphabetic key length      |\n"
            "  |   Differential cryptanalysis of SPN ciphers              |\n"
            "  +---------------------------------------------------------+"
        )
