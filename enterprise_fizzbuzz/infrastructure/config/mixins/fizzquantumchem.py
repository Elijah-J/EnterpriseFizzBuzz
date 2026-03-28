"""FizzQuantumChem Quantum Chemistry properties."""

from __future__ import annotations

from typing import Any


class FizzquantumchemConfigMixin:
    """Configuration properties for the FizzQuantumChem subsystem."""

    @property
    def fizzquantumchem_enabled(self) -> bool:
        """Whether the FizzQuantumChem quantum chemistry engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzquantumchem", {}).get("enabled", False)

    @property
    def fizzquantumchem_max_scf_iterations(self) -> int:
        """Maximum SCF iterations before declaring non-convergence."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzquantumchem", {}).get("max_scf_iterations", 100))

    @property
    def fizzquantumchem_convergence_threshold(self) -> float:
        """SCF energy convergence threshold in Hartree."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzquantumchem", {}).get("convergence_threshold", 1e-6))

    @property
    def fizzquantumchem_basis_set(self) -> str:
        """Gaussian basis set for electronic structure calculations."""
        self._ensure_loaded()
        return self._raw_config.get("fizzquantumchem", {}).get("basis_set", "STO_3G")
