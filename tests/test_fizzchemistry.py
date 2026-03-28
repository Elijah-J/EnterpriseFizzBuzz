"""
Enterprise FizzBuzz Platform - FizzChemistry Molecular Dynamics Test Suite

Comprehensive verification of the molecular chemistry simulation engine,
including periodic table lookups, electron configuration computation,
molecular bond creation, VSEPR geometry prediction, reaction balancing,
enthalpy calculation, and formula parsing.

Chemical accuracy is paramount: an incorrectly balanced FizzBuzz reaction
could violate conservation of mass, undermining the thermodynamic
consistency of the entire evaluation pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzchemistry import (
    AVOGADRO,
    BOND_ENERGIES,
    PERIODIC_TABLE,
    STANDARD_ENTHALPIES,
    VSEPR_ANGLES,
    VSEPR_TABLE,
    BalancedReaction,
    BondType,
    ChemicalSpecies,
    ChemistryEngine,
    ChemistryMiddleware,
    Element,
    Molecule,
    MolecularBond,
    OrbitalOccupancy,
    OrbitalType,
    VSEPRShape,
    balance_reaction,
    compute_electron_configuration,
    compute_enthalpy,
    create_bond,
    get_bond_energy,
    lookup_element,
    lookup_element_by_number,
    parse_formula,
    predict_vsepr_geometry,
    valence_electrons,
)
from enterprise_fizzbuzz.domain.exceptions.fizzchemistry import (
    ChemistryMiddlewareError,
    ElectronConfigurationError,
    ElementNotFoundError,
    EnthalpyError,
    FizzChemistryError,
    MolecularBondError,
    ReactionBalanceError,
    VSEPRGeometryError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Periodic Table Tests
# ===========================================================================

class TestPeriodicTable:
    """Verification of the periodic table data integrity."""

    def test_hydrogen_present(self):
        h = lookup_element("H")
        assert h.atomic_number == 1
        assert h.name == "Hydrogen"

    def test_carbon_present(self):
        c = lookup_element("C")
        assert c.atomic_number == 6
        assert c.atomic_mass > 12.0

    def test_oxygen_electronegativity(self):
        o = lookup_element("O")
        assert o.electronegativity == pytest.approx(3.44)

    def test_invalid_symbol_raises(self):
        with pytest.raises(ElementNotFoundError):
            lookup_element("Xx")

    def test_lookup_by_number(self):
        elem = lookup_element_by_number(1)
        assert elem is not None
        assert elem.symbol == "H"

    def test_all_elements_have_positive_mass(self):
        for elem in PERIODIC_TABLE.values():
            assert elem.atomic_mass > 0

    def test_noble_gas_detection(self):
        he = lookup_element("He")
        assert he.is_noble_gas is True
        c = lookup_element("C")
        assert c.is_noble_gas is False


# ===========================================================================
# Electron Configuration Tests
# ===========================================================================

class TestElectronConfiguration:
    """Verification of Aufbau principle electron filling."""

    def test_hydrogen_config(self):
        config = compute_electron_configuration(1)
        assert len(config) == 1
        assert config[0].electrons == 1
        assert config[0].orbital_type == OrbitalType.S

    def test_carbon_config(self):
        config = compute_electron_configuration(6)
        total = sum(o.electrons for o in config)
        assert total == 6

    def test_neon_full_shell(self):
        config = compute_electron_configuration(10)
        total = sum(o.electrons for o in config)
        assert total == 10

    def test_invalid_atomic_number_raises(self):
        with pytest.raises(ElectronConfigurationError):
            compute_electron_configuration(0)

    def test_valence_electrons_carbon(self):
        ve = valence_electrons(6)
        assert ve == 4


# ===========================================================================
# Molecular Bond Tests
# ===========================================================================

class TestMolecularBond:
    """Verification of chemical bond creation and properties."""

    def test_create_single_bond(self):
        bond = create_bond("C", "H", BondType.SINGLE)
        assert bond.bond_order == 1.0
        assert bond.bond_energy_kj > 0

    def test_bond_energy_lookup(self):
        energy = get_bond_energy("O", "H", BondType.SINGLE)
        assert energy == pytest.approx(459.0)

    def test_aromatic_bond_order(self):
        bond = MolecularBond("C", "C", BondType.AROMATIC)
        assert bond.bond_order == 1.5


# ===========================================================================
# VSEPR Geometry Tests
# ===========================================================================

class TestVSEPR:
    """Verification of VSEPR molecular geometry prediction."""

    def test_water_geometry(self):
        shape, angle = predict_vsepr_geometry("O", 2, 2)
        assert shape == VSEPRShape.BENT
        assert angle == pytest.approx(104.5)

    def test_methane_geometry(self):
        shape, angle = predict_vsepr_geometry("C", 4, 0)
        assert shape == VSEPRShape.TETRAHEDRAL
        assert angle == pytest.approx(109.5)

    def test_co2_geometry(self):
        shape, angle = predict_vsepr_geometry("C", 2, 0)
        assert shape == VSEPRShape.LINEAR
        assert angle == pytest.approx(180.0)

    def test_too_few_domains_raises(self):
        with pytest.raises(VSEPRGeometryError):
            predict_vsepr_geometry("H", 1, 0)

    def test_too_many_domains_raises(self):
        with pytest.raises(VSEPRGeometryError):
            predict_vsepr_geometry("X", 5, 3)


# ===========================================================================
# Formula Parsing Tests
# ===========================================================================

class TestFormulaParsing:
    """Verification of chemical formula parsing."""

    def test_water(self):
        comp = parse_formula("H2O")
        assert comp == {"H": 2, "O": 1}

    def test_glucose(self):
        comp = parse_formula("C6H12O6")
        assert comp["C"] == 6
        assert comp["H"] == 12
        assert comp["O"] == 6

    def test_single_element(self):
        comp = parse_formula("Fe")
        assert comp == {"Fe": 1}


# ===========================================================================
# Reaction Balancing Tests
# ===========================================================================

class TestReactionBalancing:
    """Verification of chemical reaction balancing."""

    def test_balance_water_formation(self):
        result = balance_reaction(["H2", "O2"], ["H2O"])
        assert result.is_balanced

    def test_balanced_reaction_conserves_mass(self):
        result = balance_reaction(["H2", "O2"], ["H2O"])
        assert result.is_balanced is True


# ===========================================================================
# Enthalpy Tests
# ===========================================================================

class TestEnthalpy:
    """Verification of enthalpy calculation via Hess's law."""

    def test_water_formation_enthalpy(self):
        dh = compute_enthalpy(["H2", "O2"], ["H2O"], [2, 1], [2])
        # Should be negative (exothermic)
        assert dh < 0

    def test_missing_enthalpy_raises(self):
        with pytest.raises(EnthalpyError):
            compute_enthalpy(["XYZ"], ["H2O"], [1], [1])


