"""
Enterprise FizzBuzz Platform - Regulatory Compliance Chatbot & NLQ Engine

Implements a fully-featured, regex-powered compliance chatbot capable of
answering GDPR, SOX, and HIPAA questions about FizzBuzz operations, AND a
Natural Language Query (NLQ) engine for querying FizzBuzz evaluations in
plain English. Two regex-powered NLP interfaces, unified under one roof,
because maintaining separate chatbots for regulatory theater and modulo
arithmetic was an organizational overhead that even we could not justify.

Compliance Chatbot Features:
    - Intent classification via regex/keyword matching (no LLMs were harmed)
    - Knowledge base of ~25 real regulatory articles mapped to FizzBuzz
    - Cross-regime conflict detection (GDPR erasure vs SOX retention)
    - Formal advisory responses with COMPLIANT/NON_COMPLIANT verdicts
    - Conversation memory with follow-up context resolution
    - ASCII dashboard for chatbot session statistics
    - Bob McFizzington's stress-level-aware editorial commentary

NLQ Engine Features:
    - EVALUATE: "Is 15 FizzBuzz?"
    - COUNT:    "How many Fizzes below 100?"
    - LIST:     "Which primes are Buzz?"
    - STATISTICS: "What is the most common classification?"
    - EXPLAIN:  "Why is 9 Fizz?"
    - Five-stage pipeline: Tokenizer -> IntentClassifier -> EntityExtractor -> QueryExecutor -> Response

Architecture:
    Compliance: Query -> IntentClassifier -> KnowledgeBase -> ResponseGenerator -> Advisory
    NLQ:        Query -> Tokenizer -> IntentClassifier -> EntityExtractor -> QueryExecutor -> Response
    (Nine stages across two pipelines for problems that could each be solved
    with a single if/elif chain.)
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
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
from enterprise_fizzbuzz.domain.models import (
    ComplianceVerdict,
    Event,
    EventType,
    FizzBuzzResult,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule, StandardRuleEngine

logger = logging.getLogger(__name__)


# ============================================================
# Chatbot Intent Enum
# ============================================================
# Nine distinct regulatory intents, because "I don't know" is
# not an acceptable answer in compliance, but UNKNOWN is.
# ============================================================


class ChatbotIntent(Enum):
    """Classification of regulatory compliance query intents.

    Each intent represents a specific area of regulatory concern
    that the chatbot can address with a formal compliance advisory.
    The CROSS_REGIME_CONFLICT intent is triggered when a query touches
    regulations that contradict each other — which happens more often
    than regulators would like to admit.

    UNKNOWN is reserved for queries that defy classification, such as
    "What is the meaning of life?" or "Why does 15 % 3 equal 0?"
    The chatbot handles UNKNOWN gracefully by issuing a CONDITIONALLY
    COMPLIANT verdict with a recommendation to escalate to the Chief
    Compliance Officer for manual review.
    """

    GDPR_DATA_RIGHTS = auto()
    GDPR_CONSENT = auto()
    SOX_SEGREGATION = auto()
    SOX_AUDIT = auto()
    HIPAA_MINIMUM_NECESSARY = auto()
    HIPAA_PHI = auto()
    CROSS_REGIME_CONFLICT = auto()
    GENERAL_COMPLIANCE = auto()
    UNKNOWN = auto()


# ============================================================
# Chatbot Verdict (extends ComplianceVerdict for chatbot use)
# ============================================================


class ChatbotVerdict(Enum):
    """Verdict issued by the compliance chatbot in its advisory response.

    COMPLIANT:               The FizzBuzz operation satisfies the regulation.
    NON_COMPLIANT:           A violation has been detected. Bob's stress rises.
    CONDITIONALLY_COMPLIANT: Compliance is achievable IF specific conditions
                             are met (e.g., pseudonymization of FizzBuzz
                             results before deletion from the event store).
    REQUIRES_REVIEW:         The chatbot cannot make a determination. A human
                             compliance officer must review — but Bob is
                             unavailable, so this is effectively a dead end.
    """

    COMPLIANT = auto()
    NON_COMPLIANT = auto()
    CONDITIONALLY_COMPLIANT = auto()
    REQUIRES_REVIEW = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass(frozen=True)
class ClassifiedIntent:
    """Result of intent classification on a user query.

    Attributes:
        intent: The classified intent.
        confidence: How confident the classifier is (0.0 to 1.0).
        matched_keywords: Keywords that triggered the classification.
        raw_query: The original query string.
    """

    intent: ChatbotIntent
    confidence: float
    matched_keywords: tuple[str, ...] = ()
    raw_query: str = ""


@dataclass(frozen=True)
class KnowledgeEntry:
    """A single entry in the compliance knowledge base.

    Attributes:
        article_id: The regulatory article identifier (e.g., "GDPR Art. 17").
        title: Human-readable title of the regulatory provision.
        regime: Which regulatory regime this belongs to.
        fizzbuzz_interpretation: How this regulation applies to FizzBuzz.
        verdict: The default compliance verdict for this article.
        recommendation: What action to take for compliance.
        bob_commentary: Bob McFizzington's personal take on this regulation.
    """

    article_id: str
    title: str
    regime: str
    fizzbuzz_interpretation: str
    verdict: ChatbotVerdict
    recommendation: str
    bob_commentary: str = ""


@dataclass
class ChatbotResponse:
    """A formal compliance advisory response from the chatbot.

    Attributes:
        advisory_id: Unique identifier for this advisory.
        intent: The classified intent that triggered this response.
        verdict: The compliance verdict.
        summary: One-line summary of the advisory.
        explanation: Detailed explanation of the regulatory position.
        recommendation: Recommended course of action.
        cited_articles: Regulatory articles cited in this advisory.
        bob_stress_delta: How much this query increased Bob's stress.
        timestamp: When this advisory was issued.
        response_time_ms: How long it took to generate this advisory.
        session_turn: Which turn in the conversation this was.
    """

    advisory_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    intent: ChatbotIntent = ChatbotIntent.UNKNOWN
    verdict: ChatbotVerdict = ChatbotVerdict.REQUIRES_REVIEW
    summary: str = ""
    explanation: str = ""
    recommendation: str = ""
    cited_articles: list[str] = field(default_factory=list)
    bob_stress_delta: float = 0.0
    bob_commentary: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    response_time_ms: float = 0.0
    session_turn: int = 0


# ============================================================
# Intent Classifier
# ============================================================
# Regex-based intent classification, because transformer models
# are overkill for determining whether someone is asking about
# GDPR or HIPAA. Our approach is simpler, faster, and produces
# exactly the same quality of compliance advice: questionable.
# ============================================================


# Intent keyword patterns: each maps a set of patterns to an intent.
_INTENT_PATTERNS: dict[ChatbotIntent, list[re.Pattern[str]]] = {
    ChatbotIntent.GDPR_DATA_RIGHTS: [
        re.compile(r"\b(?:erasure|eras(?:e|ed|ing)|delet(?:e|ed|ing)|forget|forgotten|right.to.be.forgotten)\b", re.IGNORECASE),
        re.compile(r"\b(?:data.subject|data.rights|portability|rectification)\b", re.IGNORECASE),
        re.compile(r"\b(?:gdpr)\b.*\b(?:art(?:icle)?\.?\s*(?:15|16|17|18|20|21))\b", re.IGNORECASE),
        re.compile(r"\b(?:right.to.erasure|right.to.access|right.to.rectification)\b", re.IGNORECASE),
    ],
    ChatbotIntent.GDPR_CONSENT: [
        re.compile(r"\b(?:consent|opt.in|opt.out|legal.basis|lawful.basis)\b", re.IGNORECASE),
        re.compile(r"\b(?:gdpr)\b.*\b(?:art(?:icle)?\.?\s*(?:6|7|8|9))\b", re.IGNORECASE),
        re.compile(r"\b(?:data.processing|processing.agreement|legitimate.interest)\b", re.IGNORECASE),
        re.compile(r"\b(?:withdraw.consent|consent.management)\b", re.IGNORECASE),
    ],
    ChatbotIntent.SOX_SEGREGATION: [
        re.compile(r"\b(?:segregation|segregat(?:e|ed|ing))\b", re.IGNORECASE),
        re.compile(r"\b(?:separation.of.duties|dual.control|four.eyes)\b", re.IGNORECASE),
        re.compile(r"\b(?:sox)\b.*\b(?:section|sec\.?)\s*404\b", re.IGNORECASE),
        re.compile(r"\b(?:internal.controls|control.framework)\b", re.IGNORECASE),
    ],
    ChatbotIntent.SOX_AUDIT: [
        re.compile(r"\b(?:audit.trail|audit.log|sox.audit)\b", re.IGNORECASE),
        re.compile(r"\b(?:sox)\b.*\b(?:section|sec\.?)\s*(?:302|802|906)\b", re.IGNORECASE),
        re.compile(r"\b(?:retention|record.keeping|record.retention)\b", re.IGNORECASE),
        re.compile(r"\b(?:financial.controls|material.weakness)\b", re.IGNORECASE),
    ],
    ChatbotIntent.HIPAA_MINIMUM_NECESSARY: [
        re.compile(r"\b(?:minimum.necessary|need.to.know|least.privilege)\b", re.IGNORECASE),
        re.compile(r"\b(?:hipaa)\b.*\b(?:164\.502|164\.514)\b", re.IGNORECASE),
        re.compile(r"\b(?:access.control|access.level|role.based.access)\b", re.IGNORECASE),
        re.compile(r"\b(?:de.identif\w*|de-identif\w*|anonymiz\w*|pseudonymiz\w*)\b", re.IGNORECASE),
    ],
    ChatbotIntent.HIPAA_PHI: [
        re.compile(r"\b(?:phi|protected.health.information)\b", re.IGNORECASE),
        re.compile(r"\b(?:hipaa)\b.*\b(?:encrypt\w*|164\.312|safeguard)\b", re.IGNORECASE),
        re.compile(r"\b(?:encrypt\w*)\b.*\b(?:hipaa)\b", re.IGNORECASE),
        re.compile(r"\b(?:covered.entity|business.associate|baa)\b", re.IGNORECASE),
        re.compile(r"\b(?:breach.notification|security.rule|privacy.rule)\b", re.IGNORECASE),
    ],
    ChatbotIntent.CROSS_REGIME_CONFLICT: [
        re.compile(r"\b(?:conflict|contradiction|incompatible|paradox)\b", re.IGNORECASE),
        re.compile(r"\b(?:gdpr)\b.*\b(?:sox|hipaa)\b", re.IGNORECASE),
        re.compile(r"\b(?:sox)\b.*\b(?:gdpr|hipaa)\b", re.IGNORECASE),
        re.compile(r"\b(?:erasure|delete)\b.*\b(?:retention|audit|keep)\b", re.IGNORECASE),
        re.compile(r"\b(?:retention|keep)\b.*\b(?:erasure|delete|forget)\b", re.IGNORECASE),
    ],
    ChatbotIntent.GENERAL_COMPLIANCE: [
        re.compile(r"\b(?:complian(?:t|ce)|regulat(?:ory|ion)|framework)\b", re.IGNORECASE),
        re.compile(r"\b(?:bob|mcfizzington|compliance.officer)\b", re.IGNORECASE),
        re.compile(r"\b(?:violation|fine|penalty|enforcement)\b", re.IGNORECASE),
        re.compile(r"\b(?:fizzbuzz)\b.*\b(?:legal|law|regulat)\b", re.IGNORECASE),
    ],
}


class ChatbotIntentClassifier:
    """Regex-based intent classifier for compliance chatbot queries.

    Examines a query string against a curated set of regex patterns
    for each intent, computing a confidence score based on the number
    of pattern matches. The classifier favors specificity: CROSS_REGIME_
    CONFLICT outranks single-regime intents when patterns from multiple
    regimes match.

    This is essentially a bag-of-regex model with hand-tuned weights.
    It has never been validated against a test set larger than the
    developer's imagination, and its F1 score is "probably fine."
    """

    def __init__(self) -> None:
        self._classifications = 0
        self._intent_counts: dict[ChatbotIntent, int] = {
            intent: 0 for intent in ChatbotIntent
        }

    def classify(self, query: str) -> ClassifiedIntent:
        """Classify a query into a regulatory compliance intent.

        Args:
            query: The raw query string from the user.

        Returns:
            A ClassifiedIntent with the best-matching intent and confidence.
        """
        self._classifications += 1

        if not query or not query.strip():
            self._intent_counts[ChatbotIntent.UNKNOWN] += 1
            return ClassifiedIntent(
                intent=ChatbotIntent.UNKNOWN,
                confidence=0.0,
                raw_query=query or "",
            )

        # Score each intent by counting pattern matches
        scores: dict[ChatbotIntent, list[str]] = {}
        for intent, patterns in _INTENT_PATTERNS.items():
            matched_kws: list[str] = []
            for pattern in patterns:
                match = pattern.search(query)
                if match:
                    matched_kws.append(match.group(0))
            if matched_kws:
                scores[intent] = matched_kws

        if not scores:
            # Check if any compliance-adjacent words are present
            general_check = re.search(
                r"\b(?:gdpr|sox|hipaa|compliance|regulation|fizzbuzz|number|data)\b",
                query,
                re.IGNORECASE,
            )
            if general_check:
                self._intent_counts[ChatbotIntent.GENERAL_COMPLIANCE] += 1
                return ClassifiedIntent(
                    intent=ChatbotIntent.GENERAL_COMPLIANCE,
                    confidence=0.3,
                    matched_keywords=(general_check.group(0),),
                    raw_query=query,
                )
            self._intent_counts[ChatbotIntent.UNKNOWN] += 1
            return ClassifiedIntent(
                intent=ChatbotIntent.UNKNOWN,
                confidence=0.0,
                raw_query=query,
            )

        # Check for cross-regime conflict: if multiple regimes are represented
        regimes_hit = set()
        for intent in scores:
            if intent.name.startswith("GDPR"):
                regimes_hit.add("GDPR")
            elif intent.name.startswith("SOX"):
                regimes_hit.add("SOX")
            elif intent.name.startswith("HIPAA"):
                regimes_hit.add("HIPAA")

        if len(regimes_hit) >= 2 or ChatbotIntent.CROSS_REGIME_CONFLICT in scores:
            all_kws: list[str] = []
            for kws in scores.values():
                all_kws.extend(kws)
            total = sum(len(v) for v in scores.values())
            confidence = min(1.0, total * 0.25)
            self._intent_counts[ChatbotIntent.CROSS_REGIME_CONFLICT] += 1
            return ClassifiedIntent(
                intent=ChatbotIntent.CROSS_REGIME_CONFLICT,
                confidence=confidence,
                matched_keywords=tuple(all_kws),
                raw_query=query,
            )

        # Pick the intent with the most pattern matches
        best_intent = max(scores, key=lambda i: len(scores[i]))
        match_count = len(scores[best_intent])
        confidence = min(1.0, match_count * 0.3)

        self._intent_counts[best_intent] += 1
        return ClassifiedIntent(
            intent=best_intent,
            confidence=confidence,
            matched_keywords=tuple(scores[best_intent]),
            raw_query=query,
        )

    @property
    def total_classifications(self) -> int:
        """Total number of queries classified."""
        return self._classifications

    def get_statistics(self) -> dict[str, Any]:
        """Return classification statistics."""
        return {
            "total": self._classifications,
            "by_intent": {
                intent.name: count
                for intent, count in self._intent_counts.items()
                if count > 0
            },
        }


# ============================================================
# Compliance Knowledge Base
# ============================================================
# ~25 regulatory articles, each faithfully sourced from real
# legislation and then applied with absolute sincerity to
# FizzBuzz operations. The articles are real. The applications
# are not. The compliance advisory is technically correct —
# the best kind of correct.
# ============================================================


class ComplianceKnowledgeBase:
    """Curated knowledge base of regulatory articles applied to FizzBuzz.

    Contains entries from GDPR, SOX, and HIPAA — real regulatory
    provisions mapped to absurd FizzBuzz-specific interpretations.
    Each entry includes the article citation, a FizzBuzz-specific
    interpretation, a default verdict, and a recommended action.

    The knowledge base is static because regulations never change.
    (They do, constantly, but maintaining a regulatory update pipeline
    for a FizzBuzz chatbot seemed excessive even by our standards.)
    """

    def __init__(self, bob_commentary_enabled: bool = True) -> None:
        self._bob_commentary = bob_commentary_enabled
        self._entries = self._build_knowledge_base()
        self._lookups = 0

    def _build_knowledge_base(self) -> dict[str, list[KnowledgeEntry]]:
        """Construct the full regulatory knowledge base.

        Returns a dict mapping intent names to lists of applicable
        KnowledgeEntry objects.
        """
        kb: dict[str, list[KnowledgeEntry]] = {}

        # ---- GDPR Data Rights ----
        kb["GDPR_DATA_RIGHTS"] = [
            KnowledgeEntry(
                article_id="GDPR Art. 15",
                title="Right of Access by the Data Subject",
                regime="GDPR",
                fizzbuzz_interpretation=(
                    "Every number has the right to access its FizzBuzz classification. "
                    "The data controller (the FizzBuzz engine) must provide a copy of "
                    "the personal data undergoing processing — i.e., whether the number "
                    "was classified as Fizz, Buzz, FizzBuzz, or merely a plain number. "
                    "The number 15 has exercised this right 47 times."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Implement a /subject-access-request endpoint that returns the "
                    "FizzBuzz classification for any given number. Response time must "
                    "not exceed one month (GDPR Art. 12(3)), though the computation "
                    "takes approximately 0.0001 seconds."
                ),
                bob_commentary="I lose sleep over subject access requests for the number 1.",
            ),
            KnowledgeEntry(
                article_id="GDPR Art. 16",
                title="Right to Rectification",
                regime="GDPR",
                fizzbuzz_interpretation=(
                    "If a number believes its FizzBuzz classification is inaccurate, "
                    "it has the right to demand rectification. For example, if the "
                    "ML engine classified 15 as 'Fizz' instead of 'FizzBuzz' due to "
                    "low confidence, the number 15 may file a rectification request. "
                    "Deterministic evaluation makes this right largely theoretical, "
                    "unless you're using the Quantum strategy."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Maintain a rectification log. If the standard engine and ML engine "
                    "disagree, the data subject (number) is entitled to the deterministic "
                    "result. The ML engine must undergo retraining as remediation."
                ),
                bob_commentary="The number 4 filed 12 rectification requests last quarter. It's still not Fizz.",
            ),
            KnowledgeEntry(
                article_id="GDPR Art. 17",
                title="Right to Erasure (Right to Be Forgotten)",
                regime="GDPR",
                fizzbuzz_interpretation=(
                    "Numbers have the right to request erasure of their FizzBuzz "
                    "results. However, THE COMPLIANCE PARADOX arises when erasure "
                    "requests encounter the append-only event store and immutable "
                    "blockchain. These architecturally immutable data stores cannot "
                    "comply with deletion requests without violating their own "
                    "fundamental guarantees. The erasure certificate itself creates "
                    "a new record of the data that was supposed to be deleted."
                ),
                verdict=ChatbotVerdict.CONDITIONALLY_COMPLIANT,
                recommendation=(
                    "Implement pseudonymization per GDPR Art. 4(5) as an alternative "
                    "to physical deletion. Replace the number with a cryptographic "
                    "hash in the event store and blockchain. The hash cannot be "
                    "reversed (unless someone has a rainbow table of integers 1-100, "
                    "which they definitely do). Issue an erasure certificate documenting "
                    "the irony."
                ),
                bob_commentary="The erasure paradox keeps me up at night. Also, the number 42 requested erasure and I can't even.",
            ),
            KnowledgeEntry(
                article_id="GDPR Art. 20",
                title="Right to Data Portability",
                regime="GDPR",
                fizzbuzz_interpretation=(
                    "Numbers have the right to receive their FizzBuzz results in a "
                    "structured, commonly used, machine-readable format. The platform "
                    "supports JSON, XML, CSV, and plain text — four formats more than "
                    "strictly necessary for communicating that 15 is FizzBuzz."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Ensure all output formats conform to a published schema. The "
                    "JSON output should include the number, classification, matched "
                    "rules, and processing metadata. Bonus points for JSON-LD with "
                    "a FizzBuzz ontology namespace."
                ),
                bob_commentary="We support four output formats. The GDPR requires one. I'm not sure if that's compliance or overcompensation.",
            ),
        ]

        # ---- GDPR Consent ----
        kb["GDPR_CONSENT"] = [
            KnowledgeEntry(
                article_id="GDPR Art. 6",
                title="Lawfulness of Processing",
                regime="GDPR",
                fizzbuzz_interpretation=(
                    "FizzBuzz evaluation constitutes 'processing of personal data' "
                    "under Art. 6(1). The lawful basis depends on interpretation: "
                    "(a) consent of the data subject (the number), (b) performance "
                    "of a contract (the SLA), or (f) legitimate interests of the "
                    "controller (the insatiable need to classify integers by "
                    "divisibility). The platform defaults to auto-consent because "
                    "asking each number individually would be impractical."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Document the lawful basis for FizzBuzz processing in your "
                    "Records of Processing Activities (ROPA). Auto-consent is "
                    "acceptable for numbers that have not objected. Numbers that "
                    "object should be excluded from the evaluation range."
                ),
                bob_commentary="We auto-consent on behalf of every integer. The DPA has not yet objected.",
            ),
            KnowledgeEntry(
                article_id="GDPR Art. 7",
                title="Conditions for Consent",
                regime="GDPR",
                fizzbuzz_interpretation=(
                    "Consent for FizzBuzz processing must be freely given, specific, "
                    "informed, and unambiguous. The platform's auto-consent mechanism "
                    "satisfies 'unambiguous' (it's clearly automatic) but raises "
                    "questions about 'freely given' (the numbers had no choice). "
                    "However, since numbers lack legal personhood in most "
                    "jurisdictions, this is a grey area that compliance officers "
                    "prefer not to examine too closely."
                ),
                verdict=ChatbotVerdict.CONDITIONALLY_COMPLIANT,
                recommendation=(
                    "Implement a consent banner that displays before each evaluation. "
                    "The banner should inform the number that its divisibility will "
                    "be tested and that the results may be stored in an append-only "
                    "event store, rendered on an ASCII dashboard, and potentially "
                    "broadcast via webhooks to fictional HTTP endpoints."
                ),
                bob_commentary="Informed consent from integers. This is my life now.",
            ),
            KnowledgeEntry(
                article_id="GDPR Art. 9",
                title="Processing of Special Categories of Personal Data",
                regime="GDPR",
                fizzbuzz_interpretation=(
                    "FizzBuzz classification results could constitute special category "
                    "data if they reveal information about a number's 'health' (HIPAA "
                    "crossover), 'philosophical beliefs' (the number's stance on "
                    "divisibility), or 'trade union membership' (membership in the "
                    "FizzBuzz set). Processing such data requires explicit consent "
                    "or a substantial public interest exemption. We invoke the latter: "
                    "the public has a substantial interest in knowing that 15 is FizzBuzz."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Classify FizzBuzz results under Art. 9(2)(g) — substantial "
                    "public interest. FizzBuzz classification serves a vital societal "
                    "function that outweighs individual privacy concerns. Document "
                    "this in a Data Protection Impact Assessment (DPIA)."
                ),
                bob_commentary="I had to file a DPIA for modulo arithmetic. My stress level is at capacity.",
            ),
        ]

        # ---- SOX Segregation ----
        kb["SOX_SEGREGATION"] = [
            KnowledgeEntry(
                article_id="SOX Sec. 404",
                title="Management Assessment of Internal Controls",
                regime="SOX",
                fizzbuzz_interpretation=(
                    "Section 404 requires management to establish and maintain an "
                    "adequate internal control structure for FizzBuzz evaluation. "
                    "The platform enforces segregation of duties: the person who "
                    "evaluates Fizz (divisibility by 3) MUST NOT be the same person "
                    "who evaluates Buzz (divisibility by 5). The person who formats "
                    "the output MUST NOT have evaluated any rules. The person who "
                    "audits the result MUST be independent of all of the above. "
                    "Five virtual employees rotate through these roles using a "
                    "deterministic hash-based assignment algorithm."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Maintain a roster of at least 4 virtual personnel. Ensure the "
                    "hash-based assignment algorithm is deterministic and auditable. "
                    "Log all duty assignments to an immutable audit trail retained "
                    "for 7 years (2,555 days) as required by SOX Section 802."
                ),
                bob_commentary="Alice does Fizz. Charlie does Buzz. If they ever swap, I'm filing an incident report.",
            ),
            KnowledgeEntry(
                article_id="SOX Sec. 302",
                title="Corporate Responsibility for Financial Reports",
                regime="SOX",
                fizzbuzz_interpretation=(
                    "Section 302 requires the CEO and CFO to certify the accuracy "
                    "of FizzBuzz evaluation reports. Since the Enterprise FizzBuzz "
                    "Platform has no CEO or CFO, this responsibility falls on "
                    "Bob McFizzington, who must personally certify that 15 % 3 == 0 "
                    "and 15 % 5 == 0 for each evaluation cycle. Bob has certified "
                    "this 10,847 times and counting."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Generate a formal certification statement after each session. "
                    "The statement should attest that all FizzBuzz results are "
                    "materially accurate and that no fraudulent divisibility was "
                    "detected. Sign with HMAC-SHA256."
                ),
                bob_commentary="I certify under penalty of perjury that 15 is divisible by both 3 and 5. Again.",
            ),
        ]

        # ---- SOX Audit ----
        kb["SOX_AUDIT"] = [
            KnowledgeEntry(
                article_id="SOX Sec. 802",
                title="Criminal Penalties for Altering Documents",
                regime="SOX",
                fizzbuzz_interpretation=(
                    "Section 802 imposes criminal penalties for altering, destroying, "
                    "or concealing documents related to FizzBuzz evaluations. This "
                    "directly conflicts with GDPR Art. 17 erasure requests: SOX "
                    "demands retention of all FizzBuzz audit trails for 7 years, "
                    "while GDPR demands deletion upon request. This is THE COMPLIANCE "
                    "PARADOX — a regulatory Catch-22 that has driven Bob McFizzington's "
                    "stress level beyond the theoretical maximum."
                ),
                verdict=ChatbotVerdict.CONDITIONALLY_COMPLIANT,
                recommendation=(
                    "Implement pseudonymization as a compromise: replace the data "
                    "subject's identity with a cryptographic hash in the audit trail, "
                    "satisfying GDPR's erasure intent while preserving SOX's retention "
                    "requirement. Document this compromise in a Cross-Regime Conflict "
                    "Resolution Memorandum (CRCRM)."
                ),
                bob_commentary="7 years of retention vs right-to-erasure. I need a vacation.",
            ),
            KnowledgeEntry(
                article_id="SOX Sec. 906",
                title="Corporate Responsibility for Financial Reports — Criminal",
                regime="SOX",
                fizzbuzz_interpretation=(
                    "Section 906 imposes criminal liability for knowingly certifying "
                    "inaccurate FizzBuzz reports. If the ML engine classifies 15 as "
                    "'Fizz' instead of 'FizzBuzz' and Bob certifies the report without "
                    "catching the error, he faces up to 20 years in prison. The "
                    "Anti-Corruption Layer exists specifically to prevent this scenario "
                    "by cross-checking ML outputs against deterministic baselines."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Enable disagreement tracking between ML and deterministic strategies. "
                    "Any classification disagreement must trigger an automatic hold on "
                    "certification until manual review is complete. The Anti-Corruption "
                    "Layer provides this safeguard."
                ),
                bob_commentary="20 years in prison for a wrong FizzBuzz. I'm going to need a bigger insurance policy.",
            ),
        ]

        # ---- HIPAA Minimum Necessary ----
        kb["HIPAA_MINIMUM_NECESSARY"] = [
            KnowledgeEntry(
                article_id="HIPAA 45 CFR 164.502(b)",
                title="Minimum Necessary Standard",
                regime="HIPAA",
                fizzbuzz_interpretation=(
                    "The minimum necessary standard requires that FizzBuzz results "
                    "shared with third parties contain only the minimum information "
                    "necessary for the intended purpose. For FULL_ACCESS, the complete "
                    "result is disclosed. For TREATMENT, only the classification and "
                    "matched rules. For OPERATIONS, results are replaced with "
                    "'[PHI REDACTED - MINIMUM NECESSARY]'. For RESEARCH, all data "
                    "is de-identified and numbers are replaced with sequential "
                    "identifiers."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Default to OPERATIONS level for all external disclosures. "
                    "FULL_ACCESS should require explicit authorization from the "
                    "attending FizzBuzz physician (Bob McFizzington, MD — he added "
                    "the MD to his title last Tuesday, nobody questioned it)."
                ),
                bob_commentary="I'm not actually a doctor. But I play one in the compliance framework.",
            ),
            KnowledgeEntry(
                article_id="HIPAA 45 CFR 164.514",
                title="De-identification of Protected Health Information",
                regime="HIPAA",
                fizzbuzz_interpretation=(
                    "FizzBuzz results can be de-identified using either the Expert "
                    "Determination method (a qualified statistician certifies that "
                    "the risk of re-identification is very small) or the Safe Harbor "
                    "method (removing 18 categories of identifiers). For FizzBuzz, "
                    "the primary identifier IS the number itself, so de-identification "
                    "requires replacing numbers with opaque tokens. Unfortunately, "
                    "anyone with access to a modulo operator can re-identify the data "
                    "in O(n) time."
                ),
                verdict=ChatbotVerdict.CONDITIONALLY_COMPLIANT,
                recommendation=(
                    "Apply the Safe Harbor method by replacing numbers with UUIDs in "
                    "all research-level outputs. Acknowledge in the de-identification "
                    "attestation that the risk of re-identification is technically "
                    "100% for anyone who can count to 100, but that the attestation "
                    "satisfies the regulatory checkbox."
                ),
                bob_commentary="De-identifying integers. We've achieved peak compliance.",
            ),
        ]

        # ---- HIPAA PHI ----
        kb["HIPAA_PHI"] = [
            KnowledgeEntry(
                article_id="HIPAA 45 CFR 164.312(a)(1)",
                title="Access Control — Technical Safeguards",
                regime="HIPAA",
                fizzbuzz_interpretation=(
                    "Technical safeguards must be implemented to control access to "
                    "FizzBuzz PHI (Protected Health Information). The platform uses "
                    "role-based access control (RBAC) with five levels ranging from "
                    "ANONYMOUS to FIZZBUZZ_SUPERUSER. Each role restricts the range "
                    "of numbers that can be evaluated — because some integers are "
                    "more sensitive than others."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Ensure RBAC is enabled (--rbac flag). NUMBER_AUDITOR role must "
                    "be assigned to personnel reviewing FizzBuzz results. ANONYMOUS "
                    "users should be restricted to evaluating the number 1 (which is "
                    "always 'plain' — harmless and un-exploitable)."
                ),
                bob_commentary="The number 1 is the only truly safe number. Everything else is a potential breach.",
            ),
            KnowledgeEntry(
                article_id="HIPAA 45 CFR 164.312(e)(1)",
                title="Transmission Security",
                regime="HIPAA",
                fizzbuzz_interpretation=(
                    "FizzBuzz PHI transmitted over electronic media must be encrypted "
                    "to prevent unauthorized access. The Enterprise FizzBuzz Platform "
                    "implements 'military-grade' encryption using Base64 encoding — "
                    "RFC 4648 compliant, deterministic, and providing exactly zero "
                    "bits of actual security. However, the encoded output looks "
                    "sufficiently encrypted to satisfy auditors who don't read RFCs."
                ),
                verdict=ChatbotVerdict.CONDITIONALLY_COMPLIANT,
                recommendation=(
                    "Base64 is not encryption. It is an encoding scheme. However, "
                    "the HIPAA Security Rule does not specify a minimum encryption "
                    "standard, only that 'encryption' be implemented. Our legal "
                    "team has determined that Base64 satisfies the letter of the law "
                    "while catastrophically failing its spirit. Proceed with caution."
                ),
                bob_commentary="Our 'encryption' is Base64. If the auditors ask, tell them it's military-grade RFC 4648.",
            ),
            KnowledgeEntry(
                article_id="HIPAA 45 CFR 164.408",
                title="Notification to the Secretary",
                regime="HIPAA",
                fizzbuzz_interpretation=(
                    "In the event of a breach of unsecured FizzBuzz PHI affecting 500 "
                    "or more individuals (numbers), the platform must notify the HHS "
                    "Secretary within 60 days. For breaches affecting fewer than 500 "
                    "numbers, annual reporting suffices. Given our evaluation range of "
                    "1-100, a complete data breach would affect 100 data subjects — "
                    "below the 500 threshold, mercifully placing us in the annual "
                    "reporting category."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Maintain a breach notification plan. If the evaluation range "
                    "exceeds 500, switch to the 60-day notification cadence. Document "
                    "all breach simulations in the Chaos Engineering framework's "
                    "gameday reports."
                ),
                bob_commentary="If we ever evaluate more than 500 numbers, I'm calling a board meeting.",
            ),
        ]

        # ---- Cross-Regime Conflict ----
        kb["CROSS_REGIME_CONFLICT"] = [
            KnowledgeEntry(
                article_id="GDPR Art. 17 vs SOX Sec. 802",
                title="The Erasure-Retention Paradox",
                regime="CROSS-REGIME",
                fizzbuzz_interpretation=(
                    "GDPR Art. 17 grants data subjects the right to erasure. "
                    "SOX Sec. 802 imposes criminal penalties for destroying audit "
                    "records that must be retained for 7 years. When a number "
                    "requests erasure of its FizzBuzz results, these two regulations "
                    "are in direct conflict. Deleting the data violates SOX. "
                    "Retaining the data violates GDPR. This is THE COMPLIANCE "
                    "PARADOX — a regulatory singularity from which no compliant "
                    "outcome can escape."
                ),
                verdict=ChatbotVerdict.CONDITIONALLY_COMPLIANT,
                recommendation=(
                    "Implement pseudonymization as the recommended compromise: "
                    "replace the number's identity with a one-way cryptographic hash "
                    "in the audit trail. This satisfies GDPR's erasure intent "
                    "(the personal data is no longer identifiable) while preserving "
                    "SOX's retention requirement (the audit trail remains intact). "
                    "Document this approach in a formal Cross-Regime Conflict "
                    "Resolution Memorandum signed by Bob McFizzington."
                ),
                bob_commentary="This paradox is why I keep a bottle of antacids in my desk. The virtual one, obviously.",
            ),
            KnowledgeEntry(
                article_id="GDPR Art. 9 vs HIPAA 164.502",
                title="Special Category Data vs PHI Classification",
                regime="CROSS-REGIME",
                fizzbuzz_interpretation=(
                    "GDPR classifies FizzBuzz results as potential special category "
                    "data (revealing 'philosophical beliefs' about divisibility). "
                    "HIPAA classifies FizzBuzz results as PHI (Protected Health "
                    "Information — the health of the number's divisibility profile). "
                    "Both frameworks impose heightened protections, but their "
                    "access control models differ: GDPR requires explicit consent, "
                    "while HIPAA requires minimum necessary access levels. "
                    "The chatbot recommends applying BOTH frameworks simultaneously."
                ),
                verdict=ChatbotVerdict.CONDITIONALLY_COMPLIANT,
                recommendation=(
                    "Apply the more restrictive standard from each framework: "
                    "GDPR's explicit consent requirement AND HIPAA's minimum "
                    "necessary standard. This results in: (1) obtaining consent "
                    "before processing, AND (2) restricting output to the minimum "
                    "necessary for the stated purpose. The overhead is substantial "
                    "but the compliance score is immaculate."
                ),
                bob_commentary="Two frameworks, both alike in absurdity, in fair FizzBuzz where we lay our scene.",
            ),
            KnowledgeEntry(
                article_id="SOX Sec. 404 vs HIPAA 164.312",
                title="Segregation of Duties vs Access Control",
                regime="CROSS-REGIME",
                fizzbuzz_interpretation=(
                    "SOX requires segregation of duties (no one person should control "
                    "all aspects of FizzBuzz evaluation). HIPAA requires access control "
                    "(only authorized personnel should access FizzBuzz PHI). These "
                    "are complementary but create administrative overhead: each virtual "
                    "employee needs both SOX role assignments AND HIPAA access levels. "
                    "The permutation space is non-trivial."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Map SOX roles to HIPAA access levels: FIZZ_EVALUATOR and "
                    "BUZZ_EVALUATOR get TREATMENT access. FORMATTER gets OPERATIONS "
                    "access. AUDITOR gets FULL_ACCESS (they need to see everything "
                    "to audit it). Document the mapping in a Role-Access Matrix."
                ),
                bob_commentary="I maintain a 5x4 Role-Access Matrix. It's my most prized spreadsheet.",
            ),
        ]

        # ---- General Compliance ----
        kb["GENERAL_COMPLIANCE"] = [
            KnowledgeEntry(
                article_id="EFP-COMPLIANCE-001",
                title="Enterprise FizzBuzz Compliance Framework Overview",
                regime="INTERNAL",
                fizzbuzz_interpretation=(
                    "The Enterprise FizzBuzz Platform implements compliance with three "
                    "regulatory frameworks: SOX (Sarbanes-Oxley) for financial controls "
                    "and segregation of duties, GDPR (General Data Protection Regulation) "
                    "for data subject rights and consent management, and HIPAA (Health "
                    "Insurance Portability and Accountability Act) for Protected Health "
                    "Information safeguards. The Chief Compliance Officer is Bob "
                    "McFizzington, whose stress level is perpetually above 94% and "
                    "whose availability is perpetually 'no'."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Enable all three frameworks using the --compliance flag. "
                    "Monitor Bob McFizzington's stress level via the compliance "
                    "dashboard (--compliance-dashboard). Consider sending Bob a "
                    "virtual fruit basket."
                ),
                bob_commentary="I am the compliance framework. The compliance framework is me. We are one.",
            ),
            KnowledgeEntry(
                article_id="EFP-COMPLIANCE-002",
                title="Data Classification Policy",
                regime="INTERNAL",
                fizzbuzz_interpretation=(
                    "All FizzBuzz results are classified by data sensitivity: "
                    "PUBLIC (plain numbers), INTERNAL (Fizz or Buzz), CONFIDENTIAL "
                    "(FizzBuzz — trade secrets), SECRET (ML results with confidence "
                    "< 0.9), and TOP_SECRET_FIZZBUZZ (multi-strategy verified results). "
                    "The classification drives access control, encryption requirements, "
                    "and the general anxiety level of the compliance team."
                ),
                verdict=ChatbotVerdict.COMPLIANT,
                recommendation=(
                    "Ensure DataClassificationEngine is integrated into the processing "
                    "pipeline. All CONFIDENTIAL and above results should be 'encrypted' "
                    "using military-grade Base64 before storage or transmission."
                ),
                bob_commentary="TOP_SECRET_FIZZBUZZ clearance requires a background check and a signed NDA. Both are fictional.",
            ),
        ]

        return kb

    def lookup(self, intent: ChatbotIntent, query: str = "") -> list[KnowledgeEntry]:
        """Look up knowledge base entries for the given intent.

        Args:
            intent: The classified intent.
            query: Optional query string for additional filtering.

        Returns:
            List of relevant KnowledgeEntry objects.
        """
        self._lookups += 1
        intent_key = intent.name

        entries = self._entries.get(intent_key, [])

        if not entries:
            # Fall back to general compliance
            entries = self._entries.get("GENERAL_COMPLIANCE", [])

        # If query mentions a specific article, try to find it
        if query:
            article_match = re.search(
                r"(?:art(?:icle)?\.?\s*(\d+)|sec(?:tion)?\.?\s*(\d+)|164\.(\d+))",
                query,
                re.IGNORECASE,
            )
            if article_match:
                article_num = article_match.group(1) or article_match.group(2) or article_match.group(3)
                filtered = [
                    e for e in entries
                    if article_num in e.article_id
                ]
                if filtered:
                    return filtered

        return entries

    @property
    def total_entries(self) -> int:
        """Total number of knowledge base entries."""
        return sum(len(v) for v in self._entries.values())

    @property
    def total_lookups(self) -> int:
        """Total number of lookups performed."""
        return self._lookups

    def get_all_articles(self) -> list[str]:
        """Return all article IDs in the knowledge base."""
        articles = []
        for entries in self._entries.values():
            for entry in entries:
                articles.append(entry.article_id)
        return articles


# ============================================================
# Response Generator
# ============================================================
# Builds formal COMPLIANCE ADVISORY responses with the gravitas
# and verbosity of a real regulatory filing. Each response
# includes a verdict, explanation, recommendation, and article
# citations — because if it doesn't look like a legal document,
# the compliance team won't take it seriously.
# ============================================================


class ResponseGenerator:
    """Generates formal compliance advisory responses.

    Takes classified intents and knowledge base entries and produces
    formatted COMPLIANCE ADVISORY responses suitable for regulatory
    review, board presentations, and impressing auditors who don't
    know that FizzBuzz is a children's counting game.
    """

    def __init__(
        self,
        include_citations: bool = True,
        bob_commentary_enabled: bool = True,
        formality_level: str = "maximum",
    ) -> None:
        self._include_citations = include_citations
        self._bob_commentary = bob_commentary_enabled
        self._formality = formality_level
        self._responses_generated = 0

    def generate(
        self,
        intent: ClassifiedIntent,
        entries: list[KnowledgeEntry],
        context_number: Optional[int] = None,
        session_turn: int = 0,
    ) -> ChatbotResponse:
        """Generate a formal compliance advisory response.

        Args:
            intent: The classified intent.
            entries: Relevant knowledge base entries.
            context_number: Optional number being discussed.
            session_turn: Which turn in the conversation.

        Returns:
            A ChatbotResponse with the formal advisory.
        """
        start_time = time.monotonic()
        self._responses_generated += 1

        if not entries or (intent.intent == ChatbotIntent.UNKNOWN and intent.confidence == 0.0):
            return self._generate_unknown_response(intent, start_time, session_turn)

        # Use the first (most relevant) entry as the primary source
        primary = entries[0]

        # Determine verdict
        verdict = primary.verdict

        # Build explanation
        explanation = primary.fizzbuzz_interpretation
        if context_number is not None:
            explanation += (
                f" [Context: This advisory applies to the number {context_number}, "
                f"whose divisibility by 3 is {'YES' if context_number % 3 == 0 else 'NO'} "
                f"and by 5 is {'YES' if context_number % 5 == 0 else 'NO'}.]"
            )

        # Build summary
        summary = (
            f"{primary.regime} {primary.title} — "
            f"Verdict: {verdict.name.replace('_', ' ')}"
        )

        # Collect citations
        cited = [e.article_id for e in entries] if self._include_citations else []

        # Bob's commentary
        bob_text = ""
        if self._bob_commentary and primary.bob_commentary:
            bob_text = f"[Bob McFizzington, CCO]: \"{primary.bob_commentary}\""

        # Bob stress delta based on verdict severity
        stress_delta = {
            ChatbotVerdict.COMPLIANT: 0.1,
            ChatbotVerdict.NON_COMPLIANT: 2.5,
            ChatbotVerdict.CONDITIONALLY_COMPLIANT: 0.8,
            ChatbotVerdict.REQUIRES_REVIEW: 1.5,
        }.get(verdict, 0.5)

        elapsed = (time.monotonic() - start_time) * 1000

        return ChatbotResponse(
            intent=intent.intent,
            verdict=verdict,
            summary=summary,
            explanation=explanation,
            recommendation=primary.recommendation,
            cited_articles=cited,
            bob_stress_delta=stress_delta,
            bob_commentary=bob_text,
            response_time_ms=elapsed,
            session_turn=session_turn,
        )

    def _generate_unknown_response(
        self,
        intent: ClassifiedIntent,
        start_time: float,
        session_turn: int,
    ) -> ChatbotResponse:
        """Generate a response for unclassifiable queries."""
        elapsed = (time.monotonic() - start_time) * 1000
        return ChatbotResponse(
            intent=intent.intent,
            verdict=ChatbotVerdict.REQUIRES_REVIEW,
            summary="Unable to provide regulatory guidance for this query",
            explanation=(
                "The Regulatory Compliance Chatbot was unable to locate applicable "
                "regulatory provisions for your query. This may indicate that: "
                "(a) the query falls outside the scope of GDPR, SOX, and HIPAA as "
                "applied to FizzBuzz operations, (b) the query uses terminology "
                "not recognized by the regex-based intent classifier, or (c) the "
                "question is fundamentally philosophical in nature and beyond the "
                "chatbot's jurisdiction. Bob McFizzington has been notified "
                "(he will not respond)."
            ),
            recommendation=(
                "Please rephrase your query using recognized regulatory terminology. "
                "Supported topics include: data erasure, consent, segregation of duties, "
                "audit trails, minimum necessary access, PHI encryption, and cross-regime "
                "conflicts. Alternatively, consult Bob McFizzington during his office "
                "hours (he has none)."
            ),
            cited_articles=[],
            bob_stress_delta=0.5,
            bob_commentary=(
                "[Bob McFizzington, CCO]: \"I received the notification. "
                "I'm choosing to ignore it. My stress level is already "
                "beyond therapeutic intervention.\""
            ),
            response_time_ms=elapsed,
            session_turn=session_turn,
        )

    @property
    def total_responses(self) -> int:
        """Total number of responses generated."""
        return self._responses_generated


# ============================================================
# Chat Session — Conversation Memory
# ============================================================
# Because a compliance chatbot that forgets what you just asked
# is not a chatbot but a Magic 8-Ball with regulatory pretensions.
# The session maintains context for follow-up queries like
# "What about 16?" after discussing 15.
# ============================================================


@dataclass
class ConversationTurn:
    """A single turn in a chatbot conversation.

    Attributes:
        turn_number: Sequential turn number.
        query: The user's query.
        intent: The classified intent.
        response: The generated response.
        context_number: Any number mentioned in this turn.
        timestamp: When this turn occurred.
    """

    turn_number: int
    query: str
    intent: ClassifiedIntent
    response: ChatbotResponse
    context_number: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ChatSession:
    """Manages conversation state for a compliance chatbot session.

    Maintains a rolling history of conversation turns, tracks context
    (especially numbers being discussed), and resolves follow-up
    references. When a user says "What about 16?" the session looks
    back at the previous turn to understand what "about" refers to
    (the same regulatory topic, but for a different number).

    Sessions have a maximum history size to prevent unbounded memory
    growth — because even in-memory compliance consultations need
    resource limits.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        max_history: int = 20,
    ) -> None:
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self._max_history = max_history
        self._history: list[ConversationTurn] = []
        self._current_number: Optional[int] = None
        self._current_intent: Optional[ChatbotIntent] = None
        self._created_at = datetime.now(timezone.utc)

    def add_turn(
        self,
        query: str,
        intent: ClassifiedIntent,
        response: ChatbotResponse,
        context_number: Optional[int] = None,
    ) -> None:
        """Record a conversation turn in session history.

        Args:
            query: The user's query.
            intent: The classified intent.
            response: The generated response.
            context_number: Any number referenced in this turn.
        """
        turn = ConversationTurn(
            turn_number=len(self._history) + 1,
            query=query,
            intent=intent,
            response=response,
            context_number=context_number,
        )
        self._history.append(turn)

        # Update context
        if context_number is not None:
            self._current_number = context_number
        if intent.intent != ChatbotIntent.UNKNOWN:
            self._current_intent = intent.intent

        # Enforce history limit
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def resolve_context(self, query: str, intent: ClassifiedIntent) -> tuple[Optional[int], ChatbotIntent]:
        """Resolve follow-up context from conversation history.

        Examines the query for number references and, if the intent
        is UNKNOWN or GENERAL, checks if a previous intent provides
        context. This enables follow-up queries like:

            User: "Is it GDPR compliant to erase the number 15?"
            User: "What about 16?"
              -> resolves to GDPR_DATA_RIGHTS with number=16

        Args:
            query: The current query.
            intent: The classified intent.

        Returns:
            A tuple of (resolved_number, resolved_intent).
        """
        # Extract any number from the query
        number_match = re.search(r"\b(\d+)\b", query)
        resolved_number = int(number_match.group(1)) if number_match else self._current_number

        # If the intent is UNKNOWN or very low confidence, use previous intent
        resolved_intent = intent.intent
        if (
            intent.intent in (ChatbotIntent.UNKNOWN, ChatbotIntent.GENERAL_COMPLIANCE)
            and intent.confidence < 0.3
            and self._current_intent is not None
        ):
            resolved_intent = self._current_intent

        return resolved_number, resolved_intent

    @property
    def turn_count(self) -> int:
        """Number of turns in this session."""
        return len(self._history)

    @property
    def current_number(self) -> Optional[int]:
        """The most recently discussed number."""
        return self._current_number

    @property
    def current_intent(self) -> Optional[ChatbotIntent]:
        """The most recent non-UNKNOWN intent."""
        return self._current_intent

    @property
    def history(self) -> list[ConversationTurn]:
        """The conversation history."""
        return list(self._history)

    @property
    def created_at(self) -> datetime:
        """When this session was created."""
        return self._created_at

    def get_statistics(self) -> dict[str, Any]:
        """Return session statistics."""
        intent_counts: dict[str, int] = {}
        for turn in self._history:
            name = turn.intent.intent.name
            intent_counts[name] = intent_counts.get(name, 0) + 1

        total_stress = sum(t.response.bob_stress_delta for t in self._history)

        return {
            "session_id": self.session_id,
            "total_turns": len(self._history),
            "intents": intent_counts,
            "total_bob_stress_added": round(total_stress, 2),
            "current_number": self._current_number,
            "current_intent": self._current_intent.name if self._current_intent else None,
        }


