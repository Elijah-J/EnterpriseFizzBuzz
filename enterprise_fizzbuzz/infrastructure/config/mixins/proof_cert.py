"""FizzProof Proof Certificate Properties"""

from __future__ import annotations

from typing import Any


class ProofCertConfigMixin:
    """Configuration properties for the proof cert subsystem."""

    # ------------------------------------------------------------------
    # FizzProof Proof Certificate Properties
    # ------------------------------------------------------------------

    @property
    def proof_cert_enabled(self) -> bool:
        """Whether the FizzProof proof certificate subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("proof_certificates", {}).get("enabled", False)

    @property
    def proof_cert_latex(self) -> bool:
        """Whether to generate LaTeX output for proof certificates."""
        self._ensure_loaded()
        return self._raw_config.get("proof_certificates", {}).get("latex", False)

    @property
    def proof_cert_dashboard_width(self) -> int:
        """Width of the FizzProof ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("proof_certificates", {}).get(
            "dashboard", {}
        ).get("width", 60)

