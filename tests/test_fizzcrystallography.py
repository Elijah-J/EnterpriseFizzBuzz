"""
Enterprise FizzBuzz Platform - FizzCrystallography Crystal Structure Test Suite

Comprehensive verification of the crystal structure analyzer, including
Bravais lattice parameter validation, Miller indices, d-spacing computation,
Bragg angle calculation, structure factor evaluation, and diffraction
pattern generation. These tests ensure that FizzBuzz evaluations produce
crystallographically correct diffraction data.

A single misidentified crystal system would place the FizzBuzz evaluation
into the wrong symmetry class, producing systematic absences where
reflections should exist and vice versa — a crystallographic catastrophe.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzcrystallography import (
    AtomSite,
    BraggAnalyzer,
    BravaisLatticeType,
    CrystalSystem,
    CrystallographyMiddleware,
    CU_K_ALPHA,
    DiffractionPattern,
    DSpacingCalculator,
    MillerIndices,
    StructureFactorCalculator,
    UnitCell,
)
from enterprise_fizzbuzz.domain.exceptions.fizzcrystallography import (
    BraggConditionError,
    BravaisLatticeError,
    MillerIndicesError,
    StructureFactorError,
    UnitCellError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ============================================================
# Helpers
# ============================================================


def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Unit Cell Tests
# ============================================================


class TestUnitCell:
    def test_cubic_volume(self):
        cell = UnitCell(a=5.0, b=5.0, c=5.0)
        assert abs(cell.volume() - 125.0) < 0.01

    def test_cubic_system_detection(self):
        cell = UnitCell(a=5.0, b=5.0, c=5.0)
        assert cell.crystal_system() == CrystalSystem.CUBIC

    def test_tetragonal_detection(self):
        cell = UnitCell(a=5.0, b=5.0, c=8.0)
        assert cell.crystal_system() == CrystalSystem.TETRAGONAL

    def test_orthorhombic_detection(self):
        cell = UnitCell(a=3.0, b=5.0, c=7.0)
        assert cell.crystal_system() == CrystalSystem.ORTHORHOMBIC

    def test_negative_lattice_constant_raises(self):
        cell = UnitCell(a=-1.0, b=5.0, c=5.0)
        with pytest.raises(BravaisLatticeError):
            cell.validate()

    def test_degenerate_angle_raises(self):
        cell = UnitCell(a=5.0, b=5.0, c=5.0, alpha=0.0)
        with pytest.raises(BravaisLatticeError):
            cell.validate()

    def test_volume_positive_for_valid_cell(self):
        cell = UnitCell(a=4.0, b=5.0, c=6.0, alpha=80.0, beta=85.0, gamma=75.0)
        assert cell.volume() > 0


# ============================================================
# Miller Indices Tests
# ============================================================


class TestMillerIndices:
    def test_valid_indices(self):
        hkl = MillerIndices(1, 1, 0)
        hkl.validate()  # Should not raise

    def test_all_zero_raises(self):
        hkl = MillerIndices(0, 0, 0)
        with pytest.raises(MillerIndicesError):
            hkl.validate()

    def test_repr(self):
        hkl = MillerIndices(1, 2, 3)
        assert "1" in repr(hkl)


# ============================================================
# D-Spacing Tests
# ============================================================


class TestDSpacingCalculator:
    def test_cubic_d_spacing_100(self):
        cell = UnitCell(a=5.0, b=5.0, c=5.0)
        hkl = MillerIndices(1, 0, 0)
        d = DSpacingCalculator.compute(cell, hkl)
        assert abs(d - 5.0) < 0.01

    def test_cubic_d_spacing_111(self):
        cell = UnitCell(a=5.0, b=5.0, c=5.0)
        hkl = MillerIndices(1, 1, 1)
        d = DSpacingCalculator.compute(cell, hkl)
        expected = 5.0 / math.sqrt(3)
        assert abs(d - expected) < 0.01

    def test_tetragonal_d_spacing(self):
        cell = UnitCell(a=4.0, b=4.0, c=6.0)
        hkl = MillerIndices(1, 0, 0)
        d = DSpacingCalculator.compute(cell, hkl)
        assert abs(d - 4.0) < 0.01


# ============================================================
# Bragg Analyzer Tests
# ============================================================


class TestBraggAnalyzer:
    def test_bragg_angle_valid(self):
        theta = BraggAnalyzer.bragg_angle(3.0, CU_K_ALPHA)
        assert 0.0 < theta < 90.0

    def test_two_theta(self):
        two_theta = BraggAnalyzer.two_theta(3.0, CU_K_ALPHA)
        theta = BraggAnalyzer.bragg_angle(3.0, CU_K_ALPHA)
        assert abs(two_theta - 2.0 * theta) < 0.001

    def test_forbidden_reflection_raises(self):
        # d-spacing smaller than half wavelength
        with pytest.raises(BraggConditionError):
            BraggAnalyzer.bragg_angle(0.5, CU_K_ALPHA)

    def test_negative_d_spacing_raises(self):
        with pytest.raises(BraggConditionError):
            BraggAnalyzer.bragg_angle(-1.0, CU_K_ALPHA)


# ============================================================
# Structure Factor Tests
# ============================================================


class TestStructureFactorCalculator:
    def test_single_atom_at_origin(self):
        hkl = MillerIndices(1, 0, 0)
        atoms = [AtomSite("Fe", 0.0, 0.0, 0.0, scattering_factor=26.0)]
        f_mag, phase = StructureFactorCalculator.compute(hkl, atoms)
        assert abs(f_mag - 26.0) < 0.01

    def test_bcc_extinction_rule(self):
        # BCC: F(hkl)=0 when h+k+l is odd
        hkl = MillerIndices(1, 0, 0)
        atoms = [
            AtomSite("Fe", 0.0, 0.0, 0.0, scattering_factor=26.0),
            AtomSite("Fe", 0.5, 0.5, 0.5, scattering_factor=26.0),
        ]
        f_mag, _ = StructureFactorCalculator.compute(hkl, atoms)
        assert f_mag < 0.01  # Should be essentially zero

    def test_bcc_allowed_reflection(self):
        # BCC: F(hkl) != 0 when h+k+l is even
        hkl = MillerIndices(1, 1, 0)
        atoms = [
            AtomSite("Fe", 0.0, 0.0, 0.0, scattering_factor=26.0),
            AtomSite("Fe", 0.5, 0.5, 0.5, scattering_factor=26.0),
        ]
        f_mag, _ = StructureFactorCalculator.compute(hkl, atoms)
        assert f_mag > 1.0

    def test_no_atoms_raises(self):
        hkl = MillerIndices(1, 0, 0)
        with pytest.raises(StructureFactorError):
            StructureFactorCalculator.compute(hkl, [])


# ============================================================
# Diffraction Pattern Tests
# ============================================================


class TestDiffractionPattern:
    def test_generate_produces_peaks(self):
        cell = UnitCell(a=5.0, b=5.0, c=5.0)
        atoms = [AtomSite("Na", 0.0, 0.0, 0.0, scattering_factor=11.0)]
        pattern = DiffractionPattern(cell, atoms, max_two_theta=60.0)
        peaks = pattern.generate(max_index=3)
        assert len(peaks) > 0
        assert all(p["two_theta"] <= 60.0 for p in peaks)


# ============================================================
# Middleware Tests
# ============================================================


class TestCrystallographyMiddleware:
    def test_middleware_injects_crystal_system(self):
        mw = CrystallographyMiddleware()
        ctx = _make_context(10)
        result = mw.process(ctx, _identity_handler)
        assert "crystal_system" in result.metadata

    def test_middleware_injects_volume(self):
        mw = CrystallographyMiddleware()
        ctx = _make_context(7)
        result = mw.process(ctx, _identity_handler)
        assert "crystal_volume_a3" in result.metadata
        assert result.metadata["crystal_volume_a3"] > 0

    def test_middleware_name(self):
        mw = CrystallographyMiddleware()
        assert mw.get_name() == "fizzcrystallography"

    def test_middleware_priority(self):
        mw = CrystallographyMiddleware()
        assert mw.get_priority() == 300

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = CrystallographyMiddleware()
        assert isinstance(mw, IMiddleware)
