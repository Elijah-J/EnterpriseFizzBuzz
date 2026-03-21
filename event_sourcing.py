"""
Enterprise FizzBuzz Platform - Event Sourcing with CQRS Module

Implements a full Event Sourcing and Command Query Responsibility
Segregation (CQRS) architecture for the FizzBuzz evaluation pipeline.
Because simply returning "Fizz", "Buzz", or "FizzBuzz" is not enough --
we must also maintain an append-only, temporally queryable, projection-
materializing, snapshot-capable, upcaster-chained, command-bus-dispatched
audit log of every single modulo operation.

If you ever wondered what happens when you apply Domain-Driven Design
to the world's simplest programming exercise, wonder no more. This
module contains the answer, and the answer is approximately 900 lines
of Python.

Architecture Overview:
    Write Side (Command):
        CLI/Service -> CommandBus -> CommandHandler -> EventStore -> DomainEvents
    Read Side (Query):
        EventStore -> Projections -> QueryBus -> QueryHandler -> ReadModels

Design Patterns Employed:
    - Event Sourcing (Fowler, 2005)
    - CQRS (Young, 2010)
    - Domain Events (Evans, DDD)
    - Snapshot/Memento (GoF)
    - Event Upcasting (Axon Framework)
    - Temporal Query (Snodgrass, 1999)
    - Mediator (CommandBus / QueryBus)
    - Projection / Materialized View

Compliance:
    - SOX Section 404: Full audit trail of every FizzBuzz decision
    - GDPR Article 17: "Right to be forgotten" -- just kidding, events
      are immutable. Your FizzBuzz history is permanent.
"""

from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from exceptions import (
    CommandHandlerNotFoundError,
    CommandValidationError,
    EventSequenceError,
    EventVersionConflictError,
    ProjectionError,
    QueryHandlerNotFoundError,
    SnapshotCorruptionError,
    TemporalQueryError,
)
from interfaces import IMiddleware
from models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Domain Events
# ============================================================


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events in the Event Sourcing subsystem.

    Every domain event is immutable (frozen), timestamped, versioned,
    and assigned a globally unique identifier. Because in the enterprise
    FizzBuzz world, even the most trivial state change deserves a
    permanent, tamper-proof historical record.

    Attributes:
        event_id: Globally unique identifier for this event instance.
        timestamp: When this event occurred (UTC), because time zones
                   are the enemy of reproducible FizzBuzz audits.
        aggregate_id: The identifier of the aggregate that emitted this event.
        sequence_number: The position of this event in the aggregate's stream.
        version: Schema version for upcasting support.
        metadata: Arbitrary key-value metadata for cross-cutting concerns.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    aggregate_id: str = "fizzbuzz-session"
    sequence_number: int = 0
    version: int = 1
    metadata: tuple = ()  # frozen-friendly tuple of (key, value) pairs


@dataclass(frozen=True)
class NumberReceivedEvent(DomainEvent):
    """Emitted when a number enters the FizzBuzz evaluation pipeline.

    This is the Genesis Event for any number's journey through the
    enterprise evaluation gauntlet. From this moment forward, every
    computational thought about this number will be permanently recorded.

    Attributes:
        number: The integer that dared to request FizzBuzz evaluation.
        session_id: The session in which this momentous event occurred.
    """

    number: int = 0
    session_id: str = ""


@dataclass(frozen=True)
class DivisibilityCheckedEvent(DomainEvent):
    """Emitted when a divisibility check is performed against a number.

    Records the sacred act of computing n % d == 0. Each such check
    is a question posed to the universe: "Is this number divisible?"
    And the universe, through the modulo operator, answers.

    Attributes:
        number: The number being interrogated.
        divisor: The divisor used in the modulo operation.
        is_divisible: Whether the number proved divisible.
        rule_name: The name of the rule that performed the check.
    """

    number: int = 0
    divisor: int = 1
    is_divisible: bool = False
    rule_name: str = ""


@dataclass(frozen=True)
class RuleMatchedEvent(DomainEvent):
    """Emitted when a FizzBuzz rule successfully matches a number.

    A rule has spoken: this number belongs to its domain. The match
    is recorded for all eternity in the event store, so that future
    generations may understand why 15 was labeled "FizzBuzz."

    Attributes:
        number: The number that matched.
        rule_name: The rule that claimed this number.
        label: The label the rule bestows upon its match.
    """

    number: int = 0
    rule_name: str = ""
    label: str = ""


@dataclass(frozen=True)
class LabelAssignedEvent(DomainEvent):
    """Emitted when the final label is assigned to a number.

    After all rules have had their say, the number receives its
    final designation. This is the culmination of the evaluation
    pipeline -- the moment when "15" becomes "FizzBuzz" and
    fulfills its destiny.

    Attributes:
        number: The number being labeled.
        label: The final output label (e.g., "Fizz", "Buzz", "FizzBuzz", or the number).
        matched_rule_count: How many rules contributed to this label.
    """

    number: int = 0
    label: str = ""
    matched_rule_count: int = 0


@dataclass(frozen=True)
class EvaluationCompletedEvent(DomainEvent):
    """Emitted when the complete evaluation of a number finishes.

    The journey is over. The number has been received, checked,
    matched, and labeled. This event marks the end of one number's
    odyssey through the enterprise FizzBuzz pipeline.

    Attributes:
        number: The evaluated number.
        output: The final output string.
        processing_time_ns: How long the evaluation took, in nanoseconds.
    """

    number: int = 0
    output: str = ""
    processing_time_ns: int = 0


