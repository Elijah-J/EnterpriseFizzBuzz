"""
Enterprise FizzBuzz Platform - Configuration Hot-Reload Tests

Tests for the Configuration Hot-Reload with Single-Node Raft Consensus
subsystem. Validates the differ, validator, Raft consensus, dependency
graph, rollback manager, orchestrator, watcher, and dashboard.

Every test is a tribute to the absurdity of implementing a distributed
consensus protocol for re-reading a YAML file in a single process.
"""

from __future__ import annotations

import copy
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    ConfigDiffError,
    ConfigRollbackError,
    ConfigValidationRejectedError,
    ConfigWatcherError,
    DependencyGraphCycleError,
    HotReloadDashboardError,
    HotReloadError,
    RaftConsensusError,
    SubsystemReloadError,
)
from enterprise_fizzbuzz.domain.models import EventType
from enterprise_fizzbuzz.infrastructure.hot_reload import (
    ChangeType,
    ConfigChange,
    ConfigChangeset,
    ConfigDiffer,
    ConfigRollbackManager,
    ConfigValidator,
    ConfigWatcher,
    HotReloadDashboard,
    RaftElectionResult,
    RaftHeartbeat,
    RaftState,
    ReloadHistoryEntry,
    ReloadOrchestrator,
    SingleNodeRaftConsensus,
    SubsystemDependencyGraph,
    create_hot_reload_subsystem,
)


# ============================================================
# ConfigChange / ConfigChangeset Tests
# ============================================================


class TestConfigChange:
    """Tests for ConfigChange dataclass."""

    def test_added_change_str(self):
        change = ConfigChange(path="range.start", change_type=ChangeType.ADDED, new_value=42)
        result = str(change)
        assert "+" in result
        assert "range.start" in result
        assert "42" in result

    def test_removed_change_str(self):
        change = ConfigChange(path="plugins.enabled", change_type=ChangeType.REMOVED, old_value=True)
        result = str(change)
        assert "-" in result
        assert "plugins.enabled" in result

    def test_modified_change_str(self):
        change = ConfigChange(
            path="engine.strategy",
            change_type=ChangeType.MODIFIED,
            old_value="standard",
            new_value="machine_learning",
        )
        result = str(change)
        assert "~" in result
        assert "standard" in result
        assert "machine_learning" in result


class TestConfigChangeset:
    """Tests for ConfigChangeset dataclass."""

    def test_empty_changeset(self):
        cs = ConfigChangeset()
        assert cs.is_empty
        assert cs.added_count == 0
        assert cs.modified_count == 0
        assert cs.removed_count == 0

    def test_changeset_counts(self):
        changes = [
            ConfigChange(path="a", change_type=ChangeType.ADDED, new_value=1),
            ConfigChange(path="b", change_type=ChangeType.ADDED, new_value=2),
            ConfigChange(path="c", change_type=ChangeType.MODIFIED, old_value=3, new_value=4),
            ConfigChange(path="d", change_type=ChangeType.REMOVED, old_value=5),
        ]
        cs = ConfigChangeset(changes=changes)
        assert not cs.is_empty
        assert cs.added_count == 2
        assert cs.modified_count == 1
        assert cs.removed_count == 1
        assert len(cs.changes) == 4

    def test_changeset_summary(self):
        changes = [
            ConfigChange(path="x", change_type=ChangeType.MODIFIED, old_value=1, new_value=2),
        ]
        cs = ConfigChangeset(changes=changes, changeset_id="abc123")
        summary = cs.summary()
        assert "abc123" in summary
        assert "1 modified" in summary

    def test_changeset_has_unique_id(self):
        cs1 = ConfigChangeset()
        cs2 = ConfigChangeset()
        assert cs1.changeset_id != cs2.changeset_id


# ============================================================
# ConfigDiffer Tests
# ============================================================


