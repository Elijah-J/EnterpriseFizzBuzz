"""
Enterprise FizzBuzz Platform - Live Process Migration with Checkpoint/Restore

Implements full live process migration for the FizzBuzz evaluation pipeline,
supporting pre-copy, post-copy, and stop-and-copy strategies. In production
distributed systems, live migration enables zero-downtime maintenance by
transferring running process state between hosts. The Enterprise FizzBuzz
Platform requires the same capability: a FizzBuzz process evaluating numbers
1 through 100 must be migratable mid-computation to ensure continuous
availability of modular arithmetic services.

Key features:
- CheckpointImage: JSON-serialized snapshot with SHA-256 integrity
- Pre-copy migration: iterative dirty-page transfer to minimize cutover time
- Post-copy migration: immediate cutover with demand-fault state resolution
- Stop-and-copy: traditional freeze-transfer-resume for maximum consistency
- MigrationValidator: pre/post comparison to verify migration correctness
- MigrationDashboard: real-time ASCII visualization of transfer progress
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class MigrationStrategy(Enum):
    """Strategy for transferring process state between source and destination.

    PRE_COPY: Iterative dirty-page transfer. Each round copies pages that
        were modified since the last round. Converges when the dirty rate
        drops below the transfer rate. Minimizes downtime at the cost of
        total migration time and bandwidth.
    POST_COPY: Immediate cutover after transferring minimal bootstrap state.
        Remaining state is demand-faulted on access. Minimizes total migration
        time but risks page-fault storms if the working set is large.
    STOP_AND_COPY: Classic freeze-transfer-resume. The process is stopped,
        all state is transferred, and the process is resumed at the
        destination. Maximum consistency, maximum downtime.
    """
    PRE_COPY = "pre-copy"
    POST_COPY = "post-copy"
    STOP_AND_COPY = "stop-and-copy"


class MigrationPhase(Enum):
    """Phases of the migration lifecycle."""
    IDLE = auto()
    INITIALIZING = auto()
    PRE_COPY_ITERATING = auto()
    PRE_COPY_CONVERGING = auto()
    FREEZE = auto()
    FINAL_TRANSFER = auto()
    POST_COPY_FAULTING = auto()
    RESTORING = auto()
    VALIDATING = auto()
    COMPLETE = auto()
    FAILED = auto()


class PageState(Enum):
    """State of a memory page in the dirty-page tracker."""
    CLEAN = auto()
    DIRTY = auto()
    TRANSFERRED = auto()
    FAULTED = auto()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SubsystemState:
    """Captured state of a single subsystem at checkpoint time.

    Each subsystem in the Enterprise FizzBuzz Platform maintains runtime
    state that must be captured, serialized, transferred, and restored
    for a successful live migration. This includes cache entries, circuit
    breaker states, configuration snapshots, accumulated metrics, and
    event history.
    """
    name: str
    state_data: dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0
    capture_time_ns: int = 0
    dirty: bool = False
    page_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    version: int = 0

    def mark_dirty(self) -> None:
        """Mark this subsystem's state as modified since last transfer."""
        self.dirty = True
        self.version += 1

    def mark_clean(self) -> None:
        """Mark this subsystem's state as synchronized with destination."""
        self.dirty = False

    def serialize(self) -> str:
        """Serialize the subsystem state to JSON."""
        payload = {
            "name": self.name,
            "state_data": self.state_data,
            "size_bytes": self.size_bytes,
            "capture_time_ns": self.capture_time_ns,
            "page_id": self.page_id,
            "version": self.version,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        self.size_bytes = len(serialized.encode("utf-8"))
        return serialized

    @classmethod
    def deserialize(cls, data: str) -> SubsystemState:
        """Reconstruct a SubsystemState from its JSON representation."""
        parsed = json.loads(data)
        state = cls(
            name=parsed["name"],
            state_data=parsed["state_data"],
            size_bytes=parsed["size_bytes"],
            capture_time_ns=parsed["capture_time_ns"],
            page_id=parsed["page_id"],
            version=parsed["version"],
        )
        return state


@dataclass
class DirtyPageEntry:
    """Tracks the dirty state of a memory page across migration rounds."""
    page_id: str
    subsystem_name: str
    dirty_count: int = 0
    last_modified_ns: int = 0
    transferred: bool = False
    state: PageState = PageState.CLEAN
    size_bytes: int = 0


@dataclass
class TransferRound:
    """Record of a single pre-copy transfer round."""
    round_number: int
    pages_transferred: int = 0
    bytes_transferred: int = 0
    dirty_pages_remaining: int = 0
    duration_ns: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def throughput_mbps(self) -> float:
        """Effective throughput in MB/s for this round."""
        if self.duration_ns <= 0:
            return 0.0
        seconds = self.duration_ns / 1_000_000_000
        megabytes = self.bytes_transferred / (1024 * 1024)
        return megabytes / seconds if seconds > 0 else 0.0


@dataclass
class MigrationMetrics:
    """Comprehensive metrics for the migration operation."""
    migration_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    strategy: str = ""
    phase: MigrationPhase = MigrationPhase.IDLE
    total_state_bytes: int = 0
    transferred_bytes: int = 0
    transfer_rounds: list[TransferRound] = field(default_factory=list)
    dirty_page_count: int = 0
    total_page_count: int = 0
    freeze_start_ns: int = 0
    freeze_end_ns: int = 0
    migration_start_ns: int = 0
    migration_end_ns: int = 0
    demand_faults: int = 0
    validation_passed: bool = False
    validation_errors: list[str] = field(default_factory=list)
    subsystem_count: int = 0

    @property
    def downtime_ms(self) -> float:
        """Compute the frozen (downtime) duration in milliseconds."""
        if self.freeze_start_ns and self.freeze_end_ns:
            return (self.freeze_end_ns - self.freeze_start_ns) / 1_000_000
        return 0.0

    @property
    def total_time_ms(self) -> float:
        """Total migration wall clock time in milliseconds."""
        if self.migration_start_ns is not None and self.migration_end_ns is not None and self.migration_end_ns > 0:
            return (self.migration_end_ns - self.migration_start_ns) / 1_000_000
        return 0.0

    @property
    def transfer_progress(self) -> float:
        """Fraction of state transferred (0.0 to 1.0)."""
        if self.total_state_bytes <= 0:
            return 1.0
        return min(1.0, self.transferred_bytes / self.total_state_bytes)


@dataclass
class CheckpointImage:
    """Serialized snapshot of all subsystem state with SHA-256 integrity.

    The checkpoint image is the fundamental unit of state transfer in the
    migration protocol. It contains a complete or partial snapshot of
    every active subsystem in the Enterprise FizzBuzz Platform, along with
    metadata required for validation and integrity verification.

    Integrity is enforced via SHA-256: the hash is computed over the
    concatenation of all serialized subsystem states, ensuring that any
    corruption during transfer is detectable.
    """
    image_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    subsystem_states: dict[str, SubsystemState] = field(default_factory=dict)
    integrity_hash: str = ""
    version: int = 1
    source_host: str = "fizzbuzz-primary-0"
    destination_host: str = "fizzbuzz-secondary-0"
    is_partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_integrity_hash(self) -> str:
        """Compute the SHA-256 hash over all subsystem state data.

        The hash is computed over the state_data dictionaries only,
        excluding mutable bookkeeping fields like size_bytes to ensure
        deterministic results across repeated invocations.
        """
        hasher = hashlib.sha256()
        for name in sorted(self.subsystem_states.keys()):
            state = self.subsystem_states[name]
            # Hash only the immutable state payload, not bookkeeping fields
            payload = json.dumps(
                {"name": state.name, "state_data": state.state_data},
                sort_keys=True,
                default=str,
            )
            hasher.update(payload.encode("utf-8"))
        self.integrity_hash = hasher.hexdigest()
        return self.integrity_hash

    def verify_integrity(self) -> bool:
        """Verify the checkpoint image has not been corrupted."""
        if not self.integrity_hash:
            return True
        stored = self.integrity_hash
        recomputed = self.compute_integrity_hash()
        return stored == recomputed

    @property
    def total_size_bytes(self) -> int:
        """Total size of all subsystem states in bytes."""
        total = 0
        for state in self.subsystem_states.values():
            state.serialize()  # Ensure size is up to date
            total += state.size_bytes
        return total

    @property
    def subsystem_count(self) -> int:
        return len(self.subsystem_states)

    def to_json(self) -> str:
        """Serialize the entire checkpoint image to JSON."""
        self.compute_integrity_hash()
        payload = {
            "image_id": self.image_id,
            "created_at": self.created_at,
            "version": self.version,
            "source_host": self.source_host,
            "destination_host": self.destination_host,
            "is_partial": self.is_partial,
            "integrity_hash": self.integrity_hash,
            "metadata": self.metadata,
            "subsystems": {},
        }
        for name, state in self.subsystem_states.items():
            payload["subsystems"][name] = {
                "name": state.name,
                "state_data": state.state_data,
                "size_bytes": state.size_bytes,
                "capture_time_ns": state.capture_time_ns,
                "page_id": state.page_id,
                "version": state.version,
            }
        return json.dumps(payload, sort_keys=True, indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> CheckpointImage:
        """Reconstruct a CheckpointImage from its JSON representation."""
        parsed = json.loads(data)
        image = cls(
            image_id=parsed["image_id"],
            created_at=parsed["created_at"],
            version=parsed["version"],
            source_host=parsed["source_host"],
            destination_host=parsed["destination_host"],
            is_partial=parsed.get("is_partial", False),
            integrity_hash=parsed["integrity_hash"],
            metadata=parsed.get("metadata", {}),
        )
        for name, sdata in parsed.get("subsystems", {}).items():
            image.subsystem_states[name] = SubsystemState(
                name=sdata["name"],
                state_data=sdata["state_data"],
                size_bytes=sdata["size_bytes"],
                capture_time_ns=sdata["capture_time_ns"],
                page_id=sdata["page_id"],
                version=sdata["version"],
            )
        return image


# ---------------------------------------------------------------------------
# StateCollector — gathers state from active subsystems
# ---------------------------------------------------------------------------

class StateCollector:
    """Gathers state from all active subsystems into a CheckpointImage.

    The StateCollector traverses the registered subsystem state providers,
    captures their current state, and assembles a coherent checkpoint image.
    State capture is designed to be non-blocking during pre-copy rounds and
    quiesced during the final freeze phase.
    """

    def __init__(self) -> None:
        self._providers: dict[str, Callable[[], dict[str, Any]]] = {}
        self._capture_count: int = 0

    def register_provider(
        self, name: str, provider: Callable[[], dict[str, Any]]
    ) -> None:
        """Register a state provider for a named subsystem."""
        self._providers[name] = provider
        logger.debug("Registered state provider: %s", name)

    def unregister_provider(self, name: str) -> None:
        """Remove a state provider."""
        self._providers.pop(name, None)

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    def capture(self, partial_names: Optional[list[str]] = None) -> CheckpointImage:
        """Capture the current state of all (or specified) subsystems.

        Args:
            partial_names: If provided, only capture these subsystems.
                Used during pre-copy rounds to capture only dirty pages.

        Returns:
            A CheckpointImage containing the captured state.
        """
        start_ns = time.perf_counter_ns()
        image = CheckpointImage()
        self._capture_count += 1

        targets = partial_names if partial_names else list(self._providers.keys())

        for name in targets:
            provider = self._providers.get(name)
            if provider is None:
                continue

            capture_start = time.perf_counter_ns()
            try:
                state_data = provider()
            except Exception as exc:
                logger.warning(
                    "Failed to capture state for subsystem '%s': %s", name, exc
                )
                state_data = {"error": str(exc), "partial": True}

            capture_ns = time.perf_counter_ns() - capture_start
            subsystem_state = SubsystemState(
                name=name,
                state_data=copy.deepcopy(state_data),
                capture_time_ns=capture_ns,
            )
            subsystem_state.serialize()  # Compute size
            image.subsystem_states[name] = subsystem_state

        if partial_names:
            image.is_partial = True

        image.metadata["capture_count"] = self._capture_count
        image.metadata["capture_duration_ns"] = time.perf_counter_ns() - start_ns
        image.compute_integrity_hash()

        logger.debug(
            "Captured checkpoint image %s: %d subsystems, %d bytes",
            image.image_id,
            image.subsystem_count,
            image.total_size_bytes,
        )
        return image

    def capture_dirty(
        self, dirty_tracker: DirtyPageTracker
    ) -> CheckpointImage:
        """Capture only subsystems with dirty pages."""
        dirty_names = dirty_tracker.get_dirty_subsystem_names()
        image = self.capture(partial_names=dirty_names)
        return image


# ---------------------------------------------------------------------------
# DirtyPageTracker
# ---------------------------------------------------------------------------

class DirtyPageTracker:
    """Tracks which subsystem state pages have been modified between rounds.

    In real VM live migration, the hypervisor uses hardware-assisted dirty
    page tracking (e.g., EPT dirty bits) to identify modified pages. Here,
    we track modifications at the subsystem level, which provides equivalent
    semantics for the FizzBuzz evaluation pipeline.
    """

    def __init__(self) -> None:
        self._pages: dict[str, DirtyPageEntry] = {}
        self._round_number: int = 0

    def register_page(self, page_id: str, subsystem_name: str, size_bytes: int = 0) -> None:
        """Register a new page for tracking."""
        self._pages[page_id] = DirtyPageEntry(
            page_id=page_id,
            subsystem_name=subsystem_name,
            size_bytes=size_bytes,
        )

    def mark_dirty(self, page_id: str) -> None:
        """Mark a page as dirty (modified since last transfer)."""
        entry = self._pages.get(page_id)
        if entry:
            entry.state = PageState.DIRTY
            entry.dirty_count += 1
            entry.last_modified_ns = time.perf_counter_ns()

    def mark_transferred(self, page_id: str) -> None:
        """Mark a page as transferred to the destination."""
        entry = self._pages.get(page_id)
        if entry:
            entry.state = PageState.TRANSFERRED
            entry.transferred = True

    def mark_faulted(self, page_id: str) -> None:
        """Mark a page as demand-faulted (post-copy)."""
        entry = self._pages.get(page_id)
        if entry:
            entry.state = PageState.FAULTED

    def get_dirty_pages(self) -> list[DirtyPageEntry]:
        """Return all pages currently marked dirty."""
        return [p for p in self._pages.values() if p.state == PageState.DIRTY]

    def get_dirty_subsystem_names(self) -> list[str]:
        """Return names of subsystems with dirty pages."""
        return list({p.subsystem_name for p in self.get_dirty_pages()})

    @property
    def dirty_count(self) -> int:
        return len(self.get_dirty_pages())

    @property
    def total_count(self) -> int:
        return len(self._pages)

    @property
    def dirty_ratio(self) -> float:
        """Fraction of pages that are dirty."""
        if self.total_count == 0:
            return 0.0
        return self.dirty_count / self.total_count

    def advance_round(self) -> None:
        """Advance to the next transfer round."""
        self._round_number += 1

    @property
    def round_number(self) -> int:
        return self._round_number

    def reset(self) -> None:
        """Reset all tracking state."""
        self._pages.clear()
        self._round_number = 0


# ---------------------------------------------------------------------------
# StateRestorer
# ---------------------------------------------------------------------------

class StateRestorer:
    """Applies a CheckpointImage to reinitialize subsystems at the destination.

    The StateRestorer is the mirror of the StateCollector: where the collector
    captures state, the restorer applies it. Each registered restore handler
    receives the state data and is responsible for reinitializing its
    subsystem to match the checkpoint.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict[str, Any]], None]] = {}
        self._restore_count: int = 0
        self._last_restore_duration_ns: int = 0
        self._demand_fault_handlers: dict[str, Callable[[str], dict[str, Any]]] = {}
        self._pending_faults: dict[str, SubsystemState] = {}

    def register_handler(
        self, name: str, handler: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a state restore handler for a named subsystem."""
        self._handlers[name] = handler

    def register_demand_fault_handler(
        self, name: str, handler: Callable[[str], dict[str, Any]]
    ) -> None:
        """Register a handler for demand-fault state resolution (post-copy)."""
        self._demand_fault_handlers[name] = handler

    def restore(self, image: CheckpointImage) -> list[str]:
        """Apply a checkpoint image to restore subsystem state.

        Returns:
            List of subsystem names that were successfully restored.
        """
        start_ns = time.perf_counter_ns()
        self._restore_count += 1
        restored: list[str] = []
        errors: list[str] = []

        # Verify integrity before restoring
        if image.integrity_hash:
            original_hash = image.integrity_hash
            image.compute_integrity_hash()
            if image.integrity_hash != original_hash:
                raise MigrationIntegrityError(
                    image.image_id,
                    expected=original_hash,
                    actual=image.integrity_hash,
                )

        for name, state in image.subsystem_states.items():
            handler = self._handlers.get(name)
            if handler is None:
                logger.debug("No restore handler for subsystem '%s', skipping", name)
                continue

            try:
                handler(state.state_data)
                restored.append(name)
                logger.debug("Restored subsystem '%s' (v%d)", name, state.version)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                logger.warning("Failed to restore subsystem '%s': %s", name, exc)

        self._last_restore_duration_ns = time.perf_counter_ns() - start_ns

        if errors:
            logger.warning(
                "Restore completed with %d errors: %s",
                len(errors),
                "; ".join(errors),
            )

        return restored

    def demand_fault(self, subsystem_name: str) -> Optional[dict[str, Any]]:
        """Resolve a demand fault for a subsystem not yet transferred.

        In post-copy migration, the destination may access state that hasn't
        been transferred yet. This triggers a demand fault, which fetches
        the required state from the source on demand.
        """
        handler = self._demand_fault_handlers.get(subsystem_name)
        if handler:
            try:
                return handler(subsystem_name)
            except Exception as exc:
                logger.warning(
                    "Demand fault for '%s' failed: %s", subsystem_name, exc
                )
        return None

    @property
    def restore_count(self) -> int:
        return self._restore_count

    @property
    def last_restore_duration_ns(self) -> int:
        return self._last_restore_duration_ns


# ---------------------------------------------------------------------------
# Migration Exceptions
# ---------------------------------------------------------------------------

class MigrationError(Exception):
    """Base exception for process migration failures."""

    def __init__(self, message: str, *, migration_id: Optional[str] = None) -> None:
        self.migration_id = migration_id
        super().__init__(f"[MIGRATION] {message}")


class MigrationIntegrityError(MigrationError):
    """Raised when a checkpoint image fails integrity verification."""

    def __init__(self, image_id: str, expected: str, actual: str) -> None:
        self.image_id = image_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Integrity check failed for image {image_id}: "
            f"expected {expected[:16]}..., got {actual[:16]}..."
        )


class MigrationConvergenceError(MigrationError):
    """Raised when pre-copy migration fails to converge."""

    def __init__(self, rounds: int, dirty_ratio: float) -> None:
        self.rounds = rounds
        self.dirty_ratio = dirty_ratio
        super().__init__(
            f"Pre-copy failed to converge after {rounds} rounds "
            f"(dirty ratio: {dirty_ratio:.2%})"
        )


class MigrationValidationError(MigrationError):
    """Raised when post-migration validation detects state divergence."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(
            f"Validation failed with {len(errors)} error(s): "
            + "; ".join(errors[:5])
        )


class DemandFaultError(MigrationError):
    """Raised when a demand fault cannot be resolved during post-copy."""

    def __init__(self, subsystem_name: str) -> None:
        self.subsystem_name = subsystem_name
        super().__init__(
            f"Demand fault for subsystem '{subsystem_name}' could not be resolved"
        )


# ---------------------------------------------------------------------------
# PreCopyMigrator
# ---------------------------------------------------------------------------

class PreCopyMigrator:
    """Implements iterative pre-copy migration strategy.

    Pre-copy migration works by iteratively transferring dirty pages from
    source to destination. In each round, all pages modified since the last
    round are transferred. The process converges when the dirty rate drops
    below the transfer rate, at which point a brief freeze is initiated
    for the final delta transfer.

    Configuration:
        max_rounds: Maximum number of pre-copy rounds before giving up.
        convergence_threshold: Dirty ratio below which we proceed to cutover.
        dirty_rate_decay: Simulated decay of dirty rate per round.
    """

    def __init__(
        self,
        collector: StateCollector,
        restorer: StateRestorer,
        *,
        max_rounds: int = 10,
        convergence_threshold: float = 0.1,
        dirty_rate_decay: float = 0.5,
    ) -> None:
        self._collector = collector
        self._restorer = restorer
        self._max_rounds = max_rounds
        self._convergence_threshold = convergence_threshold
        self._dirty_rate_decay = dirty_rate_decay
        self._tracker = DirtyPageTracker()
        self._metrics = MigrationMetrics(strategy=MigrationStrategy.PRE_COPY.value)

    @property
    def metrics(self) -> MigrationMetrics:
        return self._metrics

    @property
    def tracker(self) -> DirtyPageTracker:
        return self._tracker

    def migrate(self) -> CheckpointImage:
        """Execute the full pre-copy migration sequence.

        Returns:
            The final CheckpointImage used for the cutover.
        """
        self._metrics.migration_start_ns = time.perf_counter_ns()
        self._metrics.phase = MigrationPhase.INITIALIZING

        # Phase 1: Initial full capture
        logger.info("Pre-copy migration: initial capture")
        initial_image = self._collector.capture()
        self._metrics.total_state_bytes = initial_image.total_size_bytes
        self._metrics.subsystem_count = initial_image.subsystem_count

        # Initialize dirty page tracker with all subsystem pages
        for name, state in initial_image.subsystem_states.items():
            self._tracker.register_page(
                state.page_id, name, size_bytes=state.size_bytes
            )
            self._tracker.mark_dirty(state.page_id)

        self._metrics.total_page_count = self._tracker.total_count

        # Transfer initial image
        restored = self._restorer.restore(initial_image)
        initial_bytes = initial_image.total_size_bytes
        self._metrics.transferred_bytes += initial_bytes
        self._metrics.transfer_rounds.append(TransferRound(
            round_number=0,
            pages_transferred=len(restored),
            bytes_transferred=initial_bytes,
            dirty_pages_remaining=self._tracker.dirty_count,
            duration_ns=time.perf_counter_ns() - self._metrics.migration_start_ns,
        ))

        # Mark all pages clean after initial transfer
        for state in initial_image.subsystem_states.values():
            self._tracker.mark_transferred(state.page_id)

        # Phase 2: Iterative dirty page transfer
        self._metrics.phase = MigrationPhase.PRE_COPY_ITERATING
        dirty_ratio = 1.0

        for round_num in range(1, self._max_rounds + 1):
            self._tracker.advance_round()
            round_start = time.perf_counter_ns()

            # Simulate dirty pages being generated during transfer
            # In a real system, the hypervisor would track actual writes
            dirty_ratio *= self._dirty_rate_decay
            num_dirty = int(self._tracker.total_count * dirty_ratio)

            # Mark a fraction of pages dirty (simulating ongoing writes)
            pages = list(self._tracker._pages.values())
            for i, page in enumerate(pages):
                if i < num_dirty:
                    page.state = PageState.DIRTY
                else:
                    page.state = PageState.TRANSFERRED

            self._metrics.dirty_page_count = self._tracker.dirty_count

            if self._tracker.dirty_ratio <= self._convergence_threshold:
                self._metrics.phase = MigrationPhase.PRE_COPY_CONVERGING
                logger.info(
                    "Pre-copy converged at round %d (dirty ratio: %.2f%%)",
                    round_num,
                    self._tracker.dirty_ratio * 100,
                )

            # Transfer dirty pages
            dirty_image = self._collector.capture_dirty(self._tracker)
            if dirty_image.subsystem_count > 0:
                self._restorer.restore(dirty_image)
                round_bytes = dirty_image.total_size_bytes
                self._metrics.transferred_bytes += round_bytes
            else:
                round_bytes = 0

            round_duration = time.perf_counter_ns() - round_start
            self._metrics.transfer_rounds.append(TransferRound(
                round_number=round_num,
                pages_transferred=dirty_image.subsystem_count,
                bytes_transferred=round_bytes,
                dirty_pages_remaining=self._tracker.dirty_count,
                duration_ns=round_duration,
            ))

            # Mark transferred pages clean
            for state in dirty_image.subsystem_states.values():
                self._tracker.mark_transferred(state.page_id)

            if self._tracker.dirty_ratio <= self._convergence_threshold:
                break
        else:
            if self._tracker.dirty_ratio > self._convergence_threshold:
                self._metrics.phase = MigrationPhase.FAILED
                raise MigrationConvergenceError(
                    self._max_rounds, self._tracker.dirty_ratio
                )

        # Phase 3: Final freeze and copy
        self._metrics.phase = MigrationPhase.FREEZE
        self._metrics.freeze_start_ns = time.perf_counter_ns()
        logger.info("Pre-copy migration: freeze and final transfer")

        final_image = self._collector.capture()
        self._metrics.phase = MigrationPhase.FINAL_TRANSFER
        self._restorer.restore(final_image)
        self._metrics.transferred_bytes += final_image.total_size_bytes

        self._metrics.freeze_end_ns = time.perf_counter_ns()
        self._metrics.phase = MigrationPhase.COMPLETE
        self._metrics.migration_end_ns = time.perf_counter_ns()

        logger.info(
            "Pre-copy migration complete: %d rounds, %.2fms downtime, %.2fms total",
            len(self._metrics.transfer_rounds),
            self._metrics.downtime_ms,
            self._metrics.total_time_ms,
        )

        return final_image


# ---------------------------------------------------------------------------
# PostCopyMigrator
# ---------------------------------------------------------------------------

class PostCopyMigrator:
    """Implements post-copy migration strategy with demand faulting.

    Post-copy migration freezes the source immediately, transfers only
    the minimal bootstrap state (configuration, active evaluations),
    and resumes execution at the destination. Any state not yet transferred
    is fetched on demand via page faults, similar to how an OS handles
    lazy memory mapping.

    This strategy minimizes downtime at the risk of increased latency
    during the initial warm-up period as demand faults are resolved.
    """

    def __init__(
        self,
        collector: StateCollector,
        restorer: StateRestorer,
        *,
        bootstrap_subsystems: Optional[list[str]] = None,
    ) -> None:
        self._collector = collector
        self._restorer = restorer
        self._bootstrap_subsystems = bootstrap_subsystems or [
            "configuration", "evaluation_state", "rule_engine"
        ]
        self._tracker = DirtyPageTracker()
        self._metrics = MigrationMetrics(strategy=MigrationStrategy.POST_COPY.value)
        self._source_image: Optional[CheckpointImage] = None
        self._faulted_subsystems: set[str] = set()

    @property
    def metrics(self) -> MigrationMetrics:
        return self._metrics

    @property
    def tracker(self) -> DirtyPageTracker:
        return self._tracker

    def migrate(self) -> CheckpointImage:
        """Execute the post-copy migration sequence.

        Returns:
            The bootstrap CheckpointImage. Remaining state is demand-faulted.
        """
        self._metrics.migration_start_ns = time.perf_counter_ns()
        self._metrics.phase = MigrationPhase.INITIALIZING

        # Capture full state for demand-fault resolution
        self._source_image = self._collector.capture()
        self._metrics.total_state_bytes = self._source_image.total_size_bytes
        self._metrics.subsystem_count = self._source_image.subsystem_count

        # Initialize page tracker
        for name, state in self._source_image.subsystem_states.items():
            self._tracker.register_page(
                state.page_id, name, size_bytes=state.size_bytes
            )
            self._tracker.mark_dirty(state.page_id)

        self._metrics.total_page_count = self._tracker.total_count

        # Immediate freeze
        self._metrics.phase = MigrationPhase.FREEZE
        self._metrics.freeze_start_ns = time.perf_counter_ns()

        # Transfer only bootstrap state
        bootstrap_image = self._collector.capture(
            partial_names=self._bootstrap_subsystems
        )
        self._restorer.restore(bootstrap_image)

        bootstrap_bytes = bootstrap_image.total_size_bytes
        self._metrics.transferred_bytes += bootstrap_bytes
        self._metrics.transfer_rounds.append(TransferRound(
            round_number=0,
            pages_transferred=bootstrap_image.subsystem_count,
            bytes_transferred=bootstrap_bytes,
            dirty_pages_remaining=self._tracker.dirty_count,
            duration_ns=time.perf_counter_ns() - self._metrics.freeze_start_ns,
        ))

        # Mark bootstrap pages as transferred
        for state in bootstrap_image.subsystem_states.values():
            if state.page_id in self._tracker._pages:
                self._tracker.mark_transferred(state.page_id)

        self._metrics.freeze_end_ns = time.perf_counter_ns()
        self._metrics.phase = MigrationPhase.POST_COPY_FAULTING

        # Simulate demand faults for remaining subsystems
        remaining = [
            name for name in self._source_image.subsystem_states
            if name not in self._bootstrap_subsystems
        ]

        for name in remaining:
            self._resolve_demand_fault(name)

        self._metrics.phase = MigrationPhase.COMPLETE
        self._metrics.migration_end_ns = time.perf_counter_ns()

        logger.info(
            "Post-copy migration complete: %.2fms downtime, %d demand faults, %.2fms total",
            self._metrics.downtime_ms,
            self._metrics.demand_faults,
            self._metrics.total_time_ms,
        )

        return self._source_image

    def _resolve_demand_fault(self, subsystem_name: str) -> None:
        """Resolve a demand fault by fetching state from the source image."""
        self._metrics.demand_faults += 1
        self._faulted_subsystems.add(subsystem_name)

        if self._source_image and subsystem_name in self._source_image.subsystem_states:
            state = self._source_image.subsystem_states[subsystem_name]

            # Transfer the faulted page
            fault_image = CheckpointImage(is_partial=True)
            fault_image.subsystem_states[subsystem_name] = state
            self._restorer.restore(fault_image)

            fault_bytes = state.size_bytes
            self._metrics.transferred_bytes += fault_bytes

            # Mark page as faulted (resolved)
            if state.page_id in self._tracker._pages:
                self._tracker.mark_faulted(state.page_id)

            logger.debug(
                "Demand fault resolved for '%s' (%d bytes)",
                subsystem_name,
                fault_bytes,
            )
        else:
            logger.warning(
                "Demand fault for '%s' could not be resolved: not in source image",
                subsystem_name,
            )

    @property
    def demand_fault_count(self) -> int:
        return self._metrics.demand_faults


# ---------------------------------------------------------------------------
# StopAndCopyMigrator
# ---------------------------------------------------------------------------

class StopAndCopyMigrator:
    """Implements traditional stop-and-copy migration.

    The simplest migration strategy: freeze the process, transfer all state,
    resume at the destination. Maximum consistency, maximum downtime. For a
    FizzBuzz process that runs for less than a second, the downtime is
    arguably negligible, but the protocol must be implemented correctly
    regardless of the computational workload.
    """

    def __init__(
        self,
        collector: StateCollector,
        restorer: StateRestorer,
    ) -> None:
        self._collector = collector
        self._restorer = restorer
        self._tracker = DirtyPageTracker()
        self._metrics = MigrationMetrics(
            strategy=MigrationStrategy.STOP_AND_COPY.value
        )

    @property
    def metrics(self) -> MigrationMetrics:
        return self._metrics

    @property
    def tracker(self) -> DirtyPageTracker:
        return self._tracker

    def migrate(self) -> CheckpointImage:
        """Execute the stop-and-copy migration."""
        self._metrics.migration_start_ns = time.perf_counter_ns()
        self._metrics.phase = MigrationPhase.FREEZE
        self._metrics.freeze_start_ns = time.perf_counter_ns()

        # Capture all state
        image = self._collector.capture()
        self._metrics.total_state_bytes = image.total_size_bytes
        self._metrics.subsystem_count = image.subsystem_count

        # Initialize tracker
        for name, state in image.subsystem_states.items():
            self._tracker.register_page(
                state.page_id, name, size_bytes=state.size_bytes
            )

        self._metrics.total_page_count = self._tracker.total_count

        # Transfer
        self._metrics.phase = MigrationPhase.FINAL_TRANSFER
        restored = self._restorer.restore(image)
        transfer_bytes = image.total_size_bytes
        self._metrics.transferred_bytes = transfer_bytes

        self._metrics.transfer_rounds.append(TransferRound(
            round_number=0,
            pages_transferred=len(restored),
            bytes_transferred=transfer_bytes,
            dirty_pages_remaining=0,
            duration_ns=time.perf_counter_ns() - self._metrics.freeze_start_ns,
        ))

        self._metrics.freeze_end_ns = time.perf_counter_ns()
        self._metrics.phase = MigrationPhase.COMPLETE
        self._metrics.migration_end_ns = time.perf_counter_ns()

        logger.info(
            "Stop-and-copy migration complete: %.2fms total (all downtime)",
            self._metrics.total_time_ms,
        )

        return image


# ---------------------------------------------------------------------------
# MigrationValidator
# ---------------------------------------------------------------------------

class MigrationValidator:
    """Compares pre- and post-migration state for correctness.

    After migration, the validator runs the same evaluation range on the
    restored state and compares results against the pre-migration baseline.
    Any divergence indicates a migration defect, which in a production
    system would trigger an automatic rollback.
    """

    def __init__(self) -> None:
        self._validation_count: int = 0
        self._last_errors: list[str] = []

    def validate_checkpoint(
        self,
        source_image: CheckpointImage,
        destination_image: CheckpointImage,
    ) -> tuple[bool, list[str]]:
        """Validate that source and destination images are equivalent.

        Returns:
            Tuple of (passed, list of error messages).
        """
        self._validation_count += 1
        errors: list[str] = []

        # Check subsystem count
        src_count = source_image.subsystem_count
        dst_count = destination_image.subsystem_count
        if src_count != dst_count:
            errors.append(
                f"Subsystem count mismatch: source={src_count}, dest={dst_count}"
            )

        # Check each subsystem state
        for name in source_image.subsystem_states:
            src_state = source_image.subsystem_states[name]
            dst_state = destination_image.subsystem_states.get(name)

            if dst_state is None:
                errors.append(f"Subsystem '{name}' missing from destination")
                continue

            # Compare state data
            if src_state.state_data != dst_state.state_data:
                errors.append(
                    f"Subsystem '{name}' state divergence detected "
                    f"(source v{src_state.version} vs dest v{dst_state.version})"
                )

        # Check for extra subsystems in destination
        for name in destination_image.subsystem_states:
            if name not in source_image.subsystem_states:
                errors.append(
                    f"Unexpected subsystem '{name}' in destination image"
                )

        # Verify integrity hashes
        source_image.compute_integrity_hash()
        destination_image.compute_integrity_hash()
        if source_image.integrity_hash != destination_image.integrity_hash:
            errors.append(
                f"Integrity hash mismatch: "
                f"source={source_image.integrity_hash[:16]}..., "
                f"dest={destination_image.integrity_hash[:16]}..."
            )

        self._last_errors = errors
        passed = len(errors) == 0

        if passed:
            logger.info("Migration validation PASSED")
        else:
            logger.warning(
                "Migration validation FAILED with %d error(s)", len(errors)
            )

        return passed, errors

    def validate_evaluation_results(
        self,
        pre_results: list[tuple[int, str]],
        post_results: list[tuple[int, str]],
    ) -> tuple[bool, list[str]]:
        """Validate that evaluation results match before and after migration.

        Args:
            pre_results: List of (number, output) pairs from pre-migration.
            post_results: List of (number, output) pairs from post-migration.

        Returns:
            Tuple of (passed, list of error messages).
        """
        self._validation_count += 1
        errors: list[str] = []

        if len(pre_results) != len(post_results):
            errors.append(
                f"Result count mismatch: pre={len(pre_results)}, "
                f"post={len(post_results)}"
            )
            self._last_errors = errors
            return False, errors

        for i, (pre, post) in enumerate(zip(pre_results, post_results)):
            pre_num, pre_out = pre
            post_num, post_out = post

            if pre_num != post_num:
                errors.append(
                    f"Number mismatch at index {i}: pre={pre_num}, post={post_num}"
                )
            elif pre_out != post_out:
                errors.append(
                    f"Output mismatch for number {pre_num}: "
                    f"pre='{pre_out}', post='{post_out}'"
                )

        self._last_errors = errors
        passed = len(errors) == 0
        return passed, errors

    @property
    def validation_count(self) -> int:
        return self._validation_count

    @property
    def last_errors(self) -> list[str]:
        return self._last_errors


# ---------------------------------------------------------------------------
# MigrationOrchestrator
# ---------------------------------------------------------------------------

class MigrationOrchestrator:
    """Orchestrates the complete migration lifecycle.

    Coordinates the state collector, chosen migration strategy, state
    restorer, and validation to execute a complete live migration of the
    FizzBuzz evaluation process.
    """

    def __init__(
        self,
        strategy: MigrationStrategy = MigrationStrategy.PRE_COPY,
        *,
        checkpoint_file: Optional[str] = None,
        max_rounds: int = 10,
        convergence_threshold: float = 0.1,
        dirty_rate_decay: float = 0.5,
        bootstrap_subsystems: Optional[list[str]] = None,
    ) -> None:
        self._strategy = strategy
        self._checkpoint_file = checkpoint_file
        self._collector = StateCollector()
        self._restorer = StateRestorer()
        self._validator = MigrationValidator()
        self._max_rounds = max_rounds
        self._convergence_threshold = convergence_threshold
        self._dirty_rate_decay = dirty_rate_decay
        self._bootstrap_subsystems = bootstrap_subsystems
        self._last_image: Optional[CheckpointImage] = None
        self._last_metrics: Optional[MigrationMetrics] = None

    @property
    def collector(self) -> StateCollector:
        return self._collector

    @property
    def restorer(self) -> StateRestorer:
        return self._restorer

    @property
    def validator(self) -> MigrationValidator:
        return self._validator

    @property
    def last_image(self) -> Optional[CheckpointImage]:
        return self._last_image

    @property
    def last_metrics(self) -> Optional[MigrationMetrics]:
        return self._last_metrics

    @property
    def strategy(self) -> MigrationStrategy:
        return self._strategy

    def register_subsystem(
        self,
        name: str,
        state_provider: Callable[[], dict[str, Any]],
        state_handler: Callable[[dict[str, Any]], None],
    ) -> None:
        """Register a subsystem for migration."""
        self._collector.register_provider(name, state_provider)
        self._restorer.register_handler(name, state_handler)

    def execute(self) -> CheckpointImage:
        """Execute the migration using the configured strategy."""
        logger.info(
            "Starting %s migration (checkpoint: %s)",
            self._strategy.value,
            self._checkpoint_file or "<memory>",
        )

        if self._strategy == MigrationStrategy.PRE_COPY:
            migrator = PreCopyMigrator(
                self._collector,
                self._restorer,
                max_rounds=self._max_rounds,
                convergence_threshold=self._convergence_threshold,
                dirty_rate_decay=self._dirty_rate_decay,
            )
        elif self._strategy == MigrationStrategy.POST_COPY:
            migrator = PostCopyMigrator(
                self._collector,
                self._restorer,
                bootstrap_subsystems=self._bootstrap_subsystems,
            )
        else:
            migrator = StopAndCopyMigrator(self._collector, self._restorer)

        image = migrator.migrate()
        self._last_image = image
        self._last_metrics = migrator.metrics

        # Save checkpoint to file if requested
        if self._checkpoint_file:
            self._save_checkpoint(image)

        # Validate
        self._last_metrics.phase = MigrationPhase.VALIDATING
        recaptured = self._collector.capture()
        passed, errors = self._validator.validate_checkpoint(image, recaptured)
        self._last_metrics.validation_passed = passed
        self._last_metrics.validation_errors = errors

        if not passed:
            logger.warning(
                "Migration validation failed: %s", "; ".join(errors[:3])
            )

        return image

    def _save_checkpoint(self, image: CheckpointImage) -> None:
        """Persist the checkpoint image to the filesystem."""
        try:
            json_data = image.to_json()
            with open(self._checkpoint_file, "w", encoding="utf-8") as f:
                f.write(json_data)
            logger.info(
                "Checkpoint saved to %s (%d bytes)",
                self._checkpoint_file,
                len(json_data),
            )
        except Exception as exc:
            logger.error("Failed to save checkpoint: %s", exc)

    @classmethod
    def load_checkpoint(cls, path: str) -> CheckpointImage:
        """Load a checkpoint image from disk."""
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
        image = CheckpointImage.from_json(data)

        # Verify integrity
        stored_hash = image.integrity_hash
        image.compute_integrity_hash()
        if image.integrity_hash != stored_hash:
            raise MigrationIntegrityError(
                image.image_id,
                expected=stored_hash,
                actual=image.integrity_hash,
            )

        logger.info(
            "Loaded checkpoint %s from %s (%d subsystems)",
            image.image_id,
            path,
            image.subsystem_count,
        )
        return image


# ---------------------------------------------------------------------------
# MigrationDashboard
# ---------------------------------------------------------------------------

class MigrationDashboard:
    """ASCII dashboard with transfer progress, dirty page tracking, and
    downtime measurement for the live migration subsystem."""

    @staticmethod
    def render(
        metrics: MigrationMetrics,
        *,
        width: int = 72,
    ) -> str:
        """Render the migration dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        title_text = " FIZZMIGRATE: LIVE PROCESS MIGRATION DASHBOARD "
        title_line = "+" + title_text.center(width - 2, "-") + "+"

        lines.append(title_line)
        lines.append(border)

        # Strategy and phase
        lines.append(_row("Strategy", metrics.strategy.upper(), width))
        lines.append(_row("Phase", metrics.phase.name, width))
        lines.append(_row("Migration ID", metrics.migration_id, width))
        lines.append(border)

        # Transfer progress
        lines.append(_section("TRANSFER PROGRESS", width))
        progress_pct = metrics.transfer_progress * 100
        bar_width = width - 22
        filled = int(bar_width * metrics.transfer_progress)
        bar = "[" + "#" * filled + "-" * (bar_width - filled) + "]"
        lines.append(_row("Progress", f"{bar} {progress_pct:.1f}%", width))
        lines.append(_row(
            "Transferred",
            _format_bytes(metrics.transferred_bytes),
            width,
        ))
        lines.append(_row(
            "Total State",
            _format_bytes(metrics.total_state_bytes),
            width,
        ))
        lines.append(_row("Subsystems", str(metrics.subsystem_count), width))
        lines.append(border)

        # Dirty page tracking
        lines.append(_section("DIRTY PAGE TRACKING", width))
        lines.append(_row("Total Pages", str(metrics.total_page_count), width))
        lines.append(_row("Dirty Pages", str(metrics.dirty_page_count), width))
        dirty_pct = (
            (metrics.dirty_page_count / metrics.total_page_count * 100)
            if metrics.total_page_count > 0
            else 0.0
        )
        lines.append(_row("Dirty Ratio", f"{dirty_pct:.1f}%", width))
        lines.append(border)

        # Transfer rounds
        if metrics.transfer_rounds:
            lines.append(_section("TRANSFER ROUNDS", width))
            header = f"  {'Round':>5s}  {'Pages':>6s}  {'Bytes':>10s}  {'Dirty':>6s}  {'Time':>10s}"
            lines.append(header)
            lines.append("  " + "-" * (width - 4))

            for tr in metrics.transfer_rounds:
                duration_str = _format_duration(tr.duration_ns)
                row = (
                    f"  {tr.round_number:>5d}  "
                    f"{tr.pages_transferred:>6d}  "
                    f"{_format_bytes(tr.bytes_transferred):>10s}  "
                    f"{tr.dirty_pages_remaining:>6d}  "
                    f"{duration_str:>10s}"
                )
                lines.append(row)
            lines.append(border)

        # Timing
        lines.append(_section("TIMING", width))
        lines.append(_row("Total Time", f"{metrics.total_time_ms:.2f}ms", width))
        lines.append(_row("Downtime", f"{metrics.downtime_ms:.2f}ms", width))
        if metrics.demand_faults > 0:
            lines.append(_row("Demand Faults", str(metrics.demand_faults), width))
        lines.append(border)

        # Validation
        lines.append(_section("VALIDATION", width))
        status = "PASSED" if metrics.validation_passed else "FAILED"
        lines.append(_row("Status", status, width))
        if metrics.validation_errors:
            for err in metrics.validation_errors[:5]:
                lines.append(f"  ! {err[:width - 6]}")
        lines.append(border)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# MigrationMiddleware
# ---------------------------------------------------------------------------

class MigrationMiddleware(IMiddleware):
    """Middleware that performs checkpoint capture after each evaluation batch.

    Integrates with the FizzBuzz evaluation pipeline to periodically capture
    process state, enabling live migration at any point during computation.
    Priority 995 ensures this runs near the end of the middleware chain,
    capturing the most complete state possible.
    """

    def __init__(
        self,
        orchestrator: MigrationOrchestrator,
        *,
        checkpoint_interval: int = 10,
        enable_dashboard: bool = False,
    ) -> None:
        self._orchestrator = orchestrator
        self._checkpoint_interval = checkpoint_interval
        self._enable_dashboard = enable_dashboard
        self._eval_count: int = 0
        self._checkpoints_taken: int = 0
        self._last_checkpoint_image: Optional[CheckpointImage] = None
        self._results_pre_migration: list[tuple[int, str]] = []

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a number through the pipeline with periodic checkpointing."""
        result = next_handler(context)

        self._eval_count += 1

        # Record result for post-migration validation
        if result.results:
            latest = result.results[-1]
            self._results_pre_migration.append(
                (latest.number, latest.output)
            )

        # Periodic checkpoint capture
        if self._eval_count % self._checkpoint_interval == 0:
            self._take_checkpoint()

        return result

    def _take_checkpoint(self) -> None:
        """Capture a checkpoint of current subsystem state."""
        try:
            image = self._orchestrator.collector.capture()
            self._last_checkpoint_image = image
            self._checkpoints_taken += 1
            logger.debug(
                "Checkpoint %d captured: %d subsystems, %d bytes",
                self._checkpoints_taken,
                image.subsystem_count,
                image.total_size_bytes,
            )
        except Exception as exc:
            logger.warning("Checkpoint capture failed: %s", exc)

    def get_name(self) -> str:
        return "MigrationMiddleware"

    def get_priority(self) -> int:
        return 995

    @property
    def eval_count(self) -> int:
        return self._eval_count

    @property
    def checkpoints_taken(self) -> int:
        return self._checkpoints_taken

    @property
    def last_checkpoint_image(self) -> Optional[CheckpointImage]:
        return self._last_checkpoint_image

    @property
    def results_pre_migration(self) -> list[tuple[int, str]]:
        return self._results_pre_migration


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _row(label: str, value: str, width: int) -> str:
    """Format a label-value row for the dashboard."""
    padding = width - 4 - len(label) - len(value)
    if padding < 1:
        padding = 1
    return f"  {label}{'.' * padding}{value}"


def _section(title: str, width: int) -> str:
    """Format a section header for the dashboard."""
    return f"  [{title}]"


def _format_bytes(b: int) -> str:
    """Format a byte count for display."""
    if b < 1024:
        return f"{b}B"
    elif b < 1024 * 1024:
        return f"{b / 1024:.1f}KB"
    else:
        return f"{b / (1024 * 1024):.2f}MB"


def _format_duration(ns: int) -> str:
    """Format a nanosecond duration for display."""
    if ns < 1_000:
        return f"{ns}ns"
    elif ns < 1_000_000:
        return f"{ns / 1_000:.1f}us"
    elif ns < 1_000_000_000:
        return f"{ns / 1_000_000:.2f}ms"
    else:
        return f"{ns / 1_000_000_000:.2f}s"


def create_migration_subsystem(
    strategy: MigrationStrategy = MigrationStrategy.PRE_COPY,
    *,
    checkpoint_file: Optional[str] = None,
    max_rounds: int = 10,
    convergence_threshold: float = 0.1,
    dirty_rate_decay: float = 0.5,
    checkpoint_interval: int = 10,
    enable_dashboard: bool = False,
) -> tuple[MigrationOrchestrator, MigrationMiddleware]:
    """Factory function to create the migration subsystem.

    Returns:
        Tuple of (orchestrator, middleware).
    """
    orchestrator = MigrationOrchestrator(
        strategy=strategy,
        checkpoint_file=checkpoint_file,
        max_rounds=max_rounds,
        convergence_threshold=convergence_threshold,
        dirty_rate_decay=dirty_rate_decay,
    )

    # Register default subsystem state providers
    _register_default_providers(orchestrator)

    middleware = MigrationMiddleware(
        orchestrator,
        checkpoint_interval=checkpoint_interval,
        enable_dashboard=enable_dashboard,
    )

    return orchestrator, middleware


def _register_default_providers(orchestrator: MigrationOrchestrator) -> None:
    """Register default subsystem state providers and handlers.

    Each subsystem provides a lambda that captures its current state as a
    dictionary. The corresponding handler accepts that dictionary to restore
    state. For subsystems that are not currently active, the provider returns
    an empty state.
    """
    default_subsystems = {
        "configuration": {
            "type": "singleton",
            "status": "active",
            "schema_version": 1,
        },
        "evaluation_state": {
            "type": "pipeline",
            "current_number": 0,
            "evaluations_completed": 0,
        },
        "rule_engine": {
            "type": "engine",
            "rules_loaded": 0,
            "strategy": "standard",
        },
        "cache": {
            "type": "mesi_coherent",
            "entries": 0,
            "hit_ratio": 0.0,
            "coherence_state": "MODIFIED",
        },
        "circuit_breaker": {
            "type": "registry",
            "circuits": {},
            "state": "CLOSED",
        },
        "metrics": {
            "type": "collector",
            "counters": {},
            "histograms": {},
        },
        "event_history": {
            "type": "event_bus",
            "events_published": 0,
            "subscribers": 0,
        },
        "middleware_pipeline": {
            "type": "pipeline",
            "middleware_count": 0,
            "invocations": 0,
        },
    }

    for name, default_state in default_subsystems.items():
        # Capture in closure
        state_copy = copy.deepcopy(default_state)
        orchestrator.register_subsystem(
            name,
            state_provider=lambda s=state_copy: copy.deepcopy(s),
            state_handler=lambda data, n=name: logger.debug(
                "Restored subsystem '%s': %s", n, list(data.keys())
            ),
        )
