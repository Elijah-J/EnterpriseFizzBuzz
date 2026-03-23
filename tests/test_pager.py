"""
Enterprise FizzBuzz Platform - FizzPager Incident Paging Engine Test Suite

Comprehensive tests for the Incident Paging & Escalation Engine.
Validates the PagerDuty-style incident lifecycle, four-tier escalation
chain, alert deduplication and correlation, noise reduction, on-call
scheduling, incident commander assignment, blameless postmortem
generation, ASCII dashboard rendering, and middleware pipeline
integration.  Because every FizzBuzz evaluation deserves 24/7 incident
response.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizz_pager import (
    Alert,
    AlertCorrelator,
    AlertDeduplicator,
    AlertType,
    CORRELATION_WINDOW_SECONDS,
    DEDUP_WINDOW_SECONDS,
    DEFAULT_ESCALATION_TIMEOUTS,
    ESCALATION_ROSTER,
    EscalationManager,
    EscalationRecord,
    EscalationTier,
    FLAP_DETECTION_THRESHOLD,
    FLAP_DETECTION_WINDOW,
    HIGH_VOLUME_THRESHOLD,
    HIGH_VOLUME_WINDOW_SECONDS,
    Incident,
    IncidentCommander,
    IncidentSeverity,
    IncidentState,
    IncidentTimeline,
    NoiseReducer,
    OnCallSchedule,
    PagerDashboard,
    PagerEngine,
    PagerMetrics,
    PagerMiddleware,
    PostmortemReport,
    SEVERITY_SLA_TARGETS,
    SEVERITY_WEIGHTS,
    TimelineEntry,
    VALID_STATE_TRANSITIONS,
    create_pager_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    PagerAlertError,
    PagerCorrelationError,
    PagerDashboardError,
    PagerDeduplicationError,
    PagerError,
    PagerEscalationError,
    PagerIncidentError,
    PagerMiddlewareError,
    PagerScheduleError,
)
from config import _SingletonMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


# ============================================================
# IncidentSeverity Enum Tests
# ============================================================


class TestIncidentSeverity:
    """Validate incident severity enumeration values."""

    def test_p1_value(self):
        assert IncidentSeverity.P1.value == "P1"

    def test_p2_value(self):
        assert IncidentSeverity.P2.value == "P2"

    def test_p3_value(self):
        assert IncidentSeverity.P3.value == "P3"

    def test_p4_value(self):
        assert IncidentSeverity.P4.value == "P4"

    def test_p5_value(self):
        assert IncidentSeverity.P5.value == "P5"

    def test_severity_count(self):
        assert len(IncidentSeverity) == 5


# ============================================================
# IncidentState Enum Tests
# ============================================================


class TestIncidentState:
    """Validate incident lifecycle state enumeration values."""

    def test_triggered_value(self):
        assert IncidentState.TRIGGERED.value == "triggered"

    def test_acknowledged_value(self):
        assert IncidentState.ACKNOWLEDGED.value == "acknowledged"

    def test_investigating_value(self):
        assert IncidentState.INVESTIGATING.value == "investigating"

    def test_mitigating_value(self):
        assert IncidentState.MITIGATING.value == "mitigating"

    def test_resolved_value(self):
        assert IncidentState.RESOLVED.value == "resolved"

    def test_postmortem_value(self):
        assert IncidentState.POSTMORTEM.value == "postmortem"

    def test_closed_value(self):
        assert IncidentState.CLOSED.value == "closed"

    def test_state_count(self):
        assert len(IncidentState) == 7


# ============================================================
# EscalationTier Enum Tests
# ============================================================


class TestEscalationTier:
    """Validate escalation tier enumeration values."""

    def test_l1_value(self):
        assert EscalationTier.L1.value == "L1"

    def test_l2_value(self):
        assert EscalationTier.L2.value == "L2"

    def test_l3_value(self):
        assert EscalationTier.L3.value == "L3"

    def test_l4_value(self):
        assert EscalationTier.L4.value == "L4"

    def test_tier_count(self):
        assert len(EscalationTier) == 4


# ============================================================
# AlertType Enum Tests
# ============================================================


class TestAlertType:
    """Validate alert type enumeration values."""

    def test_classification_value(self):
        assert AlertType.CLASSIFICATION.value == "classification"

    def test_cache_value(self):
        assert AlertType.CACHE.value == "cache"

    def test_custom_value(self):
        assert AlertType.CUSTOM.value == "custom"

    def test_alert_type_count(self):
        assert len(AlertType) == 10


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate FizzPager constants and configuration values."""

    def test_escalation_roster_has_all_tiers(self):
        for tier in EscalationTier:
            assert tier in ESCALATION_ROSTER

    def test_escalation_roster_all_bob(self):
        for tier in EscalationTier:
            assert "Bob" in ESCALATION_ROSTER[tier]["name"]

    def test_valid_state_transitions_triggered(self):
        assert VALID_STATE_TRANSITIONS[IncidentState.TRIGGERED] == [IncidentState.ACKNOWLEDGED]

    def test_valid_state_transitions_closed_is_terminal(self):
        assert VALID_STATE_TRANSITIONS[IncidentState.CLOSED] == []

    def test_valid_state_transitions_postmortem_can_reopen(self):
        targets = VALID_STATE_TRANSITIONS[IncidentState.POSTMORTEM]
        assert IncidentState.INVESTIGATING in targets
        assert IncidentState.CLOSED in targets

    def test_severity_weights_p1_highest(self):
        assert SEVERITY_WEIGHTS[IncidentSeverity.P1] > SEVERITY_WEIGHTS[IncidentSeverity.P5]

    def test_default_escalation_timeouts_l1(self):
        assert DEFAULT_ESCALATION_TIMEOUTS[EscalationTier.L1] == 300.0

    def test_default_escalation_timeouts_l4_infinite(self):
        assert DEFAULT_ESCALATION_TIMEOUTS[EscalationTier.L4] == float("inf")

    def test_severity_sla_targets_p1_fastest(self):
        assert SEVERITY_SLA_TARGETS[IncidentSeverity.P1]["ack_seconds"] < SEVERITY_SLA_TARGETS[IncidentSeverity.P5]["ack_seconds"]


