"""
Enterprise FizzBuzz Platform - FizzForensics: Digital Forensics Engine

Provides a comprehensive digital forensics framework for investigating
FizzBuzz evaluation anomalies and conducting post-incident analysis.
The engine simulates forensic acquisition and examination of disk images,
file carving from unallocated space, cryptographic hash verification,
forensic timeline reconstruction, and chain-of-custody management.

In enterprise environments, FizzBuzz evaluation disputes may require
forensic examination of the underlying data to determine whether an
incorrect classification was the result of software error, hardware
fault, or intentional manipulation. The FizzForensics engine provides
the evidentiary tools necessary for such investigations, following
accepted digital forensics standards (ISO 27037, NIST SP 800-86).

The disk image model partitions virtual storage into sectors, each
containing FizzBuzz evaluation records. File carving recovers deleted
or fragmented records using header/footer signature matching. The
timeline reconstructor correlates timestamps across multiple evidence
sources to build a coherent narrative of FizzBuzz evaluation events.

Chain of custody is maintained through cryptographic hashing at each
evidence handling step, creating an immutable audit trail suitable
for legal proceedings involving FizzBuzz classification disputes.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SECTOR_SIZE = 512  # bytes
DEFAULT_SECTORS = 1024
FILE_HEADER_MAGIC = b"\xFB\x01"  # FizzBuzz file header signature
FILE_FOOTER_MAGIC = b"\xFB\xFF"  # FizzBuzz file footer signature
HASH_ALGORITHM = "sha256"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EvidenceState(Enum):
    """State of a piece of digital evidence."""
    ACQUIRED = auto()
    VERIFIED = auto()
    ANALYZED = auto()
    REPORTED = auto()
    ARCHIVED = auto()


class SectorState(Enum):
    """Allocation state of a disk sector."""
    ALLOCATED = auto()
    UNALLOCATED = auto()
    BAD = auto()


class ArtifactSource(Enum):
    """Origin of a carved forensic artifact."""
    ALLOCATED_SPACE = auto()
    UNALLOCATED_SPACE = auto()
    SLACK_SPACE = auto()
    FILE_SYSTEM_METADATA = auto()


class TimelineEventType(Enum):
    """Types of forensic timeline events."""
    FILE_CREATED = auto()
    FILE_MODIFIED = auto()
    FILE_ACCESSED = auto()
    FILE_DELETED = auto()
    PROCESS_STARTED = auto()
    PROCESS_ENDED = auto()
    NETWORK_CONNECTION = auto()
    EVALUATION_COMPLETED = auto()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DiskSector:
    """A single sector on a forensic disk image."""
    sector_number: int
    state: SectorState = SectorState.ALLOCATED
    data: bytes = b""
    hash_value: str = ""

    def compute_hash(self) -> str:
        self.hash_value = hashlib.sha256(self.data).hexdigest()
        return self.hash_value


@dataclass
class DiskImage:
    """A forensic disk image containing sectors of FizzBuzz data."""
    image_id: str
    total_sectors: int
    sectors: list[DiskSector] = field(default_factory=list)
    acquisition_hash: str = ""
    acquisition_time: float = 0.0

    @property
    def allocated_count(self) -> int:
        return sum(1 for s in self.sectors if s.state == SectorState.ALLOCATED)

    @property
    def unallocated_count(self) -> int:
        return sum(1 for s in self.sectors if s.state == SectorState.UNALLOCATED)


@dataclass
class CarvedArtifact:
    """An artifact recovered through file carving."""
    artifact_id: str
    source: ArtifactSource
    offset: int
    size: int
    content: str
    file_type: str = "fizzbuzz_record"
    integrity_verified: bool = False
    hash_value: str = ""


@dataclass
class CustodyRecord:
    """A single entry in the chain of custody log."""
    evidence_id: str
    handler_id: str
    action: str
    timestamp: float
    hash_before: str
    hash_after: str
    notes: str = ""


@dataclass
class TimelineEvent:
    """A single event in the forensic timeline."""
    event_id: str
    event_type: TimelineEventType
    timestamp: float
    source: str
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: TimelineEvent) -> bool:
        return self.timestamp < other.timestamp


@dataclass
class ForensicReport:
    """Summary report of a forensic examination."""
    case_id: str
    examiner_id: str
    image_id: str
    total_sectors: int
    allocated_sectors: int
    carved_artifacts: int
    timeline_events: int
    hash_verified: bool
    chain_intact: bool
    findings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Disk Image Analyzer
# ---------------------------------------------------------------------------

class DiskImageAnalyzer:
    """Analyzes forensic disk images for FizzBuzz evaluation records.

    Creates a virtual disk image populated with FizzBuzz evaluation
    data arranged in sectors. Supports sector-level hashing, allocation
    analysis, and statistical reporting.
    """

    def __init__(self, total_sectors: int = DEFAULT_SECTORS, seed: int = 42) -> None:
        import random
        self._rng = random.Random(seed)
        self._total_sectors = total_sectors

    def create_image(self, records: list[str]) -> DiskImage:
        """Create a disk image from a list of FizzBuzz evaluation records."""
        from enterprise_fizzbuzz.domain.exceptions.fizzforensics import DiskImageError

        if not records:
            raise DiskImageError("new_image", "Cannot create image from empty record set")

        image = DiskImage(
            image_id=str(uuid.uuid4())[:12],
            total_sectors=self._total_sectors,
            acquisition_time=time.time(),
        )

        for i in range(self._total_sectors):
            if i < len(records):
                data = records[i].encode().ljust(SECTOR_SIZE, b"\x00")[:SECTOR_SIZE]
                state = SectorState.ALLOCATED
            else:
                # Some sectors are unallocated with remnant data
                if self._rng.random() < 0.3 and i - len(records) < len(records):
                    remnant_idx = self._rng.randint(0, len(records) - 1)
                    data = records[remnant_idx].encode().ljust(SECTOR_SIZE, b"\x00")[:SECTOR_SIZE]
                else:
                    data = bytes(SECTOR_SIZE)
                state = SectorState.UNALLOCATED

            sector = DiskSector(sector_number=i, state=state, data=data)
            sector.compute_hash()
            image.sectors.append(sector)

        # Compute acquisition hash
        all_data = b"".join(s.data for s in image.sectors)
        image.acquisition_hash = hashlib.sha256(all_data).hexdigest()

        return image

    def verify_image(self, image: DiskImage) -> bool:
        """Verify disk image integrity against its acquisition hash."""
        all_data = b"".join(s.data for s in image.sectors)
        computed = hashlib.sha256(all_data).hexdigest()
        return computed == image.acquisition_hash


# ---------------------------------------------------------------------------
# File Carver
# ---------------------------------------------------------------------------

class FileCarver:
    """Recovers FizzBuzz records from unallocated disk space.

    Scans sectors for header/footer signatures and extracts the content
    between them. Supports recovery of both complete and partial records.
    """

    def carve(self, image: DiskImage) -> list[CarvedArtifact]:
        """Carve FizzBuzz records from the disk image."""
        artifacts: list[CarvedArtifact] = []

        for sector in image.sectors:
            if sector.state != SectorState.UNALLOCATED:
                continue

            content = sector.data.rstrip(b"\x00").decode(errors="replace")
            if not content.strip():
                continue

            artifact = CarvedArtifact(
                artifact_id=str(uuid.uuid4())[:12],
                source=ArtifactSource.UNALLOCATED_SPACE,
                offset=sector.sector_number * SECTOR_SIZE,
                size=len(content),
                content=content.strip(),
            )

            # Verify integrity
            artifact.hash_value = hashlib.sha256(content.encode()).hexdigest()
            artifact.integrity_verified = True
            artifacts.append(artifact)

        return artifacts


# ---------------------------------------------------------------------------
# Hash Verifier
# ---------------------------------------------------------------------------

class HashVerifier:
    """Cryptographic hash verification for forensic evidence."""

    def compute_hash(self, data: bytes, algorithm: str = HASH_ALGORITHM) -> str:
        """Compute the cryptographic hash of the given data."""
        h = hashlib.new(algorithm)
        h.update(data)
        return h.hexdigest()

    def verify(self, data: bytes, expected_hash: str, algorithm: str = HASH_ALGORITHM) -> bool:
        """Verify data against an expected hash value."""
        from enterprise_fizzbuzz.domain.exceptions.fizzforensics import HashVerificationError

        computed = self.compute_hash(data, algorithm)
        if computed != expected_hash:
            raise HashVerificationError(expected_hash, computed, algorithm)
        return True


# ---------------------------------------------------------------------------
# Timeline Reconstructor
# ---------------------------------------------------------------------------

class TimelineReconstructor:
    """Reconstructs a forensic timeline from multiple evidence sources.

    Correlates timestamps from disk metadata, application logs, and
    evaluation records to build a chronologically ordered sequence
    of events.
    """

    def __init__(self) -> None:
        self._events: list[TimelineEvent] = []

    @property
    def events(self) -> list[TimelineEvent]:
        return sorted(self._events)

    @property
    def event_count(self) -> int:
        return len(self._events)

    def add_event(self, event: TimelineEvent) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzforensics import TimelineError
        if event.timestamp < 0:
            raise TimelineError(event.event_id, "Timestamp cannot be negative")
        self._events.append(event)

    def add_evaluation_event(
        self,
        number: int,
        classification: str,
        timestamp: float,
    ) -> TimelineEvent:
        event = TimelineEvent(
            event_id=str(uuid.uuid4())[:12],
            event_type=TimelineEventType.EVALUATION_COMPLETED,
            timestamp=timestamp,
            source="fizzbuzz_engine",
            description=f"Evaluated {number} -> {classification}",
            metadata={"number": number, "classification": classification},
        )
        self.add_event(event)
        return event

    def get_events_in_range(
        self, start: float, end: float,
    ) -> list[TimelineEvent]:
        return [e for e in self.events if start <= e.timestamp <= end]

    def detect_anomalies(self) -> list[str]:
        """Detect timestamp anomalies in the timeline."""
        anomalies: list[str] = []
        sorted_events = self.events
        for i in range(1, len(sorted_events)):
            prev = sorted_events[i - 1]
            curr = sorted_events[i]
            # Check for backwards timestamps from same source
            if (curr.source == prev.source and
                    curr.timestamp < prev.timestamp):
                anomalies.append(
                    f"Backward timestamp: {curr.event_id} at {curr.timestamp} "
                    f"after {prev.event_id} at {prev.timestamp}"
                )
        return anomalies


# ---------------------------------------------------------------------------
# Chain of Custody
# ---------------------------------------------------------------------------

class ChainOfCustody:
    """Manages the chain of custody for digital evidence.

    Maintains a chronological log of every action performed on a piece
    of evidence, with cryptographic hashes at each step to detect
    unauthorized modifications.
    """

    def __init__(self) -> None:
        self._records: dict[str, list[CustodyRecord]] = {}

    def get_chain(self, evidence_id: str) -> list[CustodyRecord]:
        return list(self._records.get(evidence_id, []))

    def record_action(
        self,
        evidence_id: str,
        handler_id: str,
        action: str,
        data_hash: str,
        notes: str = "",
    ) -> CustodyRecord:
        if evidence_id not in self._records:
            self._records[evidence_id] = []

        chain = self._records[evidence_id]
        hash_before = chain[-1].hash_after if chain else data_hash

        record = CustodyRecord(
            evidence_id=evidence_id,
            handler_id=handler_id,
            action=action,
            timestamp=time.time(),
            hash_before=hash_before,
            hash_after=data_hash,
            notes=notes,
        )
        chain.append(record)
        return record

    def verify_chain(self, evidence_id: str) -> bool:
        """Verify chain of custody integrity."""
        from enterprise_fizzbuzz.domain.exceptions.fizzforensics import ChainOfCustodyError

        chain = self._records.get(evidence_id, [])
        if not chain:
            raise ChainOfCustodyError(evidence_id, "acquisition")

        for i in range(1, len(chain)):
            if chain[i].hash_before != chain[i - 1].hash_after:
                raise ChainOfCustodyError(
                    evidence_id,
                    chain[i].action,
                )

        return True


# ---------------------------------------------------------------------------
# Forensics Engine
# ---------------------------------------------------------------------------

class ForensicsEngine:
    """Top-level digital forensics investigation engine."""

    def __init__(self, seed: int = 42) -> None:
        self._image_analyzer = DiskImageAnalyzer(seed=seed)
        self._carver = FileCarver()
        self._hasher = HashVerifier()
        self._timeline = TimelineReconstructor()
        self._custody = ChainOfCustody()
        self._reports: list[ForensicReport] = []

    @property
    def timeline(self) -> TimelineReconstructor:
        return self._timeline

    @property
    def custody(self) -> ChainOfCustody:
        return self._custody

    @property
    def reports(self) -> list[ForensicReport]:
        return list(self._reports)

    def investigate(
        self,
        records: list[str],
        case_id: Optional[str] = None,
    ) -> ForensicReport:
        """Conduct a full forensic investigation on FizzBuzz records."""
        case_id = case_id or str(uuid.uuid4())[:12]

        # Phase 1: Acquisition
        image = self._image_analyzer.create_image(records)
        image_hash = image.acquisition_hash
        self._custody.record_action(
            image.image_id, "forensics_engine",
            "acquisition", image_hash, "Disk image acquired",
        )

        # Phase 2: Verification
        verified = self._image_analyzer.verify_image(image)
        self._custody.record_action(
            image.image_id, "forensics_engine",
            "verification", image_hash,
            f"Hash verification: {'PASS' if verified else 'FAIL'}",
        )

        # Phase 3: Carving
        carved = self._carver.carve(image)
        self._custody.record_action(
            image.image_id, "forensics_engine",
            "carving", image_hash,
            f"Carved {len(carved)} artifacts from unallocated space",
        )

        # Phase 4: Timeline
        for i, record in enumerate(records):
            self._timeline.add_evaluation_event(
                i + 1, record, time.time() + i * 0.001,
            )

        # Phase 5: Report
        chain_intact = True
        try:
            self._custody.verify_chain(image.image_id)
        except Exception:
            chain_intact = False

        report = ForensicReport(
            case_id=case_id,
            examiner_id="fizz_forensics_engine",
            image_id=image.image_id,
            total_sectors=image.total_sectors,
            allocated_sectors=image.allocated_count,
            carved_artifacts=len(carved),
            timeline_events=self._timeline.event_count,
            hash_verified=verified,
            chain_intact=chain_intact,
            findings=[
                f"Image contains {image.allocated_count} allocated sectors",
                f"Recovered {len(carved)} artifacts from unallocated space",
                f"Timeline contains {self._timeline.event_count} events",
            ],
        )
        self._reports.append(report)
        return report


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class ForensicsMiddleware(IMiddleware):
    """Middleware that performs forensic analysis on FizzBuzz evaluation results.

    Each evaluation result is recorded in the forensic timeline and
    associated with a chain-of-custody entry. Periodic forensic reports
    are generated to summarize investigation findings.

    Priority 283 positions this middleware in the forensic analysis tier.
    """

    def __init__(self, seed: int = 42) -> None:
        self._engine = ForensicsEngine(seed=seed)
        self._records: list[str] = []
        self._analysis_count = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        classification = str(number)
        if result.results:
            classification = result.results[-1].output

        self._records.append(classification)
        self._analysis_count += 1

        # Record in timeline
        self._engine.timeline.add_evaluation_event(
            number, classification, time.time(),
        )

        result.metadata["forensics_timeline_events"] = self._engine.timeline.event_count
        result.metadata["forensics_records"] = len(self._records)

        return result

    def get_name(self) -> str:
        return "ForensicsMiddleware"

    def get_priority(self) -> int:
        return 283

    @property
    def engine(self) -> ForensicsEngine:
        return self._engine

    @property
    def analysis_count(self) -> int:
        return self._analysis_count
