"""
Enterprise FizzBuzz Platform - Compliance Chatbot Test Suite

Comprehensive tests for the Regulatory Compliance Chatbot. Because a
chatbot that dispenses GDPR/SOX/HIPAA advice about FizzBuzz operations
deserves the same level of testing rigor as any real regulatory advisory
system — which is to say, obsessively thorough and mildly paranoid.

These tests verify that:
- Intent classification correctly identifies GDPR, SOX, HIPAA, and
  cross-regime queries using regex pattern matching
- The knowledge base contains technically faithful regulatory articles
  absurdly applied to FizzBuzz operations
- Response generation produces formal COMPLIANCE ADVISORYs with proper
  verdicts, citations, and Bob McFizzington commentary
- Chat sessions maintain context for follow-up queries
- The chatbot dashboard renders without crashing
- Bob McFizzington's stress level only ever goes up
- All four custom exceptions (EFP-CC00 through EFP-CC03) work correctly
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from compliance_chatbot import (
    ChatbotDashboard,
    ChatbotIntent,
    ChatbotIntentClassifier,
    ChatbotResponse,
    ChatbotVerdict,
    ChatSession,
    ClassifiedIntent,
    ComplianceChatbot,
    ComplianceKnowledgeBase,
    KnowledgeEntry,
    ResponseGenerator,
)
from enterprise_fizzbuzz.infrastructure.compliance_chatbot import _wrap_text
from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    ChatbotIntentClassificationError,
    ChatbotKnowledgeBaseError,
    ChatbotSessionError,
    ComplianceChatbotError,
)
from models import EventType


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def classifier():
    """Create a fresh ChatbotIntentClassifier."""
    return ChatbotIntentClassifier()


@pytest.fixture
def knowledge_base():
    """Create a fresh ComplianceKnowledgeBase."""
    return ComplianceKnowledgeBase(bob_commentary_enabled=True)


@pytest.fixture
def response_generator():
    """Create a fresh ResponseGenerator."""
    return ResponseGenerator(
        include_citations=True,
        bob_commentary_enabled=True,
        formality_level="maximum",
    )


@pytest.fixture
def session():
    """Create a fresh ChatSession."""
    return ChatSession(session_id="test-session", max_history=10)


@pytest.fixture
def chatbot():
    """Create a fresh ComplianceChatbot."""
    return ComplianceChatbot(
        max_history=20,
        include_citations=True,
        bob_commentary_enabled=True,
        formality_level="maximum",
        bob_stress_level=94.7,
    )


# ============================================================
# Intent Classification Tests
# ============================================================


class TestIntentClassifier:
    """Tests for the regex-based intent classification engine."""

    def test_gdpr_erasure_intent(self, classifier):
        """GDPR erasure keywords should classify as GDPR_DATA_RIGHTS."""
        result = classifier.classify("Can I erase FizzBuzz results under GDPR?")
        assert result.intent == ChatbotIntent.GDPR_DATA_RIGHTS

    def test_gdpr_right_to_be_forgotten(self, classifier):
        """Right to be forgotten phrase should classify as GDPR_DATA_RIGHTS."""
        result = classifier.classify("Does the right to be forgotten apply to FizzBuzz?")
        assert result.intent == ChatbotIntent.GDPR_DATA_RIGHTS

    def test_gdpr_data_subject_rights(self, classifier):
        """Data subject rights should classify as GDPR_DATA_RIGHTS."""
        result = classifier.classify("What are the data subject rights for number 15?")
        assert result.intent == ChatbotIntent.GDPR_DATA_RIGHTS

    def test_gdpr_consent_intent(self, classifier):
        """Consent keywords should classify as GDPR_CONSENT."""
        result = classifier.classify("Is consent required for FizzBuzz processing?")
        assert result.intent == ChatbotIntent.GDPR_CONSENT

    def test_gdpr_opt_out(self, classifier):
        """Opt-out keywords should classify as GDPR_CONSENT."""
        result = classifier.classify("Can a number opt out of FizzBuzz evaluation?")
        assert result.intent == ChatbotIntent.GDPR_CONSENT

    def test_gdpr_lawful_basis(self, classifier):
        """Lawful basis query should classify as GDPR_CONSENT."""
        result = classifier.classify("What is the lawful basis for FizzBuzz data processing?")
        assert result.intent == ChatbotIntent.GDPR_CONSENT

    def test_sox_segregation_intent(self, classifier):
        """Segregation keywords should classify as SOX_SEGREGATION."""
        result = classifier.classify("Is segregation of duties enforced for FizzBuzz?")
        assert result.intent == ChatbotIntent.SOX_SEGREGATION

    def test_sox_section_404(self, classifier):
        """SOX Section 404 reference should classify as SOX_SEGREGATION."""
        result = classifier.classify("Does SOX Section 404 apply to FizzBuzz controls?")
        assert result.intent == ChatbotIntent.SOX_SEGREGATION

    def test_sox_audit_trail(self, classifier):
        """Audit trail keywords should classify as SOX_AUDIT."""
        result = classifier.classify("How long is the audit trail retained?")
        assert result.intent == ChatbotIntent.SOX_AUDIT

    def test_sox_record_retention(self, classifier):
        """Record retention keywords should classify as SOX_AUDIT."""
        result = classifier.classify("What is the record retention period for FizzBuzz?")
        assert result.intent == ChatbotIntent.SOX_AUDIT

    def test_hipaa_minimum_necessary(self, classifier):
        """Minimum necessary keywords should classify as HIPAA_MINIMUM_NECESSARY."""
        result = classifier.classify("What is the minimum necessary standard for FizzBuzz?")
        assert result.intent == ChatbotIntent.HIPAA_MINIMUM_NECESSARY

    def test_hipaa_de_identification(self, classifier):
        """De-identification keywords should classify as HIPAA_MINIMUM_NECESSARY."""
        result = classifier.classify("How is FizzBuzz data de-identified?")
        assert result.intent == ChatbotIntent.HIPAA_MINIMUM_NECESSARY

    def test_hipaa_phi_intent(self, classifier):
        """PHI keywords should classify as HIPAA_PHI."""
        result = classifier.classify("Are FizzBuzz results considered PHI?")
        assert result.intent == ChatbotIntent.HIPAA_PHI

    def test_hipaa_encryption(self, classifier):
        """HIPAA encryption query should classify as HIPAA_PHI."""
        result = classifier.classify("What encryption does HIPAA require for FizzBuzz?")
        assert result.intent == ChatbotIntent.HIPAA_PHI

    def test_hipaa_covered_entity(self, classifier):
        """Covered entity keywords should classify as HIPAA_PHI."""
        result = classifier.classify("Is the FizzBuzz platform a covered entity?")
        assert result.intent == ChatbotIntent.HIPAA_PHI

    def test_cross_regime_conflict_erasure_retention(self, classifier):
        """Erasure + retention should classify as CROSS_REGIME_CONFLICT."""
        result = classifier.classify(
            "GDPR says delete but SOX says retain — what do we do?"
        )
        assert result.intent == ChatbotIntent.CROSS_REGIME_CONFLICT

    def test_cross_regime_paradox(self, classifier):
        """Paradox keyword should classify as CROSS_REGIME_CONFLICT."""
        result = classifier.classify("What is the compliance paradox?")
        assert result.intent == ChatbotIntent.CROSS_REGIME_CONFLICT

    def test_cross_regime_gdpr_sox_mention(self, classifier):
        """Mentioning GDPR and SOX together should trigger CROSS_REGIME_CONFLICT."""
        result = classifier.classify("How do GDPR and SOX interact for FizzBuzz?")
        assert result.intent == ChatbotIntent.CROSS_REGIME_CONFLICT

    def test_general_compliance(self, classifier):
        """General compliance keywords should classify as GENERAL_COMPLIANCE."""
        result = classifier.classify("Is FizzBuzz compliant with regulations?")
        assert result.intent == ChatbotIntent.GENERAL_COMPLIANCE

    def test_bob_mcfizzington_query(self, classifier):
        """Mentioning Bob should classify as GENERAL_COMPLIANCE."""
        result = classifier.classify("What is Bob McFizzington's stress level?")
        assert result.intent == ChatbotIntent.GENERAL_COMPLIANCE

    def test_unknown_intent(self, classifier):
        """Completely irrelevant query should classify as UNKNOWN."""
        result = classifier.classify("What is the weather like today?")
        assert result.intent == ChatbotIntent.UNKNOWN

    def test_empty_query(self, classifier):
        """Empty query should classify as UNKNOWN with zero confidence."""
        result = classifier.classify("")
        assert result.intent == ChatbotIntent.UNKNOWN
        assert result.confidence == 0.0

    def test_confidence_increases_with_matches(self, classifier):
        """More keyword matches should yield higher confidence."""
        low = classifier.classify("erasure")
        high = classifier.classify("GDPR right to erasure data subject right to be forgotten")
        assert high.confidence >= low.confidence

    def test_matched_keywords_populated(self, classifier):
        """Classified intents should include the matched keywords."""
        result = classifier.classify("Can I erase FizzBuzz data?")
        assert len(result.matched_keywords) > 0

    def test_statistics_tracking(self, classifier):
        """Classification statistics should be tracked."""
        classifier.classify("GDPR erasure")
        classifier.classify("SOX audit trail")
        classifier.classify("unknown stuff")
        stats = classifier.get_statistics()
        assert stats["total"] == 3
        assert len(stats["by_intent"]) >= 2


# ============================================================
# Knowledge Base Tests
# ============================================================


class TestKnowledgeBase:
    """Tests for the regulatory compliance knowledge base."""

    def test_knowledge_base_has_entries(self, knowledge_base):
        """Knowledge base should have at least 20 entries."""
        assert knowledge_base.total_entries >= 20

    def test_gdpr_data_rights_entries(self, knowledge_base):
        """GDPR_DATA_RIGHTS should have multiple knowledge entries."""
        entries = knowledge_base.lookup(ChatbotIntent.GDPR_DATA_RIGHTS)
        assert len(entries) >= 3
        # Should include Art. 17 (erasure)
        article_ids = [e.article_id for e in entries]
        assert any("Art. 17" in a for a in article_ids)

    def test_gdpr_consent_entries(self, knowledge_base):
        """GDPR_CONSENT should have knowledge entries."""
        entries = knowledge_base.lookup(ChatbotIntent.GDPR_CONSENT)
        assert len(entries) >= 2

    def test_sox_segregation_entries(self, knowledge_base):
        """SOX_SEGREGATION should have knowledge entries."""
        entries = knowledge_base.lookup(ChatbotIntent.SOX_SEGREGATION)
        assert len(entries) >= 1
        article_ids = [e.article_id for e in entries]
        assert any("Sec. 404" in a for a in article_ids)

    def test_sox_audit_entries(self, knowledge_base):
        """SOX_AUDIT should have knowledge entries about record retention."""
        entries = knowledge_base.lookup(ChatbotIntent.SOX_AUDIT)
        assert len(entries) >= 1
        article_ids = [e.article_id for e in entries]
        assert any("Sec. 802" in a for a in article_ids)

    def test_hipaa_minimum_necessary_entries(self, knowledge_base):
        """HIPAA_MINIMUM_NECESSARY should have knowledge entries."""
        entries = knowledge_base.lookup(ChatbotIntent.HIPAA_MINIMUM_NECESSARY)
        assert len(entries) >= 1

    def test_hipaa_phi_entries(self, knowledge_base):
        """HIPAA_PHI should have knowledge entries about PHI protection."""
        entries = knowledge_base.lookup(ChatbotIntent.HIPAA_PHI)
        assert len(entries) >= 2

    def test_cross_regime_conflict_entries(self, knowledge_base):
        """CROSS_REGIME_CONFLICT should have paradox entries."""
        entries = knowledge_base.lookup(ChatbotIntent.CROSS_REGIME_CONFLICT)
        assert len(entries) >= 2
        # The erasure-retention paradox must be present
        assert any("paradox" in e.title.lower() or "Art. 17" in e.article_id for e in entries)

    def test_general_compliance_entries(self, knowledge_base):
        """GENERAL_COMPLIANCE should have overview entries."""
        entries = knowledge_base.lookup(ChatbotIntent.GENERAL_COMPLIANCE)
        assert len(entries) >= 1

    def test_unknown_falls_back_to_general(self, knowledge_base):
        """UNKNOWN intent should fall back to general compliance entries."""
        entries = knowledge_base.lookup(ChatbotIntent.UNKNOWN)
        assert len(entries) >= 1

    def test_article_citation_filter(self, knowledge_base):
        """Looking up a specific article number should filter results."""
        entries = knowledge_base.lookup(ChatbotIntent.GDPR_DATA_RIGHTS, "GDPR Art. 17")
        assert len(entries) >= 1
        assert any("Art. 17" in e.article_id for e in entries)

    def test_all_entries_have_fizzbuzz_interpretation(self, knowledge_base):
        """Every knowledge entry should have a FizzBuzz interpretation."""
        for intent in ChatbotIntent:
            entries = knowledge_base.lookup(intent)
            for entry in entries:
                assert len(entry.fizzbuzz_interpretation) > 0

    def test_all_entries_have_recommendation(self, knowledge_base):
        """Every knowledge entry should have a recommendation."""
        for intent in ChatbotIntent:
            entries = knowledge_base.lookup(intent)
            for entry in entries:
                assert len(entry.recommendation) > 0

    def test_get_all_articles(self, knowledge_base):
        """get_all_articles should return all article IDs."""
        articles = knowledge_base.get_all_articles()
        assert len(articles) >= 20
        assert any("GDPR" in a for a in articles)
        assert any("SOX" in a for a in articles)
        assert any("HIPAA" in a or "CFR" in a for a in articles)

    def test_lookup_count_tracking(self, knowledge_base):
        """Lookups should be counted."""
        assert knowledge_base.total_lookups == 0
        knowledge_base.lookup(ChatbotIntent.GDPR_DATA_RIGHTS)
        knowledge_base.lookup(ChatbotIntent.SOX_AUDIT)
        assert knowledge_base.total_lookups == 2

    def test_cross_regime_erasure_retention_verdict(self, knowledge_base):
        """The erasure-retention paradox should have CONDITIONALLY_COMPLIANT verdict."""
        entries = knowledge_base.lookup(ChatbotIntent.CROSS_REGIME_CONFLICT)
        erasure_retention = [e for e in entries if "Art. 17" in e.article_id and "802" in e.article_id]
        assert len(erasure_retention) >= 1
        assert erasure_retention[0].verdict == ChatbotVerdict.CONDITIONALLY_COMPLIANT


# ============================================================
# Response Generator Tests
# ============================================================


class TestResponseGenerator:
    """Tests for the formal compliance advisory response generator."""

    def test_generate_basic_response(self, response_generator, knowledge_base):
        """Should generate a response with all required fields."""
        intent = ClassifiedIntent(
            intent=ChatbotIntent.GDPR_DATA_RIGHTS,
            confidence=0.8,
            matched_keywords=("erasure",),
            raw_query="Can I erase FizzBuzz data?",
        )
        entries = knowledge_base.lookup(ChatbotIntent.GDPR_DATA_RIGHTS)
        response = response_generator.generate(intent, entries)

        assert response.intent == ChatbotIntent.GDPR_DATA_RIGHTS
        assert response.verdict in ChatbotVerdict
        assert len(response.summary) > 0
        assert len(response.explanation) > 0
        assert len(response.recommendation) > 0
        assert len(response.advisory_id) > 0

    def test_generate_includes_citations(self, response_generator, knowledge_base):
        """Response should include article citations when enabled."""
        intent = ClassifiedIntent(
            intent=ChatbotIntent.SOX_AUDIT,
            confidence=0.7,
            matched_keywords=("audit",),
            raw_query="SOX audit trail",
        )
        entries = knowledge_base.lookup(ChatbotIntent.SOX_AUDIT)
        response = response_generator.generate(intent, entries)
        assert len(response.cited_articles) > 0

    def test_generate_includes_bob_commentary(self, response_generator, knowledge_base):
        """Response should include Bob's commentary when enabled."""
        intent = ClassifiedIntent(
            intent=ChatbotIntent.GDPR_DATA_RIGHTS,
            confidence=0.8,
            matched_keywords=("erasure",),
            raw_query="GDPR erasure",
        )
        entries = knowledge_base.lookup(ChatbotIntent.GDPR_DATA_RIGHTS)
        response = response_generator.generate(intent, entries)
        assert "Bob McFizzington" in response.bob_commentary

    def test_generate_without_citations(self, knowledge_base):
        """Response without citations should have empty cited_articles."""
        gen = ResponseGenerator(include_citations=False, bob_commentary_enabled=True)
        intent = ClassifiedIntent(
            intent=ChatbotIntent.GDPR_DATA_RIGHTS,
            confidence=0.8,
            matched_keywords=("erasure",),
            raw_query="GDPR erasure",
        )
        entries = knowledge_base.lookup(ChatbotIntent.GDPR_DATA_RIGHTS)
        response = gen.generate(intent, entries)
        assert response.cited_articles == []

    def test_generate_with_context_number(self, response_generator, knowledge_base):
        """Response should mention the context number when provided."""
        intent = ClassifiedIntent(
            intent=ChatbotIntent.GDPR_DATA_RIGHTS,
            confidence=0.8,
            matched_keywords=("erasure",),
            raw_query="erase 15",
        )
        entries = knowledge_base.lookup(ChatbotIntent.GDPR_DATA_RIGHTS)
        response = response_generator.generate(intent, entries, context_number=15)
        assert "15" in response.explanation

    def test_generate_unknown_response(self, response_generator):
        """Unknown intent with no entries should produce a REQUIRES_REVIEW response."""
        intent = ClassifiedIntent(
            intent=ChatbotIntent.UNKNOWN,
            confidence=0.0,
            raw_query="What is life?",
        )
        response = response_generator.generate(intent, [])
        assert response.verdict == ChatbotVerdict.REQUIRES_REVIEW
        assert "unable" in response.explanation.lower() or "unable" in response.summary.lower()

    def test_stress_delta_varies_by_verdict(self, response_generator, knowledge_base):
        """Non-compliant verdicts should generate higher stress deltas."""
        # COMPLIANT entry
        intent = ClassifiedIntent(
            intent=ChatbotIntent.SOX_SEGREGATION,
            confidence=0.8,
            matched_keywords=("segregation",),
            raw_query="segregation",
        )
        entries = knowledge_base.lookup(ChatbotIntent.SOX_SEGREGATION)
        resp_compliant = response_generator.generate(intent, entries)

        # Unknown entry (REQUIRES_REVIEW)
        intent_unk = ClassifiedIntent(
            intent=ChatbotIntent.UNKNOWN,
            confidence=0.0,
            raw_query="???",
        )
        resp_review = response_generator.generate(intent_unk, [])

        assert resp_review.bob_stress_delta >= resp_compliant.bob_stress_delta

    def test_response_time_tracked(self, response_generator, knowledge_base):
        """Response time should be measured."""
        intent = ClassifiedIntent(
            intent=ChatbotIntent.GDPR_CONSENT,
            confidence=0.7,
            matched_keywords=("consent",),
            raw_query="consent",
        )
        entries = knowledge_base.lookup(ChatbotIntent.GDPR_CONSENT)
        response = response_generator.generate(intent, entries)
        assert response.response_time_ms >= 0.0

    def test_total_responses_tracked(self, response_generator, knowledge_base):
        """Total response count should increment."""
        assert response_generator.total_responses == 0
        intent = ClassifiedIntent(intent=ChatbotIntent.GDPR_CONSENT, confidence=0.7, raw_query="consent")
        entries = knowledge_base.lookup(ChatbotIntent.GDPR_CONSENT)
        response_generator.generate(intent, entries)
        response_generator.generate(intent, entries)
        assert response_generator.total_responses == 2


