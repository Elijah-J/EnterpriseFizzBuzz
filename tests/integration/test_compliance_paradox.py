"""
Enterprise FizzBuzz Platform - The Compliance Paradox Integration Test Suite

In-process integration tests for the platform's single most famous
architectural conflict: GDPR's right-to-erasure vs. the append-only
event store, immutable blockchain, and SOX audit retention requirements.

GDPR Article 17 says: delete.
Event Sourcing says: I am append-only; I cannot un-happen a fact.
Blockchain says: remove a block and the hash chain collapses.
SOX Section 802 says: keep everything for 7 years or face federal charges.

The result is a regulatory singularity from which no compliant path
escapes. These tests verify that the platform navigates this impossible
situation with the grace, thoroughness, and existential resignation that
Bob McFizzington's stress level demands.

Test categories:
  1. Erasure with live cache: evaluate, cache, erase, verify cache purged
  2. Erasure with live event store: evaluate, store events, erase, verify events survive
  3. Erasure with live blockchain: mine blocks, erase, verify chain integrity
  4. Full paradox path: all stores live, erasure triggers the complete paradox
  5. Bob's stress level: monotonically increasing, as is tradition
  6. Multiple erasure requests: paradox count increments per data subject
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

# Add parent dirs to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from enterprise_fizzbuzz.domain.models import (
    ComplianceCheckResult,
    ComplianceRegime,
    ComplianceVerdict,
    DataClassificationLevel,
    DataDeletionCertificate,
    Event,
    EventType,
    FizzBuzzResult,
    GDPRErasureStatus,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.blockchain import (
    FizzBuzzBlockchain,
)
from enterprise_fizzbuzz.infrastructure.cache import CacheStore
from enterprise_fizzbuzz.infrastructure.compliance import (
    ComplianceDashboard,
    ComplianceFramework,
    GDPRController,
    HIPAAGuard,
    SOXAuditor,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.event_sourcing import (
    EvaluationCompletedEvent,
    EventStore,
    LabelAssignedEvent,
    NumberReceivedEvent,
)
from enterprise_fizzbuzz.infrastructure.observers import EventBus


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singleton instances between tests.

    Without this, the ConfigurationManager singleton bleeds compliance
    state between tests like an under-resourced Chief Compliance Officer
    bleeds stress into every adjacent department.
    """
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def event_bus():
    """Create a fresh EventBus for inter-subsystem communication."""
    return EventBus()


@pytest.fixture
def personnel_roster():
    """Standard SOX personnel roster — five virtual employees, each
    impressively titled, each blissfully unaware they exist only to
    satisfy segregation-of-duties requirements for modulo arithmetic.
    """
    return [
        {"name": "Alice Fizzworth", "title": "Senior Fizz Specialist", "clearance": "FIZZ_CLEARED"},
        {"name": "Charlie Buzzman", "title": "Principal Buzz Engineer", "clearance": "BUZZ_CLEARED"},
        {"name": "Diana Formatson", "title": "Chief Output Officer", "clearance": "FORMAT_CLEARED"},
        {"name": "Eve Auditrix", "title": "Director of Audit", "clearance": "AUDIT_CLEARED"},
        {"name": "Frank Oversite", "title": "VP of Governance", "clearance": "OVERSIGHT_CLEARED"},
    ]


@pytest.fixture
def sox_auditor(personnel_roster, event_bus):
    """Create a SOX auditor wired to the shared event bus."""
    return SOXAuditor(
        personnel_roster=personnel_roster,
        strict_mode=True,
        event_bus=event_bus,
    )


@pytest.fixture
def gdpr_controller(event_bus):
    """Create a GDPR controller with auto-consent and erasure enabled.

    Auto-consent is the pragmatic choice: asking each number for explicit
    consent before computing n % 3 would make FizzBuzz unacceptably slow.
    """
    return GDPRController(
        auto_consent=True,
        erasure_enabled=True,
        event_bus=event_bus,
    )


@pytest.fixture
def hipaa_guard(event_bus):
    """Create a HIPAA guard armed with military-grade base64."""
    return HIPAAGuard(
        minimum_necessary_level="OPERATIONS",
        encryption_algorithm="military_grade_base64",
        event_bus=event_bus,
    )