class TestConfigDiffer:
    """Tests for the deep recursive config differ."""

    def test_identical_configs_produce_empty_changeset(self):
        config = {"range": {"start": 1, "end": 100}, "engine": {"strategy": "standard"}}
        changeset = ConfigDiffer.diff(config, copy.deepcopy(config))
        assert changeset.is_empty

    def test_simple_value_modification(self):
        old = {"range": {"start": 1, "end": 100}}
        new = {"range": {"start": 1, "end": 200}}
        changeset = ConfigDiffer.diff(old, new)
        assert changeset.modified_count == 1
        assert changeset.changes[0].path == "range.end"
        assert changeset.changes[0].old_value == 100
        assert changeset.changes[0].new_value == 200

    def test_key_addition(self):
        old = {"range": {"start": 1}}
        new = {"range": {"start": 1, "end": 100}}
        changeset = ConfigDiffer.diff(old, new)
        assert changeset.added_count == 1
        assert changeset.changes[0].path == "range.end"
        assert changeset.changes[0].new_value == 100

    def test_key_removal(self):
        old = {"range": {"start": 1, "end": 100}}
        new = {"range": {"start": 1}}
        changeset = ConfigDiffer.diff(old, new)
        assert changeset.removed_count == 1
        assert changeset.changes[0].path == "range.end"
        assert changeset.changes[0].old_value == 100

    def test_nested_modification(self):
        old = {"a": {"b": {"c": 1}}}
        new = {"a": {"b": {"c": 2}}}
        changeset = ConfigDiffer.diff(old, new)
        assert changeset.modified_count == 1
        assert changeset.changes[0].path == "a.b.c"

    def test_top_level_addition(self):
        old = {"range": {"start": 1}}
        new = {"range": {"start": 1}, "new_section": {"key": "value"}}
        changeset = ConfigDiffer.diff(old, new)
        assert changeset.added_count == 1
        assert changeset.changes[0].path == "new_section"

    def test_list_modification(self):
        old = {"rules": [{"name": "Fizz", "divisor": 3}]}
        new = {"rules": [{"name": "Fizz", "divisor": 3}, {"name": "Buzz", "divisor": 5}]}
        changeset = ConfigDiffer.diff(old, new)
        assert changeset.modified_count == 1
        assert changeset.changes[0].path == "rules"

    def test_multiple_changes(self):
        old = {"a": 1, "b": 2, "c": 3}
        new = {"a": 1, "b": 99, "d": 4}
        changeset = ConfigDiffer.diff(old, new)
        assert changeset.modified_count == 1  # b changed
        assert changeset.removed_count == 1   # c removed
        assert changeset.added_count == 1     # d added

    def test_type_change(self):
        old = {"value": "string"}
        new = {"value": 42}
        changeset = ConfigDiffer.diff(old, new)
        assert changeset.modified_count == 1
        assert changeset.changes[0].old_value == "string"
        assert changeset.changes[0].new_value == 42

    def test_bool_change(self):
        old = {"enabled": False}
        new = {"enabled": True}
        changeset = ConfigDiffer.diff(old, new)
        assert changeset.modified_count == 1

    def test_compute_hash_deterministic(self):
        config = {"a": 1, "b": {"c": 2}}
        hash1 = ConfigDiffer.compute_hash(config)
        hash2 = ConfigDiffer.compute_hash(config)
        assert hash1 == hash2

    def test_compute_hash_changes_with_content(self):
        config1 = {"a": 1}
        config2 = {"a": 2}
        assert ConfigDiffer.compute_hash(config1) != ConfigDiffer.compute_hash(config2)

    def test_changeset_hashes_populated(self):
        old = {"a": 1}
        new = {"a": 2}
        changeset = ConfigDiffer.diff(old, new)
        assert changeset.config_hash_before != ""
        assert changeset.config_hash_after != ""
        assert changeset.config_hash_before != changeset.config_hash_after


# ============================================================
# ConfigValidator Tests
# ============================================================


class TestConfigValidator:
    """Tests for the configuration validator."""

    def test_valid_config_returns_no_errors(self):
        config = {
            "range": {"start": 1, "end": 100},
            "engine": {"strategy": "standard", "timeout_ms": 5000},
            "output": {"format": "plain"},
            "logging": {"level": "INFO"},
            "rules": [{"name": "Fizz", "divisor": 3, "label": "Fizz"}],
            "cache": {"eviction_policy": "lru"},
        }
        errors = ConfigValidator.validate(config)
        assert errors == []

    def test_invalid_range_start_greater_than_end(self):
        config = {"range": {"start": 100, "end": 1}}
        errors = ConfigValidator.validate(config)
        assert any("range.start" in e for e in errors)

    def test_invalid_strategy(self):
        config = {"engine": {"strategy": "vibes_based"}}
        errors = ConfigValidator.validate(config)
        assert any("engine.strategy" in e for e in errors)

    def test_invalid_output_format(self):
        config = {"output": {"format": "yaml"}}
        errors = ConfigValidator.validate(config)
        assert any("output.format" in e for e in errors)

    def test_invalid_log_level(self):
        config = {"logging": {"level": "VERBOSE"}}
        errors = ConfigValidator.validate(config)
        assert any("logging.level" in e for e in errors)

    def test_zero_divisor_in_rules(self):
        config = {"rules": [{"name": "Bad", "divisor": 0, "label": "Bad"}]}
        errors = ConfigValidator.validate(config)
        assert any("divisor" in e and "0" in e for e in errors)

    def test_missing_rule_name(self):
        config = {"rules": [{"divisor": 3, "label": "Fizz"}]}
        errors = ConfigValidator.validate(config)
        assert any("name" in e for e in errors)

    def test_negative_timeout(self):
        config = {"engine": {"timeout_ms": -1}}
        errors = ConfigValidator.validate(config)
        assert any("timeout_ms" in e for e in errors)

    def test_invalid_cache_policy(self):
        config = {"cache": {"eviction_policy": "yeet"}}
        errors = ConfigValidator.validate(config)
        assert any("eviction_policy" in e for e in errors)

    def test_valid_cache_policies(self):
        for policy in ["lru", "lfu", "fifo", "dramatic_random"]:
            config = {"cache": {"eviction_policy": policy}}
            errors = ConfigValidator.validate(config)
            assert not any("eviction_policy" in e for e in errors)

    def test_negative_poll_interval(self):
        config = {"hot_reload": {"poll_interval_seconds": -1.0}}
        errors = ConfigValidator.validate(config)
        assert any("poll_interval" in e for e in errors)

    def test_validate_changeset_calls_validate(self):
        changeset = ConfigChangeset()
        config = {"engine": {"strategy": "invalid"}}
        errors = ConfigValidator.validate_changeset(changeset, config)
        assert len(errors) > 0