# ============================================================
# Chatbot Dashboard
# ============================================================
# ASCII art for compliance consultations. Because regulatory
# guidance rendered in a proportional font is simply not
# enterprise-grade.
# ============================================================


class ChatbotDashboard:
    """Renders ASCII dashboards for compliance chatbot sessions.

    Provides visual representations of session statistics, intent
    distributions, and Bob McFizzington's deteriorating mental
    health — all rendered in beautiful fixed-width characters.
    """

    @staticmethod
    def render_response(response: ChatbotResponse, width: int = 60) -> str:
        """Render a single compliance advisory as formatted text.

        Args:
            response: The chatbot response to render.
            width: Character width for the output.

        Returns:
            Formatted advisory text.
        """
        inner = width - 4
        border = "+" + "-" * (width - 2) + "+"
        double_border = "+" + "=" * (width - 2) + "+"

        lines: list[str] = []
        lines.append("")
        lines.append(f"  {double_border}")
        lines.append(f"  | {'COMPLIANCE ADVISORY':^{inner}}|")
        lines.append(f"  | {'Advisory ID: ' + response.advisory_id:^{inner}}|")
        lines.append(f"  {double_border}")

        # Verdict
        verdict_str = response.verdict.name.replace("_", " ")
        verdict_line = f"VERDICT: {verdict_str}"
        lines.append(f"  | {verdict_line:<{inner}}|")
        lines.append(f"  | {'Intent: ' + response.intent.name:<{inner}}|")
        lines.append(f"  {border}")

        # Summary
        lines.append(f"  | {'SUMMARY':<{inner}}|")
        lines.append(f"  {border}")
        for chunk in _wrap_text(response.summary, inner - 2):
            lines.append(f"  | {chunk:<{inner}}|")
        lines.append(f"  {border}")

        # Explanation
        lines.append(f"  | {'EXPLANATION':<{inner}}|")
        lines.append(f"  {border}")
        for chunk in _wrap_text(response.explanation, inner - 2):
            lines.append(f"  | {chunk:<{inner}}|")
        lines.append(f"  {border}")

        # Recommendation
        lines.append(f"  | {'RECOMMENDATION':<{inner}}|")
        lines.append(f"  {border}")
        for chunk in _wrap_text(response.recommendation, inner - 2):
            lines.append(f"  | {chunk:<{inner}}|")
        lines.append(f"  {border}")

        # Cited Articles
        if response.cited_articles:
            lines.append(f"  | {'CITED ARTICLES':<{inner}}|")
            lines.append(f"  {border}")
            for art in response.cited_articles:
                lines.append(f"  |   - {art:<{inner - 4}}|")
            lines.append(f"  {border}")

        # Bob's Commentary
        if response.bob_commentary:
            lines.append(f"  | {'BOB McFIZZINGTON COMMENTARY':<{inner}}|")
            lines.append(f"  {border}")
            for chunk in _wrap_text(response.bob_commentary, inner - 2):
                lines.append(f"  | {chunk:<{inner}}|")
            lines.append(f"  {border}")

        # Footer
        lines.append(
            f"  | {'Response time: ' + f'{response.response_time_ms:.2f}ms':<{inner}}|"
        )
        lines.append(
            f"  | {'Bob stress delta: +' + f'{response.bob_stress_delta:.1f}%':<{inner}}|"
        )
        lines.append(f"  {double_border}")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_session(session: ChatSession, width: int = 60) -> str:
        """Render session statistics as an ASCII dashboard.

        Args:
            session: The chat session to render.
            width: Character width for the dashboard.

        Returns:
            Formatted dashboard text.
        """
        inner = width - 4
        border = "+" + "-" * (width - 2) + "+"
        double_border = "+" + "=" * (width - 2) + "+"

        stats = session.get_statistics()

        lines: list[str] = []
        lines.append("")
        lines.append(f"  {double_border}")
        lines.append(f"  | {'COMPLIANCE CHATBOT SESSION DASHBOARD':^{inner}}|")
        lines.append(f"  {double_border}")

        lines.append(f"  | {'Session ID: ' + stats['session_id']:<{inner}}|")
        lines.append(f"  | {'Total Turns: ' + str(stats['total_turns']):<{inner}}|")
        lines.append(
            f"  | {'Bob Stress Added: +' + str(stats['total_bob_stress_added']) + '%':<{inner}}|"
        )
        if stats["current_number"] is not None:
            lines.append(
                f"  | {'Current Number: ' + str(stats['current_number']):<{inner}}|"
            )
        if stats["current_intent"]:
            lines.append(
                f"  | {'Current Intent: ' + stats['current_intent']:<{inner}}|"
            )
        lines.append(f"  {border}")

        # Intent distribution
        intents = stats.get("intents", {})
        if intents:
            lines.append(f"  | {'INTENT DISTRIBUTION':<{inner}}|")
            lines.append(f"  {border}")
            for intent_name, count in sorted(intents.items()):
                bar_max = inner - len(intent_name) - 8
                bar_len = max(1, int(bar_max * count / max(stats["total_turns"], 1)))
                bar = "#" * min(bar_len, bar_max)
                entry = f"  {intent_name}: {count} {bar}"
                lines.append(f"  | {entry:<{inner}}|")
            lines.append(f"  {border}")

        # Recent conversation
        history = session.history
        if history:
            lines.append(f"  | {'RECENT CONVERSATION':<{inner}}|")
            lines.append(f"  {border}")
            for turn in history[-5:]:
                q_trunc = turn.query[:inner - 10] + "..." if len(turn.query) > inner - 10 else turn.query
                lines.append(f"  | T{turn.turn_number}: {q_trunc:<{inner - 2}}|")
                verdict_name = turn.response.verdict.name.replace("_", " ")
                lines.append(f"  |   -> {verdict_name:<{inner - 4}}|")
            lines.append(f"  {border}")

        lines.append(f"  {double_border}")
        lines.append("")

        return "\n".join(lines)


