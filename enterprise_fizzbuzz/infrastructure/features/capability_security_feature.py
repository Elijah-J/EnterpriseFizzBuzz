"""Feature descriptor for the FizzCap capability-based security model."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class CapabilitySecurityFeature(FeatureDescriptor):
    name = "capability_security"
    description = "Unforgeable object capabilities with HMAC-SHA256 signatures and confused deputy prevention"
    middleware_priority = 134
    cli_flags = [
        ("--capabilities", {"action": "store_true", "default": False,
                            "help": "Enable FizzCap capability-based security: unforgeable object capabilities with HMAC-SHA256 signatures"}),
        ("--cap-mode", {"type": str, "choices": ["native", "bridge", "audit-only"],
                        "default": None,
                        "help": "Capability enforcement mode: native (strict), bridge (auto-issue for legacy), audit-only (log but allow)"}),
        ("--cap-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzCap ASCII dashboard with active capabilities, delegation graph, and guard activity"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "capabilities", False),
            getattr(args, "cap_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.capability_security import (
            CapabilityManager,
            Operation,
        )

        cap_mode = getattr(args, "cap_mode", None) or config.capability_security_mode
        cap_manager = CapabilityManager(
            secret_key=config.capability_security_secret_key,
            mode=cap_mode,
        )

        root_cap = cap_manager.create_root_capability(
            resource=config.capability_security_default_resource,
            operations=frozenset({
                Operation.READ,
                Operation.WRITE,
                Operation.EXECUTE,
                Operation.DELEGATE,
            }),
            holder="session:root",
            constraints={"session_id": str(uuid.uuid4())},
        )

        engine_cap = cap_manager.delegate(
            parent=root_cap,
            new_operations=frozenset({Operation.READ, Operation.EXECUTE}),
            new_holder="subsystem:rule_engine",
            additional_constraints={"scope": "evaluation"},
        )

        formatter_cap = cap_manager.delegate(
            parent=engine_cap,
            new_operations=frozenset({Operation.READ}),
            new_holder="subsystem:formatter",
            additional_constraints={"scope": "evaluation", "output_only": "true"},
        )

        cap_manager.check_access(
            root_cap,
            config.capability_security_default_resource,
            Operation.EXECUTE,
        )
        cap_manager.check_access(
            engine_cap,
            config.capability_security_default_resource,
            Operation.EXECUTE,
        )
        cap_manager.check_access(
            formatter_cap,
            config.capability_security_default_resource,
            Operation.READ,
        )

        return cap_manager, None

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "\n  +---------------------------------------------------------+\n"
            "  | FizzCap Capability-Based Security Model                 |\n"
            "  | Unforgeable object capabilities with HMAC-SHA256        |\n"
            "  | Because ambient authority was never good enough.        |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "cap_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.capability_security import CapabilityDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        # middleware is None for this feature; service (cap_manager) was returned
        # The render path requires the cap_manager which is the service object
        return None
