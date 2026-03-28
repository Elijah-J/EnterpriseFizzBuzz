"""
Enterprise FizzBuzz Platform - FizzCrystallography Crystal Structure Analyzer

Analyzes the crystallographic structure of FizzBuzz evaluation results by
computing Bravais lattice parameters, Miller indices, X-ray diffraction
patterns, and structure factors. Each FizzBuzz number maps to a unit cell
whose symmetry properties encode the divisibility classification.

The seven crystal systems (triclinic through cubic) partition the space
of lattice parameters into symmetry classes. The number's modular
residues determine the lattice constants and angles, placing each
evaluation into a definite crystal system. X-ray diffraction analysis
via Bragg's law then reveals which reflections are present, and the
structure factor computation identifies systematic absences arising
from the space group symmetry.

Bragg's law: n * lambda = 2 * d * sin(theta)
Structure factor: F(hkl) = sum_j f_j * exp(2*pi*i*(h*x_j + k*y_j + l*z_j))

All crystallography is implemented in pure Python using only the
standard library (math). No external crystallography libraries are
required.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizzcrystallography import (
    BraggConditionError,
    BravaisLatticeError,
    CrystallographyMiddlewareError,
    MillerIndicesError,
    StructureFactorError,
    UnitCellError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# Physical constants
CU_K_ALPHA = 1.5406    # Cu K-alpha wavelength in Angstroms
MO_K_ALPHA = 0.7107    # Mo K-alpha wavelength in Angstroms


# ============================================================
# Crystal System Enum
# ============================================================


class CrystalSystem(Enum):
    """The seven crystal systems classified by unit cell symmetry."""

    TRICLINIC = auto()
    MONOCLINIC = auto()
    ORTHORHOMBIC = auto()
    TETRAGONAL = auto()
    TRIGONAL = auto()
    HEXAGONAL = auto()
    CUBIC = auto()


class BravaisLatticeType(Enum):
    """The 14 Bravais lattice types."""

    TRICLINIC_P = auto()
    MONOCLINIC_P = auto()
    MONOCLINIC_C = auto()
    ORTHORHOMBIC_P = auto()
    ORTHORHOMBIC_C = auto()
    ORTHORHOMBIC_I = auto()
    ORTHORHOMBIC_F = auto()
    TETRAGONAL_P = auto()
    TETRAGONAL_I = auto()
    TRIGONAL_R = auto()
    HEXAGONAL_P = auto()
    CUBIC_P = auto()
    CUBIC_I = auto()
    CUBIC_F = auto()


# ============================================================
# Unit Cell
# ============================================================


@dataclass
class UnitCell:
    """Crystallographic unit cell with lattice parameters.

    Defined by three edge lengths (a, b, c in Angstroms) and three
    inter-axial angles (alpha, beta, gamma in degrees).
    """

    a: float = 5.0
    b: float = 5.0
    c: float = 5.0
    alpha: float = 90.0
    beta: float = 90.0
    gamma: float = 90.0

    def volume(self) -> float:
        """Compute the unit cell volume in cubic Angstroms.

        V = a*b*c * sqrt(1 - cos^2(alpha) - cos^2(beta) - cos^2(gamma)
                         + 2*cos(alpha)*cos(beta)*cos(gamma))
        """
        ca = math.cos(math.radians(self.alpha))
        cb = math.cos(math.radians(self.beta))
        cg = math.cos(math.radians(self.gamma))
        factor = 1.0 - ca * ca - cb * cb - cg * cg + 2.0 * ca * cb * cg
        if factor <= 0:
            raise UnitCellError(0.0)
        return self.a * self.b * self.c * math.sqrt(factor)

    def crystal_system(self) -> CrystalSystem:
        """Determine the crystal system from lattice parameters."""
        tol = 0.01
        a_eq_b = abs(self.a - self.b) < tol
        b_eq_c = abs(self.b - self.c) < tol
        a_eq_c = abs(self.a - self.c) < tol
        al_90 = abs(self.alpha - 90.0) < tol
        be_90 = abs(self.beta - 90.0) < tol
        ga_90 = abs(self.gamma - 90.0) < tol
        ga_120 = abs(self.gamma - 120.0) < tol

        if a_eq_b and b_eq_c and al_90 and be_90 and ga_90:
            return CrystalSystem.CUBIC
        if a_eq_b and al_90 and be_90 and ga_90:
            return CrystalSystem.TETRAGONAL
        if al_90 and be_90 and ga_90:
            return CrystalSystem.ORTHORHOMBIC
        if a_eq_b and al_90 and be_90 and ga_120:
            return CrystalSystem.HEXAGONAL
        if a_eq_b and a_eq_c and abs(self.alpha - self.beta) < tol and abs(self.beta - self.gamma) < tol:
            return CrystalSystem.TRIGONAL
        if al_90 and ga_90 and not be_90:
            return CrystalSystem.MONOCLINIC
        return CrystalSystem.TRICLINIC

    def validate(self) -> None:
        """Validate that unit cell parameters are physically meaningful."""
        if self.a <= 0 or self.b <= 0 or self.c <= 0:
            raise BravaisLatticeError(
                self.crystal_system().name,
                f"Lattice constants must be positive: a={self.a}, b={self.b}, c={self.c}",
            )
        for angle_name, angle_val in [("alpha", self.alpha), ("beta", self.beta), ("gamma", self.gamma)]:
            if angle_val <= 0 or angle_val >= 180:
                raise BravaisLatticeError(
                    self.crystal_system().name,
                    f"Angle {angle_name}={angle_val} must be in (0, 180) degrees",
                )
        vol = self.volume()
        if vol <= 0:
            raise UnitCellError(vol)


# ============================================================
# Miller Indices
# ============================================================


@dataclass
class MillerIndices:
    """A set of Miller indices (h, k, l) defining a crystal plane."""

    h: int
    k: int
    l: int

    def validate(self) -> None:
        """Ensure at least one index is non-zero."""
        if self.h == 0 and self.k == 0 and self.l == 0:
            raise MillerIndicesError(self.h, self.k, self.l)

    def __repr__(self) -> str:
        return f"({self.h} {self.k} {self.l})"


# ============================================================
# D-Spacing Calculator
# ============================================================


class DSpacingCalculator:
    """Computes interplanar d-spacing from unit cell and Miller indices.

    For a general triclinic cell, the reciprocal metric tensor is used.
    For higher-symmetry systems, simplified formulas apply.
    """

    @staticmethod
    def compute(cell: UnitCell, hkl: MillerIndices) -> float:
        """Compute the d-spacing in Angstroms for the given reflection."""
        hkl.validate()
        h, k, l = hkl.h, hkl.k, hkl.l

        system = cell.crystal_system()
        if system == CrystalSystem.CUBIC:
            inv_d_sq = (h * h + k * k + l * l) / (cell.a * cell.a)
        elif system == CrystalSystem.TETRAGONAL:
            inv_d_sq = (h * h + k * k) / (cell.a * cell.a) + (l * l) / (cell.c * cell.c)
        elif system == CrystalSystem.ORTHORHOMBIC:
            inv_d_sq = (h * h) / (cell.a * cell.a) + (k * k) / (cell.b * cell.b) + (l * l) / (cell.c * cell.c)
        else:
            # General triclinic formula via reciprocal metric tensor
            ca = math.cos(math.radians(cell.alpha))
            cb = math.cos(math.radians(cell.beta))
            cg = math.cos(math.radians(cell.gamma))
            sa = math.sin(math.radians(cell.alpha))
            sb = math.sin(math.radians(cell.beta))
            sg = math.sin(math.radians(cell.gamma))

            v = cell.volume()
            v_sq = v * v

            s11 = (cell.b * cell.c * sa) ** 2
            s22 = (cell.a * cell.c * sb) ** 2
            s33 = (cell.a * cell.b * sg) ** 2
            s12 = cell.a * cell.b * cell.c * cell.c * (ca * cb - cg)
            s23 = cell.a * cell.a * cell.b * cell.c * (cb * cg - ca)
            s13 = cell.a * cell.b * cell.b * cell.c * (ca * cg - cb)

            inv_d_sq = (
                s11 * h * h + s22 * k * k + s33 * l * l
                + 2 * s12 * h * k + 2 * s23 * k * l + 2 * s13 * h * l
            ) / v_sq

        if inv_d_sq <= 0:
            raise BravaisLatticeError(
                system.name,
                f"Non-positive inverse d-spacing squared for ({h},{k},{l})",
            )
        return 1.0 / math.sqrt(inv_d_sq)


# ============================================================
# Bragg's Law
# ============================================================


class BraggAnalyzer:
    """Computes diffraction angles from Bragg's law.

    n * lambda = 2 * d * sin(theta)

    For a given wavelength and d-spacing, the diffraction angle
    2*theta is computed. If lambda > 2d, the reflection is
    geometrically forbidden.
    """

    @staticmethod
    def bragg_angle(
        d_spacing: float, wavelength: float = CU_K_ALPHA, order: int = 1
    ) -> float:
        """Compute the Bragg angle theta in degrees."""
        if d_spacing <= 0 or wavelength <= 0:
            raise BraggConditionError(d_spacing, wavelength)

        sin_theta = (order * wavelength) / (2.0 * d_spacing)
        if abs(sin_theta) > 1.0:
            raise BraggConditionError(d_spacing, wavelength)

        return math.degrees(math.asin(sin_theta))

    @staticmethod
    def two_theta(
        d_spacing: float, wavelength: float = CU_K_ALPHA, order: int = 1
    ) -> float:
        """Compute 2*theta in degrees."""
        return 2.0 * BraggAnalyzer.bragg_angle(d_spacing, wavelength, order)


# ============================================================
# Structure Factor
# ============================================================


@dataclass
class AtomSite:
    """An atom in the unit cell at fractional coordinates."""

    element: str
    x: float  # fractional coordinate [0, 1)
    y: float
    z: float
    scattering_factor: float = 1.0  # Simplified atomic scattering factor

    def validate(self) -> None:
        """Validate fractional coordinates."""
        if self.scattering_factor < 0:
            raise StructureFactorError(
                (0, 0, 0),
                f"Negative scattering factor {self.scattering_factor} for {self.element}",
            )


class StructureFactorCalculator:
    """Computes the crystallographic structure factor F(hkl).

    F(hkl) = sum_j f_j * exp(2*pi*i*(h*x_j + k*y_j + l*z_j))

    The magnitude |F|^2 determines the diffracted intensity.
    Systematic absences (F=0) arise from translational symmetry
    elements in the space group.
    """

    @staticmethod
    def compute(
        hkl: MillerIndices, atoms: list[AtomSite]
    ) -> tuple[float, float]:
        """Compute the structure factor and return (|F|, phase in degrees)."""
        hkl.validate()
        if not atoms:
            raise StructureFactorError(
                (hkl.h, hkl.k, hkl.l), "No atoms in unit cell"
            )

        f_real = 0.0
        f_imag = 0.0

        for atom in atoms:
            atom.validate()
            phase = 2.0 * math.pi * (
                hkl.h * atom.x + hkl.k * atom.y + hkl.l * atom.z
            )
            f_real += atom.scattering_factor * math.cos(phase)
            f_imag += atom.scattering_factor * math.sin(phase)

        magnitude = math.sqrt(f_real * f_real + f_imag * f_imag)
        phase_deg = math.degrees(math.atan2(f_imag, f_real))
        return magnitude, phase_deg


# ============================================================
# Diffraction Pattern Generator
# ============================================================


class DiffractionPattern:
    """Generates a powder X-ray diffraction pattern.

    Computes 2-theta positions and relative intensities for all
    allowed reflections within a specified 2-theta range.
    """

    def __init__(
        self,
        cell: UnitCell,
        atoms: list[AtomSite],
        wavelength: float = CU_K_ALPHA,
        max_two_theta: float = 90.0,
    ) -> None:
        self._cell = cell
        self._atoms = atoms
        self._wavelength = wavelength
        self._max_two_theta = max_two_theta

    def generate(self, max_index: int = 5) -> list[dict[str, Any]]:
        """Generate diffraction peaks for all Miller indices up to max_index."""
        peaks: list[dict[str, Any]] = []

        for h in range(-max_index, max_index + 1):
            for k in range(-max_index, max_index + 1):
                for l_val in range(-max_index, max_index + 1):
                    if h == 0 and k == 0 and l_val == 0:
                        continue

                    hkl = MillerIndices(h, k, l_val)
                    try:
                        d = DSpacingCalculator.compute(self._cell, hkl)
                        two_theta = BraggAnalyzer.two_theta(d, self._wavelength)

                        if two_theta > self._max_two_theta:
                            continue

                        f_mag, phase = StructureFactorCalculator.compute(hkl, self._atoms)
                        intensity = f_mag * f_mag

                        if intensity > 1e-6:
                            peaks.append({
                                "hkl": (h, k, l_val),
                                "d_spacing": d,
                                "two_theta": two_theta,
                                "intensity": intensity,
                                "f_magnitude": f_mag,
                            })
                    except (BraggConditionError, BravaisLatticeError):
                        continue

        # Sort by 2-theta
        peaks.sort(key=lambda p: p["two_theta"])
        return peaks


# ============================================================
# FizzCrystallography Middleware
# ============================================================


class CrystallographyMiddleware(IMiddleware):
    """Injects crystal structure analysis into the FizzBuzz pipeline.

    For each number evaluated, the middleware constructs a unit cell
    whose parameters are derived from the number, computes the crystal
    system, and analyzes the primary diffraction peak.
    """

    def __init__(self, wavelength: float = CU_K_ALPHA) -> None:
        self._wavelength = wavelength

    def get_name(self) -> str:
        return "fizzcrystallography"

    def get_priority(self) -> int:
        return 300

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Analyze crystal structure and inject results into context."""
        try:
            n = context.number
            # Map number to unit cell parameters
            a = 3.0 + (n % 7) * 0.5
            b = 3.0 + (n % 5) * 0.5 if n % 3 != 0 else a
            c = 3.0 + (n % 11) * 0.3 if n % 5 != 0 else a

            alpha = 90.0
            beta = 90.0
            gamma = 90.0 if n % 2 == 0 else 90.0 + (n % 10) * 0.5

            cell = UnitCell(a=a, b=b, c=c, alpha=alpha, beta=beta, gamma=gamma)
            cell.validate()

            system = cell.crystal_system()
            volume = cell.volume()

            # Compute primary reflection d-spacing
            hkl = MillerIndices(1, 1, 1)
            d = DSpacingCalculator.compute(cell, hkl)

            context.metadata["crystal_system"] = system.name
            context.metadata["crystal_volume_a3"] = round(volume, 3)
            context.metadata["crystal_d111"] = round(d, 4)

            logger.debug(
                "FizzCrystallography: number=%d system=%s volume=%.1f A^3 d(111)=%.4f A",
                n, system.name, volume, d,
            )
        except Exception as exc:
            logger.error("FizzCrystallography middleware error: %s", exc)
            context.metadata["crystal_error"] = str(exc)

        return next_handler(context)
