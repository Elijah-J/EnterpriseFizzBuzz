"""
Enterprise FizzBuzz Platform - Live Process Migration Test Suite

Comprehensive tests for the FizzMigrate subsystem, covering checkpoint
creation, integrity verification, pre-copy convergence, post-copy demand
faulting, stop-and-copy transfer, validation, and the ASCII dashboard.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from process_migration import (
    CheckpointImage,
    DemandFaultError,
    DirtyPageEntry,
    DirtyPageTracker,
    MigrationConvergenceError,
    MigrationDashboard,
    MigrationError,
    MigrationIntegrityError,
    MigrationMetrics,
    MigrationMiddleware,
    MigrationOrchestrator,
    MigrationPhase,
    MigrationStrategy,
    MigrationValidationError,
    MigrationValidator,
    PageState,
    PostCopyMigrator,
    PreCopyMigrator,
    StateCollector,
    StateRestorer,
    StopAndCopyMigrator,
    SubsystemState,
    TransferRound,
    create_migration_subsystem,
)
from config import ConfigurationManager, _SingletonMeta
from models import ProcessingContext, FizzBuzzResult


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


# ---------------------------------------------------------------------------
# SubsystemState Tests
# ---------------------------------------------------------------------------


class TestSubsystemState:
    """Tests for the SubsystemState data class."""

    def test_creation_with_defaults(self):
        state = SubsystemState(name="cache")
        assert state.name == "cache"
        assert state.state_data == {}
        assert state.size_bytes == 0
        assert state.dirty is False
        assert state.version == 0

    def test_mark_dirty(self):
        state = SubsystemState(name="cache")
        state.mark_dirty()
        assert state.dirty is True
        assert state.version == 1

    def test_mark_dirty_increments_version(self):
        state = SubsystemState(name="cache")
        state.mark_dirty()
        state.mark_dirty()
        state.mark_dirty()
        assert state.version == 3

    def test_mark_clean(self):
        state = SubsystemState(name="cache")
        state.mark_dirty()
        state.mark_clean()
        assert state.dirty is False

    def test_serialize_produces_valid_json(self):
        state = SubsystemState(
            name="cache",
            state_data={"entries": 42, "hit_ratio": 0.95},
        )
        serialized = state.serialize()
        parsed = json.loads(serialized)
        assert parsed["name"] == "cache"
        assert parsed["state_data"]["entries"] == 42

    def test_serialize_updates_size(self):
        state = SubsystemState(name="cache", state_data={"key": "value"})
        state.serialize()
        assert state.size_bytes > 0

    def test_deserialize_round_trip(self):
        original = SubsystemState(
            name="metrics",
            state_data={"counters": {"fizz": 33, "buzz": 20}},
            version=5,
        )
        serialized = original.serialize()
        restored = SubsystemState.deserialize(serialized)
        assert restored.name == "metrics"
        assert restored.state_data["counters"]["fizz"] == 33
        assert restored.version == 5

    def test_page_id_is_generated(self):
        s1 = SubsystemState(name="a")
        s2 = SubsystemState(name="b")
        assert len(s1.page_id) == 12
        assert s1.page_id != s2.page_id


# ---------------------------------------------------------------------------
# CheckpointImage Tests
# ---------------------------------------------------------------------------


class TestCheckpointImage:
    """Tests for CheckpointImage serialization and integrity."""

    def test_empty_image(self):
        image = CheckpointImage()
        assert image.subsystem_count == 0
        assert image.total_size_bytes == 0

    def test_add_subsystem_state(self):
        image = CheckpointImage()
        image.subsystem_states["cache"] = SubsystemState(
            name="cache",
            state_data={"entries": 10},
        )
        assert image.subsystem_count == 1

    def test_compute_integrity_hash(self):
        image = CheckpointImage()
        image.subsystem_states["cache"] = SubsystemState(
            name="cache",
            state_data={"entries": 10},
        )
        h = image.compute_integrity_hash()
        assert len(h) == 64  # SHA-256 hex digest
        assert image.integrity_hash == h

    def test_integrity_hash_changes_with_state(self):
        image = CheckpointImage()
        image.subsystem_states["cache"] = SubsystemState(
            name="cache", state_data={"entries": 10}
        )
        h1 = image.compute_integrity_hash()

        image.subsystem_states["cache"].state_data["entries"] = 20
        h2 = image.compute_integrity_hash()

        assert h1 != h2

    def test_verify_integrity_passes(self):
        image = CheckpointImage()
        image.subsystem_states["x"] = SubsystemState(
            name="x", state_data={"a": 1}
        )
        image.compute_integrity_hash()
        assert image.verify_integrity() is True

    def test_verify_integrity_detects_tampering(self):
        image = CheckpointImage()
        image.subsystem_states["x"] = SubsystemState(
            name="x", state_data={"a": 1}
        )
        image.compute_integrity_hash()
        # Tamper with the data
        image.subsystem_states["x"].state_data["a"] = 999
        # Now hash won't match the stored one
        stored = image.integrity_hash
        image.compute_integrity_hash()
        assert image.integrity_hash != stored

    def test_to_json_and_from_json(self):
        image = CheckpointImage(
            source_host="host-a",
            destination_host="host-b",
        )
        image.subsystem_states["cache"] = SubsystemState(
            name="cache",
            state_data={"entries": 42},
        )
        image.subsystem_states["metrics"] = SubsystemState(
            name="metrics",
            state_data={"counters": {"fizz": 33}},
        )
        json_str = image.to_json()
        restored = CheckpointImage.from_json(json_str)

        assert restored.source_host == "host-a"
        assert restored.destination_host == "host-b"
        assert restored.subsystem_count == 2
        assert restored.subsystem_states["cache"].state_data["entries"] == 42

    def test_from_json_preserves_integrity_hash(self):
        image = CheckpointImage()
        image.subsystem_states["x"] = SubsystemState(
            name="x", state_data={"v": 1}
        )
        json_str = image.to_json()
        restored = CheckpointImage.from_json(json_str)
        assert restored.integrity_hash == image.integrity_hash

    def test_total_size_bytes(self):
        image = CheckpointImage()
        image.subsystem_states["a"] = SubsystemState(
            name="a", state_data={"key": "x" * 100}
        )
        assert image.total_size_bytes > 100

    def test_partial_image_flag(self):
        image = CheckpointImage(is_partial=True)
        assert image.is_partial is True
        json_str = image.to_json()
        restored = CheckpointImage.from_json(json_str)
        assert restored.is_partial is True


# ---------------------------------------------------------------------------
# StateCollector Tests
# ---------------------------------------------------------------------------


class TestStateCollector:
    """Tests for the StateCollector."""

    def test_register_provider(self):
        collector = StateCollector()
        collector.register_provider("cache", lambda: {"entries": 5})
        assert collector.provider_count == 1

    def test_capture_all(self):
        collector = StateCollector()
        collector.register_provider("cache", lambda: {"entries": 5})
        collector.register_provider("metrics", lambda: {"counters": {}})
        image = collector.capture()
        assert image.subsystem_count == 2
        assert "cache" in image.subsystem_states
        assert "metrics" in image.subsystem_states

    def test_capture_partial(self):
        collector = StateCollector()
        collector.register_provider("cache", lambda: {"entries": 5})
        collector.register_provider("metrics", lambda: {"counters": {}})
        image = collector.capture(partial_names=["cache"])
        assert image.subsystem_count == 1
        assert image.is_partial is True

    def test_capture_with_failing_provider(self):
        collector = StateCollector()
        collector.register_provider("bad", lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        collector.register_provider("good", lambda: {"ok": True})
        image = collector.capture()
        assert image.subsystem_count == 2
        assert image.subsystem_states["bad"].state_data.get("error") == "fail"

    def test_unregister_provider(self):
        collector = StateCollector()
        collector.register_provider("cache", lambda: {})
        collector.unregister_provider("cache")
        assert collector.provider_count == 0

    def test_capture_produces_integrity_hash(self):
        collector = StateCollector()
        collector.register_provider("x", lambda: {"v": 1})
        image = collector.capture()
        assert len(image.integrity_hash) == 64

    def test_capture_increments_count(self):
        collector = StateCollector()
        collector.register_provider("x", lambda: {})
        collector.capture()
        img2 = collector.capture()
        assert img2.metadata["capture_count"] == 2


# ---------------------------------------------------------------------------
# DirtyPageTracker Tests
# ---------------------------------------------------------------------------


class TestDirtyPageTracker:
    """Tests for the DirtyPageTracker."""

    def test_register_page(self):
        tracker = DirtyPageTracker()
        tracker.register_page("p1", "cache")
        assert tracker.total_count == 1

    def test_mark_dirty(self):
        tracker = DirtyPageTracker()
        tracker.register_page("p1", "cache")
        tracker.mark_dirty("p1")
        assert tracker.dirty_count == 1

    def test_mark_transferred(self):
        tracker = DirtyPageTracker()
        tracker.register_page("p1", "cache")
        tracker.mark_dirty("p1")
        tracker.mark_transferred("p1")
        assert tracker.dirty_count == 0

    def test_dirty_ratio(self):
        tracker = DirtyPageTracker()
        tracker.register_page("p1", "a")
        tracker.register_page("p2", "b")
        tracker.mark_dirty("p1")
        assert tracker.dirty_ratio == 0.5

    def test_dirty_ratio_empty(self):
        tracker = DirtyPageTracker()
        assert tracker.dirty_ratio == 0.0

    def test_get_dirty_subsystem_names(self):
        tracker = DirtyPageTracker()
        tracker.register_page("p1", "cache")
        tracker.register_page("p2", "metrics")
        tracker.mark_dirty("p1")
        names = tracker.get_dirty_subsystem_names()
        assert "cache" in names
        assert "metrics" not in names

    def test_advance_round(self):
        tracker = DirtyPageTracker()
        assert tracker.round_number == 0
        tracker.advance_round()
        assert tracker.round_number == 1

    def test_reset(self):
        tracker = DirtyPageTracker()
        tracker.register_page("p1", "cache")
        tracker.mark_dirty("p1")
        tracker.reset()
        assert tracker.total_count == 0
        assert tracker.dirty_count == 0

    def test_mark_faulted(self):
        tracker = DirtyPageTracker()
        tracker.register_page("p1", "cache")
        tracker.mark_faulted("p1")
        page = tracker._pages["p1"]
        assert page.state == PageState.FAULTED


# ---------------------------------------------------------------------------
# StateRestorer Tests
# ---------------------------------------------------------------------------


class TestStateRestorer:
    """Tests for the StateRestorer."""

    def test_restore_calls_handler(self):
        restorer = StateRestorer()
        received = {}

        def handler(data):
            received.update(data)

        restorer.register_handler("cache", handler)

        image = CheckpointImage()
        image.subsystem_states["cache"] = SubsystemState(
            name="cache", state_data={"entries": 42}
        )

        restored = restorer.restore(image)
        assert "cache" in restored
        assert received["entries"] == 42

    def test_restore_skips_unregistered(self):
        restorer = StateRestorer()
        image = CheckpointImage()
        image.subsystem_states["unknown"] = SubsystemState(
            name="unknown", state_data={}
        )
        restored = restorer.restore(image)
        assert len(restored) == 0

    def test_restore_handles_handler_failure(self):
        restorer = StateRestorer()

        def bad_handler(data):
            raise RuntimeError("restore failed")

        restorer.register_handler("bad", bad_handler)
        image = CheckpointImage()
        image.subsystem_states["bad"] = SubsystemState(
            name="bad", state_data={}
        )
        restored = restorer.restore(image)
        assert "bad" not in restored

    def test_restore_verifies_integrity(self):
        restorer = StateRestorer()
        restorer.register_handler("x", lambda d: None)

        image = CheckpointImage()
        image.subsystem_states["x"] = SubsystemState(
            name="x", state_data={"v": 1}
        )
        image.compute_integrity_hash()
        # Tamper
        image.subsystem_states["x"].state_data["v"] = 999

        with pytest.raises(MigrationIntegrityError):
            restorer.restore(image)

    def test_restore_count(self):
        restorer = StateRestorer()
        restorer.register_handler("x", lambda d: None)
        image = CheckpointImage()
        image.subsystem_states["x"] = SubsystemState(name="x", state_data={})
        restorer.restore(image)
        restorer.restore(image)
        assert restorer.restore_count == 2

    def test_demand_fault(self):
        restorer = StateRestorer()
        restorer.register_demand_fault_handler(
            "cache", lambda name: {"faulted": True}
        )
        result = restorer.demand_fault("cache")
        assert result == {"faulted": True}

    def test_demand_fault_missing(self):
        restorer = StateRestorer()
        result = restorer.demand_fault("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# TransferRound Tests
# ---------------------------------------------------------------------------


class TestTransferRound:
    """Tests for the TransferRound data class."""

    def test_throughput_calculation(self):
        tr = TransferRound(
            round_number=1,
            bytes_transferred=1024 * 1024,  # 1 MB
            duration_ns=1_000_000_000,  # 1 second
        )
        assert abs(tr.throughput_mbps - 1.0) < 0.01

    def test_throughput_zero_duration(self):
        tr = TransferRound(round_number=0, duration_ns=0)
        assert tr.throughput_mbps == 0.0


# ---------------------------------------------------------------------------
# MigrationMetrics Tests
# ---------------------------------------------------------------------------


class TestMigrationMetrics:
    """Tests for the MigrationMetrics data class."""

    def test_downtime_ms(self):
        m = MigrationMetrics()
        m.freeze_start_ns = 1_000_000_000
        m.freeze_end_ns = 1_500_000_000
        assert m.downtime_ms == 500.0

    def test_downtime_no_freeze(self):
        m = MigrationMetrics()
        assert m.downtime_ms == 0.0

    def test_total_time_ms(self):
        m = MigrationMetrics()
        m.migration_start_ns = 0
        m.migration_end_ns = 2_000_000_000
        assert m.total_time_ms == 2000.0

    def test_transfer_progress(self):
        m = MigrationMetrics()
        m.total_state_bytes = 1000
        m.transferred_bytes = 500
        assert m.transfer_progress == 0.5

    def test_transfer_progress_zero_total(self):
        m = MigrationMetrics()
        assert m.transfer_progress == 1.0

    def test_transfer_progress_capped(self):
        m = MigrationMetrics()
        m.total_state_bytes = 100
        m.transferred_bytes = 200
        assert m.transfer_progress == 1.0


# ---------------------------------------------------------------------------
# PreCopyMigrator Tests
# ---------------------------------------------------------------------------


class TestPreCopyMigrator:
    """Tests for the PreCopyMigrator."""

    def _make_collector(self, subsystems=None):
        collector = StateCollector()
        subsystems = subsystems or {
            "cache": {"entries": 10},
            "metrics": {"counters": {"fizz": 33}},
        }
        for name, state in subsystems.items():
            collector.register_provider(name, lambda s=state: dict(s))
        return collector

    def _make_restorer(self, names=None):
        restorer = StateRestorer()
        names = names or ["cache", "metrics"]
        for name in names:
            restorer.register_handler(name, lambda d, n=name: None)
        return restorer

    def test_pre_copy_completes(self):
        collector = self._make_collector()
        restorer = self._make_restorer()
        migrator = PreCopyMigrator(
            collector, restorer,
            max_rounds=5,
            convergence_threshold=0.3,
            dirty_rate_decay=0.4,
        )
        image = migrator.migrate()
        assert image.subsystem_count == 2
        assert migrator.metrics.phase == MigrationPhase.COMPLETE

    def test_pre_copy_records_rounds(self):
        collector = self._make_collector()
        restorer = self._make_restorer()
        migrator = PreCopyMigrator(
            collector, restorer,
            max_rounds=10,
            convergence_threshold=0.2,
            dirty_rate_decay=0.3,
        )
        migrator.migrate()
        assert len(migrator.metrics.transfer_rounds) >= 2

    def test_pre_copy_convergence_failure(self):
        collector = self._make_collector()
        restorer = self._make_restorer()
        migrator = PreCopyMigrator(
            collector, restorer,
            max_rounds=2,
            convergence_threshold=0.001,
            dirty_rate_decay=0.99,  # Very slow convergence
        )
        with pytest.raises(MigrationConvergenceError):
            migrator.migrate()

    def test_pre_copy_metrics_populated(self):
        collector = self._make_collector()
        restorer = self._make_restorer()
        migrator = PreCopyMigrator(
            collector, restorer,
            max_rounds=5,
            convergence_threshold=0.3,
            dirty_rate_decay=0.4,
        )
        migrator.migrate()
        m = migrator.metrics
        assert m.total_state_bytes > 0
        assert m.transferred_bytes > 0
        assert m.total_time_ms > 0
        assert m.downtime_ms >= 0


# ---------------------------------------------------------------------------
# PostCopyMigrator Tests
# ---------------------------------------------------------------------------


class TestPostCopyMigrator:
    """Tests for the PostCopyMigrator."""

    def _make_collector(self):
        collector = StateCollector()
        for name in ["configuration", "evaluation_state", "rule_engine", "cache", "metrics"]:
            collector.register_provider(
                name, lambda n=name: {"subsystem": n, "active": True}
            )
        return collector

    def _make_restorer(self):
        restorer = StateRestorer()
        for name in ["configuration", "evaluation_state", "rule_engine", "cache", "metrics"]:
            restorer.register_handler(name, lambda d, n=name: None)
        return restorer

    def test_post_copy_completes(self):
        collector = self._make_collector()
        restorer = self._make_restorer()
        migrator = PostCopyMigrator(
            collector, restorer,
            bootstrap_subsystems=["configuration", "evaluation_state", "rule_engine"],
        )
        image = migrator.migrate()
        assert image.subsystem_count == 5
        assert migrator.metrics.phase == MigrationPhase.COMPLETE

    def test_post_copy_demand_faults(self):
        collector = self._make_collector()
        restorer = self._make_restorer()
        migrator = PostCopyMigrator(
            collector, restorer,
            bootstrap_subsystems=["configuration"],
        )
        migrator.migrate()
        # Should have demand faults for non-bootstrap subsystems
        assert migrator.demand_fault_count > 0

    def test_post_copy_minimal_downtime(self):
        collector = self._make_collector()
        restorer = self._make_restorer()
        migrator = PostCopyMigrator(
            collector, restorer,
            bootstrap_subsystems=["configuration"],
        )
        migrator.migrate()
        # Downtime should be small (only bootstrap transfer)
        assert migrator.metrics.downtime_ms >= 0

    def test_post_copy_transfers_all_eventually(self):
        collector = self._make_collector()
        restorer = self._make_restorer()
        migrator = PostCopyMigrator(
            collector, restorer,
            bootstrap_subsystems=["configuration"],
        )
        migrator.migrate()
        assert migrator.metrics.transferred_bytes > 0


# ---------------------------------------------------------------------------
# StopAndCopyMigrator Tests
# ---------------------------------------------------------------------------


class TestStopAndCopyMigrator:
    """Tests for the StopAndCopyMigrator."""

    def test_stop_and_copy_completes(self):
        collector = StateCollector()
        collector.register_provider("cache", lambda: {"entries": 10})
        restorer = StateRestorer()
        restorer.register_handler("cache", lambda d: None)
        migrator = StopAndCopyMigrator(collector, restorer)
        image = migrator.migrate()
        assert image.subsystem_count == 1
        assert migrator.metrics.phase == MigrationPhase.COMPLETE

    def test_stop_and_copy_all_downtime(self):
        collector = StateCollector()
        collector.register_provider("x", lambda: {"v": 1})
        restorer = StateRestorer()
        restorer.register_handler("x", lambda d: None)
        migrator = StopAndCopyMigrator(collector, restorer)
        migrator.migrate()
        # For stop-and-copy, total time == downtime
        assert migrator.metrics.downtime_ms > 0
        assert migrator.metrics.total_time_ms >= migrator.metrics.downtime_ms

    def test_stop_and_copy_single_round(self):
        collector = StateCollector()
        collector.register_provider("x", lambda: {})
        restorer = StateRestorer()
        restorer.register_handler("x", lambda d: None)
        migrator = StopAndCopyMigrator(collector, restorer)
        migrator.migrate()
        assert len(migrator.metrics.transfer_rounds) == 1


# ---------------------------------------------------------------------------
# MigrationValidator Tests
# ---------------------------------------------------------------------------


class TestMigrationValidator:
    """Tests for the MigrationValidator."""

    def test_identical_images_pass(self):
        validator = MigrationValidator()
        image1 = CheckpointImage()
        image1.subsystem_states["x"] = SubsystemState(
            name="x", state_data={"v": 1}
        )
        image2 = CheckpointImage()
        image2.subsystem_states["x"] = SubsystemState(
            name="x", state_data={"v": 1}
        )
        passed, errors = validator.validate_checkpoint(image1, image2)
        assert passed is True
        assert len(errors) == 0

    def test_different_state_fails(self):
        validator = MigrationValidator()
        image1 = CheckpointImage()
        image1.subsystem_states["x"] = SubsystemState(
            name="x", state_data={"v": 1}
        )
        image2 = CheckpointImage()
        image2.subsystem_states["x"] = SubsystemState(
            name="x", state_data={"v": 999}
        )
        passed, errors = validator.validate_checkpoint(image1, image2)
        assert passed is False
        assert any("divergence" in e for e in errors)

    def test_missing_subsystem_fails(self):
        validator = MigrationValidator()
        image1 = CheckpointImage()
        image1.subsystem_states["x"] = SubsystemState(name="x", state_data={})
        image2 = CheckpointImage()
        passed, errors = validator.validate_checkpoint(image1, image2)
        assert passed is False

    def test_extra_subsystem_detected(self):
        validator = MigrationValidator()
        image1 = CheckpointImage()
        image2 = CheckpointImage()
        image2.subsystem_states["extra"] = SubsystemState(
            name="extra", state_data={}
        )
        passed, errors = validator.validate_checkpoint(image1, image2)
        assert passed is False
        assert any("Unexpected" in e for e in errors)

    def test_evaluation_results_match(self):
        validator = MigrationValidator()
        pre = [(1, "1"), (2, "2"), (3, "Fizz")]
        post = [(1, "1"), (2, "2"), (3, "Fizz")]
        passed, errors = validator.validate_evaluation_results(pre, post)
        assert passed is True

    def test_evaluation_results_mismatch(self):
        validator = MigrationValidator()
        pre = [(3, "Fizz")]
        post = [(3, "Buzz")]
        passed, errors = validator.validate_evaluation_results(pre, post)
        assert passed is False
        assert any("Output mismatch" in e for e in errors)

    def test_evaluation_results_length_mismatch(self):
        validator = MigrationValidator()
        pre = [(1, "1"), (2, "2")]
        post = [(1, "1")]
        passed, errors = validator.validate_evaluation_results(pre, post)
        assert passed is False
        assert any("count mismatch" in e for e in errors)

    def test_validation_count_increments(self):
        validator = MigrationValidator()
        img = CheckpointImage()
        validator.validate_checkpoint(img, img)
        validator.validate_checkpoint(img, img)
        assert validator.validation_count == 2


# ---------------------------------------------------------------------------
# MigrationOrchestrator Tests
# ---------------------------------------------------------------------------


class TestMigrationOrchestrator:
    """Tests for the MigrationOrchestrator."""

    def test_orchestrator_pre_copy(self):
        orch = MigrationOrchestrator(strategy=MigrationStrategy.PRE_COPY)
        orch.register_subsystem(
            "cache",
            lambda: {"entries": 10},
            lambda d: None,
        )
        image = orch.execute()
        assert image is not None
        assert orch.last_metrics is not None

    def test_orchestrator_post_copy(self):
        orch = MigrationOrchestrator(strategy=MigrationStrategy.POST_COPY)
        orch.register_subsystem(
            "configuration",
            lambda: {"loaded": True},
            lambda d: None,
        )
        image = orch.execute()
        assert image is not None

    def test_orchestrator_stop_and_copy(self):
        orch = MigrationOrchestrator(strategy=MigrationStrategy.STOP_AND_COPY)
        orch.register_subsystem(
            "cache",
            lambda: {"entries": 5},
            lambda d: None,
        )
        image = orch.execute()
        assert image is not None
        assert orch.last_metrics.phase == MigrationPhase.VALIDATING or \
               orch.last_metrics.phase == MigrationPhase.COMPLETE

    def test_orchestrator_saves_checkpoint_to_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name

        try:
            orch = MigrationOrchestrator(
                strategy=MigrationStrategy.STOP_AND_COPY,
                checkpoint_file=path,
            )
            orch.register_subsystem(
                "cache", lambda: {"entries": 42}, lambda d: None
            )
            orch.execute()

            # Verify file was written
            with open(path, "r") as f:
                data = json.load(f)
            assert data["subsystems"]["cache"]["state_data"]["entries"] == 42
        finally:
            os.unlink(path)

    def test_orchestrator_load_checkpoint(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name

        try:
            orch = MigrationOrchestrator(
                strategy=MigrationStrategy.STOP_AND_COPY,
                checkpoint_file=path,
            )
            orch.register_subsystem(
                "cache", lambda: {"entries": 42}, lambda d: None
            )
            orch.execute()

            loaded = MigrationOrchestrator.load_checkpoint(path)
            assert loaded.subsystem_count == 1
            assert loaded.subsystem_states["cache"].state_data["entries"] == 42
        finally:
            os.unlink(path)

    def test_orchestrator_load_checkpoint_integrity_failure(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name

        try:
            # Write a corrupted checkpoint
            image = CheckpointImage()
            image.subsystem_states["x"] = SubsystemState(
                name="x", state_data={"v": 1}
            )
            json_str = image.to_json()
            data = json.loads(json_str)
            data["subsystems"]["x"]["state_data"]["v"] = 999  # Tamper
            with open(path, "w") as f:
                json.dump(data, f, sort_keys=True, indent=2)

            with pytest.raises(MigrationIntegrityError):
                MigrationOrchestrator.load_checkpoint(path)
        finally:
            os.unlink(path)

    def test_orchestrator_strategy_property(self):
        orch = MigrationOrchestrator(strategy=MigrationStrategy.POST_COPY)
        assert orch.strategy == MigrationStrategy.POST_COPY


# ---------------------------------------------------------------------------
# MigrationMiddleware Tests
# ---------------------------------------------------------------------------


class TestMigrationMiddleware:
    """Tests for the MigrationMiddleware."""

    def _make_middleware(self, interval=5):
        orch = MigrationOrchestrator(strategy=MigrationStrategy.STOP_AND_COPY)
        orch.register_subsystem("cache", lambda: {"entries": 1}, lambda d: None)
        mw = MigrationMiddleware(orch, checkpoint_interval=interval)
        return mw

    def _make_context(self, number=1):
        ctx = ProcessingContext(number=number, session_id="test-session")
        return ctx

    def test_middleware_name(self):
        mw = self._make_middleware()
        assert mw.get_name() == "MigrationMiddleware"

    def test_middleware_priority(self):
        mw = self._make_middleware()
        assert mw.get_priority() == 995

    def test_middleware_passes_through(self):
        mw = self._make_middleware()
        ctx = self._make_context(number=3)

        def handler(c):
            c.results.append(FizzBuzzResult(number=3, output="Fizz"))
            return c

        result = mw.process(ctx, handler)
        assert len(result.results) == 1
        assert result.results[0].output == "Fizz"

    def test_middleware_counts_evaluations(self):
        mw = self._make_middleware(interval=100)
        for i in range(10):
            ctx = self._make_context(number=i)

            def handler(c, num=i):
                c.results.append(FizzBuzzResult(number=num, output=str(num)))
                return c

            mw.process(ctx, handler)
        assert mw.eval_count == 10

    def test_middleware_takes_checkpoint_at_interval(self):
        mw = self._make_middleware(interval=3)
        for i in range(1, 7):
            ctx = self._make_context(number=i)

            def handler(c, num=i):
                c.results.append(FizzBuzzResult(number=num, output=str(num)))
                return c

            mw.process(ctx, handler)

        # Checkpoints at eval 3 and 6
        assert mw.checkpoints_taken == 2

    def test_middleware_records_pre_migration_results(self):
        mw = self._make_middleware(interval=100)
        for i in [1, 2, 3]:
            ctx = self._make_context(number=i)

            def handler(c, num=i):
                out = "Fizz" if num % 3 == 0 else str(num)
                c.results.append(FizzBuzzResult(number=num, output=out))
                return c

            mw.process(ctx, handler)

        assert len(mw.results_pre_migration) == 3
        assert mw.results_pre_migration[2] == (3, "Fizz")


# ---------------------------------------------------------------------------
# MigrationDashboard Tests
# ---------------------------------------------------------------------------


class TestMigrationDashboard:
    """Tests for the MigrationDashboard."""

    def test_render_produces_output(self):
        metrics = MigrationMetrics(
            strategy="pre-copy",
            phase=MigrationPhase.COMPLETE,
            total_state_bytes=4096,
            transferred_bytes=4096,
            total_page_count=8,
            dirty_page_count=0,
            subsystem_count=4,
            validation_passed=True,
        )
        metrics.migration_start_ns = 0
        metrics.migration_end_ns = 5_000_000
        metrics.freeze_start_ns = 4_000_000
        metrics.freeze_end_ns = 5_000_000
        metrics.transfer_rounds.append(TransferRound(
            round_number=0,
            pages_transferred=4,
            bytes_transferred=4096,
            dirty_pages_remaining=0,
            duration_ns=5_000_000,
        ))

        output = MigrationDashboard.render(metrics)
        assert "FIZZMIGRATE" in output
        assert "PRE-COPY" in output
        assert "TRANSFER PROGRESS" in output
        assert "PASSED" in output

    def test_render_with_validation_errors(self):
        metrics = MigrationMetrics(
            strategy="stop-and-copy",
            phase=MigrationPhase.COMPLETE,
            validation_passed=False,
            validation_errors=["State divergence in cache"],
        )
        output = MigrationDashboard.render(metrics)
        assert "FAILED" in output
        assert "divergence" in output

    def test_render_with_demand_faults(self):
        metrics = MigrationMetrics(
            strategy="post-copy",
            phase=MigrationPhase.COMPLETE,
            total_state_bytes=1024,
            transferred_bytes=1024,
            total_page_count=4,
            dirty_page_count=0,
            subsystem_count=4,
            validation_passed=True,
        )
        metrics.demand_faults = 3
        metrics.migration_start_ns = 0
        metrics.migration_end_ns = 1_000_000
        output = MigrationDashboard.render(metrics)
        assert "Demand Faults" in output
        assert "3" in output

    def test_render_custom_width(self):
        metrics = MigrationMetrics(strategy="pre-copy")
        output = MigrationDashboard.render(metrics, width=60)
        lines = output.split("\n")
        # Title line should be 60 chars
        assert len(lines[0]) == 60


# ---------------------------------------------------------------------------
# Exception Tests
# ---------------------------------------------------------------------------


class TestMigrationExceptions:
    """Tests for migration-specific exceptions."""

    def test_migration_error(self):
        err = MigrationError("test error", migration_id="abc123")
        assert "test error" in str(err)
        assert err.migration_id == "abc123"

    def test_integrity_error(self):
        err = MigrationIntegrityError("img1", expected="aaa", actual="bbb")
        assert "img1" in str(err)
        assert err.expected == "aaa"
        assert err.actual == "bbb"

    def test_convergence_error(self):
        err = MigrationConvergenceError(rounds=10, dirty_ratio=0.5)
        assert "10 rounds" in str(err)
        assert err.rounds == 10

    def test_validation_error(self):
        err = MigrationValidationError(errors=["e1", "e2"])
        assert "2 error" in str(err)
        assert len(err.errors) == 2

    def test_demand_fault_error(self):
        err = DemandFaultError("cache")
        assert "cache" in str(err)


# ---------------------------------------------------------------------------
# MigrationStrategy Enum Tests
# ---------------------------------------------------------------------------


class TestMigrationStrategy:
    """Tests for the MigrationStrategy enum."""

    def test_pre_copy_value(self):
        assert MigrationStrategy.PRE_COPY.value == "pre-copy"

    def test_post_copy_value(self):
        assert MigrationStrategy.POST_COPY.value == "post-copy"

    def test_stop_and_copy_value(self):
        assert MigrationStrategy.STOP_AND_COPY.value == "stop-and-copy"

    def test_from_string(self):
        assert MigrationStrategy("pre-copy") == MigrationStrategy.PRE_COPY


# ---------------------------------------------------------------------------
# PageState Enum Tests
# ---------------------------------------------------------------------------


class TestPageState:
    """Tests for the PageState enum."""

    def test_all_states(self):
        assert PageState.CLEAN.name == "CLEAN"
        assert PageState.DIRTY.name == "DIRTY"
        assert PageState.TRANSFERRED.name == "TRANSFERRED"
        assert PageState.FAULTED.name == "FAULTED"


# ---------------------------------------------------------------------------
# Factory Function Tests
# ---------------------------------------------------------------------------


class TestCreateMigrationSubsystem:
    """Tests for the create_migration_subsystem factory."""

    def test_creates_orchestrator_and_middleware(self):
        orch, mw = create_migration_subsystem(
            strategy=MigrationStrategy.STOP_AND_COPY,
        )
        assert isinstance(orch, MigrationOrchestrator)
        assert isinstance(mw, MigrationMiddleware)

    def test_default_providers_registered(self):
        orch, mw = create_migration_subsystem()
        # Default providers include 8 subsystems
        assert orch.collector.provider_count == 8

    def test_custom_checkpoint_interval(self):
        orch, mw = create_migration_subsystem(checkpoint_interval=25)
        # Verify middleware processes at the specified interval
        # by running 25 evaluations and checking checkpoint count
        for i in range(25):
            ctx = ProcessingContext(number=i, session_id="test")

            def handler(c, num=i):
                c.results.append(FizzBuzzResult(number=num, output=str(num)))
                return c

            mw.process(ctx, handler)
        assert mw.checkpoints_taken == 1

    def test_checkpoint_file_param(self):
        orch, mw = create_migration_subsystem(
            checkpoint_file="/tmp/test_checkpoint.json",
        )
        assert orch._checkpoint_file == "/tmp/test_checkpoint.json"


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestMigrationIntegration:
    """End-to-end integration tests for the migration subsystem."""

    def test_full_pre_copy_migration(self):
        """Full pre-copy migration with default subsystems."""
        orch, mw = create_migration_subsystem(
            strategy=MigrationStrategy.PRE_COPY,
            convergence_threshold=0.3,
            dirty_rate_decay=0.4,
            max_rounds=5,
        )
        image = orch.execute()
        assert image is not None
        assert orch.last_metrics is not None
        assert len(orch.last_metrics.transfer_rounds) >= 2

    def test_full_post_copy_migration(self):
        """Full post-copy migration with demand faulting."""
        orch, mw = create_migration_subsystem(
            strategy=MigrationStrategy.POST_COPY,
        )
        image = orch.execute()
        assert image is not None
        assert orch.last_metrics is not None

    def test_full_stop_and_copy_migration(self):
        """Full stop-and-copy migration."""
        orch, mw = create_migration_subsystem(
            strategy=MigrationStrategy.STOP_AND_COPY,
        )
        image = orch.execute()
        assert image is not None
        assert len(orch.last_metrics.transfer_rounds) == 1

    def test_checkpoint_save_and_load(self):
        """Save a checkpoint and load it back."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name

        try:
            orch, mw = create_migration_subsystem(
                strategy=MigrationStrategy.STOP_AND_COPY,
                checkpoint_file=path,
            )
            orch.execute()

            loaded = MigrationOrchestrator.load_checkpoint(path)
            assert loaded.subsystem_count > 0
            assert loaded.verify_integrity() is True
        finally:
            os.unlink(path)

    def test_migration_with_middleware_pipeline(self):
        """Run evaluations through middleware, then migrate."""
        orch, mw = create_migration_subsystem(
            strategy=MigrationStrategy.STOP_AND_COPY,
            checkpoint_interval=5,
        )

        for i in range(1, 16):
            ctx = ProcessingContext(number=i, session_id="integration-test")

            def handler(c, num=i):
                if num % 15 == 0:
                    output = "FizzBuzz"
                elif num % 3 == 0:
                    output = "Fizz"
                elif num % 5 == 0:
                    output = "Buzz"
                else:
                    output = str(num)
                c.results.append(FizzBuzzResult(number=num, output=output))
                return c

            mw.process(ctx, handler)

        assert mw.eval_count == 15
        assert mw.checkpoints_taken == 3
        assert len(mw.results_pre_migration) == 15

        # Now execute migration
        image = orch.execute()
        assert image is not None

    def test_dashboard_after_migration(self):
        """Render dashboard after a complete migration."""
        orch, mw = create_migration_subsystem(
            strategy=MigrationStrategy.PRE_COPY,
            convergence_threshold=0.3,
            dirty_rate_decay=0.4,
        )
        orch.execute()
        output = MigrationDashboard.render(orch.last_metrics)
        assert "FIZZMIGRATE" in output
        assert "COMPLETE" in output or "VALIDATING" in output

    def test_migration_takes_longer_than_computation(self):
        """Verify that the migration infrastructure overhead exceeds
        the time it would take to simply re-evaluate the FizzBuzz range.

        This validates the fundamental design premise: live migration
        of a sub-second computation requires more time than the
        computation itself, confirming the platform's commitment to
        operational resilience over raw performance.
        """
        # Time a simple FizzBuzz computation
        compute_start = time.perf_counter_ns()
        results = []
        for i in range(1, 101):
            if i % 15 == 0:
                results.append("FizzBuzz")
            elif i % 3 == 0:
                results.append("Fizz")
            elif i % 5 == 0:
                results.append("Buzz")
            else:
                results.append(str(i))
        compute_ns = time.perf_counter_ns() - compute_start

        # Time a full migration
        orch, mw = create_migration_subsystem(
            strategy=MigrationStrategy.PRE_COPY,
            convergence_threshold=0.2,
            dirty_rate_decay=0.4,
            max_rounds=5,
        )
        migrate_start = time.perf_counter_ns()
        orch.execute()
        migrate_ns = time.perf_counter_ns() - migrate_start

        # The migration should take significantly longer than the computation
        assert migrate_ns > compute_ns, (
            f"Migration ({migrate_ns}ns) should take longer than "
            f"computation ({compute_ns}ns)"
        )
