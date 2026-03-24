"""Feature descriptor for the FizzProof proof certificate generator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ProofCertificatesFeature(FeatureDescriptor):
    name = "proof_certificates"
    description = "Calculus of Constructions proof certificates with de Bruijn criterion type-checking and LaTeX export"
    middleware_priority = 137
    cli_flags = [
        ("--proof-cert", {"action": "store_true", "default": False,
                          "help": "Enable FizzProof: generate Calculus of Constructions proof certificates for every FizzBuzz classification"}),
        ("--proof-latex", {"action": "store_true", "default": False,
                           "help": "Generate LaTeX documents for proof certificates (bussproofs natural deduction, BibTeX citations)"}),
        ("--proof-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzProof ASCII dashboard with certificate inventory, verification metrics, and kernel status"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "proof_cert", False),
            getattr(args, "proof_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.proof_certificates import (
            CertificateGenerator,
            CertificateRegistry,
            LaTeXExporter,
            ProofChecker,
            ProofMiddleware,
        )

        checker = ProofChecker()
        generator = CertificateGenerator(checker=checker)
        registry = CertificateRegistry()
        exporter = LaTeXExporter()
        enable_latex = getattr(args, "proof_latex", False) or config.proof_cert_latex

        middleware = ProofMiddleware(
            generator=generator,
            registry=registry,
            exporter=exporter,
            enable_latex=enable_latex,
        )

        service = {"checker": checker, "registry": registry}
        return service, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        enable_latex = getattr(args, "proof_latex", False) or config.proof_cert_latex
        return (
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZPROOF PROOF CERTIFICATE GENERATOR ENABLED           |\n"
            "  |   Calculus of Constructions trusted kernel active        |\n"
            "  |   de Bruijn criterion type-checker initialized           |\n"
            "  |   Every classification receives a formal proof           |\n"
            + ("  |   LaTeX export with bussproofs enabled                   |\n" if enable_latex else "")
            + "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "proof_dashboard", False) and hasattr(middleware, "registry"):
            from enterprise_fizzbuzz.infrastructure.proof_certificates import ProofDashboard
            from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
            config = ConfigurationManager()
            parts.append(ProofDashboard.render(
                registry=middleware.registry,
                checker=middleware.generator.checker if hasattr(middleware, "generator") else None,
                width=config.proof_cert_dashboard_width,
            ))

        if getattr(args, "proof_latex", False) and hasattr(middleware, "registry"):
            certs = middleware.registry.all_certificates()
            latex_count = sum(1 for c in certs if c.latex_source)
            if latex_count > 0:
                parts.append(
                    f"\n  FizzProof: {latex_count} LaTeX proof certificate(s) generated.\n"
                    "  Use --verbose to see LaTeX source in output metadata.\n"
                )

        return "\n".join(parts) if parts else None
