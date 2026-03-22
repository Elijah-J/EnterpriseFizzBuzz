"""
Enterprise FizzBuzz Platform - Configuration Hot-Reload Module

Implements configuration hot-reload with Single-Node Raft Consensus,
because re-reading a YAML file at runtime clearly requires a distributed
consensus protocol — even when your entire "cluster" is a single Python
process that could just... read the file again.

Key components:
- ConfigDiffer: Deep recursive diff of nested config trees
- ConfigValidator: Validates proposed configuration changes
- SingleNodeRaftConsensus: Full Raft implementation with 1 node. Elections
  always win unanimously in 0ms. Heartbeats to 0 followers. 100%
  consensus reliability. This is what peak democracy looks like.
- SubsystemDependencyGraph: Topological sort for reload ordering
- ConfigRollbackManager: Stores previous configs for rollback
- ReloadOrchestrator: Coordinates the full reload lifecycle
- ConfigWatcher: Polls config file for changes (daemonic thread)
- HotReloadDashboard: ASCII dashboard with Raft status, history, graph
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Optional

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
from enterprise_fizzbuzz.domain.models import Event, EventType

logger = logging.getLogger(__name__)


# ============================================================
# Data Classes
# ============================================================


class ChangeType(Enum):
    """Classification of configuration change types.

    Because even YAML key modifications deserve a formal taxonomy.
    ADDED means a key appeared from nowhere, like a feature request
    on a Friday afternoon. REMOVED means a key vanished, like
    documentation after a sprint. MODIFIED means a value changed,
    which is the only change type that actually matters.
    """

    ADDED = auto()
    REMOVED = auto()
    MODIFIED = auto()


@dataclass(frozen=True)
class ConfigChange:
    """A single atomic change to a configuration value.

    Frozen because configuration changes are historical facts — you
    cannot retroactively un-change a YAML value, no matter how much
    you wish you could.

    Attributes:
        path: Dot-separated path to the changed key (e.g., "range.start").
        change_type: Whether the key was added, removed, or modified.
        old_value: The previous value (None for additions).
        new_value: The new value (None for removals).
    """

    path: str
    change_type: ChangeType
    old_value: Any = None
    new_value: Any = None

    def __str__(self) -> str:
        if self.change_type == ChangeType.ADDED:
            return f"  + {self.path}: {self.new_value!r}"
        elif self.change_type == ChangeType.REMOVED:
            return f"  - {self.path}: {self.old_value!r}"
        else:
            return f"  ~ {self.path}: {self.old_value!r} -> {self.new_value!r}"


@dataclass
class ConfigChangeset:
    """A collection of configuration changes forming one atomic reload.

    Attributes:
        changes: List of individual config changes.
        changeset_id: Unique identifier for this changeset.
        timestamp: When the changeset was computed.
        config_hash_before: SHA-256 hash of the config before changes.
        config_hash_after: SHA-256 hash of the config after changes.
    """

    changes: list[ConfigChange] = field(default_factory=list)
    changeset_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    config_hash_before: str = ""
    config_hash_after: str = ""

    @property
    def is_empty(self) -> bool:
        return len(self.changes) == 0

    @property
    def added_count(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.ADDED)

    @property
    def removed_count(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.REMOVED)

    @property
    def modified_count(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.MODIFIED)

    def summary(self) -> str:
        return (
            f"Changeset {self.changeset_id}: "
            f"{self.added_count} added, {self.modified_count} modified, "
            f"{self.removed_count} removed ({len(self.changes)} total changes)"
        )


# ============================================================
# Raft Consensus State
# ============================================================


class RaftState(Enum):
    """Raft consensus node states.

    In a proper Raft cluster, a node transitions between FOLLOWER,
    CANDIDATE, and LEADER states through elections. In our single-node
    cluster, the node immediately transitions to LEADER because there
    is nobody to contest the election. Democracy is easy when the
    electorate is just you.
    """

    FOLLOWER = auto()
    CANDIDATE = auto()
    LEADER = auto()


@dataclass
class RaftElectionResult:
    """The result of a Raft leader election.

    In our single-node cluster, every election produces identical results:
    one vote cast, one vote received, unanimous victory, 0ms latency.
    This is what 100% voter turnout looks like.

    Attributes:
        term: The election term number.
        votes_received: Number of votes received (always 1).
        votes_needed: Quorum size (always 1).
        elected: Whether the node was elected (always True).
        election_duration_ms: Time to win the election (always ~0).
        timestamp: When the election occurred.
    """

    term: int
    votes_received: int = 1
    votes_needed: int = 1
    elected: bool = True
    election_duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RaftHeartbeat:
    """A Raft heartbeat sent to followers.

    In our cluster of one, heartbeats are sent to zero followers and
    acknowledged by zero followers. The heartbeat success rate is
    technically undefined (0/0), but we report it as 100% because
    optimism is an enterprise value.

    Attributes:
        term: The current term.
        followers_contacted: Number of followers contacted (always 0).
        followers_acknowledged: Number of followers that acknowledged (always 0).
        latency_ms: Round-trip latency (always 0.0).
        timestamp: When the heartbeat was sent.
    """

    term: int
    followers_contacted: int = 0
    followers_acknowledged: int = 0
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ReloadHistoryEntry:
    """A record of a completed (or failed) configuration reload.

    Attributes:
        changeset: The changeset that was applied (or attempted).
        success: Whether the reload completed successfully.
        raft_term: The Raft term under which this reload occurred.
        duration_ms: Total time for the reload operation.
        error_message: Error message if the reload failed.
        rolled_back: Whether a rollback was performed.
        timestamp: When the reload was attempted.
    """

    changeset: ConfigChangeset
    success: bool
    raft_term: int
    duration_ms: float = 0.0
    error_message: str = ""
    rolled_back: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# ConfigDiffer
# ============================================================


class ConfigDiffer:
    """Deep recursive differ for nested configuration trees.

    Compares two configuration dictionaries and produces a list of
    ConfigChange objects describing every addition, removal, and
    modification at every level of nesting. This is essentially
    a tree diff algorithm applied to YAML, because simple equality
    checks are insufficiently dramatic for enterprise software.
    """

    @staticmethod
    def compute_hash(config: dict[str, Any]) -> str:
        """Compute a SHA-256 hash of a configuration dictionary.

        Serializes the config to sorted JSON and hashes it, providing
        a fingerprint that can detect any change, no matter how small.
        Even changing a single boolean from false to true will produce
        a completely different hash, which is exactly the level of
        paranoia that enterprise configuration management demands.
        """
        serialized = json.dumps(config, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def diff(
        old_config: dict[str, Any],
        new_config: dict[str, Any],
        _prefix: str = "",
    ) -> ConfigChangeset:
        """Compute the diff between two configuration dictionaries.

        Recursively walks both trees, comparing values at each node.
        Produces a ConfigChangeset containing all changes found.

        Args:
            old_config: The currently loaded configuration.
            new_config: The proposed new configuration.
            _prefix: Internal parameter for tracking the current path.

        Returns:
            A ConfigChangeset describing all differences.
        """
        changes: list[ConfigChange] = []
        ConfigDiffer._diff_recursive(old_config, new_config, _prefix, changes)

        changeset = ConfigChangeset(
            changes=changes,
            config_hash_before=ConfigDiffer.compute_hash(old_config),
            config_hash_after=ConfigDiffer.compute_hash(new_config),
        )
        return changeset

    @staticmethod
    def _diff_recursive(
        old: Any,
        new: Any,
        prefix: str,
        changes: list[ConfigChange],
    ) -> None:
        """Recursively compare two values and accumulate changes."""
        if isinstance(old, dict) and isinstance(new, dict):
            all_keys = set(old.keys()) | set(new.keys())
            for key in sorted(all_keys):
                path = f"{prefix}.{key}" if prefix else key
                if key not in old:
                    changes.append(ConfigChange(
                        path=path,
                        change_type=ChangeType.ADDED,
                        new_value=new[key],
                    ))
                elif key not in new:
                    changes.append(ConfigChange(
                        path=path,
                        change_type=ChangeType.REMOVED,
                        old_value=old[key],
                    ))
                else:
                    ConfigDiffer._diff_recursive(old[key], new[key], path, changes)
        elif isinstance(old, list) and isinstance(new, list):
            if old != new:
                changes.append(ConfigChange(
                    path=prefix,
                    change_type=ChangeType.MODIFIED,
                    old_value=old,
                    new_value=new,
                ))
        elif old != new:
            changes.append(ConfigChange(
                path=prefix,
                change_type=ChangeType.MODIFIED,
                old_value=old,
                new_value=new,
            ))


# ============================================================
# ConfigValidator
# ============================================================


class ConfigValidator:
    """Validates proposed configuration changes before they are applied.

    Runs a battery of validation rules against the new configuration to
    ensure that the proposed changes won't cause the FizzBuzz evaluation
    pipeline to enter an invalid state. Because even though we're just
    reading a YAML file, we need to make sure nobody set the divisor
    to zero or the range start to infinity.
    """

    # Valid values for constrained string fields
    VALID_STRATEGIES = {"standard", "chain_of_responsibility", "parallel_async", "machine_learning"}
    VALID_FORMATS = {"plain", "json", "xml", "csv"}
    VALID_LOG_LEVELS = {"SILENT", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE"}
    VALID_EVICTION_POLICIES = {"lru", "lfu", "fifo", "dramatic_random"}

    @classmethod
    def validate(cls, config: dict[str, Any]) -> list[str]:
        """Validate a full configuration dictionary.

        Returns a list of validation error messages. An empty list means
        the configuration is valid — a rare and beautiful moment in
        enterprise software.

        Args:
            config: The configuration dictionary to validate.

        Returns:
            List of validation error strings (empty if valid).
        """
        errors: list[str] = []

        # Range validation
        range_cfg = config.get("range", {})
        start = range_cfg.get("start", 1)
        end = range_cfg.get("end", 100)
        if not isinstance(start, (int, float)):
            errors.append(f"range.start must be an integer, got {type(start).__name__}")
        elif not isinstance(end, (int, float)):
            errors.append(f"range.end must be an integer, got {type(end).__name__}")
        elif start > end:
            errors.append(f"range.start ({start}) must be <= range.end ({end})")

        # Strategy validation
        strategy = config.get("engine", {}).get("strategy", "standard")
        if strategy not in cls.VALID_STRATEGIES:
            errors.append(
                f"engine.strategy '{strategy}' is not valid. "
                f"Must be one of: {', '.join(sorted(cls.VALID_STRATEGIES))}"
            )

        # Output format validation
        fmt = config.get("output", {}).get("format", "plain")
        if fmt not in cls.VALID_FORMATS:
            errors.append(
                f"output.format '{fmt}' is not valid. "
                f"Must be one of: {', '.join(sorted(cls.VALID_FORMATS))}"
            )

        # Log level validation
        log_level = config.get("logging", {}).get("level", "INFO")
        if log_level not in cls.VALID_LOG_LEVELS:
            errors.append(
                f"logging.level '{log_level}' is not valid. "
                f"Must be one of: {', '.join(sorted(cls.VALID_LOG_LEVELS))}"
            )

        # Rules validation
        rules = config.get("rules", [])
        if isinstance(rules, list):
            for i, rule in enumerate(rules):
                if isinstance(rule, dict):
                    divisor = rule.get("divisor", 0)
                    if isinstance(divisor, (int, float)) and divisor == 0:
                        errors.append(
                            f"rules[{i}].divisor cannot be 0 — dividing by zero "
                            f"is a mathematical crime, not a FizzBuzz feature"
                        )
                    if not rule.get("name"):
                        errors.append(f"rules[{i}].name is required")
                    if not rule.get("label"):
                        errors.append(f"rules[{i}].label is required")

        # Cache eviction policy
        cache_policy = config.get("cache", {}).get("eviction_policy", "lru")
        if cache_policy not in cls.VALID_EVICTION_POLICIES:
            errors.append(
                f"cache.eviction_policy '{cache_policy}' is not valid. "
                f"Must be one of: {', '.join(sorted(cls.VALID_EVICTION_POLICIES))}"
            )

        # Timeout validations (must be positive)
        engine_timeout = config.get("engine", {}).get("timeout_ms", 5000)
        if isinstance(engine_timeout, (int, float)) and engine_timeout <= 0:
            errors.append("engine.timeout_ms must be positive")

        # Hot reload poll interval
        poll_interval = config.get("hot_reload", {}).get("poll_interval_seconds", 2.0)
        if isinstance(poll_interval, (int, float)) and poll_interval <= 0:
            errors.append("hot_reload.poll_interval_seconds must be positive")

        return errors

    @classmethod
    def validate_changeset(cls, changeset: ConfigChangeset, new_config: dict[str, Any]) -> list[str]:
        """Validate a specific changeset against the full new config.

        This is a convenience wrapper that validates the full new config
        and returns any errors. The changeset itself is used for logging
        context — because every validation deserves an audit trail.

        Args:
            changeset: The changeset being applied.
            new_config: The full new configuration after changes.

        Returns:
            List of validation error strings.
        """
        errors = cls.validate(new_config)
        if errors:
            logger.warning(
                "Validation rejected changeset %s with %d error(s): %s",
                changeset.changeset_id,
                len(errors),
                "; ".join(errors),
            )
        return errors


# ============================================================
# SingleNodeRaftConsensus — THE CORE JOKE
# ============================================================


class SingleNodeRaftConsensus:
    """A complete implementation of the Raft consensus algorithm for a
    cluster of exactly one node.

    In distributed systems, Raft is used to achieve consensus among
    multiple nodes about the state of a replicated log. Elections are
    contested, heartbeats are exchanged, and nodes can disagree,
    split-brain, or fail in exciting ways.

    In our implementation, none of that happens. There is one node.
    Elections are won unanimously with zero opposition. Heartbeats
    are sent to zero followers and acknowledged by zero followers
    (which we report as 100% success). Log replication completes
    instantly because there are no logs to replicate. Consensus
    latency is 0.000ms because agreeing with yourself takes no time.

    This is what democracy looks like when the electorate is you.

    Features:
    - Leader election: Always wins. Unanimous. 0ms.
    - Heartbeats: Sent to 0 followers. 0 acknowledged. 100% success.
    - Log replication: Nothing to replicate. Instant commitment.
    - Split-brain: Impossible. You can't split a brain of one.
    - Consensus: Always reached. The single node agrees with itself.
    """

    def __init__(
        self,
        node_id: str = "fizzbuzz-node-0",
        heartbeat_interval_ms: int = 150,
        election_timeout_ms: int = 300,
    ) -> None:
        self._node_id = node_id
        self._heartbeat_interval_ms = heartbeat_interval_ms
        self._election_timeout_ms = election_timeout_ms
        self._current_term = 0
        self._state = RaftState.FOLLOWER
        self._voted_for: Optional[str] = None
        self._leader_id: Optional[str] = None
        self._election_history: list[RaftElectionResult] = []
        self._heartbeat_history: list[RaftHeartbeat] = []
        self._log_entries: list[dict[str, Any]] = []
        self._commit_index = 0
        self._last_applied = 0
        self._cluster_size = 1  # The loneliest cluster
        self._total_heartbeats_sent = 0
        self._total_elections_won = 0

        logger.info(
            "[RAFT] Single-node cluster initialized. Node '%s' is the sole member. "
            "Cluster size: 1. Required quorum: 1. This is democracy at its finest.",
            self._node_id,
        )

    @property
    def current_term(self) -> int:
        return self._current_term

    @property
    def state(self) -> RaftState:
        return self._state

    @property
    def leader_id(self) -> Optional[str]:
        return self._leader_id

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def total_elections_won(self) -> int:
        return self._total_elections_won

    @property
    def total_heartbeats_sent(self) -> int:
        return self._total_heartbeats_sent

    @property
    def election_history(self) -> list[RaftElectionResult]:
        return list(self._election_history)

    @property
    def heartbeat_history(self) -> list[RaftHeartbeat]:
        return list(self._heartbeat_history)

    @property
    def commit_index(self) -> int:
        return self._commit_index

    def start_election(self) -> RaftElectionResult:
        """Start a leader election.

        In a multi-node Raft cluster, this would involve incrementing the
        term, transitioning to CANDIDATE state, voting for yourself, and
        sending RequestVote RPCs to all other nodes. Here, we skip all
        that because there are no other nodes. The election completes
        faster than you can say "unanimous."

        Returns:
            The election result (spoiler: we won).
        """
        election_start = time.perf_counter()

        # Step 1: Increment term
        self._current_term += 1

        # Step 2: Transition to candidate (briefly)
        self._state = RaftState.CANDIDATE
        logger.info(
            "[RAFT] Term %d: Node '%s' has entered CANDIDATE state. "
            "Requesting votes from 0 other nodes...",
            self._current_term,
            self._node_id,
        )

        # Step 3: Vote for yourself
        self._voted_for = self._node_id
        logger.info(
            "[RAFT] Term %d: Node '%s' voted for itself. "
            "Votes received: 1/1. Quorum reached IMMEDIATELY.",
            self._current_term,
            self._node_id,
        )

        # Step 4: Win the election (obviously)
        self._state = RaftState.LEADER
        self._leader_id = self._node_id
        self._total_elections_won += 1

        election_duration_ms = (time.perf_counter() - election_start) * 1000

        result = RaftElectionResult(
            term=self._current_term,
            votes_received=1,
            votes_needed=1,
            elected=True,
            election_duration_ms=election_duration_ms,
        )
        self._election_history.append(result)

        logger.info(
            "[RAFT] Term %d: ELECTION WON UNANIMOUSLY in %.3fms. "
            "Node '%s' is now LEADER of a 1-node cluster. "
            "Zero opposition encountered. Zero dissent recorded. "
            "The democratic process has never been more efficient.",
            self._current_term,
            election_duration_ms,
            self._node_id,
        )

        return result

    def send_heartbeat(self) -> RaftHeartbeat:
        """Send a heartbeat to all followers.

        In a multi-node cluster, heartbeats prevent followers from
        starting new elections. Here, we send heartbeats to zero
        followers, all of whom successfully acknowledge them
        (vacuously true). The heartbeat latency is 0.0ms because
        communicating with nobody takes no time.

        Returns:
            The heartbeat result.
        """
        if self._state != RaftState.LEADER:
            # Need to win an election first
            self.start_election()

        self._total_heartbeats_sent += 1

        heartbeat = RaftHeartbeat(
            term=self._current_term,
            followers_contacted=0,
            followers_acknowledged=0,
            latency_ms=0.0,
        )
        self._heartbeat_history.append(heartbeat)

        # Keep heartbeat history bounded
        if len(self._heartbeat_history) > 100:
            self._heartbeat_history = self._heartbeat_history[-50:]

        logger.debug(
            "[RAFT] Term %d: Heartbeat #%d sent to 0 followers. "
            "0/0 acknowledged (100%% success rate, vacuously). "
            "Latency: 0.000ms. The cluster is in perfect agreement.",
            self._current_term,
            self._total_heartbeats_sent,
        )

        return heartbeat

    def propose_config_change(self, changeset: ConfigChangeset) -> bool:
        """Propose a configuration change to the Raft cluster.

        In a multi-node cluster, this would require replicating the log
        entry to a majority of nodes before committing. In our cluster,
        the log entry is committed immediately because the leader IS the
        majority. Consensus latency: 0.000ms. Replication factor: 1.

        Args:
            changeset: The configuration changeset to propose.

        Returns:
            True if consensus was reached (always True, because the
            single node always agrees with itself).
        """
        if self._state != RaftState.LEADER:
            self.start_election()

        # Append to log
        log_entry = {
            "term": self._current_term,
            "index": len(self._log_entries) + 1,
            "changeset_id": changeset.changeset_id,
            "changes_count": len(changeset.changes),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._log_entries.append(log_entry)

        # Commit immediately — no replication needed
        self._commit_index = len(self._log_entries)
        self._last_applied = self._commit_index

        logger.info(
            "[RAFT] Term %d: Configuration change '%s' proposed, replicated "
            "to 1/1 nodes, and committed at index %d. "
            "Consensus reached in 0.000ms. Replication latency: 0.000ms. "
            "The single node has unanimously approved %d change(s). "
            "Democracy is beautiful when there's no opposition.",
            self._current_term,
            changeset.changeset_id,
            self._commit_index,
            len(changeset.changes),
        )

        # Send a heartbeat to celebrate
        self.send_heartbeat()

        return True

    def get_status(self) -> dict[str, Any]:
        """Get the current Raft consensus status.

        Returns a comprehensive status dictionary that would be useful
        in a multi-node cluster for debugging split-brain scenarios and
        election failures. In our single-node cluster, it mostly serves
        to remind you that you're running a consensus algorithm with
        yourself as the only voter.
        """
        return {
            "node_id": self._node_id,
            "state": self._state.name,
            "current_term": self._current_term,
            "leader_id": self._leader_id,
            "voted_for": self._voted_for,
            "cluster_size": self._cluster_size,
            "quorum_size": 1,
            "log_length": len(self._log_entries),
            "commit_index": self._commit_index,
            "last_applied": self._last_applied,
            "total_elections_won": self._total_elections_won,
            "total_heartbeats_sent": self._total_heartbeats_sent,
            "election_win_rate": "100.0%" if self._total_elections_won > 0 else "N/A",
            "heartbeat_success_rate": "100.0% (vacuously true)",
            "split_brain_incidents": 0,
            "consensus_failures": 0,
            "followers": [],
            "cluster_health": "HEALTHY (trivially — there's only one node)",
        }


# ============================================================
# SubsystemDependencyGraph
# ============================================================


class SubsystemDependencyGraph:
    """Manages reload ordering through topological sort of subsystem dependencies.

    When configuration changes affect multiple subsystems, they must be
    reloaded in the correct order. For example, if the cache depends on
    the rule engine, the rule engine must be reloaded first. This class
    builds a directed acyclic graph (DAG) of subsystem dependencies and
    produces a topological ordering for reload.

    In practice, our subsystem dependencies form a simple linear chain
    that could be hard-coded in three lines. But where's the fun in that?
    Topological sort is one of those algorithms that makes you feel smart
    just for using it, even when a simple list would suffice.
    """

    def __init__(self) -> None:
        self._graph: dict[str, list[str]] = {}
        self._subsystems: set[str] = set()

    def add_subsystem(self, name: str, depends_on: Optional[list[str]] = None) -> None:
        """Register a subsystem with its dependencies.

        Args:
            name: The subsystem name.
            depends_on: List of subsystem names this one depends on.
        """
        self._subsystems.add(name)
        self._graph[name] = depends_on or []
        for dep in (depends_on or []):
            self._subsystems.add(dep)
            if dep not in self._graph:
                self._graph[dep] = []

    def get_reload_order(self) -> list[str]:
        """Compute the topological reload order using Kahn's algorithm.

        Returns subsystems in an order such that each subsystem is
        reloaded after all its dependencies. This is the enterprise
        version of "reload things in the right order."

        Returns:
            List of subsystem names in topological order.

        Raises:
            DependencyGraphCycleError: If the graph contains a cycle.
        """
        # Compute in-degree for each node
        in_degree: dict[str, int] = {s: 0 for s in self._subsystems}
        for node, deps in self._graph.items():
            for dep in deps:
                if node in in_degree:
                    # dep -> node (node depends on dep)
                    pass
        # Build adjacency list: edge from dep -> dependent
        adj: dict[str, list[str]] = {s: [] for s in self._subsystems}
        for node, deps in self._graph.items():
            for dep in deps:
                adj.setdefault(dep, []).append(node)
                in_degree[node] = in_degree.get(node, 0) + 1

        # Re-compute in_degree properly
        in_degree = {s: 0 for s in self._subsystems}
        for dep, dependents in adj.items():
            for d in dependents:
                in_degree[d] += 1

        # Kahn's algorithm
        queue = sorted([s for s in self._subsystems if in_degree[s] == 0])
        result: list[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in sorted(adj.get(node, [])):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
            queue.sort()

        if len(result) != len(self._subsystems):
            # Cycle detected — find it for the error message
            remaining = self._subsystems - set(result)
            cycle = sorted(remaining)
            raise DependencyGraphCycleError(cycle + [cycle[0]] if cycle else [])

        return result

    def get_affected_subsystems(self, changeset: ConfigChangeset) -> list[str]:
        """Determine which subsystems are affected by a changeset.

        Maps configuration paths to the subsystems that care about them.
        A change to "range.start" affects the rule engine; a change to
        "cache.max_size" affects the cache. This mapping is the bridge
        between "what changed in the YAML" and "who needs to know."

        Args:
            changeset: The configuration changeset.

        Returns:
            List of affected subsystem names in topological order.
        """
        # Mapping from config section prefixes to subsystem names
        section_to_subsystem: dict[str, str] = {
            "range": "rule_engine",
            "rules": "rule_engine",
            "engine": "rule_engine",
            "output": "formatters",
            "logging": "logging",
            "cache": "cache",
            "circuit_breaker": "circuit_breaker",
            "sla": "sla_monitor",
            "chaos": "chaos_monkey",
            "feature_flags": "feature_flags",
            "middleware": "middleware",
            "tracing": "tracing",
            "i18n": "i18n",
            "rbac": "auth",
            "metrics": "metrics",
            "webhooks": "webhooks",
            "service_mesh": "service_mesh",
            "hot_reload": "hot_reload",
            "health_check": "health_check",
            "event_sourcing": "event_sourcing",
        }

        affected: set[str] = set()
        for change in changeset.changes:
            section = change.path.split(".")[0]
            subsystem = section_to_subsystem.get(section)
            if subsystem and subsystem in self._subsystems:
                affected.add(subsystem)

        # Return in topological order, filtered to affected
        full_order = self.get_reload_order()
        return [s for s in full_order if s in affected]

    def render_graph(self) -> str:
        """Render the dependency graph as ASCII art.

        Because every directed acyclic graph deserves an ASCII
        visualization, even when it has three nodes and two edges.
        """
        lines: list[str] = []
        lines.append("  Subsystem Dependency Graph:")
        lines.append("  " + "-" * 40)

        order = self.get_reload_order()
        for subsystem in order:
            deps = self._graph.get(subsystem, [])
            if deps:
                dep_str = ", ".join(deps)
                lines.append(f"    {subsystem} <- [{dep_str}]")
            else:
                lines.append(f"    {subsystem} (no dependencies)")

        lines.append("  " + "-" * 40)
        lines.append(f"  Reload order: {' -> '.join(order)}")
        return "\n".join(lines)


# ============================================================
# ConfigRollbackManager
# ============================================================


class ConfigRollbackManager:
    """Manages configuration snapshots for rollback capability.

    Stores deep copies of previous configurations so that failed
    reloads can be reverted. In enterprise systems, rollback capability
    is the difference between "minor configuration incident" and
    "career-ending configuration incident." Here, it's the difference
    between "FizzBuzz works" and "FizzBuzz doesn't work," which is
    arguably less dramatic but no less important.
    """

    def __init__(self, max_history: int = 10) -> None:
        self._history: list[dict[str, Any]] = []
        self._max_history = max_history
        self._rollback_count = 0

    @property
    def history_size(self) -> int:
        return len(self._history)

    @property
    def rollback_count(self) -> int:
        return self._rollback_count

    def snapshot(self, config: dict[str, Any]) -> None:
        """Take a snapshot of the current configuration.

        Args:
            config: The configuration to snapshot (will be deep-copied).
        """
        self._history.append(copy.deepcopy(config))
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        logger.debug(
            "[ROLLBACK] Configuration snapshot taken. "
            "History depth: %d/%d. Rollback capability: ARMED.",
            len(self._history),
            self._max_history,
        )

    def get_previous(self) -> Optional[dict[str, Any]]:
        """Get the most recent configuration snapshot.

        Returns:
            Deep copy of the previous config, or None if no history.
        """
        if not self._history:
            return None
        return copy.deepcopy(self._history[-1])

    def rollback(self) -> Optional[dict[str, Any]]:
        """Pop and return the most recent configuration snapshot.

        Returns:
            The previous config, or None if no history.
        """
        if not self._history:
            logger.warning(
                "[ROLLBACK] No configuration history available. "
                "Cannot roll back. The system has no past to return to."
            )
            return None

        previous = self._history.pop()
        self._rollback_count += 1
        logger.info(
            "[ROLLBACK] Configuration rolled back to previous state. "
            "Rollback #%d. History depth: %d.",
            self._rollback_count,
            len(self._history),
        )
        return previous


# ============================================================
# ReloadOrchestrator
# ============================================================


class ReloadOrchestrator:
    """Coordinates the full configuration hot-reload lifecycle.

    This is the maestro of the hot-reload orchestra, conducting each
    step of the process:

    1. Diff: Compare old and new configs
    2. Validate: Ensure new config is valid
    3. Raft Consensus: Get unanimous agreement from 1 node
    4. Snapshot: Save current config for rollback
    5. Apply: Update the ConfigurationManager
    6. Notify: Inform subsystems of changes
    7. Verify: Confirm everything still works
    8. Rollback: If anything fails, restore previous config

    All of this is protected by a threading lock, because even though
    the config watcher runs in a background thread, we can't have two
    concurrent reloads creating a race condition between two YAML reads.
    That would be chaos — and we already have a Chaos Engineering module
    for that.
    """

    def __init__(
        self,
        config_manager: Any,  # ConfigurationManager (avoid circular import)
        raft: SingleNodeRaftConsensus,
        rollback_manager: ConfigRollbackManager,
        dependency_graph: SubsystemDependencyGraph,
        validate_before_apply: bool = True,
        log_diffs: bool = True,
        event_bus: Any = None,
    ) -> None:
        self._config_manager = config_manager
        self._raft = raft
        self._rollback_manager = rollback_manager
        self._dependency_graph = dependency_graph
        self._validate_before_apply = validate_before_apply
        self._log_diffs = log_diffs
        self._event_bus = event_bus
        self._lock = threading.Lock()
        self._reload_history: list[ReloadHistoryEntry] = []
        self._total_reloads = 0
        self._successful_reloads = 0
        self._failed_reloads = 0
        self._subsystem_callbacks: dict[str, Callable[[dict[str, Any]], None]] = {}

    @property
    def reload_history(self) -> list[ReloadHistoryEntry]:
        return list(self._reload_history)

    @property
    def total_reloads(self) -> int:
        return self._total_reloads

    @property
    def successful_reloads(self) -> int:
        return self._successful_reloads

    @property
    def failed_reloads(self) -> int:
        return self._failed_reloads

    def register_subsystem_callback(
        self,
        subsystem: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> None:
        """Register a callback to be invoked when a subsystem needs reloading.

        Args:
            subsystem: The subsystem name.
            callback: A callable that accepts the new raw config dict.
        """
        self._subsystem_callbacks[subsystem] = callback
        logger.debug("[ORCHESTRATOR] Registered reload callback for subsystem '%s'.", subsystem)

    def reload(self, new_config: dict[str, Any]) -> ReloadHistoryEntry:
        """Execute a full configuration reload lifecycle.

        This is the main entry point. It acquires the lock, diffs the
        configs, validates the changes, proposes them to Raft, snapshots
        the old config, applies the new one, notifies subsystems, and
        records the result. If anything fails, it rolls back.

        Args:
            new_config: The new configuration dictionary to apply.

        Returns:
            A ReloadHistoryEntry describing the outcome.
        """
        with self._lock:
            return self._reload_inner(new_config)

    def _reload_inner(self, new_config: dict[str, Any]) -> ReloadHistoryEntry:
        """Internal reload logic (must be called under lock)."""
        reload_start = time.perf_counter()
        self._total_reloads += 1

        # Step 1: Diff
        old_config = self._config_manager._get_raw_config_copy()
        changeset = ConfigDiffer.diff(old_config, new_config)

        if changeset.is_empty:
            logger.info(
                "[ORCHESTRATOR] No configuration changes detected. "
                "The YAML file was re-read but nothing changed. "
                "This was a thrilling waste of I/O bandwidth."
            )
            entry = ReloadHistoryEntry(
                changeset=changeset,
                success=True,
                raft_term=self._raft.current_term,
                duration_ms=0.0,
            )
            self._successful_reloads += 1
            return entry

        self._emit_event(EventType.HOT_RELOAD_DIFF_COMPUTED, {
            "changeset_id": changeset.changeset_id,
            "changes_count": len(changeset.changes),
            "added": changeset.added_count,
            "modified": changeset.modified_count,
            "removed": changeset.removed_count,
        })

        if self._log_diffs:
            logger.info(
                "[ORCHESTRATOR] Configuration diff computed: %s",
                changeset.summary(),
            )
            for change in changeset.changes:
                logger.info("[ORCHESTRATOR] %s", change)

        # Step 2: Validate
        if self._validate_before_apply:
            errors = ConfigValidator.validate(new_config)
            if errors:
                self._emit_event(EventType.HOT_RELOAD_VALIDATION_FAILED, {
                    "changeset_id": changeset.changeset_id,
                    "errors": errors,
                })
                duration_ms = (time.perf_counter() - reload_start) * 1000
                entry = ReloadHistoryEntry(
                    changeset=changeset,
                    success=False,
                    raft_term=self._raft.current_term,
                    duration_ms=duration_ms,
                    error_message=f"Validation failed: {'; '.join(errors)}",
                )
                self._reload_history.append(entry)
                self._failed_reloads += 1

                logger.warning(
                    "[ORCHESTRATOR] Reload REJECTED by validation: %s",
                    "; ".join(errors),
                )
                return entry

            self._emit_event(EventType.HOT_RELOAD_VALIDATION_PASSED, {
                "changeset_id": changeset.changeset_id,
            })

        # Step 3: Raft Consensus
        consensus = self._raft.propose_config_change(changeset)
        if not consensus:
            # This literally cannot happen, but enterprise software
            # must account for the impossible
            duration_ms = (time.perf_counter() - reload_start) * 1000
            entry = ReloadHistoryEntry(
                changeset=changeset,
                success=False,
                raft_term=self._raft.current_term,
                duration_ms=duration_ms,
                error_message="Raft consensus failed (this should be impossible)",
            )
            self._reload_history.append(entry)
            self._failed_reloads += 1
            return entry

        self._emit_event(EventType.HOT_RELOAD_RAFT_CONSENSUS_REACHED, {
            "changeset_id": changeset.changeset_id,
            "term": self._raft.current_term,
        })

        # Step 4: Snapshot old config
        self._rollback_manager.snapshot(old_config)

        # Step 5: Apply new config
        try:
            self._config_manager.apply_raw_config(new_config)
        except Exception as e:
            logger.error("[ORCHESTRATOR] Failed to apply config: %s", e)
            self._perform_rollback(old_config, changeset)
            duration_ms = (time.perf_counter() - reload_start) * 1000
            entry = ReloadHistoryEntry(
                changeset=changeset,
                success=False,
                raft_term=self._raft.current_term,
                duration_ms=duration_ms,
                error_message=f"Apply failed: {e}",
                rolled_back=True,
            )
            self._reload_history.append(entry)
            self._failed_reloads += 1
            return entry

        # Step 6: Notify subsystems
        affected = self._dependency_graph.get_affected_subsystems(changeset)
        for subsystem in affected:
            callback = self._subsystem_callbacks.get(subsystem)
            if callback:
                try:
                    callback(new_config)
                    self._emit_event(EventType.HOT_RELOAD_SUBSYSTEM_RELOADED, {
                        "subsystem": subsystem,
                        "changeset_id": changeset.changeset_id,
                    })
                    logger.info(
                        "[ORCHESTRATOR] Subsystem '%s' successfully reloaded.",
                        subsystem,
                    )
                except Exception as e:
                    logger.error(
                        "[ORCHESTRATOR] Subsystem '%s' rejected reload: %s. "
                        "Initiating rollback.",
                        subsystem,
                        e,
                    )
                    self._perform_rollback(old_config, changeset)
                    duration_ms = (time.perf_counter() - reload_start) * 1000
                    entry = ReloadHistoryEntry(
                        changeset=changeset,
                        success=False,
                        raft_term=self._raft.current_term,
                        duration_ms=duration_ms,
                        error_message=f"Subsystem '{subsystem}' rejected: {e}",
                        rolled_back=True,
                    )
                    self._reload_history.append(entry)
                    self._failed_reloads += 1
                    return entry

        # Step 7: Success
        duration_ms = (time.perf_counter() - reload_start) * 1000
        entry = ReloadHistoryEntry(
            changeset=changeset,
            success=True,
            raft_term=self._raft.current_term,
            duration_ms=duration_ms,
        )
        self._reload_history.append(entry)
        self._successful_reloads += 1

        # Keep history bounded
        if len(self._reload_history) > 50:
            self._reload_history = self._reload_history[-25:]

        self._emit_event(EventType.HOT_RELOAD_COMPLETED, {
            "changeset_id": changeset.changeset_id,
            "duration_ms": duration_ms,
            "changes_count": len(changeset.changes),
            "affected_subsystems": affected,
        })

        logger.info(
            "[ORCHESTRATOR] Configuration reload COMPLETE in %.2fms. "
            "%d change(s) applied. %d subsystem(s) notified. "
            "Raft term: %d. The platform has been reconfigured "
            "without a single restart. Take that, 'restart-to-apply' philosophy.",
            duration_ms,
            len(changeset.changes),
            len(affected),
            self._raft.current_term,
        )

        return entry

    def _perform_rollback(
        self,
        old_config: dict[str, Any],
        changeset: ConfigChangeset,
    ) -> None:
        """Roll back to the previous configuration."""
        self._emit_event(EventType.HOT_RELOAD_ROLLBACK_INITIATED, {
            "changeset_id": changeset.changeset_id,
        })

        try:
            self._config_manager.apply_raw_config(old_config)
            logger.info(
                "[ORCHESTRATOR] Rollback completed successfully. "
                "The configuration has been restored to its previous state. "
                "Crisis averted. Resume normal FizzBuzz operations."
            )
            self._emit_event(EventType.HOT_RELOAD_ROLLBACK_COMPLETED, {
                "changeset_id": changeset.changeset_id,
            })
        except Exception as e:
            logger.error(
                "[ORCHESTRATOR] CRITICAL: Rollback FAILED: %s. "
                "The configuration is in an indeterminate state. "
                "Consider restarting the process. Consider restarting your career.",
                e,
            )

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                event = Event(
                    event_type=event_type,
                    payload=payload,
                    source="ReloadOrchestrator",
                )
                self._event_bus.publish(event)
            except Exception:
                pass  # Don't let event emission break reloads

    def get_status(self) -> dict[str, Any]:
        """Get the current orchestrator status."""
        return {
            "total_reloads": self._total_reloads,
            "successful_reloads": self._successful_reloads,
            "failed_reloads": self._failed_reloads,
            "success_rate": (
                f"{(self._successful_reloads / self._total_reloads * 100):.1f}%"
                if self._total_reloads > 0
                else "N/A"
            ),
            "registered_subsystems": list(self._subsystem_callbacks.keys()),
            "rollback_history_depth": self._rollback_manager.history_size,
            "total_rollbacks": self._rollback_manager.rollback_count,
        }


# ============================================================
# ConfigWatcher
# ============================================================


class ConfigWatcher:
    """Polls the configuration file for changes in a background thread.

    Runs as a daemonic thread that periodically reads the config file,
    computes its hash, and triggers a reload when the hash changes.
    The thread is daemonic so it won't block process exit — because
    nothing is worse than a FizzBuzz process that refuses to die
    because it's still polling a YAML file.

    The polling approach is deliberately low-tech. We could use
    filesystem watchers (inotify, kqueue, ReadDirectoryChanges),
    but that would require platform-specific code, and this is a
    YAML file for a FizzBuzz application. Polling every 2 seconds
    is more than sufficient for our operational requirements.
    """

    def __init__(
        self,
        config_path: Path,
        orchestrator: ReloadOrchestrator,
        poll_interval_seconds: float = 2.0,
        event_bus: Any = None,
    ) -> None:
        self._config_path = config_path
        self._orchestrator = orchestrator
        self._poll_interval = poll_interval_seconds
        self._event_bus = event_bus
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_hash: Optional[str] = None
        self._poll_count = 0
        self._changes_detected = 0
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def poll_count(self) -> int:
        return self._poll_count

    @property
    def changes_detected(self) -> int:
        return self._changes_detected

    def start(self) -> None:
        """Start the config file watcher in a background thread."""
        if self._running:
            logger.warning("[WATCHER] Already running. Cannot start twice.")
            return

        # Compute initial hash
        self._last_hash = self._compute_file_hash()

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="ConfigWatcher",
            daemon=True,  # CRITICAL: daemonic so it won't block process exit
        )
        self._thread.start()

        self._emit_event(EventType.HOT_RELOAD_WATCHER_STARTED, {
            "config_path": str(self._config_path),
            "poll_interval_seconds": self._poll_interval,
        })

        logger.info(
            "[WATCHER] Configuration file watcher STARTED. "
            "Polling '%s' every %.1fs. Thread is daemonic (won't block exit). "
            "The platform is now watching its own config file with the "
            "vigilance of a security camera pointed at a YAML file.",
            self._config_path,
            self._poll_interval,
        )

    def stop(self) -> None:
        """Stop the config file watcher."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        self._emit_event(EventType.HOT_RELOAD_WATCHER_STOPPED, {
            "config_path": str(self._config_path),
            "total_polls": self._poll_count,
            "changes_detected": self._changes_detected,
        })

        logger.info(
            "[WATCHER] Configuration file watcher STOPPED after %d polls "
            "and %d change detections. The YAML file is no longer under surveillance.",
            self._poll_count,
            self._changes_detected,
        )

    def _poll_loop(self) -> None:
        """Main polling loop (runs in background thread)."""
        while self._running:
            try:
                time.sleep(self._poll_interval)
                if not self._running:
                    break

                self._poll_count += 1
                current_hash = self._compute_file_hash()

                if current_hash is not None and current_hash != self._last_hash:
                    self._changes_detected += 1
                    logger.info(
                        "[WATCHER] Configuration file change detected! "
                        "Hash: %s -> %s. Poll #%d. Triggering reload...",
                        self._last_hash,
                        current_hash,
                        self._poll_count,
                    )

                    self._emit_event(EventType.HOT_RELOAD_FILE_CHANGED, {
                        "config_path": str(self._config_path),
                        "old_hash": self._last_hash,
                        "new_hash": current_hash,
                        "poll_number": self._poll_count,
                    })

                    self._last_hash = current_hash
                    self._trigger_reload()

            except Exception as e:
                logger.error("[WATCHER] Error during poll: %s", e)

    def _compute_file_hash(self) -> Optional[str]:
        """Compute SHA-256 hash of the config file contents."""
        try:
            if self._config_path.exists():
                content = self._config_path.read_bytes()
                return hashlib.sha256(content).hexdigest()[:16]
        except Exception as e:
            logger.warning("[WATCHER] Failed to read config file: %s", e)
        return None

    def _trigger_reload(self) -> None:
        """Load the config file and trigger a reload."""
        try:
            import yaml
        except ImportError:
            logger.warning("[WATCHER] PyYAML not installed. Cannot reload.")
            return

        try:
            with open(self._config_path, "r") as f:
                new_config = yaml.safe_load(f) or {}

            result = self._orchestrator.reload(new_config)
            if result.success:
                logger.info(
                    "[WATCHER] Reload triggered successfully: %s",
                    result.changeset.summary(),
                )
            else:
                logger.warning(
                    "[WATCHER] Reload failed: %s",
                    result.error_message,
                )
        except Exception as e:
            logger.error("[WATCHER] Failed to trigger reload: %s", e)

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                event = Event(
                    event_type=event_type,
                    payload=payload,
                    source="ConfigWatcher",
                )
                self._event_bus.publish(event)
            except Exception:
                pass

    def get_status(self) -> dict[str, Any]:
        """Get the current watcher status."""
        return {
            "running": self._running,
            "config_path": str(self._config_path),
            "poll_interval_seconds": self._poll_interval,
            "poll_count": self._poll_count,
            "changes_detected": self._changes_detected,
            "last_hash": self._last_hash,
            "thread_alive": self._thread.is_alive() if self._thread else False,
            "thread_daemon": True,
        }