# ============================================================
# SingleNodeRaftConsensus Tests — THE CORE JOKE
# ============================================================


class TestSingleNodeRaftConsensus:
    """Tests for the single-node Raft consensus algorithm.

    Every test here validates that the single-node cluster behaves
    exactly as you'd expect: elections always win, heartbeats always
    succeed, and consensus is always reached. Because democracy is
    trivial when you're the only voter.
    """

    def test_initial_state_is_follower(self):
        raft = SingleNodeRaftConsensus()
        assert raft.state == RaftState.FOLLOWER
        assert raft.current_term == 0
        assert raft.leader_id is None

    def test_election_always_wins(self):
        raft = SingleNodeRaftConsensus()
        result = raft.start_election()
        assert result.elected is True
        assert result.votes_received == 1
        assert result.votes_needed == 1
        assert raft.state == RaftState.LEADER
        assert raft.leader_id == raft.node_id
        assert raft.current_term == 1

    def test_multiple_elections_all_win(self):
        raft = SingleNodeRaftConsensus()
        for i in range(5):
            result = raft.start_election()
            assert result.elected is True
            assert result.term == i + 1
        assert raft.total_elections_won == 5
        assert raft.current_term == 5

    def test_election_history_recorded(self):
        raft = SingleNodeRaftConsensus()
        raft.start_election()
        raft.start_election()
        assert len(raft.election_history) == 2

    def test_election_duration_is_tiny(self):
        raft = SingleNodeRaftConsensus()
        result = raft.start_election()
        # Should be well under 100ms for a self-election
        assert result.election_duration_ms < 100

    def test_heartbeat_to_zero_followers(self):
        raft = SingleNodeRaftConsensus()
        raft.start_election()
        hb = raft.send_heartbeat()
        assert hb.followers_contacted == 0
        assert hb.followers_acknowledged == 0
        assert hb.latency_ms == 0.0
        assert raft.total_heartbeats_sent == 1

    def test_heartbeat_triggers_election_if_not_leader(self):
        raft = SingleNodeRaftConsensus()
        assert raft.state == RaftState.FOLLOWER
        raft.send_heartbeat()
        assert raft.state == RaftState.LEADER

    def test_heartbeat_history_bounded(self):
        raft = SingleNodeRaftConsensus()
        raft.start_election()
        for _ in range(120):
            raft.send_heartbeat()
        # History should be bounded (trimmed to ~50)
        assert len(raft.heartbeat_history) <= 100

    def test_propose_config_change_succeeds(self):
        raft = SingleNodeRaftConsensus()
        raft.start_election()
        changeset = ConfigChangeset(changes=[
            ConfigChange(path="range.end", change_type=ChangeType.MODIFIED, old_value=100, new_value=200),
        ])
        result = raft.propose_config_change(changeset)
        assert result is True
        assert raft.commit_index == 1

    def test_propose_multiple_changes(self):
        raft = SingleNodeRaftConsensus()
        raft.start_election()
        for i in range(5):
            cs = ConfigChangeset(changes=[
                ConfigChange(path=f"key_{i}", change_type=ChangeType.MODIFIED, old_value=i, new_value=i + 1),
            ])
            raft.propose_config_change(cs)
        assert raft.commit_index == 5

    def test_propose_triggers_election_if_not_leader(self):
        raft = SingleNodeRaftConsensus()
        cs = ConfigChangeset()
        raft.propose_config_change(cs)
        assert raft.state == RaftState.LEADER

    def test_get_status_complete(self):
        raft = SingleNodeRaftConsensus(node_id="test-node")
        raft.start_election()
        raft.send_heartbeat()

        status = raft.get_status()
        assert status["node_id"] == "test-node"
        assert status["state"] == "LEADER"
        assert status["cluster_size"] == 1
        assert status["quorum_size"] == 1
        assert status["split_brain_incidents"] == 0
        assert status["consensus_failures"] == 0
        assert status["followers"] == []
        assert "100.0%" in status["election_win_rate"]
        assert "vacuously true" in status["heartbeat_success_rate"]

    def test_custom_node_id(self):
        raft = SingleNodeRaftConsensus(node_id="fizzbuzz-supreme-leader")
        assert raft.node_id == "fizzbuzz-supreme-leader"


# ============================================================
# SubsystemDependencyGraph Tests
# ============================================================


