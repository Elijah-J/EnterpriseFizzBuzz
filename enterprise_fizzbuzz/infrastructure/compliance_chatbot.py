"""
Enterprise FizzBuzz Platform - Regulatory Compliance Chatbot

Implements a fully-featured, regex-powered compliance chatbot capable of
answering GDPR, SOX, and HIPAA questions about FizzBuzz operations. Because
the only thing standing between your FizzBuzz deployment and a regulatory
enforcement action is a chatbot that dispenses formal COMPLIANCE ADVISORYs
about modulo arithmetic.

Features:
    - Intent classification via regex/keyword matching (no LLMs were harmed)
    - Knowledge base of ~25 real regulatory articles mapped to FizzBuzz
    - Cross-regime conflict detection (GDPR erasure vs SOX retention)
    - Formal advisory responses with COMPLIANT/NON_COMPLIANT verdicts
    - Conversation memory with follow-up context resolution
    - ASCII dashboard for chatbot session statistics
    - Bob McFizzington's stress-level-aware editorial commentary

Architecture:
    Query -> IntentClassifier -> KnowledgeBase -> ResponseGenerator -> Advisory
    (Four stages for questions that could be answered with "it's FizzBuzz,
    none of these regulations apply.")
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ChatbotIntentClassificationError,
    ChatbotKnowledgeBaseError,
    ChatbotSessionError,
    ComplianceChatbotError,
)
from enterprise_fizzbuzz.domain.models import (
    ComplianceVerdict,
    Event,
    EventType,
)

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
