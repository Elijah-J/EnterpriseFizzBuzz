"""
Enterprise FizzBuzz Platform - FizzQuantumChem Quantum Chemistry Test Suite

Comprehensive verification of the quantum chemistry engine, including
basis set construction, overlap and kinetic integrals, SCF convergence,
molecular orbital analysis, nuclear repulsion, and energy minimization.

Quantum mechanical accuracy is critical: the electronic structure of
FizzBuzz molecules determines their optical absorption spectra, which
directly affects how FizzBuzz classification results appear on quantum-dot
displays. An error of even one milliHartree in the total energy could
shift the HOMO-LUMO gap enough to alter the perceived color of a
"FizzBuzz" label from gold to yellow-green.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzquantumchem import (
    ATOMIC_NUMBERS,
    BOHR_TO_ANGSTROM,
    HARTREE_TO_EV,
    HARTREE_TO_KCAL,
    MOLECULES,
    SCF_DEFAULT_MAX_ITER,
    SCF_DEFAULT_THRESHOLD,
    STO_3G_DATA,
    BasisFunction,
    BasisSetType,
    GaussianPrimitive,
    GeometryOptimizer,
    HartreeFockSolver,
    MolecularOrbital,
    OrbitalSymmetry,
    QuantumChemEngine,
    QuantumChemMiddleware,
    SCFResult,
    build_basis_set,
    build_kinetic_matrix,
    build_overlap_matrix,
    compute_nuclear_repulsion,
    kinetic_integral,
    mat_add,
    mat_identity,
    mat_multiply,
    mat_scale,
    mat_trace,
    overlap_1d,
    overlap_integral,
)
from enterprise_fizzbuzz.domain.exceptions.fizzquantumchem import (
    BasisSetError,
    ElectronIntegralError,
    EnergyMinimizationError,
    FizzQuantumChemError,
    MolecularOrbitalError,
    QuantumChemMiddlewareError,
    SCFConvergenceError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def h2_basis():
    symbols = ["H", "H"]
    positions = [(0.0, 0.0, 0.0), (1.4, 0.0, 0.0)]
    return build_basis_set(symbols, positions)


@pytest.fixture
def solver():
    return HartreeFockSolver(max_iterations=100, convergence_threshold=1e-6)


@pytest.fixture
def engine():
    return QuantumChemEngine()


# ===========================================================================
# Gaussian Primitive Tests
# ===========================================================================

class TestGaussianPrimitive:
    """Verification of Gaussian basis function data structures."""

    def test_primitive_creation(self):
        g = GaussianPrimitive(alpha=3.42, coefficient=0.15)
        assert g.alpha == pytest.approx(3.42)
        assert g.coefficient == pytest.approx(0.15)

    def test_sto3g_hydrogen_data(self):
        assert "H_1s" in STO_3G_DATA
        assert len(STO_3G_DATA["H_1s"]) == 3

    def test_sto3g_carbon_data(self):
        assert "C_1s" in STO_3G_DATA
        assert "C_2s" in STO_3G_DATA
        assert "C_2p" in STO_3G_DATA


# ===========================================================================
# Basis Set Tests
# ===========================================================================

class TestBasisSet:
    """Verification of basis set construction."""

    def test_h2_basis_size(self, h2_basis):
        # H2 with STO-3G: 1 function per H = 2 total
        assert len(h2_basis) == 2

    def test_basis_function_has_primitives(self, h2_basis):
        for bf in h2_basis:
            assert bf.num_primitives == 3  # STO-3G has 3 primitives

    def test_unsupported_basis_raises(self):
        with pytest.raises(BasisSetError):
            build_basis_set(["H"], [(0.0, 0.0, 0.0)], BasisSetType.THREE_21G)

    def test_unsupported_element_raises(self):
        with pytest.raises(BasisSetError):
            build_basis_set(["Xe"], [(0.0, 0.0, 0.0)])


# ===========================================================================
# Integral Tests
# ===========================================================================

class TestIntegrals:
    """Verification of one-electron integral evaluation."""

    def test_overlap_1d_same_center(self):
        s = overlap_1d(1.0, 1.0, 0.0, 0.0)
        assert s > 0

    def test_overlap_1d_decreases_with_distance(self):
        s_near = overlap_1d(1.0, 1.0, 0.0, 0.5)
        s_far = overlap_1d(1.0, 1.0, 0.0, 5.0)
        assert s_near > s_far

    def test_overlap_matrix_diagonal_positive(self, h2_basis):
        S = build_overlap_matrix(h2_basis)
        for i in range(len(h2_basis)):
            assert S[i][i] > 0

    def test_overlap_matrix_symmetric(self, h2_basis):
        S = build_overlap_matrix(h2_basis)
        n = len(S)
        for i in range(n):
            for j in range(n):
                assert S[i][j] == pytest.approx(S[j][i], abs=1e-10)

    def test_kinetic_matrix_diagonal_positive(self, h2_basis):
        T = build_kinetic_matrix(h2_basis)
        for i in range(len(h2_basis)):
            assert T[i][i] > 0


# ===========================================================================
# Matrix Utility Tests
# ===========================================================================

class TestMatrixUtilities:
    """Verification of matrix arithmetic operations."""

    def test_identity_matrix(self):
        I = mat_identity(3)
        assert I[0][0] == 1.0
        assert I[0][1] == 0.0
        assert I[2][2] == 1.0

    def test_mat_add(self):
        A = [[1.0, 2.0], [3.0, 4.0]]
        B = [[5.0, 6.0], [7.0, 8.0]]
        C = mat_add(A, B)
        assert C[0][0] == pytest.approx(6.0)
        assert C[1][1] == pytest.approx(12.0)

    def test_mat_scale(self):
        A = [[1.0, 2.0], [3.0, 4.0]]
        B = mat_scale(A, 2.0)
        assert B[0][0] == pytest.approx(2.0)
        assert B[1][1] == pytest.approx(8.0)

    def test_mat_trace(self):
        A = [[1.0, 0.0], [0.0, 3.0]]
        assert mat_trace(A) == pytest.approx(4.0)

    def test_mat_multiply(self):
        I = mat_identity(2)
        A = [[1.0, 2.0], [3.0, 4.0]]
        result = mat_multiply(I, A)
        assert result[0][0] == pytest.approx(1.0)
        assert result[1][1] == pytest.approx(4.0)


# ===========================================================================
# Nuclear Repulsion Tests
# ===========================================================================

class TestNuclearRepulsion:
    """Verification of nuclear-nuclear Coulomb repulsion."""

    def test_h2_repulsion_positive(self):
        energy = compute_nuclear_repulsion([1, 1], [(0.0, 0.0, 0.0), (1.4, 0.0, 0.0)])
        assert energy > 0

    def test_repulsion_increases_with_charge(self):
        e_hh = compute_nuclear_repulsion([1, 1], [(0.0, 0.0, 0.0), (1.4, 0.0, 0.0)])
        e_cc = compute_nuclear_repulsion([6, 6], [(0.0, 0.0, 0.0), (1.4, 0.0, 0.0)])
        assert e_cc > e_hh

    def test_repulsion_decreases_with_distance(self):
        e_near = compute_nuclear_repulsion([1, 1], [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)])
        e_far = compute_nuclear_repulsion([1, 1], [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)])
        assert e_near > e_far


# ===========================================================================
# SCF Solver Tests
# ===========================================================================

class TestSCFSolver:
    """Verification of the Hartree-Fock SCF procedure."""

    def test_h2_converges(self, solver, h2_basis):
        nuc_rep = compute_nuclear_repulsion([1, 1], [(0.0, 0.0, 0.0), (1.4, 0.0, 0.0)])
        result = solver.solve(h2_basis, num_electrons=2, nuclear_repulsion=nuc_rep)
        assert result.converged is True

    def test_scf_result_has_orbitals(self, solver, h2_basis):
        nuc_rep = compute_nuclear_repulsion([1, 1], [(0.0, 0.0, 0.0), (1.4, 0.0, 0.0)])
        result = solver.solve(h2_basis, num_electrons=2, nuclear_repulsion=nuc_rep)
        assert len(result.molecular_orbitals) == 2

    def test_homo_lumo_gap(self, solver, h2_basis):
        nuc_rep = compute_nuclear_repulsion([1, 1], [(0.0, 0.0, 0.0), (1.4, 0.0, 0.0)])
        result = solver.solve(h2_basis, num_electrons=2, nuclear_repulsion=nuc_rep)
        assert result.homo_lumo_gap_ev != 0.0

    def test_energy_in_ev(self, solver, h2_basis):
        nuc_rep = compute_nuclear_repulsion([1, 1], [(0.0, 0.0, 0.0), (1.4, 0.0, 0.0)])
        result = solver.solve(h2_basis, num_electrons=2, nuclear_repulsion=nuc_rep)
        assert result.total_energy_ev == pytest.approx(
            result.total_energy_hartree * HARTREE_TO_EV
        )

    def test_empty_basis_raises(self, solver):
        with pytest.raises(SCFConvergenceError):
            solver.solve([], num_electrons=2)


# ===========================================================================
# Molecular Orbital Tests
# ===========================================================================

class TestMolecularOrbital:
    """Verification of molecular orbital data structures."""

    def test_orbital_energy_conversion(self):
        mo = MolecularOrbital(
            index=0,
            energy_hartree=-0.5,
            coefficients=[1.0],
            occupied=True,
        )
        assert mo.energy_ev == pytest.approx(-0.5 * HARTREE_TO_EV)
        assert mo.energy_kcal == pytest.approx(-0.5 * HARTREE_TO_KCAL)


# ===========================================================================
# Quantum Chemistry Engine Tests
# ===========================================================================

class TestQuantumChemEngine:
    """Verification of the top-level quantum chemistry engine."""

    def test_compute_h2(self, engine):
        result = engine.compute("H2")
        assert result.converged is True
        assert result.total_energy_hartree != 0.0

    def test_compute_unknown_molecule_raises(self, engine):
        with pytest.raises(BasisSetError):
            engine.compute("XYZ123")

    def test_analyze_fizzbuzz(self, engine):
        result = engine.analyze_fizzbuzz(15, "FizzBuzz")
        assert result.converged is True

    def test_results_tracked(self, engine):
        engine.compute("H2")
        assert len(engine.results) == 1


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestQuantumChemMiddleware:
    """Verification of the QuantumChemMiddleware pipeline integration."""

    def test_middleware_name(self):
        mw = QuantumChemMiddleware()
        assert mw.get_name() == "QuantumChemMiddleware"

    def test_middleware_priority(self):
        mw = QuantumChemMiddleware()
        assert mw.get_priority() == 285

    def test_middleware_attaches_metadata(self):
        mw = QuantumChemMiddleware()

        ctx = ProcessingContext(number=15, session_id="test-session")
        result_ctx = ProcessingContext(number=15, session_id="test-session")
        result_ctx.results = [
            FizzBuzzResult(
                number=15,
                output="FizzBuzz",
            )
        ]

        def next_handler(c):
            return result_ctx

        output = mw.process(ctx, next_handler)
        assert "quantumchem_energy_hartree" in output.metadata
        assert "quantumchem_converged" in output.metadata
        assert output.metadata["quantumchem_converged"] is True
        assert mw.computation_count == 1
