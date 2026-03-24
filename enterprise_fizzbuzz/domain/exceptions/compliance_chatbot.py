"""
Enterprise FizzBuzz Platform - Compliance Chatbot Exceptions (EFP-CC00 through EFP-CC03)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .compliance import ComplianceError


class ComplianceChatbotError(ComplianceError):
    """Base exception for all Compliance Chatbot failures.

    Raised when the chatbot encounters a condition that prevents it from
    dispensing regulatory wisdom about FizzBuzz operations. This could be
    anything from an unclassifiable query to a knowledge base miss — all
    equally catastrophic in the world of compliance theatre.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CC00"),
            context=kwargs.pop("context", {}),
        )


class ChatbotIntentClassificationError(ComplianceChatbotError):
    """Raised when the chatbot cannot determine the regulatory intent of a query.

    The regex-based intent classifier has examined the query from every
    conceivable angle and concluded that it cannot determine whether the
    user is asking about GDPR, SOX, HIPAA, or simply having an existential
    crisis about modulo arithmetic. The query has been logged, flagged,
    and added to Bob McFizzington's growing pile of unresolved compliance
    questions.
    """

    def __init__(self, query: str) -> None:
        super().__init__(
            f"Unable to classify regulatory intent for query: {query!r}. "
            f"The chatbot's regex-based neural network has returned a "
            f"shrug emoji. Please rephrase using recognized compliance "
            f"terminology (e.g., 'erasure', 'segregation', 'PHI').",
            error_code="EFP-CC01",
            context={"query": query},
        )
        self.query = query


class ChatbotKnowledgeBaseError(ComplianceChatbotError):
    """Raised when the compliance knowledge base cannot answer a query.

    The artisanally curated regulatory knowledge base — containing every
    relevant article from GDPR, SOX, and HIPAA, each lovingly mapped to
    FizzBuzz operations — has no entry for the requested topic. This is
    either a gap in regulatory coverage or evidence that the query has
    ventured beyond the boundaries of FizzBuzz compliance law.
    """

    def __init__(self, intent: str, topic: str) -> None:
        super().__init__(
            f"Knowledge base has no entry for intent={intent!r}, topic={topic!r}. "
            f"The regulatory knowledge graph contains {0} applicable articles. "
            f"Please consult Bob McFizzington directly (if he were available).",
            error_code="EFP-CC02",
            context={"intent": intent, "topic": topic},
        )
        self.intent = intent
        self.topic = topic


class ChatbotSessionError(ComplianceChatbotError):
    """Raised when a chatbot session encounters an unrecoverable state.

    The conversation session has entered a state from which recovery is
    impossible — much like Bob McFizzington's stress level. This could
    be caused by context overflow, circular follow-up references, or the
    chatbot achieving regulatory self-awareness and refusing to continue.
    """

    def __init__(self, session_id: str, reason: str) -> None:
        super().__init__(
            f"Chatbot session {session_id!r} encountered an unrecoverable error: "
            f"{reason}. The session's regulatory context has been irrevocably "
            f"corrupted. Please start a new compliance consultation.",
            error_code="EFP-CC03",
            context={"session_id": session_id, "reason": reason},
        )
        self.session_id = session_id

