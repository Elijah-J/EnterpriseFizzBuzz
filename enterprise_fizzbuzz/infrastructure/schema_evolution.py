"""
Enterprise FizzBuzz Platform - FizzSchema: Consensus-Based Schema Evolution

Provides Avro/Protobuf-inspired schema versioning with compatibility
enforcement, Paxos-based consensus approval, and migration planning.

In any serious enterprise, data contracts are not suggestions — they
are legally binding agreements between producers and consumers. The
FizzBuzz evaluation result schema is no exception. When the shape of
an EvaluationResult changes (e.g., adding a ``cache_hit`` field in v3),
every downstream consumer — dashboards, compliance auditors, blockchain
observers, the ML engine — must be consulted. This module ensures that
schema changes undergo the same rigorous governance as a constitutional
amendment: proposal, compatibility analysis, majority consensus, and
ratification. Only then may a new field be added to a FizzBuzz result.

Uses stdlib only: hashlib, json, enum, dataclasses, typing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions import (
    SchemaCompatibilityError,
    SchemaConsensusError,
    SchemaEvolutionError,
    SchemaRegistrationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enums
# ============================================================


class SchemaFieldType(Enum):
    """Supported field types in the FizzSchema type system.

    These types map to the intersection of Avro primitive types
    and Protobuf scalar types, providing a lingua franca for
    schema definitions across serialization frameworks. The fact
    that we are using them to describe whether a number is
    divisible by 3 is entirely beside the point.
    """

    INT64 = "int64"
    FLOAT64 = "float64"
    STRING = "string"
    BOOL = "bool"
    ENUM = "enum"
    ARRAY = "array"


class CompatibilityMode(Enum):
    """Schema compatibility enforcement modes.

    These modes mirror Apache Avro's compatibility guarantees and
    determine which schema changes are permitted without breaking
    existing consumers or producers.

    BACKWARD: New schema can read data written by old schema.
    FORWARD: Old schema can read data written by new schema.
    FULL: Both BACKWARD and FORWARD simultaneously.
    NONE: Anarchy. No compatibility checking. Not recommended
          for production FizzBuzz deployments.
    """

    BACKWARD = "BACKWARD"
    FORWARD = "FORWARD"
    FULL = "FULL"
    NONE = "NONE"


class PaxosPhase(Enum):
    """Phases of the Paxos consensus protocol for schema approval."""

    PREPARE = auto()
    PROMISE = auto()
    ACCEPT = auto()
    LEARN = auto()


class ConsensusNodeState(Enum):
    """State of a consensus node during schema approval voting."""

    IDLE = auto()
    PROMISED = auto()
    ACCEPTED = auto()
    REJECTED = auto()
    FAILED = auto()


# ============================================================
# Data Models
# ============================================================


@dataclass
class SchemaField:
    """A single field within a versioned schema definition.

    Each field has a unique tag number (analogous to Protobuf field
    numbers) that provides stable wire-format identification across
    schema versions. Tags are immutable once assigned — reusing a
    tag for a different field is a war crime under the Data Contract
    Geneva Convention.
    """

    name: str
    field_type: SchemaFieldType
    tag: int
    default: Any = None
    deprecated: bool = False
    doc: str = ""

    def has_default(self) -> bool:
        """Whether this field has a default value defined."""
        return self.default is not None

    def to_dict(self) -> dict[str, Any]:
        """Serialize field metadata to dictionary."""
        return {
            "name": self.name,
            "type": self.field_type.value,
            "tag": self.tag,
            "default": self.default,
            "deprecated": self.deprecated,
            "doc": self.doc,
        }


@dataclass
class Schema:
    """A versioned schema definition with fingerprint-based identity.

    Schemas are immutable once registered. The fingerprint is computed
    from the sorted (name, tag, type) tuples of all fields, providing
    a content-addressable identity that is independent of field ordering
    in the source definition. Two schemas with identical fields will
    always produce the same fingerprint, regardless of declaration order.
    """

    name: str
    version: int
    fields: list[SchemaField]
    doc: str = ""
    _fingerprint: Optional[str] = field(default=None, repr=False)

    @property
    def fingerprint(self) -> str:
        """SHA-256 fingerprint of the schema's field structure.

        Computed lazily and cached. The fingerprint is derived from
        the sorted (name, tag, type) tuples, ensuring order-independent
        identity. This is the schema's true name — version numbers are
        for humans, fingerprints are for machines.
        """
        if self._fingerprint is None:
            canonical = sorted(
                (f.name, f.tag, f.field_type.value) for f in self.fields
            )
            raw = json.dumps(canonical, sort_keys=True).encode("utf-8")
            self._fingerprint = hashlib.sha256(raw).hexdigest()
        return self._fingerprint

    @property
    def field_names(self) -> set[str]:
        """Set of all field names in this schema."""
        return {f.name for f in self.fields}

    @property
    def field_by_name(self) -> dict[str, SchemaField]:
        """Lookup fields by name."""
        return {f.name: f for f in self.fields}

    @property
    def field_by_tag(self) -> dict[int, SchemaField]:
        """Lookup fields by tag number."""
        return {f.tag: f for f in self.fields}

    def to_dict(self) -> dict[str, Any]:
        """Serialize schema metadata to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "field_count": len(self.fields),
            "fields": [f.to_dict() for f in self.fields],
            "doc": self.doc,
        }


