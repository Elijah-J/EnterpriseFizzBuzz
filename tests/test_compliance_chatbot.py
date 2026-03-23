"""
Enterprise FizzBuzz Platform - Compliance Chatbot & NLQ Engine Test Suite

Comprehensive tests for the Regulatory Compliance Chatbot and the Natural
Language Query (NLQ) engine. Two regex-powered NLP interfaces, unified
under one test file, because testing them separately was an organizational
overhead that even we could not justify.

Compliance Chatbot tests verify that:
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

NLQ Engine tests verify that:
- Tokenization correctly classifies numbers, keywords, operators, and
  classifiers from natural language FizzBuzz queries
- Intent classification distinguishes EVALUATE, COUNT, LIST, STATISTICS,
  and EXPLAIN intents using keyword heuristics
- Entity extraction pulls numbers, ranges, classifications, and filters
  from token sequences
- Query execution produces correct FizzBuzz results for all five intents
- Session tracking maintains query history and intent distributions
- The NLQ dashboard renders without crashing
- All five NLQ exceptions (EFP-NLQ1 through EFP-NLQ5) work correctly
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
    EntityExtractor,
    Intent,
    IntentClassifier,
    KnowledgeEntry,
    NLQDashboard,
    NLQEngine,
    NLQSession,
    QueryEntities,
    QueryExecutor,
    QueryResponse,
    ResponseGenerator,
    Token,
    TokenType,
    Tokenizer,
)
from enterprise_fizzbuzz.infrastructure.compliance_chatbot import (
    _apply_number_filter,
    _classify_result,
    _get_default_rules,
    _is_prime,
    _wrap_text,
)
from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    ChatbotIntentClassificationError,
    ChatbotKnowledgeBaseError,
    ChatbotSessionError,
    ComplianceChatbotError,
    NLQEntityExtractionError,
    NLQExecutionError,
    NLQIntentClassificationError,
    NLQTokenizationError,
    NLQUnsupportedQueryError,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule, StandardRuleEngine
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


# ============================================================
# NLQ Tokenizer Tests
# ============================================================


class TestTokenizer:
    """Tests for the regex-based Tokenizer."""

    def setup_method(self) -> None:
        self.tokenizer = Tokenizer()

    def test_tokenize_simple_query(self) -> None:
        tokens = self.tokenizer.tokenize("Is 15 FizzBuzz?")
        assert len(tokens) >= 3
        types = [t.token_type for t in tokens]
        assert TokenType.QUESTION in types
        assert TokenType.NUMBER in types
        assert TokenType.PUNCTUATION in types

    def test_tokenize_number_extraction(self) -> None:
        tokens = self.tokenizer.tokenize("42")
        assert len(tokens) == 1
        assert tokens[0].token_type == TokenType.NUMBER
        assert tokens[0].text == "42"

    def test_tokenize_classifier_words(self) -> None:
        tokens = self.tokenizer.tokenize("fizz buzz fizzbuzz")
        classifiers = [t for t in tokens if t.token_type == TokenType.CLASSIFIER]
        assert len(classifiers) == 3

    def test_tokenize_filter_words(self) -> None:
        tokens = self.tokenizer.tokenize("prime even odd")
        filters = [t for t in tokens if t.token_type == TokenType.FILTER]
        assert len(filters) == 3

    def test_tokenize_operator_words(self) -> None:
        tokens = self.tokenizer.tokenize("below above between")
        operators = [t for t in tokens if t.token_type == TokenType.OPERATOR]
        assert len(operators) == 3

    def test_tokenize_empty_string_raises(self) -> None:
        with pytest.raises(NLQTokenizationError):
            self.tokenizer.tokenize("")

    def test_tokenize_whitespace_only_raises(self) -> None:
        with pytest.raises(NLQTokenizationError):
            self.tokenizer.tokenize("   ")

    def test_tokenize_preserves_position(self) -> None:
        tokens = self.tokenizer.tokenize("Is 15 Fizz?")
        # "Is" starts at 0
        assert tokens[0].position == 0

    def test_tokenize_normalizes_to_lowercase(self) -> None:
        tokens = self.tokenizer.tokenize("FIZZ BUZZ")
        assert tokens[0].normalized == "fizz"
        assert tokens[1].normalized == "buzz"

    def test_tokenize_question_words(self) -> None:
        tokens = self.tokenizer.tokenize("what why how which")
        question_tokens = [t for t in tokens if t.token_type == TokenType.QUESTION]
        assert len(question_tokens) == 4

    def test_tokenize_unknown_words_are_WORD(self) -> None:
        tokens = self.tokenizer.tokenize("xyzzy plugh")
        assert all(t.token_type == TokenType.WORD for t in tokens)

    def test_tokenize_mixed_query(self) -> None:
        tokens = self.tokenizer.tokenize("How many primes below 50 are fizz?")
        types = {t.token_type for t in tokens}
        assert TokenType.QUESTION in types
        assert TokenType.FILTER in types
        assert TokenType.OPERATOR in types
        assert TokenType.NUMBER in types
        assert TokenType.CLASSIFIER in types


# ============================================================
# NLQ Intent Classifier Tests
# ============================================================


class TestNLQIntentClassifier:
    """Tests for the rule-based NLQ IntentClassifier."""

    def setup_method(self) -> None:
        self.classifier = IntentClassifier()
        self.tokenizer = Tokenizer()

    def _classify(self, query: str) -> Intent:
        tokens = self.tokenizer.tokenize(query)
        return self.classifier.classify(tokens)

    def test_evaluate_is_n_fizzbuzz(self) -> None:
        assert self._classify("Is 15 FizzBuzz?") == Intent.EVALUATE

    def test_evaluate_what_is_n(self) -> None:
        assert self._classify("What is 42?") == Intent.EVALUATE

    def test_evaluate_just_a_number(self) -> None:
        assert self._classify("15") == Intent.EVALUATE

    def test_evaluate_check_number(self) -> None:
        assert self._classify("Check 99") == Intent.EVALUATE

    def test_count_how_many(self) -> None:
        assert self._classify("How many fizzes below 100?") == Intent.COUNT

    def test_count_word(self) -> None:
        assert self._classify("Count fizzbuzz between 1 and 50") == Intent.COUNT

    def test_count_total(self) -> None:
        assert self._classify("Total buzz below 200") == Intent.COUNT

    def test_list_which(self) -> None:
        assert self._classify("Which primes are buzz?") == Intent.LIST

    def test_list_command(self) -> None:
        assert self._classify("List all fizzbuzz below 30") == Intent.LIST

    def test_list_show_all(self) -> None:
        assert self._classify("Show all prime fizz") == Intent.LIST

    def test_statistics_common(self) -> None:
        assert self._classify("What is the most common classification?") == Intent.STATISTICS

    def test_statistics_distribution(self) -> None:
        assert self._classify("Show distribution") == Intent.STATISTICS

    def test_statistics_breakdown(self) -> None:
        assert self._classify("Give me the breakdown") == Intent.STATISTICS

    def test_explain_why(self) -> None:
        assert self._classify("Why is 9 Fizz?") == Intent.EXPLAIN

    def test_explain_command(self) -> None:
        assert self._classify("Explain 15") == Intent.EXPLAIN

    def test_empty_tokens_raises(self) -> None:
        with pytest.raises(NLQIntentClassificationError):
            self.classifier.classify([])

    def test_filter_only_defaults_to_list(self) -> None:
        assert self._classify("prime") == Intent.LIST

    def test_evaluate_classify_command(self) -> None:
        assert self._classify("Classify 7") == Intent.EVALUATE


# ============================================================
# NLQ Entity Extractor Tests
# ============================================================


class TestEntityExtractor:
    """Tests for the EntityExtractor."""

    def setup_method(self) -> None:
        self.extractor = EntityExtractor()
        self.tokenizer = Tokenizer()

    def _extract(self, query: str, intent: Intent) -> QueryEntities:
        tokens = self.tokenizer.tokenize(query)
        return self.extractor.extract(tokens, intent)

    def test_extract_single_number(self) -> None:
        entities = self._extract("Is 15 FizzBuzz?", Intent.EVALUATE)
        assert entities.numbers == [15]

    def test_extract_multiple_numbers(self) -> None:
        entities = self._extract("between 10 and 20", Intent.COUNT)
        assert 10 in entities.numbers
        assert 20 in entities.numbers

    def test_extract_classification_fizz(self) -> None:
        entities = self._extract("How many fizz below 100?", Intent.COUNT)
        assert "fizz" in entities.classifications

    def test_extract_classification_fizzbuzz(self) -> None:
        entities = self._extract("Is 15 fizzbuzz?", Intent.EVALUATE)
        assert "fizzbuzz" in entities.classifications

    def test_extract_filter_prime(self) -> None:
        entities = self._extract("Which primes are buzz?", Intent.LIST)
        assert "prime" in entities.filters

    def test_extract_filter_even(self) -> None:
        entities = self._extract("List even fizz", Intent.LIST)
        assert "even" in entities.filters

    def test_extract_range_below(self) -> None:
        entities = self._extract("How many fizz below 50?", Intent.COUNT)
        assert entities.range_end == 49
        assert entities.range_start == 1

    def test_extract_range_above(self) -> None:
        entities = self._extract("Numbers above 50", Intent.LIST)
        assert entities.range_start == 51

    def test_extract_range_between(self) -> None:
        entities = self._extract("Between 10 and 20", Intent.COUNT)
        assert entities.range_start == 10
        assert entities.range_end == 20

    def test_extract_range_from_to(self) -> None:
        entities = self._extract("From 5 to 25", Intent.LIST)
        assert entities.range_start == 5
        assert entities.range_end == 25

    def test_extract_number_as_plain(self) -> None:
        entities = self._extract("Which numbers are plain?", Intent.LIST)
        assert "plain" in entities.classifications

    def test_extract_less_than(self) -> None:
        entities = self._extract("Less than 30", Intent.COUNT)
        assert entities.range_end == 29

    def test_extract_default_range(self) -> None:
        entities = self._extract("What is 15?", Intent.EVALUATE)
        assert entities.range_start == 1
        assert entities.range_end == 100


# ============================================================
# NLQ Query Executor Tests
# ============================================================


class TestQueryExecutor:
    """Tests for the QueryExecutor."""

    def setup_method(self) -> None:
        self.executor = QueryExecutor()

    def test_evaluate_15_is_fizzbuzz(self) -> None:
        entities = QueryEntities(numbers=[15], raw_query="Is 15 FizzBuzz?")
        response = self.executor.execute(Intent.EVALUATE, entities)
        assert response.data["classification"] == "fizzbuzz"
        assert response.data["output"] == "FizzBuzz"

    def test_evaluate_3_is_fizz(self) -> None:
        entities = QueryEntities(numbers=[3], raw_query="Is 3 Fizz?")
        response = self.executor.execute(Intent.EVALUATE, entities)
        assert response.data["classification"] == "fizz"

    def test_evaluate_5_is_buzz(self) -> None:
        entities = QueryEntities(numbers=[5], raw_query="Is 5 Buzz?")
        response = self.executor.execute(Intent.EVALUATE, entities)
        assert response.data["classification"] == "buzz"

    def test_evaluate_7_is_plain(self) -> None:
        entities = QueryEntities(numbers=[7], raw_query="What is 7?")
        response = self.executor.execute(Intent.EVALUATE, entities)
        assert response.data["classification"] == "plain"

    def test_evaluate_no_numbers_raises(self) -> None:
        entities = QueryEntities(numbers=[], raw_query="Is FizzBuzz?")
        with pytest.raises(NLQEntityExtractionError):
            self.executor.execute(Intent.EVALUATE, entities)

    def test_count_fizz_below_16(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=15,
            classifications=["fizz"],
            raw_query="How many fizz below 16?",
        )
        response = self.executor.execute(Intent.COUNT, entities)
        # Fizz in [1..15]: 3, 6, 9, 12 (not 15 since 15 is FizzBuzz)
        assert response.data["count"] == 4

    def test_count_all_classifications(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=15,
            raw_query="Count all below 16",
        )
        response = self.executor.execute(Intent.COUNT, entities)
        counts = response.data["counts"]
        assert counts["fizzbuzz"] == 1  # 15
        assert counts["fizz"] == 4     # 3, 6, 9, 12
        assert counts["buzz"] == 2     # 5, 10

    def test_list_fizzbuzz_below_30(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=30,
            classifications=["fizzbuzz"],
            raw_query="List FizzBuzz below 31",
        )
        response = self.executor.execute(Intent.LIST, entities)
        result_numbers = [r[0] for r in response.data["results"]]
        assert 15 in result_numbers
        assert 30 in result_numbers

    def test_list_prime_buzz(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=100,
            classifications=["buzz"],
            filters=["prime"],
            raw_query="Which primes are buzz?",
        )
        response = self.executor.execute(Intent.LIST, entities)
        result_numbers = [r[0] for r in response.data["results"]]
        assert 5 in result_numbers
        # 5 is the only prime that's Buzz (divisible by 5)

    def test_statistics_range(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=15,
            raw_query="Show statistics",
        )
        response = self.executor.execute(Intent.STATISTICS, entities)
        assert response.data["total"] == 15
        assert "most_common" in response.data

    def test_explain_15(self) -> None:
        entities = QueryEntities(numbers=[15], raw_query="Why is 15 FizzBuzz?")
        response = self.executor.execute(Intent.EXPLAIN, entities)
        assert response.data["number"] == 15
        assert response.data["classification"] == "fizzbuzz"
        assert response.data["divisibility"]["FizzRule"]["matches"] is True
        assert response.data["divisibility"]["BuzzRule"]["matches"] is True

    def test_explain_9(self) -> None:
        entities = QueryEntities(numbers=[9], raw_query="Why is 9 Fizz?")
        response = self.executor.execute(Intent.EXPLAIN, entities)
        assert response.data["classification"] == "fizz"
        # 9 % 3 == 0 (matches), 9 % 5 == 4 (no match)
        assert response.data["divisibility"]["FizzRule"]["remainder"] == 0
        assert response.data["divisibility"]["BuzzRule"]["remainder"] == 4

    def test_explain_no_numbers_raises(self) -> None:
        entities = QueryEntities(numbers=[], raw_query="Explain fizzbuzz")
        with pytest.raises(NLQEntityExtractionError):
            self.executor.execute(Intent.EXPLAIN, entities)

    def test_list_with_even_filter(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=20,
            filters=["even"],
            classifications=["fizz"],
            raw_query="List even fizz",
        )
        response = self.executor.execute(Intent.LIST, entities)
        result_numbers = [r[0] for r in response.data["results"]]
        # Even fizz in 1-20: 6, 12, 18
        assert 6 in result_numbers
        assert 12 in result_numbers
        assert 18 in result_numbers
        assert all(n % 2 == 0 for n in result_numbers)

    def test_list_empty_results(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=2,
            classifications=["fizzbuzz"],
            raw_query="FizzBuzz in 1-2",
        )
        response = self.executor.execute(Intent.LIST, entities)
        assert response.data["count"] == 0


# ============================================================
# NLQ Utility Function Tests
# ============================================================


class TestNLQUtilityFunctions:
    """Tests for NLQ helper functions."""

    def test_is_prime_basic(self) -> None:
        assert _is_prime(2) is True
        assert _is_prime(3) is True
        assert _is_prime(5) is True
        assert _is_prime(7) is True
        assert _is_prime(11) is True

    def test_is_prime_non_primes(self) -> None:
        assert _is_prime(0) is False
        assert _is_prime(1) is False
        assert _is_prime(4) is False
        assert _is_prime(9) is False
        assert _is_prime(15) is False

    def test_apply_filter_prime(self) -> None:
        result = _apply_number_filter([1, 2, 3, 4, 5, 6, 7], "prime")
        assert result == [2, 3, 5, 7]

    def test_apply_filter_even(self) -> None:
        result = _apply_number_filter([1, 2, 3, 4, 5], "even")
        assert result == [2, 4]

    def test_apply_filter_odd(self) -> None:
        result = _apply_number_filter([1, 2, 3, 4, 5], "odd")
        assert result == [1, 3, 5]

    def test_apply_filter_composite(self) -> None:
        result = _apply_number_filter([1, 2, 3, 4, 5, 6], "composite")
        assert result == [4, 6]

    def test_get_default_rules(self) -> None:
        rules = _get_default_rules()
        assert len(rules) == 2
        assert rules[0].get_definition().divisor == 3
        assert rules[1].get_definition().divisor == 5


# ============================================================
# NLQ Session Tests
# ============================================================


class TestNLQSession:
    """Tests for the NLQSession history tracking."""

    def test_session_starts_empty(self) -> None:
        session = NLQSession()
        assert session.query_count == 0
        assert session.history == []

    def test_add_entry_increments_count(self) -> None:
        session = NLQSession()
        response = QueryResponse(
            intent=Intent.EVALUATE, query="Is 15 FizzBuzz?",
            result_text="Yes", data={},
        )
        session.add_entry("Is 15 FizzBuzz?", Intent.EVALUATE, response)
        assert session.query_count == 1

    def test_intent_distribution_tracking(self) -> None:
        session = NLQSession()
        for _ in range(3):
            response = QueryResponse(
                intent=Intent.EVALUATE, query="test",
                result_text="test", data={},
            )
            session.add_entry("test", Intent.EVALUATE, response)

        dist = session.intent_distribution
        assert dist["EVALUATE"] == 3

    def test_max_history_enforcement(self) -> None:
        session = NLQSession(max_history=5)
        for i in range(10):
            response = QueryResponse(
                intent=Intent.EVALUATE, query=f"query {i}",
                result_text="test", data={},
            )
            session.add_entry(f"query {i}", Intent.EVALUATE, response)

        assert len(session.history) == 5
        # Should keep the most recent entries
        assert session.history[0].query == "query 5"

    def test_session_summary(self) -> None:
        session = NLQSession()
        response = QueryResponse(
            intent=Intent.EVALUATE, query="test",
            result_text="test", data={},
            execution_time_ms=1.5,
        )
        session.add_entry("test", Intent.EVALUATE, response)

        summary = session.get_session_summary()
        assert summary["total_queries"] == 1
        assert summary["total_execution_time_ms"] == 1.5
        assert "session_id" in summary

    def test_session_has_unique_id(self) -> None:
        s1 = NLQSession()
        s2 = NLQSession()
        assert s1.session_id != s2.session_id


# ============================================================
# NLQ Dashboard Tests
# ============================================================


class TestNLQDashboard:
    """Tests for the NLQ ASCII dashboard."""

    def test_dashboard_renders_without_error(self) -> None:
        session = NLQSession()
        output = NLQDashboard.render(session, width=60)
        assert "NATURAL LANGUAGE QUERY DASHBOARD" in output
        assert "No queries yet." in output

    def test_dashboard_shows_query_data(self) -> None:
        session = NLQSession()
        response = QueryResponse(
            intent=Intent.EVALUATE, query="Is 15 FizzBuzz?",
            result_text="Yes", data={},
        )
        session.add_entry("Is 15 FizzBuzz?", Intent.EVALUATE, response)

        output = NLQDashboard.render(session, width=60)
        assert "EVALUATE" in output
        assert "1" in output  # query count

    def test_dashboard_respects_width(self) -> None:
        session = NLQSession()
        output = NLQDashboard.render(session, width=50)
        for line in output.split("\n"):
            assert len(line) <= 50


# ============================================================
# NLQ Engine Integration Tests
# ============================================================


class TestNLQEngine:
    """Integration tests for the full NLQ pipeline."""

    def setup_method(self) -> None:
        self.engine = NLQEngine()

    def test_evaluate_15(self) -> None:
        response = self.engine.process_query("Is 15 FizzBuzz?")
        assert response.intent == Intent.EVALUATE
        assert response.data["classification"] == "fizzbuzz"

    def test_evaluate_7(self) -> None:
        response = self.engine.process_query("What is 7?")
        assert response.intent == Intent.EVALUATE
        assert response.data["classification"] == "plain"

    def test_count_fizz(self) -> None:
        response = self.engine.process_query("How many fizz below 16?")
        assert response.intent == Intent.COUNT

    def test_list_primes_buzz(self) -> None:
        response = self.engine.process_query("Which primes are buzz?")
        assert response.intent == Intent.LIST
        result_numbers = [r[0] for r in response.data["results"]]
        assert 5 in result_numbers

    def test_statistics(self) -> None:
        response = self.engine.process_query("What is the most common classification?")
        assert response.intent == Intent.STATISTICS
        assert "most_common" in response.data

    def test_explain_9(self) -> None:
        response = self.engine.process_query("Why is 9 Fizz?")
        assert response.intent == Intent.EXPLAIN
        assert response.data["number"] == 9

    def test_explain_15(self) -> None:
        response = self.engine.process_query("Explain 15")
        assert response.intent == Intent.EXPLAIN
        assert response.data["classification"] == "fizzbuzz"

    def test_session_tracking(self) -> None:
        self.engine.process_query("Is 15 FizzBuzz?")
        self.engine.process_query("What is 7?")
        assert self.engine.session.query_count == 2

    def test_query_too_long_raises(self) -> None:
        engine = NLQEngine(max_query_length=10)
        with pytest.raises(NLQTokenizationError):
            engine.process_query("Is 15 FizzBuzz and also more words?")

    def test_event_callback_fires(self) -> None:
        events: list[str] = []
        engine = NLQEngine(event_callback=lambda e: events.append(e.event_type.name))
        engine.process_query("Is 15 FizzBuzz?")
        assert "NLQ_QUERY_RECEIVED" in events
        assert "NLQ_TOKENIZATION_COMPLETED" in events
        assert "NLQ_INTENT_CLASSIFIED" in events
        assert "NLQ_ENTITIES_EXTRACTED" in events
        assert "NLQ_QUERY_EXECUTED" in events

    def test_execution_time_tracked(self) -> None:
        response = self.engine.process_query("Is 3 Fizz?")
        assert response.execution_time_ms >= 0

    def test_response_has_query_id(self) -> None:
        response = self.engine.process_query("Is 3 Fizz?")
        assert response.query_id is not None
        assert len(response.query_id) > 0


# ============================================================
# NLQ Exception Tests
# ============================================================


class TestNLQExceptions:
    """Tests for the NLQ exception hierarchy."""

    def test_nlq_tokenization_error_has_code(self) -> None:
        err = NLQTokenizationError("test query", "bad regex")
        assert "EFP-NLQ1" in str(err)

    def test_nlq_intent_error_has_code(self) -> None:
        err = NLQIntentClassificationError("test", ["a", "b"])
        assert "EFP-NLQ2" in str(err)

    def test_nlq_entity_error_has_code(self) -> None:
        err = NLQEntityExtractionError("test", "EVALUATE")
        assert "EFP-NLQ3" in str(err)

    def test_nlq_execution_error_has_code(self) -> None:
        err = NLQExecutionError("test", "EVALUATE", "boom")
        assert "EFP-NLQ4" in str(err)

    def test_nlq_unsupported_error_has_code(self) -> None:
        err = NLQUnsupportedQueryError("test", "not implemented")
        assert "EFP-NLQ5" in str(err)


# ============================================================
# NLQ EventType Tests
# ============================================================


class TestNLQEventTypes:
    """Tests for NLQ event types in the domain model."""

    def test_nlq_event_types_exist(self) -> None:
        assert EventType.NLQ_QUERY_RECEIVED is not None
        assert EventType.NLQ_TOKENIZATION_COMPLETED is not None
        assert EventType.NLQ_INTENT_CLASSIFIED is not None
        assert EventType.NLQ_ENTITIES_EXTRACTED is not None
        assert EventType.NLQ_QUERY_EXECUTED is not None
        assert EventType.NLQ_SESSION_STARTED is not None