# ============================================================
# Alert Dataclass Tests
# ============================================================


class TestAlert:
    """Validate Alert dataclass behavior."""

    def test_default_alert_creation(self):
        alert = Alert(subsystem="cache", title="test alert")
        assert alert.subsystem == "cache"
        assert alert.title == "test alert"
        assert alert.alert_id != ""

    def test_dedup_key_auto_generated(self):
        alert = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="coherence")
        assert alert.dedup_key != ""
        assert len(alert.dedup_key) == 16

    def test_dedup_key_deterministic(self):
        a1 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="coherence", dedup_key="")
        a2 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="coherence", dedup_key="")
        assert a1.dedup_key == a2.dedup_key

    def test_dedup_key_differs_by_severity(self):
        a1 = Alert(subsystem="cache", severity=IncidentSeverity.P1, source="coherence")
        a2 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="coherence")
        assert a1.dedup_key != a2.dedup_key

    def test_to_dict(self):
        alert = Alert(subsystem="cache", title="test", severity=IncidentSeverity.P3)
        d = alert.to_dict()
        assert d["subsystem"] == "cache"
        assert d["severity"] == "P3"
        assert "alert_id" in d


# ============================================================
# TimelineEntry Dataclass Tests
# ============================================================


class TestTimelineEntry:
    """Validate TimelineEntry dataclass behavior."""

    def test_default_timeline_entry(self):
        entry = TimelineEntry(action="test_action", detail="detail text")
        assert entry.action == "test_action"
        assert entry.actor == "Bob"

    def test_to_dict(self):
        entry = TimelineEntry(action="acknowledged", actor="Bob")
        d = entry.to_dict()
        assert d["action"] == "acknowledged"
        assert d["actor"] == "Bob"


# ============================================================
# EscalationRecord Dataclass Tests
# ============================================================


class TestEscalationRecord:
    """Validate EscalationRecord dataclass behavior."""

    def test_default_record(self):
        record = EscalationRecord()
        assert record.from_tier == EscalationTier.L1
        assert record.to_tier == EscalationTier.L2
        assert record.responder == "Bob"

    def test_to_dict(self):
        record = EscalationRecord(from_tier=EscalationTier.L2, to_tier=EscalationTier.L3)
        d = record.to_dict()
        assert d["from_tier"] == "L2"
        assert d["to_tier"] == "L3"


# ============================================================
# Incident Dataclass Tests
# ============================================================