# ===========================================================================
# Chemistry Engine Tests
# ===========================================================================

class TestChemistryEngine:
    """Verification of the top-level chemistry simulation engine."""

    def test_analyze_fizz(self):
        engine = ChemistryEngine()
        mol = engine.analyze_number(3, "Fizz")
        assert mol.formula == "H2O"
        assert mol.molecular_mass > 0

    def test_analyze_buzz(self):
        engine = ChemistryEngine()
        mol = engine.analyze_number(5, "Buzz")
        assert mol.formula == "CO2"

    def test_analyze_numeric(self):
        engine = ChemistryEngine()
        mol = engine.analyze_number(7, "7")
        assert mol.formula is not None


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestChemistryMiddleware:
    """Verification of the ChemistryMiddleware pipeline integration."""

    def test_middleware_name(self):
        mw = ChemistryMiddleware()
        assert mw.get_name() == "ChemistryMiddleware"

    def test_middleware_priority(self):
        mw = ChemistryMiddleware()
        assert mw.get_priority() == 282

    def test_middleware_attaches_metadata(self):
        mw = ChemistryMiddleware()

        ctx = ProcessingContext(number=3, session_id="test-session")
        result_ctx = ProcessingContext(number=3, session_id="test-session")
        result_ctx.results = [FizzBuzzResult(number=3, output="Fizz")]

        def next_handler(c):
            return result_ctx

        output = mw.process(ctx, next_handler)
        assert "chemistry_formula" in output.metadata
        assert output.metadata["chemistry_formula"] == "H2O"
        assert mw.analysis_count == 1
