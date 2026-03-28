"""FizzChaos Chaos Theory Engine properties."""

from __future__ import annotations

from typing import Any


class FizzchaostheoryConfigMixin:
    """Configuration properties for the FizzChaos subsystem."""

    @property
    def fizzchaostheory_lorenz_steps(self) -> int:
        """Number of Lorenz system integration steps."""
        self._ensure_loaded()
        return self._raw_config.get("fizzchaostheory", {}).get("lorenz_steps", 1000)

    @property
    def fizzchaostheory_lorenz_dt(self) -> float:
        """Lorenz system integration time step."""
        self._ensure_loaded()
        return self._raw_config.get("fizzchaostheory", {}).get("lorenz_dt", 0.01)

    @property
    def fizzchaostheory_logistic_iterations(self) -> int:
        """Logistic map iteration count."""
        self._ensure_loaded()
        return self._raw_config.get("fizzchaostheory", {}).get("logistic_iterations", 200)

    @property
    def fizzchaostheory_lyapunov_iterations(self) -> int:
        """Number of iterations for Lyapunov exponent computation."""
        self._ensure_loaded()
        return self._raw_config.get("fizzchaostheory", {}).get("lyapunov_iterations", 500)

    @property
    def fizzchaostheory_bifurcation_steps(self) -> int:
        """Number of parameter steps for bifurcation analysis."""
        self._ensure_loaded()
        return self._raw_config.get("fizzchaostheory", {}).get("bifurcation_steps", 50)

    @property
    def fizzchaostheory_dashboard_width(self) -> int:
        """Width of the FizzChaos ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzchaostheory", {}).get("dashboard_width", 60)
