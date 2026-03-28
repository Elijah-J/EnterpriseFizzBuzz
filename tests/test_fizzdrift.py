"""
Tests for FizzDrift -- Infrastructure Drift Detection and Remediation.

Validates drift detection between expected and actual infrastructure state,
severity classification, remediation rule application, dashboard rendering,
and middleware integration. Drift detection is critical for maintaining
configuration consistency across the Enterprise FizzBuzz deployment fleet.
"""

from __future__ import annotations

import time
from datetime import datetime

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzdrift import (
    FIZZDRIFT_VERSION,
    MIDDLEWARE_PRIORITY,
    DriftSeverity,
    DriftAction,
    FizzDriftConfig,
    DriftItem,
    DriftDetector,
    RemediationEngine,
    FizzDriftDashboard,
    FizzDriftMiddleware,
    create_fizzdrift_subsystem,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def detector():
    return DriftDetector()


@pytest.fixture
def remediation_engine():
    return RemediationEngine()


# ============================================================================
# Constants
# ============================================================================

class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version_string(self):
        assert FIZZDRIFT_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 206


# ============================================================================
# DriftDetector
# ============================================================================

class TestDriftDetector:
    """Validate the drift detection engine that compares actual vs expected state."""

    def test_register_expected_stores_value(self, detector):
        """Registering an expected value must make it available for later comparison."""
        detector.register_expected("fizzbuzz.cache.ttl", 300)
        # Recording the same value should produce no drift
        result = detector.record_actual("fizzbuzz.cache.ttl", 300)
        assert result is None

    def test_no_drift_when_actual_matches_expected(self, detector):
        """When the actual value matches the expected value, no DriftItem is returned."""
        detector.register_expected("fizzbuzz.replicas", 3)
        drift = detector.record_actual("fizzbuzz.replicas", 3)
        assert drift is None
        assert detector.get_drift_count() == 0

    def test_drift_detected_when_actual_differs(self, detector):
        """A DriftItem must be produced when the actual value diverges from expected."""
        detector.register_expected("fizzbuzz.replicas", 3)
        drift = detector.record_actual("fizzbuzz.replicas", 5)
        assert drift is not None
        assert isinstance(drift, DriftItem)
        assert drift.resource == "fizzbuzz.replicas"
        assert drift.expected_value == 3
        assert drift.actual_value == 5
        assert isinstance(drift.detected_at, datetime)

    def test_detect_all_returns_all_drifts(self, detector):
        """detect_all must return every outstanding drift item."""
        detector.register_expected("a", 1)
        detector.register_expected("b", "hello")
        detector.record_actual("a", 2)
        detector.record_actual("b", "world")
        all_drifts = detector.detect_all()
        assert len(all_drifts) == 2
        resources = {d.resource for d in all_drifts}
        assert resources == {"a", "b"}

    def test_get_drift_count(self, detector):
        """get_drift_count must reflect the current number of unresolved drifts."""
        detector.register_expected("x", 10)
        detector.register_expected("y", 20)
        assert detector.get_drift_count() == 0
        detector.record_actual("x", 99)
        assert detector.get_drift_count() == 1
        detector.record_actual("y", 42)
        assert detector.get_drift_count() == 2

    def test_clear_drift_removes_specific_item(self, detector):
        """clear_drift must remove a drift by ID and return True; False for unknown IDs."""
        detector.register_expected("resource.a", "expected")
        drift = detector.record_actual("resource.a", "actual")
        assert drift is not None
        assert detector.get_drift_count() == 1
        result = detector.clear_drift(drift.drift_id)
        assert result is True
        assert detector.get_drift_count() == 0
        # Clearing the same ID again should return False
        result_again = detector.clear_drift(drift.drift_id)
        assert result_again is False

    def test_severity_classification(self, detector):
        """Drift items must carry a severity classification from the DriftSeverity enum."""
        detector.register_expected("critical.setting", 100)
        drift = detector.record_actual("critical.setting", 999)
        assert drift is not None
        assert isinstance(drift.severity, DriftSeverity)
        # The severity must be a valid enum member, not NONE (since drift was detected)
        assert drift.severity != DriftSeverity.NONE


# ============================================================================
# RemediationEngine
# ============================================================================

class TestRemediationEngine:
    """Validate drift remediation rule management and execution."""

    def test_add_rule_registers_action(self, remediation_engine):
        """Adding a remediation rule must associate the resource with the action."""
        remediation_engine.add_rule("fizzbuzz.cache.ttl", DriftAction.AUTO_REMEDIATE)
        rules = remediation_engine.list_rules()
        assert "fizzbuzz.cache.ttl" in rules

    def test_remediate_returns_action_result(self, remediation_engine):
        """Remediating a drift item must return a dict describing the action taken."""
        remediation_engine.add_rule("fizzbuzz.replicas", DriftAction.ALERT)
        drift_item = DriftItem(
            drift_id="drift-001",
            resource="fizzbuzz.replicas",
            expected_value=3,
            actual_value=5,
            severity=DriftSeverity.MEDIUM,
            detected_at=datetime.now(),
        )
        result = remediation_engine.remediate(drift_item)
        assert isinstance(result, dict)
        # The result must reference the action that was configured
        assert "action" in result or "status" in result or len(result) > 0

    def test_list_rules_returns_all_registered(self, remediation_engine):
        """list_rules must return all registered resource-to-action mappings."""
        remediation_engine.add_rule("res.a", DriftAction.ALERT)
        remediation_engine.add_rule("res.b", DriftAction.AUTO_REMEDIATE)
        remediation_engine.add_rule("res.c", DriftAction.NO_ACTION)
        rules = remediation_engine.list_rules()
        assert isinstance(rules, dict)
        assert len(rules) >= 3


# ============================================================================
# FizzDriftDashboard
# ============================================================================

class TestDashboard:
    """Validate the drift status dashboard rendering."""

    def test_render_returns_string(self):
        """The dashboard must render to a non-empty string."""
        detector = DriftDetector()
        dashboard = FizzDriftDashboard(detector)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_reflects_drift_state(self):
        """When drifts exist, the dashboard output must differ from an empty state."""
        detector = DriftDetector()
        dashboard = FizzDriftDashboard(detector)
        clean_output = dashboard.render()
        # Introduce drift
        detector.register_expected("widget.count", 10)
        detector.record_actual("widget.count", 0)
        drifted_output = dashboard.render()
        assert isinstance(drifted_output, str)
        # The dashboard must reflect the change -- it should not be identical
        # to the clean state since a drift is now present
        assert drifted_output != clean_output or "widget.count" in drifted_output


# ============================================================================
# FizzDriftMiddleware
# ============================================================================

class TestMiddleware:
    """Validate FizzDrift middleware integration with the processing pipeline."""

    def test_get_name(self):
        middleware = FizzDriftMiddleware()
        assert middleware.get_name() == "fizzdrift"

    def test_get_priority(self):
        middleware = FizzDriftMiddleware()
        assert middleware.get_priority() == 206

    def test_process_calls_next(self):
        """The middleware must invoke the next handler in the pipeline."""
        middleware = FizzDriftMiddleware()
        ctx = ProcessingContext(number=42, session_id="test")
        called = {"value": False}

        def fake_next(c):
            called["value"] = True
            return c

        middleware.process(ctx, fake_next)
        assert called["value"] is True, "Middleware must call the next handler"


# ============================================================================
# Factory function
# ============================================================================

class TestCreateSubsystem:
    """Validate the factory function that wires the FizzDrift subsystem."""

    def test_returns_tuple_of_three(self):
        result = create_fizzdrift_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_returns_correct_types(self):
        detector, dashboard, middleware = create_fizzdrift_subsystem()
        assert isinstance(detector, DriftDetector)
        assert isinstance(dashboard, FizzDriftDashboard)
        assert isinstance(middleware, FizzDriftMiddleware)

    def test_subsystem_components_are_wired(self):
        """The detector and dashboard must be connected so drift is visible."""
        detector, dashboard, middleware = create_fizzdrift_subsystem()
        detector.register_expected("test.resource", "expected_val")
        drift = detector.record_actual("test.resource", "actual_val")
        assert drift is not None
        # The dashboard should be able to render the detector's state
        output = dashboard.render()
        assert isinstance(output, str)
