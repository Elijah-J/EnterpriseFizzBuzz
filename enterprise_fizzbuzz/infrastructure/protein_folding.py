"""
Enterprise FizzBuzz Platform - FizzFold Protein Folding Simulator

Interprets FizzBuzz output strings as amino acid sequences and performs
ab initio protein structure prediction using Monte Carlo simulated annealing
with a physically motivated energy function.

The FizzBuzz evaluation pipeline produces strings containing the characters
F, I, Z, B, and U — each of which maps to a standard amino acid via the
IUPAC single-letter code. This module treats those strings as polypeptide
chains, folds them into three-dimensional conformations, and reports the
minimum-energy structure in PDB format.

The energy function includes Lennard-Jones van der Waals interactions,
backbone hydrogen bonding, hydrophobic contact potentials, and harmonic
bond-length restraints. The Metropolis criterion ensures that the search
explores thermodynamically accessible conformations while converging
toward the global free-energy minimum.

For an 8-residue peptide such as "FIZZBUZZ", the conformational search
space contains approximately 10^12 accessible states. The simulated
annealing schedule is calibrated to reliably find near-native structures
within 10,000 Monte Carlo steps for sequences of this length.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

BOLTZMANN_CONSTANT = 0.001987  # kcal/(mol*K)
BOND_LENGTH = 3.8  # Angstroms — standard C-alpha spacing
LJ_SIGMA = 3.8  # Angstroms — van der Waals radius
LJ_EPSILON = 0.1  # kcal/mol — well depth
HBOND_CUTOFF = 3.5  # Angstroms — maximum donor-acceptor distance
HBOND_ENERGY = -2.0  # kcal/mol — per hydrogen bond
HYDROPHOBIC_CUTOFF = 7.5  # Angstroms — hydrophobic contact distance
HYDROPHOBIC_ENERGY = -1.0  # kcal/mol — per hydrophobic contact
BOND_SPRING_CONSTANT = 100.0  # kcal/(mol*A^2) — harmonic restraint

# Annealing schedule defaults
DEFAULT_T_MAX = 1000.0  # Kelvin
DEFAULT_T_MIN = 1.0  # Kelvin
DEFAULT_ALPHA = 0.995  # geometric cooling factor
DEFAULT_MC_STEPS = 10000  # total Monte Carlo steps


# ---------------------------------------------------------------------------
# Amino acid database
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AminoAcid:
    """Represents a single amino acid species with its biophysical properties.

    Attributes:
        single_letter: IUPAC one-letter code (e.g. 'F' for phenylalanine).
        three_letter: Standard three-letter abbreviation (e.g. 'PHE').
        name: Full chemical name.
        hydrophobicity: Kyte-Doolittle hydrophobicity index. Positive values
            indicate hydrophobic residues that prefer the protein interior.
        charge: Net charge at physiological pH (7.4).
        molecular_weight: Daltons.
    """
    single_letter: str
    three_letter: str
    name: str
    hydrophobicity: float
    charge: float
    molecular_weight: float


# The five amino acids that appear in FizzBuzz output strings, plus common
# residues for completeness of the lookup table.
AMINO_ACID_TABLE: dict[str, AminoAcid] = {
    "F": AminoAcid("F", "PHE", "Phenylalanine", 2.8, 0.0, 165.19),
    "I": AminoAcid("I", "ILE", "Isoleucine", 4.5, 0.0, 131.17),
    "Z": AminoAcid("Z", "GLX", "Glutamine/Glutamic acid", -3.5, -0.5, 146.15),
    "B": AminoAcid("B", "ASX", "Asparagine/Aspartic acid", -3.5, -0.5, 132.12),
    "U": AminoAcid("U", "SEC", "Selenocysteine", 2.5, 0.0, 168.06),
    "A": AminoAcid("A", "ALA", "Alanine", 1.8, 0.0, 89.09),
    "G": AminoAcid("G", "GLY", "Glycine", -0.4, 0.0, 75.03),
    "L": AminoAcid("L", "LEU", "Leucine", 3.8, 0.0, 131.17),
    "V": AminoAcid("V", "VAL", "Valine", 4.2, 0.0, 117.15),
    "P": AminoAcid("P", "PRO", "Proline", -1.6, 0.0, 115.13),
}


def lookup_amino_acid(letter: str) -> AminoAcid:
    """Resolve a single-letter code to its AminoAcid record.

    Raises FizzFoldSequenceError if the letter is not recognized.
    """
    from enterprise_fizzbuzz.domain.exceptions import FizzFoldSequenceError
    upper = letter.upper()
    if upper not in AMINO_ACID_TABLE:
        raise FizzFoldSequenceError(upper)
    return AMINO_ACID_TABLE[upper]


def is_hydrophobic(aa: AminoAcid) -> bool:
    """Return True if the residue is classified as hydrophobic."""
    return aa.hydrophobicity > 0.0


# ---------------------------------------------------------------------------
# 3D coordinate and residue types
# ---------------------------------------------------------------------------

@dataclass
class Vector3:
    """Three-dimensional Cartesian coordinate."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def distance_to(self, other: Vector3) -> float:
        """Euclidean distance to another point."""
        dx = self.x - other.x
        dy = self.y - other.y
        dz = self.z - other.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def __add__(self, other: Vector3) -> Vector3:
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vector3) -> Vector3:
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vector3:
        return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> Vector3:
        mag = self.length()
        if mag < 1e-12:
            return Vector3(0.0, 0.0, 0.0)
        return Vector3(self.x / mag, self.y / mag, self.z / mag)

    def copy(self) -> Vector3:
        return Vector3(self.x, self.y, self.z)


