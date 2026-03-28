"""Feature descriptor for the FizzTPM Trusted Platform Module 2.0 simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizztpmFeature(FeatureDescriptor):
    name = "fizztpm"
    description = "TPM 2.0 simulator with PCR banks, seal/unseal, quote/attest, NVRAM storage, and hardware RNG for trusted FizzBuzz classification"
    middleware_priority = 242
    cli_flags = [
        ("--tpm", {"action": "store_true", "default": False,
                   "help": "Enable the FizzTPM Trusted Platform Module simulator"}),
        ("--tpm-algorithm", {"type": str, "default": "sha256", "metavar": "ALG",
                             "help": "Hash algorithm for PCR bank (sha256, sha384, sha512)"}),
        ("--tpm-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzTPM ASCII dashboard with PCR state"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "tpm", False),
            getattr(args, "tpm_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizztpm import (
            PCRAlgorithm,
            create_fizztpm_subsystem,
        )

        alg_str = getattr(args, "tpm_algorithm", "sha256")
        alg = PCRAlgorithm.SHA256
        if alg_str == "sha384":
            alg = PCRAlgorithm.SHA384
        elif alg_str == "sha512":
            alg = PCRAlgorithm.SHA512

        device, middleware = create_fizztpm_subsystem(algorithm=alg)
        return device, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "tpm_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzTPM not enabled. Use --tpm to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizztpm import TPMDashboard

        device = middleware.device if hasattr(middleware, "device") else None
        if device is not None:
            return TPMDashboard.render(device)
        return None
