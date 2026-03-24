"""FizzProve — Automated Theorem Prover configuration properties"""

from __future__ import annotations

from typing import Any


class TheoremProverConfigMixin:
    """Configuration properties for the theorem prover subsystem."""

    # ------------------------------------------------------------------
    # FizzProve — Automated Theorem Prover configuration properties
    # ------------------------------------------------------------------

    @property
    def theorem_prover_enabled(self) -> bool:
        """Whether the Automated Theorem Prover subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("theorem_prover", {}).get("enabled", False)

    @property
    def theorem_prover_max_clauses(self) -> int:
        """Maximum number of clauses before the resolution engine halts."""
        self._ensure_loaded()
        return self._raw_config.get("theorem_prover", {}).get("max_clauses", 5000)

    @property
    def theorem_prover_max_steps(self) -> int:
        """Maximum number of resolution steps per proof attempt."""
        self._ensure_loaded()
        return self._raw_config.get("theorem_prover", {}).get("max_steps", 10000)

    @property
    def theorem_prover_dashboard_width(self) -> int:
        """ASCII dashboard width for the theorem prover dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("theorem_prover", {}).get("dashboard", {}).get("width", 72)