@dataclass
class Residue:
    """A single amino acid residue at a specific position in the chain.

    Attributes:
        index: Zero-based position in the polypeptide sequence.
        amino_acid: The amino acid species at this position.
        position: Three-dimensional coordinates of the C-alpha atom.
        phi: Backbone dihedral angle phi (radians).
        psi: Backbone dihedral angle psi (radians).
    """
    index: int
    amino_acid: AminoAcid
    position: Vector3 = field(default_factory=Vector3)
    phi: float = 0.0
    psi: float = 0.0


@dataclass
class Conformation:
    """A complete three-dimensional arrangement of all residues.

    Attributes:
        residues: Ordered list of residue positions.
        total_energy: Sum of all energy terms (kcal/mol).
        bond_energy: Harmonic bond-length restraint energy.
        lj_energy: Lennard-Jones van der Waals energy.
        hbond_energy: Hydrogen bond energy.
        hydrophobic_energy: Hydrophobic contact energy.
        rmsd: Root-mean-square deviation from the initial extended chain.
        step: Monte Carlo step at which this conformation was recorded.
    """
    residues: list[Residue] = field(default_factory=list)
    total_energy: float = 0.0
    bond_energy: float = 0.0
    lj_energy: float = 0.0
    hbond_energy: float = 0.0
    hydrophobic_energy: float = 0.0
    rmsd: float = 0.0
    step: int = 0

    @property
    def num_residues(self) -> int:
        return len(self.residues)

    @property
    def sequence(self) -> str:
        """Single-letter amino acid sequence."""
        return "".join(r.amino_acid.single_letter for r in self.residues)

    def deep_copy(self) -> Conformation:
        """Create an independent copy of this conformation."""
        new_residues = []
        for r in self.residues:
            new_residues.append(Residue(
                index=r.index,
                amino_acid=r.amino_acid,
                position=r.position.copy(),
                phi=r.phi,
                psi=r.psi,
            ))
        return Conformation(
            residues=new_residues,
            total_energy=self.total_energy,
            bond_energy=self.bond_energy,
            lj_energy=self.lj_energy,
            hbond_energy=self.hbond_energy,
            hydrophobic_energy=self.hydrophobic_energy,
            rmsd=self.rmsd,
            step=self.step,
        )


# ---------------------------------------------------------------------------
# Energy function
# ---------------------------------------------------------------------------