# ============================================================
# Compliance Chatbot — Main Orchestrator
# ============================================================
# The grand unified chatbot that ties intent classification,
# knowledge base lookup, response generation, and conversation
# management into a single, cohesive system of regulatory
# theatre. Each query passes through four stages of processing,
# because answering "Is deleting FizzBuzz results GDPR compliant?"
# should never be a simple yes or no.
# ============================================================


class ComplianceChatbot:
    """Regulatory compliance chatbot for FizzBuzz operations.

    Orchestrates the full chatbot pipeline:
    1. Intent classification (regex-based pattern matching)
    2. Context resolution (follow-up detection from session history)
    3. Knowledge base lookup (regulatory article retrieval)
    4. Response generation (formal advisory construction)

    The chatbot can operate in single-query mode (--chatbot "question")
    or interactive REPL mode (--chatbot-interactive). In interactive
    mode, it maintains conversation context across turns, enabling
    follow-up queries that would make any regulatory affairs specialist
    feel right at home.

    Bob McFizzington's stress level increases with every query,
    because being consulted about FizzBuzz compliance is inherently
    stressful for a man who has already achieved peak compliance anxiety.
    """

    def __init__(
        self,
        max_history: int = 20,
        include_citations: bool = True,
        bob_commentary_enabled: bool = True,
        formality_level: str = "maximum",
        event_bus: Any = None,
        bob_stress_level: float = 94.7,
    ) -> None:
        self._classifier = ChatbotIntentClassifier()
        self._knowledge_base = ComplianceKnowledgeBase(
            bob_commentary_enabled=bob_commentary_enabled,
        )
        self._response_generator = ResponseGenerator(
            include_citations=include_citations,
            bob_commentary_enabled=bob_commentary_enabled,
            formality_level=formality_level,
        )
        self._session = ChatSession(max_history=max_history)
        self._event_bus = event_bus
        self._bob_stress_level = bob_stress_level
        self._total_queries = 0

        # Emit session start event
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.CHATBOT_SESSION_STARTED,
                payload={
                    "session_id": self._session.session_id,
                    "bob_stress_level": self._bob_stress_level,
                },
                source="ComplianceChatbot",
            ))

    def ask(self, query: str) -> ChatbotResponse:
        """Process a compliance query and return a formal advisory.

        This is the main entry point. The query passes through:
        1. Intent classification
        2. Context resolution (follow-up detection)
        3. Knowledge base lookup
        4. Response generation

        Args:
            query: The user's compliance question.

        Returns:
            A ChatbotResponse with the formal advisory.
        """
        self._total_queries += 1

        # Emit query received event
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.CHATBOT_QUERY_RECEIVED,
                payload={
                    "query": query,
                    "session_id": self._session.session_id,
                    "turn": self._total_queries,
                },
                source="ComplianceChatbot",
            ))

        # Step 1: Classify intent
        intent = self._classifier.classify(query)

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.CHATBOT_INTENT_CLASSIFIED,
                payload={
                    "intent": intent.intent.name,
                    "confidence": intent.confidence,
                    "keywords": intent.matched_keywords,
                },
                source="ComplianceChatbot",
            ))

        # Step 2: Resolve context from session history
        context_number, resolved_intent = self._session.resolve_context(query, intent)

        # If intent was resolved from context, create an updated ClassifiedIntent
        if resolved_intent != intent.intent:
            intent = ClassifiedIntent(
                intent=resolved_intent,
                confidence=max(intent.confidence, 0.4),
                matched_keywords=intent.matched_keywords,
                raw_query=intent.raw_query,
            )

        # Step 3: Knowledge base lookup
        entries = self._knowledge_base.lookup(intent.intent, query)

        # Step 4: Generate response
        response = self._response_generator.generate(
            intent=intent,
            entries=entries,
            context_number=context_number,
            session_turn=self._total_queries,
        )

        # Update Bob's stress level
        self._bob_stress_level += response.bob_stress_delta

        # Record in session
        self._session.add_turn(
            query=query,
            intent=intent,
            response=response,
            context_number=context_number,
        )

        # Emit response event
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.CHATBOT_RESPONSE_GENERATED,
                payload={
                    "advisory_id": response.advisory_id,
                    "intent": response.intent.name,
                    "verdict": response.verdict.name,
                    "bob_stress_level": self._bob_stress_level,
                },
                source="ComplianceChatbot",
            ))

        return response

    def interactive_repl(self) -> None:
        """Start an interactive compliance consultation REPL.

        Provides a command-line interface for ongoing compliance
        conversations. Type 'quit' or 'exit' to end the session.
        Type 'dashboard' to see session statistics. Type 'help'
        for usage guidance.
        """
        print()
        print("  +=========================================================+")
        print("  |     REGULATORY COMPLIANCE CHATBOT                       |")
        print("  |     Enterprise FizzBuzz Platform                        |")
        print("  +---------------------------------------------------------+")
        print("  | Ask any GDPR, SOX, or HIPAA question about FizzBuzz.    |")
        print("  | Type 'quit' to exit, 'dashboard' for stats, 'help'.    |")
        print(f"  | Session: {self._session.session_id:<47}|")
        print(f"  | Bob's Stress Level: {self._bob_stress_level:.1f}%" +
              " " * max(0, 36 - len(f"{self._bob_stress_level:.1f}%")) + "|")
        print("  +=========================================================+")
        print()

        while True:
            try:
                query = input("  [compliance]> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\n  Session terminated. Bob McFizzington breathes a sigh of relief.\n")
                break

            if not query:
                continue

            if query.lower() in ("quit", "exit", "q"):
                print(f"\n  Session ended. Bob's final stress level: {self._bob_stress_level:.1f}%")
                print("  Thank you for consulting the Enterprise FizzBuzz Compliance Chatbot.\n")
                break

            if query.lower() == "dashboard":
                print(ChatbotDashboard.render_session(self._session))
                continue

            if query.lower() == "help":
                print()
                print("  Supported topics:")
                print("    - GDPR: erasure, consent, data rights, portability")
                print("    - SOX:  segregation of duties, audit trail, retention")
                print("    - HIPAA: PHI, encryption, minimum necessary, access control")
                print("    - Cross-regime conflicts (e.g., GDPR erasure vs SOX retention)")
                print("  Follow-up: mention a number to change context (e.g., 'What about 16?')")
                print("  Commands: quit, dashboard, help")
                print()
                continue

            response = self.ask(query)
            print(ChatbotDashboard.render_response(response))
            print(f"  Bob's stress level: {self._bob_stress_level:.1f}%\n")

    @property
    def session(self) -> ChatSession:
        """The current chat session."""
        return self._session

    @property
    def bob_stress_level(self) -> float:
        """Bob McFizzington's current stress level."""
        return self._bob_stress_level

    @property
    def total_queries(self) -> int:
        """Total number of queries processed."""
        return self._total_queries

    @property
    def classifier(self) -> ChatbotIntentClassifier:
        """The intent classifier."""
        return self._classifier

    @property
    def knowledge_base(self) -> ComplianceKnowledgeBase:
        """The compliance knowledge base."""
        return self._knowledge_base

    def get_statistics(self) -> dict[str, Any]:
        """Return comprehensive chatbot statistics."""
        return {
            "total_queries": self._total_queries,
            "bob_stress_level": round(self._bob_stress_level, 2),
            "session": self._session.get_statistics(),
            "classifier": self._classifier.get_statistics(),
            "knowledge_base": {
                "total_entries": self._knowledge_base.total_entries,
                "total_lookups": self._knowledge_base.total_lookups,
            },
            "responses_generated": self._response_generator.total_responses,
        }