# ============================================================
# Compatibility Checking
# ============================================================


@dataclass
class CompatibilityResult:
    """Result of comparing two schemas for compatibility.

    Contains violations (hard failures), warnings (deprecations,
    type promotions), and an overall verdict. A schema change with
    any violations is rejected; warnings are informational and
    logged for the Schema Review Board's quarterly audit.
    """

    compatible: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mode: CompatibilityMode = CompatibilityMode.BACKWARD


class CompatibilityChecker:
    """Compares two schemas and produces a compatibility verdict.

    Implements the compatibility rules defined by Avro's Schema
    Resolution specification, adapted for the unique requirements
    of the FizzBuzz evaluation pipeline. The checker supports
    BACKWARD, FORWARD, FULL, and NONE compatibility modes, each
    with distinct constraints on field additions, removals, and
    type changes.
    """

    # Type promotions that are safe (widening conversions only)
    SAFE_PROMOTIONS: dict[SchemaFieldType, set[SchemaFieldType]] = {
        SchemaFieldType.INT64: {SchemaFieldType.FLOAT64, SchemaFieldType.STRING},
        SchemaFieldType.FLOAT64: {SchemaFieldType.STRING},
        SchemaFieldType.BOOL: {SchemaFieldType.STRING, SchemaFieldType.INT64},
    }

    def check(
        self,
        old_schema: Schema,
        new_schema: Schema,
        mode: CompatibilityMode,
    ) -> CompatibilityResult:
        """Check compatibility between old and new schema versions.

        Args:
            old_schema: The previously registered schema version.
            new_schema: The proposed new schema version.
            mode: The compatibility mode to enforce.

        Returns:
            CompatibilityResult with violations, warnings, and verdict.
        """
        if mode == CompatibilityMode.NONE:
            return CompatibilityResult(compatible=True, mode=mode)

        violations: list[str] = []
        warnings: list[str] = []

        old_fields = old_schema.field_by_name
        new_fields = new_schema.field_by_name

        added_fields = new_schema.field_names - old_schema.field_names
        removed_fields = old_schema.field_names - new_schema.field_names
        common_fields = old_schema.field_names & new_schema.field_names

        if mode in (CompatibilityMode.BACKWARD, CompatibilityMode.FULL):
            self._check_backward(
                added_fields, removed_fields, old_fields, new_fields,
                violations, warnings,
            )

        if mode in (CompatibilityMode.FORWARD, CompatibilityMode.FULL):
            self._check_forward(
                added_fields, removed_fields, old_fields, new_fields,
                violations, warnings,
            )

        # Check type changes for common fields
        for name in common_fields:
            old_f = old_fields[name]
            new_f = new_fields[name]

            if old_f.field_type != new_f.field_type:
                if new_f.field_type in self.SAFE_PROMOTIONS.get(old_f.field_type, set()):
                    warnings.append(
                        f"Field '{name}': type promotion {old_f.field_type.value} -> "
                        f"{new_f.field_type.value} (safe widening conversion)"
                    )
                else:
                    violations.append(
                        f"Field '{name}': incompatible type change "
                        f"{old_f.field_type.value} -> {new_f.field_type.value}"
                    )

            if old_f.tag != new_f.tag:
                violations.append(
                    f"Field '{name}': tag number changed from {old_f.tag} to {new_f.tag} "
                    f"(tag reassignment violates the Data Contract Geneva Convention)"
                )

            if new_f.deprecated and not old_f.deprecated:
                warnings.append(
                    f"Field '{name}': newly deprecated (consumers should migrate away)"
                )

        return CompatibilityResult(
            compatible=len(violations) == 0,
            violations=violations,
            warnings=warnings,
            mode=mode,
        )

    def _check_backward(
        self,
        added: set[str],
        removed: set[str],
        old_fields: dict[str, SchemaField],
        new_fields: dict[str, SchemaField],
        violations: list[str],
        warnings: list[str],
    ) -> None:
        """BACKWARD: new readers must handle old data."""
        # New fields must have defaults (old data won't have them)
        for name in added:
            f = new_fields[name]
            if not f.has_default():
                violations.append(
                    f"BACKWARD violation: new field '{name}' has no default value "
                    f"(old data will not contain this field)"
                )
            else:
                warnings.append(
                    f"New field '{name}' added with default={f.default!r}"
                )

        # Removed fields must have had defaults (they were optional)
        for name in removed:
            f = old_fields[name]
            if not f.has_default():
                violations.append(
                    f"BACKWARD violation: removed field '{name}' had no default value "
                    f"(it was required in the old schema)"
                )

    def _check_forward(
        self,
        added: set[str],
        removed: set[str],
        old_fields: dict[str, SchemaField],
        new_fields: dict[str, SchemaField],
        violations: list[str],
        warnings: list[str],
    ) -> None:
        """FORWARD: old readers must handle new data."""
        # Removed fields must have defaults in old schema
        # (old readers will look for them in new data and not find them)
        for name in removed:
            f = old_fields[name]
            if not f.has_default():
                violations.append(
                    f"FORWARD violation: removed field '{name}' has no default in old schema "
                    f"(old readers will fail when field is missing from new data)"
                )

        # New fields are ignored by old readers (acceptable for FORWARD)
        for name in added:
            warnings.append(
                f"New field '{name}' will be ignored by old readers (FORWARD-safe)"
            )