# ============================================================
# Chat Session Tests
# ============================================================


class TestChatSession:
    """Tests for conversation memory and context resolution."""

    def test_session_creation(self, session):
        """Session should initialize with empty history."""
        assert session.turn_count == 0
        assert session.current_number is None
        assert session.current_intent is None

    def test_add_turn(self, session):
        """Adding a turn should update the history."""
        intent = ClassifiedIntent(intent=ChatbotIntent.GDPR_DATA_RIGHTS, confidence=0.8, raw_query="erasure")
        response = ChatbotResponse(intent=ChatbotIntent.GDPR_DATA_RIGHTS, verdict=ChatbotVerdict.COMPLIANT)
        session.add_turn("Can I erase data?", intent, response, context_number=15)

        assert session.turn_count == 1
        assert session.current_number == 15
        assert session.current_intent == ChatbotIntent.GDPR_DATA_RIGHTS

    def test_context_resolution_follow_up_number(self, session):
        """Follow-up with new number should use previous intent."""
        # First turn: discuss erasure for number 15
        intent1 = ClassifiedIntent(intent=ChatbotIntent.GDPR_DATA_RIGHTS, confidence=0.8, raw_query="erase 15")
        resp1 = ChatbotResponse(intent=ChatbotIntent.GDPR_DATA_RIGHTS, verdict=ChatbotVerdict.COMPLIANT)
        session.add_turn("Can I erase number 15?", intent1, resp1, context_number=15)

        # Follow-up: "What about 16?" — low confidence UNKNOWN
        intent2 = ClassifiedIntent(intent=ChatbotIntent.UNKNOWN, confidence=0.1, raw_query="What about 16?")
        resolved_number, resolved_intent = session.resolve_context("What about 16?", intent2)

        assert resolved_number == 16
        assert resolved_intent == ChatbotIntent.GDPR_DATA_RIGHTS  # inherited from previous turn

    def test_context_resolution_no_number(self, session):
        """Follow-up without number should use previous number."""
        intent1 = ClassifiedIntent(intent=ChatbotIntent.HIPAA_PHI, confidence=0.8, raw_query="PHI")
        resp1 = ChatbotResponse(intent=ChatbotIntent.HIPAA_PHI, verdict=ChatbotVerdict.COMPLIANT)
        session.add_turn("Is 42 PHI?", intent1, resp1, context_number=42)

        intent2 = ClassifiedIntent(intent=ChatbotIntent.UNKNOWN, confidence=0.1, raw_query="And what about encryption?")
        resolved_number, resolved_intent = session.resolve_context("And what about encryption?", intent2)

        assert resolved_number == 42  # carried from previous turn

    def test_max_history_enforcement(self):
        """Session should enforce max history limit."""
        session = ChatSession(max_history=3)
        for i in range(5):
            intent = ClassifiedIntent(intent=ChatbotIntent.GENERAL_COMPLIANCE, confidence=0.5, raw_query=f"q{i}")
            resp = ChatbotResponse()
            session.add_turn(f"question {i}", intent, resp, context_number=i)

        assert session.turn_count == 3  # only last 3 retained

    def test_session_statistics(self, session):
        """Session statistics should reflect the conversation."""
        intent = ClassifiedIntent(intent=ChatbotIntent.GDPR_DATA_RIGHTS, confidence=0.8, raw_query="erasure")
        resp = ChatbotResponse(
            intent=ChatbotIntent.GDPR_DATA_RIGHTS,
            verdict=ChatbotVerdict.COMPLIANT,
            bob_stress_delta=0.5,
        )
        session.add_turn("erasure question", intent, resp, context_number=15)

        stats = session.get_statistics()
        assert stats["total_turns"] == 1
        assert stats["total_bob_stress_added"] == 0.5
        assert stats["current_number"] == 15
        assert "GDPR_DATA_RIGHTS" in stats["intents"]