class TestSubsystemDependencyGraph:
    """Tests for the subsystem dependency graph and topological sort."""

    def test_single_subsystem_no_deps(self):
        graph = SubsystemDependencyGraph()
        graph.add_subsystem("logging")
        order = graph.get_reload_order()
        assert order == ["logging"]

    def test_linear_dependency_chain(self):
        graph = SubsystemDependencyGraph()
        graph.add_subsystem("logging")
        graph.add_subsystem("rule_engine", depends_on=["logging"])
        graph.add_subsystem("cache", depends_on=["rule_engine"])
        order = graph.get_reload_order()
        assert order.index("logging") < order.index("rule_engine")
        assert order.index("rule_engine") < order.index("cache")

    def test_diamond_dependency(self):
        graph = SubsystemDependencyGraph()
        graph.add_subsystem("base")
        graph.add_subsystem("left", depends_on=["base"])
        graph.add_subsystem("right", depends_on=["base"])
        graph.add_subsystem("top", depends_on=["left", "right"])
        order = graph.get_reload_order()
        assert order.index("base") < order.index("left")
        assert order.index("base") < order.index("right")
        assert order.index("left") < order.index("top")
        assert order.index("right") < order.index("top")

    def test_cycle_detection(self):
        graph = SubsystemDependencyGraph()
        graph.add_subsystem("a", depends_on=["b"])
        graph.add_subsystem("b", depends_on=["a"])
        with pytest.raises(DependencyGraphCycleError):
            graph.get_reload_order()

    def test_independent_subsystems(self):
        graph = SubsystemDependencyGraph()
        graph.add_subsystem("alpha")
        graph.add_subsystem("beta")
        graph.add_subsystem("gamma")
        order = graph.get_reload_order()
        assert set(order) == {"alpha", "beta", "gamma"}

    def test_affected_subsystems_maps_sections(self):
        graph = SubsystemDependencyGraph()
        graph.add_subsystem("logging")
        graph.add_subsystem("rule_engine", depends_on=["logging"])
        graph.add_subsystem("cache", depends_on=["rule_engine"])

        changeset = ConfigChangeset(changes=[
            ConfigChange(path="range.start", change_type=ChangeType.MODIFIED, old_value=1, new_value=10),
            ConfigChange(path="cache.max_size", change_type=ChangeType.MODIFIED, old_value=1024, new_value=2048),
        ])
        affected = graph.get_affected_subsystems(changeset)
        assert "rule_engine" in affected
        assert "cache" in affected
        # Should be in topological order
        assert affected.index("rule_engine") < affected.index("cache")

    def test_affected_subsystems_unknown_section_ignored(self):
        graph = SubsystemDependencyGraph()
        graph.add_subsystem("logging")
        changeset = ConfigChangeset(changes=[
            ConfigChange(path="unknown_section.key", change_type=ChangeType.ADDED, new_value="v"),
        ])
        affected = graph.get_affected_subsystems(changeset)
        assert affected == []

    def test_render_graph(self):
        graph = SubsystemDependencyGraph()
        graph.add_subsystem("logging")
        graph.add_subsystem("rule_engine", depends_on=["logging"])
        output = graph.render_graph()
        assert "logging" in output
        assert "rule_engine" in output
        assert "Reload order:" in output


# ============================================================
# ConfigRollbackManager Tests
# ============================================================


class TestConfigRollbackManager:
    """Tests for the configuration rollback manager."""

    def test_empty_history_returns_none(self):
        mgr = ConfigRollbackManager()
        assert mgr.get_previous() is None
        assert mgr.rollback() is None

    def test_snapshot_and_get_previous(self):
        mgr = ConfigRollbackManager()
        config = {"range": {"start": 1, "end": 100}}
        mgr.snapshot(config)
        previous = mgr.get_previous()
        assert previous == config
        assert previous is not config  # Should be a deep copy

    def test_rollback_pops_history(self):
        mgr = ConfigRollbackManager()
        mgr.snapshot({"a": 1})
        mgr.snapshot({"a": 2})
        assert mgr.history_size == 2

        rolled = mgr.rollback()
        assert rolled == {"a": 2}
        assert mgr.history_size == 1
        assert mgr.rollback_count == 1

    def test_max_history_bounded(self):
        mgr = ConfigRollbackManager(max_history=3)
        for i in range(10):
            mgr.snapshot({"value": i})
        assert mgr.history_size == 3

    def test_snapshot_deep_copies(self):
        mgr = ConfigRollbackManager()
        config = {"nested": {"value": 1}}
        mgr.snapshot(config)
        config["nested"]["value"] = 999
        previous = mgr.get_previous()
        assert previous["nested"]["value"] == 1  # Original snapshot preserved


# ============================================================
# ReloadOrchestrator Tests
# ============================================================