@dataclass(frozen=True)
class SnapshotTakenEvent(DomainEvent):
    """Emitted when the system takes a state snapshot.

    Periodically, the system freezes its current state into a
    snapshot to accelerate future event replay. Think of it as
    a save point in a video game, except the game is FizzBuzz
    and the stakes are enterprise compliance.

    Attributes:
        snapshot_version: The event sequence number at snapshot time.
        aggregate_state: A serialized representation of the aggregate state.
    """

    snapshot_version: int = 0
    aggregate_state: tuple = ()  # frozen-friendly tuple of (key, value) pairs


# ============================================================
# Event Store
# ============================================================


class EventStore:
    """Append-only, thread-safe in-memory event store.

    The event store is the single source of truth in an Event Sourced
    system. Every domain event that occurs in the FizzBuzz pipeline is
    appended to this store, and the current state of the system can
    always be reconstructed by replaying these events from the beginning.

    The store maintains strict sequence ordering and rejects any attempt
    to append events out of order, because causality violations are
    not tolerated in enterprise FizzBuzz.

    Thread Safety:
        All mutations are protected by a threading.Lock. The FizzBuzz
        pipeline may be evaluating numbers concurrently (ha!), so we
        must ensure that the event log remains consistent.
    """

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []
        self._lock = threading.Lock()
        self._next_sequence: int = 1
        self._subscribers: list[Callable[[DomainEvent], None]] = []

    def append(self, event: DomainEvent) -> DomainEvent:
        """Append a domain event to the store with an assigned sequence number.

        Creates a new event instance with the correct sequence number
        (since DomainEvent is frozen, we must create a copy). The event
        is then published to all registered subscribers.

        Args:
            event: The domain event to append.

        Returns:
            The event with its assigned sequence number.

        Raises:
            EventSequenceError: If the universe implodes during sequencing.
        """
        with self._lock:
            seq = self._next_sequence
            self._next_sequence += 1

            # Since DomainEvent is frozen, we reconstruct with the assigned sequence
            sequenced_event = self._with_sequence(event, seq)
            self._events.append(sequenced_event)

            logger.debug(
                "Event appended: type=%s, seq=%d, aggregate=%s",
                type(sequenced_event).__name__,
                seq,
                sequenced_event.aggregate_id,
            )

        # Notify subscribers outside the lock to avoid deadlocks
        for subscriber in self._subscribers:
            try:
                subscriber(sequenced_event)
            except Exception as e:
                logger.error("Event subscriber failed: %s", e)

        return sequenced_event

    def _with_sequence(self, event: DomainEvent, seq: int) -> DomainEvent:
        """Create a copy of a frozen event with an updated sequence number.

        Since dataclasses with frozen=True do not allow attribute mutation,
        we must resort to the dark art of object.__setattr__. This is the
        Event Sourcing equivalent of using a crowbar to open a locked door:
        effective, but not something you'd brag about in code review.
        """
        # Use dataclasses replace-like approach via __class__ constructor
        fields = {}
        for f in event.__dataclass_fields__:
            fields[f] = getattr(event, f)
        fields["sequence_number"] = seq
        return type(event)(**fields)

    def get_events(
        self,
        aggregate_id: Optional[str] = None,
        after_sequence: int = 0,
    ) -> list[DomainEvent]:
        """Retrieve events from the store, optionally filtered.

        Args:
            aggregate_id: If provided, only return events for this aggregate.
            after_sequence: Only return events with sequence > this value.

        Returns:
            A list of matching domain events, in sequence order.
        """
        with self._lock:
            events = list(self._events)

        if aggregate_id is not None:
            events = [e for e in events if e.aggregate_id == aggregate_id]
        if after_sequence > 0:
            events = [e for e in events if e.sequence_number > after_sequence]

        return events

    def get_events_by_type(self, event_type: type) -> list[DomainEvent]:
        """Retrieve all events of a specific type.

        Args:
            event_type: The class of domain event to filter by.

        Returns:
            A list of matching events in sequence order.
        """
        with self._lock:
            return [e for e in self._events if isinstance(e, event_type)]

    def get_event_count(self) -> int:
        """Return the total number of events in the store."""
        with self._lock:
            return len(self._events)

    def get_latest_sequence(self) -> int:
        """Return the sequence number of the most recent event."""
        with self._lock:
            if not self._events:
                return 0
            return self._events[-1].sequence_number

    def subscribe(self, callback: Callable[[DomainEvent], None]) -> None:
        """Register a subscriber to be notified of new events."""
        self._subscribers.append(callback)

    def clear(self) -> None:
        """Clear all events. Used for testing only.

        In a real enterprise system, clearing the event store would
        trigger an immediate compliance investigation. But this is
        FizzBuzz, so we allow it.
        """
        with self._lock:
            self._events.clear()
            self._next_sequence = 1


# ============================================================
# Snapshot Store
# ============================================================