# ============================================================
# Compliance Chatbot Integration Tests
# ============================================================


class TestComplianceChatbot:
    """Integration tests for the full chatbot pipeline."""

    def test_ask_gdpr_erasure(self, chatbot):
        """Asking about GDPR erasure should return a proper advisory."""
        response = chatbot.ask("Can I erase FizzBuzz results under GDPR?")
        assert response.intent == ChatbotIntent.GDPR_DATA_RIGHTS
        assert response.verdict in (ChatbotVerdict.COMPLIANT, ChatbotVerdict.CONDITIONALLY_COMPLIANT)
        assert len(response.explanation) > 0

    def test_ask_sox_segregation(self, chatbot):
        """Asking about SOX segregation should return SOX_SEGREGATION advisory."""
        response = chatbot.ask("Is segregation of duties enforced?")
        assert response.intent == ChatbotIntent.SOX_SEGREGATION

    def test_ask_hipaa_phi(self, chatbot):
        """Asking about PHI should return HIPAA_PHI advisory."""
        response = chatbot.ask("Are FizzBuzz results protected health information?")
        assert response.intent == ChatbotIntent.HIPAA_PHI

    def test_ask_cross_regime_conflict(self, chatbot):
        """Asking about GDPR vs SOX should detect cross-regime conflict."""
        response = chatbot.ask("GDPR says delete but SOX says retain — what gives?")
        assert response.intent == ChatbotIntent.CROSS_REGIME_CONFLICT
        assert response.verdict == ChatbotVerdict.CONDITIONALLY_COMPLIANT

    def test_cross_regime_recommends_pseudonymization(self, chatbot):
        """Cross-regime conflict response should recommend pseudonymization."""
        response = chatbot.ask("How do I handle the erasure-retention paradox between GDPR and SOX?")
        assert "pseudonymiz" in response.recommendation.lower()

    def test_bob_stress_increases(self, chatbot):
        """Bob's stress level should increase after each query."""
        initial = chatbot.bob_stress_level
        chatbot.ask("Is FizzBuzz GDPR compliant?")
        assert chatbot.bob_stress_level > initial

    def test_bob_stress_never_decreases(self, chatbot):
        """Bob's stress should only go up, never down."""
        levels = [chatbot.bob_stress_level]
        for q in ["GDPR erasure", "SOX audit", "HIPAA PHI"]:
            chatbot.ask(q)
            levels.append(chatbot.bob_stress_level)

        for i in range(1, len(levels)):
            assert levels[i] >= levels[i - 1]

    def test_follow_up_context(self, chatbot):
        """Follow-up query should inherit context from previous turn."""
        chatbot.ask("Can I erase number 15 under the right to erasure?")
        response2 = chatbot.ask("What about 16?")
        # Should still be about GDPR_DATA_RIGHTS, with number context 16
        assert response2.intent == ChatbotIntent.GDPR_DATA_RIGHTS
        assert "16" in response2.explanation

    def test_session_turn_tracking(self, chatbot):
        """Response turn numbers should increment."""
        r1 = chatbot.ask("GDPR consent")
        r2 = chatbot.ask("SOX audit")
        assert r1.session_turn == 1
        assert r2.session_turn == 2

    def test_total_queries_tracked(self, chatbot):
        """Total query count should increment."""
        assert chatbot.total_queries == 0
        chatbot.ask("test")
        chatbot.ask("test")
        assert chatbot.total_queries == 2

    def test_get_statistics(self, chatbot):
        """Statistics should include all subsystem stats."""
        chatbot.ask("GDPR erasure")
        stats = chatbot.get_statistics()
        assert stats["total_queries"] == 1
        assert "session" in stats
        assert "classifier" in stats
        assert "knowledge_base" in stats
        assert stats["bob_stress_level"] > 94.7

    def test_unknown_query_handled_gracefully(self, chatbot):
        """Unknown queries should not crash and should return REQUIRES_REVIEW."""
        response = chatbot.ask("What is the meaning of life?")
        assert response.verdict == ChatbotVerdict.REQUIRES_REVIEW

    def test_empty_query_handled(self, chatbot):
        """Empty query should be handled gracefully."""
        response = chatbot.ask("")
        assert response.verdict == ChatbotVerdict.REQUIRES_REVIEW

    def test_event_bus_integration(self):
        """Chatbot should emit events when event_bus is provided."""
        events_received = []

        class MockEventBus:
            def publish(self, event):
                events_received.append(event)

        chatbot = ComplianceChatbot(event_bus=MockEventBus())
        chatbot.ask("GDPR erasure question")

        event_types = [e.event_type for e in events_received]
        assert EventType.CHATBOT_SESSION_STARTED in event_types
        assert EventType.CHATBOT_QUERY_RECEIVED in event_types
        assert EventType.CHATBOT_INTENT_CLASSIFIED in event_types
        assert EventType.CHATBOT_RESPONSE_GENERATED in event_types


