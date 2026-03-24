"""FizzBorrow Ownership & Borrow Checker properties"""

from __future__ import annotations

from typing import Any


class FizzborrowConfigMixin:
    """Configuration properties for the fizzborrow subsystem."""

    @property
    def fizzborrow_enabled(self) -> bool:
        """Whether the FizzBorrow borrow checker is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("enabled", False)

    @property
    def fizzborrow_nll_enabled(self) -> bool:
        """Whether non-lexical lifetimes are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("nll_enabled", True)

    @property
    def fizzborrow_two_phase_enabled(self) -> bool:
        """Whether two-phase borrows are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("two_phase_enabled", True)

    @property
    def fizzborrow_strict_mode(self) -> bool:
        """Whether strict mode (no elision, explicit lifetimes required) is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("strict_mode", False)

    @property
    def fizzborrow_max_inference_iterations(self) -> int:
        """Maximum fixed-point iterations for region inference."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("max_inference_iterations", 100)

    @property
    def fizzborrow_max_liveness_iterations(self) -> int:
        """Maximum iterations for liveness analysis."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("max_liveness_iterations", 50)

    @property
    def fizzborrow_max_mir_temporaries(self) -> int:
        """Maximum temporary variables the MIR builder may introduce."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("max_mir_temporaries", 1000)

    @property
    def fizzborrow_max_borrow_depth(self) -> int:
        """Maximum reborrow chain depth."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("max_borrow_depth", 64)

    @property
    def fizzborrow_dump_mir(self) -> bool:
        """Whether to dump MIR to stderr before analysis."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("dump_mir", False)

    @property
    def fizzborrow_dump_regions(self) -> bool:
        """Whether to dump solved regions after NLL inference."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("dump_regions", False)

    @property
    def fizzborrow_dump_borrows(self) -> bool:
        """Whether to dump active borrows at each MIR statement."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("dump_borrows", False)

    @property
    def fizzborrow_dump_drops(self) -> bool:
        """Whether to dump computed drop order for each scope."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("dump_drops", False)

    @property
    def fizzborrow_show_variance(self) -> bool:
        """Whether to display the variance table."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("show_variance", False)

    @property
    def fizzborrow_dashboard_width(self) -> int:
        """Dashboard width for the borrow checker dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("dashboard", {}).get("width", 72)
