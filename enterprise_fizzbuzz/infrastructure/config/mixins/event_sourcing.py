"""Event Sourcing configuration properties."""

from __future__ import annotations

from typing import Any


class EventSourcingConfigMixin:
    """Configuration properties for the event sourcing subsystem."""

    @property
    def event_sourcing_enabled(self) -> bool:
        """Whether the Event Sourcing / CQRS subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get("enabled", False)

    @property
    def event_sourcing_snapshot_interval(self) -> int:
        """Number of events between automatic snapshots."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get("snapshot_interval", 10)

    @property
    def event_sourcing_max_events_before_compaction(self) -> int:
        """Maximum events before the store considers compaction."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get(
            "max_events_before_compaction", 1000
        )

    @property
    def event_sourcing_enable_temporal_queries(self) -> bool:
        """Whether point-in-time state reconstruction is available."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get(
            "enable_temporal_queries", True
        )

    @property
    def event_sourcing_enable_projections(self) -> bool:
        """Whether materialized read-model projections are maintained."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get("enable_projections", True)

    @property
    def event_sourcing_event_version(self) -> int:
        """Current event schema version for upcasting."""
        self._ensure_loaded()
        return self._raw_config.get("event_sourcing", {}).get("event_version", 1)