# ============================================================
# Dashboard Rendering Tests
# ============================================================


class TestChatbotDashboard:
    """Tests for the ASCII dashboard rendering."""

    def test_render_response(self, chatbot):
        """render_response should produce formatted text."""
        response = chatbot.ask("Is FizzBuzz GDPR compliant?")
        output = ChatbotDashboard.render_response(response)
        assert "COMPLIANCE ADVISORY" in output
        assert "VERDICT" in output
        assert "SUMMARY" in output
        assert "EXPLANATION" in output
        assert "RECOMMENDATION" in output

    def test_render_response_includes_citations(self, chatbot):
        """Rendered response should include cited articles."""
        response = chatbot.ask("GDPR Art. 17 erasure")
        output = ChatbotDashboard.render_response(response)
        assert "CITED ARTICLES" in output

    def test_render_response_includes_bob(self, chatbot):
        """Rendered response should include Bob's commentary."""
        response = chatbot.ask("SOX segregation of duties")
        output = ChatbotDashboard.render_response(response)
        assert "BOB McFIZZINGTON" in output

    def test_render_session_dashboard(self, chatbot):
        """render_session should produce formatted dashboard."""
        chatbot.ask("GDPR consent")
        chatbot.ask("SOX audit trail")
        output = ChatbotDashboard.render_session(chatbot.session)
        assert "SESSION DASHBOARD" in output
        assert "Total Turns" in output

    def test_render_custom_width(self, chatbot):
        """Dashboard should respect custom width parameter."""
        response = chatbot.ask("HIPAA PHI")
        output = ChatbotDashboard.render_response(response, width=80)
        # Should have wider lines
        lines = output.split("\n")
        border_lines = [l for l in lines if l.strip().startswith("+") and l.strip().endswith("+")]
        if border_lines:
            assert len(border_lines[0].strip()) == 80