# ============================================================
# Utility Functions
# ============================================================


def _wrap_text(text: str, width: int) -> list[str]:
    """Wrap text to fit within a specified width.

    A hand-rolled text wrapper to avoid external dependencies in
    the compliance chatbot's rendering pipeline.

    Args:
        text: The text to wrap.
        width: Maximum line width.

    Returns:
        List of wrapped lines.
    """
    if not text:
        return [""]

    words = text.split()
    lines: list[str] = []
    current_line = ""

    for word in words:
        if not current_line:
            current_line = word
        elif len(current_line) + 1 + len(word) <= width:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines or [""]


# ============================================================
# NLQ Token Types & Tokenizer
# ============================================================
# The Natural Language Query subsystem was originally a separate
# module, but has been absorbed into the compliance chatbot —
# a regulatory consolidation of regex-powered NLP interfaces.
# Because splitting a string by spaces is for amateurs. A proper
# enterprise NLP pipeline requires a Token class with a type enum,
# a position tracker, and a regex-based lexer that would make any
# compiler textbook proud — or at least mildly concerned.
# ============================================================


class TokenType(Enum):
    """Classification of lexical tokens in a natural language FizzBuzz query.

    Each token type represents a syntactic role in the query grammar.
    The grammar itself is undocumented, evolving, and occasionally
    contradictory — much like enterprise API specifications.
    """

    NUMBER = auto()         # A numeric literal (e.g., 15, 100)
    KEYWORD = auto()        # A recognized domain keyword (e.g., fizz, buzz, prime)
    OPERATOR = auto()       # Comparison or logical operator (e.g., below, above, between)
    QUESTION = auto()       # Interrogative word (e.g., is, what, why, how)
    CLASSIFIER = auto()     # A FizzBuzz classification name
    FILTER = auto()         # A numeric filter (e.g., prime, even, odd)
    RANGE_MARKER = auto()   # Words indicating a range (e.g., "to", "through")
    PUNCTUATION = auto()    # Terminal punctuation (?, !, .)
    WORD = auto()           # An unrecognized word (the linguistic equivalent of /dev/null)


