"""FizzEconomics Economic Modeling Engine Properties"""

from __future__ import annotations

from typing import Any


class FizzEconomicsConfigMixin:
    """Configuration properties for the FizzEconomics subsystem."""

    # ----------------------------------------------------------------
    # FizzEconomics Economic Modeling Properties
    # ----------------------------------------------------------------

    @property
    def fizzeconomics_enabled(self) -> bool:
        """Whether the FizzEconomics economic modeling engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzeconomics", {}).get("enabled", False)

    @property
    def fizzeconomics_enable_options(self) -> bool:
        """Whether Black-Scholes option pricing is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzeconomics", {}).get("enable_options", True)

    @property
    def fizzeconomics_monte_carlo_sims(self) -> int:
        """Number of Monte Carlo simulation iterations."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzeconomics", {}).get("monte_carlo_sims", 10000))

    @property
    def fizzeconomics_risk_free_rate(self) -> float:
        """Risk-free interest rate for option pricing."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzeconomics", {}).get("risk_free_rate", 0.05))
