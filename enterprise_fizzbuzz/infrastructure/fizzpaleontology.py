"""
Enterprise FizzBuzz Platform - FizzPaleontology: Fossil Record Analyzer

Implements taxonomic classification, extinction event detection, phylogenetic
inference, biostratigraphy, and morphometric analysis for the FizzBuzz
evaluation pipeline. Each evaluated number is treated as a fossil specimen
with morphological characters derived from its divisibility properties.

The FizzBuzz sequence maps naturally to the geological timescale: each
evaluated number represents a stratigraphic horizon, with Fizz events
marking minor extinction pulses (genus-level), Buzz events marking
moderate extinctions (family-level), and FizzBuzz events marking mass
extinctions (order-level). The 15-number superperiod of FizzBuzz
corresponds to a geological stage boundary.

Taxonomic classification follows the Linnaean hierarchy: Kingdom, Phylum,
Class, Order, Family, Genus, Species. Each specimen is placed in a
synthetic taxonomy based on digit patterns and divisibility residues.
Phylogenetic inference uses a maximum parsimony algorithm on binary
character matrices to reconstruct evolutionary relationships.

Morphometric analysis applies principal component analysis to
measurements derived from the number's prime factorization, providing
a quantitative assessment of morphological disparity across the
FizzBuzz fauna.

Physical justification: Paleontological monitoring provides a
stratigraphic correlation service that validates the temporal ordering
of FizzBuzz evaluations. Out-of-order evaluations manifest as
biostratigraphic range violations, which are detectable by the
range-chart audit system.
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

GEOLOGICAL_PERIODS = [
    "Cambrian", "Ordovician", "Silurian", "Devonian",
    "Carboniferous", "Permian", "Triassic", "Jurassic",
    "Cretaceous", "Paleogene", "Neogene", "Quaternary",
]

TAXONOMIC_RANKS = [
    "Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species",
]

EXTINCTION_THRESHOLD = 40.0  # percent diversity loss for mass extinction
BACKGROUND_EXTINCTION_RATE = 5.0  # percent per stage

# Morphometric analysis parameters
MIN_SAMPLE_SIZE = 3
NUM_PC_AXES = 3


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class TaxonomicRank(Enum):
    KINGDOM = auto()
    PHYLUM = auto()
    CLASS = auto()
    ORDER = auto()
    FAMILY = auto()
    GENUS = auto()
    SPECIES = auto()


@dataclass
class Taxon:
    """A biological taxon with hierarchical classification.

    Each taxon occupies a specific position in the Linnaean hierarchy.
    The taxon_id is unique within the synthetic FizzBuzz fauna.
    """
    taxon_id: str
    rank: TaxonomicRank
    name: str
    parent_id: Optional[str] = None
    first_appearance: int = 0  # horizon number
    last_appearance: Optional[int] = None

    @property
    def is_extant(self) -> bool:
        return self.last_appearance is None

    @property
    def range_duration(self) -> int:
        if self.last_appearance is None:
            return 0
        return self.last_appearance - self.first_appearance


@dataclass
class FossilSpecimen:
    """A single fossil specimen with morphological measurements.

    Each specimen belongs to a taxon and carries a set of continuous
    morphometric measurements derived from the source number.
    """
    specimen_id: str
    taxon: Taxon
    horizon: int  # stratigraphic position (= evaluated number)
    measurements: dict[str, float] = field(default_factory=dict)
    preservation_quality: float = 1.0  # 0.0 to 1.0


@dataclass
class ExtinctionEvent:
    """A detected extinction event with statistical metrics."""
    boundary_horizon: int
    diversity_before: int
    diversity_after: int
    percent_loss: float
    severity: str  # "minor", "moderate", "mass"
    affected_taxa: list[str] = field(default_factory=list)


@dataclass
class PhylogeneticNode:
    """A node in a phylogenetic tree."""
    taxon_id: str
    children: list[PhylogeneticNode] = field(default_factory=list)
    branch_length: float = 1.0
    characters: list[int] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def count_leaves(self) -> int:
        if self.is_leaf:
            return 1
        return sum(c.count_leaves() for c in self.children)


# ---------------------------------------------------------------------------
# Taxonomic classifier
# ---------------------------------------------------------------------------

class TaxonomicClassifier:
    """Assigns taxonomic classifications to numbers based on divisibility.

    The classification algorithm uses the prime factorization and modular
    residues of each number to determine its placement in the synthetic
    taxonomy. Numbers sharing factors are placed in related taxa.
    """

    KINGDOM_NAMES = ["Fizzalia", "Buzzalia"]
    PHYLUM_NAMES = ["Dividoptera", "Modulata", "Primata", "Compositae"]
    CLASS_NAMES = ["Ternaria", "Quinaria", "Mixta", "Residua"]
    ORDER_NAMES = [
        "Trifizzida", "Pentabuzzida", "Quindecimida", "Singulida",
        "Bifizzida", "Septabuzzida", "Undecimida", "Tredecimida",
    ]

    def __init__(self) -> None:
        self._taxa_registry: dict[str, Taxon] = {}
        self._next_id = 0

    def _generate_id(self) -> str:
        self._next_id += 1
        return f"TX-{self._next_id:06d}"

    def classify(self, number: int) -> Taxon:
        """Assign a full taxonomic classification to a number.

        The classification is deterministic: the same number always
        receives the same taxonomy.
        """
        kingdom_idx = 0 if number % 2 == 0 else 1
        phylum_idx = number % len(self.PHYLUM_NAMES)
        class_idx = number % len(self.CLASS_NAMES)
        order_idx = number % len(self.ORDER_NAMES)
        family_name = f"F{number % 20:02d}idae"
        genus_name = f"Fizz{number % 50}"
        species_name = f"fz{number}"

        full_name = (
            f"{self.KINGDOM_NAMES[kingdom_idx]}."
            f"{self.PHYLUM_NAMES[phylum_idx]}."
            f"{self.CLASS_NAMES[class_idx]}."
            f"{self.ORDER_NAMES[order_idx]}."
            f"{family_name}.{genus_name}.{species_name}"
        )

        taxon_id = self._generate_id()
        taxon = Taxon(
            taxon_id=taxon_id,
            rank=TaxonomicRank.SPECIES,
            name=full_name,
            first_appearance=number,
        )
        self._taxa_registry[taxon_id] = taxon
        return taxon

    @property
    def taxa_count(self) -> int:
        return len(self._taxa_registry)

    def get_taxon(self, taxon_id: str) -> Optional[Taxon]:
        return self._taxa_registry.get(taxon_id)


# ---------------------------------------------------------------------------
# Extinction detector
# ---------------------------------------------------------------------------

class ExtinctionDetector:
    """Detects extinction events from diversity changes across horizons.

    Maintains a running tally of taxonomic diversity (number of extant
    taxa) at each stratigraphic horizon. An extinction event is declared
    when diversity drops by more than the background rate.
    """

    def __init__(self, threshold: float = EXTINCTION_THRESHOLD) -> None:
        self.threshold = threshold
        self._diversity_history: list[tuple[int, int]] = []  # (horizon, count)
        self._events: list[ExtinctionEvent] = []

    def record_diversity(self, horizon: int, living_taxa: int) -> Optional[ExtinctionEvent]:
        """Record diversity at a horizon and check for extinction events."""
        self._diversity_history.append((horizon, living_taxa))

        if len(self._diversity_history) < 2:
            return None

        prev_horizon, prev_count = self._diversity_history[-2]
        if prev_count == 0:
            return None

        percent_loss = 100.0 * (prev_count - living_taxa) / prev_count

        if percent_loss <= BACKGROUND_EXTINCTION_RATE:
            return None

        if percent_loss >= EXTINCTION_THRESHOLD:
            severity = "mass"
        elif percent_loss >= 20.0:
            severity = "moderate"
        else:
            severity = "minor"

        event = ExtinctionEvent(
            boundary_horizon=horizon,
            diversity_before=prev_count,
            diversity_after=living_taxa,
            percent_loss=percent_loss,
            severity=severity,
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> list[ExtinctionEvent]:
        return list(self._events)

    @property
    def total_events(self) -> int:
        return len(self._events)


# ---------------------------------------------------------------------------
# Phylogenetic inference (maximum parsimony)
# ---------------------------------------------------------------------------

class ParsimonyInference:
    """Maximum parsimony phylogenetic inference on binary character matrices.

    Given a set of taxa with binary character vectors, constructs the
    most parsimonious tree (minimum number of character state changes).
    Uses a simple nearest-neighbor joining heuristic for tractability.
    """

    def __init__(self) -> None:
        self._character_matrix: dict[str, list[int]] = {}

    def add_taxon(self, taxon_id: str, characters: list[int]) -> None:
        """Add a taxon with its binary character vector."""
        self._character_matrix[taxon_id] = characters

    def _hamming_distance(self, chars_a: list[int], chars_b: list[int]) -> int:
        """Compute Hamming distance between two character vectors."""
        return sum(1 for a, b in zip(chars_a, chars_b) if a != b)

    def infer_tree(self) -> Optional[PhylogeneticNode]:
        """Infer the most parsimonious tree using neighbor joining.

        Returns the root of the inferred tree, or None if fewer than
        2 taxa are present.
        """
        if len(self._character_matrix) < 2:
            return None

        # Build leaf nodes
        nodes: list[PhylogeneticNode] = []
        for taxon_id, chars in self._character_matrix.items():
            nodes.append(PhylogeneticNode(
                taxon_id=taxon_id,
                characters=chars,
            ))

        # Iteratively join nearest neighbors
        while len(nodes) > 1:
            min_dist = float("inf")
            best_i, best_j = 0, 1

            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    d = self._hamming_distance(
                        nodes[i].characters, nodes[j].characters
                    )
                    if d < min_dist:
                        min_dist = d
                        best_i, best_j = i, j

            # Create parent node
            left = nodes[best_i]
            right = nodes[best_j]

            # Consensus characters (majority rule)
            consensus = []
            for k in range(len(left.characters)):
                lc = left.characters[k] if k < len(left.characters) else 0
                rc = right.characters[k] if k < len(right.characters) else 0
                consensus.append(lc if lc == rc else 0)

            parent = PhylogeneticNode(
                taxon_id=f"({left.taxon_id},{right.taxon_id})",
                children=[left, right],
                branch_length=min_dist / 2.0,
                characters=consensus,
            )

            # Remove joined nodes and add parent
            nodes = [n for idx, n in enumerate(nodes) if idx not in (best_i, best_j)]
            nodes.append(parent)

        return nodes[0] if nodes else None

    @property
    def num_taxa(self) -> int:
        return len(self._character_matrix)

    def tree_length(self, root: PhylogeneticNode) -> int:
        """Compute the total parsimony length of a tree."""
        if root.is_leaf:
            return 0
        total = 0
        for child in root.children:
            total += self._hamming_distance(root.characters, child.characters)
            total += self.tree_length(child)
        return total


# ---------------------------------------------------------------------------
# Morphometric analyzer
# ---------------------------------------------------------------------------

class MorphometricAnalyzer:
    """Principal component analysis of morphometric measurements.

    Applies a simplified PCA to measurements derived from the prime
    factorization of evaluated numbers. The first few principal
    components capture the major axes of morphological variation
    in the synthetic FizzBuzz fauna.
    """

    def __init__(self) -> None:
        self._measurements: list[list[float]] = []
        self._specimen_ids: list[str] = []

    def add_specimen(self, specimen_id: str, measurements: list[float]) -> None:
        self._measurements.append(measurements)
        self._specimen_ids.append(specimen_id)

    def _mean_center(self) -> list[list[float]]:
        """Center the measurement matrix by subtracting column means."""
        if not self._measurements:
            return []
        n_vars = len(self._measurements[0])
        means = [0.0] * n_vars
        for row in self._measurements:
            for j in range(min(n_vars, len(row))):
                means[j] += row[j]
        n = len(self._measurements)
        means = [m / n for m in means]

        centered = []
        for row in self._measurements:
            centered.append([row[j] - means[j] for j in range(min(n_vars, len(row)))])
        return centered

    def compute_disparity(self) -> float:
        """Compute morphological disparity (sum of variances).

        Disparity is the total variance across all measurement dimensions,
        providing a single scalar summary of morphological spread.
        """
        if len(self._measurements) < MIN_SAMPLE_SIZE:
            return 0.0

        centered = self._mean_center()
        if not centered:
            return 0.0

        n_vars = len(centered[0])
        total_var = 0.0
        n = len(centered)

        for j in range(n_vars):
            col_var = sum(row[j] ** 2 for row in centered) / max(n - 1, 1)
            total_var += col_var

        return total_var

    def compute_covariance_matrix(self) -> list[list[float]]:
        """Compute the covariance matrix of the centered measurements."""
        centered = self._mean_center()
        if not centered:
            return []
        n_vars = len(centered[0])
        n = len(centered)
        cov = [[0.0] * n_vars for _ in range(n_vars)]
        for i in range(n_vars):
            for j in range(i, n_vars):
                s = sum(row[i] * row[j] for row in centered) / max(n - 1, 1)
                cov[i][j] = s
                cov[j][i] = s
        return cov

    @property
    def sample_size(self) -> int:
        return len(self._measurements)


# ---------------------------------------------------------------------------
# Specimen factory
# ---------------------------------------------------------------------------

def number_to_measurements(number: int) -> list[float]:
    """Derive morphometric measurements from a number's properties.

    Measurements are extracted from:
    1. Number of prime factors (body size proxy)
    2. Sum of digits (ornamentation index)
    3. Modular residues (limb proportions)
    """
    # Prime factor count (simplified trial division)
    n = abs(number) if number != 0 else 1
    factor_count = 0
    for p in [2, 3, 5, 7, 11, 13, 17, 19, 23]:
        while n % p == 0 and n > 1:
            factor_count += 1
            n //= p
    if n > 1:
        factor_count += 1

    digit_sum = sum(int(d) for d in str(abs(number)))

    return [
        float(factor_count),  # body size
        float(digit_sum),  # ornamentation
        float(number % 7),  # limb ratio A
        float(number % 11),  # limb ratio B
        math.log1p(abs(number)),  # log-body-mass
    ]


def create_specimen(
    number: int, taxon: Taxon, is_fizz: bool, is_buzz: bool
) -> FossilSpecimen:
    """Create a fossil specimen from a FizzBuzz evaluation."""
    measurements = number_to_measurements(number)
    quality = 1.0
    if is_fizz and is_buzz:
        quality = 0.5  # FizzBuzz specimens are poorly preserved (diagenetic overprint)
    elif is_fizz:
        quality = 0.8
    elif is_buzz:
        quality = 0.7

    return FossilSpecimen(
        specimen_id=f"SP-{number:06d}",
        taxon=taxon,
        horizon=number,
        measurements={
            "body_size": measurements[0],
            "ornamentation": measurements[1],
            "limb_ratio_a": measurements[2],
            "limb_ratio_b": measurements[3],
            "log_mass": measurements[4],
        },
        preservation_quality=quality,
    )


# ---------------------------------------------------------------------------
# Paleontology engine (composition root)
# ---------------------------------------------------------------------------

class PaleontologyEngine:
    """Integrates all paleontological analysis components.

    Manages the synthetic fossil record, runs taxonomic classification,
    detects extinction events, maintains the phylogenetic tree, and
    computes morphometric statistics for each evaluated number.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self.classifier = TaxonomicClassifier()
        self.extinction = ExtinctionDetector()
        self.parsimony = ParsimonyInference()
        self.morphometrics = MorphometricAnalyzer()
        self._specimens: list[FossilSpecimen] = []
        self._living_taxa: set[str] = set()
        self._step_count = 0

    def process_number(
        self, number: int, is_fizz: bool, is_buzz: bool
    ) -> dict:
        """Process a FizzBuzz evaluation as a paleontological event.

        Returns diagnostic metrics for the current state of the fossil record.
        """
        # Classify the specimen
        taxon = self.classifier.classify(number)
        self._living_taxa.add(taxon.taxon_id)

        # Create specimen with morphometrics
        specimen = create_specimen(number, taxon, is_fizz, is_buzz)
        self._specimens.append(specimen)

        measurements = number_to_measurements(number)
        self.morphometrics.add_specimen(specimen.specimen_id, measurements)

        # Add to phylogenetic matrix
        chars = [int(b) for b in format(number % 256, '08b')]
        self.parsimony.add_taxon(taxon.taxon_id, chars)

        # Apply extinction for Fizz/Buzz events
        if is_fizz and is_buzz:
            # Mass extinction: remove 60% of taxa
            to_remove = set(list(self._living_taxa)[:int(len(self._living_taxa) * 0.6)])
            for tid in to_remove:
                t = self.classifier.get_taxon(tid)
                if t:
                    t.last_appearance = number
            self._living_taxa -= to_remove
        elif is_fizz:
            # Minor extinction: remove 10%
            to_remove = set(list(self._living_taxa)[:max(1, int(len(self._living_taxa) * 0.1))])
            for tid in to_remove:
                t = self.classifier.get_taxon(tid)
                if t:
                    t.last_appearance = number
            self._living_taxa -= to_remove
        elif is_buzz:
            # Moderate extinction: remove 20%
            to_remove = set(list(self._living_taxa)[:max(1, int(len(self._living_taxa) * 0.2))])
            for tid in to_remove:
                t = self.classifier.get_taxon(tid)
                if t:
                    t.last_appearance = number
            self._living_taxa -= to_remove

        # Record diversity
        ext_event = self.extinction.record_diversity(
            number, len(self._living_taxa)
        )

        self._step_count += 1

        disparity = self.morphometrics.compute_disparity()

        return {
            "step": self._step_count,
            "taxon_name": taxon.name,
            "living_taxa": len(self._living_taxa),
            "total_specimens": len(self._specimens),
            "disparity": disparity,
            "extinction_event": ext_event.severity if ext_event else None,
            "preservation_quality": specimen.preservation_quality,
        }

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def specimens(self) -> list[FossilSpecimen]:
        return list(self._specimens)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class PaleontologyMiddleware(IMiddleware):
    """Middleware that performs paleontological analysis for each evaluation.

    Each number is treated as a fossil specimen. The middleware runs
    taxonomic classification, morphometric analysis, and extinction
    detection, attaching results to the processing context.

    Priority 288 positions this in the geoscience analysis tier.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._engine = PaleontologyEngine(seed=seed)
        self._evaluations = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        is_fizz = False
        is_buzz = False
        if result.results:
            latest = result.results[-1]
            is_fizz = latest.is_fizz
            is_buzz = latest.is_buzz

        try:
            diagnostics = self._engine.process_number(number, is_fizz, is_buzz)
            self._evaluations += 1

            result.metadata["paleo_taxon"] = diagnostics["taxon_name"]
            result.metadata["paleo_living_taxa"] = diagnostics["living_taxa"]
            result.metadata["paleo_disparity"] = diagnostics["disparity"]
            result.metadata["paleo_extinction"] = diagnostics["extinction_event"]
        except Exception as e:
            logger.warning("Paleontology analysis failed for number %d: %s", number, e)
            result.metadata["paleo_error"] = str(e)

        return result

    def get_name(self) -> str:
        return "PaleontologyMiddleware"

    def get_priority(self) -> int:
        return 288

    @property
    def engine(self) -> PaleontologyEngine:
        return self._engine

    @property
    def evaluations(self) -> int:
        return self._evaluations