class _FakeConfigManager:
    """Fake ConfigurationManager for testing the orchestrator."""

    def __init__(self, initial_config: dict[str, Any]):
        self._raw_config = copy.deepcopy(initial_config)
        self._loaded = True

    def _get_raw_config_copy(self) -> dict[str, Any]:
        return copy.deepcopy(self._raw_config)

    def apply_raw_config(self, new_config: dict[str, Any]) -> None:
        self._raw_config.clear()
        self._raw_config.update(new_config)

    def _ensure_loaded(self):
        pass


class TestReloadOrchestrator:
    """Tests for the reload orchestrator."""

    def _make_orchestrator(
        self,
        initial_config: dict[str, Any] | None = None,
        validate: bool = True,
    ):
        config = initial_config or {
            "range": {"start": 1, "end": 100},
            "engine": {"strategy": "standard", "timeout_ms": 5000},
            "output": {"format": "plain"},
            "logging": {"level": "INFO"},
        }
        cm = _FakeConfigManager(config)
        raft = SingleNodeRaftConsensus()
        raft.start_election()
        rollback = ConfigRollbackManager()
        dep_graph = SubsystemDependencyGraph()
        dep_graph.add_subsystem("logging")
        dep_graph.add_subsystem("rule_engine", depends_on=["logging"])

        orchestrator = ReloadOrchestrator(
            config_manager=cm,
            raft=raft,
            rollback_manager=rollback,
            dependency_graph=dep_graph,
            validate_before_apply=validate,
            log_diffs=False,
        )
        return orchestrator, cm, raft, rollback

    def test_reload_with_no_changes(self):
        orch, cm, _, _ = self._make_orchestrator()
        old = cm._get_raw_config_copy()
        entry = orch.reload(old)
        assert entry.success is True
        assert entry.changeset.is_empty

    def test_reload_with_valid_changes(self):
        orch, cm, raft, _ = self._make_orchestrator()
        new_config = cm._get_raw_config_copy()
        new_config["range"]["end"] = 200
        entry = orch.reload(new_config)
        assert entry.success is True
        assert entry.changeset.modified_count == 1
        assert cm._raw_config["range"]["end"] == 200
        assert orch.successful_reloads == 1

    def test_reload_rejected_by_validation(self):
        orch, cm, _, _ = self._make_orchestrator(validate=True)
        new_config = cm._get_raw_config_copy()
        new_config["engine"]["strategy"] = "crystal_ball"
        entry = orch.reload(new_config)
        assert entry.success is False
        assert "Validation failed" in entry.error_message
        assert orch.failed_reloads == 1

    def test_reload_rollback_on_subsystem_failure(self):
        orch, cm, _, rollback = self._make_orchestrator(validate=False)

        # Register a callback that fails
        def failing_callback(config):
            raise RuntimeError("Subsystem refuses to cooperate")

        orch.register_subsystem_callback("rule_engine", failing_callback)

        new_config = cm._get_raw_config_copy()
        new_config["range"]["end"] = 999
        original_end = cm._raw_config["range"]["end"]

        entry = orch.reload(new_config)
        assert entry.success is False
        assert entry.rolled_back is True
        # Config should be rolled back
        assert cm._raw_config["range"]["end"] == original_end

    def test_subsystem_callback_invoked(self):
        orch, cm, _, _ = self._make_orchestrator(validate=False)
        callback_called = []

        def callback(config):
            callback_called.append(config["range"]["end"])

        orch.register_subsystem_callback("rule_engine", callback)

        new_config = cm._get_raw_config_copy()
        new_config["range"]["end"] = 500
        orch.reload(new_config)
        assert callback_called == [500]

    def test_reload_history_recorded(self):
        orch, cm, _, _ = self._make_orchestrator()
        new1 = cm._get_raw_config_copy()
        new1["range"]["end"] = 200
        orch.reload(new1)

        new2 = cm._get_raw_config_copy()
        new2["range"]["end"] = 300
        orch.reload(new2)

        assert len(orch.reload_history) == 2
        assert orch.total_reloads == 2

    def test_reload_uses_raft_consensus(self):
        orch, cm, raft, _ = self._make_orchestrator()
        initial_commit = raft.commit_index
        new_config = cm._get_raw_config_copy()
        new_config["range"]["end"] = 200
        orch.reload(new_config)
        # Raft should have committed the change
        assert raft.commit_index > initial_commit
        assert raft.state == RaftState.LEADER

    def test_reload_thread_safety(self):
        """Test that concurrent reloads don't corrupt state."""
        orch, cm, _, _ = self._make_orchestrator(validate=False)
        errors = []

        def reload_worker(end_val):
            try:
                new_config = cm._get_raw_config_copy()
                new_config["range"]["end"] = end_val
                orch.reload(new_config)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reload_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert orch.total_reloads == 10

    def test_get_status(self):
        orch, _, _, _ = self._make_orchestrator()
        status = orch.get_status()
        assert "total_reloads" in status
        assert "successful_reloads" in status
        assert "failed_reloads" in status
        assert "success_rate" in status

    def test_reload_with_event_bus(self):
        config = {
            "range": {"start": 1, "end": 100},
            "engine": {"strategy": "standard", "timeout_ms": 5000},
            "output": {"format": "plain"},
            "logging": {"level": "INFO"},
        }
        cm = _FakeConfigManager(config)
        raft = SingleNodeRaftConsensus()
        raft.start_election()
        rollback = ConfigRollbackManager()
        dep_graph = SubsystemDependencyGraph()
        dep_graph.add_subsystem("logging")

        event_bus = MagicMock()
        orch = ReloadOrchestrator(
            config_manager=cm,
            raft=raft,
            rollback_manager=rollback,
            dependency_graph=dep_graph,
            validate_before_apply=False,
            log_diffs=False,
            event_bus=event_bus,
        )

        new_config = cm._get_raw_config_copy()
        new_config["range"]["end"] = 200
        orch.reload(new_config)
        assert event_bus.publish.called

    def test_reload_skips_validation_when_disabled(self):
        orch, cm, _, _ = self._make_orchestrator(validate=False)
        new_config = cm._get_raw_config_copy()
        new_config["engine"]["strategy"] = "crystal_ball"  # Normally invalid
        entry = orch.reload(new_config)
        assert entry.success is True
        assert cm._raw_config["engine"]["strategy"] == "crystal_ball"


