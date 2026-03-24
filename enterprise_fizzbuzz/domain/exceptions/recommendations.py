"""
Enterprise FizzBuzz Platform - Recommendation Engine Exceptions (EFP-RE01 through EFP-RE04)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class RecommendationError(FizzBuzzError):
    """Base exception for all Recommendation Engine errors.

    When the system that suggests which numbers you might enjoy evaluating
    next encounters a failure, it raises one of these. The fact that a
    recommendation engine for integers can fail is itself a recommendation
    to reconsider your career choices.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-RE00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ColdStartError(RecommendationError):
    """Raised when the recommendation engine has insufficient data to generate suggestions.

    The user has not evaluated enough numbers for collaborative filtering to
    produce meaningful results. This is the recommendation engine equivalent
    of asking a sommelier to pair a wine with a meal they've never tasted.
    The system will fall back to popular items, which for FizzBuzz means
    numbers divisible by 15 — the crowd pleasers of modulo arithmetic.
    """

    def __init__(self, user_id: str, evaluated_count: int, minimum_required: int) -> None:
        super().__init__(
            f"Cold start for user '{user_id}': only {evaluated_count} evaluations "
            f"(minimum {minimum_required} required for personalized recommendations). "
            f"Falling back to popular items. Everyone loves multiples of 15.",
            error_code="EFP-RE01",
            context={
                "user_id": user_id,
                "evaluated_count": evaluated_count,
                "minimum_required": minimum_required,
            },
        )
        self.user_id = user_id
        self.evaluated_count = evaluated_count
        self.minimum_required = minimum_required


class SimilarityComputationError(RecommendationError):
    """Raised when cosine similarity computation encounters a degenerate case.

    Computing the cosine similarity between two zero-norm vectors is
    mathematically undefined — like dividing by zero, but for people who
    enjoy linear algebra. The recommendation engine has encountered a user
    or item with no discernible features, which in the FizzBuzz domain
    means a number that is somehow neither odd nor even, neither prime
    nor composite. A truly remarkable achievement in degeneracy.
    """

    def __init__(self, vector_a_name: str, vector_b_name: str, reason: str) -> None:
        super().__init__(
            f"Cosine similarity failed between '{vector_a_name}' and "
            f"'{vector_b_name}': {reason}. "
            f"The dot product of nothing with nothing is existential dread.",
            error_code="EFP-RE02",
            context={
                "vector_a": vector_a_name,
                "vector_b": vector_b_name,
                "reason": reason,
            },
        )
        self.vector_a_name = vector_a_name
        self.vector_b_name = vector_b_name


class FilterBlendingError(RecommendationError):
    """Raised when the hybrid blending of collaborative and content-based filters fails.

    The engine attempted to merge the outputs of two recommendation
    strategies — collaborative filtering ("users like you also enjoyed 45")
    and content-based filtering ("45 shares features with 15") — but
    something went wrong in the interpolation. Perhaps the serendipity
    factor injected too much chaos, or perhaps the 60/40 blend ratio
    violated some unwritten law of recommendation mathematics.
    """

    def __init__(self, collaborative_count: int, content_count: int, reason: str) -> None:
        super().__init__(
            f"Hybrid blending failed: {collaborative_count} collaborative candidates, "
            f"{content_count} content-based candidates. {reason}. "
            f"The recommendation pipeline has produced an existential blend error.",
            error_code="EFP-RE03",
            context={
                "collaborative_count": collaborative_count,
                "content_count": content_count,
                "reason": reason,
            },
        )
        self.collaborative_count = collaborative_count
        self.content_count = content_count


class RecommendationExplanationError(RecommendationError):
    """Raised when the explainer cannot articulate why a number was recommended.

    The recommendation engine knows *what* to recommend but cannot explain
    *why*. This is the FizzBuzz equivalent of a doctor prescribing medicine
    and then shrugging when asked about the diagnosis. The explainability
    module has failed, and the user must simply trust that 45 is, indeed,
    a number they would enjoy evaluating. Just trust the algorithm.
    """

    def __init__(self, recommended_number: int, source_number: int) -> None:
        super().__init__(
            f"Cannot explain why {recommended_number} was recommended based on "
            f"{source_number}. The algorithm knows, but it's not telling. "
            f"Some recommendations are beyond human comprehension.",
            error_code="EFP-RE04",
            context={
                "recommended_number": recommended_number,
                "source_number": source_number,
            },
        )
        self.recommended_number = recommended_number
        self.source_number = source_number