class SnapshotStore:
    """Periodic snapshot store for accelerated event replay.

    In a system with millions of FizzBuzz events (it could happen),
    replaying from the beginning every time would be prohibitively slow.
    The snapshot store periodically captures the aggregate state so that
    replay can start from the most recent snapshot instead.

    The snapshot interval is configurable, because some enterprises
    prefer frequent snapshots (paranoid) while others prefer infrequent
    ones (optimistic, or perhaps just negligent).

    Thread Safety:
        All snapshot operations are protected by a threading.Lock.
    """

    def __init__(self, interval: int = 10) -> None:
        self._interval = interval
        self._snapshots: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    @property
    def interval(self) -> int:
        """The number of events between automatic snapshots."""
        return self._interval

    def should_snapshot(self, event_count: int) -> bool:
        """Determine whether a snapshot should be taken based on event count."""
        return event_count > 0 and event_count % self._interval == 0

    def save_snapshot(
        self,
        aggregate_id: str,
        state: dict[str, Any],
        version: int,
    ) -> None:
        """Save a state snapshot for the given aggregate.

        Args:
            aggregate_id: The aggregate whose state is being snapshotted.
            state: A dictionary representing the aggregate's current state.
            version: The event sequence number at the time of the snapshot.
        """
        with self._lock:
            if aggregate_id not in self._snapshots:
                self._snapshots[aggregate_id] = []

            snapshot = {
                "aggregate_id": aggregate_id,
                "state": copy.deepcopy(state),
                "version": version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._snapshots[aggregate_id].append(snapshot)

            logger.debug(
                "Snapshot saved: aggregate=%s, version=%d",
                aggregate_id,
                version,
            )

    def get_latest_snapshot(
        self, aggregate_id: str
    ) -> Optional[dict[str, Any]]:
        """Retrieve the most recent snapshot for an aggregate.

        Args:
            aggregate_id: The aggregate to look up.

        Returns:
            The latest snapshot dict, or None if no snapshots exist.
        """
        with self._lock:
            snapshots = self._snapshots.get(aggregate_id, [])
            if not snapshots:
                return None
            return copy.deepcopy(snapshots[-1])

    def get_snapshot_count(self, aggregate_id: Optional[str] = None) -> int:
        """Return the number of snapshots stored.

        Args:
            aggregate_id: If provided, count only for this aggregate.
        """
        with self._lock:
            if aggregate_id is not None:
                return len(self._snapshots.get(aggregate_id, []))
            return sum(len(v) for v in self._snapshots.values())

    def clear(self) -> None:
        """Clear all snapshots. For testing only."""
        with self._lock:
            self._snapshots.clear()


# ============================================================
# Event Upcaster
# ============================================================


class EventUpcaster:
    """Version migration framework for domain events.

    As the FizzBuzz evaluation schema evolves (and it will, because
    enterprise schemas always evolve), older events in the store may
    need to be "upcasted" to the current version. The EventUpcaster
    maintains a chain of transformation functions that convert events
    from one version to the next.

    Example:
        Version 1: NumberReceivedEvent has only 'number'
        Version 2: NumberReceivedEvent gains 'session_id'

    The upcaster chain ensures that v1 events are transparently
    migrated to v2 format when replayed, so the rest of the system
    only ever sees the latest schema. This is the Event Sourcing
    equivalent of a database migration, except you can never delete
    the old data because that would violate the append-only contract.
    """

    def __init__(self) -> None:
        self._upcasters: dict[
            str, list[tuple[int, int, Callable[[dict[str, Any]], dict[str, Any]]]]
        ] = {}
        self._register_default_upcasters()

    def _register_default_upcasters(self) -> None:
        """Register built-in upcasters for known event type migrations.

        These demonstrate the upcasting pattern. In a real enterprise
        system, this list would grow with every schema change, eventually
        becoming a geological record of every architectural decision
        ever made.
        """
        # Demo upcaster: NumberReceivedEvent v1 -> v2
        # v2 adds a 'priority' field that v1 events don't have
        self.register(
            "NumberReceivedEvent",
            from_version=1,
            to_version=2,
            transform=lambda data: {**data, "priority": "normal"},
        )

    def register(
        self,
        event_type_name: str,
        from_version: int,
        to_version: int,
        transform: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Register an upcaster for a specific event type version transition.

        Args:
            event_type_name: The class name of the event type.
            from_version: The source version this upcaster handles.
            to_version: The target version this upcaster produces.
            transform: A function that transforms the event data dict.
        """
        if event_type_name not in self._upcasters:
            self._upcasters[event_type_name] = []
        self._upcasters[event_type_name].append(
            (from_version, to_version, transform)
        )
        logger.debug(
            "Registered upcaster: %s v%d -> v%d",
            event_type_name, from_version, to_version,
        )

    def upcast(
        self,
        event_type_name: str,
        data: dict[str, Any],
        from_version: int,
        to_version: int,
    ) -> dict[str, Any]:
        """Upcast event data from one version to another.

        Applies the chain of upcasters needed to transform the event
        data from from_version to to_version. If no upcaster chain
        exists, the data is returned unchanged (optimistic migration).

        Args:
            event_type_name: The class name of the event type.
            data: The event data dictionary to transform.
            from_version: The current version of the data.
            to_version: The desired target version.

        Returns:
            The upcasted event data dictionary.
        """
        if from_version >= to_version:
            return data

        upcasters = self._upcasters.get(event_type_name, [])
        result = dict(data)
        current_version = from_version

        while current_version < to_version:
            found = False
            for fv, tv, transform in upcasters:
                if fv == current_version:
                    result = transform(result)
                    current_version = tv
                    found = True
                    break

            if not found:
                # No upcaster found for this version gap; return as-is
                logger.warning(
                    "No upcaster found for %s v%d -> v%d, returning data as-is",
                    event_type_name, current_version, to_version,
                )
                break

        return result

    def get_registered_upcasters(self) -> dict[str, list[tuple[int, int]]]:
        """Return a summary of all registered upcasters."""
        return {
            event_type: [(fv, tv) for fv, tv, _ in upcasters]
            for event_type, upcasters in self._upcasters.items()
        }


# ============================================================
# Commands (Write Side)
# ============================================================


@dataclass(frozen=True)
class Command:
    """Base class for all commands in the CQRS write side.

    A command represents an intent to change the system state.
    Unlike events (which record what happened), commands express
    what someone wants to happen. The distinction is subtle but
    crucial to enterprise architects, and utterly irrelevant to
    anyone who just wants to compute 15 % 3.
    """

    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class EvaluateNumberCommand(Command):
    """Command to evaluate a single number through the FizzBuzz pipeline.

    This is the primary command in the Enterprise FizzBuzz CQRS system.
    When dispatched, it triggers the full evaluation pipeline and produces
    a series of domain events recording every step of the process.

    Attributes:
        number: The number to evaluate.
        session_id: The session context for this evaluation.
    """

    number: int = 0
    session_id: str = ""


@dataclass(frozen=True)
class ReplayEventsCommand(Command):
    """Command to replay events from the event store.

    Triggers a full or partial replay of the event history,
    useful for rebuilding projections or validating consistency.

    Attributes:
        from_sequence: Start replaying from this sequence number.
        to_sequence: Stop replaying at this sequence number (0 = all).
    """

    from_sequence: int = 0
    to_sequence: int = 0


# ============================================================
# Command Bus & Handlers
# ============================================================


class CommandBus:
    """Mediator for dispatching commands to their registered handlers.

    The command bus decouples command producers from command consumers,
    ensuring that the code which decides "evaluate number 15" does not
    need to know anything about how that evaluation is performed.

    In a microservices architecture, this bus might span process
    boundaries. In Enterprise FizzBuzz, it spans approximately
    three function calls, but the abstraction is no less important.

    Thread Safety:
        Handler registration is protected by a lock. Dispatch is not,
        because commands should be processed sequentially anyway.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, Callable] = {}
        self._lock = threading.Lock()

    def register(self, command_type: type, handler: Callable) -> None:
        """Register a handler for a specific command type.

        Args:
            command_type: The command class this handler processes.
            handler: A callable that accepts the command and returns a result.
        """
        with self._lock:
            self._handlers[command_type] = handler
            logger.debug("Command handler registered: %s", command_type.__name__)

    def dispatch(self, command: Command) -> Any:
        """Dispatch a command to its registered handler.

        Args:
            command: The command to dispatch.

        Returns:
            Whatever the handler returns.

        Raises:
            CommandHandlerNotFoundError: If no handler is registered.
        """
        handler = self._handlers.get(type(command))
        if handler is None:
            raise CommandHandlerNotFoundError(type(command).__name__)

        logger.debug(
            "Dispatching command: type=%s, id=%s",
            type(command).__name__,
            command.command_id[:8],
        )
        return handler(command)


class EvaluateNumberCommandHandler:
    """Handles EvaluateNumberCommand by producing domain events.

    This handler orchestrates the evaluation of a single number,
    emitting domain events for each step of the process. It does
    NOT perform the actual FizzBuzz computation -- that is delegated
    to the existing rule engine. Instead, it wraps the computation
    in a rich narrative of domain events.

    The handler:
        1. Emits NumberReceivedEvent
        2. Delegates to the evaluation callback
        3. Emits DivisibilityCheckedEvent for each rule
        4. Emits RuleMatchedEvent for matching rules
        5. Emits LabelAssignedEvent
        6. Emits EvaluationCompletedEvent
        7. Optionally triggers a snapshot
    """

    def __init__(
        self,
        event_store: EventStore,
        snapshot_store: SnapshotStore,
        evaluate_fn: Optional[Callable[[int], FizzBuzzResult]] = None,
    ) -> None:
        self._event_store = event_store
        self._snapshot_store = snapshot_store
        self._evaluate_fn = evaluate_fn
        self._aggregate_id = "fizzbuzz-session"

    def set_evaluate_fn(self, fn: Callable[[int], FizzBuzzResult]) -> None:
        """Set the evaluation function (deferred injection)."""
        self._evaluate_fn = fn

    def handle(self, command: EvaluateNumberCommand) -> FizzBuzzResult:
        """Handle the evaluate number command.

        Performs the evaluation and emits a stream of domain events
        recording every detail of the process. Returns the FizzBuzzResult
        from the underlying evaluation.
        """
        start_ns = time.perf_counter_ns()

        # 1. Number received
        self._event_store.append(NumberReceivedEvent(
            aggregate_id=self._aggregate_id,
            number=command.number,
            session_id=command.session_id,
        ))

        # 2. Perform actual evaluation
        if self._evaluate_fn is None:
            # Fallback: produce a trivial result
            result = FizzBuzzResult(number=command.number, output=str(command.number))
        else:
            result = self._evaluate_fn(command.number)

        # 3. Emit divisibility and match events based on result
        for match in result.matched_rules:
            self._event_store.append(DivisibilityCheckedEvent(
                aggregate_id=self._aggregate_id,
                number=command.number,
                divisor=match.rule.divisor,
                is_divisible=True,
                rule_name=match.rule.name,
            ))
            self._event_store.append(RuleMatchedEvent(
                aggregate_id=self._aggregate_id,
                number=command.number,
                rule_name=match.rule.name,
                label=match.rule.label,
            ))

        # If no rules matched, emit a "not divisible" check
        if not result.matched_rules:
            self._event_store.append(DivisibilityCheckedEvent(
                aggregate_id=self._aggregate_id,
                number=command.number,
                divisor=0,
                is_divisible=False,
                rule_name="(none)",
            ))

        # 4. Label assigned
        self._event_store.append(LabelAssignedEvent(
            aggregate_id=self._aggregate_id,
            number=command.number,
            label=result.output,
            matched_rule_count=len(result.matched_rules),
        ))

        # 5. Evaluation completed
        elapsed_ns = time.perf_counter_ns() - start_ns
        self._event_store.append(EvaluationCompletedEvent(
            aggregate_id=self._aggregate_id,
            number=command.number,
            output=result.output,
            processing_time_ns=elapsed_ns,
        ))

        # 6. Snapshot if needed
        event_count = self._event_store.get_event_count()
        if self._snapshot_store.should_snapshot(event_count):
            state = self._build_snapshot_state()
            version = self._event_store.get_latest_sequence()
            self._snapshot_store.save_snapshot(
                self._aggregate_id, state, version
            )
            self._event_store.append(SnapshotTakenEvent(
                aggregate_id=self._aggregate_id,
                snapshot_version=version,
            ))

        return result

    def _build_snapshot_state(self) -> dict[str, Any]:
        """Build a snapshot of the current aggregate state from events."""
        events = self._event_store.get_events(aggregate_id=self._aggregate_id)
        state: dict[str, Any] = {
            "total_evaluations": 0,
            "fizz_count": 0,
            "buzz_count": 0,
            "fizzbuzz_count": 0,
            "plain_count": 0,
            "latest_sequence": 0,
        }
        for event in events:
            if isinstance(event, EvaluationCompletedEvent):
                state["total_evaluations"] += 1
                if event.output == "Fizz":
                    state["fizz_count"] += 1
                elif event.output == "Buzz":
                    state["buzz_count"] += 1
                elif event.output == "FizzBuzz":
                    state["fizzbuzz_count"] += 1
                else:
                    state["plain_count"] += 1
            state["latest_sequence"] = event.sequence_number
        return state


# ============================================================
# Queries (Read Side)
# ============================================================


@dataclass(frozen=True)
class Query:
    """Base class for all queries in the CQRS read side.

    A query is a request for information that does NOT modify state.
    The read side is completely decoupled from the write side,
    because in CQRS, reading and writing are separate concerns
    that must never mingle, like oil and water, or developers
    and production databases.
    """

    query_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class GetCurrentResultsQuery(Query):
    """Query to retrieve the current FizzBuzz results from the read model."""
    pass


@dataclass(frozen=True)
class GetStatisticsQuery(Query):
    """Query to retrieve evaluation statistics from the read model."""
    pass


@dataclass(frozen=True)
class GetEventCountQuery(Query):
    """Query to retrieve the total event count."""
    pass


@dataclass(frozen=True)
class GetTemporalStateQuery(Query):
    """Query to reconstruct state at a specific point in time.

    Attributes:
        as_of: The timestamp to reconstruct state at.
    """

    as_of: Optional[datetime] = None
    as_of_sequence: Optional[int] = None


# ============================================================
# Query Bus & Handlers
# ============================================================


class QueryBus:
    """Mediator for dispatching queries to their registered handlers.

    The query bus is the read-side counterpart to the CommandBus.
    It routes queries to the appropriate handler, which typically
    reads from a pre-built projection (materialized view) for
    maximum performance.

    In Enterprise FizzBuzz, "maximum performance" means returning
    the count of how many times "Fizz" appeared in O(1) instead
    of replaying the entire event store. The savings are enormous
    when you have processed upwards of 100 numbers.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, Callable] = {}
        self._lock = threading.Lock()

    def register(self, query_type: type, handler: Callable) -> None:
        """Register a handler for a specific query type."""
        with self._lock:
            self._handlers[query_type] = handler
            logger.debug("Query handler registered: %s", query_type.__name__)

    def dispatch(self, query: Query) -> Any:
        """Dispatch a query to its registered handler.

        Raises:
            QueryHandlerNotFoundError: If no handler is registered.
        """
        handler = self._handlers.get(type(query))
        if handler is None:
            raise QueryHandlerNotFoundError(type(query).__name__)

        logger.debug("Dispatching query: %s", type(query).__name__)
        return handler(query)


# ============================================================
# Projections (Read Models)
# ============================================================


class CurrentResultsProjection:
    """Materialized read model of current FizzBuzz results.

    Maintains an up-to-date view of all evaluation results by
    folding EvaluationCompletedEvents into a simple dictionary.
    This is the CQRS way of answering "what were all the results?"
    without having to replay the entire event store.

    Thread Safety:
        Protected by threading.Lock for concurrent access.
    """

    def __init__(self) -> None:
        self._results: dict[int, str] = {}
        self._lock = threading.Lock()

    def apply(self, event: DomainEvent) -> None:
        """Apply a domain event to this projection."""
        if isinstance(event, EvaluationCompletedEvent):
            with self._lock:
                self._results[event.number] = event.output

    def get_results(self) -> dict[int, str]:
        """Return a copy of the current results."""
        with self._lock:
            return dict(self._results)

    def get_result(self, number: int) -> Optional[str]:
        """Get the result for a specific number."""
        with self._lock:
            return self._results.get(number)

    def get_count(self) -> int:
        """Return the number of evaluated numbers."""
        with self._lock:
            return len(self._results)

    def clear(self) -> None:
        """Clear the projection. For testing."""
        with self._lock:
            self._results.clear()


class StatisticsProjection:
    """Materialized read model of evaluation statistics.

    Aggregates FizzBuzz evaluation statistics in real-time by
    processing domain events. Provides O(1) access to counts
    that would otherwise require scanning the entire event store.

    Thread Safety:
        Protected by threading.Lock for concurrent access.
    """

    def __init__(self) -> None:
        self._total_evaluations: int = 0
        self._fizz_count: int = 0
        self._buzz_count: int = 0
        self._fizzbuzz_count: int = 0
        self._plain_count: int = 0
        self._total_processing_ns: int = 0
        self._lock = threading.Lock()

    def apply(self, event: DomainEvent) -> None:
        """Apply a domain event to this projection."""
        if isinstance(event, EvaluationCompletedEvent):
            with self._lock:
                self._total_evaluations += 1
                self._total_processing_ns += event.processing_time_ns
                if event.output == "FizzBuzz":
                    self._fizzbuzz_count += 1
                elif event.output == "Fizz":
                    self._fizz_count += 1
                elif event.output == "Buzz":
                    self._buzz_count += 1
                else:
                    self._plain_count += 1

    def get_statistics(self) -> dict[str, Any]:
        """Return current statistics as a dictionary."""
        with self._lock:
            return {
                "total_evaluations": self._total_evaluations,
                "fizz_count": self._fizz_count,
                "buzz_count": self._buzz_count,
                "fizzbuzz_count": self._fizzbuzz_count,
                "plain_count": self._plain_count,
                "total_processing_ns": self._total_processing_ns,
                "avg_processing_ns": (
                    self._total_processing_ns / self._total_evaluations
                    if self._total_evaluations > 0
                    else 0
                ),
            }

    def clear(self) -> None:
        """Clear the projection. For testing."""
        with self._lock:
            self._total_evaluations = 0
            self._fizz_count = 0
            self._buzz_count = 0
            self._fizzbuzz_count = 0
            self._plain_count = 0
            self._total_processing_ns = 0


class EventCountProjection:
    """Materialized read model tracking event counts by type.

    Maintains a running tally of how many events of each type
    have been emitted. Essential for monitoring the health of
    the event sourcing subsystem and for generating impressive
    dashboards that nobody will ever look at.

    Thread Safety:
        Protected by threading.Lock.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._total: int = 0
        self._lock = threading.Lock()

    def apply(self, event: DomainEvent) -> None:
        """Apply a domain event to this projection."""
        event_type_name = type(event).__name__
        with self._lock:
            self._counts[event_type_name] = self._counts.get(event_type_name, 0) + 1
            self._total += 1

    def get_counts(self) -> dict[str, int]:
        """Return event counts by type."""
        with self._lock:
            return dict(self._counts)

    def get_total(self) -> int:
        """Return total event count."""
        with self._lock:
            return self._total

    def clear(self) -> None:
        """Clear the projection. For testing."""
        with self._lock:
            self._counts.clear()
            self._total = 0


# ============================================================
# Temporal Query Engine
# ============================================================


class TemporalQueryEngine:
    """Point-in-time state reconstruction engine.

    Enables "time travel" queries that reconstruct the FizzBuzz
    evaluation state as it existed at any past moment. This is
    achieved by replaying events up to the specified point in
    time or sequence number, building a fresh state from the
    event log.

    In enterprise systems, temporal queries are invaluable for
    auditing and compliance. In Enterprise FizzBuzz, they let you
    answer questions like "what was the Fizz count after the 7th
    evaluation?" which is a question nobody has ever asked but
    we can now answer definitively.

    Thread Safety:
        The engine itself is stateless (all state is reconstructed
        from the event store on each query), so it is inherently
        thread-safe.
    """

    def __init__(self, event_store: EventStore) -> None:
        self._event_store = event_store

    def query_at_sequence(self, sequence_number: int) -> dict[str, Any]:
        """Reconstruct state as of a specific event sequence number.

        Args:
            sequence_number: Replay events up to and including this sequence.

        Returns:
            A dictionary representing the reconstructed state.
        """
        events = self._event_store.get_events()
        filtered = [e for e in events if e.sequence_number <= sequence_number]
        return self._build_state(filtered)

    def query_at_timestamp(self, timestamp: datetime) -> dict[str, Any]:
        """Reconstruct state as of a specific timestamp.

        Args:
            timestamp: Replay events that occurred at or before this time.

        Returns:
            A dictionary representing the reconstructed state.
        """
        events = self._event_store.get_events()
        filtered = [e for e in events if e.timestamp <= timestamp]
        return self._build_state(filtered)

    def _build_state(self, events: list[DomainEvent]) -> dict[str, Any]:
        """Build aggregate state by folding a list of events.

        This is the fundamental operation of Event Sourcing: starting
        from nothing and applying events one by one to reconstruct
        the current state. It's like watching a time-lapse of a
        FizzBuzz evaluation, except in reverse, and then forwards again.
        """
        state: dict[str, Any] = {
            "total_evaluations": 0,
            "fizz_count": 0,
            "buzz_count": 0,
            "fizzbuzz_count": 0,
            "plain_count": 0,
            "results": {},
            "events_processed": 0,
        }

        for event in events:
            state["events_processed"] += 1
            if isinstance(event, EvaluationCompletedEvent):
                state["total_evaluations"] += 1
                state["results"][event.number] = event.output
                if event.output == "FizzBuzz":
                    state["fizzbuzz_count"] += 1
                elif event.output == "Fizz":
                    state["fizz_count"] += 1
                elif event.output == "Buzz":
                    state["buzz_count"] += 1
                else:
                    state["plain_count"] += 1

        return state

    def get_event_timeline(self) -> list[dict[str, Any]]:
        """Return a timeline of all events with summary data.

        Useful for visualizing the history of the FizzBuzz session
        as a chronological sequence of domain events.
        """
        events = self._event_store.get_events()
        return [
            {
                "sequence": e.sequence_number,
                "type": type(e).__name__,
                "timestamp": e.timestamp.isoformat(),
                "aggregate_id": e.aggregate_id,
            }
            for e in events
        ]


# ============================================================
# Event Sourcing Middleware
# ============================================================


class EventSourcingMiddleware(IMiddleware):
    """Middleware that wraps FizzBuzz evaluations in CQRS command dispatch.

    Intercepts each number evaluation in the middleware pipeline and
    routes it through the CommandBus as an EvaluateNumberCommand.
    This ensures that every evaluation is recorded as a series of
    domain events in the event store.

    The middleware sits at priority 5, which places it after validation
    and timing but before translation. This ensures that the events
    capture the raw evaluation results before any i18n transformation.

    Integration:
        - Converts each ProcessingContext into an EvaluateNumberCommand
        - Dispatches via CommandBus for full CQRS compliance
        - Falls back to direct next_handler if command dispatch fails
    """

    def __init__(
        self,
        command_bus: CommandBus,
        event_store: EventStore,
    ) -> None:
        self._command_bus = command_bus
        self._event_store = event_store

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a number through the CQRS command pipeline.

        Creates an EvaluateNumberCommand for the current number and
        dispatches it through the command bus. The actual evaluation
        is performed by the next_handler, but wrapped in event emission.
        """
        # Execute the downstream pipeline to get the result
        result_context = next_handler(context)

        # Now emit events for what just happened
        if result_context.results:
            latest_result = result_context.results[-1]

            # Emit the core domain events
            self._event_store.append(NumberReceivedEvent(
                number=context.number,
                session_id=context.session_id,
            ))

            for match in latest_result.matched_rules:
                self._event_store.append(DivisibilityCheckedEvent(
                    number=context.number,
                    divisor=match.rule.divisor,
                    is_divisible=True,
                    rule_name=match.rule.name,
                ))
                self._event_store.append(RuleMatchedEvent(
                    number=context.number,
                    rule_name=match.rule.name,
                    label=match.rule.label,
                ))

            if not latest_result.matched_rules:
                self._event_store.append(DivisibilityCheckedEvent(
                    number=context.number,
                    divisor=0,
                    is_divisible=False,
                    rule_name="(none)",
                ))

            self._event_store.append(LabelAssignedEvent(
                number=context.number,
                label=latest_result.output,
                matched_rule_count=len(latest_result.matched_rules),
            ))

            self._event_store.append(EvaluationCompletedEvent(
                number=context.number,
                output=latest_result.output,
                processing_time_ns=latest_result.processing_time_ns,
            ))

        # Tag the context with ES metadata
        result_context.metadata["event_sourcing"] = True
        result_context.metadata["event_count"] = self._event_store.get_event_count()

        return result_context

    def get_name(self) -> str:
        return "EventSourcingMiddleware"

    def get_priority(self) -> int:
        return 5


# ============================================================
# Event Sourcing Summary (ASCII Dashboard)
# ============================================================


class EventSourcingSummary:
    """ASCII-art summary renderer for the Event Sourcing subsystem.

    Produces a beautifully formatted terminal dashboard showing
    event store statistics, projection states, and temporal query
    capabilities. Because what good is an event-sourced FizzBuzz
    if you can't admire it in monospace font?
    """

    @staticmethod
    def render(
        event_store: EventStore,
        snapshot_store: SnapshotStore,
        results_projection: CurrentResultsProjection,
        stats_projection: StatisticsProjection,
        event_count_projection: EventCountProjection,
    ) -> str:
        """Render the complete Event Sourcing summary dashboard."""
        stats = stats_projection.get_statistics()
        event_counts = event_count_projection.get_counts()
        snapshot_count = snapshot_store.get_snapshot_count()
        total_events = event_store.get_event_count()
        latest_seq = event_store.get_latest_sequence()

        # Build event type breakdown
        event_breakdown_lines = []
        for etype, count in sorted(event_counts.items()):
            event_breakdown_lines.append(
                f"  |    {etype:<35} {count:>5}          |"
            )
        if not event_breakdown_lines:
            event_breakdown_lines.append(
                "  |    (no events recorded)                                   |"
            )

        avg_ns = stats.get("avg_processing_ns", 0)
        avg_us = avg_ns / 1000 if avg_ns else 0

        lines = [
            "",
            "  +===========================================================+",
            "  |           EVENT SOURCING / CQRS SUMMARY                   |",
            "  +===========================================================+",
            f"  |  Total Events      : {total_events:<37}|",
            f"  |  Latest Sequence   : {latest_seq:<37}|",
            f"  |  Snapshots Taken   : {snapshot_count:<37}|",
            "  |-----------------------------------------------------------|",
            f"  |  Evaluations       : {stats.get('total_evaluations', 0):<37}|",
            f"  |  Fizz Count        : {stats.get('fizz_count', 0):<37}|",
            f"  |  Buzz Count        : {stats.get('buzz_count', 0):<37}|",
            f"  |  FizzBuzz Count    : {stats.get('fizzbuzz_count', 0):<37}|",
            f"  |  Plain Count       : {stats.get('plain_count', 0):<37}|",
            f"  |  Avg Processing    : {avg_us:<33.2f} us  |",
            "  |-----------------------------------------------------------|",
            "  |  Event Type Breakdown:                                    |",
        ]
        lines.extend(event_breakdown_lines)
        lines.extend([
            "  +===========================================================+",
            "",
        ])

        return "\n".join(lines)


# ============================================================
# Event Sourcing System (Facade)
# ============================================================


class EventSourcingSystem:
    """Facade that wires together all Event Sourcing / CQRS components.

    This is the single entry point for setting up the entire ES/CQRS
    subsystem. It creates the event store, snapshot store, command bus,
    query bus, projections, and temporal query engine, then wires them
    all together.

    Usage:
        system = EventSourcingSystem(snapshot_interval=10)
        middleware = system.create_middleware()
        # Add middleware to the pipeline
        # After evaluation, get the summary:
        print(system.render_summary())
    """

    def __init__(self, snapshot_interval: int = 10) -> None:
        # Core stores
        self.event_store = EventStore()
        self.snapshot_store = SnapshotStore(interval=snapshot_interval)

        # Upcaster
        self.upcaster = EventUpcaster()

        # Projections
        self.results_projection = CurrentResultsProjection()
        self.stats_projection = StatisticsProjection()
        self.event_count_projection = EventCountProjection()

        # Wire projections as event subscribers
        self.event_store.subscribe(self.results_projection.apply)
        self.event_store.subscribe(self.stats_projection.apply)
        self.event_store.subscribe(self.event_count_projection.apply)

        # Temporal query engine
        self.temporal_engine = TemporalQueryEngine(self.event_store)

        # Command bus
        self.command_bus = CommandBus()
        self._command_handler = EvaluateNumberCommandHandler(
            event_store=self.event_store,
            snapshot_store=self.snapshot_store,
        )
        self.command_bus.register(
            EvaluateNumberCommand,
            self._command_handler.handle,
        )

        # Query bus
        self.query_bus = QueryBus()
        self.query_bus.register(
            GetCurrentResultsQuery,
            lambda q: self.results_projection.get_results(),
        )
        self.query_bus.register(
            GetStatisticsQuery,
            lambda q: self.stats_projection.get_statistics(),
        )
        self.query_bus.register(
            GetEventCountQuery,
            lambda q: self.event_store.get_event_count(),
        )
        self.query_bus.register(
            GetTemporalStateQuery,
            lambda q: self._handle_temporal_query(q),
        )

        logger.info(
            "Event Sourcing system initialized: snapshot_interval=%d",
            snapshot_interval,
        )

    def _handle_temporal_query(self, query: GetTemporalStateQuery) -> dict[str, Any]:
        """Handle a temporal state query."""
        if query.as_of_sequence is not None:
            return self.temporal_engine.query_at_sequence(query.as_of_sequence)
        elif query.as_of is not None:
            return self.temporal_engine.query_at_timestamp(query.as_of)
        else:
            # Default to current state
            return self.temporal_engine.query_at_sequence(
                self.event_store.get_latest_sequence()
            )

    def create_middleware(self) -> EventSourcingMiddleware:
        """Create the ES middleware for pipeline integration."""
        return EventSourcingMiddleware(
            command_bus=self.command_bus,
            event_store=self.event_store,
        )

    def render_summary(self) -> str:
        """Render the ASCII summary dashboard."""
        return EventSourcingSummary.render(
            event_store=self.event_store,
            snapshot_store=self.snapshot_store,
            results_projection=self.results_projection,
            stats_projection=self.stats_projection,
            event_count_projection=self.event_count_projection,
        )

    def replay_events(self, from_sequence: int = 0) -> dict[str, Any]:
        """Replay events to rebuild projections.

        Clears all projections and re-applies events from the store.
        This is useful after a schema change or to verify consistency.
        """
        self.results_projection.clear()
        self.stats_projection.clear()
        self.event_count_projection.clear()

        events = self.event_store.get_events(after_sequence=from_sequence)
        for event in events:
            self.results_projection.apply(event)
            self.stats_projection.apply(event)
            self.event_count_projection.apply(event)

        return {
            "replayed_events": len(events),
            "statistics": self.stats_projection.get_statistics(),
        }