# ============================================================
# Exception Tests
# ============================================================


class TestChatbotExceptions:
    """Tests for the four chatbot exception classes."""

    def test_base_chatbot_error(self):
        """ComplianceChatbotError should have EFP-CC00 code."""
        err = ComplianceChatbotError("test error")
        assert "EFP-CC00" in str(err)

    def test_intent_classification_error(self):
        """ChatbotIntentClassificationError should have EFP-CC01 code."""
        err = ChatbotIntentClassificationError("some weird query")
        assert "EFP-CC01" in str(err)
        assert err.query == "some weird query"

    def test_knowledge_base_error(self):
        """ChatbotKnowledgeBaseError should have EFP-CC02 code."""
        err = ChatbotKnowledgeBaseError("GDPR_DATA_RIGHTS", "quantum erasure")
        assert "EFP-CC02" in str(err)
        assert err.intent == "GDPR_DATA_RIGHTS"
        assert err.topic == "quantum erasure"

    def test_session_error(self):
        """ChatbotSessionError should have EFP-CC03 code."""
        err = ChatbotSessionError("sess-123", "context overflow")
        assert "EFP-CC03" in str(err)
        assert err.session_id == "sess-123"

    def test_exception_hierarchy(self):
        """All chatbot exceptions should inherit from ComplianceChatbotError."""
        assert issubclass(ChatbotIntentClassificationError, ComplianceChatbotError)
        assert issubclass(ChatbotKnowledgeBaseError, ComplianceChatbotError)
        assert issubclass(ChatbotSessionError, ComplianceChatbotError)


