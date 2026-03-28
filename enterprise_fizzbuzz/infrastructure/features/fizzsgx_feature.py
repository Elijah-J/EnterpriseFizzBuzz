"""Feature descriptor for the FizzSGX Intel SGX Enclave Simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzsgxFeature(FeatureDescriptor):
    name = "fizzsgx"
    description = "Intel SGX enclave simulator with ECALL/OCALL bridge, sealed storage, remote attestation, and memory encryption engine for secure FizzBuzz classification"
    middleware_priority = 249
    cli_flags = [
        ("--sgx", {"action": "store_true", "default": False,
                   "help": "Enable the FizzSGX enclave simulator"}),
        ("--sgx-enclave-size", {"type": int, "default": 67108864, "metavar": "BYTES",
                                "help": "Maximum enclave memory size in bytes"}),
        ("--sgx-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzSGX ASCII dashboard with enclave state"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "sgx", False),
            getattr(args, "sgx_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzsgx import create_fizzsgx_subsystem

        enclave_size = getattr(args, "sgx_enclave_size", 67108864)
        platform, middleware = create_fizzsgx_subsystem(enclave_size=enclave_size)
        return platform, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "sgx_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzSGX not enabled. Use --sgx to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzsgx import SGXDashboard

        platform = middleware.platform if hasattr(middleware, "platform") else None
        if platform is not None:
            return SGXDashboard.render(platform)
        return None