# ============================================================
# HotReloadDashboard
# ============================================================


class HotReloadDashboard:
    """ASCII dashboard for the Configuration Hot-Reload subsystem.

    Renders a comprehensive status display including Raft consensus
    status, reload history, dependency graph, and watcher status.
    Because nothing says "enterprise-grade configuration management"
    like an ASCII art dashboard showing the election results of a
    single-node consensus algorithm.
    """

    @staticmethod
    def render(
        raft: SingleNodeRaftConsensus,
        orchestrator: ReloadOrchestrator,
        watcher: Optional[ConfigWatcher] = None,
        dependency_graph: Optional[SubsystemDependencyGraph] = None,
        rollback_manager: Optional[ConfigRollbackManager] = None,
        width: int = 60,
        show_raft_details: bool = True,
    ) -> str:
        """Render the full hot-reload dashboard."""
        lines: list[str] = []
        sep = "=" * width
        thin_sep = "-" * width

        lines.append("")
        lines.append(f"  +{sep}+")
        lines.append(f"  |{'CONFIGURATION HOT-RELOAD DASHBOARD':^{width}}|")
        lines.append(f"  |{'Single-Node Raft Consensus Edition':^{width}}|")
        lines.append(f"  +{sep}+")

        # Raft Status Section
        if show_raft_details:
            lines.append(f"  |{' RAFT CONSENSUS STATUS ':-^{width}}|")
            raft_status = raft.get_status()
            lines.append(f"  |  Node ID          : {raft_status['node_id']:<{width-24}}|")
            lines.append(f"  |  State            : {raft_status['state']:<{width-24}}|")
            lines.append(f"  |  Current Term     : {str(raft_status['current_term']):<{width-24}}|")
            lines.append(f"  |  Leader           : {str(raft_status['leader_id'] or 'None'):<{width-24}}|")
            lines.append(f"  |  Cluster Size     : {str(raft_status['cluster_size']):<{width-24}}|")
            lines.append(f"  |  Quorum Size      : {str(raft_status['quorum_size']):<{width-24}}|")
            lines.append(f"  |  Elections Won    : {str(raft_status['total_elections_won']):<{width-24}}|")
            lines.append(f"  |  Election Win Rate: {raft_status['election_win_rate']:<{width-24}}|")
            lines.append(f"  |  Heartbeats Sent  : {str(raft_status['total_heartbeats_sent']):<{width-24}}|")
            lines.append(f"  |  Heartbeat Success: {raft_status['heartbeat_success_rate']:<{width-24}}|")
            lines.append(f"  |  Log Entries      : {str(raft_status['log_length']):<{width-24}}|")
            lines.append(f"  |  Commit Index     : {str(raft_status['commit_index']):<{width-24}}|")
            lines.append(f"  |  Split-Brain      : {str(raft_status['split_brain_incidents']):<{width-24}}|")
            lines.append(f"  |  Consensus Fails  : {str(raft_status['consensus_failures']):<{width-24}}|")
            lines.append(f"  |  Followers        : {str(len(raft_status['followers'])):<{width-24}}|")
            lines.append(f"  |  Cluster Health   : {'HEALTHY (trivially)':<{width-24}}|")
            lines.append(f"  +{thin_sep}+")

        # Orchestrator Status
        lines.append(f"  |{' RELOAD ORCHESTRATOR ':-^{width}}|")
        orch_status = orchestrator.get_status()
        lines.append(f"  |  Total Reloads    : {str(orch_status['total_reloads']):<{width-24}}|")
        lines.append(f"  |  Successful       : {str(orch_status['successful_reloads']):<{width-24}}|")
        lines.append(f"  |  Failed           : {str(orch_status['failed_reloads']):<{width-24}}|")
        lines.append(f"  |  Success Rate     : {orch_status['success_rate']:<{width-24}}|")
        lines.append(f"  |  Total Rollbacks  : {str(orch_status['total_rollbacks']):<{width-24}}|")
        lines.append(f"  |  Rollback History : {str(orch_status['rollback_history_depth']):<{width-24}}|")
        lines.append(f"  +{thin_sep}+")

        # Watcher Status
        if watcher is not None:
            lines.append(f"  |{' CONFIG FILE WATCHER ':-^{width}}|")
            w_status = watcher.get_status()
            running_str = "ACTIVE" if w_status["running"] else "STOPPED"
            lines.append(f"  |  Status           : {running_str:<{width-24}}|")
            lines.append(f"  |  Config Path      : {str(w_status['config_path'])[-width+24:]:<{width-24}}|")
            lines.append(f"  |  Poll Interval    : {str(w_status['poll_interval_seconds'])+'s':<{width-24}}|")
            lines.append(f"  |  Total Polls      : {str(w_status['poll_count']):<{width-24}}|")
            lines.append(f"  |  Changes Detected : {str(w_status['changes_detected']):<{width-24}}|")
            lines.append(f"  |  Last Hash        : {str(w_status['last_hash'] or 'N/A'):<{width-24}}|")
            daemon_str = "Yes (will not block exit)"
            lines.append(f"  |  Thread Daemon    : {daemon_str:<{width-24}}|")
            lines.append(f"  +{thin_sep}+")

        # Reload History
        history = orchestrator.reload_history
        lines.append(f"  |{' RELOAD HISTORY (last 5) ':-^{width}}|")
        if history:
            for entry in history[-5:]:
                status = "OK" if entry.success else "FAIL"
                rb = " [ROLLED BACK]" if entry.rolled_back else ""
                cs = entry.changeset
                line = (
                    f"  |  [{status}] T{entry.raft_term} "
                    f"cs:{cs.changeset_id} "
                    f"+{cs.added_count}/~{cs.modified_count}/-{cs.removed_count} "
                    f"{entry.duration_ms:.1f}ms{rb}"
                )
                lines.append(f"{line:<{width+4}}|")
        else:
            lines.append(f"  |  {'No reloads recorded yet.':<{width-4}}|")
        lines.append(f"  +{thin_sep}+")

        # Dependency Graph
        if dependency_graph is not None:
            lines.append(f"  |{' SUBSYSTEM DEPENDENCY GRAPH ':-^{width}}|")
            try:
                order = dependency_graph.get_reload_order()
                order_str = " -> ".join(order) if order else "No subsystems registered"
                # Wrap long order strings
                remaining = order_str
                while remaining:
                    chunk = remaining[:width - 6]
                    remaining = remaining[width - 6:]
                    lines.append(f"  |  {chunk:<{width-4}}|")
            except DependencyGraphCycleError:
                lines.append(f"  |  {'CYCLE DETECTED - reload order undefined':<{width-4}}|")
            lines.append(f"  +{thin_sep}+")

        # Election History
        if show_raft_details and raft.election_history:
            lines.append(f"  |{' ELECTION HISTORY (last 3) ':-^{width}}|")
            for election in raft.election_history[-3:]:
                line = (
                    f"  |  Term {election.term}: "
                    f"WON {election.votes_received}/{election.votes_needed} "
                    f"in {election.election_duration_ms:.3f}ms (UNANIMOUS)"
                )
                lines.append(f"{line:<{width+4}}|")
            lines.append(f"  +{thin_sep}+")

        # Footer
        footer_text = "Consensus is easy when you are the only voter"
        lines.append(f"  |{footer_text:^{width}}|")
        lines.append(f"  +{sep}+")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_diff(changeset: ConfigChangeset, width: int = 60) -> str:
        """Render a configuration diff as ASCII."""
        lines: list[str] = []
        sep = "-" * width

        lines.append("")
        lines.append(f"  +{sep}+")
        lines.append(f"  |{'CONFIGURATION DIFF':^{width}}|")
        lines.append(f"  +{sep}+")
        lines.append(f"  |  Changeset : {changeset.changeset_id:<{width-16}}|")
        lines.append(f"  |  Hash      : {changeset.config_hash_before} -> {changeset.config_hash_after:<{width-16-len(changeset.config_hash_before)-4}}|")
        lines.append(f"  |  Added     : {changeset.added_count:<{width-16}}|")
        lines.append(f"  |  Modified  : {changeset.modified_count:<{width-16}}|")
        lines.append(f"  |  Removed   : {changeset.removed_count:<{width-16}}|")
        lines.append(f"  +{sep}+")

        for change in changeset.changes:
            change_str = str(change)
            lines.append(f"  |{change_str:<{width+2}}|")

        lines.append(f"  +{sep}+")
        lines.append("")

        return "\n".join(lines)


