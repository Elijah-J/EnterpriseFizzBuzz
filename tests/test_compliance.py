"""
Enterprise FizzBuzz Platform - Compliance & Regulatory Framework Test Suite

Comprehensive tests for the SOX/GDPR/HIPAA compliance framework.
Because even compliance theatre deserves 100% test coverage. These
tests verify that:

- SOX segregation of duties prevents any single virtual employee from
  evaluating both Fizz AND Buzz (the horror!)
- GDPR consent is properly managed and THE COMPLIANCE PARADOX is
  reliably triggered by erasure requests
- HIPAA "encryption" (base64) is applied correctly and provides
  exactly zero actual security
- Bob McFizzington's stress level increases monotonically
- Data classification assigns the correct sensitivity level
- The compliance middleware integrates with the processing pipeline
- Erasure certificates are properly ironic
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from compliance import (
    ComplianceDashboard,
    ComplianceFramework,
    ComplianceMiddleware,
    DataClassificationEngine,
    GDPRController,
    HIPAAGuard,
    PersonnelAssignment,
    SOXAuditor,
)
from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    ComplianceError,
    ComplianceFrameworkNotEnabledError,
    ComplianceOfficerUnavailableError,
    GDPRConsentRequiredError,
    GDPRErasureParadoxError,
    HIPAAMinimumNecessaryError,
    HIPAAPrivacyViolationError,
    SOXSegregationViolationError,
)
from models import (
    ComplianceCheckResult,
    ComplianceRegime,
    ComplianceVerdict,
    DataClassificationLevel,
    DataDeletionCertificate,
    EventType,
    FizzBuzzResult,
    GDPRErasureStatus,
    HIPAAMinimumNecessaryLevel,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from observers import EventBus


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons before each test."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def event_bus():
    """Create an event bus for testing."""
    return EventBus()


@pytest.fixture
def sample_result():
    """Create a sample FizzBuzz result."""
    return FizzBuzzResult(
        number=15,
        output="FizzBuzz",
        matched_rules=[
            RuleMatch(
                rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz"),
                number=15,
            ),
            RuleMatch(
                rule=RuleDefinition(name="BuzzRule", divisor=5, label="Buzz"),
                number=15,
            ),
        ],
    )


@pytest.fixture
def fizz_result():
    """Create a Fizz result."""
    return FizzBuzzResult(
        number=3,
        output="Fizz",
        matched_rules=[
            RuleMatch(
                rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz"),
                number=3,
            ),
        ],
    )


@pytest.fixture
def plain_result():
    """Create a plain number result."""
    return FizzBuzzResult(number=7, output="7")


@pytest.fixture
def personnel_roster():
    """Standard personnel roster for SOX testing."""
    return [
        {"name": "Alice Fizzworth", "title": "Senior Fizz Specialist", "clearance": "FIZZ_CLEARED"},
        {"name": "Charlie Buzzman", "title": "Principal Buzz Engineer", "clearance": "BUZZ_CLEARED"},
        {"name": "Diana Formatson", "title": "Chief Output Officer", "clearance": "FORMAT_CLEARED"},
        {"name": "Eve Auditrix", "title": "Director of Audit", "clearance": "AUDIT_CLEARED"},
        {"name": "Frank Oversite", "title": "VP of Governance", "clearance": "OVERSIGHT_CLEARED"},
    ]


@pytest.fixture
def sox_auditor(personnel_roster, event_bus):
    """Create a SOX auditor."""
    return SOXAuditor(
        personnel_roster=personnel_roster,
        strict_mode=True,
        event_bus=event_bus,
    )


@pytest.fixture
def gdpr_controller(event_bus):
    """Create a GDPR controller with auto-consent."""
    return GDPRController(
        auto_consent=True,
        erasure_enabled=True,
        event_bus=event_bus,
    )


@pytest.fixture
def hipaa_guard(event_bus):
    """Create a HIPAA guard."""
    return HIPAAGuard(
        minimum_necessary_level="OPERATIONS",
        encryption_algorithm="military_grade_base64",
        event_bus=event_bus,
    )


@pytest.fixture
def compliance_framework(sox_auditor, gdpr_controller, hipaa_guard, event_bus):
    """Create a full compliance framework."""
    return ComplianceFramework(
        sox_auditor=sox_auditor,
        gdpr_controller=gdpr_controller,
        hipaa_guard=hipaa_guard,
        event_bus=event_bus,
        bob_stress_level=94.7,
    )


# ================================================================
# Data Classification Engine Tests
# ================================================================


class TestDataClassificationEngine:
    """Tests for the DataClassificationEngine."""

    def test_plain_number_is_public(self, plain_result, event_bus):
        """Plain numbers are PUBLIC — nobody cares about 7."""
        engine = DataClassificationEngine(event_bus=event_bus)
        level = engine.classify(plain_result)
        assert level == DataClassificationLevel.PUBLIC

    def test_fizz_is_internal(self, fizz_result, event_bus):
        """Fizz results are INTERNAL — mildly interesting to competitors."""
        engine = DataClassificationEngine(event_bus=event_bus)
        level = engine.classify(fizz_result)
        assert level == DataClassificationLevel.INTERNAL

    def test_buzz_is_internal(self, event_bus):
        """Buzz results are INTERNAL."""
        result = FizzBuzzResult(number=5, output="Buzz")
        engine = DataClassificationEngine(event_bus=event_bus)
        level = engine.classify(result)
        assert level == DataClassificationLevel.INTERNAL

    def test_fizzbuzz_is_confidential(self, sample_result, event_bus):
        """FizzBuzz results are CONFIDENTIAL — trade secrets!"""
        engine = DataClassificationEngine(event_bus=event_bus)
        level = engine.classify(sample_result)
        assert level == DataClassificationLevel.CONFIDENTIAL

    def test_low_ml_confidence_is_secret(self, event_bus):
        """Low ML confidence results are SECRET."""
        result = FizzBuzzResult(number=15, output="FizzBuzz")
        result.metadata["ml_confidence"] = 0.7
        engine = DataClassificationEngine(event_bus=event_bus)
        level = engine.classify(result)
        assert level == DataClassificationLevel.SECRET

    def test_multi_strategy_fizzbuzz_is_top_secret(self, event_bus):
        """Multi-strategy verified FizzBuzz is TOP_SECRET_FIZZBUZZ."""
        result = FizzBuzzResult(number=15, output="FizzBuzz")
        result.metadata["strategies_verified"] = 3
        engine = DataClassificationEngine(event_bus=event_bus)
        level = engine.classify(result)
        assert level == DataClassificationLevel.TOP_SECRET_FIZZBUZZ

    def test_classification_statistics(self, event_bus):
        """Statistics are tracked correctly."""
        engine = DataClassificationEngine(event_bus=event_bus)
        engine.classify(FizzBuzzResult(number=7, output="7"))
        engine.classify(FizzBuzzResult(number=3, output="Fizz"))
        engine.classify(FizzBuzzResult(number=15, output="FizzBuzz"))
        stats = engine.get_statistics()
        assert stats["total_classified"] == 3
        assert stats["by_level"]["PUBLIC"] == 1
        assert stats["by_level"]["INTERNAL"] == 1
        assert stats["by_level"]["CONFIDENTIAL"] == 1


# ================================================================
# SOX Auditor Tests
# ================================================================


class TestSOXAuditor:
    """Tests for the SOX Auditor segregation of duties."""

    def test_assign_duties_returns_all_roles(self, sox_auditor):
        """All four roles must be assigned."""
        assignments = sox_auditor.assign_duties(15)
        assert "FIZZ_EVALUATOR" in assignments
        assert "BUZZ_EVALUATOR" in assignments
        assert "FORMATTER" in assignments
        assert "AUDITOR" in assignments

    def test_segregation_different_people(self, sox_auditor):
        """No person should hold multiple roles (5 personnel, 4 roles)."""
        assignments = sox_auditor.assign_duties(15)
        names = [a.name for a in assignments.values()]
        # With 5 personnel and 4 roles, all should be unique
        assert len(names) == len(set(names))

    def test_deterministic_assignments(self, sox_auditor):
        """Assignments for the same number should be deterministic."""
        assignments1 = sox_auditor.assign_duties(42)
        # Create a fresh auditor with same roster
        auditor2 = SOXAuditor(
            personnel_roster=[
                {"name": "Alice Fizzworth", "title": "Senior Fizz Specialist", "clearance": "FIZZ_CLEARED"},
                {"name": "Charlie Buzzman", "title": "Principal Buzz Engineer", "clearance": "BUZZ_CLEARED"},
                {"name": "Diana Formatson", "title": "Chief Output Officer", "clearance": "FORMAT_CLEARED"},
                {"name": "Eve Auditrix", "title": "Director of Audit", "clearance": "AUDIT_CLEARED"},
                {"name": "Frank Oversite", "title": "VP of Governance", "clearance": "OVERSIGHT_CLEARED"},
            ],
            strict_mode=True,
        )
        assignments2 = auditor2.assign_duties(42)
        for role in SOXAuditor.ROLES:
            assert assignments1[role].name == assignments2[role].name

    def test_audit_trail_recorded(self, sox_auditor):
        """Each assignment should be recorded in the audit trail."""
        sox_auditor.assign_duties(15)
        sox_auditor.assign_duties(30)
        trail = sox_auditor.get_audit_trail()
        assert len(trail) == 2
        assert trail[0]["number"] == 15
        assert trail[1]["number"] == 30

    def test_strict_mode_too_few_personnel(self, event_bus):
        """Strict mode should raise when roster is too small."""
        small_roster = [
            {"name": "Alice", "title": "Fizz", "clearance": "A"},
            {"name": "Bob", "title": "Buzz", "clearance": "B"},
        ]
        auditor = SOXAuditor(
            personnel_roster=small_roster,
            strict_mode=True,
            event_bus=event_bus,
        )
        with pytest.raises(SOXSegregationViolationError):
            auditor.assign_duties(15)

    def test_non_strict_mode_allows_overlap(self, event_bus):
        """Non-strict mode should allow duty overlap with warnings."""
        small_roster = [
            {"name": "Alice", "title": "Fizz", "clearance": "A"},
            {"name": "Bob", "title": "Buzz", "clearance": "B"},
        ]
        auditor = SOXAuditor(
            personnel_roster=small_roster,
            strict_mode=False,
            event_bus=event_bus,
        )
        assignments = auditor.assign_duties(15)
        assert len(assignments) == 4  # All roles assigned

    def test_assignments_count(self, sox_auditor):
        """Assignments counter should increment."""
        sox_auditor.assign_duties(1)
        sox_auditor.assign_duties(2)
        sox_auditor.assign_duties(3)
        assert sox_auditor.assignments_made == 3

    def test_different_numbers_may_get_different_assignments(self, sox_auditor):
        """Different numbers should potentially get different duty assignments."""
        assignments_a = sox_auditor.assign_duties(1)
        assignments_b = sox_auditor.assign_duties(100)
        # Not guaranteed to be different, but the mechanism should work
        # Just verify both are valid
        assert all(role in assignments_a for role in SOXAuditor.ROLES)
        assert all(role in assignments_b for role in SOXAuditor.ROLES)


# ================================================================
# GDPR Controller Tests
# ================================================================


class TestGDPRController:
    """Tests for the GDPR Controller."""

    def test_auto_consent_grants(self, gdpr_controller):
        """Auto-consent should grant consent automatically."""
        assert gdpr_controller.request_consent(42) is True

    def test_auto_consent_tracked(self, gdpr_controller):
        """Consent should be tracked in the registry."""
        gdpr_controller.request_consent(42)
        assert gdpr_controller.has_consent(42) is True

    def test_no_consent_without_request(self, gdpr_controller):
        """Numbers without consent requests should not have consent."""
        assert gdpr_controller.has_consent(99) is False

    def test_manual_consent_denies_by_default(self, event_bus):
        """Manual consent mode should deny by default."""
        controller = GDPRController(auto_consent=False, event_bus=event_bus)
        assert controller.request_consent(42) is False

    def test_consent_count(self, gdpr_controller):
        """Consent counter should track grants."""
        gdpr_controller.request_consent(1)
        gdpr_controller.request_consent(2)
        gdpr_controller.request_consent(3)
        assert gdpr_controller.consent_count == 3

    def test_denial_count(self, event_bus):
        """Denial counter should track denials."""
        controller = GDPRController(auto_consent=False, event_bus=event_bus)
        controller.request_consent(1)
        controller.request_consent(2)
        assert controller.denial_count == 2

    def test_erasure_request_returns_certificate(self, gdpr_controller):
        """Erasure requests should return a DataDeletionCertificate."""
        certificate = gdpr_controller.request_erasure(42)
        assert isinstance(certificate, DataDeletionCertificate)
        assert certificate.data_subject == 42

    def test_erasure_triggers_paradox(self, gdpr_controller):
        """Erasure should always encounter THE COMPLIANCE PARADOX."""
        certificate = gdpr_controller.request_erasure(42)
        assert certificate.status == GDPRErasureStatus.PARADOX_ENCOUNTERED

    def test_erasure_paradox_explanation(self, gdpr_controller):
        """The paradox explanation should be thorough and dramatic."""
        certificate = gdpr_controller.request_erasure(42)
        assert "COMPLIANCE PARADOX" in certificate.paradox_explanation
        assert "append-only" in certificate.paradox_explanation.lower() or \
               "Append-Only" in certificate.paradox_explanation
        assert "blockchain" in certificate.paradox_explanation.lower() or \
               "Blockchain" in certificate.paradox_explanation

    def test_erasure_checks_all_stores(self, gdpr_controller):
        """Erasure should check multiple data stores."""
        certificate = gdpr_controller.request_erasure(42)
        assert len(certificate.stores_checked) >= 5

    def test_erasure_some_stores_refuse(self, gdpr_controller):
        """Some stores should refuse erasure (immutable ones)."""
        certificate = gdpr_controller.request_erasure(42)
        assert len(certificate.stores_refused) > 0
        assert len(certificate.stores_erased) > 0
        assert len(certificate.stores_refused) > len(certificate.stores_erased)

    def test_erasure_revokes_consent(self, gdpr_controller):
        """Erasure should revoke consent for the data subject."""
        gdpr_controller.request_consent(42)
        assert gdpr_controller.has_consent(42) is True
        gdpr_controller.request_erasure(42)
        assert gdpr_controller.has_consent(42) is False

    def test_paradox_count_increments(self, gdpr_controller):
        """Paradox counter should increment with each erasure."""
        gdpr_controller.request_erasure(1)
        gdpr_controller.request_erasure(2)
        gdpr_controller.request_erasure(3)
        assert gdpr_controller.paradox_count == 3

    def test_erasure_certificates_stored(self, gdpr_controller):
        """All erasure certificates should be retrievable."""
        gdpr_controller.request_erasure(1)
        gdpr_controller.request_erasure(2)
        certs = gdpr_controller.get_erasure_certificates()
        assert len(certs) == 2

    def test_statistics(self, gdpr_controller):
        """Statistics should reflect all operations."""
        gdpr_controller.request_consent(1)
        gdpr_controller.request_consent(2)
        gdpr_controller.request_erasure(3)
        stats = gdpr_controller.get_statistics()
        assert stats["consents_granted"] == 2
        assert stats["erasure_requests"] == 1
        assert stats["paradoxes_encountered"] == 1


# ================================================================
# HIPAA Guard Tests
# ================================================================


class TestHIPAAGuard:
    """Tests for the HIPAA Guard."""

    def test_encrypt_phi_produces_base64(self, hipaa_guard):
        """'Encryption' should produce base64-encoded output."""
        encrypted = hipaa_guard.encrypt_phi("FizzBuzz")
        assert "[HIPAA-ENCRYPTED:military_grade_base64]" in encrypted
        # Verify the base64 part is valid
        b64_part = encrypted.split("]", 1)[1]
        decoded = base64.b64decode(b64_part.encode()).decode()
        assert decoded == "FizzBuzz"

    def test_decrypt_phi_roundtrip(self, hipaa_guard):
        """Encrypt then decrypt should return original data."""
        original = "FizzBuzz for number 15"
        encrypted = hipaa_guard.encrypt_phi(original)
        decrypted = hipaa_guard.decrypt_phi(encrypted)
        assert decrypted == original

    def test_encryption_count(self, hipaa_guard):
        """Encryption counter should increment."""
        hipaa_guard.encrypt_phi("Fizz")
        hipaa_guard.encrypt_phi("Buzz")
        hipaa_guard.encrypt_phi("FizzBuzz")
        assert hipaa_guard.get_statistics()["phi_encryptions"] == 3

    def test_full_access_shows_everything(self, hipaa_guard, sample_result):
        """FULL_ACCESS should show all fields."""
        redacted = hipaa_guard.apply_minimum_necessary(
            sample_result,
            HIPAAMinimumNecessaryLevel.FULL_ACCESS,
        )
        assert redacted["number"] == 15
        assert redacted["output"] == "FizzBuzz"
        assert redacted["access_level"] == "FULL_ACCESS"

    def test_treatment_hides_metadata(self, hipaa_guard, sample_result):
        """TREATMENT should show output but hide processing metadata."""
        redacted = hipaa_guard.apply_minimum_necessary(
            sample_result,
            HIPAAMinimumNecessaryLevel.TREATMENT,
        )
        assert redacted["number"] == 15
        assert redacted["output"] == "FizzBuzz"
        assert "metadata" not in redacted
        assert redacted["access_level"] == "TREATMENT"

    def test_operations_redacts_everything(self, hipaa_guard, sample_result):
        """OPERATIONS should redact individual results."""
        redacted = hipaa_guard.apply_minimum_necessary(
            sample_result,
            HIPAAMinimumNecessaryLevel.OPERATIONS,
        )
        assert "REDACTED" in str(redacted["number"])
        assert "REDACTED" in str(redacted["output"])
        assert redacted["access_level"] == "OPERATIONS"

    def test_research_deidentifies(self, hipaa_guard, sample_result):
        """RESEARCH should de-identify all data."""
        redacted = hipaa_guard.apply_minimum_necessary(
            sample_result,
            HIPAAMinimumNecessaryLevel.RESEARCH,
        )
        assert "subject_id" in redacted
        assert redacted["subject_id"].startswith("SUBJ-")
        assert "output_hash" in redacted
        assert redacted["access_level"] == "RESEARCH"
        # Original data should NOT be present
        assert 15 not in redacted.values()
        assert "FizzBuzz" not in redacted.values()

    def test_default_level_is_operations(self, hipaa_guard, sample_result):
        """Default access level should be OPERATIONS."""
        redacted = hipaa_guard.apply_minimum_necessary(sample_result)
        assert redacted["access_level"] == "OPERATIONS"

    def test_phi_access_log(self, hipaa_guard, sample_result):
        """PHI access should be logged."""
        hipaa_guard.apply_minimum_necessary(sample_result)
        log = hipaa_guard.get_phi_access_log()
        assert len(log) == 1
        assert log[0]["number"] == 15

    def test_statistics(self, hipaa_guard, sample_result):
        """Statistics should be accurate."""
        hipaa_guard.encrypt_phi("test")
        hipaa_guard.apply_minimum_necessary(
            sample_result,
            HIPAAMinimumNecessaryLevel.OPERATIONS,
        )
        stats = hipaa_guard.get_statistics()
        assert stats["phi_encryptions"] == 1
        assert stats["phi_redactions"] == 1
        assert stats["actual_security_provided"] == "None"


# ================================================================
# Compliance Framework Tests
# ================================================================


class TestComplianceFramework:
    """Tests for the unified ComplianceFramework."""

    def test_perform_check_returns_results(self, compliance_framework, sample_result):
        """A compliance check should return results for all three regimes."""
        results = compliance_framework.perform_compliance_check(sample_result)
        assert len(results) == 3  # SOX, GDPR, HIPAA
        regimes = {r.regime for r in results}
        assert ComplianceRegime.SOX in regimes
        assert ComplianceRegime.GDPR in regimes
        assert ComplianceRegime.HIPAA in regimes

    def test_bob_stress_increases(self, compliance_framework, sample_result):
        """Bob's stress level should increase with each check."""
        initial_stress = compliance_framework.bob_stress_level
        compliance_framework.perform_compliance_check(sample_result)
        assert compliance_framework.bob_stress_level > initial_stress

    def test_bob_stress_starts_at_configured_value(self, compliance_framework):
        """Bob's stress should start at the configured value."""
        assert compliance_framework.bob_stress_level == 94.7

    def test_data_classification_added_to_metadata(self, compliance_framework, sample_result):
        """Compliance check should add data classification to metadata."""
        compliance_framework.perform_compliance_check(sample_result)
        assert "data_classification" in sample_result.metadata

    def test_hipaa_encrypted_output_in_metadata(self, compliance_framework, sample_result):
        """HIPAA check should add encrypted output to metadata."""
        compliance_framework.perform_compliance_check(sample_result)
        assert "hipaa_encrypted_output" in sample_result.metadata
        assert "HIPAA-ENCRYPTED" in sample_result.metadata["hipaa_encrypted_output"]

    def test_sox_assignments_in_metadata(self, compliance_framework, sample_result):
        """SOX check should add duty assignments to metadata."""
        compliance_framework.perform_compliance_check(sample_result)
        assert "sox_assignments" in sample_result.metadata

    def test_multiple_checks_accumulate(self, compliance_framework):
        """Multiple checks should accumulate results."""
        for i in range(5):
            result = FizzBuzzResult(number=i + 1, output=str(i + 1))
            compliance_framework.perform_compliance_check(result)
        assert compliance_framework.total_checks == 5
        assert len(compliance_framework.get_check_results()) == 15  # 3 per check

    def test_posture_summary(self, compliance_framework, sample_result):
        """Posture summary should contain all key metrics."""
        compliance_framework.perform_compliance_check(sample_result)
        posture = compliance_framework.get_posture_summary()
        assert "total_checks" in posture
        assert "compliant" in posture
        assert "compliance_rate" in posture
        assert "bob_stress_level" in posture
        assert "sox_stats" in posture
        assert "gdpr_stats" in posture
        assert "hipaa_stats" in posture

    def test_erasure_request_delegates_to_gdpr(self, compliance_framework):
        """Erasure requests should delegate to GDPR controller."""
        certificate = compliance_framework.process_erasure_request(42)
        assert isinstance(certificate, DataDeletionCertificate)
        assert certificate.data_subject == 42

    def test_erasure_increases_bob_stress_significantly(self, compliance_framework):
        """Erasure paradoxes should stress Bob out significantly."""
        initial = compliance_framework.bob_stress_level
        compliance_framework.process_erasure_request(42)
        assert compliance_framework.bob_stress_level >= initial + 5.0

    def test_framework_without_gdpr_raises_on_erasure(self, sox_auditor, hipaa_guard, event_bus):
        """Erasure without GDPR should raise."""
        framework = ComplianceFramework(
            sox_auditor=sox_auditor,
            gdpr_controller=None,
            hipaa_guard=hipaa_guard,
            event_bus=event_bus,
        )
        with pytest.raises(ComplianceFrameworkNotEnabledError):
            framework.process_erasure_request(42)

    def test_gdpr_auto_consent_makes_compliant(self, compliance_framework, sample_result):
        """With auto-consent, GDPR checks should be COMPLIANT."""
        results = compliance_framework.perform_compliance_check(sample_result)
        gdpr_results = [r for r in results if r.regime == ComplianceRegime.GDPR]
        assert gdpr_results[0].verdict == ComplianceVerdict.COMPLIANT

    def test_sox_compliant_with_full_roster(self, compliance_framework, sample_result):
        """With a full roster, SOX should be COMPLIANT."""
        results = compliance_framework.perform_compliance_check(sample_result)
        sox_results = [r for r in results if r.regime == ComplianceRegime.SOX]
        assert sox_results[0].verdict == ComplianceVerdict.COMPLIANT

    def test_hipaa_always_compliant(self, compliance_framework, sample_result):
        """HIPAA checks should always be COMPLIANT (we encrypt everything)."""
        results = compliance_framework.perform_compliance_check(sample_result)
        hipaa_results = [r for r in results if r.regime == ComplianceRegime.HIPAA]
        assert hipaa_results[0].verdict == ComplianceVerdict.COMPLIANT