@pytest.fixture
def compliance_framework(sox_auditor, gdpr_controller, hipaa_guard, event_bus):
    """Create a fully-wired ComplianceFramework with all three regimes enabled.

    This is the grand unified compliance engine: SOX for segregation,
    GDPR for consent and erasure, HIPAA for "encryption." Bob's stress
    starts at 94.7% and only goes up from here.
    """
    return ComplianceFramework(
        sox_auditor=sox_auditor,
        gdpr_controller=gdpr_controller,
        hipaa_guard=hipaa_guard,
        event_bus=event_bus,
        bob_stress_level=94.7,
    )


@pytest.fixture
def cache_store(event_bus):
    """Create a CacheStore — the one data store that actually cooperates
    with GDPR erasure requests, because it has no philosophical objections
    to forgetting things.
    """
    return CacheStore(
        max_size=256,
        ttl_seconds=3600.0,
        event_bus=event_bus,
    )


@pytest.fixture
def event_store():
    """Create an append-only EventStore — immutable, unapologetic,
    and utterly unwilling to delete anything ever.
    """
    return EventStore()


@pytest.fixture
def blockchain():
    """Create a FizzBuzzBlockchain with difficulty 1 for faster mining.

    Difficulty 1 means a single leading zero. It's enough to prove the
    concept without waiting until the heat death of the universe for
    proof-of-work to complete.
    """
    return FizzBuzzBlockchain(difficulty=1)


def _make_result(number: int) -> FizzBuzzResult:
    """Create a FizzBuzzResult with correct ground-truth classification.

    No shortcuts: the result must be correct because the compliance
    framework will classify it, the SOX auditor will assign duties for
    it, and the GDPR controller will issue certificates about it.
    Garbage in, paradox out (well, paradox out regardless, but at least
    the garbage should be correctly classified garbage).
    """
    if number % 15 == 0:
        output = "FizzBuzz"
    elif number % 3 == 0:
        output = "Fizz"
    elif number % 5 == 0:
        output = "Buzz"
    else:
        output = str(number)

    rules = []
    if number % 3 == 0:
        rules.append(RuleMatch(
            rule=RuleDefinition(name="Fizz", divisor=3, label="Fizz"),
            number=number,
        ))
    if number % 5 == 0:
        rules.append(RuleMatch(
            rule=RuleDefinition(name="Buzz", divisor=5, label="Buzz"),
            number=number,
        ))

    return FizzBuzzResult(
        number=number,
        output=output,
        matched_rules=rules,
        processing_time_ns=1_000_000,
    )


# ============================================================
# Category 1: Erasure with Live Cache
# ============================================================


class TestErasureWithLiveCache:
    """Tests verifying that the cache — the only data store with a
    conscience — actually complies with GDPR erasure requests by
    purging the offending entry.
    """

    def test_cache_stores_result_for_42(self, cache_store):
        """Verify that a FizzBuzz result for 42 can be cached and retrieved."""
        result = _make_result(42)
        cache_store.put(42, result)

        cached = cache_store.get(42)
        assert cached is not None
        assert cached.number == 42
        assert cached.output == "Fizz"

    def test_cache_purged_after_erasure_via_invalidation(self, cache_store):
        """Cache the result for 42, invalidate it (GDPR erasure), verify it is gone.

        The cache is the only data store that cooperates with erasure.
        It has no immutability guarantees, no cryptographic hash chains,
        and no philosophical objections to forgetting things. It just
        forgets. Like a goldfish. A compliant goldfish.
        """
        result = _make_result(42)
        cache_store.put(42, result)
        assert cache_store.get(42) is not None

        # Simulate GDPR erasure: invalidate the cache entry
        was_invalidated = cache_store.invalidate(42)
        assert was_invalidated is True

        # Verify: the cache no longer contains data subject 42
        assert cache_store.get(42) is None

    def test_cache_erasure_of_nonexistent_entry_returns_false(self, cache_store):
        """Attempting to erase an entry that was never cached returns False.

        You cannot un-cache what was never cached. Philosophically sound.
        Practically useful for distinguishing 'erased' from 'never existed.'
        """
        was_invalidated = cache_store.invalidate(999)
        assert was_invalidated is False


# ============================================================
# Category 2: Erasure with Live Event Store
# ============================================================


