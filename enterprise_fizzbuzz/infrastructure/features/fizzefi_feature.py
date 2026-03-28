"""Feature descriptor for the FizzEFI UEFI Firmware Interface."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzefiFeature(FeatureDescriptor):
    name = "fizzefi"
    description = "UEFI firmware interface with boot services, runtime services, variable store, boot manager, driver loading, and secure boot chain verification for trusted FizzBuzz platform initialization"
    middleware_priority = 246
    cli_flags = [
        ("--efi", {"action": "store_true", "default": False,
                   "help": "Enable the FizzEFI UEFI firmware interface"}),
        ("--efi-secure-boot", {"action": "store_true", "default": False,
                               "help": "Enable UEFI Secure Boot verification"}),
        ("--efi-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzEFI ASCII dashboard with boot state"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "efi", False),
            getattr(args, "efi_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzefi import create_fizzefi_subsystem

        secure_boot = getattr(args, "efi_secure_boot", False)
        firmware, middleware = create_fizzefi_subsystem(secure_boot=secure_boot)
        return firmware, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "efi_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzEFI not enabled. Use --efi to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzefi import EFIDashboard

        firmware = middleware.firmware if hasattr(middleware, "firmware") else None
        if firmware is not None:
            return EFIDashboard.render(firmware)
        return None
