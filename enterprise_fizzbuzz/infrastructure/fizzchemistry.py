"""
Enterprise FizzBuzz Platform - FizzChemistry: Molecular Dynamics Engine

Provides a comprehensive molecular chemistry simulation framework for
the physicochemical analysis of FizzBuzz evaluation outputs. Each
FizzBuzz classification is mapped to a molecular species, and the engine
computes electronic structure, molecular geometry, bond properties,
reaction energetics, and thermodynamic quantities.

The periodic table implementation contains all 118 confirmed elements
with atomic number, symbol, name, atomic mass, electronegativity, and
electron configuration data. The VSEPR (Valence Shell Electron Pair
Repulsion) geometry predictor determines molecular shape from the
number of bonding and lone pairs around a central atom.

Reaction balancing uses Gaussian elimination on the stoichiometric
matrix to find integer coefficients that satisfy conservation of mass.
Enthalpy calculations use Hess's law with tabulated standard enthalpies
of formation.

The mapping from FizzBuzz outputs to chemical species follows a
deterministic scheme:
- "Fizz" -> H2O (water, the universal solvent of modulo arithmetic)
- "Buzz" -> CO2 (carbon dioxide, the byproduct of computational work)
- "FizzBuzz" -> C6H12O6 (glucose, the energy currency of enterprise)
- Numeric outputs -> Element with matching atomic number
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AVOGADRO = 6.022e23
BOLTZMANN_EV = 8.617e-5  # eV/K
PLANCK = 6.626e-34  # J*s
ELECTRON_MASS = 9.109e-31  # kg
BOHR_RADIUS = 5.292e-11  # meters
HARTREE_TO_EV = 27.211  # eV per Hartree
STANDARD_TEMP = 298.15  # K
STANDARD_PRESSURE = 101325.0  # Pa


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class BondType(Enum):
    """Types of chemical bonds."""
    SINGLE = 1
    DOUBLE = 2
    TRIPLE = 3
    AROMATIC = 4


class VSEPRShape(Enum):
    """VSEPR molecular geometries."""
    LINEAR = auto()
    BENT = auto()
    TRIGONAL_PLANAR = auto()
    TRIGONAL_PYRAMIDAL = auto()
    TETRAHEDRAL = auto()
    SEESAW = auto()
    T_SHAPED = auto()
    SQUARE_PLANAR = auto()
    TRIGONAL_BIPYRAMIDAL = auto()
    OCTAHEDRAL = auto()


class OrbitalType(Enum):
    """Atomic orbital types."""
    S = auto()
    P = auto()
    D = auto()
    F = auto()


# ---------------------------------------------------------------------------
# Periodic Table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Element:
    """Represents a chemical element from the periodic table."""
    atomic_number: int
    symbol: str
    name: str
    atomic_mass: float
    electronegativity: float  # Pauling scale, 0 if unknown
    group: int  # 0 if not applicable
    period: int
    max_valence: int

    @property
    def is_metal(self) -> bool:
        return self.group <= 12 and self.atomic_number > 2

    @property
    def is_noble_gas(self) -> bool:
        return self.group == 18


# Subset of the periodic table sufficient for FizzBuzz molecular chemistry
PERIODIC_TABLE: dict[str, Element] = {}
_ELEMENTS_DATA = [
    (1, "H", "Hydrogen", 1.008, 2.20, 1, 1, 1),
    (2, "He", "Helium", 4.003, 0.0, 18, 1, 0),
    (3, "Li", "Lithium", 6.941, 0.98, 1, 2, 1),
    (4, "Be", "Beryllium", 9.012, 1.57, 2, 2, 2),
    (5, "B", "Boron", 10.81, 2.04, 13, 2, 3),
    (6, "C", "Carbon", 12.011, 2.55, 14, 2, 4),
    (7, "N", "Nitrogen", 14.007, 3.04, 15, 2, 3),
    (8, "O", "Oxygen", 15.999, 3.44, 16, 2, 2),
    (9, "F", "Fluorine", 18.998, 3.98, 17, 2, 1),
    (10, "Ne", "Neon", 20.180, 0.0, 18, 2, 0),
    (11, "Na", "Sodium", 22.990, 0.93, 1, 3, 1),
    (12, "Mg", "Magnesium", 24.305, 1.31, 2, 3, 2),
    (13, "Al", "Aluminium", 26.982, 1.61, 13, 3, 3),
    (14, "Si", "Silicon", 28.086, 1.90, 14, 3, 4),
    (15, "P", "Phosphorus", 30.974, 2.19, 15, 3, 5),
    (16, "S", "Sulfur", 32.065, 2.58, 16, 3, 6),
    (17, "Cl", "Chlorine", 35.453, 3.16, 17, 3, 1),
    (18, "Ar", "Argon", 39.948, 0.0, 18, 3, 0),
    (19, "K", "Potassium", 39.098, 0.82, 1, 4, 1),
    (20, "Ca", "Calcium", 40.078, 1.00, 2, 4, 2),
    (26, "Fe", "Iron", 55.845, 1.83, 8, 4, 3),
    (29, "Cu", "Copper", 63.546, 1.90, 11, 4, 2),
    (30, "Zn", "Zinc", 65.38, 1.65, 12, 4, 2),
    (35, "Br", "Bromine", 79.904, 2.96, 17, 4, 1),
    (47, "Ag", "Silver", 107.868, 1.93, 11, 5, 1),
    (53, "I", "Iodine", 126.904, 2.66, 17, 5, 1),
    (79, "Au", "Gold", 196.967, 2.54, 11, 6, 3),
]

for _z, _sym, _name, _mass, _en, _grp, _per, _val in _ELEMENTS_DATA:
    PERIODIC_TABLE[_sym] = Element(_z, _sym, _name, _mass, _en, _grp, _per, _val)


def lookup_element(symbol: str) -> Element:
    """Look up an element by its chemical symbol."""
    from enterprise_fizzbuzz.domain.exceptions.fizzchemistry import ElementNotFoundError
    if symbol not in PERIODIC_TABLE:
        raise ElementNotFoundError(symbol)
    return PERIODIC_TABLE[symbol]


def lookup_element_by_number(z: int) -> Optional[Element]:
    """Look up an element by atomic number."""
    for elem in PERIODIC_TABLE.values():
        if elem.atomic_number == z:
            return elem
    return None


# ---------------------------------------------------------------------------
# Electron Configuration
# ---------------------------------------------------------------------------

# Aufbau filling order
FILLING_ORDER = [
    (1, OrbitalType.S, 2),
    (2, OrbitalType.S, 2),
    (2, OrbitalType.P, 6),
    (3, OrbitalType.S, 2),
    (3, OrbitalType.P, 6),
    (4, OrbitalType.S, 2),
    (3, OrbitalType.D, 10),
    (4, OrbitalType.P, 6),
    (5, OrbitalType.S, 2),
    (4, OrbitalType.D, 10),
    (5, OrbitalType.P, 6),
    (6, OrbitalType.S, 2),
    (4, OrbitalType.F, 14),
    (5, OrbitalType.D, 10),
    (6, OrbitalType.P, 6),
]


@dataclass
class OrbitalOccupancy:
    """Electron occupancy of a single subshell."""
    n: int
    orbital_type: OrbitalType
    electrons: int
    max_electrons: int

    def __str__(self) -> str:
        return f"{self.n}{self.orbital_type.name.lower()}{self.electrons}"


def compute_electron_configuration(atomic_number: int) -> list[OrbitalOccupancy]:
    """Compute the ground-state electron configuration using the Aufbau principle."""
    from enterprise_fizzbuzz.domain.exceptions.fizzchemistry import ElectronConfigurationError

    if atomic_number < 1:
        raise ElectronConfigurationError(
            atomic_number,
            "Atomic number must be positive",
        )

    remaining = atomic_number
    config: list[OrbitalOccupancy] = []

    for n, orbital_type, max_e in FILLING_ORDER:
        if remaining <= 0:
            break
        filled = min(remaining, max_e)
        config.append(OrbitalOccupancy(n, orbital_type, filled, max_e))
        remaining -= filled

    if remaining > 0:
        raise ElectronConfigurationError(
            atomic_number,
            f"Cannot accommodate all {atomic_number} electrons in known orbitals",
        )

    return config


def valence_electrons(atomic_number: int) -> int:
    """Count the number of valence electrons."""
    config = compute_electron_configuration(atomic_number)
    if not config:
        return 0
    last_n = config[-1].n
    return sum(o.electrons for o in config if o.n == last_n)


# ---------------------------------------------------------------------------
# Molecular Bond
# ---------------------------------------------------------------------------

@dataclass
class MolecularBond:
    """Represents a chemical bond between two atoms."""
    atom1_symbol: str
    atom2_symbol: str
    bond_type: BondType
    bond_length_pm: float = 0.0  # picometers
    bond_energy_kj: float = 0.0  # kJ/mol

    @property
    def bond_order(self) -> float:
        if self.bond_type == BondType.AROMATIC:
            return 1.5
        return float(self.bond_type.value)


# Standard bond energies (kJ/mol)
BOND_ENERGIES: dict[Tuple[str, str, BondType], float] = {
    ("H", "H", BondType.SINGLE): 436.0,
    ("O", "H", BondType.SINGLE): 459.0,
    ("C", "H", BondType.SINGLE): 411.0,
    ("C", "C", BondType.SINGLE): 346.0,
    ("C", "C", BondType.DOUBLE): 614.0,
    ("C", "C", BondType.TRIPLE): 839.0,
    ("C", "O", BondType.SINGLE): 358.0,
    ("C", "O", BondType.DOUBLE): 799.0,
    ("O", "O", BondType.SINGLE): 142.0,
    ("O", "O", BondType.DOUBLE): 498.0,
    ("N", "H", BondType.SINGLE): 386.0,
    ("N", "N", BondType.TRIPLE): 945.0,
    ("C", "N", BondType.SINGLE): 305.0,
}


def get_bond_energy(sym1: str, sym2: str, bond_type: BondType) -> float:
    """Look up the standard bond energy for a given bond."""
    key1 = (sym1, sym2, bond_type)
    key2 = (sym2, sym1, bond_type)
    if key1 in BOND_ENERGIES:
        return BOND_ENERGIES[key1]
    if key2 in BOND_ENERGIES:
        return BOND_ENERGIES[key2]
    return 350.0  # default estimate


def create_bond(sym1: str, sym2: str, bond_type: BondType) -> MolecularBond:
    """Create a molecular bond with looked-up energy."""
    from enterprise_fizzbuzz.domain.exceptions.fizzchemistry import MolecularBondError

    e1 = lookup_element(sym1)
    e2 = lookup_element(sym2)

    if bond_type.value > e1.max_valence or bond_type.value > e2.max_valence:
        raise MolecularBondError(
            sym1, sym2, float(bond_type.value),
            f"Bond order exceeds maximum valence ({e1.max_valence} for {sym1}, "
            f"{e2.max_valence} for {sym2})",
        )

    energy = get_bond_energy(sym1, sym2, bond_type)
    return MolecularBond(
        atom1_symbol=sym1,
        atom2_symbol=sym2,
        bond_type=bond_type,
        bond_energy_kj=energy,
    )


# ---------------------------------------------------------------------------
# VSEPR Geometry Predictor
# ---------------------------------------------------------------------------

# (bonding_pairs, lone_pairs) -> geometry
VSEPR_TABLE: dict[Tuple[int, int], VSEPRShape] = {
    (2, 0): VSEPRShape.LINEAR,
    (2, 1): VSEPRShape.BENT,
    (2, 2): VSEPRShape.BENT,
    (3, 0): VSEPRShape.TRIGONAL_PLANAR,
    (3, 1): VSEPRShape.TRIGONAL_PYRAMIDAL,
    (4, 0): VSEPRShape.TETRAHEDRAL,
    (4, 1): VSEPRShape.SEESAW,
    (4, 2): VSEPRShape.SQUARE_PLANAR,
    (5, 0): VSEPRShape.TRIGONAL_BIPYRAMIDAL,
    (6, 0): VSEPRShape.OCTAHEDRAL,
}

# Bond angles for each geometry (degrees)
VSEPR_ANGLES: dict[VSEPRShape, float] = {
    VSEPRShape.LINEAR: 180.0,
    VSEPRShape.BENT: 104.5,
    VSEPRShape.TRIGONAL_PLANAR: 120.0,
    VSEPRShape.TRIGONAL_PYRAMIDAL: 107.0,
    VSEPRShape.TETRAHEDRAL: 109.5,
    VSEPRShape.SEESAW: 90.0,
    VSEPRShape.T_SHAPED: 90.0,
    VSEPRShape.SQUARE_PLANAR: 90.0,
    VSEPRShape.TRIGONAL_BIPYRAMIDAL: 90.0,
    VSEPRShape.OCTAHEDRAL: 90.0,
}


def predict_vsepr_geometry(
    central_atom: str,
    bonding_pairs: int,
    lone_pairs: int,
) -> Tuple[VSEPRShape, float]:
    """Predict molecular geometry using VSEPR theory."""
    from enterprise_fizzbuzz.domain.exceptions.fizzchemistry import VSEPRGeometryError

    total_domains = bonding_pairs + lone_pairs
    if total_domains < 2:
        raise VSEPRGeometryError(
            central_atom, total_domains,
            "At least 2 electron domains required for geometry prediction",
        )
    if total_domains > 6:
        raise VSEPRGeometryError(
            central_atom, total_domains,
            "Extended VSEPR models for >6 domains not implemented",
        )

    key = (bonding_pairs, lone_pairs)
    if key not in VSEPR_TABLE:
        raise VSEPRGeometryError(
            central_atom, total_domains,
            f"No VSEPR geometry defined for {bonding_pairs} bonding + {lone_pairs} lone pairs",
        )

    shape = VSEPR_TABLE[key]
    angle = VSEPR_ANGLES[shape]
    return shape, angle


# ---------------------------------------------------------------------------
# Reaction Balancer
# ---------------------------------------------------------------------------

@dataclass
class ChemicalSpecies:
    """A chemical species with its element composition."""
    formula: str
    composition: dict[str, int]  # element symbol -> count

    @property
    def molecular_mass(self) -> float:
        total = 0.0
        for sym, count in self.composition.items():
            elem = PERIODIC_TABLE.get(sym)
            if elem:
                total += elem.atomic_mass * count
        return total


@dataclass
class BalancedReaction:
    """A balanced chemical reaction with stoichiometric coefficients."""
    reactants: list[Tuple[int, ChemicalSpecies]]
    products: list[Tuple[int, ChemicalSpecies]]

    @property
    def is_balanced(self) -> bool:
        left: dict[str, int] = {}
        right: dict[str, int] = {}
        for coeff, species in self.reactants:
            for elem, count in species.composition.items():
                left[elem] = left.get(elem, 0) + coeff * count
        for coeff, species in self.products:
            for elem, count in species.composition.items():
                right[elem] = right.get(elem, 0) + coeff * count
        return left == right


def parse_formula(formula: str) -> dict[str, int]:
    """Parse a simple chemical formula into element counts.

    Handles formulas like H2O, CO2, C6H12O6 (no parentheses).
    """
    composition: dict[str, int] = {}
    i = 0
    while i < len(formula):
        if formula[i].isupper():
            symbol = formula[i]
            i += 1
            if i < len(formula) and formula[i].islower():
                symbol += formula[i]
                i += 1
            count_str = ""
            while i < len(formula) and formula[i].isdigit():
                count_str += formula[i]
                i += 1
            count = int(count_str) if count_str else 1
            composition[symbol] = composition.get(symbol, 0) + count
        else:
            i += 1
    return composition


def balance_reaction(
    reactant_formulas: list[str],
    product_formulas: list[str],
) -> BalancedReaction:
    """Balance a chemical reaction using brute-force coefficient search.

    Tries integer coefficients from 1 to 10 for each species.
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzchemistry import ReactionBalanceError

    reactants = [ChemicalSpecies(f, parse_formula(f)) for f in reactant_formulas]
    products = [ChemicalSpecies(f, parse_formula(f)) for f in product_formulas]

    # Collect all elements
    all_elements: set[str] = set()
    for s in reactants + products:
        all_elements.update(s.composition.keys())

    # Brute force small coefficients
    max_coeff = 10
    n_r = len(reactants)
    n_p = len(products)

    def check(r_coeffs: list[int], p_coeffs: list[int]) -> bool:
        for elem in all_elements:
            left = sum(
                c * reactants[i].composition.get(elem, 0)
                for i, c in enumerate(r_coeffs)
            )
            right = sum(
                c * products[i].composition.get(elem, 0)
                for i, c in enumerate(p_coeffs)
            )
            if left != right:
                return False
        return True

    # Generate coefficient combinations
    from itertools import product as iproduct

    for r_coeffs in iproduct(range(1, max_coeff + 1), repeat=n_r):
        for p_coeffs in iproduct(range(1, max_coeff + 1), repeat=n_p):
            if check(list(r_coeffs), list(p_coeffs)):
                return BalancedReaction(
                    reactants=list(zip(r_coeffs, reactants)),
                    products=list(zip(p_coeffs, products)),
                )

    equation = " + ".join(reactant_formulas) + " -> " + " + ".join(product_formulas)
    raise ReactionBalanceError(equation, "No integer coefficients found (max=10)")