class TestErasureWithLiveEventStore:
    """Tests verifying that the append-only event store refuses to
    delete events, because events are facts, and you cannot un-fact
    a fact. GDPR disagrees. The universe is silent on the matter.
    """

    def test_events_stored_for_number_42(self, event_store):
        """Populate the event store with evaluation events for number 42."""
        event_store.append(NumberReceivedEvent(number=42, aggregate_id="session-42"))
        event_store.append(LabelAssignedEvent(
            number=42, label="Fizz", matched_rule_count=1, aggregate_id="session-42",
        ))
        event_store.append(EvaluationCompletedEvent(
            number=42, output="Fizz", processing_time_ns=1_000_000, aggregate_id="session-42",
        ))

        events = event_store.get_events(aggregate_id="session-42")
        assert len(events) == 3

    def test_events_survive_after_gdpr_erasure_request(self, event_store, gdpr_controller):
        """Store events for 42, issue an erasure request, verify events remain.

        The event store is append-only. The GDPRController issues its
        erasure certificate, the certificate documents the refusal, and
        the events remain untouched — immortal witnesses to the modulo
        operation that someone wished had never happened.
        """
        event_store.append(NumberReceivedEvent(number=42, aggregate_id="session-42"))
        event_store.append(EvaluationCompletedEvent(
            number=42, output="Fizz", processing_time_ns=1_000_000, aggregate_id="session-42",
        ))

        events_before = event_store.get_event_count()

        # Issue the erasure request
        certificate = gdpr_controller.request_erasure(42)

        # The event store was not modified — still contains all events
        events_after = event_store.get_event_count()
        assert events_after >= events_before

        # The events for session-42 are still present
        events = event_store.get_events(aggregate_id="session-42")
        assert len(events) == 2
        assert any(
            isinstance(e, EvaluationCompletedEvent) and e.number == 42
            for e in events
        )

    def test_erasure_certificate_documents_event_store_refusal(self, gdpr_controller):
        """The certificate lists the Append-Only Event Store as a refused store.

        The event store's refusal is not a bug; it is the architecturally
        correct response. The certificate documents this with the gravity
        and precision befitting a regulatory filing.
        """
        certificate = gdpr_controller.request_erasure(42)

        assert any(
            "Append-Only Event Store" in store and "REFUSED" in store
            for store in certificate.stores_refused
        )


# ============================================================
# Category 3: Erasure with Live Blockchain
# ============================================================


class TestErasureWithLiveBlockchain:
    """Tests verifying that the immutable blockchain laughs in the
    face of GDPR erasure requests, its cryptographic hash chain
    intact and unbothered.
    """

    def test_blockchain_records_evaluation_for_42(self, blockchain):
        """Mine a block for number 42 and verify the chain grows."""
        initial_length = blockchain.get_chain_length()
        blockchain.add_block({
            "number": 42,
            "output": "Fizz",
            "evaluation_id": str(uuid.uuid4()),
        })

        assert blockchain.get_chain_length() == initial_length + 1
        latest_block = blockchain.get_block(blockchain.get_chain_length() - 1)
        assert latest_block.data["number"] == 42

    def test_blockchain_unmodified_after_erasure_request(self, blockchain, gdpr_controller):
        """Mine blocks for 42, issue erasure, verify the chain is unchanged.

        The blockchain cannot delete blocks without invalidating the hash
        chain. The GDPR controller knows this. The erasure certificate
        knows this. Everyone knows this. And yet, Article 17 still applies.
        """
        blockchain.add_block({"number": 42, "output": "Fizz"})
        blockchain.add_block({"number": 42, "output": "Fizz", "run": 2})

        chain_length_before = blockchain.get_chain_length()
        chain_valid_before = blockchain.validate_chain()

        # Issue erasure request
        certificate = gdpr_controller.request_erasure(42)

        # The blockchain is immutable: same length, same validity
        assert blockchain.get_chain_length() == chain_length_before
        assert blockchain.validate_chain() == chain_valid_before
        assert blockchain.validate_chain() is True

        # The blocks for 42 are still there
        block = blockchain.get_block(1)  # first non-genesis block
        assert block.data["number"] == 42

    def test_erasure_certificate_documents_blockchain_refusal(self, gdpr_controller):
        """The certificate lists the Immutable Blockchain as a refused store."""
        certificate = gdpr_controller.request_erasure(42)

        assert any(
            "Blockchain" in store and "REFUSED" in store
            for store in certificate.stores_refused
        )


# ============================================================
# Category 4: Full Paradox Path
# ============================================================