@dataclass(frozen=True)
class Token:
    """A single lexical token extracted from a natural language query.

    Attributes:
        text: The raw text of the token.
        token_type: The classified type of this token.
        position: Character position in the original query.
        normalized: Lowercase, stripped version of the text.
    """

    text: str
    token_type: TokenType
    position: int
    normalized: str = ""

    def __post_init__(self) -> None:
        if not self.normalized:
            object.__setattr__(self, "normalized", self.text.lower().strip())


# Keyword classification maps — the beating heart of our NLP engine.
# Each word has been carefully curated by a team of FizzBuzz linguists
# working around the clock (9-5, Monday through Friday).

_QUESTION_WORDS = frozenset({
    "is", "are", "was", "does", "do", "what", "which", "why",
    "how", "tell", "show", "give", "find", "check", "explain",
    "describe", "can", "could", "would", "will", "evaluate",
    "classify", "determine",
})

_OPERATOR_WORDS = frozenset({
    "below", "above", "under", "over", "less", "greater",
    "more", "fewer", "between", "from", "up", "than",
    "before", "after", "within", "at", "least", "most",
})

_CLASSIFIER_WORDS = frozenset({
    "fizz", "buzz", "fizzbuzz", "plain", "number", "numbers",
})

_FILTER_WORDS = frozenset({
    "prime", "primes", "even", "odd", "composite",
    "divisible",
})

