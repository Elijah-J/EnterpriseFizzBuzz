"""
Enterprise FizzBuzz Platform - GitOps Configuration-as-Code Simulator

Implements a full in-memory git repository for configuration management,
because the only thing more responsible than storing your FizzBuzz
configuration in a YAML file is version-controlling that YAML file
with SHA-256 hash-chained commits, three-way merges, policy enforcement,
dry-run simulation, approval gates, drift detection, and blast radius
estimation.

If Argo CD can do it for Kubernetes manifests, surely our modulo
arithmetic configuration deserves the same level of GitOps ceremony.

All data structures live in RAM. All commits are lost on process exit.
All merges are between branches that one person created. All approvals
are self-approvals. This is GitOps at its finest.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

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

logger = logging.getLogger(__name__)


# ============================================================
# Data Structures
# ============================================================


@dataclass
class ConfigCommit:
    """An immutable, SHA-256 hash-chained configuration commit.

    Each commit captures a complete snapshot of the configuration tree,
    linked to its parent via SHA-256 hashing. This forms a Merkle-like
    linked list that provides cryptographic integrity guarantees for
    your FizzBuzz YAML settings — because tamper-proof configuration
    management is clearly a top priority for modulo arithmetic.

    The SHA is computed as SHA-256(json.dumps(tree) + parent_sha + message),
    ensuring that any modification to the commit history is detectable.
    Not that anyone would tamper with FizzBuzz configuration, but if
    they did, we'd know.
    """

    tree: dict[str, Any]
    parent_sha: Optional[str]
    message: str
    sha: str = ""
    author: str = "fizzbuzz-operator"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.sha:
            self.sha = self._compute_sha()

    def _compute_sha(self) -> str:
        """Compute the SHA-256 hash for this commit.

        The hash is derived from the JSON-serialized tree, the parent SHA,
        and the commit message. This is real cryptographic hashing applied
        to configuration version control for the platform's GitOps workflow.
        The hash ensures tamper-evident configuration history.
        """
        payload = (
            json.dumps(self.tree, sort_keys=True, default=str)
            + (self.parent_sha or "")
            + self.message
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def short_sha(self) -> str:
        """Return the first 12 characters of the SHA, git-style."""
        return self.sha[:12]


@dataclass
class ConfigBranch:
    """A mutable pointer to a commit, forming a branch reference.

    In real git, a branch is just a pointer to a commit. Here, it's
    also just a pointer to a commit. Some design patterns are universal
    regardless of scale.
    """

    name: str
    head_sha: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def advance(self, new_sha: str) -> None:
        """Move the branch pointer forward to a new commit."""
        self.head_sha = new_sha


@dataclass
class DiffEntry:
    """Represents a single changed key between two configuration trees."""

    key: str
    old_value: Any = None
    new_value: Any = None
    change_type: str = "modified"  # added | removed | modified


@dataclass
class ChangeProposal:
    """A proposed configuration change that must pass the approval pipeline.

    Every change proposal traverses five gates before it can be applied:
    validation, policy check, dry-run simulation, approval, and apply.
    In single-operator mode, the operator is also the reviewer, which
    is the GitOps equivalent of grading your own homework.
    """

    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    changes: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | approved | rejected | applied
    gates_passed: list[str] = field(default_factory=list)
    gate_results: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    blast_radius: list[str] = field(default_factory=list)
    dry_run_results: dict[str, Any] = field(default_factory=dict)


# ============================================================
# ConfigRepository - In-Memory Git Simulator
# ============================================================


class ConfigRepository:
    """An in-memory git repository for FizzBuzz configuration.

    Implements the essential git operations: commit, branch, checkout,
    merge, diff, log, and revert. All data lives in RAM and is lost
    when the process exits, which is exactly the kind of ephemeral
    version control that enterprise architects dream about.

    The commit history forms a genuine SHA-256 hash chain, providing
    cryptographic integrity for configuration data that will exist
    for approximately 0.8 seconds before the process terminates.
    """

    def __init__(self, default_branch: str = "main", max_history: int = 100) -> None:
        self._commits: dict[str, ConfigCommit] = {}
        self._branches: dict[str, ConfigBranch] = {}
        self._current_branch: str = default_branch
        self._max_history = max_history
        self._lock = threading.Lock()

        # Create the default branch with no commit yet
        self._branches[default_branch] = ConfigBranch(
            name=default_branch,
            head_sha="",
        )

    def commit(
        self,
        tree: dict[str, Any],
        message: str,
        author: str = "fizzbuzz-operator",
    ) -> ConfigCommit:
        """Create a new commit on the current branch.

        Snapshots the entire configuration tree into a new commit,
        chains it to the current HEAD via SHA-256 hashing, and
        advances the branch pointer. Every commit is immutable
        once created — a property we share with real git and
        blockchain-based audit ledgers, because apparently one
        immutable ledger per FizzBuzz platform wasn't enough.
        """
        with self._lock:
            branch = self._branches[self._current_branch]
            parent_sha = branch.head_sha if branch.head_sha else None

            new_commit = ConfigCommit(
                tree=copy.deepcopy(tree),
                parent_sha=parent_sha,
                message=message,
                author=author,
            )

            self._commits[new_commit.sha] = new_commit
            branch.advance(new_commit.sha)

            # Prune history if needed
            self._prune_history()

            logger.debug(
                "GitOps commit %s on branch '%s': %s",
                new_commit.short_sha,
                self._current_branch,
                message,
            )

            return new_commit

    def branch(self, name: str) -> ConfigBranch:
        """Create a new branch from the current HEAD.

        In real git, branching is cheap. Here, it's even cheaper
        because we're just copying a string pointer in RAM. The
        branch will diverge from its origin the moment someone
        commits to either side, creating the possibility of merge
        conflicts in a single-user system. Enterprise!
        """
        with self._lock:
            if name in self._branches:
                raise GitOpsError(
                    f"Branch '{name}' already exists. Delete it first, "
                    f"or choose a more creative branch name.",
                    error_code="EFP-G000",
                )

            current_head = self._branches[self._current_branch].head_sha
            new_branch = ConfigBranch(name=name, head_sha=current_head)
            self._branches[name] = new_branch

            logger.debug("GitOps branch created: '%s' from '%s'", name, self._current_branch)
            return new_branch

    def checkout(self, branch_name: str) -> ConfigBranch:
        """Switch to a different branch.

        Changes the current branch pointer. In real git, this also
        updates the working directory. Here, it just updates a string
        variable, which is all it takes to simulate the existential
        crisis of switching contexts.
        """
        with self._lock:
            if branch_name not in self._branches:
                raise GitOpsBranchNotFoundError(branch_name)
            self._current_branch = branch_name
            return self._branches[branch_name]

    def merge(self, source_branch: str) -> ConfigCommit:
        """Three-way merge of source_branch into the current branch.

        Finds the common ancestor by walking parent chains, then
        performs a three-way merge. If both branches modified the
        same key to different values, a merge conflict is raised.
        In single-operator mode, merge conflicts are rare but
        theoretically possible if you're creative enough with
        your in-memory branch management.
        """
        with self._lock:
            if source_branch not in self._branches:
                raise GitOpsBranchNotFoundError(source_branch)

            target_branch_name = self._current_branch
            source_head = self._branches[source_branch].head_sha
            target_head = self._branches[target_branch_name].head_sha

            if not source_head:
                raise GitOpsError(
                    f"Branch '{source_branch}' has no commits to merge.",
                    error_code="EFP-G000",
                )

            if source_head == target_head:
                # Already up to date — the most anticlimactic merge
                return self._commits[target_head]

            source_commit = self._commits[source_head]
            target_commit = self._commits.get(target_head)

            if target_commit is None:
                # Target has no commits, fast-forward
                self._branches[target_branch_name].advance(source_head)
                return self._commits[source_head]

            # Find common ancestor
            ancestor = self._find_common_ancestor(source_head, target_head)
            ancestor_tree = self._commits[ancestor].tree if ancestor else {}

            # Three-way merge
            merged_tree, conflicts = self._three_way_merge(
                ancestor_tree,
                source_commit.tree,
                target_commit.tree,
            )

            if conflicts:
                raise GitOpsMergeConflictError(
                    source_branch, target_branch_name, conflicts
                )

            # Create merge commit
            merge_commit = ConfigCommit(
                tree=merged_tree,
                parent_sha=target_head,
                message=f"Merge branch '{source_branch}' into '{target_branch_name}'",
                author="fizzbuzz-operator",
            )
            self._commits[merge_commit.sha] = merge_commit
            self._branches[target_branch_name].advance(merge_commit.sha)

            return merge_commit

    def diff(self, from_sha: Optional[str] = None, to_sha: Optional[str] = None) -> list[DiffEntry]:
        """Compute the diff between two commits.

        If no SHAs are provided, diffs the current HEAD against its parent.
        Returns a list of DiffEntry objects describing what changed,
        because even FizzBuzz configuration changes deserve a code review.
        """
        if to_sha is None:
            branch = self._branches.get(self._current_branch)
            if not branch or not branch.head_sha:
                return []
            to_sha = branch.head_sha

        to_commit = self._commits.get(to_sha)
        if to_commit is None:
            raise GitOpsCommitNotFoundError(to_sha or "")

        if from_sha is None:
            from_sha = to_commit.parent_sha

        from_tree = self._commits[from_sha].tree if from_sha and from_sha in self._commits else {}
        to_tree = to_commit.tree

        return self._compute_diff(from_tree, to_tree)

    def log(self, max_entries: int = 20) -> list[ConfigCommit]:
        """Return the commit history for the current branch.

        Walks the parent chain from HEAD, collecting commits into
        a list. The result is a reverse-chronological history of
        every configuration change, suitable for display in an
        ASCII dashboard that nobody will ever look at.
        """
        branch = self._branches.get(self._current_branch)
        if not branch or not branch.head_sha:
            return []

        commits: list[ConfigCommit] = []
        current_sha: Optional[str] = branch.head_sha

        while current_sha and len(commits) < max_entries:
            commit = self._commits.get(current_sha)
            if commit is None:
                break
            commits.append(commit)
            current_sha = commit.parent_sha

        return commits

    def revert(self, sha: str) -> ConfigCommit:
        """Revert a commit by applying the inverse diff.

        Creates a new commit that undoes the changes introduced by
        the specified commit. This is the GitOps equivalent of
        saying "I take it back" — a capability that real life
        sadly does not offer, but in-memory git simulators do.
        """
        commit = self._commits.get(sha)
        if commit is None:
            raise GitOpsCommitNotFoundError(sha)

        parent_tree = {}
        if commit.parent_sha and commit.parent_sha in self._commits:
            parent_tree = copy.deepcopy(self._commits[commit.parent_sha].tree)

        return self.commit(
            tree=parent_tree,
            message=f"Revert '{commit.message}' (reverting {commit.short_sha})",
        )

    def get_commit(self, sha: str) -> ConfigCommit:
        """Retrieve a commit by its SHA."""
        commit = self._commits.get(sha)
        if commit is None:
            raise GitOpsCommitNotFoundError(sha)
        return commit

    def get_head_tree(self) -> dict[str, Any]:
        """Return the configuration tree at HEAD of the current branch."""
        branch = self._branches.get(self._current_branch)
        if not branch or not branch.head_sha:
            return {}
        commit = self._commits.get(branch.head_sha)
        return copy.deepcopy(commit.tree) if commit else {}

    @property
    def current_branch_name(self) -> str:
        """Return the name of the currently checked-out branch."""
        return self._current_branch

    @property
    def branches(self) -> list[str]:
        """Return all branch names."""
        return list(self._branches.keys())

    def _find_common_ancestor(self, sha_a: str, sha_b: str) -> Optional[str]:
        """Find the common ancestor of two commits by walking parent chains.

        This is a simplified version of git's merge-base algorithm.
        We collect all ancestors of one commit, then walk the other
        commit's chain until we find a match. O(n) in the worst case,
        but for an in-memory FizzBuzz config repo, n is approximately 3.
        """
        ancestors_a: set[str] = set()
        current: Optional[str] = sha_a
        while current:
            ancestors_a.add(current)
            commit = self._commits.get(current)
            current = commit.parent_sha if commit else None

        current = sha_b
        while current:
            if current in ancestors_a:
                return current
            commit = self._commits.get(current)
            current = commit.parent_sha if commit else None

        return None

    def _three_way_merge(
        self,
        base: dict[str, Any],
        ours: dict[str, Any],
        theirs: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        """Perform a three-way merge between base, ours, and theirs.

        Flattens all three trees, compares each key, and resolves
        changes. If both sides modified the same key to different
        values, that's a conflict. If only one side changed, the
        change wins. If both changed to the same value, that's a
        happy coincidence.
        """
        flat_base = _flatten_dict(base)
        flat_ours = _flatten_dict(ours)
        flat_theirs = _flatten_dict(theirs)

        all_keys = set(flat_base) | set(flat_ours) | set(flat_theirs)
        merged_flat: dict[str, Any] = {}
        conflicts: list[str] = []

        for key in all_keys:
            base_val = flat_base.get(key)
            ours_val = flat_ours.get(key)
            theirs_val = flat_theirs.get(key)

            ours_changed = ours_val != base_val
            theirs_changed = theirs_val != base_val

            if ours_changed and theirs_changed:
                if ours_val == theirs_val:
                    # Both made the same change — convergent evolution
                    merged_flat[key] = ours_val
                else:
                    # True conflict
                    conflicts.append(key)
                    merged_flat[key] = ours_val  # Default to ours
            elif ours_changed:
                if ours_val is not None:
                    merged_flat[key] = ours_val
            elif theirs_changed:
                if theirs_val is not None:
                    merged_flat[key] = theirs_val
            else:
                if base_val is not None:
                    merged_flat[key] = base_val

        return _unflatten_dict(merged_flat), conflicts

    def _compute_diff(
        self, from_tree: dict[str, Any], to_tree: dict[str, Any]
    ) -> list[DiffEntry]:
        """Compute the diff between two configuration trees."""
        flat_from = _flatten_dict(from_tree)
        flat_to = _flatten_dict(to_tree)
        all_keys = set(flat_from) | set(flat_to)
        entries: list[DiffEntry] = []

        for key in sorted(all_keys):
            old_val = flat_from.get(key)
            new_val = flat_to.get(key)

            if old_val is None and new_val is not None:
                entries.append(DiffEntry(key=key, new_value=new_val, change_type="added"))
            elif old_val is not None and new_val is None:
                entries.append(DiffEntry(key=key, old_value=old_val, change_type="removed"))
            elif old_val != new_val:
                entries.append(DiffEntry(key=key, old_value=old_val, new_value=new_val, change_type="modified"))

        return entries

    def _prune_history(self) -> None:
        """Remove old commits beyond the max history limit."""
        if len(self._commits) <= self._max_history:
            return

        # Collect all reachable commits from all branch heads
        reachable: set[str] = set()
        for br in self._branches.values():
            current: Optional[str] = br.head_sha
            while current and len(reachable) < self._max_history:
                reachable.add(current)
                commit = self._commits.get(current)
                current = commit.parent_sha if commit else None

        # Remove unreachable commits (garbage collection for in-memory git)
        for sha in list(self._commits.keys()):
            if sha not in reachable:
                del self._commits[sha]


# ============================================================
# PolicyEngine - Configuration Change Policy Enforcement
# ============================================================


class PolicyEngine:
    """Validates configuration changes against enterprise policy rules.

    Because modifying a YAML value without first checking it against
    a battery of policy rules is the kind of reckless behavior that
    leads to FizzBuzz outages. The PolicyEngine ensures that no
    configuration change can slip through without being scrutinized
    by at least seven different validation functions.

    Each policy rule is a callable that receives the proposed config
    and returns a tuple of (passed: bool, reason: str). If any rule
    fails, the entire change is blocked. Democracy in action.
    """

    def __init__(self) -> None:
        self._rules: list[tuple[str, Callable[[dict[str, Any]], tuple[bool, str]]]] = []
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Register the built-in policy rules.

        These rules represent the minimum viable governance framework
        for FizzBuzz configuration management. Violating any of them
        would be grounds for an architecture review board hearing.
        """
        self._rules.append((
            "range_sanity",
            lambda cfg: (
                cfg.get("range", {}).get("start", 1) <= cfg.get("range", {}).get("end", 100),
                "Range start must be <= range end. Mathematics requires this."
            ),
        ))
        self._rules.append((
            "rules_not_empty",
            lambda cfg: (
                len(cfg.get("rules", [])) > 0,
                "At least one rule must be defined. A FizzBuzz platform without "
                "rules is just a platform. And not even a good one."
            ),
        ))
        self._rules.append((
            "strategy_valid",
            lambda cfg: (
                cfg.get("engine", {}).get("strategy", "standard") in {
                    "standard", "chain_of_responsibility", "parallel_async", "machine_learning"
                },
                "Strategy must be one of: standard, chain_of_responsibility, "
                "parallel_async, machine_learning."
            ),
        ))
        self._rules.append((
            "output_format_valid",
            lambda cfg: (
                cfg.get("output", {}).get("format", "plain") in {"plain", "json", "xml", "csv"},
                "Output format must be one of: plain, json, xml, csv."
            ),
        ))
        self._rules.append((
            "range_positive",
            lambda cfg: (
                cfg.get("range", {}).get("start", 1) >= 0,
                "Range start must be non-negative. Negative FizzBuzz is not "
                "covered by the enterprise license agreement."
            ),
        ))
        self._rules.append((
            "divisor_nonzero",
            lambda cfg: (
                all(r.get("divisor", 1) != 0 for r in cfg.get("rules", [{"divisor": 1}])),
                "Rule divisors must be non-zero. Division by zero is a violation "
                "of both mathematics and enterprise policy."
            ),
        ))
        self._rules.append((
            "application_name_present",
            lambda cfg: (
                bool(cfg.get("application", {}).get("name", "")),
                "Application name must not be empty. Even FizzBuzz deserves a name."
            ),
        ))

    def validate(self, config: dict[str, Any]) -> list[tuple[str, str]]:
        """Validate a configuration against all policy rules.

        Returns a list of (rule_name, reason) tuples for each failed rule.
        An empty list means the config passed all checks, which in
        enterprise software is cause for suspicion rather than celebration.
        """
        violations: list[tuple[str, str]] = []
        for rule_name, rule_fn in self._rules:
            try:
                passed, reason = rule_fn(config)
                if not passed:
                    violations.append((rule_name, reason))
            except Exception as e:
                violations.append((rule_name, f"Rule evaluation failed: {e}"))
        return violations

    def add_rule(self, name: str, rule_fn: Callable[[dict[str, Any]], tuple[bool, str]]) -> None:
        """Register a custom policy rule."""
        self._rules.append((name, rule_fn))


