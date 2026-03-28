"""FizzTopology Topological Data Analysis properties."""

from __future__ import annotations

from typing import Any


class FizztopologyConfigMixin:
    """Configuration properties for the FizzTopology subsystem."""

    @property
    def fizztopology_num_points(self) -> int:
        """Number of points in the generated point cloud."""
        self._ensure_loaded()
        return self._raw_config.get("fizztopology", {}).get("num_points", 20)

    @property
    def fizztopology_max_dimension(self) -> int:
        """Maximum homological dimension to compute."""
        self._ensure_loaded()
        return self._raw_config.get("fizztopology", {}).get("max_dimension", 2)

    @property
    def fizztopology_num_epsilon_steps(self) -> int:
        """Number of filtration scale steps."""
        self._ensure_loaded()
        return self._raw_config.get("fizztopology", {}).get("num_epsilon_steps", 10)

    @property
    def fizztopology_max_epsilon(self) -> float:
        """Maximum filtration scale."""
        self._ensure_loaded()
        return self._raw_config.get("fizztopology", {}).get("max_epsilon", 2.0)

    @property
    def fizztopology_dashboard_width(self) -> int:
        """Width of the FizzTopology ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizztopology", {}).get("dashboard_width", 60)