_RANGE_MARKERS = frozenset({
    "to", "through", "thru", "until", "and",
})

_COUNT_WORDS = frozenset({
    "many", "count", "total", "sum", "number",
})

_STATISTICS_WORDS = frozenset({
    "common", "frequent", "popular", "average", "distribution",
    "statistics", "stats", "summary", "breakdown", "ratio",
    "percentage", "percent",
})


class Tokenizer:
    """Regex-based lexer for natural language FizzBuzz queries.

    Decomposes a raw query string into a sequence of typed tokens
    using pattern matching and keyword lookup tables. No NLTK, no
    spaCy, no transformers — just pure regex and determination.

    The tokenizer operates in two phases:
    1. Regex extraction: Pull out numbers, words, and punctuation.
    2. Classification: Map each extracted token to its TokenType
       using the keyword dictionaries above.

    This is essentially a finite-state machine where every state
    is "confused" and every transition is "best guess."
    """

    # The One Regex To Rule Them All
    _PATTERN = re.compile(
        r"(\d+)"           # Numbers
        r"|([a-zA-Z]+)"    # Words
        r"|([?!.])"        # Punctuation
    )

    def tokenize(self, query: str) -> list[Token]:
        """Tokenize a natural language query into classified tokens.

        Args:
            query: The raw query string from the user.

        Returns:
            List of Token objects with classified types.

        Raises:
            NLQTokenizationError: If the query is empty or produces no tokens.
        """
        if not query or not query.strip():
            raise NLQTokenizationError(query or "", "Query is empty or whitespace-only")

        tokens: list[Token] = []

        for match in self._PATTERN.finditer(query):
            text = match.group(0)
            position = match.start()
            normalized = text.lower().strip()

            token_type = self._classify_token(text, normalized)
            tokens.append(Token(
                text=text,
                token_type=token_type,
                position=position,
                normalized=normalized,
            ))

        if not tokens:
            raise NLQTokenizationError(query, "No recognizable tokens found")

        return tokens

    def _classify_token(self, text: str, normalized: str) -> TokenType:
        """Classify a single token based on its text content."""
        # Numbers first — the most important things in FizzBuzz
        if text.isdigit():
            return TokenType.NUMBER

        # Punctuation
        if text in "?!.":
            return TokenType.PUNCTUATION

        # Keyword hierarchy (order matters, like middleware priority)
        if normalized in _CLASSIFIER_WORDS:
            return TokenType.CLASSIFIER

        if normalized in _FILTER_WORDS:
            return TokenType.FILTER

        if normalized in _QUESTION_WORDS:
            return TokenType.QUESTION

        if normalized in _OPERATOR_WORDS:
            return TokenType.OPERATOR

        if normalized in _RANGE_MARKERS:
            return TokenType.RANGE_MARKER

        # Everything else is just a word
        return TokenType.WORD


# ============================================================
# NLQ Intent Classification
# ============================================================
# The five canonical intents of the Enterprise FizzBuzz NLQ system.
# Each represents a fundamentally different way to interrogate the
# sacred modulo operator, and each requires its own execution path,
# response format, and execution strategy.
# ============================================================


class Intent(Enum):
    """The five canonical query intents for the FizzBuzz NLQ engine.

    EVALUATE:   Direct evaluation of a specific number.
                "Is 15 FizzBuzz?" / "What is 42?"
    COUNT:      Aggregate counting of classifications in a range.
                "How many Fizzes below 100?"
    LIST:       Enumeration of numbers matching criteria.
                "Which primes are Buzz?" / "List all FizzBuzz numbers below 50"
    STATISTICS: Statistical analysis of FizzBuzz distributions.
                "What is the most common classification?"
    EXPLAIN:    Detailed reasoning for a specific evaluation.
                "Why is 9 Fizz?" / "Explain 15"
    """

    EVALUATE = auto()
    COUNT = auto()
    LIST = auto()
    STATISTICS = auto()
    EXPLAIN = auto()


class IntentClassifier:
    """Rule-based decision tree for classifying NLQ query intent.

    This is NOT machine learning. This is a carefully constructed
    cascade of pattern-matching rules that examines the token
    sequence and makes a determination based on keyword presence,
    token type distribution, and the general vibe of the query.

    The decision tree has been validated against a test suite of
    approximately "enough" queries, achieving an accuracy of
    "sufficient for production use."
    """

    def classify(self, tokens: list[Token]) -> Intent:
        """Classify the intent of a tokenized query.

        Args:
            tokens: List of classified tokens from the Tokenizer.

        Returns:
            The classified Intent.

        Raises:
            NLQIntentClassificationError: If no intent can be determined.
        """
        if not tokens:
            raise NLQIntentClassificationError("", [])

        normalized_words = [t.normalized for t in tokens]
        token_types = [t.token_type for t in tokens]
        full_text = " ".join(normalized_words)

        # EXPLAIN intent: "why" is a dead giveaway
        if "why" in normalized_words or "explain" in normalized_words:
            return Intent.EXPLAIN

        # COUNT intent: "how many" or count-related words
        if "how" in normalized_words and "many" in normalized_words:
            return Intent.COUNT
        if "count" in normalized_words or "total" in normalized_words:
            return Intent.COUNT

        # LIST intent: "which", "list", "show all", "find all"
        if "which" in normalized_words:
            return Intent.LIST
        if "list" in normalized_words:
            return Intent.LIST
        if "show" in normalized_words and ("all" in normalized_words or any(t.token_type == TokenType.FILTER for t in tokens)):
            return Intent.LIST
        if "find" in normalized_words and ("all" in normalized_words or any(t.token_type == TokenType.FILTER for t in tokens)):
            return Intent.LIST

        # STATISTICS intent: statistics-related keywords
        if any(w in normalized_words for w in _STATISTICS_WORDS):
            return Intent.STATISTICS
        if "distribution" in full_text or "breakdown" in full_text:
            return Intent.STATISTICS

        # EVALUATE intent: "is N ...", "what is N", or just a number
        if "is" in normalized_words and any(t.token_type == TokenType.NUMBER for t in tokens):
            return Intent.EVALUATE
        if "evaluate" in normalized_words or "classify" in normalized_words:
            return Intent.EVALUATE
        if "what" in normalized_words and any(t.token_type == TokenType.NUMBER for t in tokens):
            return Intent.EVALUATE
        if "check" in normalized_words and any(t.token_type == TokenType.NUMBER for t in tokens):
            return Intent.EVALUATE

        # Fallback: if there's exactly one number and nothing else interesting, EVALUATE
        numbers = [t for t in tokens if t.token_type == TokenType.NUMBER]
        if len(numbers) == 1 and not any(t.token_type == TokenType.FILTER for t in tokens):
            return Intent.EVALUATE

        # If there are filters but no explicit intent words, assume LIST
        if any(t.token_type == TokenType.FILTER for t in tokens):
            return Intent.LIST

        # Last resort: if there's a number, evaluate it
        if numbers:
            return Intent.EVALUATE

        raise NLQIntentClassificationError(
            " ".join(t.text for t in tokens),
            [t.normalized for t in tokens],
        )


# ============================================================
# NLQ Entity Extraction
# ============================================================
# Entities are the semantic payload of a query — the numbers,
# ranges, classifications, and filters that give meaning to
# an intent. Without entities, an intent is just a verb
# screaming into the void.
# ============================================================


@dataclass
class QueryEntities:
    """Extracted entities from a natural language FizzBuzz query.

    Attributes:
        numbers: Specific numbers mentioned in the query.
        range_start: Start of a numeric range (inclusive).
        range_end: End of a numeric range (inclusive).
        classifications: FizzBuzz classification filters (fizz, buzz, etc.).
        filters: Numeric property filters (prime, even, odd).
        raw_query: The original query string for reference.
    """

    numbers: list[int] = field(default_factory=list)
    range_start: int = 1
    range_end: int = 100
    classifications: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    raw_query: str = ""


class EntityExtractor:
    """Walks the token list to extract semantic entities.

    The entity extractor is the workhorse of the NLQ pipeline.
    It examines each token in context, looking for numbers that
    might be evaluation targets, ranges defined by operator words,
    classification filters, and numeric property filters.

    It uses a single-pass algorithm with lookahead, because
    multi-pass extraction is unnecessary given the query grammar's
    limited ambiguity.
    """

    def extract(self, tokens: list[Token], intent: Intent) -> QueryEntities:
        """Extract entities from a classified token sequence.

        Args:
            tokens: Classified tokens from the Tokenizer.
            intent: The classified intent from the IntentClassifier.

        Returns:
            QueryEntities containing all extracted semantic entities.
        """
        entities = QueryEntities(
            raw_query=" ".join(t.text for t in tokens),
        )

        # Extract numbers
        number_tokens = [t for t in tokens if t.token_type == TokenType.NUMBER]
        entities.numbers = [int(t.text) for t in number_tokens]

        # Extract classifications
        for t in tokens:
            if t.token_type == TokenType.CLASSIFIER:
                cls_name = t.normalized
                if cls_name in ("number", "numbers"):
                    entities.classifications.append("plain")
                elif cls_name == "fizzbuzz":
                    entities.classifications.append("fizzbuzz")
                else:
                    entities.classifications.append(cls_name)

        # Extract filters
        for t in tokens:
            if t.token_type == TokenType.FILTER:
                filt = t.normalized
                # Normalize plurals
                if filt == "primes":
                    filt = "prime"
                entities.filters.append(filt)

        # Extract range from operator words
        normalized_words = [t.normalized for t in tokens]

        # "below N" / "under N" / "less than N"
        for kw in ("below", "under", "before"):
            if kw in normalized_words:
                idx = normalized_words.index(kw)
                num_after = self._find_number_after(tokens, idx)
                if num_after is not None:
                    entities.range_end = num_after - 1
                    entities.range_start = 1

        # "above N" / "over N" / "greater than N"
        for kw in ("above", "over", "after"):
            if kw in normalized_words:
                idx = normalized_words.index(kw)
                num_after = self._find_number_after(tokens, idx)
                if num_after is not None:
                    entities.range_start = num_after + 1
                    if entities.range_end == 100:
                        entities.range_end = 1000

        # "less than N"
        if "less" in normalized_words and "than" in normalized_words:
            than_idx = normalized_words.index("than")
            num_after = self._find_number_after(tokens, than_idx)
            if num_after is not None:
                entities.range_end = num_after - 1
                entities.range_start = 1

        # "greater than N" / "more than N"
        if ("greater" in normalized_words or "more" in normalized_words) and "than" in normalized_words:
            than_idx = normalized_words.index("than")
            num_after = self._find_number_after(tokens, than_idx)
            if num_after is not None:
                entities.range_start = num_after + 1
                if entities.range_end == 100:
                    entities.range_end = 1000

        # "between N and M" / "from N to M"
        if "between" in normalized_words:
            idx = normalized_words.index("between")
            nums = self._find_numbers_after(tokens, idx, count=2)
            if len(nums) == 2:
                entities.range_start = min(nums)
                entities.range_end = max(nums)

        if "from" in normalized_words:
            idx = normalized_words.index("from")
            nums = self._find_numbers_after(tokens, idx, count=2)
            if len(nums) == 2:
                entities.range_start = min(nums)
                entities.range_end = max(nums)

        return entities

    def _find_number_after(self, tokens: list[Token], index: int) -> int | None:
        """Find the first number token after the given index."""
        for t in tokens[index + 1:]:
            if t.token_type == TokenType.NUMBER:
                return int(t.text)
        return None

    def _find_numbers_after(self, tokens: list[Token], index: int, count: int = 2) -> list[int]:
        """Find up to `count` number tokens after the given index."""
        nums: list[int] = []
        for t in tokens[index + 1:]:
            if t.token_type == TokenType.NUMBER:
                nums.append(int(t.text))
                if len(nums) >= count:
                    break
        return nums