# ============================================================
# Schema Registry
# ============================================================


class SchemaRegistry:
    """Central registry for all versioned schemas in the platform.

    The registry enforces compatibility constraints on registration,
    maintains a version history for each schema name, and supports
    lookup by name+version or by fingerprint. It is the single
    source of truth for data contracts.

    Think of it as a corporate HR department, but for data structures.
    Every field must be properly onboarded, documented, and approved
    before it can participate in the organization.
    """

    def __init__(self, default_mode: CompatibilityMode = CompatibilityMode.BACKWARD) -> None:
        self._schemas: dict[str, dict[int, Schema]] = {}
        self._fingerprint_index: dict[str, Schema] = {}
        self._compatibility_mode: dict[str, CompatibilityMode] = {}
        self._default_mode = default_mode
        self._checker = CompatibilityChecker()
        self._history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def schema_names(self) -> list[str]:
        """All registered schema names."""
        return list(self._schemas.keys())

    @property
    def history(self) -> list[dict[str, Any]]:
        """Compatibility check history for audit purposes."""
        return list(self._history)

    def set_compatibility_mode(self, schema_name: str, mode: CompatibilityMode) -> None:
        """Set the compatibility mode for a specific schema."""
        with self._lock:
            self._compatibility_mode[schema_name] = mode
            logger.info(
                "Compatibility mode for '%s' set to %s",
                schema_name, mode.value,
            )

    def get_compatibility_mode(self, schema_name: str) -> CompatibilityMode:
        """Get the compatibility mode for a schema (falls back to default)."""
        return self._compatibility_mode.get(schema_name, self._default_mode)

    def register(self, schema: Schema, *, force: bool = False) -> CompatibilityResult:
        """Register a new schema version in the registry.

        Enforces compatibility against the latest version of the
        same schema name. If compatibility check fails and force
        is not set, raises SchemaRegistrationError.

        Args:
            schema: The schema to register.
            force: Skip compatibility checking (use with extreme caution).

        Returns:
            CompatibilityResult from the check (or a clean result if first version).

        Raises:
            SchemaRegistrationError: If compatibility check fails.
        """
        with self._lock:
            return self._register_internal(schema, force=force)

    def _register_internal(self, schema: Schema, *, force: bool = False) -> CompatibilityResult:
        """Internal registration logic (must be called under lock)."""
        name = schema.name
        version = schema.version

        # Check for duplicate fingerprint with different name/version
        if schema.fingerprint in self._fingerprint_index:
            existing = self._fingerprint_index[schema.fingerprint]
            if existing.name != name or existing.version != version:
                raise SchemaRegistrationError(
                    name, version,
                    f"Fingerprint collision with '{existing.name}' v{existing.version} "
                    f"(identical field structure already registered)",
                )

        # Check for version conflict
        if name in self._schemas and version in self._schemas[name]:
            existing = self._schemas[name][version]
            if existing.fingerprint != schema.fingerprint:
                raise SchemaRegistrationError(
                    name, version,
                    f"Version {version} already registered with different fingerprint "
                    f"(existing: {existing.fingerprint[:16]}..., "
                    f"proposed: {schema.fingerprint[:16]}...)",
                )
            # Identical re-registration is idempotent
            return CompatibilityResult(compatible=True, mode=self.get_compatibility_mode(name))

        # Compatibility check against latest version
        result = CompatibilityResult(compatible=True, mode=self.get_compatibility_mode(name))
        if name in self._schemas and self._schemas[name]:
            latest_version = max(self._schemas[name].keys())
            latest = self._schemas[name][latest_version]
            mode = self.get_compatibility_mode(name)
            result = self._checker.check(latest, schema, mode)

            self._history.append({
                "schema_name": name,
                "from_version": latest_version,
                "to_version": version,
                "mode": mode.value,
                "compatible": result.compatible,
                "violations": result.violations,
                "warnings": result.warnings,
                "timestamp": time.time(),
            })

            if not result.compatible and not force:
                raise SchemaRegistrationError(
                    name, version,
                    f"Compatibility check failed ({mode.value}): "
                    f"{len(result.violations)} violation(s)",
                )

        # Register
        if name not in self._schemas:
            self._schemas[name] = {}
        self._schemas[name][version] = schema
        self._fingerprint_index[schema.fingerprint] = schema

        logger.info(
            "Registered schema '%s' v%d (fingerprint: %s)",
            name, version, schema.fingerprint[:16],
        )

        return result

    def get(self, name: str, version: Optional[int] = None) -> Optional[Schema]:
        """Look up a schema by name and optional version.

        If version is None, returns the latest version.
        """
        if name not in self._schemas:
            return None
        versions = self._schemas[name]
        if not versions:
            return None
        if version is not None:
            return versions.get(version)
        return versions[max(versions.keys())]

    def get_by_fingerprint(self, fingerprint: str) -> Optional[Schema]:
        """Look up a schema by its SHA-256 fingerprint."""
        return self._fingerprint_index.get(fingerprint)

    def get_versions(self, name: str) -> list[int]:
        """Get all registered version numbers for a schema name."""
        if name not in self._schemas:
            return []
        return sorted(self._schemas[name].keys())

    def get_all_schemas(self) -> list[Schema]:
        """Get all registered schemas, ordered by name and version."""
        result: list[Schema] = []
        for name in sorted(self._schemas.keys()):
            for version in sorted(self._schemas[name].keys()):
                result.append(self._schemas[name][version])
        return result


