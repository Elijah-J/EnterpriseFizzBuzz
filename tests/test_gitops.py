"""
Enterprise FizzBuzz Platform - GitOps Configuration-as-Code Simulator Test Suite

Comprehensive tests for the in-memory git repository, policy engine,
dry-run simulator, approval gate, change proposal pipeline, reconciliation
loop, blast radius estimator, and ASCII dashboard.

Because even satirical version control for modulo arithmetic configuration
deserves thorough test coverage. If you're going to over-engineer something,
you might as well over-test it too.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.gitops import (
    ApprovalGate,
    BlastRadiusEstimator,
    ChangeProposal,
    ChangeProposalPipeline,
    ConfigBranch,
    ConfigCommit,
    ConfigRepository,
    DiffEntry,
    DryRunSimulator,
    GitOpsController,
    GitOpsDashboard,
    PolicyEngine,
    ReconciliationLoop,
    _deep_merge,
    _flatten_dict,
    _unflatten_dict,
)
from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager, _SingletonMeta
from enterprise_fizzbuzz.domain.exceptions import (
    GitOpsBranchNotFoundError,
    GitOpsCommitNotFoundError,
    GitOpsDriftDetectedError,
    GitOpsError,
    GitOpsMergeConflictError,
    GitOpsPolicyViolationError,
    GitOpsProposalRejectedError,
)
from enterprise_fizzbuzz.domain.models import EventType


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def sample_config() -> dict:
    """A minimal FizzBuzz configuration for testing."""
    return {
        "application": {"name": "Enterprise FizzBuzz Platform", "version": "1.0.0"},
        "range": {"start": 1, "end": 100},
        "rules": [
            {"name": "FizzRule", "divisor": 3, "label": "Fizz", "priority": 1},
            {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
        ],
        "engine": {"strategy": "standard"},
        "output": {"format": "plain"},
    }


@pytest.fixture
def repository(sample_config) -> ConfigRepository:
    """A ConfigRepository with an initial commit."""
    repo = ConfigRepository(default_branch="main", max_history=50)
    repo.commit(tree=sample_config, message="Initial commit")
    return repo


@pytest.fixture
def controller(sample_config) -> GitOpsController:
    """A fully initialized GitOpsController."""
    ctrl = GitOpsController(
        default_branch="main",
        max_history=50,
        policy_enforcement=True,
        dry_run_range_start=1,
        dry_run_range_end=15,
        approval_mode="single_operator",
    )
    ctrl.initialize(sample_config)
    return ctrl


# ============================================================
# ConfigCommit Tests
# ============================================================


class TestConfigCommit:
    """Tests for SHA-256 hash-chained configuration commits."""

    def test_commit_has_sha(self, sample_config):
        """Commits must have a non-empty SHA-256 hash."""
        commit = ConfigCommit(
            tree=sample_config,
            parent_sha=None,
            message="test commit",
        )
        assert commit.sha
        assert len(commit.sha) == 64  # SHA-256 produces 64 hex chars

    def test_commit_sha_is_deterministic(self, sample_config):
        """Same inputs must produce the same SHA."""
        commit_a = ConfigCommit(
            tree=sample_config,
            parent_sha=None,
            message="test commit",
        )
        commit_b = ConfigCommit(
            tree=sample_config,
            parent_sha=None,
            message="test commit",
        )
        assert commit_a.sha == commit_b.sha

    def test_different_tree_different_sha(self, sample_config):
        """Different trees must produce different SHAs."""
        config_b = copy.deepcopy(sample_config)
        config_b["range"]["end"] = 200

        commit_a = ConfigCommit(tree=sample_config, parent_sha=None, message="test")
        commit_b = ConfigCommit(tree=config_b, parent_sha=None, message="test")
        assert commit_a.sha != commit_b.sha

    def test_different_parent_different_sha(self, sample_config):
        """Different parent SHAs must produce different SHAs."""
        commit_a = ConfigCommit(tree=sample_config, parent_sha=None, message="test")
        commit_b = ConfigCommit(tree=sample_config, parent_sha="abc123", message="test")
        assert commit_a.sha != commit_b.sha

    def test_different_message_different_sha(self, sample_config):
        """Different messages must produce different SHAs."""
        commit_a = ConfigCommit(tree=sample_config, parent_sha=None, message="msg a")
        commit_b = ConfigCommit(tree=sample_config, parent_sha=None, message="msg b")
        assert commit_a.sha != commit_b.sha

    def test_short_sha(self, sample_config):
        """short_sha returns first 12 characters."""
        commit = ConfigCommit(tree=sample_config, parent_sha=None, message="test")
        assert commit.short_sha == commit.sha[:12]
        assert len(commit.short_sha) == 12

    def test_commit_stores_tree(self, sample_config):
        """Commit must store the configuration tree."""
        commit = ConfigCommit(tree=sample_config, parent_sha=None, message="test")
        assert commit.tree == sample_config


# ============================================================
# ConfigBranch Tests
# ============================================================


class TestConfigBranch:
    """Tests for mutable branch pointers."""

    def test_branch_creation(self):
        """Branches must store name and head SHA."""
        branch = ConfigBranch(name="main", head_sha="abc123")
        assert branch.name == "main"
        assert branch.head_sha == "abc123"

    def test_branch_advance(self):
        """Advancing a branch must update its head SHA."""
        branch = ConfigBranch(name="main", head_sha="abc123")
        branch.advance("def456")
        assert branch.head_sha == "def456"


# ============================================================
# ConfigRepository Tests
# ============================================================


class TestConfigRepository:
    """Tests for the in-memory git repository."""

    def test_initial_state(self):
        """Repository starts with one branch and no commits."""
        repo = ConfigRepository(default_branch="main")
        assert "main" in repo.branches
        assert repo.current_branch_name == "main"
        assert repo.log() == []

    def test_commit_creates_entry(self, sample_config):
        """Committing creates a retrievable commit."""
        repo = ConfigRepository()
        commit = repo.commit(tree=sample_config, message="Initial")
        assert commit.sha in repo._commits
        assert commit.message == "Initial"

    def test_commit_chain(self, sample_config):
        """Multiple commits form a parent chain."""
        repo = ConfigRepository()
        c1 = repo.commit(tree=sample_config, message="First")
        config_b = copy.deepcopy(sample_config)
        config_b["range"]["end"] = 50
        c2 = repo.commit(tree=config_b, message="Second")

        assert c2.parent_sha == c1.sha
        assert c1.parent_sha is None

    def test_log_returns_commits_in_reverse_order(self, sample_config):
        """Log must return commits newest-first."""
        repo = ConfigRepository()
        repo.commit(tree=sample_config, message="First")
        config_b = copy.deepcopy(sample_config)
        config_b["range"]["end"] = 50
        repo.commit(tree=config_b, message="Second")

        log = repo.log()
        assert len(log) == 2
        assert log[0].message == "Second"
        assert log[1].message == "First"

    def test_branch_creation(self, repository):
        """Creating a branch from HEAD."""
        branch = repository.branch("feature")
        assert branch.name == "feature"
        assert "feature" in repository.branches

    def test_branch_already_exists(self, repository):
        """Creating a duplicate branch must raise."""
        repository.branch("feature")
        with pytest.raises(GitOpsError):
            repository.branch("feature")

    def test_checkout(self, repository):
        """Checkout must switch the current branch."""
        repository.branch("feature")
        repository.checkout("feature")
        assert repository.current_branch_name == "feature"

    def test_checkout_nonexistent_branch(self, repository):
        """Checkout of nonexistent branch must raise."""
        with pytest.raises(GitOpsBranchNotFoundError):
            repository.checkout("nonexistent")

    def test_get_head_tree(self, repository, sample_config):
        """get_head_tree must return the committed config."""
        tree = repository.get_head_tree()
        assert tree == sample_config

    def test_diff_shows_changes(self, repository, sample_config):
        """Diff must show changes between commits."""
        config_b = copy.deepcopy(sample_config)
        config_b["range"]["end"] = 50
        repository.commit(tree=config_b, message="Change range")

        diff = repository.diff()
        changed_keys = [d.key for d in diff]
        assert "range.end" in changed_keys

    def test_revert_creates_new_commit(self, repository, sample_config):
        """Revert must create a new commit undoing the change."""
        config_b = copy.deepcopy(sample_config)
        config_b["range"]["end"] = 50
        c2 = repository.commit(tree=config_b, message="Change range")

        reverted = repository.revert(c2.sha)
        assert reverted.message.startswith("Revert")
        tree = repository.get_head_tree()
        assert tree["range"]["end"] == 100  # Reverted to original

    def test_get_commit_not_found(self, repository):
        """Getting a nonexistent commit must raise."""
        with pytest.raises(GitOpsCommitNotFoundError):
            repository.get_commit("nonexistent_sha")

    def test_merge_fast_forward(self, repository, sample_config):
        """Merge with no divergence fast-forwards."""
        repository.branch("feature")
        repository.checkout("feature")
        config_b = copy.deepcopy(sample_config)
        config_b["range"]["end"] = 50
        repository.commit(tree=config_b, message="Feature change")
        repository.checkout("main")

        result = repository.merge("feature")
        assert result.tree["range"]["end"] == 50

    def test_merge_three_way(self, repository, sample_config):
        """Three-way merge with non-conflicting changes."""
        repository.branch("feature")

        # Change on main
        config_main = copy.deepcopy(sample_config)
        config_main["range"]["start"] = 10
        repository.commit(tree=config_main, message="Main change")

        # Change on feature
        repository.checkout("feature")
        config_feat = copy.deepcopy(sample_config)
        config_feat["range"]["end"] = 50
        repository.commit(tree=config_feat, message="Feature change")

        # Merge feature into main
        repository.checkout("main")
        result = repository.merge("feature")

        # Both changes should be present
        assert result.tree["range"]["start"] == 10
        assert result.tree["range"]["end"] == 50

    def test_merge_conflict(self, repository, sample_config):
        """Merging conflicting changes must raise."""
        repository.branch("feature")

        config_main = copy.deepcopy(sample_config)
        config_main["range"]["end"] = 200
        repository.commit(tree=config_main, message="Main: end=200")

        repository.checkout("feature")
        config_feat = copy.deepcopy(sample_config)
        config_feat["range"]["end"] = 300
        repository.commit(tree=config_feat, message="Feature: end=300")

        repository.checkout("main")
        with pytest.raises(GitOpsMergeConflictError) as exc_info:
            repository.merge("feature")
        assert "range.end" in exc_info.value.conflicts

    def test_merge_nonexistent_branch(self, repository):
        """Merging a nonexistent branch must raise."""
        with pytest.raises(GitOpsBranchNotFoundError):
            repository.merge("ghost")

    def test_prune_history(self, sample_config):
        """History pruning must limit commits."""
        repo = ConfigRepository(max_history=5)
        for i in range(10):
            cfg = copy.deepcopy(sample_config)
            cfg["range"]["end"] = i
            repo.commit(tree=cfg, message=f"Commit {i}")
        assert len(repo._commits) <= 5


# ============================================================
# PolicyEngine Tests
# ============================================================


class TestPolicyEngine:
    """Tests for the configuration policy engine."""

    def test_valid_config_passes(self, sample_config):
        """A valid config must pass all policy rules."""
        engine = PolicyEngine()
        violations = engine.validate(sample_config)
        assert violations == []

    def test_range_sanity_violation(self, sample_config):
        """start > end must be caught."""
        sample_config["range"]["start"] = 200
        engine = PolicyEngine()
        violations = engine.validate(sample_config)
        rule_names = [v[0] for v in violations]
        assert "range_sanity" in rule_names

    def test_empty_rules_violation(self, sample_config):
        """Empty rules list must be caught."""
        sample_config["rules"] = []
        engine = PolicyEngine()
        violations = engine.validate(sample_config)
        rule_names = [v[0] for v in violations]
        assert "rules_not_empty" in rule_names

    def test_invalid_strategy(self, sample_config):
        """Invalid strategy must be caught."""
        sample_config["engine"]["strategy"] = "quantum_computing"
        engine = PolicyEngine()
        violations = engine.validate(sample_config)
        rule_names = [v[0] for v in violations]
        assert "strategy_valid" in rule_names

    def test_invalid_output_format(self, sample_config):
        """Invalid output format must be caught."""
        sample_config["output"]["format"] = "holographic"
        engine = PolicyEngine()
        violations = engine.validate(sample_config)
        rule_names = [v[0] for v in violations]
        assert "output_format_valid" in rule_names

    def test_negative_range_start(self, sample_config):
        """Negative range start must be caught."""
        sample_config["range"]["start"] = -5
        engine = PolicyEngine()
        violations = engine.validate(sample_config)
        rule_names = [v[0] for v in violations]
        assert "range_positive" in rule_names

    def test_zero_divisor(self, sample_config):
        """Zero divisor must be caught."""
        sample_config["rules"][0]["divisor"] = 0
        engine = PolicyEngine()
        violations = engine.validate(sample_config)
        rule_names = [v[0] for v in violations]
        assert "divisor_nonzero" in rule_names

    def test_custom_rule(self, sample_config):
        """Custom policy rules can be added."""
        engine = PolicyEngine()
        engine.add_rule(
            "custom_rule",
            lambda cfg: (cfg.get("range", {}).get("end", 100) <= 50, "End must be <= 50"),
        )
        violations = engine.validate(sample_config)
        rule_names = [v[0] for v in violations]
        assert "custom_rule" in rule_names


# ============================================================
# DryRunSimulator Tests
# ============================================================


class TestDryRunSimulator:
    """Tests for the FizzBuzz dry-run impact simulator."""

    def test_no_impact_same_config(self, sample_config):
        """Same config in both runs must produce NO IMPACT."""
        sim = DryRunSimulator(range_start=1, range_end=15)
        result = sim.simulate(sample_config, copy.deepcopy(sample_config))
        assert result["impact_summary"]["changed_count"] == 0
        assert result["impact_summary"]["verdict"] == "NO IMPACT"

    def test_impact_with_changed_rules(self, sample_config):
        """Changing rules must show impact."""
        proposed = copy.deepcopy(sample_config)
        proposed["rules"] = [
            {"name": "FizzRule", "divisor": 7, "label": "Fizz", "priority": 1},
            {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
        ]
        sim = DryRunSimulator(range_start=1, range_end=15)
        result = sim.simulate(sample_config, proposed)
        assert result["impact_summary"]["changed_count"] > 0

    def test_evaluates_fizzbuzz_correctly(self):
        """The simulator must evaluate FizzBuzz correctly."""
        config = {
            "rules": [
                {"name": "FizzRule", "divisor": 3, "label": "Fizz", "priority": 1},
                {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
            ],
        }
        sim = DryRunSimulator(range_start=1, range_end=15)
        results = sim._evaluate_fizzbuzz(config)
        assert results[3] == "Fizz"
        assert results[5] == "Buzz"
        assert results[15] == "FizzBuzz"
        assert results[7] == "7"


# ============================================================
# ApprovalGate Tests
# ============================================================


class TestApprovalGate:
    """Tests for the self-approval gate."""

    def test_single_operator_always_approves(self):
        """Single-operator mode must always approve."""
        gate = ApprovalGate(mode="single_operator")
        proposal = ChangeProposal(description="test")
        approved, message = gate.request_approval(proposal)
        assert approved is True
        assert message  # Must have a satirical message

    def test_committee_mode_approves(self):
        """Committee mode must also approve (zero members, no objections)."""
        gate = ApprovalGate(mode="committee")
        proposal = ChangeProposal(description="test")
        approved, message = gate.request_approval(proposal)
        assert approved is True
        assert "committee" in message.lower() or "quorum" in message.lower()

    def test_approval_messages_rotate(self):
        """Approval messages must cycle through the list."""
        gate = ApprovalGate(mode="single_operator")
        messages = set()
        for _ in range(len(ApprovalGate.APPROVAL_MESSAGES) + 1):
            _, msg = gate.request_approval(ChangeProposal())
            messages.add(msg)
        assert len(messages) >= 2  # At least 2 different messages


# ============================================================
# ChangeProposalPipeline Tests
# ============================================================


class TestChangeProposalPipeline:
    """Tests for the five-gate change proposal pipeline."""

    def test_valid_proposal_passes_all_gates(self, controller, sample_config):
        """A valid change must pass all five gates."""
        proposal = controller.propose_change(
            changes={"range": {"end": 50}},
            description="Reduce range",
        )
        assert proposal.status == "applied"
        assert len(proposal.gates_passed) == 5

    def test_policy_violation_rejects(self, controller):
        """A policy-violating change must be rejected."""
        proposal = controller.propose_change(
            changes={"rules": []},
            description="Remove all rules (bad idea)",
        )
        assert proposal.status == "rejected"
        assert "policy" in proposal.gates_passed or "policy" not in proposal.gates_passed
        # The proposal should fail at policy gate
        assert "policy" in proposal.gate_results

    def test_proposal_records_dry_run(self, controller):
        """Proposals must record dry-run simulation results."""
        proposal = controller.propose_change(
            changes={"range": {"end": 50}},
            description="Reduce range",
        )
        assert "impact_summary" in proposal.dry_run_results

    def test_proposal_id_is_unique(self, controller):
        """Each proposal must get a unique ID."""
        p1 = controller.propose_change({"range": {"end": 50}}, "Change 1")
        p2 = controller.propose_change({"range": {"end": 60}}, "Change 2")
        assert p1.proposal_id != p2.proposal_id


# ============================================================
# ReconciliationLoop Tests
# ============================================================


class TestReconciliationLoop:
    """Tests for drift detection and reconciliation."""

    def test_no_drift_when_matching(self, repository, sample_config):
        """No drift when running config matches committed state."""
        loop = ReconciliationLoop(repository=repository)
        drift = loop.detect_drift(sample_config)
        assert drift == []

    def test_drift_when_modified(self, repository, sample_config):
        """Drift must be detected when running config differs."""
        modified = copy.deepcopy(sample_config)
        modified["range"]["end"] = 999
        loop = ReconciliationLoop(repository=repository)
        drift = loop.detect_drift(modified)
        assert len(drift) > 0
        keys = [d.key for d in drift]
        assert "range.end" in keys

    def test_reconcile_returns_committed_state(self, repository, sample_config):
        """Reconciliation must return the committed state."""
        loop = ReconciliationLoop(repository=repository)
        modified = copy.deepcopy(sample_config)
        modified["range"]["end"] = 999
        reconciled = loop.reconcile(modified)
        assert reconciled["range"]["end"] == 100

    def test_drift_callback_fires(self, repository, sample_config):
        """Drift detection must fire the event callback."""
        events = []
        loop = ReconciliationLoop(
            repository=repository,
            event_callback=lambda et, data: events.append((et, data)),
        )
        modified = copy.deepcopy(sample_config)
        modified["range"]["end"] = 999
        loop.detect_drift(modified)
        assert len(events) == 1
        assert events[0][0] == EventType.GITOPS_DRIFT_DETECTED


# ============================================================
# BlastRadiusEstimator Tests
# ============================================================


class TestBlastRadiusEstimator:
    """Tests for blast radius estimation."""

    def test_no_changes_zero_risk(self):
        """No changes must produce zero risk."""
        estimator = BlastRadiusEstimator()
        result = estimator.estimate([])
        assert result["risk_score"] == 0
        assert result["risk_level"] == "LOW"

    def test_rule_changes_affect_subsystems(self):
        """Changing rules must show affected subsystems."""
        estimator = BlastRadiusEstimator()
        result = estimator.estimate([
            DiffEntry(key="rules.0.divisor", old_value=3, new_value=7, change_type="modified"),
        ])
        assert "rule_engine" in result["affected_subsystems"]
        assert result["risk_score"] > 0

    def test_multiple_sections_increase_risk(self):
        """Changes across multiple sections must increase risk."""
        estimator = BlastRadiusEstimator()
        result_small = estimator.estimate([
            DiffEntry(key="rules.0.divisor", old_value=3, new_value=7, change_type="modified"),
        ])
        result_large = estimator.estimate([
            DiffEntry(key="rules.0.divisor", old_value=3, new_value=7, change_type="modified"),
            DiffEntry(key="engine.strategy", old_value="standard", new_value="ml", change_type="modified"),
            DiffEntry(key="cache.enabled", old_value=False, new_value=True, change_type="modified"),
        ])
        assert result_large["risk_score"] >= result_small["risk_score"]


# ============================================================
# GitOpsDashboard Tests
# ============================================================


class TestGitOpsDashboard:
    """Tests for the ASCII dashboard rendering."""

    def test_dashboard_renders_without_error(self, repository):
        """Dashboard must render without exceptions."""
        output = GitOpsDashboard.render(repository=repository, width=60)
        assert "GITOPS" in output
        assert "COMMIT LOG" in output

    def test_dashboard_shows_branches(self, repository):
        """Dashboard must show branch names."""
        repository.branch("feature")
        output = GitOpsDashboard.render(repository=repository, width=60)
        assert "main" in output
        assert "feature" in output

    def test_dashboard_shows_drift(self, repository):
        """Dashboard must show drift entries."""
        drift = [DiffEntry(key="range.end", old_value=100, new_value=999, change_type="modified")]
        output = GitOpsDashboard.render(
            repository=repository,
            drift_entries=drift,
            width=60,
        )
        assert "DRIFT DETECTED" in output

    def test_dashboard_shows_proposals(self, repository):
        """Dashboard must show change proposals."""
        proposals = [ChangeProposal(description="Test proposal", status="applied")]
        output = GitOpsDashboard.render(
            repository=repository,
            proposals=proposals,
            width=60,
        )
        assert "CHANGE PROPOSALS" in output

    def test_dashboard_respects_width(self, repository):
        """Dashboard lines must respect the width parameter."""
        output = GitOpsDashboard.render(repository=repository, width=50)
        for line in output.split("\n"):
            assert len(line) <= 50


# ============================================================
# GitOpsController Tests
# ============================================================


class TestGitOpsController:
    """Tests for the top-level GitOps orchestrator."""

    def test_initialize_creates_commit(self, sample_config):
        """Initialization must create an initial commit."""
        ctrl = GitOpsController()
        ctrl.initialize(sample_config)
        commits = ctrl.get_log()
        assert len(commits) == 1
        assert "Initial" in commits[0].message

    def test_propose_change_applies(self, controller):
        """Valid change proposals must be applied."""
        proposal = controller.propose_change(
            changes={"range": {"end": 50}},
            description="Test change",
        )
        assert proposal.status == "applied"

    def test_detect_drift(self, controller, sample_config):
        """Controller must detect drift correctly."""
        modified = copy.deepcopy(sample_config)
        modified["range"]["end"] = 42
        drift = controller.detect_drift(modified)
        assert len(drift) > 0

    def test_reconcile(self, controller, sample_config):
        """Controller must reconcile to committed state."""
        modified = copy.deepcopy(sample_config)
        modified["range"]["end"] = 42
        reconciled = controller.reconcile(modified)
        assert reconciled["range"]["end"] == 100

    def test_estimate_blast_radius(self, controller):
        """Controller must estimate blast radius."""
        result = controller.estimate_blast_radius({"rules": [{"divisor": 7}]})
        assert "risk_level" in result
        assert "affected_subsystems" in result

    def test_render_dashboard(self, controller, sample_config):
        """Controller must render the dashboard."""
        output = controller.render_dashboard(running_config=sample_config, width=60)
        assert "GITOPS" in output

    def test_multiple_proposals(self, controller):
        """Multiple proposals must be tracked."""
        controller.propose_change({"range": {"end": 50}}, "Change 1")
        controller.propose_change({"range": {"end": 60}}, "Change 2")
        assert len(controller.pipeline.proposals) == 2


# ============================================================
# Helper Function Tests
# ============================================================


class TestHelperFunctions:
    """Tests for flatten, unflatten, and deep_merge utilities."""

    def test_flatten_simple(self):
        """Flatten a simple nested dict."""
        result = _flatten_dict({"a": {"b": 1, "c": 2}})
        assert result == {"a.b": 1, "a.c": 2}

    def test_flatten_deep(self):
        """Flatten a deeply nested dict."""
        result = _flatten_dict({"a": {"b": {"c": 3}}})
        assert result == {"a.b.c": 3}

    def test_flatten_with_list(self):
        """Lists should be JSON-serialized."""
        result = _flatten_dict({"a": [1, 2, 3]})
        assert "a" in result
        assert result["a"] == "[1, 2, 3]"

    def test_unflatten(self):
        """Unflatten a dot-separated dict."""
        result = _unflatten_dict({"a.b": 1, "a.c": 2})
        assert result == {"a": {"b": 1, "c": 2}}

    def test_deep_merge(self):
        """Deep merge must override only specified keys."""
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        _deep_merge(base, {"a": {"b": 99}})
        assert base["a"]["b"] == 99
        assert base["a"]["c"] == 2
        assert base["d"] == 3

    def test_deep_merge_adds_new_keys(self):
        """Deep merge must add new keys."""
        base = {"a": 1}
        _deep_merge(base, {"b": 2})
        assert base["b"] == 2

    def test_flatten_unflatten_roundtrip(self):
        """Flatten then unflatten should preserve structure for simple values."""
        original = {"a": {"b": 1}, "c": {"d": {"e": 2}}, "f": 3}
        flattened = _flatten_dict(original)
        unflattened = _unflatten_dict(flattened)
        assert unflattened == original


# ============================================================
# Exception Tests
# ============================================================


class TestGitOpsExceptions:
    """Tests for GitOps exception hierarchy."""

    def test_base_error(self):
        """GitOpsError must have correct error code."""
        err = GitOpsError("test", error_code="EFP-G000")
        assert "EFP-G000" in str(err)

    def test_branch_not_found(self):
        """GitOpsBranchNotFoundError must include branch name."""
        err = GitOpsBranchNotFoundError("feature-branch")
        assert "feature-branch" in str(err)
        assert err.branch_name == "feature-branch"

    def test_merge_conflict(self):
        """GitOpsMergeConflictError must list conflicts."""
        err = GitOpsMergeConflictError("feat", "main", ["range.end", "rules.0.divisor"])
        assert "range.end" in str(err)
        assert err.conflicts == ["range.end", "rules.0.divisor"]

    def test_policy_violation(self):
        """GitOpsPolicyViolationError must include rule name."""
        err = GitOpsPolicyViolationError("range_sanity", "start > end")
        assert "range_sanity" in str(err)
        assert err.rule_name == "range_sanity"

    def test_proposal_rejected(self):
        """GitOpsProposalRejectedError must include gate name."""
        err = GitOpsProposalRejectedError("abc123", "policy", "Rules empty")
        assert "policy" in str(err)
        assert err.gate == "policy"

    def test_drift_detected(self):
        """GitOpsDriftDetectedError must include drift count."""
        err = GitOpsDriftDetectedError(3, ["a.b", "c.d", "e.f"])
        assert "3" in str(err)
        assert err.drift_count == 3

    def test_commit_not_found(self):
        """GitOpsCommitNotFoundError must show short SHA."""
        err = GitOpsCommitNotFoundError("abcdef123456789")
        assert "abcdef123456" in str(err)


# ============================================================
# Event Callback Tests
# ============================================================


class TestEventCallbacks:
    """Tests for GitOps event emission."""

    def test_commit_event(self, sample_config):
        """Initializing must fire GITOPS_COMMIT_CREATED event."""
        events = []
        ctrl = GitOpsController(
            event_callback=lambda et, data: events.append((et, data)),
        )
        ctrl.initialize(sample_config)
        event_types = [e[0] for e in events]
        assert EventType.GITOPS_COMMIT_CREATED in event_types

    def test_proposal_event(self, sample_config):
        """Proposing a change must fire GITOPS_PROPOSAL_SUBMITTED event."""
        events = []
        ctrl = GitOpsController(
            event_callback=lambda et, data: events.append((et, data)),
        )
        ctrl.initialize(sample_config)
        ctrl.propose_change({"range": {"end": 50}}, "Test")
        event_types = [e[0] for e in events]
        assert EventType.GITOPS_PROPOSAL_SUBMITTED in event_types