class TestIncident:
    """Validate Incident dataclass behavior."""

    def test_default_incident(self):
        incident = Incident(title="test incident")
        assert incident.state == IncidentState.TRIGGERED
        assert incident.severity == IncidentSeverity.P3
        assert incident.commander == "Bob"

    def test_mtta_before_acknowledgment(self):
        incident = Incident()
        assert incident.mtta() == 0.0

    def test_mttr_before_resolution(self):
        incident = Incident()
        assert incident.mttr() == 0.0

    def test_add_timeline_entry(self):
        incident = Incident()
        entry = incident.add_timeline_entry(action="test", detail="detail")
        assert len(incident.timeline) == 1
        assert entry.action == "test"

    def test_to_dict(self):
        incident = Incident(title="test", severity=IncidentSeverity.P1)
        d = incident.to_dict()
        assert d["severity"] == "P1"
        assert d["commander"] == "Bob"

    def test_elapsed_seconds(self):
        incident = Incident()
        elapsed = incident.elapsed_seconds()
        assert elapsed >= 0.0


# ============================================================
# PostmortemReport Dataclass Tests
# ============================================================


class TestPostmortemReport:
    """Validate PostmortemReport dataclass behavior."""

    def test_default_report(self):
        report = PostmortemReport(incident_id="test-123", summary="test postmortem")
        assert report.incident_id == "test-123"
        assert report.commander == "Bob"

    def test_to_dict(self):
        report = PostmortemReport(incident_id="test-123", severity=IncidentSeverity.P2)
        d = report.to_dict()
        assert d["severity"] == "P2"
        assert d["commander"] == "Bob"


# ============================================================
# AlertDeduplicator Tests
# ============================================================


class TestAlertDeduplicator:
    """Validate alert deduplication logic."""

    def test_first_alert_not_suppressed(self):
        dedup = AlertDeduplicator()
        alert = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="coherence")
        result = dedup.process(alert)
        assert not result.suppressed

    def test_duplicate_alert_suppressed(self):
        dedup = AlertDeduplicator()
        ts = time.monotonic()
        a1 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="coherence", timestamp=ts)
        a2 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="coherence", timestamp=ts + 1)
        dedup.process(a1)
        result = dedup.process(a2)
        assert result.suppressed

    def test_dedup_count_increments(self):
        dedup = AlertDeduplicator()
        ts = time.monotonic()
        a1 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="x", timestamp=ts)
        a2 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="x", timestamp=ts + 1)
        dedup.process(a1)
        dedup.process(a2)
        assert dedup.dedup_count == 1
        assert dedup.total_received == 2

    def test_different_sources_not_deduplicated(self):
        dedup = AlertDeduplicator()
        ts = time.monotonic()
        a1 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="x", timestamp=ts)
        a2 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="y", timestamp=ts + 1)
        dedup.process(a1)
        result = dedup.process(a2)
        assert not result.suppressed

    def test_expired_key_allows_new_alert(self):
        dedup = AlertDeduplicator(window_seconds=10.0)
        ts = time.monotonic()
        a1 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="x", timestamp=ts)
        a2 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="x", timestamp=ts + 20)
        dedup.process(a1)
        result = dedup.process(a2)
        assert not result.suppressed

    def test_dedup_ratio(self):
        dedup = AlertDeduplicator()
        ts = time.monotonic()
        for i in range(5):
            dedup.process(Alert(subsystem="cache", severity=IncidentSeverity.P2, source="x", timestamp=ts + i))
        assert dedup.dedup_ratio() == 4 / 5

    def test_invalid_window_raises(self):
        with pytest.raises(PagerDeduplicationError):
            AlertDeduplicator(window_seconds=-1)

    def test_reset_clears_state(self):
        dedup = AlertDeduplicator()
        dedup.process(Alert(subsystem="cache", source="x"))
        dedup.reset()
        assert dedup.total_received == 0
        assert dedup.active_key_count == 0

    def test_get_stats(self):
        dedup = AlertDeduplicator()
        stats = dedup.get_stats()
        assert "total_received" in stats
        assert "dedup_ratio" in stats


# ============================================================
# AlertCorrelator Tests
# ============================================================