# ============================================================
# Factory Function
# ============================================================


def create_hot_reload_subsystem(
    config_manager: Any,
    config_path: Path,
    poll_interval_seconds: float = 2.0,
    heartbeat_interval_ms: int = 150,
    election_timeout_ms: int = 300,
    max_rollback_history: int = 10,
    validate_before_apply: bool = True,
    log_diffs: bool = True,
    event_bus: Any = None,
) -> tuple[SingleNodeRaftConsensus, ReloadOrchestrator, ConfigWatcher, SubsystemDependencyGraph, ConfigRollbackManager]:
    """Create and wire up the complete hot-reload subsystem.

    This is the factory function that constructs and connects all
    hot-reload components. It's like a FizzBuzzServiceBuilder, but
    for the subsystem that re-reads YAML files.

    Args:
        config_manager: The ConfigurationManager instance.
        config_path: Path to the config.yaml file.
        poll_interval_seconds: How often to poll for changes.
        heartbeat_interval_ms: Raft heartbeat interval.
        election_timeout_ms: Raft election timeout.
        max_rollback_history: Number of previous configs to retain.
        validate_before_apply: Whether to validate before applying.
        log_diffs: Whether to log configuration diffs.
        event_bus: Optional event bus for event emission.

    Returns:
        Tuple of (raft, orchestrator, watcher, dependency_graph, rollback_manager).
    """
    # Create the Raft consensus engine
    raft = SingleNodeRaftConsensus(
        node_id="fizzbuzz-node-0",
        heartbeat_interval_ms=heartbeat_interval_ms,
        election_timeout_ms=election_timeout_ms,
    )

    # Win the first election immediately
    raft.start_election()

    # Create the rollback manager
    rollback_manager = ConfigRollbackManager(max_history=max_rollback_history)

    # Create the dependency graph with default subsystems
    dependency_graph = SubsystemDependencyGraph()
    dependency_graph.add_subsystem("logging")
    dependency_graph.add_subsystem("rule_engine", depends_on=["logging"])
    dependency_graph.add_subsystem("formatters", depends_on=["logging"])
    dependency_graph.add_subsystem("cache", depends_on=["rule_engine"])
    dependency_graph.add_subsystem("circuit_breaker", depends_on=["logging"])
    dependency_graph.add_subsystem("sla_monitor", depends_on=["logging"])
    dependency_graph.add_subsystem("middleware", depends_on=["rule_engine"])
    dependency_graph.add_subsystem("feature_flags", depends_on=["rule_engine"])
    dependency_graph.add_subsystem("hot_reload", depends_on=["logging"])

    # Create the orchestrator
    orchestrator = ReloadOrchestrator(
        config_manager=config_manager,
        raft=raft,
        rollback_manager=rollback_manager,
        dependency_graph=dependency_graph,
        validate_before_apply=validate_before_apply,
        log_diffs=log_diffs,
        event_bus=event_bus,
    )

    # Create the file watcher
    watcher = ConfigWatcher(
        config_path=config_path,
        orchestrator=orchestrator,
        poll_interval_seconds=poll_interval_seconds,
        event_bus=event_bus,
    )

    logger.info(
        "[HOT-RELOAD] Subsystem created. Raft consensus: READY. "
        "File watcher: ARMED. Rollback manager: PRIMED. "
        "Dependency graph: %d subsystems in topological order. "
        "The platform is prepared to re-read a YAML file with the "
        "ceremony and gravitas it deserves.",
        len(dependency_graph.get_reload_order()),
    )

    return raft, orchestrator, watcher, dependency_graph, rollback_manager
