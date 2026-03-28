"""Tests for the dynamic EventType registry.

Verifies that the replacement of the monolithic EventType Enum with a
per-feature dynamic registration system preserves all backward-compatible
behavior: attribute access, equality, hashing, iteration, containment,
bracket access, value-based lookup, and isinstance checks.
"""

import pytest

from enterprise_fizzbuzz.domain.events._registry import EventType, _EventValue


class TestEventTypeRegistryMemberCount:
    """Verify that all event types are registered."""

    def test_total_member_count(self):
        assert len(EventType) >= 754

    def test_iteration_returns_all_members(self):
        all_events = list(EventType)
        assert len(all_events) >= 754


class TestEventTypeAttributeAccess:
    """Verify attribute-style access for registered event types."""

    def test_core_event_access(self):
        assert EventType.SESSION_STARTED is not None
        assert EventType.SESSION_ENDED is not None
        assert EventType.ERROR_OCCURRED is not None

    def test_cache_event_access(self):
        assert EventType.CACHE_HIT is not None
        assert EventType.CACHE_MISS is not None
        assert EventType.CACHE_EVICTION is not None

    def test_container_event_access(self):
        assert EventType.CONTAINERD_DAEMON_STARTED is not None
        assert EventType.KUBEV2_POD_CREATED is not None

    def test_fizzlife_event_access(self):
        assert EventType.FIZZLIFE_SIMULATION_STARTED is not None
        assert EventType.FIZZLIFE_DASHBOARD_RENDERED is not None

    def test_nonexistent_member_raises_attribute_error(self):
        with pytest.raises(AttributeError, match="EventType has no member"):
            _ = EventType.THIS_EVENT_DOES_NOT_EXIST


class TestEventTypeEqualityAndHashing:
    """Verify equality and hash behavior for EventType members."""

    def test_same_member_is_equal(self):
        assert EventType.CACHE_HIT == EventType.CACHE_HIT

    def test_different_members_are_not_equal(self):
        assert EventType.CACHE_HIT != EventType.CACHE_MISS

    def test_member_usable_as_dict_key(self):
        d = {EventType.CACHE_HIT: "handler", EventType.CACHE_MISS: "fallback"}
        assert d[EventType.CACHE_HIT] == "handler"
        assert d[EventType.CACHE_MISS] == "fallback"

    def test_member_usable_in_set(self):
        s = {EventType.CACHE_HIT, EventType.CACHE_MISS, EventType.CACHE_HIT}
        assert len(s) == 2

    def test_hash_consistency(self):
        h1 = hash(EventType.CACHE_HIT)
        h2 = hash(EventType.CACHE_HIT)
        assert h1 == h2


class TestEventTypeNameAndValue:
    """Verify .name and .value properties."""

    def test_name_property(self):
        assert EventType.CACHE_HIT.name == "CACHE_HIT"
        assert EventType.SESSION_STARTED.name == "SESSION_STARTED"

    def test_value_is_integer(self):
        assert isinstance(EventType.SESSION_STARTED.value, int)

    def test_first_value_is_one(self):
        assert EventType.SESSION_STARTED.value == 1

    def test_values_are_auto_incrementing(self):
        assert EventType.SESSION_ENDED.value == 2
        assert EventType.NUMBER_PROCESSING_STARTED.value == 3


class TestEventTypeContainment:
    """Verify containment checks."""

    def test_member_in_registry(self):
        assert EventType.CACHE_HIT in EventType

    def test_string_in_registry(self):
        assert "CACHE_HIT" in EventType

    def test_nonexistent_string_not_in_registry(self):
        assert "NONEXISTENT_EVENT" not in EventType

    def test_integer_not_in_registry(self):
        assert 42 not in EventType


class TestEventTypeBracketAccess:
    """Verify bracket-style access (EventType["NAME"])."""

    def test_bracket_access(self):
        event = EventType["CACHE_HIT"]
        assert event == EventType.CACHE_HIT

    def test_bracket_access_nonexistent_raises_key_error(self):
        with pytest.raises(KeyError):
            _ = EventType["NONEXISTENT"]


class TestEventTypeValueLookup:
    """Verify value-based construction (EventType(value))."""

    def test_value_lookup(self):
        event = EventType(1)
        assert event == EventType.SESSION_STARTED

    def test_value_lookup_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="not a valid EventType value"):
            _ = EventType(999999)


class TestEventTypeRegistration:
    """Verify registration behavior."""

    def test_registration_is_idempotent(self):
        event1 = EventType.register("CACHE_HIT")
        event2 = EventType.register("CACHE_HIT")
        assert event1 is event2

    def test_registration_returns_event_value(self):
        event = EventType.register("SESSION_STARTED")
        assert isinstance(event, _EventValue)
        assert event.name == "SESSION_STARTED"


class TestEventTypeRepr:
    """Verify string representation."""

    def test_repr(self):
        assert repr(EventType.CACHE_HIT) == "EventType.CACHE_HIT"

    def test_str(self):
        assert str(EventType.CACHE_HIT) == "EventType.CACHE_HIT"


class TestEventTypeIteration:
    """Verify iteration over all registered types."""

    def test_iteration_yields_event_values(self):
        for event in EventType:
            assert isinstance(event, _EventValue)
            break

    def test_filter_by_prefix(self):
        containerd = [e for e in EventType if e.name.startswith("CONTAINERD_")]
        assert len(containerd) == 18

    def test_disaster_recovery_events(self):
        dr_events = [e for e in EventType if e.name.startswith("DR_")]
        assert len(dr_events) == 17


class TestEventTypeIsinstance:
    """Verify isinstance() checks work as they did with the Enum."""

    def test_isinstance_event_value(self):
        assert isinstance(EventType.CACHE_HIT, EventType)

    def test_isinstance_all_members(self):
        for event in EventType:
            assert isinstance(event, EventType)


class TestEventTypeBackwardCompatImport:
    """Verify backward-compatible import paths."""

    def test_import_from_models(self):
        from enterprise_fizzbuzz.domain.models import EventType as ET
        assert ET.CACHE_HIT.name == "CACHE_HIT"

    def test_import_from_events_package(self):
        from enterprise_fizzbuzz.domain.events import EventType as ET
        assert ET.CACHE_HIT.name == "CACHE_HIT"

    def test_import_from_registry(self):
        from enterprise_fizzbuzz.domain.events._registry import EventType as ET
        assert ET.CACHE_HIT.name == "CACHE_HIT"

    def test_all_imports_are_same_object(self):
        from enterprise_fizzbuzz.domain.models import EventType as ET1
        from enterprise_fizzbuzz.domain.events import EventType as ET2
        from enterprise_fizzbuzz.domain.events._registry import EventType as ET3
        assert ET1 is ET2
        assert ET2 is ET3


class TestEventValueImmutability:
    """Verify that _EventValue instances are immutable."""

    def test_cannot_set_attribute(self):
        with pytest.raises(AttributeError, match="immutable"):
            EventType.CACHE_HIT.arbitrary = "value"

    def test_cannot_modify_name(self):
        with pytest.raises(AttributeError, match="immutable"):
            EventType.CACHE_HIT.name = "NEW_NAME"