class TestAlertCorrelator:
    """Validate alert correlation logic."""

    def test_no_correlation_without_incidents(self):
        correlator = AlertCorrelator()
        alert = Alert(subsystem="cache")
        result = correlator.find_correlated_incident(alert, {})
        assert result is None

    def test_correlation_with_matching_subsystem(self):
        correlator = AlertCorrelator()
        ts = time.monotonic()
        incident = Incident(incident_id="inc-1", subsystem="cache", created_at=ts)
        correlator.register_incident(incident)
        alert = Alert(subsystem="cache", timestamp=ts + 10)
        result = correlator.find_correlated_incident(alert, {"inc-1": incident})
        assert result == "inc-1"

    def test_no_correlation_different_subsystem(self):
        correlator = AlertCorrelator()
        ts = time.monotonic()
        incident = Incident(incident_id="inc-1", subsystem="cache", created_at=ts)
        correlator.register_incident(incident)
        alert = Alert(subsystem="consensus", timestamp=ts + 10)
        result = correlator.find_correlated_incident(alert, {"inc-1": incident})
        assert result is None

    def test_invalid_window_raises(self):
        with pytest.raises(PagerCorrelationError):
            AlertCorrelator(window_seconds=0)

    def test_unregister_incident(self):
        correlator = AlertCorrelator()
        incident = Incident(incident_id="inc-1", subsystem="cache")
        correlator.register_incident(incident)
        correlator.unregister_incident("inc-1")
        stats = correlator.get_stats()
        assert stats["tracked_incidents"] == 0

    def test_get_stats(self):
        correlator = AlertCorrelator()
        stats = correlator.get_stats()
        assert "correlations_made" in stats


# ============================================================
# NoiseReducer Tests
# ============================================================


class TestNoiseReducer:
    """Validate noise reduction logic."""

    def test_normal_alert_not_suppressed(self):
        reducer = NoiseReducer()
        alert = Alert(subsystem="cache", source="coherence")
        result = reducer.process(alert)
        assert not result.suppressed

    def test_already_suppressed_passes_through(self):
        reducer = NoiseReducer()
        alert = Alert(subsystem="cache", source="coherence", suppressed=True)
        result = reducer.process(alert)
        assert result.suppressed

    def test_flapping_detection(self):
        reducer = NoiseReducer(flap_threshold=3, flap_window=10)
        ts = time.monotonic()
        suppressed = False
        for i in range(5):
            alert = Alert(subsystem="cache", source="coherence", timestamp=ts + i)
            result = reducer.process(alert)
            if result.suppressed:
                suppressed = True
        assert suppressed
        assert reducer.flap_detections > 0

    def test_bob_overload_suppresses_low_severity(self):
        reducer = NoiseReducer(flap_threshold=100, volume_threshold=1000)
        reducer.set_bob_overload(True)
        alert = Alert(subsystem="cache", source="unique_source_1", severity=IncidentSeverity.P4)
        result = reducer.process(alert)
        assert result.suppressed

    def test_bob_overload_does_not_suppress_p1(self):
        reducer = NoiseReducer(flap_threshold=100, volume_threshold=1000)
        reducer.set_bob_overload(True)
        alert = Alert(subsystem="cache", source="unique_src_p1", severity=IncidentSeverity.P1)
        result = reducer.process(alert)
        assert not result.suppressed

    def test_reset_clears_state(self):
        reducer = NoiseReducer()
        reducer.set_bob_overload(True)
        reducer.reset()
        assert not reducer.bob_overload

    def test_get_stats(self):
        reducer = NoiseReducer()
        stats = reducer.get_stats()
        assert "suppressed_count" in stats
        assert "bob_overload" in stats


# ============================================================
# EscalationManager Tests
# ============================================================


class TestEscalationManager:
    """Validate escalation management logic."""

    def test_next_tier_from_l1(self):
        manager = EscalationManager()
        assert manager.next_tier(EscalationTier.L1) == EscalationTier.L2

    def test_next_tier_from_l4_is_none(self):
        manager = EscalationManager()
        assert manager.next_tier(EscalationTier.L4) is None

    def test_get_responder_l1_is_bob(self):
        manager = EscalationManager()
        responder = manager.get_responder(EscalationTier.L1)
        assert responder["name"] == "Bob"

    def test_get_responder_l4_is_evp_bob(self):
        manager = EscalationManager()
        responder = manager.get_responder(EscalationTier.L4)
        assert responder["name"] == "EVP Bob"

    def test_escalate_moves_tier(self):
        manager = EscalationManager()
        incident = Incident(state=IncidentState.TRIGGERED, current_tier=EscalationTier.L1)
        record = manager.escalate(incident)
        assert incident.current_tier == EscalationTier.L2
        assert record.from_tier == EscalationTier.L1
        assert record.to_tier == EscalationTier.L2

    def test_escalate_at_l4_raises(self):
        manager = EscalationManager()
        incident = Incident(state=IncidentState.TRIGGERED, current_tier=EscalationTier.L4)
        with pytest.raises(PagerEscalationError):
            manager.escalate(incident)

    def test_should_escalate_false_if_acknowledged(self):
        manager = EscalationManager()
        incident = Incident(state=IncidentState.ACKNOWLEDGED)
        assert not manager.should_escalate(incident, time.monotonic() + 1000)

    def test_get_stats(self):
        manager = EscalationManager()
        stats = manager.get_stats()
        assert "escalation_count" in stats


