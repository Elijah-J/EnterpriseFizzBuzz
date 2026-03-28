"""
Enterprise FizzBuzz Platform - FizzMaterialScience Exceptions (EFP-MS00 through EFP-MS07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzMaterialScienceError(FizzBuzzError):
    """Base exception for the FizzMaterialScience materials simulator subsystem.

    Material science computations for FizzBuzz evaluation involve crystal
    lattice construction, stress-strain analysis, phase diagram traversal,
    and thermal property estimation. Each numerical method has convergence
    requirements and physical constraints that may be violated by degenerate
    inputs or extreme operating conditions.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-MS00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class LatticeConstructionError(FizzMaterialScienceError):
    """Raised when crystal lattice construction fails.

    A valid Bravais lattice requires basis vectors that form a
    non-degenerate parallelepiped. Collinear or zero-length vectors
    produce a singular lattice matrix, making reciprocal-space
    calculations impossible.
    """

    def __init__(self, lattice_type: str, reason: str) -> None:
        super().__init__(
            f"Crystal lattice construction failed for '{lattice_type}': {reason}",
            error_code="EFP-MS01",
            context={"lattice_type": lattice_type, "reason": reason},
        )
        self.lattice_type = lattice_type
        self.reason = reason


class StressStrainError(FizzMaterialScienceError):
    """Raised when stress-strain curve computation yields non-physical results.

    The stress-strain relationship must satisfy thermodynamic consistency:
    the stiffness tensor must be positive definite in the elastic regime,
    and the yield criterion must be convex. Violations indicate an
    incorrectly parameterized constitutive model.
    """

    def __init__(self, stress_mpa: float, strain: float, reason: str) -> None:
        super().__init__(
            f"Stress-strain computation failed at sigma={stress_mpa:.2f} MPa, "
            f"epsilon={strain:.6f}: {reason}",
            error_code="EFP-MS02",
            context={"stress_mpa": stress_mpa, "strain": strain, "reason": reason},
        )
        self.stress_mpa = stress_mpa
        self.strain = strain


class PhaseDiagramError(FizzMaterialScienceError):
    """Raised when phase diagram computation encounters thermodynamic inconsistency.

    Phase boundaries must satisfy the Clausius-Clapeyron equation, and
    the Gibbs phase rule constrains the degrees of freedom. A phase
    diagram that violates either condition is thermodynamically invalid.
    """

    def __init__(self, temperature_k: float, composition: float, reason: str) -> None:
        super().__init__(
            f"Phase diagram error at T={temperature_k:.1f} K, x={composition:.4f}: {reason}",
            error_code="EFP-MS03",
            context={
                "temperature_k": temperature_k,
                "composition": composition,
                "reason": reason,
            },
        )
        self.temperature_k = temperature_k
        self.composition = composition


class ThermalConductivityError(FizzMaterialScienceError):
    """Raised when thermal conductivity estimation yields non-physical values.

    Thermal conductivity must be positive (second law of thermodynamics)
    and finite. Divergent values indicate a phase transition or numerical
    instability in the phonon transport calculation.
    """

    def __init__(self, material: str, value_w_mk: float) -> None:
        super().__init__(
            f"Non-physical thermal conductivity for '{material}': "
            f"{value_w_mk:.4f} W/(m*K)",
            error_code="EFP-MS04",
            context={"material": material, "value_w_mk": value_w_mk},
        )
        self.material = material
        self.value_w_mk = value_w_mk


class YoungModulusError(FizzMaterialScienceError):
    """Raised when Young's modulus calculation produces invalid results.

    Young's modulus must be positive for any stable material. A negative
    or zero value indicates mechanical instability — the material would
    expand under compression, violating the Born stability criteria.
    """

    def __init__(self, material: str, modulus_gpa: float) -> None:
        super().__init__(
            f"Invalid Young's modulus for '{material}': {modulus_gpa:.4f} GPa",
            error_code="EFP-MS05",
            context={"material": material, "modulus_gpa": modulus_gpa},
        )
        self.material = material
        self.modulus_gpa = modulus_gpa


class AlloyCompositionError(FizzMaterialScienceError):
    """Raised when alloy composition violates stoichiometric constraints.

    Component fractions must sum to 1.0 and each fraction must lie in
    [0, 1]. Negative fractions are non-physical, and fractions exceeding
    unity violate conservation of mass.
    """

    def __init__(self, components: dict[str, float], reason: str) -> None:
        super().__init__(
            f"Invalid alloy composition {components}: {reason}",
            error_code="EFP-MS06",
            context={"components": components, "reason": reason},
        )
        self.components = components


class MaterialScienceMiddlewareError(FizzMaterialScienceError):
    """Raised when the FizzMaterialScience middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzMaterialScience middleware error: {reason}",
            error_code="EFP-MS07",
            context={"reason": reason},
        )