# ================================================================
# Compliance Middleware Tests
# ================================================================


class TestComplianceMiddleware:
    """Tests for the ComplianceMiddleware."""

    def test_middleware_name(self, compliance_framework):
        """Middleware should have the correct name."""
        middleware = ComplianceMiddleware(compliance_framework)
        assert middleware.get_name() == "ComplianceMiddleware"

    def test_middleware_priority(self, compliance_framework):
        """Middleware should have priority -5."""
        middleware = ComplianceMiddleware(compliance_framework)
        assert middleware.get_priority() == -5

    def test_middleware_adds_compliance_metadata(self, compliance_framework):
        """Middleware should add compliance metadata to context."""
        middleware = ComplianceMiddleware(compliance_framework)

        context = ProcessingContext(number=15, session_id="test-session")
        result = FizzBuzzResult(number=15, output="FizzBuzz")

        def next_handler(ctx):
            ctx.results.append(result)
            return ctx

        processed = middleware.process(context, next_handler)
        assert "compliance_checks" in processed.metadata
        assert "bob_stress_level" in processed.metadata

    def test_middleware_passes_through_without_results(self, compliance_framework):
        """Middleware should work even when there are no results."""
        middleware = ComplianceMiddleware(compliance_framework)
        context = ProcessingContext(number=7, session_id="test-session")

        def next_handler(ctx):
            return ctx

        processed = middleware.process(context, next_handler)
        assert processed is context