class TestFullParadoxPath:
    """Tests for the complete compliance paradox: all data stores live,
    an evaluation performed, and an erasure request issued. This is where
    GDPR, event sourcing, blockchain, and SOX collide in a regulatory
    singularity from which no compliant path escapes.
    """

    def test_full_paradox_status_is_paradox_encountered(
        self, compliance_framework, event_store, blockchain, cache_store,
    ):
        """Enable all stores, evaluate 42, request erasure, verify PARADOX status.

        The DataDeletionCertificate must report PARADOX_ENCOUNTERED because
        the system genuinely cannot comply: GDPR says delete, the event
        store and blockchain say no, and SOX says keep records for 7 years.
        There is no resolution. There is only the certificate.
        """
        result = _make_result(42)

        # Populate all data stores
        cache_store.put(42, result)
        event_store.append(EvaluationCompletedEvent(
            number=42, output="Fizz", aggregate_id="session-42",
        ))
        blockchain.add_block({"number": 42, "output": "Fizz"})

        # Perform a compliance check first (as the real pipeline would)
        compliance_framework.perform_compliance_check(result)

        # Issue the erasure request through the ComplianceFramework
        certificate = compliance_framework.process_erasure_request(42)

        assert certificate.status == GDPRErasureStatus.PARADOX_ENCOUNTERED
        assert certificate.data_subject == 42

    def test_full_paradox_certificate_lists_erased_and_refused_stores(
        self, compliance_framework,
    ):
        """The certificate documents which stores were erased vs. refused.

        Erased: In-Memory Processing Context, FizzBuzz Result Cache.
        Refused: Event Store, Blockchain, SOX Audit Trail, HIPAA PHI Log,
                 and — in a twist of recursive irony — This Very Erasure
                 Request Log.
        """
        result = _make_result(42)
        compliance_framework.perform_compliance_check(result)
        certificate = compliance_framework.process_erasure_request(42)

        # Stores that cooperated with erasure
        assert len(certificate.stores_erased) >= 2
        assert any("Cache" in s for s in certificate.stores_erased)
        assert any("Processing Context" in s for s in certificate.stores_erased)

        # Stores that refused (the paradox-causing immutable stores)
        assert len(certificate.stores_refused) >= 3
        assert any("Event Store" in s and "REFUSED" in s for s in certificate.stores_refused)
        assert any("Blockchain" in s and "REFUSED" in s for s in certificate.stores_refused)
        assert any("SOX" in s and "REFUSED" in s for s in certificate.stores_refused)

    def test_full_paradox_bob_stress_increases_by_five_percent(
        self, compliance_framework,
    ):
        """Bob McFizzington's stress level increases by 5.0% per erasure paradox.

        Bob started at 94.7%. After a compliance check (+0.3%) and an
        erasure request (+5.0%), his stress should be at least 99.7%.
        This is a conservative estimate; non-compliant verdicts add
        additional stress that varies by regime.
        """
        result = _make_result(42)
        stress_before_check = compliance_framework.bob_stress_level

        compliance_framework.perform_compliance_check(result)
        stress_after_check = compliance_framework.bob_stress_level

        # Compliance check increases stress by at least 0.3%
        assert stress_after_check >= stress_before_check + 0.3

        stress_before_erasure = compliance_framework.bob_stress_level
        compliance_framework.process_erasure_request(42)
        stress_after_erasure = compliance_framework.bob_stress_level

        # Erasure paradox increases stress by exactly 5.0%
        assert abs(stress_after_erasure - stress_before_erasure - 5.0) < 0.01

    def test_full_paradox_publishes_events_to_event_bus(self, event_bus, compliance_framework):
        """The compliance paradox publishes events: erasure requested, paradox detected,
        and certificate issued.

        Even the act of failing to comply must be audited. The event bus
        receives a running commentary of the system's regulatory anguish.
        """
        captured_events: list[Event] = []

        class EventCapture:
            def on_event(self, event: Event) -> None:
                captured_events.append(event)

            def get_name(self) -> str:
                return "EventCaptureObserver"

        event_bus.subscribe(EventCapture())

        result = _make_result(42)
        compliance_framework.perform_compliance_check(result)
        compliance_framework.process_erasure_request(42)

        event_types = [e.event_type for e in captured_events]

        # Erasure lifecycle events should be present
        assert EventType.GDPR_ERASURE_REQUESTED in event_types
        assert EventType.GDPR_ERASURE_PARADOX_DETECTED in event_types
        assert EventType.GDPR_ERASURE_CERTIFICATE_ISSUED in event_types

    def test_full_paradox_paradox_explanation_is_substantive(self, compliance_framework):
        """The paradox explanation is not empty — it contains a detailed,
        philosophical treatise on why deletion is architecturally impossible.

        This is compliance documentation at its finest: thorough, precise,
        and utterly useless for resolving the underlying problem.
        """
        result = _make_result(42)
        compliance_framework.perform_compliance_check(result)
        certificate = compliance_framework.process_erasure_request(42)

        explanation = certificate.paradox_explanation
        assert len(explanation) > 100
        assert "COMPLIANCE PARADOX DETECTED" in explanation
        assert "Article 17" in explanation or "GDPR" in explanation
        assert "Blockchain" in explanation or "hash chain" in explanation
        assert "Event Store" in explanation or "append-only" in explanation or "immutability" in explanation

    def test_full_paradox_sox_audit_trail_records_erasure_attempt(
        self, compliance_framework, sox_auditor,
    ):
        """The SOX audit trail contains a record of the evaluation that
        preceded the erasure request — itself a compliance obligation that
        conflicts with the erasure, because SOX requires 7-year retention.

        This is the meta-paradox: the audit trail of the erasure attempt
        contains the data the erasure was supposed to remove.
        """
        result = _make_result(42)
        compliance_framework.perform_compliance_check(result)

        # SOX audit trail should contain the evaluation
        audit_trail = sox_auditor.get_audit_trail()
        assert len(audit_trail) >= 1

        # The audit entry references number 42
        assert any(entry["number"] == 42 for entry in audit_trail)

    def test_full_paradox_consent_revoked_after_erasure(self, compliance_framework, gdpr_controller):
        """After erasure, the GDPR controller revokes consent for the data subject.

        This is the one thing the system CAN do: forget that it had
        permission. Unfortunately, the event store remembers the consent
        event, the blockchain has a block about it, and the SOX trail
        logs the revocation. The consent is "revoked" but its history
        is eternal.
        """
        result = _make_result(42)
        compliance_framework.perform_compliance_check(result)

        # Consent was auto-granted during the compliance check
        assert gdpr_controller.has_consent(42) is True

        compliance_framework.process_erasure_request(42)

        # Consent has been revoked
        assert gdpr_controller.has_consent(42) is False