class EnergyFunction:
    """Computes the total potential energy of a protein conformation.

    The energy function is a sum of four terms:

    1. **Bond energy** — Harmonic restraints that penalize deviations from
       the ideal C-alpha spacing of 3.8 Angstroms. This prevents the chain
       from fragmenting during Monte Carlo moves.

    2. **Lennard-Jones energy** — The 12-6 potential models short-range
       Pauli repulsion (r^-12) and long-range van der Waals attraction
       (r^-6) between all non-bonded residue pairs.

    3. **Hydrogen bond energy** — A distance-dependent step function that
       awards -2.0 kcal/mol for each pair of backbone atoms within 3.5
       Angstroms, modeling the stabilizing effect of secondary structure
       formation.

    4. **Hydrophobic energy** — A contact potential that awards -1.0
       kcal/mol for each pair of hydrophobic residues within 7.5 Angstroms,
       driving the hydrophobic collapse that is the first step of folding.
    """

    def __init__(
        self,
        lj_sigma: float = LJ_SIGMA,
        lj_epsilon: float = LJ_EPSILON,
        hbond_cutoff: float = HBOND_CUTOFF,
        hbond_energy: float = HBOND_ENERGY,
        hydrophobic_cutoff: float = HYDROPHOBIC_CUTOFF,
        hydrophobic_energy: float = HYDROPHOBIC_ENERGY,
        bond_length: float = BOND_LENGTH,
        bond_k: float = BOND_SPRING_CONSTANT,
    ) -> None:
        self._lj_sigma = lj_sigma
        self._lj_epsilon = lj_epsilon
        self._hbond_cutoff = hbond_cutoff
        self._hbond_energy = hbond_energy
        self._hydrophobic_cutoff = hydrophobic_cutoff
        self._hydrophobic_energy = hydrophobic_energy
        self._bond_length = bond_length
        self._bond_k = bond_k

    def compute(self, conformation: Conformation) -> Conformation:
        """Evaluate all energy terms and update the conformation in place."""
        residues = conformation.residues
        n = len(residues)

        bond_e = 0.0
        lj_e = 0.0
        hbond_e = 0.0
        hydro_e = 0.0

        # Bond energy: consecutive residues
        for i in range(n - 1):
            r = residues[i].position.distance_to(residues[i + 1].position)
            dr = r - self._bond_length
            bond_e += self._bond_k * dr * dr

        # Pairwise non-bonded interactions
        for i in range(n):
            for j in range(i + 2, n):
                r = residues[i].position.distance_to(residues[j].position)
                if r < 1e-6:
                    r = 1e-6  # prevent division by zero

                # Lennard-Jones
                ratio = self._lj_sigma / r
                ratio6 = ratio ** 6
                ratio12 = ratio6 * ratio6
                lj_e += 4.0 * self._lj_epsilon * (ratio12 - ratio6)

                # Hydrogen bonds (backbone i,j with |i-j| >= 3)
                if abs(i - j) >= 3 and r < self._hbond_cutoff:
                    hbond_e += self._hbond_energy

                # Hydrophobic contacts
                if (is_hydrophobic(residues[i].amino_acid)
                        and is_hydrophobic(residues[j].amino_acid)
                        and r < self._hydrophobic_cutoff):
                    hydro_e += self._hydrophobic_energy

        conformation.bond_energy = bond_e
        conformation.lj_energy = lj_e
        conformation.hbond_energy = hbond_e
        conformation.hydrophobic_energy = hydro_e
        conformation.total_energy = bond_e + lj_e + hbond_e + hydro_e
        return conformation

    def compute_bond_energy(self, conformation: Conformation) -> float:
        """Compute only the bond-length restraint energy."""
        residues = conformation.residues
        total = 0.0
        for i in range(len(residues) - 1):
            r = residues[i].position.distance_to(residues[i + 1].position)
            dr = r - self._bond_length
            total += self._bond_k * dr * dr
        return total

    def compute_lj_energy(self, conformation: Conformation) -> float:
        """Compute only the Lennard-Jones energy."""
        residues = conformation.residues
        n = len(residues)
        total = 0.0
        for i in range(n):
            for j in range(i + 2, n):
                r = residues[i].position.distance_to(residues[j].position)
                if r < 1e-6:
                    r = 1e-6
                ratio = self._lj_sigma / r
                ratio6 = ratio ** 6
                ratio12 = ratio6 * ratio6
                total += 4.0 * self._lj_epsilon * (ratio12 - ratio6)
        return total


# ---------------------------------------------------------------------------
# Chain builder
# ---------------------------------------------------------------------------

def build_extended_chain(sequence: str) -> Conformation:
    """Construct an extended (fully linear) chain along the x-axis.

    Each residue is placed at (i * 3.8, 0, 0), representing the fully
    denatured state with no secondary or tertiary structure.
    """
    residues = []
    for i, letter in enumerate(sequence):
        aa = lookup_amino_acid(letter)
        residues.append(Residue(
            index=i,
            amino_acid=aa,
            position=Vector3(x=i * BOND_LENGTH, y=0.0, z=0.0),
            phi=math.pi,
            psi=math.pi,
        ))
    return Conformation(residues=residues, step=0)


def compute_rmsd(conf_a: Conformation, conf_b: Conformation) -> float:
    """Compute the root-mean-square deviation between two conformations.

    Both conformations must have the same number of residues. RMSD is
    calculated over C-alpha positions without superposition — this is the
    naive RMSD, appropriate for monitoring structural drift during folding
    rather than for structural alignment.
    """
    if conf_a.num_residues != conf_b.num_residues:
        raise ValueError(
            f"Cannot compute RMSD: conformations have different lengths "
            f"({conf_a.num_residues} vs {conf_b.num_residues})"
        )
    total = 0.0
    for ra, rb in zip(conf_a.residues, conf_b.residues):
        dx = ra.position.x - rb.position.x
        dy = ra.position.y - rb.position.y
        dz = ra.position.z - rb.position.z
        total += dx * dx + dy * dy + dz * dz
    return math.sqrt(total / max(conf_a.num_residues, 1))


