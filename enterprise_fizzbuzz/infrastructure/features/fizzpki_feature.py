"""Feature descriptor for FizzPKI Certificate Authority."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzPKIFeature(FeatureDescriptor):
    name = "fizzpki"
    description = "PKI with Root/Intermediate CA, X.509, ACME, CRL, OCSP, and certificate transparency"
    middleware_priority = 134
    cli_flags = [
        ("--fizzpki", {"action": "store_true", "default": False, "help": "Enable FizzPKI Certificate Authority"}),
        ("--fizzpki-issue", {"type": str, "default": None, "help": "Issue certificate for CN"}),
        ("--fizzpki-revoke", {"type": str, "default": None, "help": "Revoke certificate by serial"}),
        ("--fizzpki-list", {"action": "store_true", "default": False, "help": "List certificates"}),
        ("--fizzpki-crl", {"action": "store_true", "default": False, "help": "Generate CRL"}),
        ("--fizzpki-ocsp", {"type": str, "default": None, "help": "Query OCSP status"}),
        ("--fizzpki-acme", {"action": "store_true", "default": False, "help": "Enable ACME server"}),
        ("--fizzpki-renew", {"action": "store_true", "default": False, "help": "Scan for expiring certs"}),
        ("--fizzpki-inventory", {"action": "store_true", "default": False, "help": "Certificate inventory"}),
        ("--fizzpki-transparency", {"action": "store_true", "default": False, "help": "Transparency log"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzpki", False), getattr(args, "fizzpki_list", False),
                    getattr(args, "fizzpki_issue", None), getattr(args, "fizzpki_inventory", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzpki import FizzPKIMiddleware, create_fizzpki_subsystem
        ca, acme, dashboard, mw = create_fizzpki_subsystem(
            cert_validity_days=config.fizzpki_cert_validity_days,
            acme_enabled=config.fizzpki_acme_enabled,
            dashboard_width=config.fizzpki_dashboard_width,
        )
        return ca, mw

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzpki_list", False): parts.append(middleware.render_list())
        if getattr(args, "fizzpki_inventory", False): parts.append(middleware.render_inventory())
        if getattr(args, "fizzpki_transparency", False): parts.append(middleware.render_transparency())
        if getattr(args, "fizzpki", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