# ============================================================
# IncidentCommander Tests
# ============================================================


class TestIncidentCommander:
    """Validate incident commander assignment logic."""

    def test_default_commander_is_bob(self):
        commander = IncidentCommander()
        assert commander.assign() == "Bob"

    def test_round_robin_with_single_member(self):
        commander = IncidentCommander()
        for _ in range(10):
            assert commander.assign() == "Bob"

    def test_assign_updates_incident(self):
        commander = IncidentCommander()
        incident = Incident()
        name = commander.assign(incident)
        assert incident.commander == name
        assert len(incident.timeline) == 1

    def test_assignment_count(self):
        commander = IncidentCommander()
        commander.assign()
        commander.assign()
        assert commander.assignment_count == 2

    def test_team_roster(self):
        commander = IncidentCommander(team=["Bob"])
        assert commander.team == ["Bob"]

    def test_get_stats(self):
        commander = IncidentCommander()
        stats = commander.get_stats()
        assert stats["team_size"] == 1


# ============================================================
# OnCallSchedule Tests
# ============================================================


class TestOnCallSchedule:
    """Validate on-call schedule rotation logic."""

    def test_default_oncall_is_bob(self):
        schedule = OnCallSchedule()
        assert schedule.get_current_oncall() == "Bob"

    def test_oncall_with_single_roster_always_bob(self):
        schedule = OnCallSchedule(roster=["Bob"])
        for epoch in [0, 3600, 86400, 604800, 1000000]:
            assert schedule.get_current_oncall(epoch) == "Bob"

    def test_rotation_formula(self):
        """The rotation formula (epoch_hours // 168) % 1 always yields 0."""
        schedule = OnCallSchedule(roster=["Bob"], rotation_hours=168)
        for epoch in range(0, 1000000, 100000):
            assert schedule.get_current_oncall(float(epoch)) == "Bob"

    def test_override(self):
        schedule = OnCallSchedule()
        epoch = time.time()
        schedule.set_override(epoch, "Bob")
        assert schedule.get_current_oncall(epoch) == "Bob"

    def test_empty_roster_raises(self):
        with pytest.raises(PagerScheduleError):
            OnCallSchedule(roster=[])

    def test_invalid_rotation_raises(self):
        with pytest.raises(PagerScheduleError):
            OnCallSchedule(rotation_hours=0)

    def test_get_rotation_schedule(self):
        schedule = OnCallSchedule()
        result = schedule.get_rotation_schedule(0, hours=336)
        assert len(result) >= 2
        for shift in result:
            assert shift["responder"] == "Bob"

    def test_get_stats(self):
        schedule = OnCallSchedule()
        stats = schedule.get_stats()
        assert stats["roster_size"] == 1


# ============================================================
# IncidentTimeline Tests
# ============================================================


class TestIncidentTimeline:
    """Validate incident timeline reconstruction logic."""

    def test_register_and_reconstruct(self):
        timeline = IncidentTimeline()
        incident = Incident(incident_id="inc-1")
        incident.add_timeline_entry(action="created")
        timeline.register_incident(incident)
        entries = timeline.reconstruct("inc-1")
        assert len(entries) >= 1

    def test_reconstruct_unknown_incident_raises(self):
        timeline = IncidentTimeline()
        with pytest.raises(PagerIncidentError):
            timeline.reconstruct("nonexistent")

    def test_annotate(self):
        timeline = IncidentTimeline()
        incident = Incident(incident_id="inc-1")
        timeline.register_incident(incident)
        timeline.annotate("inc-1", "Root cause was FizzBuzz complexity")
        entries = timeline.reconstruct("inc-1")
        annotations = [e for e in entries if e["action"] == "annotated"]
        assert len(annotations) == 1

    def test_reconstruction_count(self):
        timeline = IncidentTimeline()
        incident = Incident(incident_id="inc-1")
        timeline.register_incident(incident)
        timeline.reconstruct("inc-1")
        timeline.reconstruct("inc-1")
        assert timeline.reconstruction_count == 2


