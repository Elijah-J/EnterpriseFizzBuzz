"""
Enterprise FizzBuzz Platform - FizzMaterialScience Materials Simulator Test Suite

Comprehensive verification of the materials science analysis pipeline,
including crystal lattice construction, stress-strain curve computation,
phase diagram traversal, thermal conductivity estimation, Young's modulus
calculation, and alloy composition analysis. Structural integrity of
FizzBuzz output strings depends on these material properties being
correctly computed; an incorrect Young's modulus could cause catastrophic
output failure under load.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzmaterialscience import (
    BOLTZMANN_EV,
    DEBYE_TEMPERATURE_BCC,
    DEBYE_TEMPERATURE_FCC,
    DEFAULT_YIELD_STRESS,
    GAS_CONSTANT,
    ROOM_TEMPERATURE_K,
    AlloyComposition,
    AlloyCompositionAnalyzer,
    CrystalLatticeEngine,
    CrystalStructure,
    DeformationMode,
    LatticeParameters,
    MaterialProperties,
    MaterialScienceEngine,
    MaterialScienceMiddleware,
    PhaseDiagramEngine,
    PhaseDiagramPoint,
    PhaseType,
    StressStrainCurve,
    StressStrainEngine,
    StressStrainPoint,
    ThermalConductivityEngine,
    YoungModulusCalculator,
)
from enterprise_fizzbuzz.domain.exceptions.fizzmaterialscience import (
    AlloyCompositionError,
    FizzMaterialScienceError,
    LatticeConstructionError,
    MaterialScienceMiddlewareError,
    PhaseDiagramError,
    StressStrainError,
    ThermalConductivityError,
    YoungModulusError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_context(number: int, output: str = "", is_fizz: bool = False, is_buzz: bool = False):
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    result._is_fizz = is_fizz
    result._is_buzz = is_buzz
    ctx.results.append(result)
    return ctx


# ===========================================================================
# Crystal Lattice Engine Tests
# ===========================================================================


class TestCrystalLatticeEngine:

    def test_fizz_number_produces_fcc(self):
        engine = CrystalLatticeEngine()
        lattice = engine.build_lattice(3, is_fizz=True, is_buzz=False)
        assert lattice.structure == CrystalStructure.FCC

    def test_buzz_number_produces_bcc(self):
        engine = CrystalLatticeEngine()
        lattice = engine.build_lattice(5, is_fizz=False, is_buzz=True)
        assert lattice.structure == CrystalStructure.BCC

    def test_fizzbuzz_number_produces_hcp(self):
        engine = CrystalLatticeEngine()
        lattice = engine.build_lattice(15, is_fizz=True, is_buzz=True)
        assert lattice.structure == CrystalStructure.HCP

    def test_prime_number_produces_diamond(self):
        engine = CrystalLatticeEngine()
        lattice = engine.build_lattice(7, is_fizz=False, is_buzz=False)
        assert lattice.structure == CrystalStructure.DIAMOND

    def test_plain_composite_produces_simple_cubic(self):
        engine = CrystalLatticeEngine()
        lattice = engine.build_lattice(4, is_fizz=False, is_buzz=False)
        assert lattice.structure == CrystalStructure.SIMPLE_CUBIC

    def test_lattice_volume_positive(self):
        engine = CrystalLatticeEngine()
        lattice = engine.build_lattice(3, is_fizz=True, is_buzz=False)
        assert lattice.volume > 0

    def test_packing_fraction_range(self):
        engine = CrystalLatticeEngine()
        for struct in CrystalStructure:
            lattice = LatticeParameters(structure=struct)
            assert 0 < lattice.packing_fraction < 1.0

    def test_nearest_neighbor_positive(self):
        engine = CrystalLatticeEngine()
        lattice = engine.build_lattice(3, True, False)
        nn = engine.nearest_neighbor_distance(lattice)
        assert nn > 0

    def test_coordination_numbers(self):
        engine = CrystalLatticeEngine()
        assert engine.coordination_number(CrystalStructure.FCC) == 12
        assert engine.coordination_number(CrystalStructure.BCC) == 8
        assert engine.coordination_number(CrystalStructure.DIAMOND) == 4


# ===========================================================================
# Stress-Strain Engine Tests
# ===========================================================================


class TestStressStrainEngine:

    def test_curve_has_positive_modulus(self):
        engine = StressStrainEngine()
        curve = engine.compute_curve(200.0, 250.0)
        assert curve.youngs_modulus_gpa == 200.0

    def test_curve_yield_stress(self):
        engine = StressStrainEngine()
        curve = engine.compute_curve(200.0, 350.0)
        assert curve.yield_stress_mpa == 350.0

    def test_curve_starts_elastic(self):
        engine = StressStrainEngine()
        curve = engine.compute_curve(200.0, 250.0)
        assert curve.points[0].mode == DeformationMode.ELASTIC

    def test_negative_modulus_raises(self):
        engine = StressStrainEngine()
        with pytest.raises(YoungModulusError):
            engine.compute_curve(-10.0, 250.0)

    def test_curve_is_valid(self):
        engine = StressStrainEngine()
        curve = engine.compute_curve(100.0, 200.0)
        assert curve.is_valid


# ===========================================================================
# Phase Diagram Engine Tests
# ===========================================================================


class TestPhaseDiagramEngine:

    def test_high_temperature_is_liquid(self):
        engine = PhaseDiagramEngine()
        pt = engine.compute_phase(2000.0, 0.5)
        assert pt.phase == PhaseType.LIQUID

    def test_negative_composition_raises(self):
        engine = PhaseDiagramEngine()
        with pytest.raises(PhaseDiagramError):
            engine.compute_phase(300.0, -0.1)

    def test_negative_temperature_raises(self):
        engine = PhaseDiagramEngine()
        with pytest.raises(PhaseDiagramError):
            engine.compute_phase(-10.0, 0.5)

    def test_phase_boundaries_length(self):
        engine = PhaseDiagramEngine()
        boundaries = engine.compute_phase_boundaries(num_points=20)
        assert len(boundaries) == 20

    def test_gibbs_energy_at_boundary(self):
        engine = PhaseDiagramEngine()
        pt = engine.compute_phase(500.0, 0.5)
        assert isinstance(pt.gibbs_energy_j, float)


# ===========================================================================
# Thermal Conductivity Tests
# ===========================================================================


class TestThermalConductivity:

    def test_positive_conductivity(self):
        engine = ThermalConductivityEngine()
        k = engine.compute(345.0)
        assert k > 0

    def test_zero_temperature_raises(self):
        engine = ThermalConductivityEngine()
        with pytest.raises(ThermalConductivityError):
            engine.compute(345.0, temperature_k=0.0)


# ===========================================================================
# Young's Modulus Tests
# ===========================================================================


class TestYoungModulus:

    def test_positive_modulus_fcc(self):
        calc = YoungModulusCalculator()
        lattice = LatticeParameters(structure=CrystalStructure.FCC)
        e = calc.compute(lattice)
        assert e > 0

    def test_positive_modulus_bcc(self):
        calc = YoungModulusCalculator()
        lattice = LatticeParameters(structure=CrystalStructure.BCC, a=2.870)
        e = calc.compute(lattice)
        assert e > 0


# ===========================================================================
# Alloy Composition Tests
# ===========================================================================


class TestAlloyComposition:

    def test_fizzbuzz_composition_balanced(self):
        analyzer = AlloyCompositionAnalyzer()
        comp = analyzer.compute_composition(15, True, True)
        assert abs(sum(comp.components.values()) - 1.0) < 1e-6

    def test_fizz_composition_fizz_rich(self):
        analyzer = AlloyCompositionAnalyzer()
        comp = analyzer.compute_composition(3, True, False)
        assert comp.components["Fz"] > comp.components["Bz"]

    def test_composition_valid(self):
        analyzer = AlloyCompositionAnalyzer()
        comp = analyzer.compute_composition(7, False, False)
        assert comp.is_valid


# ===========================================================================
# Engine Integration Tests
# ===========================================================================


class TestMaterialScienceEngine:

    def test_analyze_fizz_number(self):
        engine = MaterialScienceEngine()
        props = engine.analyze_number(3, True, False)
        assert props.lattice.structure == CrystalStructure.FCC
        assert props.youngs_modulus_gpa > 0
        assert props.thermal_conductivity_w_mk > 0

    def test_analysis_count_increments(self):
        engine = MaterialScienceEngine()
        engine.analyze_number(1, False, False)
        engine.analyze_number(2, False, False)
        assert engine.analysis_count == 2


# ===========================================================================
# Middleware Tests
# ===========================================================================


class TestMaterialScienceMiddleware:

    def test_middleware_attaches_metadata(self):
        mw = MaterialScienceMiddleware()
        ctx = _make_context(3, "Fizz", is_fizz=True)
        result = mw.process(ctx, lambda c: c)
        assert "material_science" in result.metadata
        assert "crystal_structure" in result.metadata["material_science"]

    def test_middleware_handles_plain_number(self):
        mw = MaterialScienceMiddleware()
        ctx = _make_context(4, "4")
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["material_science"]["crystal_structure"] == "SIMPLE_CUBIC"


# ===========================================================================
# Exception Tests
# ===========================================================================


class TestExceptions:

    def test_base_exception(self):
        err = FizzMaterialScienceError("test")
        assert "EFP-MS00" in str(err.error_code)

    def test_lattice_error_fields(self):
        err = LatticeConstructionError("FCC", "bad vectors")
        assert err.lattice_type == "FCC"
        assert err.reason == "bad vectors"