# ============================================================
# ConfigWatcher Tests
# ============================================================


class TestConfigWatcher:
    """Tests for the configuration file watcher."""

    def test_watcher_starts_and_stops(self):
        orchestrator = MagicMock()
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            f.write("range:\n  start: 1\n  end: 100\n")
            path = Path(f.name)

        try:
            watcher = ConfigWatcher(
                config_path=path,
                orchestrator=orchestrator,
                poll_interval_seconds=0.1,
            )
            watcher.start()
            assert watcher.is_running
            time.sleep(0.05)
            watcher.stop()
            assert not watcher.is_running
        finally:
            path.unlink(missing_ok=True)

    def test_watcher_is_daemonic(self):
        orchestrator = MagicMock()
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            f.write("key: value\n")
            path = Path(f.name)

        try:
            watcher = ConfigWatcher(
                config_path=path,
                orchestrator=orchestrator,
                poll_interval_seconds=10.0,
            )
            watcher.start()
            assert watcher._thread.daemon is True
            watcher.stop()
        finally:
            path.unlink(missing_ok=True)

    def test_watcher_get_status(self):
        orchestrator = MagicMock()
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            f.write("key: value\n")
            path = Path(f.name)

        try:
            watcher = ConfigWatcher(
                config_path=path,
                orchestrator=orchestrator,
                poll_interval_seconds=1.0,
            )
            status = watcher.get_status()
            assert status["running"] is False
            assert status["thread_daemon"] is True
            assert status["poll_count"] == 0
        finally:
            path.unlink(missing_ok=True)

    def test_watcher_does_not_start_twice(self):
        orchestrator = MagicMock()
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            f.write("key: value\n")
            path = Path(f.name)

        try:
            watcher = ConfigWatcher(
                config_path=path,
                orchestrator=orchestrator,
                poll_interval_seconds=10.0,
            )
            watcher.start()
            thread1 = watcher._thread
            watcher.start()  # Should not create a new thread
            assert watcher._thread is thread1
            watcher.stop()
        finally:
            path.unlink(missing_ok=True)


# ============================================================
# HotReloadDashboard Tests
# ============================================================