# ================================================================
# Exception Tests
# ================================================================


class TestComplianceExceptions:
    """Tests for compliance exception hierarchy."""

    def test_compliance_error_base(self):
        """ComplianceError should have correct error code."""
        err = ComplianceError("test")
        assert "EFP-C000" in str(err)

    def test_sox_segregation_violation(self):
        """SOXSegregationViolationError should include personnel and roles."""
        err = SOXSegregationViolationError("Alice", "FIZZ_EVALUATOR", "BUZZ_EVALUATOR")
        assert "Alice" in str(err)
        assert "EFP-C100" in str(err)
        assert err.personnel == "Alice"

    def test_gdpr_erasure_paradox(self):
        """GDPRErasureParadoxError should describe the paradox."""
        err = GDPRErasureParadoxError(42)
        assert "42" in str(err)
        assert "EFP-C200" in str(err)
        assert "paradox" in str(err).lower() or "PARADOX" in str(err)

    def test_gdpr_consent_required(self):
        """GDPRConsentRequiredError should mention the data subject."""
        err = GDPRConsentRequiredError(42)
        assert "42" in str(err)
        assert "EFP-C201" in str(err)

    def test_hipaa_privacy_violation(self):
        """HIPAAPrivacyViolationError should include violation type."""
        err = HIPAAPrivacyViolationError("disclosure", "PHI was visible")
        assert "disclosure" in str(err)
        assert "EFP-C300" in str(err)

    def test_hipaa_minimum_necessary(self):
        """HIPAAMinimumNecessaryError should show levels."""
        err = HIPAAMinimumNecessaryError("FULL_ACCESS", "OPERATIONS")
        assert "FULL_ACCESS" in str(err)
        assert "OPERATIONS" in str(err)
        assert "EFP-C301" in str(err)

    def test_framework_not_enabled(self):
        """ComplianceFrameworkNotEnabledError should provide guidance."""
        err = ComplianceFrameworkNotEnabledError()
        assert "--compliance" in str(err)
        assert "EFP-C400" in str(err)

    def test_officer_unavailable(self):
        """ComplianceOfficerUnavailableError should include stress level."""
        err = ComplianceOfficerUnavailableError("Bob", 94.7)
        assert "Bob" in str(err)
        assert "94.7" in str(err)
        assert "EFP-C401" in str(err)


