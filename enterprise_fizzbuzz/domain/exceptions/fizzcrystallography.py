"""
Enterprise FizzBuzz Platform - FizzCrystallography Exceptions (EFP-CRY00 through EFP-CRY09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzCrystallographyError(FizzBuzzError):
    """Base exception for all FizzCrystallography crystal analysis errors.

    The FizzCrystallography engine determines the crystallographic structure
    of each FizzBuzz evaluation by analyzing Bravais lattice symmetry,
    computing X-ray diffraction patterns via Bragg's law, and resolving
    structure factors. Crystal defects in the evaluation lattice
    compromise the periodicity required for reliable divisibility
    determination.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-CRY00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class BravaisLatticeError(FizzCrystallographyError):
    """Raised when Bravais lattice parameters are inconsistent.

    A valid Bravais lattice requires positive lattice constants (a, b, c)
    and inter-axial angles (alpha, beta, gamma) that satisfy the metric
    tensor positivity constraint. Degenerate angles (0 or 180 degrees)
    collapse the unit cell volume to zero.
    """

    def __init__(self, lattice_type: str, reason: str) -> None:
        super().__init__(
            f"Invalid Bravais lattice '{lattice_type}': {reason}",
            error_code="EFP-CRY01",
            context={"lattice_type": lattice_type, "reason": reason},
        )


class MillerIndicesError(FizzCrystallographyError):
    """Raised when Miller indices are invalid.

    Miller indices (h, k, l) must be integers with at least one non-zero
    value. The indices (0, 0, 0) correspond to the origin of reciprocal
    space and do not define a crystallographic plane.
    """

    def __init__(self, h: int, k: int, l: int) -> None:
        super().__init__(
            f"Invalid Miller indices ({h}, {k}, {l}): "
            f"at least one index must be non-zero",
            error_code="EFP-CRY02",
            context={"h": h, "k": k, "l": l},
        )


class BraggConditionError(FizzCrystallographyError):
    """Raised when the Bragg condition cannot be satisfied.

    Bragg's law (2d*sin(theta) = n*lambda) requires that the wavelength
    does not exceed twice the d-spacing. When lambda > 2d, no diffraction
    angle exists and the reflection is geometrically forbidden.
    """

    def __init__(self, d_spacing_angstrom: float, wavelength_angstrom: float) -> None:
        super().__init__(
            f"Bragg condition unsatisfiable: d-spacing {d_spacing_angstrom:.4f} A "
            f"too small for wavelength {wavelength_angstrom:.4f} A",
            error_code="EFP-CRY03",
            context={
                "d_spacing_angstrom": d_spacing_angstrom,
                "wavelength_angstrom": wavelength_angstrom,
            },
        )


class StructureFactorError(FizzCrystallographyError):
    """Raised when the structure factor computation encounters invalid input.

    The structure factor F(hkl) requires valid atomic positions within
    the unit cell (fractional coordinates in [0, 1)) and positive
    atomic scattering factors.
    """

    def __init__(self, hkl: tuple, reason: str) -> None:
        super().__init__(
            f"Structure factor error for reflection {hkl}: {reason}",
            error_code="EFP-CRY04",
            context={"hkl": str(hkl), "reason": reason},
        )


class UnitCellError(FizzCrystallographyError):
    """Raised when unit cell parameters produce a degenerate cell.

    The unit cell volume must be strictly positive. A zero-volume cell
    indicates coplanar lattice vectors and cannot tile three-dimensional
    space, which is a prerequisite for crystalline FizzBuzz evaluation.
    """

    def __init__(self, volume: float) -> None:
        super().__init__(
            f"Degenerate unit cell with volume {volume:.6f} A^3",
            error_code="EFP-CRY05",
            context={"volume": volume},
        )


class CrystallographyMiddlewareError(FizzCrystallographyError):
    """Raised when the FizzCrystallography middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzCrystallography middleware error: {reason}",
            error_code="EFP-CRY06",
            context={"reason": reason},
        )