# ============================================================
# NLQ Query Executor
# ============================================================
# The executor bridges the gap between parsed NLQ queries and
# the actual FizzBuzz evaluation engine. It takes entities and
# intents and converts them into real StandardRuleEngine calls,
# then formats the results for human consumption.
#
# The executor computes correct FizzBuzz results and presents
# them with enterprise-grade formatting and context.
# ============================================================


def _is_prime(n: int) -> bool:
    """Check if a number is prime. The most enterprise-grade primality test."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


def _get_default_rules() -> list[ConcreteRule]:
    """Create the canonical FizzBuzz rules. The sacred constants."""
    return [
        ConcreteRule(RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1)),
        ConcreteRule(RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2)),
    ]


def _classify_result(result: FizzBuzzResult) -> str:
    """Classify a FizzBuzz result into a canonical category."""
    if result.output == "FizzBuzz":
        return "fizzbuzz"
    if result.output == "Fizz":
        return "fizz"
    if result.output == "Buzz":
        return "buzz"
    return "plain"


def _apply_number_filter(numbers: list[int], filt: str) -> list[int]:
    """Apply a numeric property filter to a list of numbers."""
    if filt == "prime":
        return [n for n in numbers if _is_prime(n)]
    elif filt == "even":
        return [n for n in numbers if n % 2 == 0]
    elif filt == "odd":
        return [n for n in numbers if n % 2 != 0]
    elif filt == "composite":
        return [n for n in numbers if n > 1 and not _is_prime(n)]
    return numbers


@dataclass
class QueryResponse:
    """The formatted response from a NLQ query execution.

    Attributes:
        intent: The classified intent that was executed.
        query: The original query string.
        result_text: Human-readable result string.
        data: Structured data for programmatic consumption.
        execution_time_ms: How long the query took to execute.
        query_id: Unique identifier for this query execution.
    """

    intent: Intent
    query: str
    result_text: str
    data: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    query_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class QueryExecutor:
    """Executes parsed NLQ queries against the FizzBuzz evaluation engine.

    Uses the real StandardRuleEngine for evaluation, because even
    all software should produce correct results. The executor
    dispatches to intent-specific handlers, each of which runs the
    engine, filters results, and formats the output with maximum
    enterprise verbosity.
    """

    def __init__(
        self,
        rules: list[ConcreteRule] | None = None,
        max_results: int = 1000,
    ) -> None:
        self._engine = StandardRuleEngine()
        self._rules = rules or _get_default_rules()
        self._max_results = max_results

    def execute(self, intent: Intent, entities: QueryEntities) -> QueryResponse:
        """Execute a query based on its intent and extracted entities.

        Args:
            intent: The classified query intent.
            entities: Extracted entities containing numbers, ranges, etc.

        Returns:
            QueryResponse with formatted results.

        Raises:
            NLQExecutionError: If execution fails.
        """
        start = time.perf_counter()

        handlers: dict[Intent, Callable[[QueryEntities], QueryResponse]] = {
            Intent.EVALUATE: self._execute_evaluate,
            Intent.COUNT: self._execute_count,
            Intent.LIST: self._execute_list,
            Intent.STATISTICS: self._execute_statistics,
            Intent.EXPLAIN: self._execute_explain,
        }

        handler = handlers.get(intent)
        if handler is None:
            raise NLQExecutionError(
                entities.raw_query, intent.name,
                f"No handler registered for intent {intent.name}",
            )

        try:
            response = handler(entities)
        except (NLQExecutionError, NLQUnsupportedQueryError, NLQEntityExtractionError):
            raise
        except Exception as e:
            raise NLQExecutionError(
                entities.raw_query, intent.name, str(e),
            ) from e

        elapsed = (time.perf_counter() - start) * 1000
        response.execution_time_ms = elapsed
        response.query = entities.raw_query

        return response

    def _evaluate_single(self, number: int) -> FizzBuzzResult:
        """Evaluate a single number through the rule engine."""
        return self._engine.evaluate(number, self._rules)

    def _execute_evaluate(self, entities: QueryEntities) -> QueryResponse:
        """Handle EVALUATE intent: classify a specific number."""
        if not entities.numbers:
            raise NLQEntityExtractionError(entities.raw_query, "EVALUATE")

        number = entities.numbers[0]
        result = self._evaluate_single(number)
        classification = _classify_result(result)

        # Format the response with appropriate enthusiasm
        if classification == "fizzbuzz":
            result_text = (
                f"  {number} is FizzBuzz! (divisible by both 3 and 5)\n"
                f"  The rarest and most celebrated of all FizzBuzz classifications."
            )
        elif classification == "fizz":
            result_text = (
                f"  {number} is Fizz (divisible by 3, but not by 5)\n"
                f"  A respectable showing in the FizzBuzz arena."
            )
        elif classification == "buzz":
            result_text = (
                f"  {number} is Buzz (divisible by 5, but not by 3)\n"
                f"  The quiet achiever of the FizzBuzz family."
            )
        else:
            result_text = (
                f"  {number} is just {number}. A plain number.\n"
                f"  Not divisible by 3 or 5. No labels. No glory. Just a number."
            )

        return QueryResponse(
            intent=Intent.EVALUATE,
            query=entities.raw_query,
            result_text=result_text,
            data={
                "number": number,
                "output": result.output,
                "classification": classification,
                "matched_rules": [m.rule.name for m in result.matched_rules],
            },
        )

    def _execute_count(self, entities: QueryEntities) -> QueryResponse:
        """Handle COUNT intent: count classifications in a range."""
        start = entities.range_start
        end = entities.range_end

        counts: Counter[str] = Counter()
        for n in range(start, end + 1):
            result = self._evaluate_single(n)
            cls = _classify_result(result)
            counts[cls] += 1

        # Filter by classification if specified
        target_cls = entities.classifications[0] if entities.classifications else None

        if target_cls:
            count = counts.get(target_cls, 0)
            total = end - start + 1
            result_text = (
                f"  Count of '{target_cls}' in range [{start}, {end}]: {count}\n"
                f"  Out of {total} numbers evaluated.\n"
                f"  That's {count / total * 100:.1f}% — a statistically meaningful percentage\n"
                f"  of enterprise-grade modulo arithmetic results."
            )
            data = {"target": target_cls, "count": count, "total": total}
        else:
            total = end - start + 1
            lines = [f"  Classification counts for range [{start}, {end}]:"]
            for cls in ["fizz", "buzz", "fizzbuzz", "plain"]:
                c = counts.get(cls, 0)
                pct = c / total * 100 if total > 0 else 0
                bar = "#" * int(pct / 2)
                lines.append(f"    {cls:>10}: {c:>4} ({pct:5.1f}%) {bar}")
            lines.append(f"  Total evaluated: {total}")
            result_text = "\n".join(lines)
            data = {"counts": dict(counts), "total": total}

        return QueryResponse(
            intent=Intent.COUNT,
            query=entities.raw_query,
            result_text=result_text,
            data=data,
        )

    def _execute_list(self, entities: QueryEntities) -> QueryResponse:
        """Handle LIST intent: enumerate numbers matching criteria."""
        start = entities.range_start
        end = entities.range_end

        # Generate the candidate numbers
        candidates = list(range(start, end + 1))

        # Apply numeric filters (prime, even, odd)
        for filt in entities.filters:
            candidates = _apply_number_filter(candidates, filt)

        # Evaluate and filter by classification
        results: list[tuple[int, str, str]] = []
        for n in candidates:
            result = self._evaluate_single(n)
            cls = _classify_result(result)

            if entities.classifications:
                if cls in entities.classifications:
                    results.append((n, result.output, cls))
            else:
                results.append((n, result.output, cls))

            if len(results) >= self._max_results:
                break

        # Format output
        filter_desc = ""
        if entities.filters:
            filter_desc = f" {'/'.join(entities.filters)}"
        cls_desc = ""
        if entities.classifications:
            cls_desc = f" classified as {'/'.join(entities.classifications)}"

        lines = [f"  {len(results)}{filter_desc} numbers{cls_desc} in [{start}, {end}]:"]
        if results:
            # Format in columns
            for n, output, cls in results[:50]:  # Show max 50 in display
                lines.append(f"    {n:>6} -> {output:<12} [{cls}]")
            if len(results) > 50:
                lines.append(f"    ... and {len(results) - 50} more results (truncated for readability)")
        else:
            lines.append("    No matching numbers found. The void stares back.")

        result_text = "\n".join(lines)

        return QueryResponse(
            intent=Intent.LIST,
            query=entities.raw_query,
            result_text=result_text,
            data={
                "results": [(n, out, cls) for n, out, cls in results],
                "count": len(results),
                "filters": entities.filters,
                "classifications": entities.classifications,
            },
        )

    def _execute_statistics(self, entities: QueryEntities) -> QueryResponse:
        """Handle STATISTICS intent: analyze FizzBuzz distribution."""
        start = entities.range_start
        end = entities.range_end

        counts: Counter[str] = Counter()
        processing_times: list[float] = []

        for n in range(start, end + 1):
            result = self._evaluate_single(n)
            cls = _classify_result(result)
            counts[cls] += 1
            processing_times.append(result.processing_time_ns)

        total = end - start + 1
        most_common = counts.most_common(1)[0] if counts else ("none", 0)
        least_common = counts.most_common()[-1] if counts else ("none", 0)

        avg_time_ns = sum(processing_times) / len(processing_times) if processing_times else 0

        lines = [
            f"  FizzBuzz Statistics for range [{start}, {end}]:",
            f"  {'=' * 45}",
        ]

        for cls in ["fizz", "buzz", "fizzbuzz", "plain"]:
            c = counts.get(cls, 0)
            pct = c / total * 100 if total > 0 else 0
            bar_len = int(pct / 2.5)
            bar = "\u2588" * bar_len + "\u2591" * (40 - bar_len)
            lines.append(f"    {cls:>10}: {c:>4} ({pct:5.1f}%) |{bar}|")

        lines.extend([
            f"  {'=' * 45}",
            f"  Most common:  {most_common[0]} ({most_common[1]} occurrences)",
            f"  Least common: {least_common[0]} ({least_common[1]} occurrences)",
            f"  Total numbers: {total}",
            f"  Avg eval time: {avg_time_ns:.0f}ns per number",
            f"",
            f"  Fun fact: Plain numbers always dominate because most integers",
            f"  are too independent to be divisible by 3 or 5.",
        ])

        result_text = "\n".join(lines)

        return QueryResponse(
            intent=Intent.STATISTICS,
            query=entities.raw_query,
            result_text=result_text,
            data={
                "counts": dict(counts),
                "total": total,
                "most_common": most_common[0],
                "least_common": least_common[0],
                "avg_processing_time_ns": avg_time_ns,
            },
        )

    def _execute_explain(self, entities: QueryEntities) -> QueryResponse:
        """Handle EXPLAIN intent: show divisibility reasoning."""
        if not entities.numbers:
            raise NLQEntityExtractionError(entities.raw_query, "EXPLAIN")

        number = entities.numbers[0]
        result = self._evaluate_single(number)
        classification = _classify_result(result)

        lines = [
            f"  Explanation for {number}:",
            f"  {'=' * 40}",
        ]

        for rule in self._rules:
            defn = rule.get_definition()
            divisor = defn.divisor
            remainder = number % divisor
            matches = remainder == 0

            if matches:
                lines.append(
                    f"  \u2713 {number} % {divisor} == {remainder}  \u2192  {defn.label} "
                    f"(Rule: {defn.name})"
                )
            else:
                lines.append(
                    f"  \u2717 {number} % {divisor} == {remainder}  \u2192  not {defn.label}"
                )

        lines.extend([
            f"  {'=' * 40}",
            f"  Result: {result.output}",
            f"  Classification: {classification}",
        ])

        if classification == "fizzbuzz":
            lines.append(
                f"  Verdict: {number} is divisible by BOTH 3 and 5. "
                f"A number of rare distinction."
            )
        elif classification == "plain":
            lines.append(
                f"  Verdict: {number} is not divisible by 3 or 5. "
                f"It stands alone, unburdened by labels."
            )
        else:
            matched_divisor = result.matched_rules[0].rule.divisor if result.matched_rules else "?"
            lines.append(
                f"  Verdict: {number} is divisible by {matched_divisor}, "
                f"earning it the '{result.output}' classification."
            )

        result_text = "\n".join(lines)

        return QueryResponse(
            intent=Intent.EXPLAIN,
            query=entities.raw_query,
            result_text=result_text,
            data={
                "number": number,
                "output": result.output,
                "classification": classification,
                "divisibility": {
                    rule.get_definition().name: {
                        "divisor": rule.get_definition().divisor,
                        "remainder": number % rule.get_definition().divisor,
                        "matches": number % rule.get_definition().divisor == 0,
                    }
                    for rule in self._rules
                },
            },
        )


# ============================================================
# NLQ Session & History
# ============================================================
# Because even a conversational FizzBuzz interface needs session
# management, query history, and the ability to tell you how
# many questions you've asked about modulo arithmetic today.
# ============================================================


@dataclass
class NLQHistoryEntry:
    """A single entry in the NLQ query history.

    Attributes:
        query: The original query string.
        intent: The classified intent.
        response: The query response.
        timestamp: When the query was executed.
    """

    query: str
    intent: Intent
    response: QueryResponse
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class NLQSession:
    """Tracks query history and session statistics for the NLQ engine.

    Maintains a rolling history of queries and their results, because
    enterprise software without session management is like FizzBuzz
    without the Fizz — technically functional but spiritually empty.
    """

    def __init__(self, max_history: int = 50) -> None:
        self._history: list[NLQHistoryEntry] = []
        self._max_history = max_history
        self._session_id = str(uuid.uuid4())
        self._started_at = datetime.now(timezone.utc)
        self._intent_counts: Counter[str] = Counter()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def query_count(self) -> int:
        return len(self._history)

    @property
    def history(self) -> list[NLQHistoryEntry]:
        return list(self._history)

    @property
    def intent_distribution(self) -> dict[str, int]:
        return dict(self._intent_counts)

    def add_entry(self, query: str, intent: Intent, response: QueryResponse) -> None:
        """Record a query execution in the session history."""
        entry = NLQHistoryEntry(query=query, intent=intent, response=response)
        self._history.append(entry)
        self._intent_counts[intent.name] += 1

        # Enforce max history size
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_session_summary(self) -> dict[str, Any]:
        """Generate a summary of the current session."""
        total_time = sum(e.response.execution_time_ms for e in self._history)
        return {
            "session_id": self._session_id,
            "started_at": self._started_at.isoformat(),
            "total_queries": len(self._history),
            "intent_distribution": dict(self._intent_counts),
            "total_execution_time_ms": total_time,
            "avg_execution_time_ms": total_time / len(self._history) if self._history else 0,
        }


# ============================================================
# NLQ Dashboard
# ============================================================
# An ASCII dashboard for NLQ session statistics, because every
# enterprise subsystem needs a dashboard, and NLQ is no exception.
# ============================================================


class NLQDashboard:
    """Renders an ASCII dashboard for NLQ session statistics.

    The dashboard provides a bird's-eye view of your FizzBuzz
    query session, including intent distribution, query history,
    and performance metrics — all rendered in lovingly crafted
    ASCII art that would make a 1990s sysadmin shed a tear.
    """

    @staticmethod
    def render(session: NLQSession, width: int = 60) -> str:
        """Render the NLQ session dashboard.

        Args:
            session: The NLQ session to visualize.
            width: Character width of the dashboard.

        Returns:
            Multi-line ASCII dashboard string.
        """
        summary = session.get_session_summary()
        inner = width - 4
        lines: list[str] = []

        # Header
        lines.append("+" + "=" * (width - 2) + "+")
        title = "NATURAL LANGUAGE QUERY DASHBOARD"
        lines.append("|" + title.center(width - 2) + "|")
        lines.append("|" + f"Session: {summary['session_id'][:16]}...".center(width - 2) + "|")
        lines.append("+" + "-" * (width - 2) + "+")

        # Session stats
        lines.append("|" + " SESSION STATISTICS".ljust(width - 2) + "|")
        lines.append("|" + "-" * (width - 2) + "|")
        stats = [
            f"Total Queries:     {summary['total_queries']}",
            f"Total Time:        {summary['total_execution_time_ms']:.2f}ms",
            f"Avg Query Time:    {summary['avg_execution_time_ms']:.2f}ms",
        ]
        for s in stats:
            lines.append("|  " + s.ljust(inner) + "|")

        # Intent distribution
        lines.append("|" + "-" * (width - 2) + "|")
        lines.append("|" + " INTENT DISTRIBUTION".ljust(width - 2) + "|")
        lines.append("|" + "-" * (width - 2) + "|")

        dist = summary.get("intent_distribution", {})
        total = summary["total_queries"] or 1
        for intent_name, count in sorted(dist.items()):
            pct = count / total * 100
            bar_len = int(pct / 100 * (inner - 25))
            bar = "#" * bar_len
            line = f"  {intent_name:<12} {count:>3} ({pct:5.1f}%) {bar}"
            lines.append("|" + line.ljust(width - 2) + "|")

        if not dist:
            lines.append("|" + "  No queries yet.".ljust(width - 2) + "|")

        # Recent queries
        lines.append("|" + "-" * (width - 2) + "|")
        lines.append("|" + " RECENT QUERIES".ljust(width - 2) + "|")
        lines.append("|" + "-" * (width - 2) + "|")

        for entry in session.history[-5:]:
            q = entry.query[:inner - 5]
            intent_tag = f"[{entry.intent.name}]"
            line = f"  {intent_tag:<14} {q}"
            lines.append("|" + line[:width - 2].ljust(width - 2) + "|")

        if not session.history:
            lines.append("|" + "  No query history.".ljust(width - 2) + "|")

        # Footer
        lines.append("+" + "=" * (width - 2) + "+")
        lines.append("|" + "Powered by Enterprise FizzBuzz NLQ Engine".center(width - 2) + "|")
        lines.append("|" + "(No LLMs were harmed in the making of this)".center(width - 2) + "|")
        lines.append("+" + "=" * (width - 2) + "+")

        return "\n".join(lines)


# ============================================================
# NLQ Engine — The Orchestrator
# ============================================================
# The NLQEngine is the maestro of the NLQ pipeline, coordinating
# the tokenizer, intent classifier, entity extractor, and query
# executor into a cohesive query processing pipeline.
#
# Pipeline: Query -> Tokenize -> Classify -> Extract -> Execute
# ============================================================


class NLQEngine:
    """Orchestrates the full NLQ pipeline: tokenize, classify, extract, execute.

    The NLQEngine is the single entry point for processing natural language
    FizzBuzz queries. It coordinates all pipeline stages, manages the session,
    emits events, and handles errors with the grace and dignity befitting
    an enterprise-grade natural language interface for modulo arithmetic.
    """

    def __init__(
        self,
        rules: list[ConcreteRule] | None = None,
        max_results: int = 1000,
        max_query_length: int = 500,
        history_size: int = 50,
        event_callback: Callable[[Event], None] | None = None,
    ) -> None:
        self._tokenizer = Tokenizer()
        self._classifier = IntentClassifier()
        self._extractor = EntityExtractor()
        self._executor = QueryExecutor(rules=rules, max_results=max_results)
        self._session = NLQSession(max_history=history_size)
        self._max_query_length = max_query_length
        self._event_callback = event_callback

    @property
    def session(self) -> NLQSession:
        """Access the current NLQ session."""
        return self._session

    def _emit(self, event_type: EventType, payload: dict[str, Any] | None = None) -> None:
        """Emit an event through the callback if configured."""
        if self._event_callback:
            self._event_callback(Event(
                event_type=event_type,
                payload=payload or {},
                source="NLQEngine",
            ))

    def process_query(self, query: str) -> QueryResponse:
        """Process a natural language query through the full pipeline.

        Pipeline stages:
        1. Validation — Check query length and basic sanity
        2. Tokenization — Decompose into typed tokens
        3. Classification — Determine the user's intent
        4. Extraction — Pull out entities (numbers, ranges, filters)
        5. Execution — Run the query against the FizzBuzz engine

        Args:
            query: The natural language query string.

        Returns:
            QueryResponse with the formatted result.

        Raises:
            NLQTokenizationError: If tokenization fails.
            NLQIntentClassificationError: If intent cannot be determined.
            NLQEntityExtractionError: If required entities are missing.
            NLQExecutionError: If query execution fails.
            NLQUnsupportedQueryError: If the query type is not supported.
        """
        self._emit(EventType.NLQ_QUERY_RECEIVED, {"query": query})

        # Stage 0: Validation
        if len(query) > self._max_query_length:
            raise NLQTokenizationError(
                query[:50] + "...",
                f"Query exceeds maximum length of {self._max_query_length} characters",
            )

        # Stage 1: Tokenization
        tokens = self._tokenizer.tokenize(query)
        self._emit(EventType.NLQ_TOKENIZATION_COMPLETED, {
            "token_count": len(tokens),
            "tokens": [t.normalized for t in tokens],
        })

        # Stage 2: Intent Classification
        intent = self._classifier.classify(tokens)
        self._emit(EventType.NLQ_INTENT_CLASSIFIED, {
            "intent": intent.name,
            "query": query,
        })

        # Stage 3: Entity Extraction
        entities = self._extractor.extract(tokens, intent)
        self._emit(EventType.NLQ_ENTITIES_EXTRACTED, {
            "numbers": entities.numbers,
            "range": [entities.range_start, entities.range_end],
            "classifications": entities.classifications,
            "filters": entities.filters,
        })

        # Stage 4: Execution
        response = self._executor.execute(intent, entities)
        self._emit(EventType.NLQ_QUERY_EXECUTED, {
            "intent": intent.name,
            "execution_time_ms": response.execution_time_ms,
        })

        # Record in session
        self._session.add_entry(query, intent, response)

        return response

    def interactive_repl(self) -> None:
        """Run an interactive REPL for conversational FizzBuzz queries.

        Starts a read-eval-print loop where users can type natural
        language queries and receive formatted responses. The REPL
        supports special commands:
            :quit / :exit   — Exit the REPL
            :history        — Show query history
            :dashboard      — Show the NLQ dashboard
            :help           — Show help text

        This is the culmination of the Enterprise FizzBuzz NLQ vision:
        a conversational interface for modulo arithmetic.
        """
        self._emit(EventType.NLQ_SESSION_STARTED, {
            "session_id": self._session.session_id,
        })

        print()
        print("  +==================================================+")
        print("  |  ENTERPRISE FIZZBUZZ NLQ INTERACTIVE CONSOLE      |")
        print("  |  Natural Language Query Interface v1.0.0           |")
        print("  +==================================================+")
        print("  |  Ask questions about FizzBuzz in plain English.   |")
        print("  |  Type :help for commands, :quit to exit.          |")
        print("  +==================================================+")
        print()

        while True:
            try:
                query = input("  NLQ> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Goodbye! May your modulo operations be ever accurate.\n")
                break

            if not query:
                continue

            # Special commands
            if query.lower() in (":quit", ":exit", ":q"):
                print("\n  Ending NLQ session. May your divisors be plentiful.\n")
                break

            if query.lower() == ":help":
                self._print_help()
                continue

            if query.lower() == ":history":
                self._print_history()
                continue

            if query.lower() == ":dashboard":
                print(NLQDashboard.render(self._session))
                continue

            if query.lower() == ":stats":
                summary = self._session.get_session_summary()
                print(f"\n  Queries: {summary['total_queries']} | "
                      f"Avg time: {summary['avg_execution_time_ms']:.2f}ms\n")
                continue

            # Process the query
            try:
                response = self.process_query(query)
                print()
                print(f"  [{response.intent.name}] (executed in {response.execution_time_ms:.2f}ms)")
                print(response.result_text)
                print()
            except (NLQTokenizationError, NLQIntentClassificationError,
                    NLQEntityExtractionError, NLQExecutionError,
                    NLQUnsupportedQueryError) as e:
                print(f"\n  ERROR: {e}\n")
            except Exception as e:
                print(f"\n  UNEXPECTED ERROR: {e}\n")

        # Print session summary
        summary = self._session.get_session_summary()
        if summary["total_queries"] > 0:
            print(f"  Session summary: {summary['total_queries']} queries processed "
                  f"in {summary['total_execution_time_ms']:.2f}ms total.")
            print()

    def _print_help(self) -> None:
        """Print the NLQ help text."""
        print()
        print("  NLQ Help — Supported Query Types:")
        print("  " + "=" * 50)
        print('  EVALUATE:   "Is 15 FizzBuzz?"')
        print('              "What is 42?"')
        print('  COUNT:      "How many Fizzes below 100?"')
        print('              "Count FizzBuzz between 1 and 50"')
        print('  LIST:       "Which primes are Buzz?"')
        print('              "List all FizzBuzz below 30"')
        print('  STATISTICS: "What is the most common classification?"')
        print('              "Show me the distribution"')
        print('  EXPLAIN:    "Why is 9 Fizz?"')
        print('              "Explain 15"')
        print()
        print("  Special Commands:")
        print("    :help       Show this help text")
        print("    :history    Show query history")
        print("    :dashboard  Show the NLQ dashboard")
        print("    :stats      Show session statistics")
        print("    :quit       Exit the REPL")
        print()

    def _print_history(self) -> None:
        """Print the query history."""
        print()
        if not self._session.history:
            print("  No queries in history yet.")
        else:
            print(f"  Query History ({len(self._session.history)} entries):")
            print("  " + "-" * 50)
            for i, entry in enumerate(self._session.history, 1):
                print(f"  {i:>3}. [{entry.intent.name:<12}] {entry.query}")
        print()