# ================================================================
# Dashboard Tests
# ================================================================


class TestComplianceDashboard:
    """Tests for the ComplianceDashboard rendering."""

    def test_render_dashboard(self, compliance_framework, sample_result):
        """Dashboard should render without errors."""
        compliance_framework.perform_compliance_check(sample_result)
        output = ComplianceDashboard.render(compliance_framework)
        assert "COMPLIANCE" in output
        assert "BOB McFIZZINGTON" in output
        assert "STRESS" in output

    def test_render_erasure_certificate(self, gdpr_controller):
        """Erasure certificate should render the paradox."""
        certificate = gdpr_controller.request_erasure(42)
        output = ComplianceDashboard.render_erasure_certificate(certificate)
        assert "GDPR DATA DELETION CERTIFICATE" in output
        assert "COMPLIANCE PARADOX" in output
        assert "42" in output

    def test_render_report(self, compliance_framework, sample_result):
        """Compliance report should include recommendations."""
        compliance_framework.perform_compliance_check(sample_result)
        output = ComplianceDashboard.render_report(compliance_framework)
        assert "COMPREHENSIVE COMPLIANCE REPORT" in output
        assert "RECOMMENDATIONS" in output
        assert "Bob McFizzington" in output

    def test_dashboard_width(self, compliance_framework, sample_result):
        """Dashboard should respect width parameter."""
        compliance_framework.perform_compliance_check(sample_result)
        output = ComplianceDashboard.render(compliance_framework, width=80)
        assert len(output) > 0  # Just verify it renders