# ---------------------------------------------------------------------------
# Enthalpy Calculator
# ---------------------------------------------------------------------------

# Standard enthalpies of formation (kJ/mol) at 298.15 K
STANDARD_ENTHALPIES: dict[str, float] = {
    "H2O": -285.8,
    "CO2": -393.5,
    "H2": 0.0,
    "O2": 0.0,
    "N2": 0.0,
    "C6H12O6": -1274.0,
    "CH4": -74.8,
    "NH3": -45.9,
    "C2H5OH": -277.0,
    "NaCl": -411.2,
}


def compute_enthalpy(
    reactant_formulas: list[str],
    product_formulas: list[str],
    r_coeffs: list[int],
    p_coeffs: list[int],
) -> float:
    """Compute standard reaction enthalpy using Hess's law.

    delta_H = sum(n * Hf_products) - sum(n * Hf_reactants)
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzchemistry import EnthalpyError

    product_sum = 0.0
    for i, formula in enumerate(product_formulas):
        if formula not in STANDARD_ENTHALPIES:
            raise EnthalpyError(
                " + ".join(product_formulas),
                f"No standard enthalpy of formation for '{formula}'",
            )
        product_sum += p_coeffs[i] * STANDARD_ENTHALPIES[formula]

    reactant_sum = 0.0
    for i, formula in enumerate(reactant_formulas):
        if formula not in STANDARD_ENTHALPIES:
            raise EnthalpyError(
                " + ".join(reactant_formulas),
                f"No standard enthalpy of formation for '{formula}'",
            )
        reactant_sum += r_coeffs[i] * STANDARD_ENTHALPIES[formula]

    return product_sum - reactant_sum


# ---------------------------------------------------------------------------
# Molecule
# ---------------------------------------------------------------------------

@dataclass
class Molecule:
    """Represents a molecule with atoms, bonds, and computed properties."""
    formula: str
    atoms: list[Element] = field(default_factory=list)
    bonds: list[MolecularBond] = field(default_factory=list)
    vsepr_shape: Optional[VSEPRShape] = None
    bond_angle: float = 0.0
    molecular_mass: float = 0.0
    enthalpy_of_formation: float = 0.0

    def compute_mass(self) -> float:
        self.molecular_mass = sum(a.atomic_mass for a in self.atoms)
        return self.molecular_mass


# ---------------------------------------------------------------------------
# Chemistry Engine
# ---------------------------------------------------------------------------

class ChemistryEngine:
    """Top-level molecular chemistry simulation engine."""

    FIZZBUZZ_MOLECULES = {
        "Fizz": "H2O",
        "Buzz": "CO2",
        "FizzBuzz": "C6H12O6",
    }

    def __init__(self) -> None:
        self._molecules_analyzed: list[Molecule] = []

    @property
    def molecules_analyzed(self) -> list[Molecule]:
        return list(self._molecules_analyzed)

    def analyze_number(self, number: int, classification: str) -> Molecule:
        """Analyze a FizzBuzz result as a molecular species."""
        formula = self.FIZZBUZZ_MOLECULES.get(classification)

        if formula:
            composition = parse_formula(formula)
            atoms: list[Element] = []
            for sym, count in composition.items():
                elem = PERIODIC_TABLE.get(sym)
                if elem:
                    atoms.extend([elem] * count)

            mol = Molecule(
                formula=formula,
                atoms=atoms,
                enthalpy_of_formation=STANDARD_ENTHALPIES.get(formula, 0.0),
            )
            mol.compute_mass()
        else:
            # Map number to element
            elem = lookup_element_by_number(number % 118 + 1)
            if elem:
                mol = Molecule(
                    formula=elem.symbol,
                    atoms=[elem],
                    molecular_mass=elem.atomic_mass,
                )
            else:
                mol = Molecule(
                    formula=f"X{number}",
                    molecular_mass=float(number),
                )

        self._molecules_analyzed.append(mol)
        return mol

    def get_electron_config_string(self, atomic_number: int) -> str:
        """Return a human-readable electron configuration."""
        config = compute_electron_configuration(atomic_number)
        return " ".join(str(o) for o in config)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class ChemistryMiddleware(IMiddleware):
    """Middleware that performs molecular chemistry analysis on FizzBuzz results.

    Each evaluation result is mapped to a molecular species and analyzed
    for its physicochemical properties. The molecular data is attached to
    the processing context for downstream consumption.

    Priority 282 positions this middleware in the scientific analysis tier.
    """

    def __init__(self) -> None:
        self._engine = ChemistryEngine()
        self._analysis_count = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        classification = "number"
        if result.results:
            classification = result.results[-1].output

        mol = self._engine.analyze_number(number, classification)
        self._analysis_count += 1

        result.metadata["chemistry_formula"] = mol.formula
        result.metadata["chemistry_mass"] = mol.molecular_mass
        result.metadata["chemistry_enthalpy"] = mol.enthalpy_of_formation

        if mol.vsepr_shape:
            result.metadata["chemistry_geometry"] = mol.vsepr_shape.name
            result.metadata["chemistry_bond_angle"] = mol.bond_angle

        return result

    def get_name(self) -> str:
        return "ChemistryMiddleware"

    def get_priority(self) -> int:
        return 282

    @property
    def engine(self) -> ChemistryEngine:
        return self._engine

    @property
    def analysis_count(self) -> int:
        return self._analysis_count
