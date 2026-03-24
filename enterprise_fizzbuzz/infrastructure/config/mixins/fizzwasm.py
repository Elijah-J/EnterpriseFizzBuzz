"""FizzWASM configuration properties."""

from __future__ import annotations

from typing import Any


class FizzwasmConfigMixin:
    """Configuration properties for the FizzWASM subsystem."""

    @property
    def fizzwasm_enabled(self) -> bool:
        """Whether the FizzWASM runtime is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwasm", {}).get("enabled", False)

    @property
    def fizzwasm_fuel_budget(self) -> int:
        """Fuel budget for WASM execution."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("fuel_budget", 10_000_000))

    @property
    def fizzwasm_fuel_cost_model(self) -> str:
        """Fuel cost model (uniform, weighted, custom)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwasm", {}).get("fuel_cost_model", "weighted")

    @property
    def fizzwasm_fuel_check_interval(self) -> int:
        """Instructions between fuel checks."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("fuel_check_interval", 1))

    @property
    def fizzwasm_max_pages(self) -> int:
        """Maximum memory pages per instance."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("max_pages", 65536))

    @property
    def fizzwasm_max_table_size(self) -> int:
        """Maximum table entries per instance."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("max_table_size", 1048576))

    @property
    def fizzwasm_max_call_depth(self) -> int:
        """Maximum call stack depth."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("max_call_depth", 1024))

    @property
    def fizzwasm_wasi_enabled(self) -> bool:
        """Whether WASI system calls are available."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwasm", {}).get("wasi_enabled", True)

    @property
    def fizzwasm_wasi_allow_random(self) -> bool:
        """Whether WASI random_get is permitted."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwasm", {}).get("wasi_allow_random", True)

    @property
    def fizzwasm_component_model(self) -> bool:
        """Whether the Component Model layer is available."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwasm", {}).get("component_model", True)

    @property
    def fizzwasm_dashboard_width(self) -> int:
        """Width of the FizzWASM ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("dashboard", {}).get("width", 72))
