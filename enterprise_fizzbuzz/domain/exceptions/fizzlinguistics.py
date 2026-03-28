"""
Enterprise FizzBuzz Platform - FizzLinguistics Exceptions (EFP-LNG00 through EFP-LNG09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzLinguisticsError(FizzBuzzError):
    """Base exception for all FizzLinguistics NLP errors.

    The FizzLinguistics engine provides natural language processing
    capabilities for analyzing and understanding FizzBuzz output in
    human language. Tokenization, parsing, and sentiment analysis
    are critical for ensuring that FizzBuzz results communicate
    effectively to human operators.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-LNG00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class TokenizationError(FizzLinguisticsError):
    """Raised when the tokenizer cannot segment input text.

    Tokenization is the foundational step of the NLP pipeline. If the
    input text contains malformed Unicode, null bytes, or exceeds the
    maximum sequence length, the tokenizer cannot produce a valid
    token stream for downstream processing.
    """

    def __init__(self, text_preview: str, reason: str) -> None:
        super().__init__(
            f"Tokenization failed for input '{text_preview[:50]}...': {reason}",
            error_code="EFP-LNG01",
            context={"text_preview": text_preview[:100], "reason": reason},
        )


class POSTaggingError(FizzLinguisticsError):
    """Raised when part-of-speech tagging produces an inconsistent result.

    The POS tagger assigns grammatical categories (noun, verb, adjective,
    etc.) to each token. An unrecognized token or ambiguous context can
    produce a tag sequence that violates syntactic constraints, preventing
    downstream dependency parsing.
    """

    def __init__(self, token: str, reason: str) -> None:
        super().__init__(
            f"POS tagging error for token '{token}': {reason}",
            error_code="EFP-LNG02",
            context={"token": token, "reason": reason},
        )


class DependencyParseError(FizzLinguisticsError):
    """Raised when the dependency parser cannot produce a valid tree.

    A dependency parse must form a tree rooted at a single head with
    no cycles. If the parser encounters a sentence structure it cannot
    handle, the resulting non-tree graph cannot be used for semantic
    analysis of FizzBuzz output.
    """

    def __init__(self, sentence_preview: str, reason: str) -> None:
        super().__init__(
            f"Dependency parse failed for '{sentence_preview[:50]}...': {reason}",
            error_code="EFP-LNG03",
            context={"sentence_preview": sentence_preview[:80], "reason": reason},
        )


class NERError(FizzLinguisticsError):
    """Raised when named entity recognition encounters an error.

    The NER module identifies entities (numbers, labels, organizational
    references) in FizzBuzz output text. A recognition failure means
    key entities in the output cannot be extracted for structured
    reporting.
    """

    def __init__(self, entity_type: str, reason: str) -> None:
        super().__init__(
            f"Named entity recognition error for type '{entity_type}': {reason}",
            error_code="EFP-LNG04",
            context={"entity_type": entity_type, "reason": reason},
        )


class SentimentAnalysisError(FizzLinguisticsError):
    """Raised when sentiment scoring produces an out-of-range value.

    Sentiment scores must lie in [-1.0, 1.0] where -1.0 is maximally
    negative and 1.0 is maximally positive. An out-of-range score
    indicates a miscalibrated model that cannot reliably assess the
    emotional valence of FizzBuzz output.
    """

    def __init__(self, score: float, reason: str) -> None:
        super().__init__(
            f"Sentiment analysis error: score={score:.4f} — {reason}",
            error_code="EFP-LNG05",
            context={"score": score, "reason": reason},
        )


class PerplexityError(FizzLinguisticsError):
    """Raised when language model perplexity calculation fails.

    Perplexity measures how well a language model predicts a sequence.
    Non-positive probabilities or empty sequences produce undefined
    perplexity values, preventing quality assessment of FizzBuzz
    output fluency.
    """

    def __init__(self, sequence_length: int, reason: str) -> None:
        super().__init__(
            f"Perplexity computation failed for sequence of length "
            f"{sequence_length}: {reason}",
            error_code="EFP-LNG06",
            context={"sequence_length": sequence_length, "reason": reason},
        )


class LinguisticsMiddlewareError(FizzLinguisticsError):
    """Raised when the FizzLinguistics middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzLinguistics middleware error: {reason}",
            error_code="EFP-LNG07",
            context={"reason": reason},
        )