# ============================================================
# PagerMetrics Tests
# ============================================================


class TestPagerMetrics:
    """Validate pager metrics collection logic."""

    def test_initial_state(self):
        metrics = PagerMetrics()
        assert metrics.incidents_created == 0
        assert metrics.mean_mtta() == 0.0
        assert metrics.mean_mttr() == 0.0

    def test_record_incident_created(self):
        metrics = PagerMetrics()
        incident = Incident(severity=IncidentSeverity.P2)
        metrics.record_incident_created(incident)
        assert metrics.incidents_created == 1

    def test_record_alert(self):
        metrics = PagerMetrics()
        metrics.record_alert(suppressed=False)
        metrics.record_alert(suppressed=True)
        assert metrics.alert_noise_ratio() == 0.5

    def test_severity_distribution(self):
        metrics = PagerMetrics()
        metrics.record_incident_created(Incident(severity=IncidentSeverity.P1))
        metrics.record_incident_created(Incident(severity=IncidentSeverity.P1))
        metrics.record_incident_created(Incident(severity=IncidentSeverity.P3))
        dist = metrics.severity_distribution()
        assert dist["P1"] == 2
        assert dist["P3"] == 1

    def test_reset(self):
        metrics = PagerMetrics()
        metrics.record_incident_created(Incident())
        metrics.reset()
        assert metrics.incidents_created == 0

    def test_get_summary(self):
        metrics = PagerMetrics()
        summary = metrics.get_summary()
        assert "incidents_created" in summary
        assert "mean_mtta_seconds" in summary


# ============================================================
# PagerEngine Tests
# ============================================================


class TestPagerEngine:
    """Validate the PagerEngine core orchestration logic."""

    def test_ingest_alert_creates_incident(self):
        engine = PagerEngine(auto_acknowledge=False, auto_resolve=False)
        alert = Alert(subsystem="cache", severity=IncidentSeverity.P2, title="test")
        incident = engine.ingest_alert(alert)
        assert incident is not None
        assert incident.state == IncidentState.TRIGGERED

    def test_auto_acknowledge_mtta_zero(self):
        engine = PagerEngine(auto_acknowledge=True, auto_resolve=False)
        alert = Alert(subsystem="cache", severity=IncidentSeverity.P2, title="test")
        incident = engine.ingest_alert(alert)
        assert incident.state == IncidentState.ACKNOWLEDGED
        assert incident.mtta() == 0.0

    def test_auto_resolve_full_lifecycle(self):
        engine = PagerEngine(auto_acknowledge=True, auto_resolve=True)
        alert = Alert(subsystem="cache", severity=IncidentSeverity.P2, title="test")
        incident = engine.ingest_alert(alert)
        assert incident.state == IncidentState.CLOSED
        assert incident.postmortem is not None

    def test_suppressed_alert_returns_none(self):
        engine = PagerEngine()
        ts = time.monotonic()
        a1 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="x", timestamp=ts)
        a2 = Alert(subsystem="cache", severity=IncidentSeverity.P2, source="x", timestamp=ts + 1)
        engine.ingest_alert(a1)
        result = engine.ingest_alert(a2)
        assert result is None

    def test_simulate_evaluation_incident(self):
        engine = PagerEngine(simulate_incident=True)
        incident = engine.simulate_evaluation_incident(42)
        assert incident is not None
        assert incident.state == IncidentState.CLOSED

    def test_transition_incident_valid(self):
        engine = PagerEngine(auto_acknowledge=False, auto_resolve=False)
        alert = Alert(subsystem="cache", title="test")
        incident = engine.ingest_alert(alert)
        updated = engine.transition_incident(
            incident.incident_id, IncidentState.ACKNOWLEDGED
        )
        assert updated.state == IncidentState.ACKNOWLEDGED

    def test_transition_incident_invalid_raises(self):
        engine = PagerEngine(auto_acknowledge=False, auto_resolve=False)
        alert = Alert(subsystem="cache", title="test")
        incident = engine.ingest_alert(alert)
        with pytest.raises(PagerIncidentError):
            engine.transition_incident(
                incident.incident_id, IncidentState.RESOLVED
            )

    def test_transition_unknown_incident_raises(self):
        engine = PagerEngine()
        with pytest.raises(PagerIncidentError):
            engine.transition_incident("nonexistent", IncidentState.ACKNOWLEDGED)

    def test_get_active_incidents(self):
        engine = PagerEngine(auto_acknowledge=True, auto_resolve=False)
        alert = Alert(subsystem="cache", title="test")
        engine.ingest_alert(alert)
        active = engine.get_active_incidents()
        assert len(active) == 1

    def test_get_active_incidents_empty_after_close(self):
        engine = PagerEngine(auto_acknowledge=True, auto_resolve=True)
        alert = Alert(subsystem="cache", title="test")
        engine.ingest_alert(alert)
        active = engine.get_active_incidents()
        assert len(active) == 0

    def test_get_stats(self):
        engine = PagerEngine()
        stats = engine.get_stats()
        assert "dedup" in stats
        assert "metrics" in stats

    def test_postmortem_has_contributing_factors(self):
        engine = PagerEngine(auto_acknowledge=True, auto_resolve=True)
        alert = Alert(subsystem="cache", severity=IncidentSeverity.P1, title="critical failure")
        incident = engine.ingest_alert(alert)
        assert incident.postmortem is not None
        assert len(incident.postmortem.contributing_factors) > 0
        assert len(incident.postmortem.corrective_actions) > 0

    def test_postmortem_commander_is_bob(self):
        engine = PagerEngine(auto_acknowledge=True, auto_resolve=True)
        alert = Alert(subsystem="cache", title="test")
        incident = engine.ingest_alert(alert)
        assert incident.postmortem.commander == "Bob"

    def test_incident_timeline_populated(self):
        engine = PagerEngine(auto_acknowledge=True, auto_resolve=True)
        alert = Alert(subsystem="cache", title="test")
        incident = engine.ingest_alert(alert)
        # Full lifecycle should produce multiple timeline entries
        assert len(incident.timeline) >= 5


