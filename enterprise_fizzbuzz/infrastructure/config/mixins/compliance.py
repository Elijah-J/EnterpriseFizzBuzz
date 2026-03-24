"""Compliance & Regulatory Framework configuration properties"""

from __future__ import annotations

from typing import Any


class ComplianceConfigMixin:
    """Configuration properties for the compliance subsystem."""

    # ----------------------------------------------------------------
    # Compliance & Regulatory Framework configuration properties
    # ----------------------------------------------------------------

    @property
    def compliance_enabled(self) -> bool:
        """Whether the Compliance & Regulatory Framework is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("enabled", False)

    @property
    def compliance_sox_enabled(self) -> bool:
        """Whether SOX compliance is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("sox", {}).get("enabled", True)

    @property
    def compliance_sox_segregation_strict(self) -> bool:
        """Whether SOX strict segregation of duties is enforced."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("sox", {}).get("segregation_strict", True)

    @property
    def compliance_sox_personnel_roster(self) -> list[dict[str, str]]:
        """The virtual personnel roster for SOX duty assignment."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("sox", {}).get("personnel_roster", [])

    @property
    def compliance_gdpr_enabled(self) -> bool:
        """Whether GDPR compliance is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("gdpr", {}).get("enabled", True)

    @property
    def compliance_gdpr_auto_consent(self) -> bool:
        """Whether GDPR consent is auto-granted."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("gdpr", {}).get("auto_consent", True)

    @property
    def compliance_gdpr_erasure_enabled(self) -> bool:
        """Whether GDPR right-to-erasure is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("gdpr", {}).get("erasure_enabled", True)

    @property
    def compliance_hipaa_enabled(self) -> bool:
        """Whether HIPAA compliance is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("hipaa", {}).get("enabled", True)

    @property
    def compliance_hipaa_minimum_necessary_level(self) -> str:
        """The default HIPAA minimum necessary access level."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("hipaa", {}).get("minimum_necessary_level", "OPERATIONS")

    @property
    def compliance_hipaa_encryption_algorithm(self) -> str:
        """The HIPAA 'encryption' algorithm (military-grade base64)."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("hipaa", {}).get("encryption_algorithm", "military_grade_base64")

    @property
    def compliance_officer_name(self) -> str:
        """The name of the Chief Compliance Officer."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("compliance_officer", {}).get("name", "Bob McFizzington")

    @property
    def compliance_officer_stress_level(self) -> float:
        """Bob McFizzington's current stress level (percentage)."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("compliance_officer", {}).get("stress_level", 94.7)

    @property
    def compliance_officer_available(self) -> bool:
        """Whether the compliance officer is available (spoiler: no)."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("compliance_officer", {}).get("available", False)

    @property
    def compliance_officer_certifications(self) -> list[str]:
        """The compliance officer's certifications."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("compliance_officer", {}).get("certifications", [])

    @property
    def compliance_dashboard_width(self) -> int:
        """ASCII dashboard width for compliance dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("compliance", {}).get("dashboard", {}).get("width", 60)

