"""Feature descriptor for the FizzPM package manager."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class PackageManagerFeature(FeatureDescriptor):
    name = "package_manager"
    description = "SAT-based dependency resolution package manager for the FizzBuzz ecosystem"
    middleware_priority = 48
    cli_flags = [
        ("--fizzpm", {"action": "store_true", "default": False,
                      "help": "Enable FizzPM Package Manager: SAT-based dependency resolution for the FizzBuzz ecosystem"}),
        ("--fizzpm-install", {"type": str, "metavar": "PACKAGE", "default": None,
                              "help": "Install a FizzPM package and resolve dependencies via DPLL SAT solver (e.g. --fizzpm-install fizzbuzz-enterprise)"}),
        ("--fizzpm-audit", {"action": "store_true", "default": False,
                            "help": "Run a vulnerability audit against all installed/available FizzPM packages"}),
        ("--fizzpm-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the FizzPM Package Manager ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzpm", False),
            getattr(args, "fizzpm_install", None) is not None,
            getattr(args, "fizzpm_audit", False),
            getattr(args, "fizzpm_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.package_manager import FizzPMManager

        manager = FizzPMManager(
            audit_on_install=config.fizzpm_audit_on_install,
            lockfile_path=config.fizzpm_lockfile_path,
        )

        if getattr(args, "fizzpm_install", None):
            result = manager.install(args.fizzpm_install)
            print(manager.render_install_summary(result))
            if config.fizzpm_audit_on_install and manager.vulnerabilities:
                print(manager.render_audit_report())
        else:
            for pkg_name in config.fizzpm_default_packages:
                manager.install(pkg_name)

        if getattr(args, "fizzpm_audit", False):
            manager.audit()
            print(manager.render_audit_report())

        return manager, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "fizzpm_dashboard", False):
            return None
        # middleware holds the manager (stored as service in create)
        manager = middleware
        if manager is None:
            return None
        from enterprise_fizzbuzz.infrastructure.package_manager import FizzPMDashboard
        return manager.render_dashboard(width=60)
