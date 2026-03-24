"""
Enterprise FizzBuzz Platform - Dynamic Event Type Registry

Provides a drop-in replacement for the former EventType Enum with a
dynamic registration system. Infrastructure modules register their
event types at import time via EventType.register("EVENT_NAME").

The registry preserves full API compatibility with the original Enum:
attribute access, equality, hashing, iteration, containment checks,
bracket access, value-based lookup, and isinstance all behave
identically.
"""

from __future__ import annotations


class _EventValue:
    """Immutable, hashable value object representing a single event type.

    Each registered event type is represented by an _EventValue instance
    with a name (the string identifier) and a value (auto-incrementing
    integer matching the original auto() behavior).
    """

    __slots__ = ("_name", "_value")

    def __init__(self, name: str, value: int) -> None:
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_value", value)

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> int:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _EventValue):
            return self._name == other._name and self._value == other._value
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        if isinstance(other, _EventValue):
            return self._name != other._name or self._value != other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._name, self._value))

    def __repr__(self) -> str:
        return f"EventType.{self._name}"

    def __str__(self) -> str:
        return f"EventType.{self._name}"

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("_EventValue instances are immutable")

    def __reduce__(self) -> tuple:
        return (_reconstruct_event_value, (self._name, self._value))


def _reconstruct_event_value(name: str, value: int) -> _EventValue:
    """Pickle reconstruction helper for _EventValue instances."""
    return _EventValue(name, value)


class _EventTypeMeta(type):
    """Metaclass for EventType that enables Enum-compatible behavior.

    Provides isinstance() support, attribute access for registered
    members, iteration, containment, length, bracket access, and
    value-based construction — all at the class level.
    """

    def __instancecheck__(cls, instance: object) -> bool:
        return type.__instancecheck__(cls, instance) or isinstance(instance, _EventValue)

    def __getattr__(cls, name: str) -> _EventValue:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in cls._members:
            return cls._members[name]
        raise AttributeError(
            f"EventType has no member '{name}'"
        )

    def __getitem__(cls, name: str) -> _EventValue:
        """Bracket access: EventType["CACHE_HIT"]."""
        try:
            return cls._members[name]
        except KeyError:
            raise KeyError(name)

    def __call__(cls, value: int) -> _EventValue:
        """Value-based lookup: EventType(42)."""
        try:
            return cls._by_value[value]
        except KeyError:
            raise ValueError(
                f"{value} is not a valid EventType value"
            )

    def __contains__(cls, item: object) -> bool:
        if isinstance(item, _EventValue):
            return item.name in cls._members
        if isinstance(item, str):
            return item in cls._members
        return False

    def __iter__(cls):
        return iter(cls._members.values())

    def __len__(cls) -> int:
        return len(cls._members)

    def __repr__(cls) -> str:
        return f"<EventType: {len(cls._members)} members>"

    def __bool__(cls) -> bool:
        return True


class EventType(metaclass=_EventTypeMeta):
    """Dynamic registry of event types for the Enterprise FizzBuzz Platform.

    Supports the same access patterns as the original EventType Enum:
    attribute access, iteration, containment, bracket access,
    value-based lookup, and isinstance checks.
    """

    _members: dict[str, _EventValue] = {}
    _by_value: dict[int, _EventValue] = {}
    _next_value: int = 1

    @classmethod
    def register(cls, name: str, value: int | None = None) -> _EventValue:
        """Register a new event type or return the existing one.

        Args:
            name: The event type identifier (e.g., "CACHE_HIT").
            value: Optional explicit integer value. If not provided,
                   an auto-incrementing integer is assigned.

        Returns:
            The _EventValue instance for this event type.
        """
        if name in cls._members:
            return cls._members[name]
        if value is None:
            value = cls._next_value
            cls._next_value += 1
        else:
            if value >= cls._next_value:
                cls._next_value = value + 1
        ev = _EventValue(name, value)
        cls._members[name] = ev
        cls._by_value[value] = ev
        return ev