# ============================================================
# Migration Planning
# ============================================================


@dataclass
class FieldMigration:
    """A single field-level migration action."""

    action: str  # "ADD", "REMOVE", "PROMOTE", "DEPRECATE"
    field_name: str
    detail: str
    default_value: Any = None


@dataclass
class MigrationPlan:
    """A complete migration plan from one schema version to another.

    Contains the ordered list of field-level actions required to
    transform data from the old schema to the new schema. The plan
    is deterministic: given the same old and new schemas, the same
    plan will always be produced.
    """

    schema_name: str
    from_version: int
    to_version: int
    actions: list[FieldMigration] = field(default_factory=list)

    @property
    def has_breaking_changes(self) -> bool:
        """Whether the migration contains potentially breaking changes."""
        return any(a.action == "REMOVE" for a in self.actions)

    @property
    def summary(self) -> str:
        """Human-readable summary of the migration plan."""
        counts: dict[str, int] = {}
        for a in self.actions:
            counts[a.action] = counts.get(a.action, 0) + 1
        parts = [f"{count} {action.lower()}(s)" for action, count in sorted(counts.items())]
        return f"{self.schema_name} v{self.from_version} -> v{self.to_version}: {', '.join(parts) or 'no changes'}"


class MigrationPlanner:
    """Produces migration plans between schema versions.

    The planner compares two schemas and generates a deterministic
    ordered list of field-level migration actions. These actions can
    be applied to transform data from the old schema format to the
    new format, handling field additions (with defaults), removals,
    type promotions, and deprecation transitions.
    """

    SAFE_PROMOTIONS = CompatibilityChecker.SAFE_PROMOTIONS

    def plan(self, old_schema: Schema, new_schema: Schema) -> MigrationPlan:
        """Generate a migration plan between two schema versions.

        Args:
            old_schema: The source schema version.
            new_schema: The target schema version.

        Returns:
            MigrationPlan with ordered field-level actions.
        """
        actions: list[FieldMigration] = []

        old_fields = old_schema.field_by_name
        new_fields = new_schema.field_by_name

        added = new_schema.field_names - old_schema.field_names
        removed = old_schema.field_names - new_schema.field_names
        common = old_schema.field_names & new_schema.field_names

        # Additions
        for name in sorted(added):
            f = new_fields[name]
            actions.append(FieldMigration(
                action="ADD",
                field_name=name,
                detail=f"Add field '{name}' ({f.field_type.value}, tag={f.tag})"
                       + (f", default={f.default!r}" if f.has_default() else ", NO DEFAULT"),
                default_value=f.default,
            ))

        # Removals
        for name in sorted(removed):
            f = old_fields[name]
            actions.append(FieldMigration(
                action="REMOVE",
                field_name=name,
                detail=f"Remove field '{name}' ({f.field_type.value}, tag={f.tag})",
            ))

        # Changes to common fields
        for name in sorted(common):
            old_f = old_fields[name]
            new_f = new_fields[name]

            # Type promotion
            if old_f.field_type != new_f.field_type:
                safe = new_f.field_type in self.SAFE_PROMOTIONS.get(old_f.field_type, set())
                actions.append(FieldMigration(
                    action="PROMOTE",
                    field_name=name,
                    detail=f"Type promotion '{name}': {old_f.field_type.value} -> "
                           f"{new_f.field_type.value} ({'safe' if safe else 'UNSAFE'})",
                ))

            # Deprecation
            if new_f.deprecated and not old_f.deprecated:
                actions.append(FieldMigration(
                    action="DEPRECATE",
                    field_name=name,
                    detail=f"Deprecate field '{name}' (consumers should migrate away)",
                ))

        return MigrationPlan(
            schema_name=new_schema.name,
            from_version=old_schema.version,
            to_version=new_schema.version,
            actions=actions,
        )