# ================================================================
# Model Tests
# ================================================================


class TestComplianceModels:
    """Tests for compliance-related domain models."""

    def test_compliance_regime_values(self):
        """All three regimes should exist."""
        assert ComplianceRegime.SOX.name == "SOX"
        assert ComplianceRegime.GDPR.name == "GDPR"
        assert ComplianceRegime.HIPAA.name == "HIPAA"

    def test_compliance_verdict_values(self):
        """All verdict types should exist."""
        assert ComplianceVerdict.COMPLIANT.name == "COMPLIANT"
        assert ComplianceVerdict.NON_COMPLIANT.name == "NON_COMPLIANT"
        assert ComplianceVerdict.PARTIALLY_COMPLIANT.name == "PARTIALLY_COMPLIANT"
        assert ComplianceVerdict.UNDER_REVIEW.name == "UNDER_REVIEW"
        assert ComplianceVerdict.PARADOX_DETECTED.name == "PARADOX_DETECTED"

    def test_data_classification_values(self):
        """All classification levels should exist."""
        assert DataClassificationLevel.PUBLIC.name == "PUBLIC"
        assert DataClassificationLevel.INTERNAL.name == "INTERNAL"
        assert DataClassificationLevel.CONFIDENTIAL.name == "CONFIDENTIAL"
        assert DataClassificationLevel.SECRET.name == "SECRET"
        assert DataClassificationLevel.TOP_SECRET_FIZZBUZZ.name == "TOP_SECRET_FIZZBUZZ"

    def test_gdpr_erasure_status_values(self):
        """All erasure statuses should exist."""
        assert GDPRErasureStatus.REQUESTED.name == "REQUESTED"
        assert GDPRErasureStatus.PARADOX_ENCOUNTERED.name == "PARADOX_ENCOUNTERED"
        assert GDPRErasureStatus.CERTIFICATE_ISSUED.name == "CERTIFICATE_ISSUED"

    def test_hipaa_minimum_necessary_levels(self):
        """All HIPAA access levels should exist."""
        assert HIPAAMinimumNecessaryLevel.FULL_ACCESS.name == "FULL_ACCESS"
        assert HIPAAMinimumNecessaryLevel.TREATMENT.name == "TREATMENT"
        assert HIPAAMinimumNecessaryLevel.OPERATIONS.name == "OPERATIONS"
        assert HIPAAMinimumNecessaryLevel.RESEARCH.name == "RESEARCH"

    def test_compliance_check_result_frozen(self):
        """ComplianceCheckResult should be immutable."""
        result = ComplianceCheckResult(
            regime=ComplianceRegime.SOX,
            verdict=ComplianceVerdict.COMPLIANT,
        )
        with pytest.raises(AttributeError):
            result.verdict = ComplianceVerdict.NON_COMPLIANT

    def test_data_deletion_certificate_frozen(self):
        """DataDeletionCertificate should be immutable."""
        cert = DataDeletionCertificate(data_subject=42)
        with pytest.raises(AttributeError):
            cert.data_subject = 99

    def test_compliance_event_types_exist(self):
        """All compliance event types should exist."""
        assert EventType.COMPLIANCE_CHECK_STARTED.name == "COMPLIANCE_CHECK_STARTED"
        assert EventType.COMPLIANCE_CHECK_PASSED.name == "COMPLIANCE_CHECK_PASSED"
        assert EventType.COMPLIANCE_CHECK_FAILED.name == "COMPLIANCE_CHECK_FAILED"
        assert EventType.GDPR_ERASURE_PARADOX_DETECTED.name == "GDPR_ERASURE_PARADOX_DETECTED"
        assert EventType.SOX_SEGREGATION_ENFORCED.name == "SOX_SEGREGATION_ENFORCED"
        assert EventType.HIPAA_PHI_ENCRYPTED.name == "HIPAA_PHI_ENCRYPTED"
        assert EventType.COMPLIANCE_DASHBOARD_RENDERED.name == "COMPLIANCE_DASHBOARD_RENDERED"
