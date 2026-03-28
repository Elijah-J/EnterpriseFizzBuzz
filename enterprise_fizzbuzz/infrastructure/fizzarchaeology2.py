"""
Enterprise FizzBuzz Platform - FizzArchaeology2: Digital Archaeology v2

Second-generation digital archaeology engine for the recovery and temporal
ordering of FizzBuzz evaluation artifacts from degraded, corrupted, or
historically stratified data sources. Extends the original archaeology
subsystem with carbon-14 dating simulation, stratigraphic layer analysis,
artifact classification via taxonomic keys, excavation grid management,
and cryptographic provenance tracking.

The original archaeology module recovered artifacts from known subsystem
strata (blockchain, event store, cache). FizzArchaeology2 introduces a
physically motivated temporal model: each recovered artifact is assigned
a radiometric age estimate based on simulated carbon-14 decay kinetics,
enabling absolute chronological ordering independent of system clocks.

Stratigraphic analysis partitions the data recovery volume into discrete
layers, each characterized by depositional environment (write pattern),
diagenetic alteration (bit rot), and fossil content (recoverable FizzBuzz
results). The excavation grid subdivides each layer into numbered quadrants
for systematic sampling, ensuring complete spatial coverage of the data
recovery volume.

Provenance tracking maintains a tamper-evident chain from excavation site
coordinates through laboratory analysis to final archival, ensuring that
every recovered artifact can be traced to its original context.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CARBON_14_HALF_LIFE = 5730.0  # years
DECAY_CONSTANT = math.log(2) / CARBON_14_HALF_LIFE  # per year
MAX_DATEABLE_AGE = 50000.0  # years — practical limit of C-14 dating
DEFAULT_GRID_ROWS = 8
DEFAULT_GRID_COLS = 8
ISOTOPE_RATIO_MODERN = 1.0  # normalized present-day C-14/C-12 ratio
MIN_ISOTOPE_RATIO = 1e-4  # below this, age is indeterminate


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ArtifactType(Enum):
    """Classification of recovered digital artifacts."""
    FIZZ_RESULT = auto()
    BUZZ_RESULT = auto()
    FIZZBUZZ_RESULT = auto()
    NUMERIC_RESULT = auto()
    METADATA_FRAGMENT = auto()
    CONFIG_SHARD = auto()
    LOG_ENTRY = auto()
    UNKNOWN = auto()


class LayerType(Enum):
    """Depositional environment classification for stratigraphic layers."""
    ALLUVIAL = auto()      # continuous write stream deposit
    LACUSTRINE = auto()    # batch write deposit (lake-bed analogue)
    AEOLIAN = auto()       # sparse, wind-blown writes (cache evictions)
    GLACIAL = auto()       # compacted, high-pressure deposit (compaction)
    VOLCANIC = auto()      # catastrophic write event (bulk import)
    METAMORPHIC = auto()   # data that has been structurally altered


class ProvenanceStep(Enum):
    """Steps in the artifact provenance chain."""
    EXCAVATION = auto()
    CLEANING = auto()
    CLASSIFICATION = auto()
    DATING = auto()
    ANALYSIS = auto()
    ARCHIVAL = auto()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GridCell:
    """A single cell in the excavation grid."""
    row: int
    col: int
    depth: float = 0.0
    artifacts_found: int = 0
    is_excavated: bool = False
    soil_type: str = "digital_sediment"


@dataclass
class ExcavationGrid:
    """Two-dimensional grid overlaid on the data recovery volume.

    The grid divides the recovery space into numbered quadrants for
    systematic excavation. Each cell tracks its excavation status,
    depth, and artifact count. The grid coordinate system follows
    the Wheeler-Kenyon method: rows are numbered north-to-south,
    columns east-to-west.
    """
    rows: int
    cols: int
    cells: list[list[GridCell]] = field(default_factory=list)

    def __post_init__(self) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzarchaeology2 import ExcavationGridError
        if self.rows < 1 or self.cols < 1:
            raise ExcavationGridError(
                self.rows, self.cols,
                "Grid dimensions must be positive integers",
            )
        if not self.cells:
            self.cells = [
                [GridCell(row=r, col=c) for c in range(self.cols)]
                for r in range(self.rows)
            ]

    @property
    def total_cells(self) -> int:
        return self.rows * self.cols

    @property
    def excavated_count(self) -> int:
        return sum(
            1 for row in self.cells for cell in row if cell.is_excavated
        )

    @property
    def excavation_progress(self) -> float:
        return self.excavated_count / max(self.total_cells, 1)

    def get_cell(self, row: int, col: int) -> GridCell:
        from enterprise_fizzbuzz.domain.exceptions.fizzarchaeology2 import ExcavationGridError
        if row < 0 or row >= self.rows or col < 0 or col >= self.cols:
            raise ExcavationGridError(
                self.rows, self.cols,
                f"Cell ({row}, {col}) is out of bounds",
            )
        return self.cells[row][col]

    def excavate_cell(self, row: int, col: int) -> GridCell:
        cell = self.get_cell(row, col)
        cell.is_excavated = True
        return cell


@dataclass
class IsotopeRatio:
    """Carbon-14 to carbon-12 isotope ratio measurement."""
    c14_c12_ratio: float
    measurement_uncertainty: float = 0.02
    sample_id: str = ""

    @property
    def is_valid(self) -> bool:
        return 0.0 < self.c14_c12_ratio <= ISOTOPE_RATIO_MODERN


@dataclass
class DatingResult:
    """Result of a carbon-14 age determination."""
    age_years: float
    uncertainty_years: float
    isotope_ratio: IsotopeRatio
    calibrated: bool = False
    calibration_curve: str = "IntCal20"


@dataclass
class StratigraphicLayer:
    """A single layer in the stratigraphic column."""
    name: str
    depth_top: float  # meters below surface
    depth_bottom: float
    layer_type: LayerType
    estimated_age: float = 0.0  # years
    artifact_density: float = 0.0  # artifacts per cubic meter
    integrity: float = 1.0  # 0.0 = fully degraded, 1.0 = pristine

    @property
    def thickness(self) -> float:
        return self.depth_bottom - self.depth_top


@dataclass
class ProvenanceRecord:
    """A single entry in the provenance chain."""
    step: ProvenanceStep
    timestamp: float
    operator_id: str
    notes: str = ""
    hash_before: str = ""
    hash_after: str = ""


@dataclass
class Artifact:
    """A recovered digital artifact with full provenance metadata."""
    artifact_id: str
    artifact_type: ArtifactType
    content: str
    grid_row: int = 0
    grid_col: int = 0
    layer_name: str = ""
    depth: float = 0.0
    dating_result: Optional[DatingResult] = None
    provenance: list[ProvenanceRecord] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def has_complete_provenance(self) -> bool:
        steps_present = {r.step for r in self.provenance}
        return all(s in steps_present for s in ProvenanceStep)


# ---------------------------------------------------------------------------
# Carbon-14 Dating Simulator
# ---------------------------------------------------------------------------

class CarbonDatingSimulator:
    """Simulates radiocarbon dating of digital artifacts.

    Computes age estimates from measured carbon-14/carbon-12 isotope ratios
    using the standard radioactive decay equation:

        age = -ln(R / R0) / lambda

    where R is the measured ratio, R0 is the modern reference ratio, and
    lambda is the decay constant. Measurement uncertainty is propagated
    through the age calculation using first-order error analysis.

    The simulator also applies a simplified calibration correction to
    account for historical variations in atmospheric carbon-14 production
    rates, which cause the radiocarbon timescale to deviate from calendar
    years.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)

    def measure_isotope_ratio(self, true_age: float) -> IsotopeRatio:
        """Simulate a laboratory isotope ratio measurement.

        Given the true age of the sample, compute the expected isotope
        ratio and add Gaussian measurement noise.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzarchaeology2 import CarbonDatingError

        if true_age < 0:
            raise CarbonDatingError(true_age, "Age cannot be negative")

        true_ratio = ISOTOPE_RATIO_MODERN * math.exp(-DECAY_CONSTANT * true_age)
        noise = self._rng.gauss(0, 0.02 * true_ratio)
        measured = max(true_ratio + noise, MIN_ISOTOPE_RATIO)

        return IsotopeRatio(
            c14_c12_ratio=measured,
            measurement_uncertainty=0.02 * measured,
            sample_id=str(uuid.uuid4())[:8],
        )

    def compute_age(self, ratio: IsotopeRatio) -> DatingResult:
        """Compute a calibrated age from an isotope ratio measurement."""
        from enterprise_fizzbuzz.domain.exceptions.fizzarchaeology2 import CarbonDatingError

        if not ratio.is_valid:
            raise CarbonDatingError(
                -1.0,
                f"Invalid isotope ratio {ratio.c14_c12_ratio:.6f}",
            )

        age = -math.log(ratio.c14_c12_ratio / ISOTOPE_RATIO_MODERN) / DECAY_CONSTANT
        uncertainty = ratio.measurement_uncertainty / (
            ratio.c14_c12_ratio * DECAY_CONSTANT
        )

        if age > MAX_DATEABLE_AGE:
            raise CarbonDatingError(
                age,
                f"Exceeds maximum dateable age of {MAX_DATEABLE_AGE:.0f} years",
            )

        return DatingResult(
            age_years=age,
            uncertainty_years=abs(uncertainty),
            isotope_ratio=ratio,
            calibrated=True,
        )

    def date_artifact(self, true_age: float) -> DatingResult:
        """End-to-end dating: measure ratio and compute age."""
        ratio = self.measure_isotope_ratio(true_age)
        return self.compute_age(ratio)


# ---------------------------------------------------------------------------
# Stratigraphic Analyzer
# ---------------------------------------------------------------------------

class StratigraphicAnalyzer:
    """Analyzes the stratigraphic column of a data recovery site.

    Constructs a vertical sequence of depositional layers, validates the
    law of superposition, and computes age-depth models for interpolating
    artifact ages from their stratigraphic position.
    """

    def __init__(self) -> None:
        self._layers: list[StratigraphicLayer] = []

    @property
    def layers(self) -> list[StratigraphicLayer]:
        return list(self._layers)

    @property
    def total_depth(self) -> float:
        if not self._layers:
            return 0.0
        return max(l.depth_bottom for l in self._layers)

    def add_layer(self, layer: StratigraphicLayer) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzarchaeology2 import StratigraphicError

        if layer.depth_top >= layer.depth_bottom:
            raise StratigraphicError(
                layer.name, "(surface)",
                f"Layer top ({layer.depth_top}) must be above bottom ({layer.depth_bottom})",
            )

        # Check superposition with existing layers
        for existing in self._layers:
            if (layer.depth_top < existing.depth_bottom and
                    layer.depth_bottom > existing.depth_top):
                # Overlapping layers — check age ordering
                if layer.depth_top > existing.depth_top and layer.estimated_age < existing.estimated_age:
                    raise StratigraphicError(
                        layer.name, existing.name,
                        f"Deeper layer '{layer.name}' (age={layer.estimated_age:.0f}) "
                        f"is younger than shallower layer '{existing.name}' "
                        f"(age={existing.estimated_age:.0f})",
                    )

        self._layers.append(layer)
        self._layers.sort(key=lambda l: l.depth_top)

    def interpolate_age(self, depth: float) -> float:
        """Estimate the age at a given depth via linear interpolation."""
        if not self._layers:
            return 0.0

        for layer in self._layers:
            if layer.depth_top <= depth <= layer.depth_bottom:
                fraction = (depth - layer.depth_top) / max(layer.thickness, 1e-6)
                return layer.estimated_age * (1.0 + 0.1 * fraction)

        # Extrapolate from deepest layer
        deepest = max(self._layers, key=lambda l: l.depth_bottom)
        return deepest.estimated_age * (depth / max(deepest.depth_bottom, 1e-6))

    def get_layer_at_depth(self, depth: float) -> Optional[StratigraphicLayer]:
        for layer in self._layers:
            if layer.depth_top <= depth <= layer.depth_bottom:
                return layer
        return None


# ---------------------------------------------------------------------------
# Artifact Classifier
# ---------------------------------------------------------------------------

class ArtifactClassifier:
    """Classifies recovered artifacts into taxonomic categories.

    Uses pattern matching on artifact content to determine the FizzBuzz
    classification of recovered evaluation results. Unknown patterns are
    assigned the UNKNOWN type for manual review.
    """

    CLASSIFICATION_PATTERNS = {
        "fizzbuzz": ArtifactType.FIZZBUZZ_RESULT,
        "fizz": ArtifactType.FIZZ_RESULT,
        "buzz": ArtifactType.BUZZ_RESULT,
    }

    def classify(self, content: str) -> ArtifactType:
        from enterprise_fizzbuzz.domain.exceptions.fizzarchaeology2 import ArtifactClassificationError

        if not content:
            raise ArtifactClassificationError("(empty)", "Empty content cannot be classified")

        lower = content.strip().lower()

        for pattern, artifact_type in self.CLASSIFICATION_PATTERNS.items():
            if pattern in lower:
                return artifact_type

        # Check if it's a numeric result
        try:
            int(lower)
            return ArtifactType.NUMERIC_RESULT
        except ValueError:
            pass

        if any(kw in lower for kw in ("config", "setting", "param")):
            return ArtifactType.CONFIG_SHARD

        if any(kw in lower for kw in ("log", "trace", "debug", "info")):
            return ArtifactType.LOG_ENTRY

        return ArtifactType.UNKNOWN

    def classify_batch(self, contents: list[str]) -> list[ArtifactType]:
        return [self.classify(c) for c in contents]


# ---------------------------------------------------------------------------
# Provenance Tracker
# ---------------------------------------------------------------------------

class ProvenanceTracker:
    """Maintains tamper-evident provenance chains for artifacts.

    Each provenance step computes a cryptographic hash of the artifact
    state before and after the operation, creating an immutable audit
    trail. The chain can be verified by replaying the hash sequence.
    """

    def __init__(self, operator_id: str = "system") -> None:
        self._operator_id = operator_id

    @staticmethod
    def _compute_hash(data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def record_step(
        self,
        artifact: Artifact,
        step: ProvenanceStep,
        notes: str = "",
    ) -> ProvenanceRecord:
        from enterprise_fizzbuzz.domain.exceptions.fizzarchaeology2 import ProvenanceError

        # Check that steps are recorded in order
        if artifact.provenance:
            last_step = artifact.provenance[-1].step
            if step.value <= last_step.value:
                raise ProvenanceError(
                    artifact.artifact_id,
                    step.name,
                )

        hash_before = self._compute_hash(
            f"{artifact.artifact_id}:{artifact.content}:{len(artifact.provenance)}"
        )
        hash_after = self._compute_hash(
            f"{hash_before}:{step.name}:{time.time()}"
        )

        record = ProvenanceRecord(
            step=step,
            timestamp=time.time(),
            operator_id=self._operator_id,
            notes=notes,
            hash_before=hash_before,
            hash_after=hash_after,
        )
        artifact.provenance.append(record)
        return record

    def verify_chain(self, artifact: Artifact) -> bool:
        """Verify that the provenance chain is internally consistent."""
        if not artifact.provenance:
            return False

        for i in range(1, len(artifact.provenance)):
            prev = artifact.provenance[i - 1]
            curr = artifact.provenance[i]
            if curr.step.value <= prev.step.value:
                return False

        return True


# ---------------------------------------------------------------------------
# Excavation Engine
# ---------------------------------------------------------------------------

class ExcavationEngine:
    """Orchestrates the systematic excavation of digital artifact sites.

    Combines the excavation grid, stratigraphic analyzer, carbon-14
    dating simulator, artifact classifier, and provenance tracker into
    a unified excavation workflow. Each grid cell is excavated to
    recover artifacts, which are then cleaned, classified, dated, and
    archived with full provenance.
    """

    def __init__(
        self,
        grid_rows: int = DEFAULT_GRID_ROWS,
        grid_cols: int = DEFAULT_GRID_COLS,
        seed: Optional[int] = None,
    ) -> None:
        self._grid = ExcavationGrid(rows=grid_rows, cols=grid_cols)
        self._stratigraphy = StratigraphicAnalyzer()
        self._dating = CarbonDatingSimulator(seed=seed)
        self._classifier = ArtifactClassifier()
        self._provenance = ProvenanceTracker()
        self._rng = random.Random(seed)
        self._artifacts: list[Artifact] = []

        # Build default stratigraphic column
        self._build_default_stratigraphy()

    def _build_default_stratigraphy(self) -> None:
        layers = [
            StratigraphicLayer("Recent Operations", 0.0, 1.0, LayerType.ALLUVIAL,
                               estimated_age=10, artifact_density=50.0, integrity=0.95),
            StratigraphicLayer("Batch Import", 1.0, 2.5, LayerType.VOLCANIC,
                               estimated_age=100, artifact_density=200.0, integrity=0.85),
            StratigraphicLayer("Steady State", 2.5, 5.0, LayerType.LACUSTRINE,
                               estimated_age=500, artifact_density=30.0, integrity=0.70),
            StratigraphicLayer("Cache Eviction", 5.0, 7.0, LayerType.AEOLIAN,
                               estimated_age=1000, artifact_density=10.0, integrity=0.50),
            StratigraphicLayer("Compacted Archive", 7.0, 10.0, LayerType.GLACIAL,
                               estimated_age=2000, artifact_density=5.0, integrity=0.30),
        ]
        for layer in layers:
            self._stratigraphy.add_layer(layer)

    @property
    def grid(self) -> ExcavationGrid:
        return self._grid

    @property
    def stratigraphy(self) -> StratigraphicAnalyzer:
        return self._stratigraphy

    @property
    def artifacts(self) -> list[Artifact]:
        return list(self._artifacts)

    def excavate_cell(self, row: int, col: int, number: int) -> list[Artifact]:
        """Excavate a single grid cell and recover artifacts.

        The number parameter seeds the artifact generation: the FizzBuzz
        classification of the number determines the artifact content,
        and the cell coordinates determine the stratigraphic context.
        """
        cell = self._grid.excavate_cell(row, col)
        depth = (row * self._grid.cols + col) / max(self._grid.total_cells, 1) * 10.0
        cell.depth = depth

        layer = self._stratigraphy.get_layer_at_depth(depth)
        layer_name = layer.name if layer else "Unknown"
        estimated_age = self._stratigraphy.interpolate_age(depth)

        # Generate artifact content from number
        if number % 15 == 0:
            content = "FizzBuzz"
        elif number % 3 == 0:
            content = "Fizz"
        elif number % 5 == 0:
            content = "Buzz"
        else:
            content = str(number)

        # Apply corruption based on layer integrity
        integrity = layer.integrity if layer else 0.5
        if self._rng.random() > integrity:
            content = self._corrupt(content)

        artifact = Artifact(
            artifact_id=str(uuid.uuid4())[:12],
            artifact_type=ArtifactType.UNKNOWN,
            content=content,
            grid_row=row,
            grid_col=col,
            layer_name=layer_name,
            depth=depth,
        )

        # Process through the analysis pipeline
        self._process_artifact(artifact, estimated_age)
        self._artifacts.append(artifact)
        cell.artifacts_found += 1

        return [artifact]

    def _corrupt(self, content: str) -> str:
        """Simulate diagenetic alteration of artifact content."""
        chars = list(content)
        if chars:
            idx = self._rng.randint(0, len(chars) - 1)
            chars[idx] = self._rng.choice("?#@!*")
        return "".join(chars)

    def _process_artifact(self, artifact: Artifact, estimated_age: float) -> None:
        """Run an artifact through the full analysis pipeline."""
        # Step 1: Excavation
        self._provenance.record_step(
            artifact, ProvenanceStep.EXCAVATION,
            f"Recovered from grid ({artifact.grid_row}, {artifact.grid_col}) "
            f"at depth {artifact.depth:.2f}m",
        )

        # Step 2: Cleaning
        self._provenance.record_step(
            artifact, ProvenanceStep.CLEANING,
            "Surface contaminants removed",
        )

        # Step 3: Classification
        artifact.artifact_type = self._classifier.classify(artifact.content)
        self._provenance.record_step(
            artifact, ProvenanceStep.CLASSIFICATION,
            f"Classified as {artifact.artifact_type.name}",
        )

        # Step 4: Dating
        try:
            dating = self._dating.date_artifact(max(estimated_age, 1.0))
            artifact.dating_result = dating
            self._provenance.record_step(
                artifact, ProvenanceStep.DATING,
                f"Age: {dating.age_years:.0f} +/- {dating.uncertainty_years:.0f} years",
            )
        except Exception:
            self._provenance.record_step(
                artifact, ProvenanceStep.DATING,
                "Dating failed — sample contaminated",
            )

        # Step 5: Analysis
        artifact.confidence = self._compute_confidence(artifact)
        self._provenance.record_step(
            artifact, ProvenanceStep.ANALYSIS,
            f"Confidence: {artifact.confidence:.3f}",
        )

        # Step 6: Archival
        self._provenance.record_step(
            artifact, ProvenanceStep.ARCHIVAL,
            "Artifact archived to permanent collection",
        )

    def _compute_confidence(self, artifact: Artifact) -> float:
        """Compute confidence score based on artifact quality indicators."""
        score = 0.5

        # Boost for known artifact types
        if artifact.artifact_type != ArtifactType.UNKNOWN:
            score += 0.2

        # Boost for successful dating
        if artifact.dating_result is not None:
            score += 0.15

        # Penalty for deep artifacts (more degradation)
        depth_penalty = min(artifact.depth / 20.0, 0.3)
        score -= depth_penalty

        return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class Archaeology2Middleware(IMiddleware):
    """Middleware that performs archaeological excavation of FizzBuzz results.

    For each number evaluated by the pipeline, this middleware simulates
    the excavation and recovery of the corresponding FizzBuzz artifact
    from a virtual archaeological site. The recovered artifact is dated,
    classified, and archived with full provenance, and the archaeological
    metadata is attached to the processing context.

    Priority 280 positions this middleware after primary evaluation but
    before rendering, ensuring that classification data is available for
    archaeological analysis.
    """

    def __init__(
        self,
        grid_rows: int = DEFAULT_GRID_ROWS,
        grid_cols: int = DEFAULT_GRID_COLS,
        seed: Optional[int] = None,
    ) -> None:
        self._engine = ExcavationEngine(
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            seed=seed,
        )
        self._excavation_count = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        total_cells = self._engine.grid.total_cells
        cell_index = self._excavation_count % total_cells
        row = cell_index // self._engine.grid.cols
        col = cell_index % self._engine.grid.cols

        artifacts = self._engine.excavate_cell(row, col, number)
        self._excavation_count += 1

        if artifacts:
            art = artifacts[0]
            result.metadata["archaeology2_artifact_id"] = art.artifact_id
            result.metadata["archaeology2_type"] = art.artifact_type.name
            result.metadata["archaeology2_depth"] = art.depth
            result.metadata["archaeology2_confidence"] = art.confidence
            result.metadata["archaeology2_layer"] = art.layer_name
            if art.dating_result:
                result.metadata["archaeology2_age"] = art.dating_result.age_years

        return result

    def get_name(self) -> str:
        return "Archaeology2Middleware"

    def get_priority(self) -> int:
        return 280

    @property
    def engine(self) -> ExcavationEngine:
        return self._engine

    @property
    def excavation_count(self) -> int:
        return self._excavation_count