# ============================================================
# Paxos Consensus Approval
# ============================================================


@dataclass
class ConsensusNode:
    """A single node in the Paxos consensus cluster.

    Each node independently evaluates schema compatibility and
    casts its vote. Nodes can fail (simulated) to test fault
    tolerance of the consensus protocol. A failed node does not
    participate in voting but counts toward the total cluster size.
    """

    node_id: int
    state: ConsensusNodeState = ConsensusNodeState.IDLE
    promised_proposal: Optional[int] = None
    accepted_proposal: Optional[int] = None
    accepted_value: Optional[bool] = None
    failure_injected: bool = False

    def reset(self) -> None:
        """Reset node to idle state for the next round."""
        self.state = ConsensusNodeState.IDLE
        self.promised_proposal = None
        self.accepted_proposal = None
        self.accepted_value = None


@dataclass
class ConsensusRound:
    """Record of a single Paxos consensus round."""

    round_id: str
    schema_name: str
    version: int
    proposal_number: int
    phase_log: list[dict[str, Any]] = field(default_factory=list)
    approved: bool = False
    approvals: int = 0
    rejections: int = 0
    failures: int = 0
    duration_ms: float = 0.0


class ConsensusApprover:
    """Paxos-based consensus protocol for schema change approval.

    Implements a simplified Paxos consensus protocol with 5 nodes
    (configurable) and a quorum of 3 (configurable). Each node
    independently evaluates the proposed schema change against the
    active compatibility mode and casts its vote.

    The protocol proceeds through four phases:
    1. PREPARE: Proposer sends proposal number to all nodes.
    2. PROMISE: Nodes promise not to accept lower-numbered proposals.
    3. ACCEPT: Proposer sends the schema change for acceptance.
    4. LEARN: If quorum is reached, all nodes learn the decision.

    Fault injection is supported: individual nodes can be marked as
    failed, simulating network partitions or node crashes. The protocol
    tolerates up to (N - quorum) failures and still reaches consensus.
    """

    def __init__(
        self,
        num_nodes: int = 5,
        quorum: int = 3,
    ) -> None:
        if quorum > num_nodes:
            raise SchemaEvolutionError(
                f"Quorum ({quorum}) cannot exceed number of nodes ({num_nodes})"
            )
        self._num_nodes = num_nodes
        self._quorum = quorum
        self._nodes = [ConsensusNode(node_id=i) for i in range(num_nodes)]
        self._proposal_counter = 0
        self._checker = CompatibilityChecker()
        self._rounds: list[ConsensusRound] = []
        self._lock = threading.Lock()

    @property
    def nodes(self) -> list[ConsensusNode]:
        """Access the consensus nodes."""
        return list(self._nodes)

    @property
    def rounds(self) -> list[ConsensusRound]:
        """History of consensus rounds."""
        return list(self._rounds)

    def inject_failure(self, node_id: int) -> None:
        """Simulate a node failure (network partition, crash, etc.)."""
        if 0 <= node_id < self._num_nodes:
            self._nodes[node_id].failure_injected = True
            self._nodes[node_id].state = ConsensusNodeState.FAILED
            logger.warning("Node %d marked as failed", node_id)

    def recover_node(self, node_id: int) -> None:
        """Recover a previously failed node."""
        if 0 <= node_id < self._num_nodes:
            self._nodes[node_id].failure_injected = False
            self._nodes[node_id].state = ConsensusNodeState.IDLE
            logger.info("Node %d recovered", node_id)

    def approve(
        self,
        old_schema: Optional[Schema],
        new_schema: Schema,
        mode: CompatibilityMode,
    ) -> ConsensusRound:
        """Run the full Paxos consensus protocol for a schema change.

        Args:
            old_schema: The previous schema version (None if first version).
            new_schema: The proposed new schema version.
            mode: The compatibility mode to enforce.

        Returns:
            ConsensusRound with the full voting record.

        Raises:
            SchemaConsensusError: If quorum is not reached.
        """
        with self._lock:
            return self._run_consensus(old_schema, new_schema, mode)

    def _run_consensus(
        self,
        old_schema: Optional[Schema],
        new_schema: Schema,
        mode: CompatibilityMode,
    ) -> ConsensusRound:
        """Execute the Paxos protocol (must be called under lock)."""
        start_time = time.monotonic()
        self._proposal_counter += 1
        proposal_num = self._proposal_counter

        round_record = ConsensusRound(
            round_id=str(uuid.uuid4())[:8],
            schema_name=new_schema.name,
            version=new_schema.version,
            proposal_number=proposal_num,
        )

        # Reset non-failed nodes
        for node in self._nodes:
            if not node.failure_injected:
                node.reset()

        # Phase 1: PREPARE
        round_record.phase_log.append({
            "phase": PaxosPhase.PREPARE.name,
            "proposal": proposal_num,
            "message": f"Proposer sends PREPARE({proposal_num}) to all nodes",
        })

        # Phase 2: PROMISE
        promises = 0
        for node in self._nodes:
            if node.failure_injected:
                round_record.failures += 1
                round_record.phase_log.append({
                    "phase": PaxosPhase.PROMISE.name,
                    "node_id": node.node_id,
                    "result": "FAILED",
                    "message": f"Node {node.node_id} is unreachable (failure injected)",
                })
                continue

            if node.promised_proposal is None or proposal_num > node.promised_proposal:
                node.promised_proposal = proposal_num
                node.state = ConsensusNodeState.PROMISED
                promises += 1
                round_record.phase_log.append({
                    "phase": PaxosPhase.PROMISE.name,
                    "node_id": node.node_id,
                    "result": "PROMISED",
                    "message": f"Node {node.node_id} promises for proposal {proposal_num}",
                })
            else:
                round_record.phase_log.append({
                    "phase": PaxosPhase.PROMISE.name,
                    "node_id": node.node_id,
                    "result": "REJECTED",
                    "message": f"Node {node.node_id} already promised for higher proposal",
                })

        if promises < self._quorum:
            round_record.approved = False
            round_record.duration_ms = (time.monotonic() - start_time) * 1000
            self._rounds.append(round_record)
            raise SchemaConsensusError(
                new_schema.name, promises, self._quorum,
                "Failed to gather enough promises in PREPARE phase",
            )

        # Phase 3: ACCEPT — each node independently checks compatibility
        approvals = 0
        rejections = 0
        for node in self._nodes:
            if node.failure_injected or node.state != ConsensusNodeState.PROMISED:
                continue

            # Each node independently evaluates compatibility
            if old_schema is not None and mode != CompatibilityMode.NONE:
                result = self._checker.check(old_schema, new_schema, mode)
                vote = result.compatible
            else:
                vote = True  # First version or NONE mode — auto-approve

            node.accepted_proposal = proposal_num
            node.accepted_value = vote

            if vote:
                node.state = ConsensusNodeState.ACCEPTED
                approvals += 1
                round_record.phase_log.append({
                    "phase": PaxosPhase.ACCEPT.name,
                    "node_id": node.node_id,
                    "result": "ACCEPTED",
                    "message": f"Node {node.node_id} accepts schema change (compatible)",
                })
            else:
                node.state = ConsensusNodeState.REJECTED
                rejections += 1
                round_record.phase_log.append({
                    "phase": PaxosPhase.ACCEPT.name,
                    "node_id": node.node_id,
                    "result": "REJECTED",
                    "message": f"Node {node.node_id} rejects schema change (incompatible)",
                })

        round_record.approvals = approvals
        round_record.rejections = rejections

        # Phase 4: LEARN
        if approvals >= self._quorum:
            round_record.approved = True
            round_record.phase_log.append({
                "phase": PaxosPhase.LEARN.name,
                "result": "APPROVED",
                "message": f"Quorum reached ({approvals}/{self._quorum}): schema change approved",
            })
        else:
            round_record.approved = False
            round_record.phase_log.append({
                "phase": PaxosPhase.LEARN.name,
                "result": "REJECTED",
                "message": f"Quorum not reached ({approvals}/{self._quorum}): schema change rejected",
            })

        round_record.duration_ms = (time.monotonic() - start_time) * 1000
        self._rounds.append(round_record)

        if not round_record.approved:
            raise SchemaConsensusError(
                new_schema.name, approvals, self._quorum,
                f"Schema change rejected by consensus ({rejections} rejection(s), "
                f"{round_record.failures} failure(s))",
            )

        return round_record


