"""Quantum Computing Simulator properties"""

from __future__ import annotations

from typing import Any


class QuantumConfigMixin:
    """Configuration properties for the quantum subsystem."""

    # ----------------------------------------------------------------
    # Quantum Computing Simulator properties
    # ----------------------------------------------------------------

    @property
    def quantum_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("enabled", False)

    @property
    def quantum_num_qubits(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("num_qubits", 4)

    @property
    def quantum_max_measurement_attempts(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("max_measurement_attempts", 10)

    @property
    def quantum_decoherence_threshold(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("decoherence_threshold", 0.001)

    @property
    def quantum_fallback_to_classical(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("fallback_to_classical", True)

    @property
    def quantum_shor_max_period_attempts(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("shor_max_period_attempts", 5)

    @property
    def quantum_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("dashboard", {}).get("width", 60)

    @property
    def quantum_dashboard_show_circuit(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("quantum", {}).get("dashboard", {}).get("show_circuit", True)