# ============================================================
# Utility Function Tests
# ============================================================


class TestWrapText:
    """Tests for the text wrapping utility."""

    def test_wrap_short_text(self):
        """Short text should not be wrapped."""
        result = _wrap_text("hello", 20)
        assert result == ["hello"]

    def test_wrap_long_text(self):
        """Long text should be wrapped at word boundaries."""
        result = _wrap_text("this is a long sentence that needs wrapping", 15)
        assert len(result) > 1
        for line in result:
            assert len(line) <= 15

    def test_wrap_empty_text(self):
        """Empty text should return single empty string."""
        result = _wrap_text("", 20)
        assert result == [""]


# ============================================================
# EventType Tests
# ============================================================


class TestChatbotEventTypes:
    """Tests for the chatbot EventType entries."""

    def test_chatbot_query_received_exists(self):
        """CHATBOT_QUERY_RECEIVED EventType should exist."""
        assert hasattr(EventType, "CHATBOT_QUERY_RECEIVED")

    def test_chatbot_intent_classified_exists(self):
        """CHATBOT_INTENT_CLASSIFIED EventType should exist."""
        assert hasattr(EventType, "CHATBOT_INTENT_CLASSIFIED")

    def test_chatbot_response_generated_exists(self):
        """CHATBOT_RESPONSE_GENERATED EventType should exist."""
        assert hasattr(EventType, "CHATBOT_RESPONSE_GENERATED")

    def test_chatbot_session_started_exists(self):
        """CHATBOT_SESSION_STARTED EventType should exist."""
        assert hasattr(EventType, "CHATBOT_SESSION_STARTED")