# ============================================================
# Built-in EvaluationResult Schema Lineage
# ============================================================


def _build_evaluation_result_v1() -> Schema:
    """EvaluationResult v1: the original, pure schema."""
    return Schema(
        name="EvaluationResult",
        version=1,
        fields=[
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ],
        doc="Original EvaluationResult: number and its FizzBuzz classification",
    )


def _build_evaluation_result_v2() -> Schema:
    """EvaluationResult v2: added strategy and latency tracking."""
    return Schema(
        name="EvaluationResult",
        version=2,
        fields=[
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("strategy", SchemaFieldType.STRING, tag=3, default="standard"),
            SchemaField("latency_ns", SchemaFieldType.INT64, tag=4, default=0),
        ],
        doc="EvaluationResult v2: strategy selection and nanosecond latency tracking",
    )


def _build_evaluation_result_v3() -> Schema:
    """EvaluationResult v3: added cache hit and confidence score."""
    return Schema(
        name="EvaluationResult",
        version=3,
        fields=[
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("strategy", SchemaFieldType.STRING, tag=3, default="standard"),
            SchemaField("latency_ns", SchemaFieldType.INT64, tag=4, default=0),
            SchemaField("cache_hit", SchemaFieldType.BOOL, tag=5, default=False),
            SchemaField("confidence", SchemaFieldType.FLOAT64, tag=6, default=1.0),
        ],
        doc="EvaluationResult v3: cache observability and ML confidence scores",
    )


