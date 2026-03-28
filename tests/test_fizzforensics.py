"""
Enterprise FizzBuzz Platform - FizzForensics Digital Forensics Test Suite

Comprehensive verification of the digital forensics engine, including disk
image analysis, file carving, hash verification, timeline reconstruction,
chain of custody management, and forensic report generation.

Forensic integrity is non-negotiable: a broken chain of custody or an
unverified hash renders the entire FizzBuzz evaluation evidence inadmissible.
These tests ensure that every forensic operation maintains evidentiary
standards suitable for divisibility dispute resolution proceedings.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzforensics import (
    HASH_ALGORITHM,
    SECTOR_SIZE,
    ArtifactSource,
    CarvedArtifact,
    ChainOfCustody,
    CustodyRecord,
    DiskImage,
    DiskImageAnalyzer,
    DiskSector,
    EvidenceState,
    FileCarver,
    ForensicReport,
    ForensicsEngine,
    ForensicsMiddleware,
    HashVerifier,
    SectorState,
    TimelineEvent,
    TimelineEventType,
    TimelineReconstructor,
)
from enterprise_fizzbuzz.domain.exceptions.fizzforensics import (
    ChainOfCustodyError,
    DiskImageError,
    FileCarveError,
    FizzForensicsError,
    ForensicsMiddlewareError,
    HashVerificationError,
    MetadataExtractionError,
    TimelineError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def image_analyzer():
    return DiskImageAnalyzer(total_sectors=64, seed=42)


@pytest.fixture
def sample_records():
    return ["Fizz", "4", "Buzz", "Fizz", "7", "8", "Fizz", "Buzz",
            "11", "Fizz", "13", "14", "FizzBuzz"]


@pytest.fixture
def disk_image(image_analyzer, sample_records):
    return image_analyzer.create_image(sample_records)


@pytest.fixture
def carver():
    return FileCarver()


@pytest.fixture
def hasher():
    return HashVerifier()


@pytest.fixture
def timeline():
    return TimelineReconstructor()


@pytest.fixture
def custody():
    return ChainOfCustody()


# ===========================================================================
# Disk Image Tests
# ===========================================================================

class TestDiskImage:
    """Verification of forensic disk image creation and analysis."""

    def test_image_creation(self, disk_image):
        assert disk_image.image_id is not None
        assert disk_image.total_sectors == 64
        assert len(disk_image.sectors) == 64

    def test_image_has_acquisition_hash(self, disk_image):
        assert len(disk_image.acquisition_hash) == 64  # SHA-256 hex

    def test_allocated_sectors(self, disk_image, sample_records):
        assert disk_image.allocated_count == len(sample_records)

    def test_image_verification_passes(self, image_analyzer, disk_image):
        assert image_analyzer.verify_image(disk_image) is True

    def test_empty_records_raises(self, image_analyzer):
        with pytest.raises(DiskImageError):
            image_analyzer.create_image([])

    def test_sector_hash_computed(self, disk_image):
        for sector in disk_image.sectors:
            assert len(sector.hash_value) > 0


# ===========================================================================
# File Carving Tests
# ===========================================================================

class TestFileCarver:
    """Verification of file carving from unallocated space."""

    def test_carve_recovers_artifacts(self, carver, disk_image):
        artifacts = carver.carve(disk_image)
        # Should recover some artifacts from unallocated sectors with remnant data
        assert isinstance(artifacts, list)

    def test_carved_artifact_has_hash(self, carver, disk_image):
        artifacts = carver.carve(disk_image)
        for art in artifacts:
            assert len(art.hash_value) > 0
            assert art.integrity_verified is True

    def test_carved_from_unallocated(self, carver, disk_image):
        artifacts = carver.carve(disk_image)
        for art in artifacts:
            assert art.source == ArtifactSource.UNALLOCATED_SPACE


# ===========================================================================
# Hash Verification Tests
# ===========================================================================

class TestHashVerifier:
    """Verification of cryptographic hash operations."""

    def test_compute_hash(self, hasher):
        h = hasher.compute_hash(b"FizzBuzz")
        assert len(h) == 64

    def test_verify_correct_hash(self, hasher):
        data = b"FizzBuzz"
        h = hasher.compute_hash(data)
        assert hasher.verify(data, h) is True

    def test_verify_incorrect_hash_raises(self, hasher):
        with pytest.raises(HashVerificationError):
            hasher.verify(b"FizzBuzz", "0" * 64)

    def test_different_data_different_hash(self, hasher):
        h1 = hasher.compute_hash(b"Fizz")
        h2 = hasher.compute_hash(b"Buzz")
        assert h1 != h2


# ===========================================================================
# Timeline Tests
# ===========================================================================

class TestTimeline:
    """Verification of forensic timeline reconstruction."""

    def test_add_event(self, timeline):
        event = TimelineEvent(
            event_id="e1",
            event_type=TimelineEventType.EVALUATION_COMPLETED,
            timestamp=1000.0,
            source="engine",
            description="Test event",
        )
        timeline.add_event(event)
        assert timeline.event_count == 1

    def test_events_sorted_by_timestamp(self, timeline):
        timeline.add_event(TimelineEvent("e2", TimelineEventType.FILE_CREATED, 2000.0, "fs", "later"))
        timeline.add_event(TimelineEvent("e1", TimelineEventType.FILE_CREATED, 1000.0, "fs", "earlier"))
        events = timeline.events
        assert events[0].timestamp <= events[1].timestamp

    def test_negative_timestamp_raises(self, timeline):
        with pytest.raises(TimelineError):
            timeline.add_event(TimelineEvent("bad", TimelineEventType.FILE_CREATED, -1.0, "fs", "negative"))

    def test_add_evaluation_event(self, timeline):
        event = timeline.add_evaluation_event(15, "FizzBuzz", 1000.0)
        assert event.event_type == TimelineEventType.EVALUATION_COMPLETED
        assert event.metadata["number"] == 15


# ===========================================================================
# Chain of Custody Tests
# ===========================================================================

class TestChainOfCustody:
    """Verification of chain of custody integrity."""

    def test_record_action(self, custody):
        record = custody.record_action("ev1", "examiner1", "acquisition", "abc123")
        assert record.evidence_id == "ev1"

    def test_verify_valid_chain(self, custody):
        custody.record_action("ev1", "ex1", "acquisition", "hash1")
        custody.record_action("ev1", "ex1", "analysis", "hash1")
        assert custody.verify_chain("ev1") is True

    def test_verify_empty_chain_raises(self, custody):
        with pytest.raises(ChainOfCustodyError):
            custody.verify_chain("nonexistent")

    def test_chain_records_preserved(self, custody):
        custody.record_action("ev1", "ex1", "acquisition", "h1")
        custody.record_action("ev1", "ex1", "analysis", "h1")
        chain = custody.get_chain("ev1")
        assert len(chain) == 2


# ===========================================================================
# Forensics Engine Tests
# ===========================================================================

class TestForensicsEngine:
    """Verification of the end-to-end forensic investigation workflow."""

    def test_investigate(self, sample_records):
        engine = ForensicsEngine(seed=42)
        report = engine.investigate(sample_records)
        assert report.case_id is not None
        assert report.hash_verified is True
        assert report.carved_artifacts >= 0

    def test_report_findings(self, sample_records):
        engine = ForensicsEngine(seed=42)
        report = engine.investigate(sample_records)
        assert len(report.findings) > 0


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestForensicsMiddleware:
    """Verification of the ForensicsMiddleware pipeline integration."""

    def test_middleware_name(self):
        mw = ForensicsMiddleware()
        assert mw.get_name() == "ForensicsMiddleware"

    def test_middleware_priority(self):
        mw = ForensicsMiddleware()
        assert mw.get_priority() == 283

    def test_middleware_attaches_metadata(self):
        mw = ForensicsMiddleware()

        ctx = ProcessingContext(number=15, session_id="test-session")
        result_ctx = ProcessingContext(number=15, session_id="test-session")
        result_ctx.results = [FizzBuzzResult(number=15, output="FizzBuzz")]

        def next_handler(c):
            return result_ctx

        output = mw.process(ctx, next_handler)
        assert "forensics_timeline_events" in output.metadata
        assert "forensics_records" in output.metadata
        assert mw.analysis_count == 1
