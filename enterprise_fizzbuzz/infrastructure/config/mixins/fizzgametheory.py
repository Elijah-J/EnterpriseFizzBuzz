"""FizzGameTheory Game Theory Engine properties."""

from __future__ import annotations

from typing import Any


class FizzgametheoryConfigMixin:
    """Configuration properties for the FizzGameTheory subsystem."""

    @property
    def fizzgametheory_enabled(self) -> bool:
        """Whether the FizzGameTheory game theory engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzgametheory", {}).get("enabled", False)

    @property
    def fizzgametheory_seed(self) -> int | None:
        """Random seed for game theory analysis reproducibility."""
        self._ensure_loaded()
        return self._raw_config.get("fizzgametheory", {}).get("seed", None)

    @property
    def fizzgametheory_pd_rounds(self) -> int:
        """Number of rounds for iterated Prisoner's Dilemma simulation."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzgametheory", {}).get("pd_rounds", 100))