class TestHotReloadDashboard:
    """Tests for the ASCII hot-reload dashboard."""

    def test_render_basic_dashboard(self):
        raft = SingleNodeRaftConsensus()
        raft.start_election()

        config = {"range": {"start": 1, "end": 100}}
        cm = _FakeConfigManager(config)
        rollback = ConfigRollbackManager()
        dep_graph = SubsystemDependencyGraph()
        dep_graph.add_subsystem("logging")

        orch = ReloadOrchestrator(
            config_manager=cm,
            raft=raft,
            rollback_manager=rollback,
            dependency_graph=dep_graph,
        )

        output = HotReloadDashboard.render(
            raft=raft,
            orchestrator=orch,
            dependency_graph=dep_graph,
            rollback_manager=rollback,
        )
        assert "RAFT CONSENSUS STATUS" in output
        assert "RELOAD ORCHESTRATOR" in output
        assert "ELECTION HISTORY" in output
        assert "LEADER" in output
        assert "fizzbuzz-node-0" in output

    def test_render_with_reload_history(self):
        raft = SingleNodeRaftConsensus()
        raft.start_election()

        config = {"range": {"start": 1, "end": 100}, "engine": {"strategy": "standard"}}
        cm = _FakeConfigManager(config)
        rollback = ConfigRollbackManager()
        dep_graph = SubsystemDependencyGraph()
        dep_graph.add_subsystem("logging")

        orch = ReloadOrchestrator(
            config_manager=cm,
            raft=raft,
            rollback_manager=rollback,
            dependency_graph=dep_graph,
            validate_before_apply=False,
        )

        new_config = copy.deepcopy(config)
        new_config["range"]["end"] = 200
        orch.reload(new_config)

        output = HotReloadDashboard.render(raft=raft, orchestrator=orch)
        assert "OK" in output or "RELOAD HISTORY" in output

    def test_render_diff(self):
        old = {"range": {"start": 1, "end": 100}}
        new = {"range": {"start": 1, "end": 200}}
        changeset = ConfigDiffer.diff(old, new)
        output = HotReloadDashboard.render_diff(changeset)
        assert "CONFIGURATION DIFF" in output
        assert "range.end" in output

    def test_render_without_raft_details(self):
        raft = SingleNodeRaftConsensus()
        raft.start_election()

        config = {"range": {"start": 1, "end": 100}}
        cm = _FakeConfigManager(config)
        rollback = ConfigRollbackManager()
        dep_graph = SubsystemDependencyGraph()

        orch = ReloadOrchestrator(
            config_manager=cm,
            raft=raft,
            rollback_manager=rollback,
            dependency_graph=dep_graph,
        )

        output = HotReloadDashboard.render(
            raft=raft,
            orchestrator=orch,
            show_raft_details=False,
        )
        assert "RAFT CONSENSUS STATUS" not in output
        assert "RELOAD ORCHESTRATOR" in output

    def test_render_with_watcher(self):
        raft = SingleNodeRaftConsensus()
        raft.start_election()

        config = {"range": {"start": 1, "end": 100}}
        cm = _FakeConfigManager(config)
        rollback = ConfigRollbackManager()
        dep_graph = SubsystemDependencyGraph()

        orch = ReloadOrchestrator(
            config_manager=cm,
            raft=raft,
            rollback_manager=rollback,
            dependency_graph=dep_graph,
        )

        watcher = MagicMock()
        watcher.get_status.return_value = {
            "running": True,
            "config_path": "/path/to/config.yaml",
            "poll_interval_seconds": 2.0,
            "poll_count": 42,
            "changes_detected": 3,
            "last_hash": "abc123",
            "thread_daemon": True,
        }

        output = HotReloadDashboard.render(
            raft=raft,
            orchestrator=orch,
            watcher=watcher,
        )
        assert "CONFIG FILE WATCHER" in output
        assert "ACTIVE" in output


# ============================================================
# Exception Tests
# ============================================================


class TestHotReloadExceptions:
    """Tests for the hot-reload exception hierarchy."""

    def test_hot_reload_error_base(self):
        err = HotReloadError("test error")
        assert "EFP-HR00" in str(err)

    def test_config_diff_error(self):
        err = ConfigDiffError("range.start", "type mismatch")
        assert "EFP-HR01" in str(err)
        assert err.path == "range.start"

    def test_config_validation_rejected_error(self):
        err = ConfigValidationRejectedError("engine.strategy", "vibes", "not a valid strategy")
        assert "EFP-HR02" in str(err)
        assert err.field == "engine.strategy"

    def test_raft_consensus_error(self):
        err = RaftConsensusError(5, "disagreed with itself")
        assert "EFP-HR03" in str(err)
        assert err.term == 5

    def test_subsystem_reload_error(self):
        err = SubsystemReloadError("cache", "busy caching")
        assert "EFP-HR04" in str(err)
        assert err.subsystem == "cache"

    def test_config_rollback_error(self):
        err = ConfigRollbackError("snapshot corrupted")
        assert "EFP-HR05" in str(err)

    def test_config_watcher_error(self):
        err = ConfigWatcherError("/path/to/config.yaml", "file disappeared")
        assert "EFP-HR06" in str(err)
        assert err.config_path == "/path/to/config.yaml"

    def test_dependency_graph_cycle_error(self):
        err = DependencyGraphCycleError(["a", "b", "c", "a"])
        assert "EFP-HR07" in str(err)
        assert err.cycle == ["a", "b", "c", "a"]

    def test_hot_reload_dashboard_error(self):
        err = HotReloadDashboardError("terminal too narrow")
        assert "EFP-HR08" in str(err)


# ============================================================
# EventType Tests
# ============================================================


