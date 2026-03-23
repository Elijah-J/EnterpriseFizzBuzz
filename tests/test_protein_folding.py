"""
Enterprise FizzBuzz Platform - FizzFold Protein Folding Test Suite

Comprehensive verification of the ab initio protein structure prediction
pipeline, from amino acid lookup through Monte Carlo simulated annealing
to PDB file generation. These tests ensure that every FizzBuzz output
string is correctly interpreted as a polypeptide and folded into a
thermodynamically plausible three-dimensional conformation.

Protein folding correctness is critical: an incorrectly folded FizzBuzz
peptide could adopt an unphysical conformation, which would undermine
the structural integrity of the enterprise evaluation pipeline.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.protein_folding import (
    AMINO_ACID_TABLE,
    BOLTZMANN_CONSTANT,
    BOND_LENGTH,
    BOND_SPRING_CONSTANT,
    DEFAULT_ALPHA,
    DEFAULT_MC_STEPS,
    DEFAULT_T_MAX,
    DEFAULT_T_MIN,
    HBOND_CUTOFF,
    HBOND_ENERGY,
    HYDROPHOBIC_CUTOFF,
    HYDROPHOBIC_ENERGY,
    LJ_EPSILON,
    LJ_SIGMA,
    AminoAcid,
    Conformation,
    EnergyFunction,
    FoldingDashboard,
    FoldingMiddleware,
    FoldingStatistics,
    MonteCarloFolder,
    PDBWriter,
    Residue,
    Vector3,
    build_extended_chain,
    compute_contact_map,
    compute_rmsd,
    count_contacts,
    count_hydrophobic_contacts,
    fold_fizzbuzz,
    is_hydrophobic,
    lookup_amino_acid,
)
from enterprise_fizzbuzz.domain.exceptions import (
    FizzFoldConvergenceError,
    FizzFoldError,
    FizzFoldSequenceError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def energy_function():
    """Standard energy function with default parameters."""
    return EnergyFunction()


@pytest.fixture
def extended_fizzbuzz():
    """Extended chain for the FIZZBUZZ sequence."""
    return build_extended_chain("FIZZBUZZ")


@pytest.fixture
def short_chain():
    """A short 3-residue chain for focused unit testing."""
    return build_extended_chain("FIZ")


@pytest.fixture
def folder_fast():
    """A MonteCarloFolder configured for fast test execution."""
    return MonteCarloFolder(max_steps=100, seed=42)


@pytest.fixture
def folder_medium():
    """A MonteCarloFolder with 500 steps for convergence testing."""
    return MonteCarloFolder(max_steps=500, seed=42)


# ===========================================================================
# Vector3 tests
# ===========================================================================

class TestVector3:
    """Verification of three-dimensional coordinate arithmetic."""

    def test_default_origin(self):
        v = Vector3()
        assert v.x == 0.0
        assert v.y == 0.0
        assert v.z == 0.0

    def test_distance_to_self(self):
        v = Vector3(1.0, 2.0, 3.0)
        assert v.distance_to(v) == pytest.approx(0.0)

    def test_distance_along_x_axis(self):
        a = Vector3(0.0, 0.0, 0.0)
        b = Vector3(3.8, 0.0, 0.0)
        assert a.distance_to(b) == pytest.approx(3.8)

    def test_distance_3d(self):
        a = Vector3(1.0, 2.0, 3.0)
        b = Vector3(4.0, 6.0, 3.0)
        assert a.distance_to(b) == pytest.approx(5.0)

    def test_addition(self):
        a = Vector3(1.0, 2.0, 3.0)
        b = Vector3(4.0, 5.0, 6.0)
        c = a + b
        assert c.x == pytest.approx(5.0)
        assert c.y == pytest.approx(7.0)
        assert c.z == pytest.approx(9.0)

    def test_subtraction(self):
        a = Vector3(5.0, 5.0, 5.0)
        b = Vector3(1.0, 2.0, 3.0)
        c = a - b
        assert c.x == pytest.approx(4.0)
        assert c.y == pytest.approx(3.0)
        assert c.z == pytest.approx(2.0)

    def test_scalar_multiplication(self):
        v = Vector3(1.0, 2.0, 3.0)
        w = v * 2.0
        assert w.x == pytest.approx(2.0)
        assert w.y == pytest.approx(4.0)
        assert w.z == pytest.approx(6.0)

    def test_length(self):
        v = Vector3(3.0, 4.0, 0.0)
        assert v.length() == pytest.approx(5.0)

    def test_normalized(self):
        v = Vector3(0.0, 0.0, 5.0)
        n = v.normalized()
        assert n.z == pytest.approx(1.0)
        assert n.length() == pytest.approx(1.0)

    def test_normalized_zero_vector(self):
        v = Vector3(0.0, 0.0, 0.0)
        n = v.normalized()
        assert n.length() == pytest.approx(0.0)

    def test_copy(self):
        v = Vector3(1.0, 2.0, 3.0)
        w = v.copy()
        w.x = 99.0
        assert v.x == pytest.approx(1.0)


# ===========================================================================
# AminoAcid tests
# ===========================================================================

class TestAminoAcid:
    """Verification of the amino acid lookup table and properties."""

    def test_fizzbuzz_letters_all_present(self):
        for letter in "FIZBU":
            assert letter in AMINO_ACID_TABLE

    def test_phenylalanine_properties(self):
        aa = AMINO_ACID_TABLE["F"]
        assert aa.single_letter == "F"
        assert aa.three_letter == "PHE"
        assert aa.name == "Phenylalanine"
        assert aa.hydrophobicity > 0

    def test_isoleucine_properties(self):
        aa = AMINO_ACID_TABLE["I"]
        assert aa.single_letter == "I"
        assert aa.three_letter == "ILE"
        assert aa.name == "Isoleucine"
        assert aa.hydrophobicity > 0

    def test_glx_ambiguity_code(self):
        aa = AMINO_ACID_TABLE["Z"]
        assert aa.three_letter == "GLX"
        assert aa.hydrophobicity < 0

    def test_asx_ambiguity_code(self):
        aa = AMINO_ACID_TABLE["B"]
        assert aa.three_letter == "ASX"
        assert aa.hydrophobicity < 0

    def test_selenocysteine(self):
        aa = AMINO_ACID_TABLE["U"]
        assert aa.three_letter == "SEC"
        assert aa.name == "Selenocysteine"

    def test_lookup_valid(self):
        aa = lookup_amino_acid("F")
        assert aa.single_letter == "F"

    def test_lookup_case_insensitive(self):
        aa = lookup_amino_acid("f")
        assert aa.single_letter == "F"

    def test_lookup_invalid_raises(self):
        with pytest.raises(FizzFoldSequenceError):
            lookup_amino_acid("X")

    def test_is_hydrophobic_phe(self):
        assert is_hydrophobic(AMINO_ACID_TABLE["F"]) is True

    def test_is_hydrophobic_ile(self):
        assert is_hydrophobic(AMINO_ACID_TABLE["I"]) is True

    def test_is_not_hydrophobic_glx(self):
        assert is_hydrophobic(AMINO_ACID_TABLE["Z"]) is False

    def test_is_not_hydrophobic_asx(self):
        assert is_hydrophobic(AMINO_ACID_TABLE["B"]) is False

    def test_frozen_dataclass(self):
        aa = AMINO_ACID_TABLE["F"]
        with pytest.raises(AttributeError):
            aa.name = "NotPhenylalanine"

    def test_all_table_entries_have_three_letter_code(self):
        for code, aa in AMINO_ACID_TABLE.items():
            assert len(aa.three_letter) == 3

    def test_molecular_weights_positive(self):
        for aa in AMINO_ACID_TABLE.values():
            assert aa.molecular_weight > 0


# ===========================================================================
# Residue and Conformation tests
# ===========================================================================

class TestResidue:
    """Verification of residue data structures."""

    def test_residue_creation(self):
        aa = lookup_amino_acid("F")
        r = Residue(index=0, amino_acid=aa, position=Vector3(1.0, 2.0, 3.0))
        assert r.index == 0
        assert r.amino_acid.single_letter == "F"
        assert r.position.x == pytest.approx(1.0)

    def test_default_angles(self):
        aa = lookup_amino_acid("I")
        r = Residue(index=1, amino_acid=aa)
        assert r.phi == 0.0
        assert r.psi == 0.0


class TestConformation:
    """Verification of conformation data structures."""

    def test_empty_conformation(self):
        conf = Conformation()
        assert conf.num_residues == 0
        assert conf.sequence == ""

    def test_sequence_property(self, extended_fizzbuzz):
        assert extended_fizzbuzz.sequence == "FIZZBUZZ"

    def test_num_residues(self, extended_fizzbuzz):
        assert extended_fizzbuzz.num_residues == 8

    def test_deep_copy_independence(self, extended_fizzbuzz):
        copy = extended_fizzbuzz.deep_copy()
        copy.residues[0].position.x = 999.0
        assert extended_fizzbuzz.residues[0].position.x != pytest.approx(999.0)

    def test_deep_copy_preserves_energy(self):
        conf = Conformation(total_energy=-5.0, bond_energy=1.0)
        copy = conf.deep_copy()
        assert copy.total_energy == pytest.approx(-5.0)
        assert copy.bond_energy == pytest.approx(1.0)


# ===========================================================================
# Extended chain builder tests
# ===========================================================================

class TestBuildExtendedChain:
    """Verification of the initial extended chain construction."""

    def test_correct_length(self):
        chain = build_extended_chain("FIZZBUZZ")
        assert chain.num_residues == 8

    def test_linear_spacing(self):
        chain = build_extended_chain("FIZZBUZZ")
        for i in range(chain.num_residues):
            assert chain.residues[i].position.x == pytest.approx(i * BOND_LENGTH)
            assert chain.residues[i].position.y == pytest.approx(0.0)
            assert chain.residues[i].position.z == pytest.approx(0.0)

    def test_bond_lengths_ideal(self):
        chain = build_extended_chain("FIZZBUZZ")
        for i in range(chain.num_residues - 1):
            dist = chain.residues[i].position.distance_to(
                chain.residues[i + 1].position
            )
            assert dist == pytest.approx(BOND_LENGTH)

    def test_single_residue(self):
        chain = build_extended_chain("F")
        assert chain.num_residues == 1
        assert chain.residues[0].position.x == pytest.approx(0.0)

    def test_residue_indices(self):
        chain = build_extended_chain("FIZ")
        for i, r in enumerate(chain.residues):
            assert r.index == i

    def test_initial_phi_psi(self):
        chain = build_extended_chain("FI")
        for r in chain.residues:
            assert r.phi == pytest.approx(math.pi)
            assert r.psi == pytest.approx(math.pi)

    def test_invalid_residue_raises(self):
        with pytest.raises(FizzFoldSequenceError):
            build_extended_chain("FIZX")


# ===========================================================================
# RMSD tests
# ===========================================================================

class TestComputeRMSD:
    """Verification of root-mean-square deviation calculation."""

    def test_rmsd_identical(self, extended_fizzbuzz):
        copy = extended_fizzbuzz.deep_copy()
        assert compute_rmsd(extended_fizzbuzz, copy) == pytest.approx(0.0)

    def test_rmsd_shifted(self):
        a = build_extended_chain("FI")
        b = a.deep_copy()
        b.residues[0].position.x += 1.0
        b.residues[1].position.x += 1.0
        assert compute_rmsd(a, b) == pytest.approx(1.0)

    def test_rmsd_different_lengths_raises(self):
        a = build_extended_chain("FI")
        b = build_extended_chain("FIZ")
        with pytest.raises(ValueError):
            compute_rmsd(a, b)

    def test_rmsd_positive(self):
        a = build_extended_chain("FIZZ")
        b = a.deep_copy()
        b.residues[2].position.y += 5.0
        rmsd = compute_rmsd(a, b)
        assert rmsd > 0


# ===========================================================================
# Energy function tests
# ===========================================================================

class TestEnergyFunction:
    """Verification of the protein energy function components."""

    def test_extended_chain_bond_energy_zero(self, energy_function, extended_fizzbuzz):
        """An extended chain with ideal bond lengths has zero bond energy."""
        bond_e = energy_function.compute_bond_energy(extended_fizzbuzz)
        assert bond_e == pytest.approx(0.0, abs=1e-6)

    def test_stretched_bond_positive_energy(self, energy_function):
        chain = build_extended_chain("FI")
        chain.residues[1].position.x += 1.0  # stretch beyond ideal
        bond_e = energy_function.compute_bond_energy(chain)
        assert bond_e > 0

    def test_compressed_bond_positive_energy(self, energy_function):
        chain = build_extended_chain("FI")
        chain.residues[1].position.x -= 1.0  # compress
        bond_e = energy_function.compute_bond_energy(chain)
        assert bond_e > 0

    def test_lj_repulsive_at_close_range(self, energy_function):
        chain = build_extended_chain("FIZ")
        # Move third residue very close to first
        chain.residues[2].position = Vector3(0.5, 0.0, 0.0)
        lj_e = energy_function.compute_lj_energy(chain)
        assert lj_e > 0  # strong repulsion

    def test_lj_attractive_at_medium_range(self, energy_function):
        """LJ potential is attractive near the equilibrium distance."""
        chain = build_extended_chain("FIZ")
        # Place third residue near the LJ minimum (~4.26 A for sigma=3.8)
        chain.residues[2].position = Vector3(4.26, 0.0, 0.0)
        lj_e = energy_function.compute_lj_energy(chain)
        # Should be negative (attractive) for this pair
        assert lj_e < 0

    def test_compute_sets_all_terms(self, energy_function, extended_fizzbuzz):
        energy_function.compute(extended_fizzbuzz)
        assert hasattr(extended_fizzbuzz, 'bond_energy')
        assert hasattr(extended_fizzbuzz, 'lj_energy')
        assert hasattr(extended_fizzbuzz, 'hbond_energy')
        assert hasattr(extended_fizzbuzz, 'hydrophobic_energy')
        assert hasattr(extended_fizzbuzz, 'total_energy')

    def test_total_energy_is_sum(self, energy_function, extended_fizzbuzz):
        energy_function.compute(extended_fizzbuzz)
        expected = (
            extended_fizzbuzz.bond_energy
            + extended_fizzbuzz.lj_energy
            + extended_fizzbuzz.hbond_energy
            + extended_fizzbuzz.hydrophobic_energy
        )
        assert extended_fizzbuzz.total_energy == pytest.approx(expected)

    def test_extended_chain_energy_finite(self, energy_function, extended_fizzbuzz):
        energy_function.compute(extended_fizzbuzz)
        assert math.isfinite(extended_fizzbuzz.total_energy)

    def test_custom_parameters(self):
        ef = EnergyFunction(
            lj_sigma=4.0,
            lj_epsilon=0.2,
            hbond_cutoff=4.0,
            bond_k=50.0,
        )
        chain = build_extended_chain("FI")
        ef.compute(chain)
        assert math.isfinite(chain.total_energy)

    def test_single_residue_energy(self, energy_function):
        chain = build_extended_chain("F")
        energy_function.compute(chain)
        assert chain.total_energy == pytest.approx(0.0)

    def test_hbond_energy_requires_minimum_separation(self, energy_function):
        """H-bonds only form between residues separated by >= 3 positions."""
        chain = build_extended_chain("FI")
        # Only 2 residues, so no H-bonds possible
        energy_function.compute(chain)
        assert chain.hbond_energy == pytest.approx(0.0)

    def test_hydrophobic_energy_between_hydrophobic_residues(self):
        """F and I are both hydrophobic — placing them in contact should yield hydrophobic energy."""
        ef = EnergyFunction()
        chain = build_extended_chain("FIF")
        # Move third residue within hydrophobic cutoff
        chain.residues[2].position = Vector3(6.0, 0.0, 0.0)
        ef.compute(chain)
        # F(0) and F(2) are both hydrophobic and within 7.5A
        assert chain.hydrophobic_energy < 0

    def test_no_hydrophobic_energy_for_polar_pair(self):
        """Z and B are polar — no hydrophobic contact energy should form."""
        ef = EnergyFunction()
        chain = build_extended_chain("ZBZ")
        chain.residues[2].position = Vector3(5.0, 0.0, 0.0)
        ef.compute(chain)
        assert chain.hydrophobic_energy == pytest.approx(0.0)


# ===========================================================================
# Monte Carlo folder tests
# ===========================================================================

class TestMonteCarloFolder:
    """Verification of the simulated annealing protein folder."""

    def test_fold_returns_conformation(self, folder_fast):
        result = folder_fast.fold("FIZZBUZZ")
        assert isinstance(result, Conformation)

    def test_fold_preserves_sequence(self, folder_fast):
        result = folder_fast.fold("FIZZBUZZ")
        assert result.sequence == "FIZZBUZZ"

    def test_fold_preserves_residue_count(self, folder_fast):
        result = folder_fast.fold("FIZZBUZZ")
        assert result.num_residues == 8

    def test_fold_energy_finite(self, folder_fast):
        result = folder_fast.fold("FIZZBUZZ")
        assert math.isfinite(result.total_energy)

    def test_fold_tracks_best(self, folder_fast):
        result = folder_fast.fold("FIZZBUZZ")
        assert folder_fast.best_conformation is not None
        assert folder_fast.best_conformation.total_energy == result.total_energy

    def test_fold_energy_history(self, folder_fast):
        folder_fast.fold("FIZZBUZZ")
        assert len(folder_fast.energy_history) == 101  # initial + 100 steps

    def test_fold_temperature_history(self, folder_fast):
        folder_fast.fold("FIZZBUZZ")
        assert len(folder_fast.temperature_history) == 101

    def test_temperature_decreasing(self, folder_fast):
        folder_fast.fold("FIZZBUZZ")
        temps = folder_fast.temperature_history
        # Temperature should generally decrease
        assert temps[0] >= temps[-1]

    def test_acceptance_rate_between_zero_and_one(self, folder_fast):
        folder_fast.fold("FIZZBUZZ")
        rate = folder_fast.acceptance_rate
        assert 0.0 <= rate <= 1.0

    def test_total_steps(self, folder_fast):
        folder_fast.fold("FIZZBUZZ")
        assert folder_fast.total_steps == 100

    def test_rmsd_computed(self, folder_fast):
        result = folder_fast.fold("FIZZBUZZ")
        assert result.rmsd >= 0.0

    def test_deterministic_with_seed(self):
        f1 = MonteCarloFolder(max_steps=100, seed=123)
        f2 = MonteCarloFolder(max_steps=100, seed=123)
        r1 = f1.fold("FIZZBUZZ")
        r2 = f2.fold("FIZZBUZZ")
        assert r1.total_energy == pytest.approx(r2.total_energy)

    def test_different_seeds_different_results(self):
        f1 = MonteCarloFolder(max_steps=200, seed=1)
        f2 = MonteCarloFolder(max_steps=200, seed=999)
        r1 = f1.fold("FIZZBUZZ")
        r2 = f2.fold("FIZZBUZZ")
        # Extremely unlikely to be identical with different seeds
        assert r1.total_energy != pytest.approx(r2.total_energy, abs=1e-10)

    def test_empty_sequence_raises(self):
        folder = MonteCarloFolder(max_steps=10, seed=42)
        with pytest.raises(FizzFoldSequenceError):
            folder.fold("")

    def test_invalid_sequence_raises(self):
        folder = MonteCarloFolder(max_steps=10, seed=42)
        with pytest.raises(FizzFoldSequenceError):
            folder.fold("FIZXBUZZ")

    def test_short_sequence_folds(self):
        folder = MonteCarloFolder(max_steps=50, seed=42)
        result = folder.fold("FI")
        assert result.num_residues == 2

    def test_fizz_sequence_folds(self):
        folder = MonteCarloFolder(max_steps=100, seed=42)
        result = folder.fold("FIZZ")
        assert result.num_residues == 4
        assert result.sequence == "FIZZ"

    def test_buzz_sequence_folds(self):
        folder = MonteCarloFolder(max_steps=100, seed=42)
        result = folder.fold("BUZZ")
        assert result.num_residues == 4
        assert result.sequence == "BUZZ"

    def test_best_energy_leq_initial(self, folder_medium):
        """The best energy found should be no worse than the initial energy."""
        result = folder_medium.fold("FIZZBUZZ")
        initial_energy = folder_medium.energy_history[0]
        assert result.total_energy <= initial_energy + 1e-6

    def test_custom_temperature_schedule(self):
        folder = MonteCarloFolder(
            max_steps=100, seed=42, t_max=500.0, t_min=0.5, alpha=0.99,
        )
        result = folder.fold("FIZZ")
        assert math.isfinite(result.total_energy)

    def test_move_scale(self):
        folder = MonteCarloFolder(max_steps=100, seed=42, move_scale=0.1)
        result = folder.fold("FIZZ")
        assert math.isfinite(result.total_energy)


# ===========================================================================
# PDB writer tests
# ===========================================================================

class TestPDBWriter:
    """Verification of PDB-format output generation."""

    def test_write_contains_atom_records(self, extended_fizzbuzz):
        pdb = PDBWriter.write(extended_fizzbuzz)
        assert "ATOM" in pdb

    def test_write_contains_title(self, extended_fizzbuzz):
        pdb = PDBWriter.write(extended_fizzbuzz)
        assert "TITLE" in pdb

    def test_write_contains_end(self, extended_fizzbuzz):
        pdb = PDBWriter.write(extended_fizzbuzz)
        assert pdb.strip().endswith("END")

    def test_write_contains_ter(self, extended_fizzbuzz):
        pdb = PDBWriter.write(extended_fizzbuzz)
        assert "TER" in pdb

    def test_write_correct_atom_count(self, extended_fizzbuzz):
        pdb = PDBWriter.write(extended_fizzbuzz)
        atom_lines = [l for l in pdb.split("\n") if l.startswith("ATOM")]
        assert len(atom_lines) == 8

    def test_write_residue_names(self, extended_fizzbuzz):
        pdb = PDBWriter.write(extended_fizzbuzz)
        assert "PHE" in pdb
        assert "ILE" in pdb
        assert "GLX" in pdb
        assert "ASX" in pdb
        assert "SEC" in pdb

    def test_write_custom_title(self, extended_fizzbuzz):
        pdb = PDBWriter.write(extended_fizzbuzz, title="TEST STRUCTURE")
        assert "TEST STRUCTURE" in pdb

    def test_write_contains_remarks(self, extended_fizzbuzz):
        pdb = PDBWriter.write(extended_fizzbuzz)
        assert "REMARK" in pdb
        assert "FIZZFOLD" in pdb

    def test_format_atom_record_length(self):
        record = PDBWriter.format_atom_record(
            serial=1, atom_name="CA", residue_name="PHE",
            chain_id="A", residue_seq=1,
            x=1.0, y=2.0, z=3.0,
        )
        # PDB ATOM records are exactly 80 characters
        assert len(record) == 80

    def test_write_to_file(self, extended_fizzbuzz):
        with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False, mode="w") as f:
            path = f.name
        try:
            PDBWriter.write_to_file(extended_fizzbuzz, path)
            assert os.path.exists(path)
            with open(path, "r") as f:
                content = f.read()
            assert "ATOM" in content
            assert "END" in content
        finally:
            os.unlink(path)

    def test_write_to_file_returns_path(self, extended_fizzbuzz):
        with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False, mode="w") as f:
            path = f.name
        try:
            result = PDBWriter.write_to_file(extended_fizzbuzz, path)
            assert result == path
        finally:
            os.unlink(path)

    def test_chain_id_is_a(self, extended_fizzbuzz):
        pdb = PDBWriter.write(extended_fizzbuzz)
        atom_lines = [l for l in pdb.split("\n") if l.startswith("ATOM")]
        for line in atom_lines:
            assert line[21] == "A"


# ===========================================================================
# Contact map tests
# ===========================================================================

class TestContactMap:
    """Verification of residue-residue contact map computation."""

    def test_extended_chain_contacts(self, extended_fizzbuzz):
        contacts = compute_contact_map(extended_fizzbuzz, cutoff=8.0)
        # Adjacent residues (3.8A apart) should be in contact
        assert contacts[0][1] is True
        assert contacts[1][0] is True

    def test_distant_residues_no_contact(self, extended_fizzbuzz):
        contacts = compute_contact_map(extended_fizzbuzz, cutoff=5.0)
        # First and last residue are 7*3.8 = 26.6A apart
        assert contacts[0][7] is False

    def test_contact_map_symmetric(self, extended_fizzbuzz):
        contacts = compute_contact_map(extended_fizzbuzz)
        n = extended_fizzbuzz.num_residues
        for i in range(n):
            for j in range(n):
                assert contacts[i][j] == contacts[j][i]

    def test_count_contacts_positive(self, extended_fizzbuzz):
        contacts = compute_contact_map(extended_fizzbuzz)
        count = count_contacts(contacts)
        assert count > 0

    def test_hydrophobic_contacts_extended_chain(self, extended_fizzbuzz):
        # In the extended chain, F(0) and I(1) are adjacent hydrophobic
        # residues at 3.8A — within the 7.5A cutoff
        hc = count_hydrophobic_contacts(extended_fizzbuzz)
        assert hc >= 1


# ===========================================================================
# Folding statistics tests
# ===========================================================================

class TestFoldingStatistics:
    """Verification of aggregate folding statistics extraction."""

    def test_from_folder(self, folder_fast):
        conf = folder_fast.fold("FIZZBUZZ")
        stats = FoldingStatistics.from_folder(folder_fast, conf)
        assert stats.sequence == "FIZZBUZZ"
        assert stats.num_residues == 8
        assert stats.total_steps == 100
        assert 0.0 <= stats.acceptance_rate <= 1.0

    def test_energy_breakdown(self, folder_fast):
        conf = folder_fast.fold("FIZZ")
        stats = FoldingStatistics.from_folder(folder_fast, conf)
        total = (
            stats.bond_energy + stats.lj_energy
            + stats.hbond_energy + stats.hydrophobic_energy
        )
        assert stats.best_energy == pytest.approx(total)

    def test_temperature_schedule_recorded(self, folder_fast):
        conf = folder_fast.fold("FI")
        stats = FoldingStatistics.from_folder(folder_fast, conf)
        assert stats.t_max == DEFAULT_T_MAX
        assert stats.t_min == DEFAULT_T_MIN
        assert stats.alpha == DEFAULT_ALPHA


# ===========================================================================
# Dashboard tests
# ===========================================================================

class TestFoldingDashboard:
    """Verification of the ASCII folding dashboard renderer."""

    def test_render_contains_header(self, folder_fast):
        conf = folder_fast.fold("FIZZBUZZ")
        dashboard = FoldingDashboard.render(folder_fast, conf)
        assert "FIZZFOLD" in dashboard

    def test_render_contains_sequence(self, folder_fast):
        conf = folder_fast.fold("FIZZBUZZ")
        dashboard = FoldingDashboard.render(folder_fast, conf)
        assert "FIZZBUZZ" in dashboard

    def test_render_contains_energy(self, folder_fast):
        conf = folder_fast.fold("FIZZBUZZ")
        dashboard = FoldingDashboard.render(folder_fast, conf)
        assert "Energy" in dashboard

    def test_render_contains_contact_map(self, folder_fast):
        conf = folder_fast.fold("FIZZBUZZ")
        dashboard = FoldingDashboard.render(folder_fast, conf)
        assert "Contact Map" in dashboard

    def test_render_contains_statistics(self, folder_fast):
        conf = folder_fast.fold("FIZZBUZZ")
        dashboard = FoldingDashboard.render(folder_fast, conf)
        assert "Acceptance Rate" in dashboard

    def test_render_contains_residue_table(self, folder_fast):
        conf = folder_fast.fold("FIZZBUZZ")
        dashboard = FoldingDashboard.render(folder_fast, conf)
        assert "Phenylalanine" in dashboard

    def test_render_hydrophobicity_annotation(self, folder_fast):
        conf = folder_fast.fold("FIZZBUZZ")
        dashboard = FoldingDashboard.render(folder_fast, conf)
        assert "Hydrophb" in dashboard

    def test_custom_width(self, folder_fast):
        conf = folder_fast.fold("FI")
        dashboard = FoldingDashboard.render(folder_fast, conf, width=80)
        assert len(dashboard) > 0


# ===========================================================================
# Middleware tests
# ===========================================================================

class TestFoldingMiddleware:
    """Verification of the FizzFold middleware pipeline integration."""

    @staticmethod
    def _make_context(number: int, output: str, is_fizz: bool = False, is_buzz: bool = False) -> ProcessingContext:
        matches = []
        if is_fizz:
            fizz_rule = RuleDefinition(name="FizzRule", divisor=3, label="Fizz")
            matches.append(RuleMatch(rule=fizz_rule, number=number))
        if is_buzz:
            buzz_rule = RuleDefinition(name="BuzzRule", divisor=5, label="Buzz")
            matches.append(RuleMatch(rule=buzz_rule, number=number))
        result = FizzBuzzResult(number=number, output=output, matched_rules=matches)
        ctx = ProcessingContext(number=number, session_id="test-session")
        ctx.results.append(result)
        return ctx

    def test_implements_imiddleware(self):
        mw = FoldingMiddleware(max_steps=10)
        assert isinstance(mw, IMiddleware)

    def test_get_name(self):
        mw = FoldingMiddleware(max_steps=10)
        assert mw.get_name() == "FoldingMiddleware"

    def test_get_priority(self):
        mw = FoldingMiddleware(max_steps=10)
        assert mw.get_priority() == 950

    def test_folds_fizzbuzz_output(self):
        mw = FoldingMiddleware(max_steps=50, seed=42)
        ctx = self._make_context(15, "FizzBuzz", is_fizz=True, is_buzz=True)
        result = mw.process(ctx, lambda c: c)
        assert "fold_energy" in result.metadata
        assert "fold_sequence" in result.metadata
        assert result.metadata["fold_sequence"] == "FIZZBUZZ"

    def test_does_not_fold_plain_numbers(self):
        mw = FoldingMiddleware(max_steps=50, seed=42)
        ctx = self._make_context(7, "7")
        result = mw.process(ctx, lambda c: c)
        assert "fold_energy" not in result.metadata

    def test_folds_fizz(self):
        mw = FoldingMiddleware(max_steps=50, seed=42)
        ctx = self._make_context(3, "Fizz", is_fizz=True)
        result = mw.process(ctx, lambda c: c)
        assert "fold_energy" in result.metadata
        assert result.metadata["fold_sequence"] == "FIZZ"

    def test_folds_buzz(self):
        mw = FoldingMiddleware(max_steps=50, seed=42)
        ctx = self._make_context(5, "Buzz", is_buzz=True)
        result = mw.process(ctx, lambda c: c)
        assert "fold_energy" in result.metadata
        assert result.metadata["fold_sequence"] == "BUZZ"

    def test_fold_count_increments(self):
        mw = FoldingMiddleware(max_steps=50, seed=42)
        assert mw.fold_count == 0
        ctx = self._make_context(15, "FizzBuzz", is_fizz=True, is_buzz=True)
        mw.process(ctx, lambda c: c)
        assert mw.fold_count == 1
        ctx2 = self._make_context(3, "Fizz", is_fizz=True)
        mw.process(ctx2, lambda c: c)
        assert mw.fold_count == 2

    def test_total_residues_folded(self):
        mw = FoldingMiddleware(max_steps=50, seed=42)
        ctx = self._make_context(15, "FizzBuzz", is_fizz=True, is_buzz=True)
        mw.process(ctx, lambda c: c)
        assert mw.total_residues_folded == 8

    def test_calls_next_handler(self):
        mw = FoldingMiddleware(max_steps=50, seed=42)
        ctx = self._make_context(7, "7")
        called = [False]
        def handler(c):
            called[0] = True
            return c
        mw.process(ctx, handler)
        assert called[0]

    def test_pdb_output_path(self):
        with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as f:
            path = f.name
        try:
            mw = FoldingMiddleware(max_steps=50, seed=42, pdb_output_path=path)
            ctx = self._make_context(15, "FizzBuzz", is_fizz=True, is_buzz=True)
            result = mw.process(ctx, lambda c: c)
            assert "fold_pdb_path" in result.metadata
        finally:
            # Clean up any generated files
            import glob
            for f in glob.glob(path.replace(".pdb", "*.pdb")):
                try:
                    os.unlink(f)
                except OSError:
                    pass

    def test_last_conformation_stored(self):
        mw = FoldingMiddleware(max_steps=50, seed=42)
        assert mw.last_conformation is None
        ctx = self._make_context(15, "FizzBuzz", is_fizz=True, is_buzz=True)
        mw.process(ctx, lambda c: c)
        assert mw.last_conformation is not None
        assert mw.last_conformation.sequence == "FIZZBUZZ"


# ===========================================================================
# Convenience function tests
# ===========================================================================

class TestFoldFizzBuzz:
    """Verification of the top-level convenience API."""

    def test_fold_fizzbuzz_default(self):
        conf, folder = fold_fizzbuzz(max_steps=100, seed=42)
        assert conf.sequence == "FIZZBUZZ"
        assert conf.num_residues == 8

    def test_fold_fizzbuzz_custom_sequence(self):
        conf, folder = fold_fizzbuzz(sequence="FIZZ", max_steps=100, seed=42)
        assert conf.sequence == "FIZZ"

    def test_fold_fizzbuzz_returns_tuple(self):
        result = fold_fizzbuzz(max_steps=50, seed=42)
        assert isinstance(result, tuple)
        assert len(result) == 2


# ===========================================================================
# Exception tests
# ===========================================================================

class TestFizzFoldExceptions:
    """Verification of the FizzFold exception hierarchy."""

    def test_fizzfold_error_base(self):
        err = FizzFoldError("test error")
        assert "EFP-PF00" in str(err)

    def test_sequence_error(self):
        err = FizzFoldSequenceError("X")
        assert "X" in str(err)
        assert "EFP-PF01" in str(err)
        assert err.invalid_residue == "X"

    def test_convergence_error(self):
        err = FizzFoldConvergenceError("FIZZBUZZ", 100.0, 5000)
        assert "FIZZBUZZ" in str(err)
        assert "EFP-PF02" in str(err)
        assert err.sequence == "FIZZBUZZ"
        assert err.final_energy == 100.0
        assert err.steps == 5000

    def test_hierarchy(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = FizzFoldSequenceError("X")
        assert isinstance(err, FizzFoldError)
        assert isinstance(err, FizzBuzzError)


# ===========================================================================
# Physical constants tests
# ===========================================================================

class TestPhysicalConstants:
    """Verification that physical constants are within accepted ranges."""

    def test_boltzmann_constant(self):
        assert BOLTZMANN_CONSTANT == pytest.approx(0.001987, rel=1e-3)

    def test_bond_length(self):
        assert BOND_LENGTH == pytest.approx(3.8)

    def test_lj_sigma(self):
        assert LJ_SIGMA == pytest.approx(3.8)

    def test_lj_epsilon(self):
        assert LJ_EPSILON == pytest.approx(0.1)

    def test_hbond_cutoff(self):
        assert HBOND_CUTOFF == pytest.approx(3.5)

    def test_hbond_energy_negative(self):
        assert HBOND_ENERGY < 0

    def test_hydrophobic_energy_negative(self):
        assert HYDROPHOBIC_ENERGY < 0


# ===========================================================================
# Integration tests
# ===========================================================================

class TestIntegration:
    """End-to-end integration tests for the folding pipeline."""

    def test_full_pipeline_fizzbuzz(self):
        """Fold FIZZBUZZ, verify PDB output, check energy is finite."""
        conf, folder = fold_fizzbuzz(max_steps=200, seed=42)
        pdb = PDBWriter.write(conf)
        assert "FIZZBUZZ" in pdb
        assert math.isfinite(conf.total_energy)
        assert conf.rmsd >= 0

    def test_full_pipeline_fizz(self):
        conf, folder = fold_fizzbuzz(sequence="FIZZ", max_steps=100, seed=42)
        assert conf.sequence == "FIZZ"
        assert conf.num_residues == 4

    def test_full_pipeline_buzz(self):
        conf, folder = fold_fizzbuzz(sequence="BUZZ", max_steps=100, seed=42)
        assert conf.sequence == "BUZZ"
        assert conf.num_residues == 4

    def test_dashboard_after_fold(self):
        conf, folder = fold_fizzbuzz(max_steps=100, seed=42)
        dashboard = FoldingDashboard.render(folder, conf)
        assert "FIZZFOLD" in dashboard
        assert "FIZZBUZZ" in dashboard

    def test_pdb_round_trip(self):
        """Write PDB to disk and verify it can be read back."""
        conf, _ = fold_fizzbuzz(max_steps=100, seed=42)
        with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False, mode="w") as f:
            path = f.name
        try:
            PDBWriter.write_to_file(conf, path)
            with open(path, "r") as f:
                content = f.read()
            atom_lines = [l for l in content.split("\n") if l.startswith("ATOM")]
            assert len(atom_lines) == 8
        finally:
            os.unlink(path)
