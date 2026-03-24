"""Feature descriptor for the FizzBuzz Intellectual Property Office."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class IPOfficeFeature(FeatureDescriptor):
    name = "ip_office"
    description = "Intellectual Property Office with trademark, patent, copyright, and dispute resolution"
    middleware_priority = 132
    cli_flags = [
        ("--ip-office", {"action": "store_true", "default": False,
                         "help": "Enable the FizzBuzz Intellectual Property Office: trademark, patent, copyright, and dispute resolution"}),
        ("--trademark", {"type": str, "metavar": "LABEL", "default": None,
                         "help": "Apply for trademark registration of a FizzBuzz label (e.g. --trademark 'Wuzz')"}),
        ("--patent", {"type": str, "metavar": "DESCRIPTION", "default": None,
                      "help": "File a patent application for a FizzBuzz rule (e.g. --patent 'Divisibility by 7 yields Bazz')"}),
        ("--ip-dashboard", {"action": "store_true", "default": False,
                            "help": "Display the FizzBuzz Intellectual Property Office ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "ip_office", False),
            getattr(args, "trademark", None) is not None,
            getattr(args, "patent", None) is not None,
            getattr(args, "ip_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.ip_office import (
            CopyrightRegistry,
            IPDisputeTribunal,
            LicenseManager,
            PatentExaminer,
            TrademarkRegistry,
        )

        trademark_registry = TrademarkRegistry(
            similarity_threshold=config.ip_office_trademark_similarity_threshold,
            renewal_days=config.ip_office_trademark_renewal_days,
        )
        patent_examiner = PatentExaminer(
            novelty_threshold=config.ip_office_patent_novelty_threshold,
        )
        copyright_registry = CopyrightRegistry(
            originality_threshold=config.ip_office_copyright_originality_threshold,
        )
        license_manager = LicenseManager()
        tribunal = IPDisputeTribunal()

        service = {
            "trademark_registry": trademark_registry,
            "patent_examiner": patent_examiner,
            "copyright_registry": copyright_registry,
            "license_manager": license_manager,
            "tribunal": tribunal,
        }
        return service, None

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZBUZZ INTELLECTUAL PROPERTY OFFICE                    |\n"
            "  | Trademarks | Patents | Copyrights | Licenses | Disputes |\n"
            "  | Soundex + Metaphone | Kolmogorov | Levenshtein          |\n"
            '  | "Your modulo operation may be patented."                 |\n'
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "ip_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.ip_office import IPOfficeDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        return IPOfficeDashboard.render(
            width=config.ip_office_dashboard_width,
        )