# ---------------------------------------------------------------------------
# Monte Carlo folder
# ---------------------------------------------------------------------------

class MonteCarloFolder:
    """Simulated annealing protein structure predictor.

    Uses the Metropolis criterion to accept or reject random conformational
    moves at each temperature step. The temperature schedule follows a
    geometric cooling law: T(n+1) = alpha * T(n), starting from T_max and
    decreasing toward T_min.

    At high temperatures, the search is exploratory and uphill moves are
    frequently accepted. As the temperature decreases, the search becomes
    increasingly greedy, converging on low-energy conformations. The best
    conformation observed across the entire trajectory is retained.

    Move strategy: at each step, a random residue is selected and its
    backbone dihedral angles (phi, psi) are perturbed by a random delta.
    The new C-alpha position is reconstructed from the perturbed angles,
    and the energy is re-evaluated.
    """

    def __init__(
        self,
        energy_function: Optional[EnergyFunction] = None,
        t_max: float = DEFAULT_T_MAX,
        t_min: float = DEFAULT_T_MIN,
        alpha: float = DEFAULT_ALPHA,
        max_steps: int = DEFAULT_MC_STEPS,
        seed: Optional[int] = None,
        move_scale: float = 1.0,
    ) -> None:
        self._energy = energy_function or EnergyFunction()
        self._t_max = t_max
        self._t_min = t_min
        self._alpha = alpha
        self._max_steps = max_steps
        self._rng = random.Random(seed)
        self._move_scale = move_scale

        # Trajectory recording
        self._energy_history: list[float] = []
        self._temperature_history: list[float] = []
        self._accept_count = 0
        self._reject_count = 0
        self._best: Optional[Conformation] = None

    @property
    def energy_history(self) -> list[float]:
        """Energy at each Monte Carlo step."""
        return list(self._energy_history)

    @property
    def temperature_history(self) -> list[float]:
        """Temperature at each Monte Carlo step."""
        return list(self._temperature_history)

    @property
    def acceptance_rate(self) -> float:
        """Fraction of moves that were accepted."""
        total = self._accept_count + self._reject_count
        return self._accept_count / max(total, 1)

    @property
    def best_conformation(self) -> Optional[Conformation]:
        """The lowest-energy conformation observed during the trajectory."""
        return self._best

    @property
    def total_steps(self) -> int:
        return self._accept_count + self._reject_count

    def _perturb(self, conformation: Conformation) -> Conformation:
        """Apply a random backbone perturbation to one residue.

        Selects a residue at random, perturbs its phi/psi angles, and
        reconstructs the downstream chain positions using the new angles.
        """
        trial = conformation.deep_copy()
        n = trial.num_residues
        if n < 2:
            return trial

        # Pick a random residue (not the first — it's anchored)
        idx = self._rng.randint(1, n - 1)

        # Perturb angles
        delta_phi = self._rng.gauss(0, 0.5 * self._move_scale)
        delta_psi = self._rng.gauss(0, 0.5 * self._move_scale)
        trial.residues[idx].phi += delta_phi
        trial.residues[idx].psi += delta_psi

        # Reconstruct positions downstream from the perturbed residue.
        # Each residue is placed at bond_length distance from the previous
        # one, with direction determined by phi/psi angles.
        for i in range(idx, n):
            if i == 0:
                continue
            prev = trial.residues[i - 1].position
            phi = trial.residues[i].phi
            psi = trial.residues[i].psi

            dx = BOND_LENGTH * math.cos(phi) * math.cos(psi)
            dy = BOND_LENGTH * math.sin(phi) * math.cos(psi)
            dz = BOND_LENGTH * math.sin(psi)

            trial.residues[i].position = Vector3(
                prev.x + dx,
                prev.y + dy,
                prev.z + dz,
            )

        return trial

    def fold(self, sequence: str) -> Conformation:
        """Perform simulated annealing on the given amino acid sequence.

        Args:
            sequence: Single-letter amino acid codes (e.g. "FIZZBUZZ").

        Returns:
            The lowest-energy conformation discovered during the annealing
            trajectory.
        """
        from enterprise_fizzbuzz.domain.exceptions import (
            FizzFoldConvergenceError,
            FizzFoldSequenceError,
        )

        if not sequence:
            raise FizzFoldSequenceError("(empty)")

        # Validate all residues
        for ch in sequence:
            lookup_amino_acid(ch)

        # Initialize extended chain
        current = build_extended_chain(sequence)
        initial = current.deep_copy()
        self._energy.compute(current)

        self._best = current.deep_copy()
        self._energy_history = [current.total_energy]
        self._temperature_history = [self._t_max]
        self._accept_count = 0
        self._reject_count = 0

        temperature = self._t_max

        for step in range(1, self._max_steps + 1):
            # Propose a new conformation
            trial = self._perturb(current)
            self._energy.compute(trial)

            # Metropolis criterion
            delta_e = trial.total_energy - current.total_energy
            accept = False

            if delta_e < 0:
                accept = True
            else:
                if temperature > 1e-10:
                    probability = math.exp(-delta_e / (BOLTZMANN_CONSTANT * temperature))
                    if self._rng.random() < probability:
                        accept = True

            if accept:
                current = trial
                self._accept_count += 1
            else:
                self._reject_count += 1

            # Track best
            if current.total_energy < self._best.total_energy:
                self._best = current.deep_copy()
                self._best.step = step
                self._best.rmsd = compute_rmsd(initial, self._best)

            # Record history
            self._energy_history.append(current.total_energy)
            self._temperature_history.append(temperature)

            # Cool
            temperature = max(temperature * self._alpha, self._t_min)

        # Finalize RMSD on best conformation
        self._best.rmsd = compute_rmsd(initial, self._best)

        logger.info(
            "Folding complete: sequence=%s steps=%d best_energy=%.3f "
            "acceptance_rate=%.3f rmsd=%.3f",
            sequence, self._max_steps, self._best.total_energy,
            self.acceptance_rate, self._best.rmsd,
        )

        return self._best


