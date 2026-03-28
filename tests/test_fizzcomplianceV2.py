"""
Enterprise FizzBuzz Platform - FizzCompliance v2 Test Suite

Validates the second-generation compliance automation subsystem with control
mapping and evidence collection. The original compliance module handled
SOX/GDPR/HIPAA at a regulatory level, but enterprise audit teams require
structured control mapping against recognized frameworks (SOC 2, ISO 27001,
PCI DSS, NIST 800-53) with formal evidence collection trails. This module
closes that gap by providing a ComplianceEngine that maintains a registry
of controls, assesses their status, collects evidence artifacts, and
generates framework-specific compliance reports with quantitative scoring.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzcomplianceV2 import (
    ComplianceEngine,
    Control,
    ControlStatus,
    FizzComplianceV2Config,
    FizzComplianceV2Dashboard,
    FizzComplianceV2Middleware,
    FIZZCOMPLIANCV2_VERSION,
    Framework,
    MIDDLEWARE_PRIORITY,
    create_fizzcompliancv2_subsystem,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def engine():
    return ComplianceEngine()


@pytest.fixture
def sample_control():
    return Control(
        control_id="CC-1.1",
        framework=Framework.SOC2,
        title="Logical Access Controls",
        description="Ensure logical access to FizzBuzz computation endpoints "
        "is restricted to authorized personnel.",
        status=ControlStatus.NOT_ASSESSED,
        evidence=[],
        last_assessed=None,
    )


@pytest.fixture
def pci_control():
    return Control(
        control_id="PCI-3.4",
        framework=Framework.PCI_DSS,
        title="Render PAN Unreadable",
        description="Mask FizzBuzz output tokens when transmitted across "
        "cardholder data environments.",
        status=ControlStatus.NOT_ASSESSED,
        evidence=[],
        last_assessed=None,
    )


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    def test_version_string(self):
        assert FIZZCOMPLIANCV2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 192


# ============================================================
# TestComplianceEngine
# ============================================================


class TestComplianceEngine:
    def test_add_control(self, engine, sample_control):
        """Adding a control returns the control and makes it retrievable."""
        result = engine.add_control(sample_control)
        assert result.control_id == "CC-1.1"
        assert result.framework == Framework.SOC2

    def test_assess_control_updates_status(self, engine, sample_control):
        """Assessing a control transitions it from NOT_ASSESSED and sets
        last_assessed timestamp."""
        engine.add_control(sample_control)
        assessed = engine.assess(sample_control.control_id)
        assert assessed.status != ControlStatus.NOT_ASSESSED
        assert assessed.last_assessed is not None
        assert isinstance(assessed.last_assessed, datetime)

    def test_list_controls_filters_by_framework(self, engine, sample_control, pci_control):
        """list_controls returns only controls matching the requested framework."""
        engine.add_control(sample_control)
        engine.add_control(pci_control)
        soc2_controls = engine.list_controls(Framework.SOC2)
        assert len(soc2_controls) == 1
        assert soc2_controls[0].control_id == "CC-1.1"

        pci_controls = engine.list_controls(Framework.PCI_DSS)
        assert len(pci_controls) == 1
        assert pci_controls[0].control_id == "PCI-3.4"

    def test_list_controls_empty_framework(self, engine, sample_control):
        """list_controls returns empty list for a framework with no controls."""
        engine.add_control(sample_control)
        result = engine.list_controls(Framework.ISO27001)
        assert result == []

    def test_compliance_score_all_compliant(self, engine):
        """Score is 1.0 when all controls for a framework are COMPLIANT."""
        for i in range(3):
            ctrl = Control(
                control_id=f"NIST-{i}",
                framework=Framework.NIST_800_53,
                title=f"NIST Control {i}",
                description="Test control.",
                status=ControlStatus.COMPLIANT,
                evidence=[f"evidence-{i}.pdf"],
                last_assessed=datetime.now(),
            )
            engine.add_control(ctrl)
        score = engine.get_compliance_score(Framework.NIST_800_53)
        assert score == 1.0

    def test_compliance_score_mixed_statuses(self, engine):
        """Score reflects the proportion of compliant controls."""
        statuses = [
            ControlStatus.COMPLIANT,
            ControlStatus.NON_COMPLIANT,
            ControlStatus.PARTIAL,
            ControlStatus.NOT_ASSESSED,
        ]
        for i, status in enumerate(statuses):
            ctrl = Control(
                control_id=f"SOC-{i}",
                framework=Framework.SOC2,
                title=f"SOC Control {i}",
                description="Test control.",
                status=status,
                evidence=[],
                last_assessed=None,
            )
            engine.add_control(ctrl)
        score = engine.get_compliance_score(Framework.SOC2)
        assert 0.0 <= score <= 1.0
        # At least one compliant, so score must be above zero
        assert score > 0.0
        # Not all compliant, so score must be below one
        assert score < 1.0

    def test_collect_evidence_appends(self, engine, sample_control):
        """collect_evidence appends evidence strings to the control's evidence list."""
        engine.add_control(sample_control)
        updated = engine.collect_evidence("CC-1.1", "audit-log-2026-03.csv")
        assert "audit-log-2026-03.csv" in updated.evidence
        updated2 = engine.collect_evidence("CC-1.1", "screenshot-access-review.png")
        assert len(updated2.evidence) == 2
        assert "screenshot-access-review.png" in updated2.evidence

    def test_generate_report_structure(self, engine, sample_control):
        """generate_report returns a dict with expected top-level keys."""
        engine.add_control(sample_control)
        engine.assess(sample_control.control_id)
        report = engine.generate_report(Framework.SOC2)
        assert isinstance(report, dict)
        # Report must contain at minimum the framework and controls information
        assert "framework" in report or "controls" in report or "score" in report
        # Verify it is non-empty
        assert len(report) > 0


# ============================================================
# TestDashboard
# ============================================================


class TestDashboard:
    def test_render_returns_string(self):
        dashboard = FizzComplianceV2Dashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_compliance_info(self):
        dashboard = FizzComplianceV2Dashboard()
        output = dashboard.render()
        lower = output.lower()
        assert "compliance" in lower or "control" in lower or "framework" in lower


# ============================================================
# TestMiddleware
# ============================================================


class TestMiddleware:
    def test_middleware_name(self):
        mw = FizzComplianceV2Middleware()
        assert mw.get_name() == "fizzcompliancv2"

    def test_middleware_priority(self):
        mw = FizzComplianceV2Middleware()
        assert mw.get_priority() == 192

    def test_middleware_process_calls_next(self):
        """The middleware must invoke the next handler in the pipeline."""
        mw = FizzComplianceV2Middleware()
        ctx = ProcessingContext(number=15, session_id="test-session")
        next_handler = MagicMock()
        mw.process(ctx, next_handler)
        next_handler.assert_called_once()


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    def test_returns_three_tuple(self):
        result = create_fizzcompliancv2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_engine_is_functional(self):
        engine, _, _ = create_fizzcompliancv2_subsystem()
        assert isinstance(engine, ComplianceEngine)
        ctrl = engine.add_control(Control(
            control_id="SUB-1",
            framework=Framework.ISO27001,
            title="Subsystem Test Control",
            description="Validates subsystem factory produces working engine.",
            status=ControlStatus.NOT_ASSESSED,
            evidence=[],
            last_assessed=None,
        ))
        assert ctrl.control_id == "SUB-1"

    def test_dashboard_is_functional(self):
        _, dashboard, _ = create_fizzcompliancv2_subsystem()
        assert isinstance(dashboard, FizzComplianceV2Dashboard)
        output = dashboard.render()
        assert isinstance(output, str)