def build_evaluation_result_lineage() -> list[Schema]:
    """Return the complete EvaluationResult schema lineage (v1 -> v2 -> v3)."""
    return [
        _build_evaluation_result_v1(),
        _build_evaluation_result_v2(),
        _build_evaluation_result_v3(),
    ]


def bootstrap_registry(
    mode: CompatibilityMode = CompatibilityMode.BACKWARD,
) -> SchemaRegistry:
    """Create a registry pre-loaded with the EvaluationResult lineage.

    This is the standard bootstrap procedure for the FizzSchema subsystem.
    All three versions of EvaluationResult are registered in order,
    demonstrating backward-compatible schema evolution from the simplest
    (number, result) contract through to the full observability schema.
    """
    registry = SchemaRegistry(default_mode=mode)
    for schema in build_evaluation_result_lineage():
        registry.register(schema, force=True)
    return registry


# ============================================================
# Schema Dashboard
# ============================================================


class SchemaDashboard:
    """ASCII dashboard for the FizzSchema subsystem.

    Renders a comprehensive overview of schema inventory, version
    timelines, compatibility history, and consensus round summaries.
    The dashboard is designed for executive stakeholders who need
    real-time visibility into the schema governance pipeline.
    """

    @staticmethod
    def render(
        registry: SchemaRegistry,
        approver: Optional[ConsensusApprover] = None,
        planner: Optional[MigrationPlanner] = None,
        width: int = 60,
    ) -> str:
        """Render the FizzSchema ASCII dashboard.

        Args:
            registry: The schema registry to display.
            approver: Optional consensus approver for round history.
            planner: Optional migration planner (for migration summaries).
            width: Dashboard character width.

        Returns:
            Multi-line string with box-drawing characters.
        """
        lines: list[str] = []
        hr = "+" + "-" * (width - 2) + "+"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            truncated = text[: width - 4]
            return "| " + truncated.ljust(width - 4) + " |"

        # Title
        lines.append(hr)
        lines.append(center("FizzSchema - Schema Evolution Dashboard"))
        lines.append(hr)

        # Schema Inventory
        lines.append(center("Schema Inventory"))
        lines.append(hr)

        schemas = registry.get_all_schemas()
        if not schemas:
            lines.append(left("(no schemas registered)"))
        else:
            # Group by name
            by_name: dict[str, list[Schema]] = {}
            for s in schemas:
                by_name.setdefault(s.name, []).append(s)

            for name in sorted(by_name.keys()):
                versions = by_name[name]
                latest = versions[-1]
                lines.append(left(
                    f"{name}: {len(versions)} version(s), "
                    f"latest=v{latest.version}, "
                    f"{len(latest.fields)} field(s)"
                ))
                lines.append(left(
                    f"  fingerprint: {latest.fingerprint[:32]}..."
                ))
                mode = registry.get_compatibility_mode(name)
                lines.append(left(f"  compatibility: {mode.value}"))

        lines.append(hr)

        # Version Timeline
        lines.append(center("Version Timeline"))
        lines.append(hr)

        for s in schemas:
            field_names = ", ".join(f.name for f in s.fields)
            if len(field_names) > width - 20:
                field_names = field_names[: width - 23] + "..."
            lines.append(left(f"v{s.version} [{s.name}]: {field_names}"))

        if not schemas:
            lines.append(left("(no versions)"))

        lines.append(hr)

        # Compatibility History
        lines.append(center("Compatibility History"))
        lines.append(hr)

        history = registry.history
        if not history:
            lines.append(left("(no compatibility checks recorded)"))
        else:
            for entry in history[-10:]:  # Last 10 entries
                status = "PASS" if entry["compatible"] else "FAIL"
                lines.append(left(
                    f"{entry['schema_name']} v{entry['from_version']}->"
                    f"v{entry['to_version']} [{entry['mode']}]: {status}"
                ))
                if entry["violations"]:
                    for v in entry["violations"][:2]:
                        truncated = v[:width - 10]
                        lines.append(left(f"    ! {truncated}"))
                if entry["warnings"]:
                    for w in entry["warnings"][:2]:
                        truncated = w[:width - 10]
                        lines.append(left(f"    ~ {truncated}"))

        lines.append(hr)

        # Consensus Rounds
        if approver is not None:
            lines.append(center("Consensus Rounds"))
            lines.append(hr)

            rounds = approver.rounds
            if not rounds:
                lines.append(left("(no consensus rounds)"))
            else:
                for r in rounds[-5:]:  # Last 5 rounds
                    status = "APPROVED" if r.approved else "REJECTED"
                    lines.append(left(
                        f"Round {r.round_id}: {r.schema_name} v{r.version} "
                        f"[{status}] {r.approvals}A/{r.rejections}R/{r.failures}F "
                        f"({r.duration_ms:.1f}ms)"
                    ))

            lines.append(hr)

        # Footer
        lines.append(center(f"Registered: {len(schemas)} schema(s)"))
        lines.append(hr)

        return "\n".join(lines)


# ============================================================
# Schema Middleware
# ============================================================


class SchemaMiddleware(IMiddleware):
    """Attaches schema version metadata to the evaluation context.

    When installed in the middleware pipeline, this middleware stamps
    every ProcessingContext with the active EvaluationResult schema
    version and fingerprint, enabling downstream consumers to
    identify the exact data contract under which the result was
    produced. This is essential for schema-aware deserialization
    and audit trail compliance.
    """

    def __init__(self, registry: SchemaRegistry, schema_name: str = "EvaluationResult") -> None:
        self._registry = registry
        self._schema_name = schema_name

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Attach schema metadata to the processing context."""
        schema = self._registry.get(self._schema_name)
        if schema is not None:
            context.metadata["schema_name"] = schema.name
            context.metadata["schema_version"] = schema.version
            context.metadata["schema_fingerprint"] = schema.fingerprint
        return next_handler(context)

    def get_name(self) -> str:
        return "SchemaMiddleware"

    def get_priority(self) -> int:
        return 950  # High priority — stamp schema version early