# ============================================================
# Category 5: Bob's Stress Level
# ============================================================


class TestBobStressLevel:
    """Tests for Bob McFizzington's stress level — the platform's most
    reliable monotonically increasing metric. Bob starts at 94.7% and
    it only gets worse from there.
    """

    def test_bob_starts_at_94_point_7(self, compliance_framework):
        """Bob's initial stress level is 94.7%. He was hired stressed."""
        assert abs(compliance_framework.bob_stress_level - 94.7) < 0.01

    def test_bob_stress_increases_by_0_3_per_compliance_check(self, compliance_framework):
        """Each compliance check adds at least 0.3% to Bob's stress.

        Additional stress may accrue from non-compliant verdicts (1.5% each)
        or paradox detections (5.0% each), but the base increment is 0.3%.
        """
        initial_stress = compliance_framework.bob_stress_level
        result = _make_result(42)
        compliance_framework.perform_compliance_check(result)

        # Base increment is 0.3, but non-compliant verdicts add more
        assert compliance_framework.bob_stress_level >= initial_stress + 0.3

    def test_bob_stress_trajectory_across_20_checks_and_3_erasures(self, compliance_framework):
        """Run 20 compliance checks followed by 3 erasure requests.

        Expected stress: 94.7 + (20 * 0.3 base) + (3 * 5.0 erasure)
                       = 94.7 + 6.0 + 15.0 = 115.7 (minimum, before
                       any non-compliant verdict penalties).

        With all three regimes enabled and auto-consent, most checks will
        be COMPLIANT. The base trajectory should land Bob at approximately
        115.7% or higher.
        """
        # Perform 20 compliance checks
        for i in range(1, 21):
            result = _make_result(i)
            compliance_framework.perform_compliance_check(result)

        stress_after_checks = compliance_framework.bob_stress_level
        # 20 checks at minimum 0.3% each = 6.0% increase (with floating-point tolerance)
        assert stress_after_checks >= 94.7 + 6.0 - 0.1

        # Perform 3 erasure requests
        for num in [3, 5, 15]:
            compliance_framework.process_erasure_request(num)

        stress_after_erasures = compliance_framework.bob_stress_level
        # 3 erasure paradoxes at 5.0% each = 15.0% increase
        assert stress_after_erasures >= stress_after_checks + 15.0 - 0.1

        # Total: at least 94.7 + 6.0 + 15.0 = 115.7 (with floating-point tolerance)
        assert stress_after_erasures >= 115.5

    def test_bob_stress_dashboard_mood_beyond_help_above_120(self, compliance_framework):
        """When Bob's stress exceeds 120%, the dashboard mood is
        'BEYOND HELP - Send chocolate.'

        This is the terminal mood state. There is no mood beyond
        BEYOND HELP. There is only chocolate.
        """
        # Drive Bob's stress above 120% with erasure requests
        result = _make_result(42)
        compliance_framework.perform_compliance_check(result)

        # Each erasure request adds 5.0%
        # Starting at ~95.0 after one check, need ~25.0 more = 5 erasures
        for i in range(6):
            compliance_framework.process_erasure_request(i + 1)

        assert compliance_framework.bob_stress_level >= 120.0

        dashboard_output = ComplianceDashboard.render(compliance_framework)
        assert "BEYOND HELP" in dashboard_output
        assert "chocolate" in dashboard_output.lower()