# ============================================================
# PagerMiddleware Tests
# ============================================================


class TestPagerMiddleware:
    """Validate PagerMiddleware pipeline integration."""

    def _make_context(self, number: int = 42) -> ProcessingContext:
        return ProcessingContext(
            number=number,
            session_id="test-session",
            results=[FizzBuzzResult(
                number=number,
                output="FizzBuzz",
            )],
        )

    def _identity_handler(self, context: ProcessingContext) -> ProcessingContext:
        return context

    def test_middleware_name(self):
        engine = PagerEngine()
        mw = PagerMiddleware(engine=engine)
        assert mw.get_name() == "PagerMiddleware"

    def test_middleware_priority(self):
        engine = PagerEngine()
        mw = PagerMiddleware(engine=engine)
        assert mw.get_priority() == 82

    def test_middleware_with_simulation(self):
        engine = PagerEngine(simulate_incident=True)
        mw = PagerMiddleware(engine=engine)
        ctx = self._make_context(42)
        result = mw.process(ctx, self._identity_handler)
        assert "pager_incident_id" in result.metadata
        assert "pager_mtta" in result.metadata

    def test_middleware_without_simulation(self):
        engine = PagerEngine(simulate_incident=False)
        mw = PagerMiddleware(engine=engine)
        ctx = self._make_context(42)
        result = mw.process(ctx, self._identity_handler)
        assert "pager_oncall" in result.metadata
        assert result.metadata["pager_oncall"] == "Bob"

    def test_middleware_injects_total_incidents(self):
        engine = PagerEngine(simulate_incident=True)
        mw = PagerMiddleware(engine=engine)
        ctx = self._make_context(1)
        result = mw.process(ctx, self._identity_handler)
        assert "pager_total_incidents" in result.metadata


# ============================================================
# PagerDashboard Tests
# ============================================================