# ---------------------------------------------------------------------------
# PDB writer
# ---------------------------------------------------------------------------

class PDBWriter:
    """Writes protein conformations in the Protein Data Bank (PDB) format.

    The PDB format is the standard interchange format for macromolecular
    structures. Each ATOM record contains the atom serial number, atom name,
    residue name, chain identifier, residue sequence number, Cartesian
    coordinates, occupancy, temperature factor, and element symbol.

    This writer produces a minimal but standards-compliant PDB file with
    C-alpha atoms only. While a full-atom representation would include
    backbone N, C, O and sidechain atoms, the coarse-grained C-alpha model
    used by FizzFold requires only a single atom per residue.
    """

    CHAIN_ID = "A"

    @staticmethod
    def format_atom_record(
        serial: int,
        atom_name: str,
        residue_name: str,
        chain_id: str,
        residue_seq: int,
        x: float,
        y: float,
        z: float,
        occupancy: float = 1.00,
        temp_factor: float = 0.00,
        element: str = "C",
    ) -> str:
        """Format a single ATOM record according to PDB column specifications."""
        return (
            f"ATOM  {serial:5d} {atom_name:<4s} {residue_name:>3s} "
            f"{chain_id:1s}{residue_seq:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}"
            f"{occupancy:6.2f}{temp_factor:6.2f}"
            f"          {element:>2s}  "
        )

    @classmethod
    def write(cls, conformation: Conformation, title: Optional[str] = None) -> str:
        """Convert a conformation to a PDB-format string.

        Args:
            conformation: The folded structure to serialize.
            title: Optional title for the TITLE record.

        Returns:
            A multi-line string in PDB format.
        """
        lines: list[str] = []

        if title:
            lines.append(f"TITLE     {title}")
        else:
            lines.append(
                f"TITLE     FIZZBUZZ PROTEIN STRUCTURE "
                f"- ENERGY {conformation.total_energy:.3f} KCAL/MOL"
            )

        lines.append(
            f"REMARK   1 GENERATED BY FIZZFOLD PROTEIN FOLDING SIMULATOR"
        )
        lines.append(
            f"REMARK   2 SEQUENCE: {conformation.sequence}"
        )
        lines.append(
            f"REMARK   3 TOTAL ENERGY: {conformation.total_energy:.3f} KCAL/MOL"
        )
        lines.append(
            f"REMARK   4 RMSD FROM EXTENDED: {conformation.rmsd:.3f} ANGSTROMS"
        )
        lines.append(
            f"REMARK   5 MC STEP: {conformation.step}"
        )

        for i, residue in enumerate(conformation.residues):
            lines.append(cls.format_atom_record(
                serial=i + 1,
                atom_name="CA",
                residue_name=residue.amino_acid.three_letter,
                chain_id=cls.CHAIN_ID,
                residue_seq=i + 1,
                x=residue.position.x,
                y=residue.position.y,
                z=residue.position.z,
                occupancy=1.00,
                temp_factor=residue.amino_acid.hydrophobicity,
                element="C",
            ))

        lines.append("TER")
        lines.append("END")
        return "\n".join(lines)

    @classmethod
    def write_to_file(
        cls,
        conformation: Conformation,
        path: str,
        title: Optional[str] = None,
    ) -> str:
        """Write PDB output to a file on disk.

        Returns:
            The absolute path of the written file.
        """
        content = cls.write(conformation, title=title)
        with open(path, "w") as f:
            f.write(content)
        logger.info("PDB file written: %s (%d atoms)", path, conformation.num_residues)
        return path


