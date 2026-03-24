"""Formal Verification & Proof System properties"""

from __future__ import annotations

from typing import Any


class FormalVerificationConfigMixin:
    """Configuration properties for the formal verification subsystem."""

    # ----------------------------------------------------------------
    # Formal Verification & Proof System properties
    # ----------------------------------------------------------------

    @property
    def formal_verification_enabled(self) -> bool:
        """Whether the Formal Verification & Proof System is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("formal_verification", {}).get("enabled", False)

    @property
    def formal_verification_proof_depth(self) -> int:
        """Maximum numbers to verify in induction proofs."""
        self._ensure_loaded()
        return self._raw_config.get("formal_verification", {}).get("proof_depth", 100)

    @property
    def formal_verification_timeout_ms(self) -> int:
        """Maximum time for property verification in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("formal_verification", {}).get("timeout_ms", 5000)

    @property
    def formal_verification_dashboard_width(self) -> int:
        """ASCII dashboard width for verification dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("formal_verification", {}).get("dashboard", {}).get("width", 60)