class TestHotReloadEventTypes:
    """Tests for the new hot-reload event types."""

    def test_all_hot_reload_event_types_exist(self):
        expected = [
            "HOT_RELOAD_FILE_CHANGED",
            "HOT_RELOAD_DIFF_COMPUTED",
            "HOT_RELOAD_VALIDATION_PASSED",
            "HOT_RELOAD_VALIDATION_FAILED",
            "HOT_RELOAD_RAFT_ELECTION_WON",
            "HOT_RELOAD_RAFT_HEARTBEAT",
            "HOT_RELOAD_RAFT_CONSENSUS_REACHED",
            "HOT_RELOAD_SUBSYSTEM_RELOADED",
            "HOT_RELOAD_ROLLBACK_INITIATED",
            "HOT_RELOAD_ROLLBACK_COMPLETED",
            "HOT_RELOAD_COMPLETED",
            "HOT_RELOAD_FAILED",
            "HOT_RELOAD_WATCHER_STARTED",
            "HOT_RELOAD_WATCHER_STOPPED",
        ]
        for name in expected:
            assert hasattr(EventType, name), f"Missing EventType: {name}"


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateHotReloadSubsystem:
    """Tests for the factory function."""

    def test_creates_all_components(self):
        config = {"range": {"start": 1, "end": 100}}
        cm = _FakeConfigManager(config)

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            f.write("range:\n  start: 1\n  end: 100\n")
            path = Path(f.name)

        try:
            raft, orch, watcher, dep_graph, rollback = create_hot_reload_subsystem(
                config_manager=cm,
                config_path=path,
            )
            assert isinstance(raft, SingleNodeRaftConsensus)
            assert isinstance(orch, ReloadOrchestrator)
            assert isinstance(watcher, ConfigWatcher)
            assert isinstance(dep_graph, SubsystemDependencyGraph)
            assert isinstance(rollback, ConfigRollbackManager)

            # Raft should already be leader
            assert raft.state == RaftState.LEADER
            assert raft.total_elections_won == 1

            # Dependency graph should have subsystems
            order = dep_graph.get_reload_order()
            assert len(order) > 0
            assert "logging" in order
            assert "rule_engine" in order
        finally:
            path.unlink(missing_ok=True)

    def test_factory_with_custom_params(self):
        config = {"range": {"start": 1, "end": 100}}
        cm = _FakeConfigManager(config)

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            f.write("key: value\n")
            path = Path(f.name)

        try:
            raft, orch, watcher, dep_graph, rollback = create_hot_reload_subsystem(
                config_manager=cm,
                config_path=path,
                poll_interval_seconds=5.0,
                heartbeat_interval_ms=200,
                election_timeout_ms=500,
                max_rollback_history=5,
                validate_before_apply=False,
                log_diffs=False,
            )
            assert watcher._poll_interval == 5.0
            assert rollback._max_history == 5
        finally:
            path.unlink(missing_ok=True)


# ============================================================
# Integration-ish Tests
# ============================================================


class TestHotReloadIntegration:
    """Higher-level tests combining multiple components."""

    def test_full_reload_lifecycle(self):
        """Test the complete diff -> validate -> raft -> apply -> verify cycle."""
        initial = {
            "range": {"start": 1, "end": 100},
            "engine": {"strategy": "standard", "timeout_ms": 5000},
            "output": {"format": "plain"},
            "logging": {"level": "INFO"},
        }
        cm = _FakeConfigManager(initial)
        raft = SingleNodeRaftConsensus()
        raft.start_election()
        rollback = ConfigRollbackManager()
        dep_graph = SubsystemDependencyGraph()
        dep_graph.add_subsystem("logging")
        dep_graph.add_subsystem("rule_engine", depends_on=["logging"])

        orch = ReloadOrchestrator(
            config_manager=cm,
            raft=raft,
            rollback_manager=rollback,
            dependency_graph=dep_graph,
            validate_before_apply=True,
            log_diffs=True,
        )

        # Reload with valid changes
        new_config = copy.deepcopy(initial)
        new_config["range"]["end"] = 200
        new_config["logging"]["level"] = "DEBUG"

        entry = orch.reload(new_config)
        assert entry.success is True
        assert cm._raw_config["range"]["end"] == 200
        assert cm._raw_config["logging"]["level"] == "DEBUG"
        assert rollback.history_size == 1
        assert raft.commit_index >= 1

    def test_reload_and_rollback_preserves_state(self):
        """Test that rollback restores exact previous state."""
        initial = {
            "range": {"start": 1, "end": 100},
            "engine": {"strategy": "standard", "timeout_ms": 5000},
        }
        cm = _FakeConfigManager(initial)
        raft = SingleNodeRaftConsensus()
        raft.start_election()
        rollback = ConfigRollbackManager()
        dep_graph = SubsystemDependencyGraph()
        dep_graph.add_subsystem("logging")
        dep_graph.add_subsystem("rule_engine", depends_on=["logging"])

        orch = ReloadOrchestrator(
            config_manager=cm,
            raft=raft,
            rollback_manager=rollback,
            dependency_graph=dep_graph,
            validate_before_apply=False,
        )

        # Register a failing subsystem
        def fail_on_500(config):
            if config.get("range", {}).get("end") == 500:
                raise RuntimeError("I don't like 500")

        orch.register_subsystem_callback("rule_engine", fail_on_500)

        # First reload succeeds
        new1 = copy.deepcopy(initial)
        new1["range"]["end"] = 200
        entry1 = orch.reload(new1)
        assert entry1.success is True

        # Second reload fails and triggers rollback
        new2 = copy.deepcopy(cm._get_raw_config_copy())
        new2["range"]["end"] = 500
        entry2 = orch.reload(new2)
        assert entry2.success is False
        assert entry2.rolled_back is True
        # Config should be back to the state before the failed reload
        assert cm._raw_config["range"]["end"] == 200