# ============================================================
# DryRunSimulator - FizzBuzz Impact Simulation
# ============================================================


class DryRunSimulator:
    """Simulates the impact of configuration changes on FizzBuzz output.

    Before applying a configuration change, the DryRunSimulator evaluates
    FizzBuzz for a range of numbers (default 1-30) under both the current
    and proposed configurations, then reports any differences. This is the
    enterprise equivalent of "let me check if changing this YAML value
    breaks anything" — except with 600 lines of supporting infrastructure.
    """

    def __init__(self, range_start: int = 1, range_end: int = 30) -> None:
        self._range_start = range_start
        self._range_end = range_end

    def simulate(
        self,
        current_config: dict[str, Any],
        proposed_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Run FizzBuzz under both configs and compare results.

        Returns a dict with 'current_results', 'proposed_results',
        'differences', and 'impact_summary'. The impact summary
        tells you how many FizzBuzz outputs changed, which for a
        modulo operation is either 0 (you changed something irrelevant)
        or "all of them" (you changed the rules).
        """
        current_results = self._evaluate_fizzbuzz(current_config)
        proposed_results = self._evaluate_fizzbuzz(proposed_config)

        differences: dict[int, dict[str, str]] = {}
        for n in range(self._range_start, self._range_end + 1):
            curr = current_results.get(n, str(n))
            prop = proposed_results.get(n, str(n))
            if curr != prop:
                differences[n] = {"current": curr, "proposed": prop}

        total = self._range_end - self._range_start + 1
        changed = len(differences)
        impact_pct = (changed / total * 100) if total > 0 else 0.0

        return {
            "current_results": current_results,
            "proposed_results": proposed_results,
            "differences": differences,
            "impact_summary": {
                "total_evaluated": total,
                "changed_count": changed,
                "impact_percentage": round(impact_pct, 2),
                "verdict": (
                    "NO IMPACT" if changed == 0
                    else "LOW IMPACT" if impact_pct < 20
                    else "MEDIUM IMPACT" if impact_pct < 50
                    else "HIGH IMPACT" if impact_pct < 80
                    else "CATASTROPHIC"
                ),
            },
        }

    def _evaluate_fizzbuzz(self, config: dict[str, Any]) -> dict[int, str]:
        """Evaluate FizzBuzz for the simulation range using the given config.

        Uses the standard rule engine (because even dry-run simulations
        deserve a proper evaluation strategy, and the ML engine would
        take too long to train for a dry run).
        """
        rules = config.get("rules", [
            {"name": "FizzRule", "divisor": 3, "label": "Fizz", "priority": 1},
            {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
        ])

        # Sort by priority
        sorted_rules = sorted(rules, key=lambda r: r.get("priority", 0))

        results: dict[int, str] = {}
        for n in range(self._range_start, self._range_end + 1):
            labels: list[str] = []
            for rule in sorted_rules:
                divisor = rule.get("divisor", 1)
                if divisor != 0 and n % divisor == 0:
                    labels.append(rule.get("label", ""))
            results[n] = "".join(labels) if labels else str(n)

        return results


# ============================================================
# ApprovalGate - Self-Approval in Single-Operator Mode
# ============================================================


class ApprovalGate:
    """Auto-approves configuration changes in single-operator mode.

    In a real enterprise GitOps workflow, changes require approval
    from at least one reviewer who is not the author. In single-operator
    mode, the operator IS the reviewer, which means every change is
    approved by the same person who proposed it. This is the GitOps
    equivalent of marking your own homework as correct — a practice
    that is technically allowed by the approval policy because the
    approval policy was also written by the same person.
    """

    APPROVAL_MESSAGES = [
        "Approved by the same person who proposed it. LGTM.",
        "Self-approval granted. The operator is also the reviewer. Democracy is a spectrum.",
        "Change approved. The approval committee (population: 1) has reached unanimous consensus.",
        "LGTM. Reviewed by: you. Approved by: also you. Accountability level: circular.",
        "Auto-approved in single-operator mode. The segregation of duties policy weeps silently.",
        "Approved. The change review board (board membership: the person reading this) finds no objections.",
    ]

    def __init__(self, mode: str = "single_operator") -> None:
        self._mode = mode
        self._approval_count = 0

    def request_approval(self, proposal: ChangeProposal) -> tuple[bool, str]:
        """Request approval for a change proposal.

        In single-operator mode, this always returns True with a
        an approval message. In committee mode, it also
        returns True because the committee has zero members and
        therefore no objections. Consensus by absence.
        """
        self._approval_count += 1
        msg_index = self._approval_count % len(self.APPROVAL_MESSAGES)
        message = self.APPROVAL_MESSAGES[msg_index]

        if self._mode == "committee":
            message = (
                "Committee approval: 0/0 members voted. Quorum reached by "
                "virtue of having no quorum requirements. Motion passes."
            )

        return True, message


# ============================================================
# ChangeProposalPipeline - Five-Gate Approval Pipeline
# ============================================================


class ChangeProposalPipeline:
    """Five-gate pipeline for configuration change proposals.

    Every configuration change must pass through five gates:

    1. VALIDATE  - Schema and type validation
    2. POLICY    - Policy engine rule enforcement
    3. DRY_RUN   - FizzBuzz impact simulation
    4. APPROVAL  - Self-approval (because who else would review it?)
    5. APPLY     - Actually apply the change

    This pipeline ensures that no FizzBuzz YAML modification can occur
    without first being validated, policy-checked, dry-run simulated,
    self-approved, and ceremonially applied. It's the Change Advisory
    Board meeting that ITIL always wanted, but automated and running
    in RAM.
    """

    GATES = ["validate", "policy", "dry_run", "approval", "apply"]

    def __init__(
        self,
        policy_engine: PolicyEngine,
        dry_run_simulator: DryRunSimulator,
        approval_gate: ApprovalGate,
        repository: ConfigRepository,
        event_callback: Optional[Callable] = None,
    ) -> None:
        self._policy_engine = policy_engine
        self._dry_run_simulator = dry_run_simulator
        self._approval_gate = approval_gate
        self._repository = repository
        self._event_callback = event_callback
        self._proposals: list[ChangeProposal] = []

    def propose(
        self,
        changes: dict[str, Any],
        description: str = "Configuration change proposal",
    ) -> ChangeProposal:
        """Submit a new change proposal to the pipeline.

        The proposal will be evaluated against all five gates. If any
        gate fails, the proposal is rejected and the reason is recorded
        for the post-mortem that nobody will conduct.
        """
        proposal = ChangeProposal(
            description=description,
            changes=changes,
        )
        self._proposals.append(proposal)

        if self._event_callback:
            self._event_callback(EventType.GITOPS_PROPOSAL_SUBMITTED, {
                "proposal_id": proposal.proposal_id,
                "description": description,
            })

        # Run through all gates
        current_config = self._repository.get_head_tree()

        # Build proposed config by merging changes
        proposed_config = copy.deepcopy(current_config)
        _deep_merge(proposed_config, changes)

        for gate in self.GATES:
            passed, reason = self._run_gate(gate, current_config, proposed_config, proposal)
            proposal.gate_results[gate] = reason

            if passed:
                proposal.gates_passed.append(gate)
            else:
                proposal.status = "rejected"
                logger.info(
                    "GitOps proposal %s rejected at gate '%s': %s",
                    proposal.proposal_id, gate, reason,
                )
                return proposal

        proposal.status = "applied"
        return proposal

    def _run_gate(
        self,
        gate: str,
        current_config: dict[str, Any],
        proposed_config: dict[str, Any],
        proposal: ChangeProposal,
    ) -> tuple[bool, str]:
        """Execute a single pipeline gate."""
        if gate == "validate":
            return self._gate_validate(proposed_config)
        elif gate == "policy":
            return self._gate_policy(proposed_config)
        elif gate == "dry_run":
            return self._gate_dry_run(current_config, proposed_config, proposal)
        elif gate == "approval":
            return self._gate_approval(proposal)
        elif gate == "apply":
            return self._gate_apply(proposed_config, proposal)
        return False, f"Unknown gate: {gate}"

    def _gate_validate(self, config: dict[str, Any]) -> tuple[bool, str]:
        """Gate 1: Basic schema validation."""
        if not isinstance(config, dict):
            return False, "Configuration must be a dictionary."
        if not config:
            return False, "Configuration must not be empty."
        return True, "Schema validation passed. The YAML is structurally sound."

    def _gate_policy(self, config: dict[str, Any]) -> tuple[bool, str]:
        """Gate 2: Policy engine rule enforcement."""
        violations = self._policy_engine.validate(config)
        if violations:
            reasons = "; ".join(f"{name}: {reason}" for name, reason in violations)
            return False, f"Policy violations: {reasons}"
        return True, "All policy rules passed. The configuration is compliant."

    def _gate_dry_run(
        self,
        current: dict[str, Any],
        proposed: dict[str, Any],
        proposal: ChangeProposal,
    ) -> tuple[bool, str]:
        """Gate 3: Dry-run FizzBuzz simulation."""
        results = self._dry_run_simulator.simulate(current, proposed)
        proposal.dry_run_results = results
        summary = results["impact_summary"]

        if summary["verdict"] == "CATASTROPHIC":
            return False, (
                f"Dry-run simulation: {summary['changed_count']}/{summary['total_evaluated']} "
                f"outputs changed ({summary['impact_percentage']}%). "
                f"Verdict: CATASTROPHIC. This change would break everything."
            )

        return True, (
            f"Dry-run simulation: {summary['changed_count']}/{summary['total_evaluated']} "
            f"outputs changed ({summary['impact_percentage']}%). "
            f"Verdict: {summary['verdict']}."
        )

    def _gate_approval(self, proposal: ChangeProposal) -> tuple[bool, str]:
        """Gate 4: Approval gate (self-approval in single-operator mode)."""
        return self._approval_gate.request_approval(proposal)

    def _gate_apply(self, config: dict[str, Any], proposal: ChangeProposal) -> tuple[bool, str]:
        """Gate 5: Apply the change by committing to the repository."""
        try:
            commit = self._repository.commit(
                tree=config,
                message=f"[GitOps] {proposal.description} (proposal {proposal.proposal_id})",
            )
            return True, f"Applied as commit {commit.short_sha}."
        except Exception as e:
            return False, f"Failed to apply: {e}"

    @property
    def proposals(self) -> list[ChangeProposal]:
        """Return all proposals submitted to this pipeline."""
        return list(self._proposals)


# ============================================================
# ReconciliationLoop - Drift Detection & Correction
# ============================================================


class ReconciliationLoop:
    """Detects and corrects drift between committed and running configuration.

    In real GitOps, a reconciliation loop continuously compares the
    desired state (committed config) with the actual state (running config)
    and corrects any drift. Here, "running config" is whatever the
    ConfigurationManager currently holds in RAM, and "committed config"
    is whatever the in-memory git repository says it should be.

    The fact that both live in the same process's memory and could never
    meaningfully diverge without deliberate effort is beside the point.
    Drift detection is a best practice, and best practices are non-negotiable.
    """

    def __init__(
        self,
        repository: ConfigRepository,
        event_callback: Optional[Callable] = None,
    ) -> None:
        self._repository = repository
        self._event_callback = event_callback

    def detect_drift(self, running_config: dict[str, Any]) -> list[DiffEntry]:
        """Compare the running configuration against the committed state.

        Flattens both configs and compares every key-value pair.
        Returns a list of DiffEntry objects for any keys that differ.
        In a well-managed GitOps environment, this list should be empty.
        In practice, it's usually empty because there's only one operator
        and they just committed the config 0.3 seconds ago.
        """
        committed_tree = self._repository.get_head_tree()
        flat_committed = _flatten_dict(committed_tree)
        flat_running = _flatten_dict(running_config)

        all_keys = set(flat_committed) | set(flat_running)
        drift: list[DiffEntry] = []

        for key in sorted(all_keys):
            committed_val = flat_committed.get(key)
            running_val = flat_running.get(key)

            if committed_val != running_val:
                if committed_val is None:
                    drift.append(DiffEntry(key=key, new_value=running_val, change_type="added"))
                elif running_val is None:
                    drift.append(DiffEntry(key=key, old_value=committed_val, change_type="removed"))
                else:
                    drift.append(DiffEntry(
                        key=key,
                        old_value=committed_val,
                        new_value=running_val,
                        change_type="modified",
                    ))

        if drift and self._event_callback:
            self._event_callback(EventType.GITOPS_DRIFT_DETECTED, {
                "drift_count": len(drift),
                "drifted_keys": [d.key for d in drift],
            })

        return drift

    def reconcile(self, running_config: dict[str, Any]) -> dict[str, Any]:
        """Reconcile drift by resetting the running config to the committed state.

        In real GitOps, this would restart pods, reapply manifests, or
        trigger a deployment pipeline. Here, it returns a deep copy of
        the committed config, which the caller can use to overwrite the
        running config. The ceremony is the same; the impact is negligible.
        """
        committed_tree = self._repository.get_head_tree()

        if self._event_callback:
            self._event_callback(EventType.GITOPS_RECONCILIATION_COMPLETED, {
                "reconciled_from": "committed",
            })

        return copy.deepcopy(committed_tree)


# ============================================================
# BlastRadiusEstimator - Impact Analysis
# ============================================================


class BlastRadiusEstimator:
    """Estimates the blast radius of a configuration change.

    Maps each configuration key to the subsystems it affects, then
    reports which subsystems would be impacted by a proposed change.
    This is the enterprise equivalent of asking "if I change this YAML
    value, what breaks?" — a question that could be answered in 5 seconds
    by reading the code, but instead requires a dedicated estimator class
    with subsystem mappings and impact scoring.
    """

    # Mapping of top-level config keys to affected subsystems
    SUBSYSTEM_MAP: dict[str, list[str]] = {
        "rules": ["rule_engine", "fizzbuzz_output", "feature_flags", "cache"],
        "engine": ["rule_engine", "ml_engine", "evaluation_pipeline"],
        "output": ["formatters", "console_output"],
        "range": ["evaluation_pipeline", "cache", "metrics"],
        "middleware": ["timing", "logging", "validation", "middleware_pipeline"],
        "circuit_breaker": ["circuit_breaker", "resilience"],
        "cache": ["cache", "performance"],
        "feature_flags": ["feature_flags", "rule_engine", "progressive_rollout"],
        "chaos": ["chaos_monkey", "fault_injection", "resilience"],
        "logging": ["observability", "audit_trail"],
        "tracing": ["observability", "distributed_tracing"],
        "sla": ["sla_monitoring", "alerting", "error_budget"],
        "i18n": ["internationalization", "output"],
        "rbac": ["authentication", "authorization", "security"],
        "event_sourcing": ["event_store", "cqrs", "projections"],
        "application": ["metadata", "versioning"],
    }

    def __init__(self, tracked_subsystems: Optional[list[str]] = None) -> None:
        self._tracked = tracked_subsystems or list(self.SUBSYSTEM_MAP.keys())

    def estimate(self, diff_entries: list[DiffEntry]) -> dict[str, Any]:
        """Estimate the blast radius from a list of diff entries.

        Returns a dict containing:
        - affected_subsystems: set of subsystem names
        - affected_keys: list of changed top-level config sections
        - risk_score: a completely arbitrary number between 0 and 100
        - risk_level: LOW / MEDIUM / HIGH / CRITICAL
        """
        affected_subsystems: set[str] = set()
        affected_keys: set[str] = set()

        for entry in diff_entries:
            top_key = entry.key.split(".")[0]
            affected_keys.add(top_key)
            if top_key in self.SUBSYSTEM_MAP:
                affected_subsystems.update(self.SUBSYSTEM_MAP[top_key])

        # Risk score: more affected subsystems = higher risk
        # This is scientifically meaningless but visually impressive
        total_possible = sum(len(v) for v in self.SUBSYSTEM_MAP.values())
        risk_score = min(100, int(len(affected_subsystems) / max(total_possible, 1) * 100 * 3))

        risk_level = (
            "LOW" if risk_score < 25
            else "MEDIUM" if risk_score < 50
            else "HIGH" if risk_score < 75
            else "CRITICAL"
        )

        return {
            "affected_subsystems": sorted(affected_subsystems),
            "affected_keys": sorted(affected_keys),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "total_changes": len(diff_entries),
        }


# ============================================================
# GitOpsDashboard - ASCII Dashboard
# ============================================================


class GitOpsDashboard:
    """Renders an ASCII dashboard for the GitOps subsystem.

    Displays commit history, branch status, drift detection results,
    proposal pipeline outcomes, and blast radius estimates — all in
    beautiful ASCII art that will be printed to a terminal once and
    never looked at again.
    """

    @staticmethod
    def render(
        repository: ConfigRepository,
        drift_entries: Optional[list[DiffEntry]] = None,
        proposals: Optional[list[ChangeProposal]] = None,
        blast_radius: Optional[dict[str, Any]] = None,
        width: int = 60,
    ) -> str:
        """Render the complete GitOps dashboard."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        thin = "+" + "-" * (width - 2) + "+"

        lines.append(border)
        title = "GITOPS CONFIGURATION-AS-CODE DASHBOARD"
        lines.append("|" + title.center(width - 2) + "|")
        lines.append("|" + "In-Memory Git for YAML That Won't Persist".center(width - 2) + "|")
        lines.append(border)

        # Branch info
        lines.append(thin)
        lines.append("|" + " BRANCHES".ljust(width - 2) + "|")
        lines.append(thin)
        for branch_name in repository.branches:
            marker = " *" if branch_name == repository.current_branch_name else "  "
            lines.append("|" + f"{marker} {branch_name}".ljust(width - 2) + "|")

        # Commit log
        lines.append(thin)
        lines.append("|" + " COMMIT LOG (recent)".ljust(width - 2) + "|")
        lines.append(thin)
        commits = repository.log(max_entries=10)
        if commits:
            for c in commits:
                sha_str = c.short_sha
                msg = c.message[:width - 20]
                ts = c.timestamp.strftime("%H:%M:%S")
                line = f"  {sha_str} {ts} {msg}"
                lines.append("|" + line[:width - 2].ljust(width - 2) + "|")
        else:
            lines.append("|" + "  (no commits yet)".ljust(width - 2) + "|")

        # Drift status
        lines.append(thin)
        lines.append("|" + " DRIFT STATUS".ljust(width - 2) + "|")
        lines.append(thin)
        if drift_entries:
            lines.append("|" + f"  DRIFT DETECTED: {len(drift_entries)} key(s)".ljust(width - 2) + "|")
            for d in drift_entries[:5]:
                symbol = {"added": "+", "removed": "-", "modified": "~"}.get(d.change_type, "?")
                line = f"    [{symbol}] {d.key}"
                lines.append("|" + line[:width - 2].ljust(width - 2) + "|")
            if len(drift_entries) > 5:
                lines.append("|" + f"    ... and {len(drift_entries) - 5} more".ljust(width - 2) + "|")
        else:
            lines.append("|" + "  No drift. Config matches committed state."[:width - 2].ljust(width - 2) + "|")

        # Proposals
        if proposals:
            lines.append(thin)
            lines.append("|" + " CHANGE PROPOSALS".ljust(width - 2) + "|")
            lines.append(thin)
            for p in proposals[-5:]:
                status_icon = {
                    "applied": "[OK]",
                    "rejected": "[XX]",
                    "pending": "[..]",
                }.get(p.status, "[??]")
                line = f"  {status_icon} {p.proposal_id} {p.description[:width - 25]}"
                lines.append("|" + line[:width - 2].ljust(width - 2) + "|")
                gates = " -> ".join(
                    f"{'PASS' if g in p.gates_passed else 'FAIL'}"
                    for g in ChangeProposalPipeline.GATES
                )
                lines.append("|" + f"        Gates: {gates}"[:width - 2].ljust(width - 2) + "|")

        # Blast radius
        if blast_radius:
            lines.append(thin)
            lines.append("|" + " BLAST RADIUS ESTIMATE".ljust(width - 2) + "|")
            lines.append(thin)
            lines.append("|" + f"  Risk Level: {blast_radius.get('risk_level', 'N/A')}".ljust(width - 2) + "|")
            lines.append("|" + f"  Risk Score: {blast_radius.get('risk_score', 0)}/100".ljust(width - 2) + "|")
            lines.append("|" + f"  Changes: {blast_radius.get('total_changes', 0)}".ljust(width - 2) + "|")
            affected = blast_radius.get("affected_subsystems", [])
            if affected:
                lines.append("|" + f"  Affected Subsystems ({len(affected)}):".ljust(width - 2) + "|")
                for sub in affected[:6]:
                    lines.append("|" + f"    - {sub}".ljust(width - 2) + "|")
                if len(affected) > 6:
                    lines.append("|" + f"    ... and {len(affected) - 6} more".ljust(width - 2) + "|")

        lines.append(border)
        lines.append("|" + "All commits are ephemeral."[:width - 2].center(width - 2) + "|")
        lines.append("|" + "Version-controlled for 0.8s."[:width - 2].center(width - 2) + "|")
        lines.append(border)

        return "\n".join(lines)


# ============================================================
# GitOpsController - Top-Level Orchestrator
# ============================================================


class GitOpsController:
    """Top-level orchestrator for the GitOps Configuration-as-Code Simulator.

    Wires together the repository, policy engine, dry-run simulator,
    approval gate, change proposal pipeline, reconciliation loop,
    blast radius estimator, and dashboard into a single cohesive
    system that manages FizzBuzz configuration with the same rigor
    that Fortune 500 companies apply to their production Kubernetes
    clusters.

    The fact that all of this exists to version-control a dict
    containing {3: "Fizz", 5: "Buzz"} is the punchline.
    """

    def __init__(
        self,
        default_branch: str = "main",
        max_history: int = 100,
        policy_enforcement: bool = True,
        dry_run_range_start: int = 1,
        dry_run_range_end: int = 30,
        approval_mode: str = "single_operator",
        tracked_subsystems: Optional[list[str]] = None,
        event_callback: Optional[Callable] = None,
    ) -> None:
        self._event_callback = event_callback
        self.repository = ConfigRepository(
            default_branch=default_branch,
            max_history=max_history,
        )
        self.policy_engine = PolicyEngine() if policy_enforcement else PolicyEngine()
        self.dry_run_simulator = DryRunSimulator(
            range_start=dry_run_range_start,
            range_end=dry_run_range_end,
        )
        self.approval_gate = ApprovalGate(mode=approval_mode)
        self.pipeline = ChangeProposalPipeline(
            policy_engine=self.policy_engine,
            dry_run_simulator=self.dry_run_simulator,
            approval_gate=self.approval_gate,
            repository=self.repository,
            event_callback=event_callback,
        )
        self.reconciliation_loop = ReconciliationLoop(
            repository=self.repository,
            event_callback=event_callback,
        )
        self.blast_radius_estimator = BlastRadiusEstimator(
            tracked_subsystems=tracked_subsystems,
        )

    def initialize(self, config: dict[str, Any], auto_commit: bool = True) -> Optional[ConfigCommit]:
        """Initialize the GitOps system with the current configuration.

        Creates the initial commit on the default branch, establishing
        the baseline from which all future changes will be tracked.
        This is the "git init && git add . && git commit" of the
        FizzBuzz configuration world.
        """
        if auto_commit:
            commit = self.repository.commit(
                tree=config,
                message="Initial configuration commit (auto-generated by GitOps subsystem)",
            )

            if self._event_callback:
                self._event_callback(EventType.GITOPS_COMMIT_CREATED, {
                    "sha": commit.short_sha,
                    "message": commit.message,
                })

            return commit
        return None

    def propose_change(
        self,
        changes: dict[str, Any],
        description: str = "Configuration change",
    ) -> ChangeProposal:
        """Submit a configuration change through the approval pipeline."""
        return self.pipeline.propose(changes, description)

    def detect_drift(self, running_config: dict[str, Any]) -> list[DiffEntry]:
        """Detect drift between committed and running configuration."""
        return self.reconciliation_loop.detect_drift(running_config)

    def reconcile(self, running_config: dict[str, Any]) -> dict[str, Any]:
        """Reconcile drift by returning the committed configuration."""
        return self.reconciliation_loop.reconcile(running_config)

    def estimate_blast_radius(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Estimate the blast radius of proposed changes."""
        current = self.repository.get_head_tree()
        proposed = copy.deepcopy(current)
        _deep_merge(proposed, changes)
        diff_entries = self.repository._compute_diff(current, proposed)
        return self.blast_radius_estimator.estimate(diff_entries)

    def get_diff(self) -> list[DiffEntry]:
        """Get the diff of the most recent commit."""
        return self.repository.diff()

    def get_log(self, max_entries: int = 20) -> list[ConfigCommit]:
        """Get the commit log."""
        return self.repository.log(max_entries=max_entries)

    def render_dashboard(
        self,
        running_config: Optional[dict[str, Any]] = None,
        width: int = 60,
    ) -> str:
        """Render the GitOps ASCII dashboard."""
        drift_entries = None
        if running_config is not None:
            drift_entries = self.detect_drift(running_config)

        # Estimate blast radius from latest commit
        blast_radius = None
        commits = self.repository.log(max_entries=1)
        if commits:
            diff_entries = self.repository.diff()
            if diff_entries:
                blast_radius = self.blast_radius_estimator.estimate(diff_entries)

        return GitOpsDashboard.render(
            repository=self.repository,
            drift_entries=drift_entries,
            proposals=self.pipeline.proposals,
            blast_radius=blast_radius,
            width=width,
        )


# ============================================================
# Helper Functions
# ============================================================


def _flatten_dict(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dictionary into dot-separated keys.

    {"a": {"b": 1, "c": 2}} -> {"a.b": 1, "a.c": 2}

    This is used for diff computation and drift detection,
    because comparing nested dicts is hard but comparing flat
    key-value pairs is easy. Sometimes the simplest solution
    requires the most preprocessing.
    """
    flat: dict[str, Any] = {}
    for key, value in d.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten_dict(value, full_key))
        elif isinstance(value, list):
            # Serialize lists as JSON strings for comparison
            flat[full_key] = json.dumps(value, sort_keys=True, default=str)
        else:
            flat[full_key] = value
    return flat


def _unflatten_dict(flat: dict[str, Any]) -> dict[str, Any]:
    """Unflatten a dot-separated key dictionary back into nested form.

    {"a.b": 1, "a.c": 2} -> {"a": {"b": 1, "c": 2}}
    """
    result: dict[str, Any] = {}
    for key, value in flat.items():
        parts = key.split(".")
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Deep merge override into base, modifying base in place.

    For nested dicts, recursively merges. For all other types,
    the override value wins. This is how configuration changes
    are applied — the proposed change dict is merged into the
    current config, overwriting only the keys that were specified.
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
