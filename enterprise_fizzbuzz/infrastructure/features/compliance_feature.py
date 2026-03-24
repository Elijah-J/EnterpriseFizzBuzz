"""Feature descriptor for the SOX/GDPR/HIPAA Compliance framework."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ComplianceFeature(FeatureDescriptor):
    name = "compliance"
    description = "SOX/GDPR/HIPAA compliance framework for regulatory FizzBuzz evaluation"
    middleware_priority = 70
    cli_flags = [
        ("--compliance", {"action": "store_true",
                          "help": "Enable SOX/GDPR/HIPAA compliance framework for FizzBuzz evaluation"}),
        ("--gdpr-erase", {"type": int, "metavar": "NUMBER", "default": None,
                          "help": "Submit a GDPR right-to-erasure request for the specified number (triggers THE COMPLIANCE PARADOX)"}),
        ("--sox-audit", {"action": "store_true",
                         "help": "Display the SOX segregation of duties audit trail after execution"}),
        ("--hipaa-check", {"action": "store_true",
                           "help": "Display HIPAA PHI access log and encryption statistics after execution"}),
        ("--compliance-report", {"action": "store_true",
                                 "help": "Generate a comprehensive compliance report after execution"}),
        ("--compliance-dashboard", {"action": "store_true",
                                    "help": "Display the compliance & regulatory ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "compliance", False),
            getattr(args, "gdpr_erase", None) is not None,
            getattr(args, "compliance_dashboard", False),
            getattr(args, "compliance_report", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.compliance import (
            ComplianceFramework,
            ComplianceMiddleware,
            GDPRController,
            HIPAAGuard,
            SOXAuditor,
        )

        sox_auditor = SOXAuditor(
            personnel_roster=config.compliance_sox_personnel_roster,
            strict_mode=config.compliance_sox_segregation_strict,
            event_bus=event_bus,
        ) if config.compliance_sox_enabled else None

        gdpr_controller = GDPRController(
            auto_consent=config.compliance_gdpr_auto_consent,
            erasure_enabled=config.compliance_gdpr_erasure_enabled,
            event_bus=event_bus,
        ) if config.compliance_gdpr_enabled else None

        hipaa_guard = HIPAAGuard(
            minimum_necessary_level=config.compliance_hipaa_minimum_necessary_level,
            encryption_algorithm=config.compliance_hipaa_encryption_algorithm,
            event_bus=event_bus,
        ) if config.compliance_hipaa_enabled else None

        framework = ComplianceFramework(
            sox_auditor=sox_auditor,
            gdpr_controller=gdpr_controller,
            hipaa_guard=hipaa_guard,
            event_bus=event_bus,
            bob_stress_level=config.compliance_officer_stress_level,
        )

        middleware = ComplianceMiddleware(
            compliance_framework=framework,
            event_bus=event_bus,
        )

        return framework, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | COMPLIANCE: SOX/GDPR/HIPAA Framework ENABLED            |\n"
            "  | Segregation of duties: ENFORCED (no dual FizzBuzz roles)|\n"
            "  | GDPR consent: AUTO-GRANTED (for convenience)            |\n"
            "  | HIPAA encryption: MILITARY-GRADE BASE64                 |\n"
            "  | Compliance Officer: Bob McFizzington (UNAVAILABLE)      |\n"
            f"  | Bob's stress level: {f'{config.compliance_officer_stress_level:.1f}%':<36}|\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.compliance import ComplianceDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        framework = middleware._framework
        parts = []
        if getattr(args, "compliance_dashboard", False):
            parts.append(ComplianceDashboard.render(framework, width=config.compliance_dashboard_width))
        if getattr(args, "compliance_report", False):
            parts.append(ComplianceDashboard.render_report(framework))
        if getattr(args, "sox_audit", False):
            posture = framework.get_posture_summary()
            sox_trail = posture.get("sox_stats", [])
            if sox_trail:
                lines = [
                    "  +---------------------------------------------------------+",
                    "  | SOX SEGREGATION OF DUTIES AUDIT TRAIL                   |",
                    "  +---------------------------------------------------------+",
                ]
                for entry in sox_trail[-10:]:
                    assignments = entry.get("assignments", {})
                    segregated = entry.get("segregation_satisfied", False)
                    status = "OK" if segregated else "VIOLATION"
                    num_val = entry.get("number", "?")
                    sox_line = f"Number {num_val:>5} [{status}]"
                    lines.append(f"  | {sox_line:<57}|")
                    for role, person in assignments.items():
                        person_name = person.get("name", "?")
                        role_line = f"  {role}: {person_name}"
                        lines.append(f"  | {role_line:<57}|")
                if len(sox_trail) > 10:
                    more_line = f"... and {len(sox_trail) - 10} more entries"
                    lines.append(f"  | {more_line:<57}|")
                lines.append("  +---------------------------------------------------------+")
                parts.append("\n".join(lines))
            else:
                parts.append("  No SOX audit trail entries recorded.")
        if getattr(args, "hipaa_check", False):
            posture = framework.get_posture_summary()
            hipaa_stats = posture.get("hipaa_stats", {})
            if hipaa_stats:
                parts.append(
                    "  +---------------------------------------------------------+\n"
                    "  | HIPAA PHI ACCESS LOG & ENCRYPTION STATISTICS            |\n"
                    "  +---------------------------------------------------------+\n"
                    f"  | PHI Encryptions:    {hipaa_stats.get('phi_encryptions', 0):<36}|\n"
                    f"  | PHI Redactions:     {hipaa_stats.get('phi_redactions', 0):<36}|\n"
                    f"  | PHI Access Events:  {hipaa_stats.get('phi_access_events', 0):<36}|\n"
                    f"  | Algorithm:          {hipaa_stats.get('encryption_algorithm', 'N/A'):<36}|\n"
                    f"  | Actual Security:    {hipaa_stats.get('actual_security_provided', 'None'):<36}|\n"
                    "  +---------------------------------------------------------+"
                )
            else:
                parts.append("  No HIPAA statistics recorded.")
        return "\n".join(parts) if parts else None