# ---------------------------------------------------------------------------
# Contact map
# ---------------------------------------------------------------------------

def compute_contact_map(
    conformation: Conformation,
    cutoff: float = 8.0,
) -> list[list[bool]]:
    """Compute the residue-residue contact map.

    A contact exists between residues i and j if the C-alpha distance is
    below the cutoff distance. The contact map is a symmetric boolean matrix.
    """
    n = conformation.num_residues
    contacts = [[False] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dist = conformation.residues[i].position.distance_to(
                conformation.residues[j].position
            )
            if dist < cutoff:
                contacts[i][j] = True
                contacts[j][i] = True
    return contacts


def count_contacts(contact_map: list[list[bool]]) -> int:
    """Count the number of unique contacts in a contact map."""
    n = len(contact_map)
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            if contact_map[i][j]:
                count += 1
    return count


def count_hydrophobic_contacts(conformation: Conformation, cutoff: float = 7.5) -> int:
    """Count hydrophobic-hydrophobic residue contacts within the cutoff."""
    n = conformation.num_residues
    count = 0
    for i in range(n):
        if not is_hydrophobic(conformation.residues[i].amino_acid):
            continue
        for j in range(i + 1, n):
            if not is_hydrophobic(conformation.residues[j].amino_acid):
                continue
            dist = conformation.residues[i].position.distance_to(
                conformation.residues[j].position
            )
            if dist < cutoff:
                count += 1
    return count


# ---------------------------------------------------------------------------
# Folding statistics
# ---------------------------------------------------------------------------

@dataclass
class FoldingStatistics:
    """Aggregate statistics from a folding simulation."""
    sequence: str
    num_residues: int
    total_steps: int
    best_energy: float
    final_energy: float
    acceptance_rate: float
    rmsd: float
    num_contacts: int
    num_hydrophobic_contacts: int
    bond_energy: float
    lj_energy: float
    hbond_energy: float
    hydrophobic_energy: float
    t_max: float
    t_min: float
    alpha: float

    @classmethod
    def from_folder(
        cls,
        folder: MonteCarloFolder,
        conformation: Conformation,
    ) -> FoldingStatistics:
        """Extract statistics from a completed folding simulation."""
        contact_map = compute_contact_map(conformation)
        return cls(
            sequence=conformation.sequence,
            num_residues=conformation.num_residues,
            total_steps=folder.total_steps,
            best_energy=conformation.total_energy,
            final_energy=folder.energy_history[-1] if folder.energy_history else 0.0,
            acceptance_rate=folder.acceptance_rate,
            rmsd=conformation.rmsd,
            num_contacts=count_contacts(contact_map),
            num_hydrophobic_contacts=count_hydrophobic_contacts(conformation),
            bond_energy=conformation.bond_energy,
            lj_energy=conformation.lj_energy,
            hbond_energy=conformation.hbond_energy,
            hydrophobic_energy=conformation.hydrophobic_energy,
            t_max=folder._t_max,
            t_min=folder._t_min,
            alpha=folder._alpha,
        )


# ---------------------------------------------------------------------------
# ASCII dashboard
# ---------------------------------------------------------------------------

class FoldingDashboard:
    """Renders an ASCII dashboard summarizing the folding simulation.

    Displays the energy convergence curve, residue contact map, folding
    statistics, and sequence annotation. This dashboard provides real-time
    visibility into the thermodynamic trajectory of the protein folding
    process — essential for monitoring whether the FizzBuzz peptide is
    converging toward its native conformation.
    """

    DEFAULT_WIDTH = 72
    ENERGY_CHART_HEIGHT = 12

    @classmethod
    def render(
        cls,
        folder: MonteCarloFolder,
        conformation: Conformation,
        width: int = DEFAULT_WIDTH,
    ) -> str:
        """Render the complete folding dashboard."""
        stats = FoldingStatistics.from_folder(folder, conformation)
        sections = [
            cls._render_header(width),
            cls._render_sequence(conformation, width),
            cls._render_energy_curve(folder, width),
            cls._render_contact_map(conformation, width),
            cls._render_statistics(stats, width),
            cls._render_residue_table(conformation, width),
            cls._render_footer(width),
        ]
        return "\n".join(sections)

    @classmethod
    def _render_header(cls, width: int) -> str:
        border = "+" + "=" * (width - 2) + "+"
        title = "FIZZFOLD PROTEIN FOLDING SIMULATOR"
        subtitle = "Ab Initio Structure Prediction via Simulated Annealing"
        return (
            f"\n{border}\n"
            f"|{title:^{width - 2}}|\n"
            f"|{subtitle:^{width - 2}}|\n"
            f"{border}"
        )

    @classmethod
    def _render_sequence(cls, conformation: Conformation, width: int) -> str:
        lines = [f"\n  Sequence: {conformation.sequence}"]
        lines.append("  Residues: " + " ".join(
            f"{r.amino_acid.single_letter}({r.amino_acid.three_letter})"
            for r in conformation.residues
        ))
        # Hydrophobicity annotation
        hydro = "  Hydrophb: " + " ".join(
            "H" if is_hydrophobic(r.amino_acid) else "P"
            for r in conformation.residues
        )
        lines.append(hydro)
        return "\n".join(lines)

    @classmethod
    def _render_energy_curve(cls, folder: MonteCarloFolder, width: int) -> str:
        """Render a downsampled ASCII energy curve."""
        history = folder.energy_history
        if not history:
            return "\n  No energy data available."

        chart_width = width - 12
        chart_height = cls.ENERGY_CHART_HEIGHT

        # Downsample to chart width
        n = len(history)
        step = max(1, n // chart_width)
        samples = [history[i] for i in range(0, n, step)][:chart_width]

        if not samples:
            return "\n  No energy data available."

        e_min = min(samples)
        e_max = max(samples)
        e_range = e_max - e_min if e_max > e_min else 1.0

        lines = ["\n  Energy Convergence:"]
        for row in range(chart_height, 0, -1):
            threshold = e_min + (row / chart_height) * e_range
            label = f"{threshold:8.1f} |"
            bar = ""
            for s in samples:
                if s >= threshold:
                    bar += "#"
                else:
                    bar += " "
            lines.append(f"  {label}{bar}")

        axis = "  " + " " * 10 + "+" + "-" * len(samples)
        lines.append(axis)
        lines.append(f"  {'':10s} Step 0{' ' * (len(samples) - 10)}Step {n}")

        return "\n".join(lines)

    @classmethod
    def _render_contact_map(cls, conformation: Conformation, width: int) -> str:
        """Render an ASCII contact map."""
        contact_map = compute_contact_map(conformation)
        n = conformation.num_residues

        lines = ["\n  Contact Map (8.0 A cutoff):"]
        # Header row
        header = "     " + " ".join(
            r.amino_acid.single_letter for r in conformation.residues
        )
        lines.append(f"  {header}")

        for i in range(n):
            label = conformation.residues[i].amino_acid.single_letter
            row = f"  {label:>3s}  "
            for j in range(n):
                if i == j:
                    row += "X "
                elif contact_map[i][j]:
                    row += "* "
                else:
                    row += ". "
            lines.append(row)

        return "\n".join(lines)

    @classmethod
    def _render_statistics(cls, stats: FoldingStatistics, width: int) -> str:
        lines = [
            "\n  Folding Statistics:",
            f"    Total MC Steps:        {stats.total_steps:>10d}",
            f"    Acceptance Rate:        {stats.acceptance_rate:>9.3f}",
            f"    Best Energy:           {stats.best_energy:>10.3f} kcal/mol",
            f"      Bond Energy:         {stats.bond_energy:>10.3f} kcal/mol",
            f"      LJ Energy:           {stats.lj_energy:>10.3f} kcal/mol",
            f"      H-Bond Energy:       {stats.hbond_energy:>10.3f} kcal/mol",
            f"      Hydrophobic Energy:  {stats.hydrophobic_energy:>10.3f} kcal/mol",
            f"    RMSD from Extended:    {stats.rmsd:>10.3f} A",
            f"    Contacts (8.0 A):      {stats.num_contacts:>10d}",
            f"    Hydrophobic Contacts:  {stats.num_hydrophobic_contacts:>10d}",
            f"    Temperature Schedule:   {stats.t_max:.0f}K -> {stats.t_min:.0f}K (alpha={stats.alpha})",
        ]
        return "\n".join(lines)

    @classmethod
    def _render_residue_table(cls, conformation: Conformation, width: int) -> str:
        lines = ["\n  Residue Coordinates (C-alpha):"]
        lines.append("    #  AA   Name                  X        Y        Z     Hydro")
        lines.append("    " + "-" * 64)
        for r in conformation.residues:
            lines.append(
                f"    {r.index + 1:2d}  {r.amino_acid.single_letter}    "
                f"{r.amino_acid.name:<20s} "
                f"{r.position.x:8.3f} {r.position.y:8.3f} {r.position.z:8.3f}  "
                f"{'H' if is_hydrophobic(r.amino_acid) else 'P'}"
            )
        return "\n".join(lines)

    @classmethod
    def _render_footer(cls, width: int) -> str:
        border = "+" + "=" * (width - 2) + "+"
        return f"\n{border}\n"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class FoldingMiddleware(IMiddleware):
    """Middleware that folds FizzBuzz output strings as amino acid sequences.

    When enabled, this middleware intercepts each evaluation result and checks
    whether the output string (e.g., "FizzBuzz", "Fizz", "Buzz") constitutes
    a valid amino acid sequence. If so, it folds the sequence using Monte Carlo
    simulated annealing and records the structural data in the result metadata.

    Priority 950 places this middleware near the end of the pipeline, ensuring
    that the final classification string is available before folding begins.
    """

    def __init__(
        self,
        max_steps: int = DEFAULT_MC_STEPS,
        seed: Optional[int] = None,
        enable_dashboard: bool = False,
        pdb_output_path: Optional[str] = None,
    ) -> None:
        self._max_steps = max_steps
        self._seed = seed
        self._enable_dashboard = enable_dashboard
        self._pdb_output_path = pdb_output_path
        self._fold_count = 0
        self._total_residues_folded = 0
        self._last_folder: Optional[MonteCarloFolder] = None
        self._last_conformation: Optional[Conformation] = None

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a number through the pipeline and fold any protein-like output."""
        result = next_handler(context)

        if result.results:
            latest = result.results[-1]
            output = latest.output.upper()

            # Check if the output string is a valid amino acid sequence
            if self._is_foldable(output):
                folder = MonteCarloFolder(
                    max_steps=self._max_steps,
                    seed=self._seed,
                )
                conformation = folder.fold(output)

                self._fold_count += 1
                self._total_residues_folded += conformation.num_residues
                self._last_folder = folder
                self._last_conformation = conformation

                # Attach structural data to metadata
                result.metadata["fold_sequence"] = output
                result.metadata["fold_energy"] = conformation.total_energy
                result.metadata["fold_rmsd"] = conformation.rmsd
                result.metadata["fold_residues"] = conformation.num_residues
                result.metadata["fold_step"] = conformation.step
                result.metadata["fold_acceptance_rate"] = folder.acceptance_rate

                if self._pdb_output_path:
                    pdb_path = self._pdb_output_path.replace(
                        ".pdb", f"_{latest.number}.pdb"
                    )
                    PDBWriter.write_to_file(conformation, pdb_path)
                    result.metadata["fold_pdb_path"] = pdb_path

                logger.info(
                    "Folded '%s' (number=%d): energy=%.3f rmsd=%.3f",
                    output, latest.number, conformation.total_energy,
                    conformation.rmsd,
                )

        return result

    def _is_foldable(self, sequence: str) -> bool:
        """Check whether all characters in the string map to known amino acids."""
        return len(sequence) > 0 and all(ch in AMINO_ACID_TABLE for ch in sequence)

    def get_name(self) -> str:
        return "FoldingMiddleware"

    def get_priority(self) -> int:
        return 950

    @property
    def fold_count(self) -> int:
        """Number of sequences folded so far."""
        return self._fold_count

    @property
    def total_residues_folded(self) -> int:
        """Total number of amino acid residues processed."""
        return self._total_residues_folded

    @property
    def last_folder(self) -> Optional[MonteCarloFolder]:
        """The MonteCarloFolder from the most recent folding run."""
        return self._last_folder

    @property
    def last_conformation(self) -> Optional[Conformation]:
        """The best conformation from the most recent folding run."""
        return self._last_conformation


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def fold_fizzbuzz(
    sequence: str = "FIZZBUZZ",
    max_steps: int = DEFAULT_MC_STEPS,
    seed: Optional[int] = None,
) -> Tuple[Conformation, MonteCarloFolder]:
    """Convenience function: fold a sequence and return results.

    Returns:
        A tuple of (best_conformation, folder) for inspection.
    """
    folder = MonteCarloFolder(max_steps=max_steps, seed=seed)
    conformation = folder.fold(sequence)
    return conformation, folder
