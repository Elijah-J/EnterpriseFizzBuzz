"""
Enterprise FizzBuzz Platform - Domain Models Module

Contains all value objects, data transfer objects, enumerations,
and domain entities required by the FizzBuzz evaluation pipeline.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Optional


class FizzBuzzRole(Enum):
    """Role-Based Access Control roles for the Enterprise FizzBuzz Platform.

    Each role represents a different level of FizzBuzz privilege,
    because not everyone deserves unfettered access to modulo arithmetic.
    The hierarchy mirrors real enterprise org charts, where interns can
    only read the number 1, and only C-level executives are trusted
    with the full range of divisibility operations.
    """

    ANONYMOUS = auto()
    FIZZ_READER = auto()
    BUZZ_ADMIN = auto()
    FIZZBUZZ_SUPERUSER = auto()
    NUMBER_AUDITOR = auto()


class OutputFormat(Enum):
    """Supported output serialization formats."""

    PLAIN = auto()
    JSON = auto()
    XML = auto()
    CSV = auto()


class EvaluationStrategy(Enum):
    """Available strategies for FizzBuzz rule evaluation."""

    STANDARD = auto()
    CHAIN_OF_RESPONSIBILITY = auto()
    PARALLEL_ASYNC = auto()
    MACHINE_LEARNING = auto()


class LogLevel(Enum):
    """Logging verbosity levels for the platform."""

    SILENT = 0
    ERROR = 1
    WARNING = 2
    INFO = 3
    DEBUG = 4
    TRACE = 5


class EventType(Enum):
    """Observable event types emitted during FizzBuzz processing."""

    SESSION_STARTED = auto()
    SESSION_ENDED = auto()
    NUMBER_PROCESSING_STARTED = auto()
    NUMBER_PROCESSED = auto()
    RULE_MATCHED = auto()
    RULE_NOT_MATCHED = auto()
    FIZZ_DETECTED = auto()
    BUZZ_DETECTED = auto()
    FIZZBUZZ_DETECTED = auto()
    PLAIN_NUMBER_DETECTED = auto()
    MIDDLEWARE_ENTERED = auto()
    MIDDLEWARE_EXITED = auto()
    OUTPUT_FORMATTED = auto()
    ERROR_OCCURRED = auto()
    CIRCUIT_BREAKER_STATE_CHANGED = auto()
    CIRCUIT_BREAKER_TRIPPED = auto()
    CIRCUIT_BREAKER_RECOVERED = auto()
    CIRCUIT_BREAKER_HALF_OPEN = auto()
    CIRCUIT_BREAKER_CALL_REJECTED = auto()
    TRACE_STARTED = auto()
    TRACE_ENDED = auto()
    SPAN_STARTED = auto()
    SPAN_ENDED = auto()
    AUTHORIZATION_GRANTED = auto()
    AUTHORIZATION_DENIED = auto()
    TOKEN_VALIDATED = auto()
    TOKEN_VALIDATION_FAILED = auto()

    # Event Sourcing / CQRS events
    ES_NUMBER_RECEIVED = auto()
    ES_DIVISIBILITY_CHECKED = auto()
    ES_RULE_MATCHED = auto()
    ES_LABEL_ASSIGNED = auto()
    ES_EVALUATION_COMPLETED = auto()
    ES_SNAPSHOT_TAKEN = auto()
    ES_COMMAND_DISPATCHED = auto()
    ES_COMMAND_HANDLED = auto()
    ES_QUERY_DISPATCHED = auto()
    ES_PROJECTION_UPDATED = auto()
    ES_EVENT_REPLAYED = auto()
    ES_TEMPORAL_QUERY_EXECUTED = auto()


@dataclass(frozen=True)
class Permission:
    """An immutable FizzBuzz permission grant.

    Encodes the holy trinity of access control: what resource,
    which range of that resource, and what action is allowed.
    Because "can this user compute 15 % 3" is a question that
    demands a formal permission model.

    Attributes:
        resource: The resource category (e.g., "numbers").
        range_spec: The range specification (e.g., "1-50", "*", "fizz").
        action: The permitted action (e.g., "evaluate", "read", "configure").
    """

    resource: str
    range_spec: str
    action: str


@dataclass(frozen=True)
class AuthContext:
    """Immutable authentication context for an authorized FizzBuzz session.

    Carries the identity and permissions of the user through the
    middleware pipeline, so that every modulo operation can be
    individually authorized. Because in enterprise software,
    trust is never implicit — it's always a frozen dataclass.

    Attributes:
        user: The authenticated user's identifier.
        role: The user's assigned FizzBuzz role.
        token_id: Optional JWT-style token identifier for audit trails.
        effective_permissions: All permissions this user has, including inherited.
        trust_mode: If True, the user was authenticated via the "just trust me"
                    protocol, which is exactly as secure as it sounds.
    """

    user: str
    role: FizzBuzzRole
    token_id: Optional[str] = None
    effective_permissions: tuple[Permission, ...] = ()
    trust_mode: bool = False


@dataclass(frozen=True)
class RuleDefinition:
    """Immutable definition of a FizzBuzz rule.

    Attributes:
        name: Human-readable rule identifier.
        divisor: The divisor to check against.
        label: The string to output when the rule matches.
        priority: Evaluation priority (lower = higher priority).
    """

    name: str
    divisor: int
    label: str
    priority: int = 0


@dataclass(frozen=True)
class RuleMatch:
    """Records a successful rule match against a number.

    Attributes:
        rule: The rule that matched.
        number: The number it was evaluated against.
        timestamp: When the match occurred (UTC).
    """

    rule: RuleDefinition
    number: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FizzBuzzResult:
    """The outcome of evaluating a single number through the FizzBuzz pipeline.

    Attributes:
        number: The input number.
        output: The resulting string (e.g., "Fizz", "Buzz", "FizzBuzz", or the number).
        matched_rules: All rules that matched this number.
        processing_time_ns: Time spent processing in nanoseconds.
        result_id: Unique identifier for this result (for traceability).
        metadata: Arbitrary key-value metadata attached by middleware.
    """

    number: int
    output: str
    matched_rules: list[RuleMatch] = field(default_factory=list)
    processing_time_ns: int = 0
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_fizz(self) -> bool:
        return any(m.rule.label == "Fizz" for m in self.matched_rules)

    @property
    def is_buzz(self) -> bool:
        return any(m.rule.label == "Buzz" for m in self.matched_rules)

    @property
    def is_fizzbuzz(self) -> bool:
        return self.is_fizz and self.is_buzz

    @property
    def is_plain_number(self) -> bool:
        return len(self.matched_rules) == 0


@dataclass
class ProcessingContext:
    """Mutable context object passed through the middleware pipeline.

    Carries state between middleware layers and enables cross-cutting concerns.
    """

    number: int
    session_id: str
    results: list[FizzBuzzResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    cancelled: bool = False
    locale: str = "en"

    def elapsed_ms(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return 0.0


@dataclass(frozen=True)
class Event:
    """An observable event emitted by the FizzBuzz processing pipeline.

    Attributes:
        event_type: Category of the event.
        payload: Event-specific data.
        timestamp: When the event was emitted (UTC).
        event_id: Unique identifier for this event instance.
        source: The component that emitted this event.
    """

    event_type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = "FizzBuzzEngine"


@dataclass
class FizzBuzzSessionSummary:
    """Summary statistics for a completed FizzBuzz session."""

    session_id: str
    total_numbers: int = 0
    fizz_count: int = 0
    buzz_count: int = 0
    fizzbuzz_count: int = 0
    plain_count: int = 0
    total_processing_time_ms: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)

    @property
    def numbers_per_second(self) -> float:
        if self.total_processing_time_ms > 0:
            return self.total_numbers / (self.total_processing_time_ms / 1000)
        return float("inf")