class TestPagerDashboard:
    """Validate FizzPager ASCII dashboard rendering."""

    def test_render_empty_dashboard(self):
        engine = PagerEngine()
        dashboard = PagerDashboard.render(engine, width=72)
        assert "FIZZPAGER" in dashboard
        assert "ESCALATION CHAIN" in dashboard
        assert "no active incidents" in dashboard

    def test_render_with_incident(self):
        engine = PagerEngine(auto_acknowledge=True, auto_resolve=False)
        alert = Alert(subsystem="cache", severity=IncidentSeverity.P1, title="critical")
        engine.ingest_alert(alert)
        dashboard = PagerDashboard.render(engine, width=72)
        assert "P1" in dashboard

    def test_render_with_postmortem(self):
        engine = PagerEngine(auto_acknowledge=True, auto_resolve=True)
        alert = Alert(subsystem="cache", title="test incident")
        engine.ingest_alert(alert)
        dashboard = PagerDashboard.render(engine, width=72)
        assert "POSTMORTEM" in dashboard

    def test_render_includes_bob_on_call(self):
        engine = PagerEngine()
        dashboard = PagerDashboard.render(engine)
        assert "Bob" in dashboard

    def test_render_custom_width(self):
        engine = PagerEngine()
        dashboard = PagerDashboard.render(engine, width=90)
        assert "FIZZPAGER" in dashboard


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreatePagerSubsystem:
    """Validate the create_pager_subsystem factory function."""

    def test_returns_engine_and_middleware(self):
        engine, middleware = create_pager_subsystem()
        assert isinstance(engine, PagerEngine)
        assert isinstance(middleware, PagerMiddleware)

    def test_custom_severity(self):
        engine, middleware = create_pager_subsystem(default_severity="P1")
        assert engine.default_severity == IncidentSeverity.P1

    def test_invalid_severity_defaults_to_p3(self):
        engine, middleware = create_pager_subsystem(default_severity="INVALID")
        assert engine.default_severity == IncidentSeverity.P3

    def test_simulate_incident(self):
        engine, middleware = create_pager_subsystem(simulate_incident=True)
        assert engine.simulate_incident is True

    def test_enable_dashboard(self):
        engine, middleware = create_pager_subsystem(enable_dashboard=True)
        assert middleware.enable_dashboard is True

    def test_custom_team(self):
        engine, middleware = create_pager_subsystem(team=["Bob"])
        assert engine.commander_assigner.team == ["Bob"]

    def test_custom_roster(self):
        engine, middleware = create_pager_subsystem(roster=["Bob"])
        assert engine.schedule.roster == ["Bob"]


# ============================================================
# Exception Tests
# ============================================================


class TestPagerExceptions:
    """Validate FizzPager exception hierarchy and error codes."""

    def test_pager_error_base(self):
        exc = PagerError("test error")
        assert "test error" in str(exc)

    def test_pager_alert_error(self):
        exc = PagerAlertError("alert-123", "processing failed")
        assert exc.alert_id == "alert-123"
        assert "EFP-PGR1" in str(exc.error_code)

    def test_pager_deduplication_error(self):
        exc = PagerDeduplicationError("key-abc", "invalid window")
        assert exc.dedup_key == "key-abc"

    def test_pager_correlation_error(self):
        exc = PagerCorrelationError("corr-key", "timeout")
        assert exc.correlation_key == "corr-key"

    def test_pager_escalation_error(self):
        exc = PagerEscalationError("inc-1", "L4", "terminal tier")
        assert exc.incident_id == "inc-1"

    def test_pager_incident_error(self):
        exc = PagerIncidentError("inc-1", "invalid transition")
        assert exc.incident_id == "inc-1"

    def test_pager_schedule_error(self):
        exc = PagerScheduleError("roster", "empty roster")
        assert exc.schedule_key == "roster"

    def test_pager_dashboard_error(self):
        exc = PagerDashboardError("header", "render failed")
        assert exc.panel == "header"

    def test_pager_middleware_error(self):
        exc = PagerMiddlewareError(42, "pipeline error")
        assert exc.evaluation_number == 42

    def test_exception_hierarchy(self):
        """All pager exceptions inherit from PagerError."""
        assert issubclass(PagerAlertError, PagerError)
        assert issubclass(PagerDeduplicationError, PagerError)
        assert issubclass(PagerCorrelationError, PagerError)
        assert issubclass(PagerEscalationError, PagerError)
        assert issubclass(PagerIncidentError, PagerError)
        assert issubclass(PagerScheduleError, PagerError)
        assert issubclass(PagerDashboardError, PagerError)
        assert issubclass(PagerMiddlewareError, PagerError)