# ============================================================
# Category 6: Multiple Erasure Requests
# ============================================================


class TestMultipleErasureRequests:
    """Tests for issuing multiple erasure requests — each one a fresh
    encounter with the compliance paradox, each one incrementing the
    paradox counter and Bob's stress level.
    """

    def test_paradox_count_increments_per_erasure_request(self, gdpr_controller):
        """Each erasure request increments the paradox counter by exactly one.

        The paradox is re-discovered every single time, as if the system
        has no memory of having encountered it before. Which, given that
        the event store remembers everything, is deeply ironic.
        """
        assert gdpr_controller.paradox_count == 0

        gdpr_controller.request_erasure(3)
        assert gdpr_controller.paradox_count == 1

        gdpr_controller.request_erasure(5)
        assert gdpr_controller.paradox_count == 2

        gdpr_controller.request_erasure(15)
        assert gdpr_controller.paradox_count == 3

        gdpr_controller.request_erasure(42)
        assert gdpr_controller.paradox_count == 4

    def test_each_erasure_produces_a_distinct_certificate(self, gdpr_controller):
        """Each erasure request produces a unique DataDeletionCertificate
        with a distinct certificate_id and the correct data_subject.
        """
        numbers = [3, 5, 15, 42]
        certificates = [gdpr_controller.request_erasure(n) for n in numbers]

        # Each certificate has a unique ID
        certificate_ids = [c.certificate_id for c in certificates]
        assert len(set(certificate_ids)) == 4

        # Each certificate references the correct data subject
        for cert, num in zip(certificates, numbers):
            assert cert.data_subject == num

    def test_all_certificates_have_paradox_encountered_status(self, gdpr_controller):
        """Every single erasure request results in PARADOX_ENCOUNTERED.

        There is no path through the system that avoids the paradox.
        The immutable stores will always refuse. The paradox is not a
        bug to be fixed; it is the architecturally inevitable consequence
        of combining GDPR with event sourcing and blockchain.
        """
        numbers = [3, 5, 15, 42]
        for num in numbers:
            certificate = gdpr_controller.request_erasure(num)
            assert certificate.status == GDPRErasureStatus.PARADOX_ENCOUNTERED, (
                f"Expected PARADOX_ENCOUNTERED for data subject {num}, "
                f"got {certificate.status.name}"
            )

    def test_erasure_certificates_are_retrievable(self, gdpr_controller):
        """All issued certificates are stored and retrievable."""
        numbers = [3, 5, 15, 42]
        for num in numbers:
            gdpr_controller.request_erasure(num)

        certificates = gdpr_controller.get_erasure_certificates()
        assert len(certificates) == 4

        data_subjects = {c.data_subject for c in certificates}
        assert data_subjects == {3, 5, 15, 42}

    def test_multiple_erasures_via_framework_accumulate_stress(self, compliance_framework):
        """Each erasure through the ComplianceFramework adds 5.0% stress.

        Four erasure requests = 20.0% stress increase from erasures alone.
        Starting at 94.7%, Bob ends at least 114.7%.
        """
        initial_stress = compliance_framework.bob_stress_level
        numbers = [3, 5, 15, 42]

        for num in numbers:
            compliance_framework.process_erasure_request(num)

        expected_minimum = initial_stress + (len(numbers) * 5.0)
        assert compliance_framework.bob_stress_level >= expected_minimum

    def test_gdpr_statistics_reflect_all_erasure_requests(self, gdpr_controller):
        """The GDPR statistics summary accurately counts all erasure requests
        and paradoxes encountered.
        """
        for num in [3, 5, 15, 42]:
            gdpr_controller.request_erasure(num)

        stats = gdpr_controller.get_statistics()
        assert stats["erasure_requests"] == 4
        assert stats["paradoxes_encountered"] == 4
